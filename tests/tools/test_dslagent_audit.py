# -*- coding: utf-8 -*-
"""N2：核查.zs 重写——程序检查是动词（全局检查 items / 全量回归·接口冒烟 方式=核查 / 取文件 / 列出模块 / 核查任务表 / 逻辑核查 /
存问题清单 多份结果），需要判断的地方派子任务（派任务 / 并行派任务）。不调真模型。

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


def verb_engine(p, out, req="需求全文", req_path=None):
    ctx = core.Ctx(p, out, req, None, req_path=req_path)
    e = T.engine(p)
    e.v3 = ctx
    return e, ctx


def run(e, text):
    e.run("用包 common v3\n" + text)
    return e.returned[0] if e.returned else None


def item(issue, modules="a", basis="b", type_="code"):
    return {"issue": issue, "modules": modules, "basis": basis, "type": type_}


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
    check(len(g["items"]) == 2 and all(i["basis"] == "程序检查" and i["type"] == "contract" and i["modules"] in ("a", "b") and i["issue"] for i in g["items"]),
          "items：basis=程序检查、type=contract、modules 是模块名", g["items"])
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
    check(r2["count"] == 1 and r2["items"][0]["modules"] == "graph" and r2["items"][0]["basis"] == "全量回归" and r2["items"][0]["type"] == "code",
          "graph 一条：basis=全量回归、type=code", r2)
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
    check(r2["count"] >= 1 and all(i["basis"] == "接口冒烟" and i["type"] == "code" for i in r2["items"]), "删掉路由后冒烟报出问题：basis=接口冒烟、type=code", r2)
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


def test_read_file_and_list():
    print("取文件 / 列出模块")
    p = T.solution_project()
    reqdir = fresh("req")
    req = reqdir / "req.md"
    req.write_text("## 1 概述\n需求原文\n", encoding="utf-8")
    secret = fresh("secret") / "s.txt"
    secret.write_text("机密", encoding="utf-8")
    e, ctx = verb_engine(p, fresh("o"), req_path=req)
    got = run(e, f"设 t = 取文件 {req}\n返回 {{t}}\n")
    check("需求原文" in got, "需求文件（在项目目录之外）读得到", got)
    check("项目 demo" in run(e, "设 t = 取文件 plan/top.zs\n返回 {t}\n"), "项目目录内相对路径读得到")
    check(run(e, f"设 t = 取文件 {secret}\n返回 {{t}}\n") == "", "项目和需求文件之外的路径读不到（空串）")
    check(run(e, "设 t = 取文件 ../x.txt\n返回 {t}\n") == "" and run(e, "设 t = 取文件 nothere.md\n返回 {t}\n") == "", "越界 / 不存在返回空串")
    why = [r for r in ctx.records.get("取文件", [])]
    check(len(why) >= 3 and all(r["summary"] for r in why), "读不到的原因记在日志 summary 里", why)
    check("架构复核员" in run(e, "设 t = 取文件 @audit.md\n返回 {t}\n"), "@audit.md 读 v3 自带提示词")
    check(run(e, "设 m = 列出模块\n返回 {m}\n") == "graph,vocab,progress", "列出模块")
    (p / "services" / "progress.zs").unlink()
    for f in list((p / "routes").glob("progress*")) + list((p / "queries").glob("progress_*")) + [p / "entities" / "progress.entity"]:
        f.unlink()
    check(run(e, "设 m = 列出模块 有代码=是\n返回 {m}\n") == "graph,vocab", "有代码=是：只列有代码文件的模块")
    check(run(verb_engine(fresh("empty"), fresh("o"))[0], "设 m = 列出模块\n返回 {m}\n") == "", "没有 top.zs 返回空串")


def test_audit_task_table():
    print("核查任务表：每项四个字段齐、入参含约定与代码引用、超长分段")
    p = T.solution_project()
    long_f = p / "services" / "vocab.zs"
    long_f.write_text(long_f.read_text(encoding="utf-8") + "".join(f"# 填充 {i}\n" for i in range(900)), encoding="utf-8")
    req = "## 1 概述\n总体说明\n\n## 2 词库\nvocab 词库要求\n\n## 3 无关\n别的\n"
    e, ctx = verb_engine(p, fresh("o"), req=req)
    e.vars["known"] = {"a": {"items": [item("vocab 有重复", "vocab", "程序检查", "contract"), item("graph 的问题", "graph")]}, "b": ""}
    jobs = run(e, "设 j = 核查任务表 graph,vocab 加一种练习 已知问题={known}\n返回 {j}\n")
    check(len(jobs) == 2 and all(set(j) == {"任务", "入参", "逻辑", "格式"} and all(j[k] for k in j) for j in jobs), "两个模块两项，四个字段齐", [list(j) for j in jobs])
    v = jobs[1]
    check("核查模块 vocab" in v["任务"] and "vocab 有重复" in v["任务"] and "graph 的问题" not in v["任务"], "任务描述点名模块，带本模块的已知问题（别的模块的不带）", v["任务"])
    check(v["格式"] == "found:是否,items:列表", "格式字段", v["格式"])
    inp = v["入参"]
    check("vocab 词库要求" in inp["需求相关节"] and "别的" not in inp["需求相关节"] and "加一种练习" in inp["需求相关节"], "需求相关节只取相关的节，并带任务", inp["需求相关节"])
    check("## 用例" not in inp["约定全文（去用例）"] and "模块 vocab" in inp["约定全文（去用例）"], "约定全文去用例")
    check("graph" in inp["上游公开函数头"], "上游公开函数头（vocab 依赖 graph）", inp["上游公开函数头"])
    refs = {k: x for k, x in inp.items() if x.endswith(tuple("0123456789")) and ":" in x and "/" in x}
    check(any(x == "entities/vocab.entity:1-" + str(len((p / "entities" / "vocab.entity").read_text(encoding="utf-8").splitlines())) for x in refs.values()),
          "现有代码文件各一个「文件:1-N」引用", refs)
    segs = [x for x in refs.values() if x.startswith("services/vocab.zs:")]
    check(len(segs) >= 3 and segs[0].endswith(":1-400") and segs[1].startswith("services/vocab.zs:401-"), "超过 400 行的文件分段", segs)
    check(any("第 1/" in k for k in refs), "分段的小标题带第几段", list(refs))
    g = jobs[0]["入参"]
    check(g["上游公开函数头"] == "（没有上游依赖）", "没有上游依赖的写明白")
    # 交给 派任务 读出代码行
    from tools.dsl_task import collect_inputs
    pairs = dict(collect_inputs(inp, p))
    check(any("   1| " in c for k, c in pairs.items() if "vocab.zs" in k), "派任务 读得出这些引用（带行号）")


def test_store_issues():
    print("存问题清单：合并、去重、编号、类型行；非成功子任务进 unchecked；found/items 不一致与缺字段被丢弃")
    p = fresh("store")
    (p / "plan" / "issues").mkdir(parents=True)
    (p / "plan" / "issues" / "4.md").write_text("# 问题清单 4\n\n（没有发现问题）\n", encoding="utf-8")
    e, ctx = verb_engine(p, fresh("o"))
    e.vars.update({
        "a": {"count": 1, "items": [item("程序一", "a", "程序检查", "contract")]},
        "b": {"count": 1, "items": [item("回归一", "a", "全量回归", "code")]},
        "pl": ok(True, [item("规划一", "a、b", "需求", "req"), item("程序一", "a", "又一次", "contract")]),
        "ml": [ok(True, [item("模块 a 一", "a"), item("规划一", "a、b", "x", "req")]),
               {"result": "无", "status": "失败", "reason": "格式不合格"},
               ok(True, []),                                     # found=是 但 items 空
               ok(False, [item("矛盾", "c")]),                   # found=否 但 items 非空
               ok(True, [{"issue": "缺字段", "modules": "d"}, item("坏类型", "d", "b", "乱写"), item("好的", "d")]),
               {"result": ok(True, [])["result"], "status": "超出预期", "reason": "前提不对"}],
        "e": {"count": 1, "items": [item("疑点一", "a", "logic_check(疑点)：x", "contract")]},
    })
    s = run(e, "设 s = 存问题清单 程序={a} 回归={b} 规划={pl} 模块={ml} 模块名=a,b,c,d,e,f 疑点={e}\n返回 {s}\n")
    check(s["path"] == "plan/issues/5.md", "序号接着上一份往后编", s["path"])
    text = (p / s["path"]).read_text(encoding="utf-8")
    check(s["count"] == 6 and [l.split(". ", 1)[1] for l in text.splitlines() if l[:1].isdigit()] == ["程序一", "回归一", "规划一", "模块 a 一", "好的", "疑点一"],
          "合并顺序 程序、回归、规划、模块、疑点；按（issue, modules）去重（同文本同模块的第二条去掉）", text)
    check("   类型：code" in text and "   类型：req" in text and text.count("类型：") == 4, "带「类型：」行（contract 缺省不写）", text)
    check([(u["module"], u["reason"]) for u in s["unchecked"]] == [("b", "格式不合格"), ("f", "前提不对")], "非成功的子任务进 unchecked（模块名 + reason），不当作没问题", s["unchecked"])
    why = [d["reason"] for d in s["dropped"]]
    check(len(s["dropped"]) == 4 and any("前后矛盾" in w and "items 为空" in w for w in why) and any("前后矛盾" in w and "非空" in w for w in why)
          and any("缺字段" in w for w in why) and any("type" in w for w in why), "found/items 不一致、缺字段、type 不对：丢弃并记入 dropped", s["dropped"])
    check(all("raw" in d and "source" in d for d in s["dropped"]), "dropped 带原文")
    # 规划层失败
    e.vars["pf"] = {"result": {"found": False, "items": []}, "status": "失败", "reason": "模型没有回应"}
    s2 = run(e, "设 s = 存问题清单 规划={pf}\n返回 {s}\n")
    check(s2["count"] == 0 and s2["unchecked"][0]["module"] == "规划层" and "模型没有回应" in s2["unchecked"][0]["reason"], "规划层失败：清单仍存（0 条），unchecked 有它", s2)
    check((p / s2["path"]).is_file(), "清单文件照样存盘")
    s3 = run(e, "设 m =\n设 s = 存问题清单 程序={a} 规划={m} 模块={m}\n返回 {s}\n")
    check(s3["count"] == 1 and s3["unchecked"] == [], "空串当作没传", s3)


def test_logic_verb():
    print("逻辑核查：items（basis=logic_check(疑点)，type=contract）；缓存规则不变；没有 top 0 条")
    p = fresh("lc")
    (p / "plan").mkdir()
    (p / "plan" / "top.zs").write_text("项目 demo\n模块 a\n", encoding="utf-8")
    (p / "contracts").mkdir()
    (p / "contracts" / "a.md").write_text("模块 a\n\n## 函数\n公开 函数 x\n  伪代码 返回 1\n", encoding="utf-8")
    fk = Fake(scripts={"v3_logic_check": ['[{"issue":"漏了鉴权","basis":"函数 x"}]']})
    out = fresh("o")
    res = core.run_entry("核查", p, out, "需求全文", extra_vars={"task": "", "llm": "sonnet", "deep": "否", "logic_check": "是"}, backend=fk)
    check(res["status"] == "成功", "logic_check=是 的核查跑成功", res)
    text = (p / res["returned"]["path"]).read_text(encoding="utf-8")
    check("漏了鉴权" in text and "logic_check(疑点)" in text, "疑点并进清单，标 logic_check(疑点)", text)
    check(fk.n("v3_logic_check") == 1 and (out / "logic_cache.json").is_file(), "调了一次角色，缓存落盘")
    res2 = core.run_entry("核查", p, out, "需求全文", extra_vars={"task": "", "llm": "sonnet", "deep": "否", "logic_check": "是"}, backend=fk)
    check(fk.n("v3_logic_check") == 1, "同一 out 目录、约定没变：第二次走缓存，不再调角色", fk.n("v3_logic_check"))
    res3 = core.run_entry("核查", p, fresh("o"), "需求全文", extra_vars={"task": "", "llm": "sonnet", "deep": "否", "logic_check": "否"}, backend=fk)
    check("漏了鉴权" not in (p / res3["returned"]["path"]).read_text(encoding="utf-8"), "logic_check=否 不并疑点")


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
    v = {"task": "", "llm": "sonnet", "deep": "否", "logic_check": "否", **vars_}
    return core.run_entry("核查", p, out, "## 1 概述\n需求全文\n", extra_vars=v, backend=fk, req_path=None), out


def test_audit_flow():
    print("核查.zs 整条（假模型）：有代码且回归失败 / deep 是否 / 子任务失败 / 回复前后矛盾")
    # 有代码、回归失败，deep=否
    p = audit_project(broken=True)
    fk = ByContent([("架构复核员", ok(True, [item("需求第 2 节的导出没人做", "vocab", "需求第 2 节", "req")]))])
    res, out = run_audit(p, fk)
    ret = res.get("returned") or {}
    check(res["status"] == "成功" and ret.get("count") == 2, "回归失败 1 条 + 规划层 1 条", res)
    text = (p / ret["path"]).read_text(encoding="utf-8")
    check("模块 graph 全量回归不过" in text and "依据：全量回归" in text and "类型：code" in text and "需求第 2 节的导出没人做" in text, "清单里有回归的 code 问题和规划层问题", text)
    check(fk.n("dsl") == 1, "deep=否：只派规划层一个子任务", [c["tag"] for c in fk.calls])
    user = fk.calls[0]["user"]
    check("全量回归" in user and "graph" in user and "接口冒烟" in user, "规划层子任务的入参带回归 / 冒烟摘要", user[-600:])
    check((out / "smoke_1.json").is_file(), "冒烟完整结果存在 out/smoke_1.json")
    # deep=是
    p2 = audit_project()
    fk2 = ByContent([("架构复核员", ok(False, [])),
                     ("核查模块 graph", ok(True, [item("graph.zs 第 3 行没按伪代码查重", "graph", "services/graph.zs:3", "code")])),
                     ("核查模块 vocab", {"result": {"found": False, "items": []}, "status": "失败", "reason": "超时了"}),
                     ("核查模块 progress", ok(True, []))])
    res2, _ = run_audit(p2, fk2, deep="是", task="加一种练习")
    ret2 = res2.get("returned") or {}
    check(res2["status"] == "成功" and fk2.n("dsl") == 4, "deep=是：规划层 1 + 每个有代码的模块 1 = 4 次子任务", [c["tag"] for c in fk2.calls])
    check(ret2["count"] == 1 and [u["module"] for u in ret2["unchecked"]] == ["vocab"] and ret2["unchecked"][0]["reason"] == "超时了",
          "一个子任务失败：清单仍存，unchecked 里有它", ret2)
    check([d["source"] for d in ret2["dropped"]] == ["模块 progress"], "found=是 但 items 空的回复丢进 dropped", ret2["dropped"])
    mod_user = [c["user"] for c in fk2.calls if "核查模块 graph" in c["user"]][0]
    check("services/graph.zs 第 1-" in mod_user and "   1| " in mod_user and "【处理逻辑】" in mod_user, "模块子任务的 user 里带出了代码原文（带行号）", mod_user[:300])
    check("## 用例" not in mod_user.split("◆ 约定全文（去用例）")[1].split("◆")[0], "约定全文去用例")
    check("加一种练习" in mod_user, "任务带进模块子任务")
    # 没有 top
    p3 = fresh("notop")
    fk3 = ByContent([("架构复核员", ok(True, [item("无顶层", "a")]))])
    res3, _ = run_audit(p3, fk3, deep="是")
    check(res3["status"] == "成功" and res3["returned"]["count"] == 1 and fk3.n("dsl") == 1, "没有 top：程序检查 0 条，规划层照派，deep 无效", res3)
    # 规划层失败
    p4 = audit_project()
    fk4 = ByContent([("架构复核员", {"result": {"found": False, "items": []}, "status": "失败", "reason": "模型没有回应"})])
    res4, _ = run_audit(p4, fk4)
    ret4 = res4["returned"]
    check(res4["status"] == "成功" and ret4["count"] == 0 and ret4["unchecked"][0]["module"] == "规划层", "规划层失败：清单照存，unchecked 记下规划层", res4)


def test_audit_then_modify():
    print("核查 → 修改.zs 整条仍通过：code 类型问题走 改文件")
    p = T.solution_project()
    out = fresh("aout")
    for m in ("graph", "vocab", "progress"):
        core.Ctx(p, out, "x", None).mark_done(m)
    bad = {"issue": "vocab 的 记作答 错误提示和约定不一致", "modules": "vocab", "basis": "services/vocab.zs", "type": "code"}
    fk = ByContent([("架构复核员", ok(True, [bad]))])
    GOOD = "# 对应问题 1\n改文件 services/vocab.zs correct\\_只能是\\_0\\_或\\_1 correct\\_必须是\\_0\\_或\\_1\n落实修改\n"
    fk.scripts["v3_change_plan"] = [GOOD]
    res = core.run_entry("核查", p, out, "需求全文", extra_vars={"task": "", "llm": "sonnet", "deep": "否", "logic_check": "否"}, backend=fk)
    ret = res["returned"]
    check(res["status"] == "成功" and "类型：code" in (p / ret["path"]).read_text(encoding="utf-8"), "核查产出带类型的清单", res)
    res2 = core.run_entry("修改", p, out, "需求全文", extra_vars={"issues": "latest", "task": "", "llm": "sonnet", "retries": "3"},
                          backend=fk, module_cmd=T.CMD)
    check(res2["status"] == "成功" and "services/vocab.zs" in res2["reason"], "修改.zs 读这份清单，code 问题走 改文件", res2)
    check("correct 必须是 0 或 1" in (p / "services" / "vocab.zs").read_text(encoding="utf-8"), "文件改了")


if __name__ == "__main__":
    try:
        test_global_check_items()
        test_regression_report()
        test_smoke_report()
        test_read_file_and_list()
        test_audit_task_table()
        test_store_issues()
        test_logic_verb()
        test_audit_flow()
        test_audit_then_modify()
    finally:
        shutil.rmtree(T.TMP, ignore_errors=True)
    print(f"\n通过 {T.PASS}，失败 {T.FAIL}")
    sys.exit(1 if T.FAIL else 0)
