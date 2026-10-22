# -*- coding: utf-8 -*-
"""#改法 块写 JSON + 改文件 / 核对计划 / verify.code.apply_edits 共用一套套用规则（old 唯一 / line 选最近 / 全有或全无）。不调模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_editsrule.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_editsrule_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ.pop("DSLAGENT_RULES", None)
(TMP / "state").mkdir()

from tools import dsl_sections as DS                                  # noqa: E402
from tools.dslagent import plan as P, scope as SC                     # noqa: E402
from tools.dslagent.common import _verb_module                        # noqa: E402
from tools.dslagent.engine import AgentEngine                         # noqa: E402
from tools.dslagent.verify import code as VC                          # noqa: E402
from tools.mock import MockClient                                     # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  ✓ " if cond else "  ✗ ") + msg + ("" if cond or extra == "" else f"\n      {str(extra)[:900]}"))


# 第 1、5 行都有 `返回 p`，第 3 行没有；x.zs 共 8 行
XZS = "函数 a\n  返回 p\n  设 z = 1\n结束\n函数 b\n  返回 p\n结束\n尾\n"


def project(name, files=None):
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    for rel, text in (files or {"services/x.zs": XZS, "services/y.zs": "甲\n"}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    return d


def run(proj, edits, extra_head=""):
    """脚本末尾 #改法 e1 写 JSON（多行），跑 设 res = 改文件 {e1}，返回 (res, engine)。"""
    body = "[\n" + ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in edits) + "\n]" if isinstance(edits, list) else edits
    m = MockClient(handler=lambda p, s=None: "嗯", offline=True)
    eng = AgentEngine(client=m, workdir=proj, verbose=False, verbs_root=P.PKG / "verbs")
    eng.run(f"用包 common text code\n{extra_head}设 res = 改文件 {{e1}}\n\n#改法 e1\n{body}\n")
    return eng.vars["res"], eng


def read(proj, rel):
    return (Path(proj) / rel).read_text(encoding="utf-8")


def t_block():
    print("一、#改法 块写 JSON")
    p = project("blk")
    # 带 {p} 的新文本：引擎不能把它当插值；变量 p 已设
    r, eng = run(p, [{"file": "services/y.zs", "old": "甲", "new": "返回 {p}\n  设 q = {p}.x"}], extra_head="设 p = 被展开了\n")
    check(r["ok"] == "是" and read(p, "services/y.zs") == "返回 {p}\n  设 q = {p}.x\n", "多行 JSON 套上，{p} 原样写进文件、不被展开", (r, read(p, "services/y.zs")))
    check(eng.vars["e1"]["edits"][0]["new"].startswith("返回 {p}"), "e1 变量里 {p} 也是字面")
    rest, secs, _, probs = DS.split_sections('x\n#改法 e1\n{"edits": [{"file": "a", "old": "", "new": "n"}]}\n')
    check(not probs and secs["e1"]["edits"][0]["file"] == "a", "也接受 {\"edits\": […]}", (secs, probs))
    _, secs, _, probs = DS.split_sections('#改法 e1\n[{"file":"a","old":"o","new":"n","line":3}]\n')
    check(secs["e1"]["edits"][0]["line"] == 3 and not probs, "line 原样保留")
    _, _, _, probs = DS.split_sections("#改法 e1\n[{\"file\": \"a\",\n")
    check(len(probs) == 1 and "JSON 解析失败" in probs[0] and "#改法 e1" in probs[0], "JSON 写坏 → 段问题", probs)
    _, _, _, probs = DS.split_sections("#改法 e1\n[]\n")
    check(len(probs) == 1 and "空" in probs[0], "空列表 → 段问题", probs)
    _, _, _, probs = DS.split_sections("#改法 e1\n{\"a\": 1}\n")
    check(len(probs) == 1 and "列表" in probs[0], "不是列表的对象 → 段问题", probs)
    _, secs, _, probs = DS.split_sections("#改法 e1\n@@ 改 a.py\n<<<<<<< 原文\nA\n=======\nB\n>>>>>>> 新文\n")
    check(not probs and secs["e1"]["edits"] == [{"file": "a.py", "old": "A", "new": "B"}], "旧 @@ 标记写法仍可解析（其它包在用）")
    _, _, _, probs = DS.split_sections('#改法 e1\n[{"file":"a","old":"o","new":"n"}]\n设 x = 1\n')
    check(len(probs) == 1 and "JSON" in probs[0], "段后面多写了语句 → 报（不静默吞掉）", probs)
    # 全流程：plan 的白名单检查认 JSON 段
    script = "用包 common text code\n设 res = 改文件 {e1}\n终止 成功 好\n\n#改法 e1\n[\n  {\"file\": \"services/y.zs\", \"old\": \"甲\", \"new\": \"乙\"}\n]\n"
    probs = P.whitelist_check(P.strip_prose(script)[0], {})
    check(probs == [], "whitelist_check 跳过 JSON 段、不误报", probs)


