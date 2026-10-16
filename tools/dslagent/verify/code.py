"""验收 code（改代码任务）：规划路径 v2 的验收 / 补改 / 边界复核，实现 verify/__init__.py 里写的验收接口，配套资料包是
packs/code.py（这里直接用它的文件遍历 / 片段 / grep 工具）。

验收一次（check）：全量测试（代码自上次真跑以来没变就复用）→ #清单 核对 → 查残留（只搜计划开头「# 旧写法: 正则」声明的，
范围限清单 / 改动文件所在的顶层目录，不含测试和本次新建的文件）；有缺口就组补改入参（缺口所在函数全文；定位不到函数时逐级回退：
失败栈涉及的改过的文件片段 → 本次改动所在函数 → diff），fix 派 1 次补改（FIX_SYS）。
边界复核（boundary）：一次短调用（BOUND_SYS）按任务原文 + diff 写 3–5 个 unittest 边界用例（写在任务目录 boundary/，不进项目），
跑；失败带失败信息派 1 次补改（BFIX_SYS），再跑用例和全量测试；仍失败 → 超出预期；补改弄坏现有测试 → 撤回补改，同样超出预期；
用例文件跑不起来（语法错、导入错）记下来，不算代码的问题。
"""
import ast
import difflib
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from .. import agents as AG
from ..packs import code as K
from ..packs.code import OLD_RX_LINE
from ..snap import changed, code_hash, diff_text, restore, snapshot
from ..v2 import Stop

NAME = "code"
TEST_TIMEOUT = 600
BOUND_TIMEOUT = 120
FN_CAP = 250             # 补改入参：单个函数最多给多少行
FIX_CAP = 40000          # 补改入参总字符
MISSING_MSG = "项目里探测不到测试（没有 tests/、test_*.py 或 pytest 配置），v2 要靠测试验收；可以传 test_cmd"

FIX_SYS = AG.FIX.system_text()

BOUND_SYS = AG.BOUND.system_text()

BFIX_SYS = AG.BFIX.system_text()


# ------------------------------------------------------------------ 项目快照 / 改法 / 测试


def apply_edits(project, edits):
    """全部能套才套（原子）。不改测试文件、不出项目。返回 (ok, 说明)。"""
    root = Path(project).resolve()
    new_txt = {}
    if not isinstance(edits, list) or not edits:
        return False, "没有 edits"
    for e in edits:
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) for k in ("file", "old", "new")):
            return False, f"edits 项格式不对：{str(e)[:120]}"
        rel = e["file"][2:] if e["file"].startswith("./") else e["file"]
        p = (root / rel).resolve()
        if p == root or root not in p.parents:
            return False, f"不允许改项目外的 {rel}"
        if K.is_test(rel):
            return False, f"不允许改测试文件 {rel}"
        cur = new_txt.get(rel, p.read_text(encoding="utf-8") if p.is_file() else None)
        if e["old"] == "":
            if cur is not None and cur.strip():
                return False, f"{rel} 已存在且非空，新建文件 old 不能为空"
            new_txt[rel] = e["new"]
            continue
        if cur is None:
            return False, f"{rel} 不存在"
        n = cur.count(e["old"])
        if n != 1:
            return False, f"{rel}: old 出现 {n} 次（应为 1）：{e['old'][:120]!r}"
        new_txt[rel] = cur.replace(e["old"], e["new"], 1)
    for rel, t in new_txt.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
    return True, f"已套 {len(edits)} 处，涉及 {sorted(new_txt)}"


def _test_verb():
    from ..common import _verb_module
    return _verb_module("跑测试")


