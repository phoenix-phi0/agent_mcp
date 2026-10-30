# -*- coding: utf-8 -*-
"""kg_v4 跨模块调用核对（常驻检查）：约定里「调用 模块.函数 k=v …」与被调函数的函数头逐个对。

    cd /workspace/agent_mcp && .venv/bin/python -m pytest tests/kg_v4/test_xcall.py -q
    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_xcall.py        # 直接跑，打印明细

为什么要有它：现有「约定检查」只查函数存在且公开，不查参数名；调用方传了被调函数不认识的参数、漏传必填参数，
要等 change2 落地后「比对约定」才暴露（K75c2 的失败模式）。这里在约定层提前兜住，每个模块 change2 合并后都应再跑一遍。

核对项（读 kg_v4/contracts/*.md 和 kg_v4/plan/top.zs，不需要实现，离线）：
  1. 伪代码里的「调用 模块.函数 k=v」、「调用 [本模块] 函数 k=v」（函数是本模块的），用例里的「调用 f」「先 调用 m.f」：
     被调函数存在且公开（跨模块）、传的每个参数名都在被调函数入参里、必填入参都传了
  2. top.zs 的依赖 == 约定里的依赖、实际调用的模块都在依赖里、没有多余依赖、依赖无环
  3. 跨模块被调用的公开函数都在被调模块 top.zs 的「提供」里
只写文字、没写 k=v 的调用无法核对参数名，数量单独报出（不算失败）。
"""

import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

NAMES = ("subject kg lesson progress account quiz vocab dictation teacher_rules tutor report textbook_import "
         "assist_common assist_kg assist_setting assist_draft assist_file teacher_assist").split()
IDENT = r"[A-Za-z0-9_一-鿿]+"


def _kv_after(text, pos):
    """「调用 X」之后按空白切词收 k= 的参数名；全角括号里的说明先去掉；遇到 ，；。、或「得/取/报错/返回」等词停。"""
    seg = re.sub(r"（[^）]*）", " ", text[pos:])
    names = []
    for tok in seg.split():
        m = re.match(r"^([a-z][a-z0-9_]*)=", tok)
        if m:
            names.append(m.group(1))
        if re.search(r"[，；。、]", tok) or tok in ("得", "取", "取不到", "报错", "返回", "看", "则", "时", "得到"):
            break
    return names


def run_xcall(kg_dir):
    """核对 kg_dir（含 contracts/、plan/top.zs）。返回 dict：
    总数 / 跨模块不一致 [(调用方, 位置, 说明)] / 模块内疑点 / top问题 / 提供未列 / 无参调用数。"""
    from tools.dslagent.packs.dslproj import contract as C
    from tools.dslagent.v3 import top as vtop

    root = Path(kg_dir)
    mods = {}
    for n in NAMES:
        c, probs = C.parse((root / "contracts" / f"{n}.md").read_text(encoding="utf-8"))
        assert not probs, (n, probs)
        mods[n] = c
    fns = {n: {f["名"]: f for f in c["函数"]} for n, c in mods.items()}

    noargs, own_problems, problems, calls = set(), set(), [], []
    total = 0

    def check_call(caller, where, mod, fn, given):
        nonlocal total
        total += 1
        calls.append((caller, mod, fn))
        bucket = (lambda msg: own_problems.add((caller, where, msg))) if mod == caller else \
                 (lambda msg: problems.append((caller, where, msg)))
        if mod not in fns:
            return bucket(f"调用 {mod}.{fn}：没有模块 {mod}")
        f = fns[mod].get(fn)
        if f is None:
            return bucket(f"调用 {mod}.{fn}：{mod} 没有函数「{fn}」")
        if mod != caller and not f["公开"]:
            bucket(f"调用 {mod}.{fn}：不是公开函数")
        if not given:
            noargs.add((caller, where, f"{mod}.{fn}"))
            return
        req, opt, _ = C.params(f)
        allp = set(req) | set(opt)
        for g in given:
            if g not in allp:
                bucket(f"调用 {mod}.{fn}：传了 {g}=，但 {mod}.{fn} 的入参是 [{' '.join(f['入参'])}]")
        for r in req:
            if r not in given:
                bucket(f"调用 {mod}.{fn}：必填入参 {r} 没传（传了 {given}）")

    for n, c in mods.items():
        for f in c["函数"]:
            for p in f["伪代码"]:
                t = p["文字"]
                where = f"{n}.md:{p['行']}（函数 {f['名']}）"
                for m in re.finditer(rf"调用\s*({IDENT})\.({IDENT})", t):
                    if m.group(1) in mods:        # 「调用 kg./lesson.」之类泛指、或 doc.读文档 这类动词前缀不算
                        check_call(n, where, m.group(1), m.group(2), _kv_after(t, m.end()))
                for m in re.finditer(rf"调用\s*(?:本模块\s*)?({IDENT})(?![\w.一-鿿])", t):
                    fn = m.group(1)
                    if fn == "本模块" or fn not in fns[n] or t[m.start():m.end() + 1].endswith("."):
                        continue
                    check_call(n, where, n, fn, _kv_after(t, m.end()))
        for u in c["用例"]:
            where = f"{n}.md:{u['行']}（用例 {u['名']}）"
            for st in u["先"]:
                if st["种类"] == "调用":
                    mod, _, fn = st["目标"].rpartition(".")
                    check_call(n, where, mod or n, fn, list(st["参数"].keys()))
            if u["调用"]:
                check_call(n, where, n, u["调用"]["目标"], list(u["调用"]["参数"].keys()))

    tp, tprobs = vtop.parse((root / "plan" / "top.zs").read_text(encoding="utf-8"))
    assert not tprobs, tprobs
    tmods = {m["名"]: m for m in tp["模块"]}
    top_issues = []
    for n in NAMES:
        if set(mods[n]["依赖"]) != set(tmods[n]["依赖"]):
            top_issues.append(f"{n}：约定依赖 {sorted(mods[n]['依赖'])} ≠ top.zs 依赖 {sorted(tmods[n]['依赖'])}")
        called = {m for (cn, m, _) in calls if cn == n and m != n}
        for d in sorted(called - set(tmods[n]["依赖"])):
            top_issues.append(f"{n}：伪代码/用例调了 {d}，但 top.zs 依赖里没有 {d}")
        for d in sorted(set(tmods[n]["依赖"]) - called):
            top_issues.append(f"{n}：top.zs 依赖 {d}，但伪代码/用例没有调用 {d}（多余依赖）")
    color = {}

    def dfs(x, path):
        color[x] = 1
        for d in tmods[x]["依赖"]:
            if color.get(d) == 1:
                top_issues.append("依赖有环：" + " → ".join(path + [x, d]))
            elif d not in color:
                dfs(d, path + [x])
        color[x] = 2

    for n in NAMES:
        if n not in color:
            dfs(n, [])
    prov = sorted({f"{cn} 调用 {mod}.{fn}，但 top.zs 里 {mod} 的「提供」没列 {fn}"
                   for (cn, mod, fn) in calls
                   if cn != mod and fn in fns.get(mod, {}) and fns[mod][fn]["公开"] and fn not in tmods[mod]["提供"]})
    seen, uniq = set(), []
    for p in problems:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return {"总数": total, "跨模块不一致": uniq, "模块内疑点": sorted(own_problems), "top问题": top_issues,
            "提供未列": prov, "无参调用数": len(noargs)}


