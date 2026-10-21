# -*- coding: utf-8 -*-
"""核查.zs——程序检查是动词（全局检查 items / 全量回归·接口冒烟 方式=核查 / 存问题清单 多份结果），需要判断的地方派子任务（派任务）。
另有 R 的小修复：检查修改计划 按传入的问题清单检查、next_no/latest_path 容忍非数字文件名、--issues 路径限项目目录内。不调真模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_audit.py

复用 test_dslagent_v3.py 的夹具（参考实现 graph / vocab / progress、假模型 Fake）。
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_dslagent_v3 as T                                   # noqa: E402

check, fresh, core, Fake = T.check, T.fresh, T.core, T.Fake
from tools.dslagent.v3 import planning as PLC                # noqa: E402


def verb_engine(p, out, req="需求全文", req_path=None):
    ctx = core.Ctx(p, out, req, None, req_path=req_path)
    e = T.engine(p)
    e.v3 = ctx
    return e, ctx


def run(e, text):
    e.run("用包 common v3\n" + text)
    return e.returned[0] if e.returned else None


def item(issue, modules="a", basis="b"):
    return {"issue": issue, "modules": modules, "basis": basis}


def ok(found, items):
    return {"result": {"found": found, "items": items}, "status": "成功", "reason": ""}


# ------------------------------------------------------------------ 动词

def test_global_check_items():
    print("全局检查：返回补 items（同 program_items）；没有 top.zs 时 0 条")
    p = fresh("gc")
    (p / "plan").mkdir()
    (p / "plan" / "top.zs").write_text("项目 demo\n模块 a\n模块 b\n", encoding="utf-8")
    (p / "contracts").mkdir()
    (p / "contracts" / "a.md").write_text(T.DUP_A, encoding="utf-8")
    (p / "contracts" / "b.md").write_text(T.DUP_B, encoding="utf-8")
    e, _ = verb_engine(p, fresh("o"))
    g = run(e, "设 g = 全局检查\n返回 {g}\n")
    check(g["count"] == 2 and set(g["by_module"]) == {"a", "b"} and g["summary"], "原有 count / by_module / summary 保留", g)
    check(len(g["items"]) == 2 and all(i["basis"] == "程序检查" and i["modules"] in ("a", "b") and i["issue"] for i in g["items"]),
          "items：basis=程序检查、modules 是模块名", g["items"])
    q = fresh("gc0")
    e0, _ = verb_engine(q, fresh("o"))
    g0 = run(e0, "设 g = 全局检查\n返回 {g}\n")
    check(g0["count"] == 0 and g0["items"] == [], "没有 plan/top.zs：0 条，不报错", g0)


def broken_graph(p):
    f = p / "services" / "graph.zs"
    f.write_text(f.read_text(encoding="utf-8").replace("报错 404 没有这个知识点", "报错 400 没有这个知识点", 1), encoding="utf-8")


def test_regression_report():
    print("全量回归 方式=核查：只报告，不重做、不改 state；失败项带原文；没有代码跳过")
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    out = fresh("o")
    e, ctx = verb_engine(p, out)
    for m in ("graph", "vocab", "progress"):
        ctx.mark_done(m)
    r = run(e, "设 r = 全量回归 方式=核查\n返回 {r}\n")
    check(r["count"] == 0 and r["items"] == [], "参考实现全部通过：0 条", r)
    broken_graph(p)
    state_before = (p / "plan" / "state.json").read_bytes() if (p / "plan" / "state.json").is_file() else None
    ctx.module_cmd = [sys.executable, "-c", "raise SystemExit('不该被调用')"]      # 要是被当成「重做」调起来就炸
    r2 = run(e, "设 r = 全量回归 方式=核查\n返回 {r}\n")
    check(r2["count"] == 1 and r2["items"][0]["modules"] == "graph" and r2["items"][0]["basis"] == "全量回归",
          "graph 一条：basis=全量回归", r2)
    check("跑用例" in r2["items"][0]["issue"] and "graph" in r2["items"][0]["issue"], "issue 带模块名、哪项检查和失败原文", r2["items"][0]["issue"])
    check(ctx.is_done("graph") and ctx.is_done("vocab"), "state 不改：graph 仍标记完成（没有 unmark）")
    check(((p / "plan" / "state.json").read_bytes() if (p / "plan" / "state.json").is_file() else None) == state_before, "plan/state.json 字节不变")
    check(not ctx.records["验收"], "没有记验收（只报告）", ctx.records["验收"])
    # 没有代码
    q = fresh("nocode")
    (q / "plan").mkdir()
    (q / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    shutil.copytree(T.SOL / "contracts", q / "contracts")
    e2, _ = verb_engine(q, fresh("o"))
    r3 = run(e2, "设 r = 全量回归 方式=核查\n返回 {r}\n")
    check(r3["count"] == 0 and "还没有代码，跳过" in r3["summary"], "没有任何模块有代码文件：count=0、summary 写「还没有代码，跳过」", r3)


def test_smoke_report():
    print("接口冒烟 方式=核查：只报告；每个不过的接口一条；完整结果存 out/smoke_<n>；没有代码跳过")
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    out = fresh("o")
    e, ctx = verb_engine(p, out)
    r = run(e, "设 r = 接口冒烟 方式=核查\n返回 {r}\n")
    check(r["count"] == 0 and len(r["files"]) == 2 and Path(r["files"][0]).name == "smoke_1.json", "参考实现冒烟全过：0 条，结果存 smoke_1.json / .txt", r)
    (p / "routes" / "progress.zs").unlink()                          # HTTP 一侧 404、直接调用 200
    ctx.module_cmd = [sys.executable, "-c", "raise SystemExit('不该被调用')"]
    r2 = run(e, "设 r = 接口冒烟 方式=核查\n返回 {r}\n")
    check(r2["count"] >= 1 and all(i["basis"] == "接口冒烟" for i in r2["items"]), "删掉路由后冒烟报出问题：basis=接口冒烟", r2)
    check(any("progress" in i["modules"] and ("状态码不一致" in i["issue"] or "404" in i["issue"]) for i in r2["items"]), "issue 带方法路径和直接调用与 HTTP 的差异原文", r2["items"])
    check(Path(r2["files"][0]).name == "smoke_2.json" and Path(r2["files"][0]).is_file() and Path(r2["files"][1]).is_file(), "第二次接着编号 smoke_2", r2["files"])
    check(ctx.is_done("graph") is False and not ctx.records["验收"], "没有碰 state / 没记验收")
    q = fresh("nocode")
    (q / "plan").mkdir()
    (q / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    shutil.copytree(T.SOL / "contracts", q / "contracts")
    e2, _ = verb_engine(q, fresh("o"))
    r3 = run(e2, "设 r = 接口冒烟 方式=核查\n返回 {r}\n")
    check(r3["count"] == 0 and "还没有代码，跳过" in r3["summary"] and "files" not in r3, "没有代码：跳过", r3)


def test_store_issues():
    print("存问题清单：合并、去重、编号；规划子任务非成功进 unchecked；found/items 不一致与缺字段被丢弃")
    p = fresh("store")
    (p / "plan" / "issues").mkdir(parents=True)
    (p / "plan" / "issues" / "4.md").write_text("# 问题清单 4\n\n（没有发现问题）\n", encoding="utf-8")
    e, ctx = verb_engine(p, fresh("o"))
    e.vars.update({
        "a": {"count": 1, "items": [item("程序一", "a", "程序检查")]},
        "b": {"count": 1, "items": [item("回归一", "a", "全量回归"), {"issue": "缺依据", "modules": "a"}]},
        "pl": ok(True, [item("规划一", "a、b", "需求"), item("程序一", "a", "又一次")]),
        "pm": ok(True, [item("矛盾", "c")]) | {"result": {"found": False, "items": [item("矛盾", "c")]}},
        "pe": ok(True, []),
    })
    s = run(e, "设 s = 存问题清单 程序={a} 回归={b} 规划={pl}\n返回 {s}\n")
    check(s["path"] == "plan/issues/5.md", "序号接着上一份往后编", s["path"])
    text = (p / s["path"]).read_text(encoding="utf-8")
    check(s["count"] == 3 and [l.split(". ", 1)[1] for l in text.splitlines() if l[:1].isdigit()] == ["程序一", "回归一", "规划一"],
          "合并顺序 程序、回归、规划；按（issue, modules）去重（同文本同模块的第二条去掉）", text)
    check("类型" not in text, "清单里没有类型行", text)
    check(len(s["dropped"]) == 1 and "缺字段" in s["dropped"][0]["reason"] and "basis" in s["dropped"][0]["reason"], "缺字段的条目丢弃并记入 dropped", s["dropped"])
    s1 = run(e, "设 s = 存问题清单 规划={pm}\n返回 {s}\n")
    check(s1["count"] == 0 and len(s1["dropped"]) == 1 and "前后矛盾" in s1["dropped"][0]["reason"], "found=否 但 items 非空：丢弃", s1)
    s1b = run(e, "设 s = 存问题清单 规划={pe}\n返回 {s}\n")
    check(s1b["count"] == 0 and len(s1b["dropped"]) == 1 and "items 为空" in s1b["dropped"][0]["reason"], "found=是 但 items 为空：丢弃", s1b)
    # 规划层失败
    e.vars["pf"] = {"result": {"found": False, "items": []}, "status": "失败", "reason": "模型没有回应"}
    s2 = run(e, "设 s = 存问题清单 规划={pf}\n返回 {s}\n")
    check(s2["count"] == 0 and s2["unchecked"][0]["module"] == "规划层" and "模型没有回应" in s2["unchecked"][0]["reason"], "规划层失败：清单仍存（0 条），unchecked 有它", s2)
    check((p / s2["path"]).is_file(), "清单文件照样存盘")
    s3 = run(e, "设 m =\n设 s = 存问题清单 程序={a} 规划={m}\n返回 {s}\n")
    check(s3["count"] == 1 and s3["unchecked"] == [], "空串当作没传", s3)


# ------------------------------------------------------------------ 核查.zs 整条

class ByContent(Fake):
    """按 user 文本里的关键字回子任务：rules = [(关键字, 回复文本)]，没命中的回 found=否。"""

    def __init__(self, rules, **kw):
        super().__init__(**kw)
        self.rules = rules

    def __call__(self, system, user, tag, timeout, **kw):
        if tag.startswith("dsl"):
            self.calls.append({"tag": tag, "user": user, "system": system, "model": kw.get("model"), "idle": kw.get("idle")})
            for key, reply in self.rules:
                if key in user:
                    return {"text": reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False), "cost": 0.01}
            return {"text": json.dumps(ok(False, []), ensure_ascii=False), "cost": 0.01}
        return super().__call__(system, user, tag, timeout, **kw)


def audit_project(broken=False):
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    if broken:
        broken_graph(p)
    return p


def run_audit(p, fk, **vars_):
    out = fresh("aout")
    v = {"task": "", "llm": "sonnet", **vars_}
    return core.run_entry("核查", p, out, "## 1 概述\n需求全文\n", extra_vars=v, backend=fk, req_path=None), out


def test_audit_flow():
    print("核查.zs 整条（假模型）：有代码且回归失败 / 没有 top / 子任务失败")
    p = audit_project(broken=True)
    fk = ByContent([("规划层核查", ok(True, [item("需求第 2 节的导出没人做", "vocab", "需求第 2 节")]))])
    res, out = run_audit(p, fk)
    ret = res.get("returned") or {}
    check(res["status"] == "成功" and ret.get("count") == 2, "回归失败 1 条 + 规划层 1 条", res)
    text = (p / ret["path"]).read_text(encoding="utf-8")
    check("模块 graph 全量回归不过" in text and "依据：全量回归" in text and "需求第 2 节的导出没人做" in text, "清单里有回归问题和规划层问题", text)
    check(fk.n("dsl") == 1, "只派规划层一个子任务", [c["tag"] for c in fk.calls])
    user = fk.calls[0]["user"]
    check("plan/top.zs" in user and "contracts/graph.md" in user and "plan/catalog.md" in user, "规划层入参带 top.zs、目录、各模块约定文件", user[:600])
    check("需求全文" in user, "需求全文当一项文本放进入参", user[:600])
    check((out / "smoke_1.json").is_file(), "冒烟完整结果存在 out/smoke_1.json")
    # 没有 top
    p3 = fresh("notop")
    fk3 = ByContent([("规划层核查", ok(True, [item("无顶层", "a")]))])
    res3, _ = run_audit(p3, fk3)
    check(res3["status"] == "成功" and res3["returned"]["count"] == 1 and fk3.n("dsl") == 1, "没有 top：程序检查 0 条，规划层照派", res3)
    # 规划层失败
    p4 = audit_project()
    fk4 = ByContent([("规划层核查", {"result": {"found": False, "items": []}, "status": "失败", "reason": "模型没有回应"})])
    res4, _ = run_audit(p4, fk4)
    ret4 = res4["returned"]
    check(res4["status"] == "成功" and ret4["count"] == 0 and ret4["unchecked"][0]["module"] == "规划层", "规划层失败：清单照存，unchecked 记下规划层", res4)


def test_issue_fixes():
    print("小修复：next_no / latest_path 容忍非数字文件名；resolve 路径限项目目录内；检查修改计划 按传入的问题清单检查")
    from tools.dslagent.v3 import issues as IS
    p = fresh("iss")
    (p / "plan" / "issues").mkdir(parents=True)
    (p / "plan" / "issues" / "notes.md").write_text("x", encoding="utf-8")
    check(IS.next_no(p) == 1 and IS.latest_path(p) is None, "plan/issues/ 下有非数字文件名也不炸")
    (p / "plan" / "issues" / "2.md").write_text("# 问题清单 2\n\n1. a\n", encoding="utf-8")
    check(IS.next_no(p) == 3 and IS.latest_path(p).name == "2.md", "有数字文件名时照常取最大")
    (p / "my").mkdir()
    (p / "my" / "iss.md").write_text("# 问题清单 x\n\n1. x\n   涉及模块：vocab\n", encoding="utf-8")
    check(IS.resolve(p, "my/iss.md").name == "iss.md", "项目目录内任意路径的清单可用")
    outside = fresh("outside")
    (outside / "i.md").write_text("1. x\n", encoding="utf-8")
    try:
        IS.resolve(p, str(outside / "i.md"))
        check(False, "项目目录外的清单被拒")
    except ValueError as e:
        check("不在项目目录" in str(e), "项目目录外的清单被拒", e)
    # 检查修改计划 按传入的问题清单，而不是 plan/issues 最新一份
    q = T.full_project()
    (q / "plan").mkdir(exist_ok=True)
    (q / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    (q / "plan" / "issues").mkdir(exist_ok=True)
    (q / "plan" / "issues" / "1.md").write_text("# 问题清单 1\n\n1. 最新那份的问题\n   涉及模块：vocab\n", encoding="utf-8")
    e, _ = verb_engine(q, fresh("o"))
    plan = "# 对应问题 1\n改约定 vocab 补一个说明\n落实修改\n"
    e.vars["pl"] = plan
    e.vars["two"] = [{"issue": "甲", "modules": "vocab", "basis": "b"}, {"issue": "乙", "modules": "graph", "basis": "b"}]
    c1 = run(e, "设 c = 检查修改计划 {pl}\n返回 {c}\n")
    check(c1["ok"] == "是", "不传问题：读 plan/issues 最新一份（1 条，计划覆盖了）", c1)
    c2 = run(e, "设 c = 检查修改计划 {pl} 问题={two}\n返回 {c}\n")
    check(c2["ok"] == "否" and "2" in c2["problems"], "传了 2 条的清单：第 2 条没被计划覆盖，检查不过", c2)


if __name__ == "__main__":
    try:
        test_global_check_items()
        test_regression_report()
        test_smoke_report()
        test_store_issues()
        test_audit_flow()
        test_issue_fixes()
    finally:
        shutil.rmtree(T.TMP, ignore_errors=True)
    print(f"\n通过 {T.PASS}，失败 {T.FAIL}")
    sys.exit(1 if T.FAIL else 0)