def full_test(project, test_cmd):
    """跑一次全量测试：{passed, summary, sec}。"""
    m = _test_verb()
    t0 = time.time()
    rc, text = m.run_raw(Path(project).resolve(), test_cmd, int(os.environ.get("DSLAGENT_TEST_TIMEOUT") or TEST_TIMEOUT))
    s = m.summarize(Path(project).resolve(), rc, text)
    return {"passed": s["passed"] == "是", "summary": s["summary"], "sec": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ 5 验收


def enclosing(text, ln):
    """包含第 ln 行的最内层函数 (起, 止)；不在函数里返回 None。"""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    best = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.lineno - len(n.decorator_list)
            if a <= ln <= n.end_lineno and (best is None or n.end_lineno - a < best[1] - best[0]):
                best = (a, n.end_lineno)
    return best


def func_span(text, name):
    """名为 name（可带类名 A.f）的函数 / 类 (起, 止)。"""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    last = name.split(".")[-1]
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == last:
            return n.lineno - len(getattr(n, "decorator_list", [])), n.end_lineno
    return None


def scope_dirs(files):
    """查残留的范围：清单 / 改动文件所在的顶层目录（根目录下的文件就是它自己）。"""
    out = set()
    for f in files:
        parts = Path(f).parts
        out.add(parts[0] if len(parts) > 1 else f)
    return sorted(out)


def residuals(project, patterns, dirs, new_files):
    hits = []
    for s in patterns:
        try:
            rx = re.compile(s)
        except re.error:
            continue
        _, _, allh = K.grep(project, rx, limit=0, py_only=True, skip_tests=True, dirs=dirs)
        for rel, i, l in allh:
            if rel in new_files:
                continue
            hits.append({"文件": rel, "行": i, "该行": l.strip()[:200], "模式": s})
    return hits


def checklist_gaps(project, cl, changed_files):
    out = []
    for op, path, loc in (cl or {}).get("items") or []:
        exists = (Path(project) / path).is_file()
        if op in ("删", "删除"):
            ok = not exists
        elif op == "新建":
            ok = exists
        else:
            ok = exists and path in changed_files      # 位置（函数名）可能被正当删掉（改成 import），不核对
        if not ok:
            out.append({"文件": path, "操作": op, "位置": loc,
                        "说明": {"删": "该删没删", "删除": "该删没删", "新建": "该新建的文件不存在"}.get(op, "清单里要改，但文件没改动"
                                                                             if exists else "文件不存在")})
    return out


TB_LOC = re.compile(r"^\s+([\w./-]+\.py):(\d+)\s")


TRACE_REF = re.compile(r"(?:File \"([^\"\n]+)\", line (\d+)|([\w./-]+\.(?:py|zs|ui|entity)):(\d+))")


def _trace_refs(project, summary):
    """失败摘要里出现的 (项目内相对路径, 行号)，按出现顺序去重。"""
    root = str(Path(project).resolve()) + os.sep
    out = []
    for m in TRACE_REF.finditer(summary or ""):
        rel, ln = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if rel.startswith(root):
            rel = rel[len(root):]
        if (rel, int(ln)) not in out:
            out.append((rel, int(ln)))
    return out


def _fix_fallback(project, before, after, summary):
    """定位不到被改的源码函数时的退路：失败栈涉及的、本次改过的文件里行号前后各 30 行 → 本次改动所在函数 → diff。"""
    ch = set(changed(before, after))
    blks, total = [], 0
    for rel, ln in _trace_refs(project, summary):
        t = after.get(rel) if rel in ch else None
        if t is None:
            continue
        n = len(t.splitlines())
        s = K.snippet(project, rel, max(1, ln - 30), min(n, ln + 30), text=t)
        if total + len(s) > FIX_CAP:
            break
        total += len(s)
        blks.append(s)
    if blks:
        return "（没定位到函数；失败栈涉及的、本次改过的文件里相关片段，按行号前后各 30 行）\n\n" + "\n\n".join(blks)
    fn = _changed_funcs(project, before, after)
    if fn:
        return "（没定位到函数；本次改动所在函数的完整当前代码）\n\n" + fn
    diff = diff_text(before, after)
    return "未能定位，附 diff：\n" + (diff or "（本次没有任何文件改动）")


def _fix_user(project, task, gaps, before, after, test_summary=""):
    """补改入参：任务原文、新模块接口、缺口列表、每处缺口所在函数全文（当前代码）、文件开头。"""
    parts = [f"【任务原文】\n{task}"]
    news = [r for r in changed(before, after) if before.get(r) is None and r.endswith(".py") and after.get(r)]
    if news:
        parts.append("【本次新建的模块】\n" + "\n\n".join(
            f"（import 写法：from {K.modname(r)} import …）\n" + K.snippet(project, r, 1, 120) for r in news))
    parts.append("【缺口列表】\n" + "\n".join(f"{k}. {g['说明']}" for k, g in enumerate(gaps, 1)))
    if test_summary:
        parts.append("【全量测试失败摘要】\n" + test_summary[:4000])
    locs = []
    for g in gaps:
        if g.get("文件") and g.get("行"):
            locs.append((g["文件"], g["行"], None))
        elif g.get("文件") and g.get("位置"):
            locs.append((g["文件"], None, g["位置"]))
        elif g.get("文件"):
            locs.append((g["文件"], None, None))
    for l in (test_summary or "").splitlines():
        m = TB_LOC.match(l)
        if m and not K.is_test(m.group(1)):
            locs.append((m.group(1), int(m.group(2)), None))
    parts.append("【缺口所在函数的完整当前代码】")
    seen, total, got = set(), 0, False
    for rel in dict.fromkeys(x[0] for x in locs):
        t = K.read(project, rel)
        if t is None:
            continue
        n = len(t.splitlines())
        blk = [K.snippet(project, rel, 1, min(n, 25), text=t) + "\n（文件开头，供加 import）"]
        for r2, ln, name in locs:
            if r2 != rel:
                continue
            sp = (enclosing(t, ln) or (max(1, ln - 15), min(n, ln + 15))) if ln else \
                (func_span(t, name) if name else None) or (1, min(n, FN_CAP))
            a, b = sp[0], min(sp[1], sp[0] + FN_CAP - 1)
            if (rel, a) in seen:
                continue
            seen.add((rel, a))
            blk.append(K.snippet(project, rel, a, b, text=t))
        s2 = "\n\n".join(blk)
        if total + len(s2) > FIX_CAP:
            parts.append(f"（{rel} 等后面的代码超出长度上限，略）")
            break
        total += len(s2)
        got = got or len(blk) > 1
        parts.append(s2)
    if not got:
        parts.append(_fix_fallback(project, before, after, test_summary))
    return "\n\n".join(parts)


def _check_reply(rep):
    """补改回复在通用 {结果,状态,原因} 校验（dsl_task.check_reply）之上叠加的：状态 成功 时 结果.edits 的结构。rep 是已通过通用校验的回复。"""
    if rep["状态"] == "成功":
        res = rep.get("结果")
        ed = res.get("edits") if isinstance(res, dict) else None
        if not isinstance(ed, list) or not all(isinstance(e, dict) and all(isinstance(e.get(k), str)
                                                                            for k in ("file", "old", "new")) for e in ed):
            return "结果.edits 必须是 [{file, old, new}] 列表（都是字符串）"
    return None


def dispatch_fix(M, project, system, user, tag):
    """派 1 次补改（回复不合格重答 1 次），能套就套。返回记录 {状态, 原因, 说明, edits, 套用, 套用说明, files}。"""
    from tools import dsl_task as T
    rec = {"发生": True}

    def ask(text):
        p = T.parse_check(text, [], extra=_check_reply)
        return p["value"], "；".join(p["problems"]), p["repaired"]
    try:
        rep, bad, repaired = ask(M(system, user, tag))
        if bad and AG.AGENTS[tag].retry.times > 1:
            rep, bad, repaired = ask(M(system, user + f"\n\n【你上一次的回复不合格：{bad}。请严格按回复格式只输出 JSON。】", tag + "_reask"))
    except (Stop, RuntimeError) as e:
        return {"发生": False, "原因": f"没派成：{e}"}
    if repaired:
        rec["repaired"] = repaired
    if bad:
        rec.update(状态="回复不合格", 原因=bad)
        return rec
    res = rep.get("结果") if isinstance(rep.get("结果"), dict) else {}
    rec.update(状态=rep["状态"], 原因=str(rep.get("原因") or ""), 说明=str(res.get("说明") or "")[:1000])
    if isinstance(res.get("用例代码"), str) and res["用例代码"].strip():
        rec["用例代码"] = res["用例代码"]
    ed = res.get("edits") or []
    rec["edits"] = len(ed)
    if rep["状态"] == "成功" and ed:
        ok, msg = apply_edits(project, ed)
        if not ok:          # 整体套不上时逐条套，能套的先套上
            n_ok = sum(1 for e in ed if apply_edits(project, [e])[0])
            msg += f"；逐条套上 {n_ok}/{len(ed)}"
            ok = n_ok > 0
        rec.update(套用=ok, 套用说明=msg)
    return rec


# ------------------------------------------------------------------ 6 边界复核


def test_python(test_cmd):
    try:
        first = shlex.split(test_cmd or "")[0]
    except (IndexError, ValueError):
        return sys.executable
    return first if re.search(r"python[\d.]*$", Path(first).name) else sys.executable


def strip_code(text):
    t = (text or "").strip()
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", t, re.S)
    if m:
        return m.group(1).strip() + "\n"
    i = t.find("import ")
    return (t[i:] if i > 0 and not t.startswith(("import", "from", "#", '"""')) else t) + "\n"


FAIL_LINE = re.compile(r"^(FAIL|ERROR): (\w+) \(([^)]*)\)", re.M)


def run_boundary(project, test_cmd, bdir):
    """跑用例文件 bdir/test_boundary_v2.py。返回 {ok, ran, failed: [名], broken, tail, sec}。
    broken：用例文件本身跑不起来（语法错 / 导入错 / 一个用例都没跑到）。"""
    env = _test_verb().clean_env(PYTHONDONTWRITEBYTECODE="1", PROJ=str(Path(project).resolve()),
                                 PYTHONPATH=os.pathsep.join([str(bdir), str(Path(project).resolve())]))
    env.pop("PYTHONPYCACHEPREFIX", None)
    t0 = time.time()
    try:
        p = subprocess.run([test_python(test_cmd), "-m", "unittest", "-v", "test_boundary_v2"], cwd=project,
                           capture_output=True, text=True, timeout=BOUND_TIMEOUT, env=env, stdin=subprocess.DEVNULL)
        out, rc = (p.stderr or "") + (p.stdout or ""), p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"边界用例超过 {BOUND_TIMEOUT} 秒没跑完", None
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    ran = int(m.group(1)) if m else 0
    failed = [(n, c) for _, n, c in FAIL_LINE.findall(out)]
    broken = rc is None or ran == 0 or any("_FailedTest" in c or n == "test_boundary_v2" for n, c in failed)
    docs = _docs(bdir / "test_boundary_v2.py")
    return {"ok": rc == 0 and ran > 0, "ran": ran, "failed": [n for n, _ in failed],
            "failed_desc": [f"{n}（{docs.get(n, '')}）" if docs.get(n) else n for n, _ in failed],
            "broken": broken, "tail": out[-6000:], "sec": round(time.time() - t0, 1)}


def _docs(f):
    try:
        tree = ast.parse(Path(f).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return {}
    return {n.name: (ast.get_docstring(n) or "").strip().splitlines()[0] if ast.get_docstring(n) else ""
            for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test")}


def _changed_funcs(project, before, after, cap=FIX_CAP):
    """改动过的 .py 里，改动行所在函数的完整当前代码（新建文件给全文前 200 行）。"""
    parts, total = [], 0
    for rel in changed(before, after):
        a, b = before.get(rel), after.get(rel)
        if b is None or not rel.endswith(".py"):
            continue
        if a is None:
            s = K.snippet(project, rel, 1, 200, text=b)
        else:
            lines = set()
            sm = difflib.SequenceMatcher(None, a.splitlines(), b.splitlines(), autojunk=False)
            for tag, _, _, j1, j2 in sm.get_opcodes():
                if tag != "equal":
                    lines.update(range(j1 + 1, max(j1 + 1, j2) + 1))
            spans = sorted({enclosing(b, ln) or (max(1, ln - 10), ln + 10) for ln in lines})
            n = len(b.splitlines())
            s = "\n\n".join([K.snippet(project, rel, 1, min(n, 25), text=b) + "\n（文件开头）"] +
                            [K.snippet(project, rel, x, min(y, x + FN_CAP - 1), text=b) for x, y in spans])
        if total + len(s) > cap:
            break
        total += len(s)
        parts.append(s)
    return "\n\n".join(parts)



def boundary(M, project, plan_result):
    """边界复核（plan_result 见 verify/__init__.py；另用 out、bound）。返回 {状态, 原因}。"""
    task, test_cmd, base = plan_result["task"], plan_result["test_cmd"], plan_result["base"]
    out, bound = plan_result["out"], plan_result["bound"]
    cur = snapshot(project)
    diff = diff_text(base, cur)
    bdir = out / "boundary"
    bdir.mkdir(parents=True, exist_ok=True)
    bound["跑了"] = True
    why = ""
    try:
        code = strip_code(M(BOUND_SYS, f"【任务原文】\n{task}\n\n【改动（diff，新建文件给全文）】\n{diff}", "bound"))
        if not re.search(r"^\s*def test", code, re.M):
            why = "模型回复里没有任何 def test 用例"
    except (Stop, RuntimeError) as e:
        why = f"没生成用例（{e}）"
    if why:                 # 没拿到用例不能当通过（引擎出错 / 额度用完 / 超时 / 空回复）
        bound["结论"] = f"未复核：{why}"
        bound["未复核"] = True
        return {"状态": "超出预期", "原因": f"边界复核没做成：{why}"}
    (bdir / "test_boundary_v2.py").write_text(code, encoding="utf-8")
    r = run_boundary(project, test_cmd, bdir)
    bound["第1次"] = {k: r[k] for k in ("ok", "ran", "failed_desc", "broken", "sec")}
    (bdir / "run1.txt").write_text(r["tail"], encoding="utf-8")
    if r["ok"]:
        bound["结论"] = f"{r['ran']} 个用例全过"
        return {"状态": "成功", "原因": ""}
    if r["broken"]:
        bound["结论"] = f"用例文件跑不起来，未复核：{r['tail'][-300:]}"
        bound["未复核"] = True
        return {"状态": "成功", "原因": ""}
    names = "、".join(r["failed_desc"])
    user = (f"【任务原文】\n{task}\n\n【改动（diff）】\n{diff}\n\n【边界用例】\n```python\n{code}```\n\n"
            f"【没过的用例和输出】\n{r['tail'][-5000:]}\n\n【改动所在函数的完整当前代码】\n{_changed_funcs(project, base, cur)}")
    fx = dispatch_fix(M, project, BFIX_SYS, user, "bfix")
    new_case = strip_code(fx.pop("用例代码", "")) if fx.get("用例代码") and fx.get("状态") == "成功" else ""
    bound["补改"] = dict(fx, 改了用例=bool(new_case))
    if new_case:            # 用例自身的编程错误：换成改好的用例文件（原文件留作 test_boundary_v2.run1.py）
        (bdir / "test_boundary_v2.run1.py").write_text(code, encoding="utf-8")
        (bdir / "test_boundary_v2.py").write_text(new_case, encoding="utf-8")
    after = snapshot(project)
    if not changed(cur, after) and not new_case:
        bound["结论"] = f"用例没过：{names}；补改没改代码（{fx.get('状态', '')}：{fx.get('原因', '')[:200]}）"
        return {"状态": "超出预期", "原因": f"边界复核：用例 {names} 没过；补改没有改代码"
                + (f"（补改说：{fx.get('原因', '')[:200]}）" if fx.get("原因") else "")}
    r2 = run_boundary(project, test_cmd, bdir)
    bound["第2次"] = {k: r2[k] for k in ("ok", "ran", "failed_desc", "broken", "sec")}
    (bdir / "run2.txt").write_text(r2["tail"], encoding="utf-8")
    t = test_now(project, plan_result, after, "边界补改后")
    if not t["passed"]:
        restore(project, cur, changed(cur, after))
        bound["结论"] = f"用例 {names} 没过；补改弄坏了现有测试，已撤回"
        return {"状态": "超出预期", "原因": f"边界复核：用例 {names} 没过；补改会让现有测试失败，已撤回补改"}
    if r2["ok"]:
        what = "、".join(x for x, y in (("改了代码", changed(cur, after)), ("修了用例自身的错", new_case)) if y)
        bound["结论"] = f"用例 {names} 第 1 次没过，补改（{what}）后全过"
        return {"状态": "成功", "原因": ""}
    if r2["broken"]:
        bound["结论"] = f"用例 {names} 没过；补改后用例文件跑不起来：{r2['tail'][-300:]}"
        return {"状态": "超出预期", "原因": f"边界复核：用例 {names} 没过；补改后用例文件跑不起来"}
    left = "、".join(r2["failed_desc"]) or names
    bound["结论"] = f"补改后用例 {left} 仍没过"
    return {"状态": "超出预期", "原因": f"边界复核：补改后用例 {left} 仍没过"}


# ------------------------------------------------------------------ 验收接口（见 verify/__init__.py）


def detect_cmd(project, given):
    from ..common import detect_test_cmd
    return given or detect_test_cmd(project)


def setup(out, cmd):
    os.environ["DSLAGENT_STATE"] = str(Path(out) / "state")
    os.environ["DSLAGENT_TEST_CMD"] = cmd
    os.environ.setdefault("DSLAGENT_TEST_TIMEOUT", str(TEST_TIMEOUT))


def test_now(project, plan_result, snap_now, tag):
    """全量测试一次：代码自上次真跑（known）以来没变就复用；记进计划内测试记录和验收记录的「测试」。"""
    tests, accept = plan_result["tests"], plan_result["accept"]
    h = code_hash(snap_now)
    last = next((x for x in reversed(tests) if x["mode"] == "real" and x.get("known")), None)
    if last and last["hash"] == h:
        r = {"passed": last["passed"], "summary": last["summary"], "sec": 0.0, "mode": "复用"}
    else:
        r = dict(full_test(project, plan_result["test_cmd"]), mode="真跑")
        tests.append({"line": tag, "mode": "real", "sec": r["sec"], "passed": r["passed"],
                      "summary": r["summary"][:4000], "hash": h, "known": True})
    accept.setdefault("测试", []).append({"步": tag, "通过": r["passed"], "秒": r["sec"], "方式": r["mode"]})
    return r


def check(project, plan_result, checklist):
    """验收一次（见 verify/__init__.py）。stage=验收 时定下查残留的旧写法和范围（记进 accept），没通过就组补改入参。"""
    base, cur, accept = plan_result["base"], plan_result["cur"], plan_result["accept"]
    after_fix = plan_result.get("stage") == "补改后"
    if not after_fix:
        old_rx = OLD_RX_LINE.findall(plan_result["main"])
        ch = changed(base, cur)
        cl_files = [p for _, p, _ in (checklist or {}).get("items") or []]
        accept.update(旧写法=old_rx, 范围=scope_dirs(ch + cl_files))
    old_rx, dirs = accept["旧写法"], accept["范围"]
    chn = changed(base, cur)
    hits = residuals(project, old_rx, dirs, {r for r in chn if base.get(r) is None}) if old_rx else []
    gaps = checklist_gaps(project, checklist, set(chn))
    t = test_now(project, plan_result, cur, plan_result.get("stage") or "验收")
    if after_fix:
        accept.update(补改后残留=len(hits), 补改后残留列表=hits[:40], 补改后清单缺口=gaps)
    else:
        accept.update(残留=len(hits), 残留列表=hits[:40], 清单缺口=gaps)
    ok = t["passed"] and not hits and not gaps
    glist = []
    if not ok and not after_fix:
        glist = [dict(h, 说明=f"{h['文件']}:{h['行']} 还有旧写法（匹配 {h['模式']}）：{h['该行']}") for h in hits[:30]]
        glist += [dict(g, 说明=f"清单 {g['操作']} {g['文件']}{':' + g['位置'] if g.get('位置') else ''}：{g['说明']}")
                  for g in gaps]
        if not t["passed"]:
            glist.append({"说明": "全量测试没过（失败摘要见下）"})
    why = [] if t["passed"] else ["全量测试没过：" + t["summary"][:300]]
    why += [f"仍有 {len(hits)} 处旧写法残留（{hits[0]['文件']}:{hits[0]['行']}）"] if hits else []
    why += ["清单没做到：" + "；".join(f"{g['操作']} {g['文件']}" for g in gaps[:4])] if gaps else []
    return {"通过": ok, "缺口列表": glist, "补改系统": FIX_SYS,
            "补改入参": _fix_user(project, plan_result["task"], glist, base, cur, "" if t["passed"] else t["summary"])
            if glist else None,
            "原因": "" if ok else "验收没过（已派 1 次补改）：" + "；".join(why), "测试摘要": t["summary"][:2000]}


def fix(M, project, chk, tag="fix"):
    """按 check 的出参派 1 次补改。"""
    return dispatch_fix(M, project, chk["补改系统"], chk["补改入参"], tag)