def _real():
    return run_xcall(ROOT / "kg_v4")


def test_xcall_cross_module_params():
    """跨模块调用：函数存在且公开、参数名都在被调入参里、必填都传了。"""
    r = _real()
    assert r["总数"] > 1000, r["总数"]          # 解析到的调用数不该骤降（解析器坏了会变 0）
    assert not r["跨模块不一致"], "\n".join(f"[{c}] {w}: {m}" for c, w, m in r["跨模块不一致"][:20])


def test_xcall_module_internal_calls():
    r = _real()
    assert not r["模块内疑点"], "\n".join(f"[{c}] {w}: {m}" for c, w, m in r["模块内疑点"][:20])


def test_xcall_top_zs_consistent():
    """top.zs 依赖与约定依赖一致、无多余依赖、无环；被跨模块调用的公开函数都在「提供」里。"""
    r = _real()
    assert not r["top问题"], "\n".join(r["top问题"][:20])
    assert not r["提供未列"], "\n".join(r["提供未列"][:20])


def test_xcall_detects_bad_param(tmp_path=None):
    """自检：往拷贝里塞一个被调函数不认识的参数名，应当被查出来（防止检查器静默失效）。"""
    tmp = Path(tempfile.mkdtemp(prefix="xcall_selftest_"))
    try:
        dst = tmp / "kg_v4"
        shutil.copytree(ROOT / "kg_v4", dst, ignore=shutil.ignore_patterns("app.db", "web", "uploads", "__pycache__"))
        f = dst / "contracts" / "account.md"
        text = f.read_text(encoding="utf-8")
        old = "调用 subject.登记学生 learner=username code=jp_grammar"
        assert old in text
        f.write_text(text.replace(old, "调用 subject.登记学生 learner=username bogus_arg=1 code=jp_grammar", 1), encoding="utf-8")
        r = run_xcall(dst)
        assert any("bogus_arg" in m for _, _, m in r["跨模块不一致"]), r["跨模块不一致"][:3]
        f.write_text(text.replace(old, "调用 subject.登记学生 code=jp_grammar", 1), encoding="utf-8")
        r = run_xcall(dst)
        assert any("必填入参 learner" in m for _, _, m in r["跨模块不一致"]), r["跨模块不一致"][:3]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    r = _real()
    print(f"跨模块/模块内调用共核对 {r['总数']} 处（含用例）")
    print(f"== 跨模块不一致 {len(r['跨模块不一致'])} 条")
    for c, w, m in r["跨模块不一致"]:
        print(f"  [{c}] {w}: {m}")
    print(f"== 只写文字、没写 k=v 参数的调用（无法核对参数名）{r['无参调用数']} 处")
    print(f"== 本模块内部互调疑点 {len(r['模块内疑点'])} 条")
    for c, w, m in r["模块内疑点"]:
        print(f"  [{c}] {w}: {m}")
    print(f"== top.zs 问题 {len(r['top问题'])} 条")
    for x in r["top问题"]:
        print("  ", x)
    print(f"== 提供列表未列 {len(r['提供未列'])} 条")
    for x in r["提供未列"]:
        print("  ", x)
    sys.exit(1 if r["跨模块不一致"] or r["模块内疑点"] or r["top问题"] or r["提供未列"] else 0)