def t_rules():
    print("二、改文件 套用规则")
    p = project("r1")
    r, _ = run(p, [{"file": "services/y.zs", "old": "甲", "new": "乙"}])
    check(r["ok"] == "是" and read(p, "services/y.zs") == "乙\n", "old 唯一直接套", r)
    p = project("r2")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q", "line": 6}])
    got = read(p, "services/x.zs")
    check(r["ok"] == "是" and got == XZS.replace("  返回 p\n结束\n尾", "  返回 q\n结束\n尾"), "出现 2 次 + 正确 line=6 → 改第二处", (r, got))
    p = project("r3")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q", "line": 1}])
    check(r["ok"] == "是" and read(p, "services/x.zs").startswith("函数 a\n  返回 q"), "line=1（偏了 1 行）仍选最近的第 2 行那处", r)
    p = project("r3b")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q", "line": 5}])
    check(r["ok"] == "是" and read(p, "services/x.zs").splitlines()[5] == "  返回 q", "line=5（偏 1 行）选第 6 行那处", r)
    p = project("r3c")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q", "line": 99}])
    check(r["ok"] == "是" and read(p, "services/x.zs").splitlines()[5] == "  返回 q", "line=99 偏得远也选最近（第 6 行那处）", r)
    p = project("r4")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q", "line": 4}])
    check(r["ok"] == "否" and "一样近" in r["msg"] and read(p, "services/x.zs") == XZS, "并列最近（第 2、6 行到 4 一样远）→ 报错、不写", r)
    p = project("r5")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q"}])
    check(r["ok"] == "否" and "出现 2 次" in r["msg"] and "没给 line" in r["msg"] and "第 2 行" in r["msg"] and "第 6 行" in r["msg"]
          and read(p, "services/x.zs") == XZS, "无 line 且不唯一 → 报错并列各处行号", r)
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "x", "line": "abc"}])
    check(r["ok"] == "否" and "line" in r["msg"], "line 不是整数 → 报错", r)
    p = project("r6")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  设 z = 1\n  设 w = 2", "new": "x"}])
    check(r["ok"] == "否" and "出现 0 次" in r["msg"] and "第 1 条" in r["msg"] and "services/x.zs" in r["msg"] and "第 3 行" in r["msg"],
          "0 处 → 报错带条号、文件、近似行提示", r)
    p = project("r7")
    r, _ = run(p, [{"file": "services/new.zs", "old": "", "new": "新\n"}])
    check(r["ok"] == "是" and read(p, "services/new.zs") == "新\n", "old 空 = 新建", r)
    r, _ = run(p, [{"file": "services/y.zs", "old": "", "new": "覆盖"}])
    check(r["ok"] == "否" and "已存在" in r["msg"] and read(p, "services/y.zs") == "甲\n", "old 空而文件已存在 → 报错", r)
    p = project("r8")
    r, _ = run(p, [{"file": "services/y.zs", "old": "甲", "new": "乙"}, {"file": "services/x.zs", "old": "不存在的", "new": "x"},
                   {"file": "services/n.zs", "old": "", "new": "n"}])
    check(r["ok"] == "否" and "第 2 条" in r["msg"] and read(p, "services/y.zs") == "甲\n" and not (p / "services/n.zs").exists(),
          "一条错整体不写（前面的改、后面的新建都没落盘）", r)
    p = project("r9")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  设 z = 1", "new": "  设 z = 2"}, {"file": "services/x.zs", "old": "  设 z = 1", "new": "y"},
                   {"file": "nope.zs", "old": "a", "new": "b"}])
    check(r["ok"] == "否" and "第 2 条" in r["msg"] and "冲突" in r["msg"] and "第 3 条" in r["msg"] and "没有这个文件" in r["msg"],
          "逐条报错：第 2 条与第 1 条冲突、第 3 条文件不存在，一次全列", r)
    p = project("r10")
    r, _ = run(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q", "line": 6},
                   {"file": "services/x.zs", "old": "  返回 p", "new": "  返回 r", "line": 2}])
    got = read(p, "services/x.zs").splitlines()
    check(r["ok"] == "是" and got[1] == "  返回 r" and got[5] == "  返回 q", "同文件两条按顺序叠加，第二条按 line 选到剩下的那处", (r, got))
    p = project("r11")
    r, _ = run(p, [{"file": "tests/test_x.py", "old": "", "new": "x"}])
    check(r["ok"] == "否" and "测试文件" in r["msg"], "不许写测试文件（约束不变）", r)
    r, _ = run(p, [{"file": "../out.zs", "old": "", "new": "x"}])
    check(r["ok"] == "否" and "越界" in r["msg"], "不许越出项目（约束不变）", r)
    # CRLF 文件
    p = project("r12", {"services/c.zs": "a\r\n  返回 p\r\nb\r\n  返回 p\r\n"})
    r, _ = run(p, [{"file": "services/c.zs", "old": "  返回 p", "new": "  返回 q", "line": 4}])
    check(r["ok"] == "是" and (p / "services/c.zs").read_bytes() == b"a\r\n  \xe8\xbf\x94\xe5\x9b\x9e p\r\nb\r\n  \xe8\xbf\x94\xe5\x9b\x9e q\r\n", "CRLF 保持，line 选对", r)


def t_apply_edits():
    print("三、verify.code.apply_edits 与 改文件 同一套规则")
    p = project("a1")
    ok, msg = VC.apply_edits(p, [{"file": "services/y.zs", "old": "甲", "new": "乙"}, {"file": "services/x.zs", "old": "不存在", "new": "x"}])
    check(not ok and "第 2 条" in msg and read(p, "services/y.zs") == "甲\n", "一条错整体不套（不再逐条套上能套的）", (ok, msg))
    ok, msg = VC.apply_edits(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "  返回 q", "line": 6}])
    check(ok and read(p, "services/x.zs").splitlines()[5] == "  返回 q", "line 选最近", (ok, msg))
    ok, msg = VC.apply_edits(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "q"}])
    check(ok, "剩下只有一处时直接套", msg)
    p = project("a2")
    ok, msg = VC.apply_edits(p, [{"file": "services/x.zs", "old": "  返回 p", "new": "q"}])
    check(not ok and "没给 line" in msg and read(p, "services/x.zs") == XZS, "多处无 line 报错", msg)
    ok, msg = VC.apply_edits(p, [{"file": "services/y.zs", "old": "", "new": "x"}])
    check(not ok and "已存在" in msg, "old 空而文件已存在报错", msg)
    ok, msg = VC.apply_edits(p, [{"file": "services/new.zs", "old": "", "new": "x"}])
    check(ok and read(p, "services/new.zs") == "x", "old 空新建", msg)
    ok, msg = VC.apply_edits(p, [{"file": "tests/test_a.py", "old": "", "new": "x"}])
    check(not ok and "测试文件" in msg, "测试文件不许改", msg)
    ok, msg = VC.apply_edits(p, [])
    check(not ok, "空 edits 报错")
    p = project("a3", {"services/c.zs": "a\r\nb\r\n"})
    ok, _ = VC.apply_edits(p, [{"file": "services/c.zs", "old": "a", "new": "z"}])
    check(ok and (p / "services/c.zs").read_bytes() == b"z\r\nb\r\n", "CRLF 文件套完仍是 CRLF")
    # 同一函数：分发补改时整体套不上就是没套上
    p = project("a4")
    reply = {"result": {"edits": [{"file": "services/y.zs", "old": "甲", "new": "乙"}, {"file": "services/y.zs", "old": "没有", "new": "x", "line": 1}],
                        "说明": "x"}, "status": "成功", "reason": ""}
    rec = VC.dispatch_fix(lambda s, u, t: json.dumps(reply, ensure_ascii=False), p, "sys", "usr", "fix")
    check(rec.get("套用") is False and read(p, "services/y.zs") == "甲\n" and "逐条套上" not in rec.get("套用说明", ""),
          "dispatch_fix：整体套不上就是没套上，不再「逐条套上 n/m」", rec)
    reply["result"]["edits"] = [{"file": "services/y.zs", "old": "甲", "new": "乙", "line": 1}]
    rec = VC.dispatch_fix(lambda s, u, t: json.dumps(reply, ensure_ascii=False), p, "sys", "usr", "fix")
    check(rec.get("套用") is True and read(p, "services/y.zs") == "乙\n", "dispatch_fix：回复里的 line 字段接受并套上", rec)


def t_check_plan():
    print("四、核对计划（预检）同规则")
    p = project("c1")
    chk = _verb_module("改文件").核对计划
    secs = {"e1": {"edits": [{"file": "services/x.zs", "old": "  返回 p", "new": "q", "line": 6}]}}
    check(chk(p, secs) == [], "多处 + line 能选出 → 预检通过", chk(p, secs))
    secs = {"e1": {"edits": [{"file": "services/x.zs", "old": "  返回 p", "new": "q"}]}}
    pr = chk(p, secs)
    check(len(pr) == 1 and "#改法 e1" in pr[0] and "没给 line" in pr[0] and "第 2 行" in pr[0] and "第 6 行" in pr[0], "多处无 line → 预检报各处行号", pr)
    secs = {"e1": {"edits": [{"file": "services/x.zs", "old": "  返回 p", "new": "q", "line": 4}]}}
    pr = chk(p, secs)
    check(len(pr) == 1 and "一样近" in pr[0], "并列最近 → 预检报错", pr)
    secs = {"e1": {"edits": [{"file": "services/x.zs", "old": "  设 z = 1", "new": "  设 z = 2"}, {"file": "services/x.zs", "old": "  设 z = 1", "new": "y"},
                             {"file": "services/y.zs", "old": "", "new": "x"}]}}
    pr = chk(p, secs)
    check(len(pr) == 2 and "第 2 条" in pr[0] and "冲突" in pr[0] and "第 3 条" in pr[1] and "已存在" in pr[1], "逐条列：冲突、新建已存在", pr)
    check(read(p, "services/x.zs") == XZS, "预检只读")
    # 与 改文件 的结论一致
    for ed in ([{"file": "services/x.zs", "old": "  返回 p", "new": "q", "line": 6}], [{"file": "services/x.zs", "old": "  返回 p", "new": "q"}],
               [{"file": "services/x.zs", "old": "  返回 p", "new": "q", "line": 4}], [{"file": "services/x.zs", "old": "没有", "new": "q"}]):
        q = project("c2")
        r, _ = run(q, ed)
        check((chk(q, {"e1": {"edits": ed}}) == []) == (r["ok"] == "是"), f"预检与实际套用结论一致：{ed[0]['old']!r} line={ed[0].get('line')}")
    # dslcheck.edit_problems 走 JSON 段
    from tools.dslagent import dslcheck as DC
    sc = '用包 common text code\n设 res = 改文件 {e1}\n终止 成功 好\n\n#改法 e1\n[{"file": "services/x.zs", "old": "  返回 p", "new": "q"}]\n'
    pr = DC.edit_problems(p, sc)
    check(len(pr) == 1 and "没给 line" in pr[0], "dslcheck.edit_problems 读 JSON 段并预检", pr)


def t_fix_input():
    print("五、补改入参带本模块全部文件；读片段 通配")
    from tools.dslagent.packs import dslproj as DPJ
    sol = ROOT / "tests" / "tools" / "fixtures" / "dslproj_solution"
    p = TMP / "fi"
    shutil.rmtree(p, ignore_errors=True)
    shutil.copytree(sol, p)
    mod = "progress"
    files = [str(f.relative_to(p)) for g in DPJ.P.scope_globs(mod, p) for f in sorted(p.glob(g)) if f.is_file() and not str(f.relative_to(p)).startswith("tests/")]
    inp = DPJ.fix_input(p, {"task": f"做模块\n模块 {mod}"}, ["比对约定：x"])
    kinds = {k: any(f.startswith(k) for f in files) for k in ("entities/", "services/", "routes/", "queries/")}
    check(all(kinds.values()), "夹具里 progress 模块四类文件都有", kinds)
    check(all(f"### {f}" in inp for f in files), "fix_input 含本模块 entities / services / routes / queries 全部文件", [f for f in files if f"### {f}" not in inp])
    # 读片段 通配
    from tools.dslagent.verbs.code.defs import _read as RD
    got = RD.split_segs("queries/progress_*.sql,services/progress.zs", p)
    check(len(got) >= 2 and all(g.startswith("queries/progress_") for g in got[:-1]) and got[-1] == "services/progress.zs", "读片段 通配展开成匹配文件", got)
    check(RD.split_segs("queries/none_*.sql", p) == ["queries/none_*.sql"], "没有匹配的通配原样留着（读时报没有这个文件）")
    r = _verb_module("改文件")
    r.WORKSPACE = p
    check(r.改文件("[]")["ok"] == "否", "空列表 → 报错")


def main():
    try:
        t_block()
        t_rules()
        t_apply_edits()
        t_check_plan()
        t_fix_input()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
