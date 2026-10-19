# -*- coding: utf-8 -*-
"""modular 先约定接口再按约定实现（contract.py + modbuild 的约定模式 / --from-plan）。不调真模型。

    .venv/bin/python tests/tools/test_dslagent_contract.py

一、约定 JSON 校验：引用不存在 / 参数不匹配 / 越层 / 跨模块非法调用 / 未知动词 / 规则未落地 / 命名与范围
二、比对函数：sql 返回列（空库真跑）/ 调用对象 / 响应键 / 界面动作
三、假模型全流程（约定模式）：约定先于实现、实现只看约定签名、CONTRACTS.md、约定重写与失败
四、实现与约定不一致被拒：sql 写入 / 可选参数保护 / 流程出参与调用 / 接口动作 / 调用 / 响应键 / 界面动作
五、不因别的文件失败而跳过；mgen_fallback；试调（外键 409 / 整体试调一轮后点名重写）；继续构建
六、--from-plan / CLI
"""
import copy
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_dslagent_modbuild as TM     # noqa: E402  (带上假模型 Fake、REQ、ZS_* 等夹具；它的 main 不会跑)
from tools.dslagent import contract as C, modbuild as MB, v2 as V      # noqa: E402

PASS = FAIL = 0
dump, REQ = TM.dump, TM.REQ


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  ✓ " if cond else "  ✗ ") + msg + ("" if cond or extra == "" else f"\n      {str(extra)[:1500]}"))


def Pm(*names, opt=()):
    return [{"名": n, "要求": "可选" if n in opt else "必填"} for n in names]


def contract_obj(m, mut=None):
    if m == "quiz":
        o = {"sql": [{"名": "quiz_log", "参数": Pm("question_id", "given"), "返回": "写入", "作用": "写作答记录", "表": ["attempt"], "用列": ["attempt.question_id", "attempt.given"], "规则": ["R1"]}],
             "流程": [{"名": "quiz_judge", "入参": Pm("question_id", "given"), "出参": ["ok", "n"], "写哪些表": ["attempt"], "调": [{"名": "quiz_log", "给": ["question_id", "given"]}],
                       "用动词": ["写库表"], "业务错误": [{"情形": "题目不存在", "返回": "{\"error\":\"题目不存在\"}"}], "作用": "判一道题并写记录", "规则": ["R1"]}],
             "接口": [{"文件": "quiz", "路径": "/quiz/answer", "动作": "quiz_answer", "角色": "", "请求字段": Pm("question_id", "given"),
                       "调用": [{"名": "quiz_judge", "给": ["question_id", "given"]}], "响应": {"state": ["ok"], "lists": [], "messages": "否"},
                       "业务错误": [{"码": 404, "情形": "题目不存在"}], "作用": "交答案", "规则": ["R1"]}],
             "界面": [{"页": "quiz_page", "用接口": ["/quiz/answer"], "字段": ["given"]}]}
    else:
        o = {"sql": [], "流程": [],
             "接口": [{"文件": "progress", "路径": "/progress/recheck", "动作": "progress_recheck", "角色": "", "请求字段": Pm("question_id", "given"),
                       "调用": [{"名": "quiz_judge", "给": ["question_id", "given"]}], "响应": {"state": ["ok"], "lists": [], "messages": "否"},
                       "业务错误": [], "作用": "重判", "规则": ["R2"]}],
             "界面": [{"页": "progress_page", "用接口": ["/progress/recheck"], "字段": ["given"]}]}
    if mut:
        mut(o)
    return o


TOP = MB.validate_top(dump(TM.top_obj()), TM.PACKS)["top"]
SPLIT = MB.validate_split(dump(TM.split_obj()), TOP, TM.CAPS)["split"]
ENTS = {"question": {"id", "title", "answer"}, "attempt": {"id", "question_id", "given", "correct"}, "mastery": {"id", "question_id", "score"}}
VERBS = {v["名"] for p in ("db", "http", "common") for v in TM.CAPS[p]}
GEN = MB.L.gen_sqls(list(ENTS))


def uctx(m, quiz=None, **over):
    v = SPLIT["模块"][m]
    ctx = {"mod": m, "v": v, "ents": ENTS, "own_tables": v["数据"], "flows_ext": {},
           "sql_known": {s: {"名": s, "参数": Pm("question_id", "given", "correct") if s == "attempt_insert" else Pm("id")} for s in GEN},
           "gen_sqls": GEN, "taken_sqls": set(), "taken_paths": set(), "taken_acts": set(), "ui_paths": set(), "verbs": VERBS, "roles": [],
           "other_flows": {"quiz_judge"}, "must_by_file": {"quiz": ["quiz_judge"], "progress": ["quiz_judge"]}}
    if m == "progress":
        quiz = quiz or MB.C.validate_contract(contract_obj("quiz"), uctx("quiz"))["contract"]
        ctx["sql_known"].update({s["名"]: s for s in quiz["sql"]})
        ctx["flows_ext"] = {f["名"]: f for f in quiz["流程"]}
        ctx["ui_paths"] = {a["路径"] for a in quiz["接口"]}
        ctx["taken_paths"] = set(ctx["ui_paths"])
        ctx["taken_acts"] = {a["动作"] for a in quiz["接口"]}
    ctx.update(over)
    return ctx


def vc(m, mut=None, **over):
    return C.validate_contract(contract_obj(m, mut), uctx(m, **over))


def has(r, want):
    return (not r["ok"]) and any(want in e for e in r["errors"])


def t_validate():
    print("一、约定 JSON 校验")
    r = vc("quiz")
    check(r["ok"] and r["contract"]["流程"][0]["调"][0]["类"] == "sql" and r["contract"]["接口"][0]["调用"][0]["类"] == "流程", "合法约定通过，调用项标上 sql / 流程 类别", r["errors"])
    check(vc("progress")["ok"], "progress 调 quiz 的共用流程（顶层允许）→ 通过", vc("progress")["errors"])
    check(C.validate_contract("不是对象", uctx("quiz"))["ok"] is False, "不是 JSON 对象 → 拒")
    # 引用不存在
    check(has(vc("quiz", lambda o: o["sql"][0].update(用列=["attempt.nope"])), "没有列「nope」"), "sql 用的列不在实体里 → 拒")
    check(has(vc("quiz", lambda o: o["sql"][0].update(表=["ghost"])), "表「ghost」"), "sql 的表不存在 → 拒")
    check(has(vc("quiz", lambda o: o["sql"][0].update(用列=["nope"])), "不在表 attempt 的列里") or has(vc("quiz", lambda o: o["sql"][0].update(用列=["nope"])), "不在"), "单写的列名不在所列表的列里 → 拒")
    check(has(vc("quiz", lambda o: o["流程"][0]["调"].append({"名": "ghost_sql", "给": []})), "「ghost_sql」不存在"), "流程调的 sql / 流程不在约定里 → 拒")
    check(has(vc("quiz", lambda o: o["接口"][0]["调用"].append({"名": "ghost_flow", "给": []})), "「ghost_flow」不存在"), "接口调的东西不存在 → 拒")
    check(has(vc("quiz", lambda o: o["界面"][0].update(用接口=["/nope"])), "用的接口「/nope」不存在"), "界面用的接口不存在 → 拒")
    check(vc("quiz", lambda o: o["接口"][0]["调用"].append({"名": "attempt_insert", "给": ["question_id", "given"]}))["ok"] is False, "接口调 gen 自带 sql 时同样核对参数（缺 gen sql 的必填）")
    check(vc("quiz", lambda o: o["接口"][0]["调用"].append({"名": "question_one", "给": ["id"]}))["ok"], "接口可以直接调 gen 的 CRUD sql（给全必填就行）")
    # 参数对不上
    check(has(vc("quiz", lambda o: o["接口"][0]["调用"][0].update(给=["question_id"])), "缺必填参数 ['given']"), "调用方给的没覆盖被调方必填 → 拒")
    check(has(vc("quiz", lambda o: o["接口"][0]["调用"][0].update(给=["question_id", "given", "zz"])), "多给了它没约定的键 ['zz']"), "调用方多给被调方没约定的键 → 拒")
    check(vc("quiz", lambda o: o["流程"][0]["入参"].append({"名": "level", "要求": "可选"}))["ok"], "被调方多出的可选入参，调用方可以不给")
    check(has(vc("quiz", lambda o: o["流程"][0]["入参"].append({"名": "level", "要求": "必填"})), "缺必填参数 ['level']"), "被调方多出必填入参，调用方没给 → 拒")
    check(has(vc("quiz", lambda o: o["流程"][0]["调"][0].pop("给")), "要写 给"), "调用只写名字不写给了哪些键 → 拒（没法核对）")
    check(has(vc("quiz", lambda o: o["sql"][0]["参数"].append({"名": "p", "要求": "随便"})), "只能是 必填 或 可选"), "要求不是 必填/可选 → 拒")
    # 越层 / 跨模块
    check(has(vc("quiz", lambda o: o["流程"][0]["调"].append({"名": "/quiz/answer", "给": []})), "越层"), "流程调接口 → 越层，拒")
    check(has(vc("quiz", lambda o: o["接口"][0]["调用"].append({"名": "/quiz/answer", "给": []})), "越层"), "接口调接口 → 越层，拒")
    check(has(vc("progress", lambda o: o["接口"][0]["调用"].append({"名": "ghost", "给": []})), "不存在"), "跨模块调不存在的东西 → 拒")
    check(has(vc("progress", flows_ext={}), "别的模块的流程「quiz_judge」"), "跨模块调流程：顶层「共用流程」没给本模块用 → 拒", vc("progress", flows_ext={})["errors"])
    check(has(vc("quiz", lambda o: (o["流程"][0]["调"].append({"名": "quiz_judge", "给": ["question_id", "given"]}))), "成环"), "流程互调成环 → 拒")
    # 动词 / 规则 / 范围 / 命名
    check(has(vc("quiz", lambda o: o["流程"][0].update(用动词=["魔法写入"])), "「魔法写入」不在能力清单里"), "未知动词 → 拒")
    check(has(vc("quiz", lambda o: [o["sql"][0].update(规则=[]), o["流程"][0].update(规则=[]), o["接口"][0].update(规则=[])]), "规则 R1 没有落在任何约定项上"), "本模块规则一条都没落地 → 拒")
    check(vc("quiz", lambda o: [o["sql"][0].update(规则=[]), o["流程"][0].update(规则=[])])["ok"], "规则只要落在一个约定项上就行（接口那条）")
    check(has(vc("quiz", lambda o: o["sql"][0].update(规则=["R9"])), "不是分给本模块的规则"), "规则号不是本模块的 → 拒")
    check(has(vc("quiz", lambda o: o["流程"].append(dict(o["流程"][0], 名="extra_flow"))), "不在层次×模块给本模块定的流程里"), "多出流程 → 拒")
    check(has(vc("quiz", lambda o: o["流程"].clear()), "没有约定"), "少流程 → 拒")
    check(has(vc("quiz", lambda o: o["接口"].clear()), "一个接口也没约定"), "接口文件里一个接口也没有 → 拒")
    check(has(vc("quiz", lambda o: o["接口"][0].update(文件="other")), "不在层次×模块给本模块定的接口文件里"), "接口文件不在计划里 → 拒")
    check(has(vc("quiz", lambda o: o["界面"].clear()), "没有约定"), "少界面 → 拒")
    check(has(vc("quiz", lambda o: o["sql"][0].update(名="log_x")), "要以「quiz_」开头"), "sql 名没带模块前缀 → 拒")
    check(has(vc("quiz", lambda o: o["sql"][0].update(名="attempt_list")), "gen 自动生成的重名"), "sql 与 gen 自带重名 → 拒")
    check(has(vc("quiz", lambda o: o["sql"][0].update(名="Quiz-Log")), "snake"), "命名不合规 → 拒")
    check(has(vc("quiz", taken_paths={"/quiz/answer"}), "已被占用"), "接口路径与已有重复 → 拒")
    check(has(vc("quiz", lambda o: o["接口"][0].update(动作="x y")), "snake"), "动作名不合规 → 拒")
    check(has(vc("quiz", lambda o: o["接口"][0].update(角色="admin")), "不在项目角色"), "角色不在项目角色里 → 拒")
    check(has(vc("quiz", lambda o: o["接口"][0].pop("响应")), "要有「响应」"), "接口没写响应 → 拒")
    check(has(vc("quiz", lambda o: o["接口"][0]["业务错误"].append({"码": 500, "情形": "x"})), "要是 4xx"), "业务错误码不是 4xx → 拒")
    check(has(vc("quiz", lambda o: o["流程"][0].update(出参=[])), "出参不能空"), "流程出参空 → 拒")
    check(has(vc("quiz", lambda o: o["流程"][0].update(写哪些表=["ghost"])), "写的表「ghost」"), "流程写的表不存在 → 拒")
    check(has(vc("progress", lambda o: o["接口"][0].update(调用=[])), "规定流程「quiz_judge」给接口文件「progress」用"), "层次×模块规定要用的流程，接口没调 → 拒")
    # 派生 / 签名 / 渲染
    q = vc("quiz")["contract"]
    dsql, dflow, dif = C.derive_sql(q), C.derive_flow(q["流程"][0]), C.derive_iface(q["接口"])
    check(dsql["sql"][0]["参数"] == ["question_id", "given"] and dsql["sql"][0]["可选参数"] == [], "derive_sql：参数 / 可选参数")
    check(dflow["入参"] == ["question_id", "given"] and dflow["用sql"] == ["quiz_log"] and dflow["出参"] == ["ok", "n"], "derive_flow：入参 / 用sql / 出参", dflow)
    check(dif["接口"][0]["调用"] == {"quiz_judge": ["question_id", "given"]} and dif["接口"][0]["响应"]["state"] == ["ok"], "derive_iface：调用 / 响应", dif)
    o = contract_obj("quiz", lambda x: x["sql"][0].update(参数=Pm("question_id", "given", opt=["given"])))
    o["流程"][0]["调"][0]["给"] = ["question_id"]
    qo = C.validate_contract(o, uctx("quiz"))
    check(qo["ok"] and C.derive_sql(qo["contract"])["sql"][0]["可选参数"] == ["given"], "可选参数 → 单文件计划的「可选参数」（实现要带空串保护）", qo["errors"])
    sg = C.signature(q)
    check(sg["sql"][0]["参数"] == ["question_id", "given"] and "作用" not in sg["sql"][0] and sg["流程"][0]["出参"] == ["ok", "n"] and sg["接口"][0]["响应"]["state"] == ["ok"], "signature 只给签名（不带作用 / 规则）")
    md = C.contracts_md(TOP, {"quiz": q})
    check("## quiz" in md and "POST /quiz/answer" in md and "quiz_judge" in md and "## progress" in md and "约定没写成" in md, "CONTRACTS.md 渲染（没写成的模块标出）", md[:300])


def t_compare():
    print("二、实现比对函数")
    ents_sql = "CREATE TABLE attempt (id INTEGER PRIMARY KEY, question_id INTEGER, given TEXT);"
    check(C.sql_result_cols("SELECT id, given AS g FROM attempt WHERE given = :g", ents_sql) == ["id", "g"], "sql_result_cols：空库里真跑，取返回列（别名也取）")
    check(C.sql_result_cols("INSERT INTO attempt(question_id) VALUES (:q)", ents_sql) == "写入", "写操作 → 写入")
    check(C.sql_result_cols("SELECT nope FROM attempt", ents_sql) is None, "跑不通 → None（判不了，放过，预编译另有检查）")
    it = {"返回": ["id", "given"]}
    check(C.check_sql_returns("a", it, ["id", "given"]) == [] and C.check_sql_returns("a", it, ["given", "id"]) == [], "返回列一致（顺序不计）")
    check("返回的列与约定不符" in C.check_sql_returns("a", it, ["id"])[0], "返回列不一致 → 报")
    check("约定返回列" in C.check_sql_returns("a", it, "写入")[0] and "约定是「写入」" in C.check_sql_returns("a", {"返回": "写入"}, ["id"])[0], "查询 / 写入 对不上 → 报")
    check(C.check_sql_returns("a", it, None) == [], "判不了的放过")
    sqls = lambda t: set(re.findall(r"sql:(\w+)", t))       # noqa: E731
    flows = lambda t: set(re.findall(r"flow:(\w+)", t))     # noqa: E731
    check(C.check_calls_match("f", "sql:a flow:x", ["a"], ["x"], sqls, flows) == [], "调用对象与约定一致")
    e = C.check_calls_match("f", "sql:b", ["a"], ["x"], sqls, flows)
    check(len(e) == 3 and any("约定要用 sql「a」" in x for x in e) and any("约定之外的 sql「b」" in x for x in e) and any("约定要调流程「x」" in x for x in e), "少调 / 多调 / 调了约定之外的 → 都报", e)
    resp = {"state": ["ok"], "lists": ["rows"], "messages": "是"}
    check(C.check_response("/p", resp, '消息 bot hi\n状态 ok 1\n表格 rows {rows}') == [], "响应键齐全")
    e = C.check_response("/p", resp, "返回 {\"x\":1}")
    check(len(e) == 3, "state / lists / messages 都缺 → 3 条", e)
    check(C.check_response("/p", {"state": ["ok"], "lists": [], "messages": "否"}, "返回 {\"ok\":\"{result.ok}\"}") == [], "返回 JSON 里的键也算")
    check(C.check_ui_actions("pg", "动作 a 远程 提交 x\n动作 b 远程 提交 y", {"a", "b"}) == [], "界面动作与约定一致")
    e = C.check_ui_actions("pg", "动作 a 远程 提交 x\n动作 z 远程 提交 y", {"a", "b"})
    check(len(e) == 2 and any("没有 `动作 b 远程" in x for x in e) and any("约定之外的接口动作「z」" in x for x in e), "界面少用 / 多用动作 → 报", e)


# ------------------------------------------------------------------ 三~五、假模型全流程

class FakeC(TM.Fake):
    """在 Fake 之上加「接口约定助手」的回复；bad = {("约定", 模块): [回复…]}。"""

    def __init__(self, contracts=None, **kw):
        super().__init__(**kw)
        self.cobj = contracts or {}

    def reply(self, user):
        if "接口约定助手" in user:
            m = re.search(r'"模块": "(\w+)"', user).group(1)
            return self.pick(("约定", m), dump(self.cobj.get(m) or contract_obj(m)))
        return super().reply(user)


def go(name, fake, **kw):
    return TM.go(name, fake, contract=True, **kw)


def files(r):
    return {f["文件"]: f for f in r["v2"].get("文件", [])}


def gens(fk, marker, file):
    return [u for u in fk.of(marker) if f"本文件：{file}" in u]


def t_full():
    print("三、假模型全流程（约定模式）")
    fk = FakeC()
    r, p, out = go("c_full", fk)
    fs = files(r)
    check(r["fixed"] and r["v2"]["结论"] == "成功" and r["v2"]["contract"] is True, "约定模式全流程成功", (r["stop"], {k: v["结果"] for k, v in fs.items()}))
    order = [f["文件"] for f in r["v2"]["文件"]]
    check(order.index("contracts/quiz.json") < order.index("contracts/progress.json") < order.index("queries/quiz_*.sql") and fs["contracts/quiz.json"]["层"] == "约定",
          "数据层之后、实现之前先做约定（按构建顺序每个模块一条记录）", order)
    check(len(fk.of("接口约定助手")) == 2 and not any(fk.of(m) for m in ("单文件规划助手（查询层）", "单文件规划助手（流程层）", "单文件规划助手（接口层）", "单文件规划助手（界面层）")),
          "每个模块一次约定调用；查询 / 流程 / 接口 / 界面不再另外做单文件规划", (len(fk.of("接口约定助手")), fk.calls))
    check(all((out / n).is_file() for n in ("CONTRACTS.md", "contracts.json")), "输出目录有 CONTRACTS.md + contracts.json")
    cj = json.loads((out / "contracts.json").read_text(encoding="utf-8"))
    check(set(cj) == {"quiz", "progress"} and cj["quiz"]["接口"][0]["响应"]["state"] == ["ok"] and "POST /quiz/answer" in (out / "CONTRACTS.md").read_text(encoding="utf-8"), "contracts.json / CONTRACTS.md 内容", list(cj))
    check(r["v2"]["约定"] == {"quiz": {"sql": 1, "流程": 1, "接口": 1, "界面": 1}, "progress": {"sql": 0, "流程": 0, "接口": 1, "界面": 1}}, "result.json v2.约定 记每模块约定项数", r["v2"]["约定"])
    p2 = fk.of("接口约定助手")[1]
    check("quiz_judge" in p2 and "quiz_log" in p2 and "写库表 app.db quiz_log" not in p2 and "本模块可调的共用流程" in p2, "progress 的约定调用只拿到 quiz 约定的签名（不是实现全文）", p2[-1500:])
    check(fs["scripts/quiz_judge.zs"]["规划尝试"] == 0 and fs["routes/quiz.zs"]["生成尝试"] == 1, "实现文件没有单独规划（计划由约定派生）", fs["routes/quiz.zs"])
    ip = fk.of(".zs 接口助手")
    check("本文件的约定项（已冻结）" in ip[1] and "约定签名" in ip[1] and "写库表 app.db quiz_log" not in ip[1] and "# 判一道题并写作答记录" not in ip[1], "接口生成：自己的约定项 + 被调流程的约定签名，没有对方实现全文", ip[1][-1200:])
    fp = fk.of(".zs 流程助手")[0]
    check("本流程的约定项（已冻结）" in fp and "约定签名" in fp and "本模块的 sql 全文" not in fp, "流程生成：自己的约定项 + 本模块 sql 的约定签名", fp[-900:])
    check(len(fk.of("需求核对员")) == 3, "规则核对照旧（流程 R1、quiz 接口 R1、progress 接口 R2）", len(fk.of("需求核对员")))
    check("实体 question" in fk.of("应用建模助手")[1], "数据层照旧：依赖模块实体全文")
    # 约定重写
    cb = contract_obj("quiz", lambda o: [o["sql"][0].update(规则=[]), o["流程"][0].update(规则=[]), o["接口"][0].update(规则=[])])
    fk = FakeC(bad={("约定", "quiz"): [dump(cb), dump(contract_obj("quiz"))]})
    r, _, _ = go("c_rw", fk)
    f = files(r)["contracts/quiz.json"]
    cp = fk.of("接口约定助手")
    check(r["fixed"] and f["规划尝试"] == 2 and len(cp) == 3 and "规则 R1 没有落在任何约定项上" in cp[1], "约定没过校验 → 报错原话带回重写一次通过", (f, cp[1][-300:]))
    # 约定两次不过 → 失败；本模块实现与依赖它的模块都跳过
    fk = FakeC(bad={("约定", "quiz"): [dump(cb)]})
    r, p, _ = go("c_fail", fk)
    fs = files(r)
    check(fs["contracts/quiz.json"]["结果"] == "失败" and "约定两次没过" in fs["contracts/quiz.json"]["失败原因"] and fs["contracts/progress.json"]["结果"] == "跳过", "约定两次不过 → 该模块失败，依赖它的模块约定跳过", {k: v["结果"] for k, v in fs.items()})
    check(all(fs[f]["结果"] == "跳过" for f in ("scripts/quiz_judge.zs", "routes/quiz.zs", "ui/quiz_page.ui", "routes/progress.zs", "ui/progress_page.ui")) and r["v2"]["结论"] != "成功" and not (p / "routes/quiz.zs").exists(), "没有约定的模块，下层文件都跳过（不调模型）")
    check(len(gens(fk, ".zs 接口助手", "routes/quiz.zs")) == 0, "跳过的文件没调模型")
    # 老做法仍可用
    r, _, _ = TM.go("c_old", TM.Fake())
    check(r["fixed"] and "contracts/quiz.json" not in files(r) and r["v2"]["contract"] is False, "--no-contract（contract=False）：仍是逐文件规划的老做法")


def bad_replies(name, kind, rel, bad, marker, want, fk_kw=None, files_key=None, second=None, ok=True, contracts=None):
    """第一次生成给 bad（或 bad 列表），之后用默认；检查被拒、报错原话进了下一次提示、最后通过。"""
    good = {"查询": f"=== queries/quiz_log.sql ===\n{TM.SQL_A}", "流程": f"=== scripts/quiz_judge.zs ===\n{TM.ZS_FLOW}", "接口": f"=== routes/quiz.zs ===\n{TM.ZS_QUIZ}", "界面": f"=== ui/quiz_page.ui ===\n{TM.UI_Q}"}[kind]
    seq = [bad, good] if isinstance(bad, str) else list(bad)
    fk = FakeC(bad={("生成", kind, rel): seq}, contracts=contracts)
    r, p, out = go(name, fk)
    f = files(r)[rel]
    ps = gens(fk, marker, rel)
    return fk, r, p, f, ps


def t_reject():
    print("四、实现与约定不一致被拒")
    SQL_SEL = "=== queries/quiz_log.sql ===\nSELECT :question_id AS a, :given AS b FROM attempt\n"
    fk, r, p, f, ps = bad_replies("c_sql_kind", "查询", "queries/quiz_*.sql", SQL_SEL, "SQLite 语句助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and "约定是「写入」，实现却是查询" in ps[1], "sql：约定是写入，实现写成查询 → 拒，带原话重写", (f, ps[1][-300:] if len(ps) > 1 else ps))
    # 可选参数保护（约定标可选 → sql 比较必须带空串保护）
    co = contract_obj("quiz", lambda o: o["sql"][0].update(参数=Pm("question_id", "given", opt=["given"])))
    co["流程"][0]["调"][0]["给"] = ["question_id"]
    SQL_G = "=== queries/quiz_log.sql ===\nINSERT INTO attempt(question_id, given, correct) SELECT :question_id, 'x', 0 FROM question q WHERE q.id = :question_id AND (:given IS NULL OR :given = '' OR q.answer = :given)\n"
    fk = FakeC(bad={("生成", "查询", "queries/quiz_*.sql"): [f"=== queries/quiz_log.sql ===\n{TM.SQL_A}", SQL_G]}, contracts={"quiz": co})
    r, p, out = go("c_opt", fk)
    f = files(r)["queries/quiz_*.sql"]
    ps = gens(fk, "SQLite 语句助手", "queries/quiz_*.sql")
    check(r["fixed"] and f["生成尝试"] == 2 and "没有空值保护" in ps[1], "约定标可选的 sql 参数：比较没带空串保护 → 拒，带保护写法后通过", (f, r["stop"], ps[1][-300:] if len(ps) > 1 else ""))
    # 流程出参
    zs = TM.ZS_FLOW.replace(',"n":"{n}"', "")
    fk, r, p, f, ps = bad_replies("c_flow_out", "流程", "scripts/quiz_judge.zs", f"=== scripts/quiz_judge.zs ===\n{zs}", ".zs 流程助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and "没有出参 n" in ps[1], "流程：返回里缺约定的出参 → 拒", (f, ps[1][-300:] if len(ps) > 1 else ""))
    # 流程调用对象
    zs = TM.ZS_FLOW.replace("写库表 app.db quiz_log {args}", "写库表 app.db attempt_insert {args}").replace("设 args.given = {given}\n", "设 args.given = {given}\n设 args.correct = 0\n")
    fk, r, p, f, ps = bad_replies("c_flow_call", "流程", "scripts/quiz_judge.zs", f"=== scripts/quiz_judge.zs ===\n{zs}", ".zs 流程助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and "约定要用 sql「quiz_log」" in ps[1] and "约定之外的 sql「attempt_insert」" in ps[1], "流程：用的 sql 与约定的调用对象不一致 → 拒", (f, ps[1][-400:] if len(ps) > 1 else ""))
    # 接口：响应键 / 动作 / 调用 / 路径
    zs = TM.ZS_QUIZ.replace('返回 {"ok":"{result.ok}"}', '返回 {"done":"{result.ok}"}')
    fk, r, p, f, ps = bad_replies("c_if_resp", "接口", "routes/quiz.zs", f"=== routes/quiz.zs ===\n{zs}", ".zs 接口助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and "state 里有「ok」" in ps[1], "接口：响应里缺约定的 state 键 → 拒", (f, ps[1][-300:] if len(ps) > 1 else ""))
    zs = TM.ZS_QUIZ.replace("动作 quiz_answer", "动作 other_name")
    fk, r, p, f, ps = bad_replies("c_if_act", "接口", "routes/quiz.zs", f"=== routes/quiz.zs ===\n{zs}", ".zs 接口助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and "动作名要是「quiz_answer」" in ps[1], "接口：动作名与约定不符 → 拒", (f, ps[1][-300:] if len(ps) > 1 else ""))
    zs = TM.ZS_QUIZ.replace("  设 result = 执行 scripts/quiz_judge.zs question_id={question_id} given={given}\n", "  设 result.ok = 1\n")
    fk, r, p, f, ps = bad_replies("c_if_call", "接口", "routes/quiz.zs", f"=== routes/quiz.zs ===\n{zs}", ".zs 接口助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and "约定要调流程「quiz_judge」" in ps[1], "接口：没调约定里的流程 → 拒", (f, ps[1][-300:] if len(ps) > 1 else ""))
    zs = TM.ZS_QUIZ + "\n接口 POST /quiz/extra 动作 quiz_extra\n  用包 db http common\n  返回 {\"ok\":\"1\"}\n结束\n"
    fk, r, p, f, ps = bad_replies("c_if_path", "接口", "routes/quiz.zs", f"=== routes/quiz.zs ===\n{zs}", ".zs 接口助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and "多写了约定之外的接口 /quiz/extra" in ps[1], "接口：多写约定之外的接口 → 拒", (f, ps[1][-300:] if len(ps) > 1 else ""))
    co = contract_obj("quiz", lambda o: o["接口"][0]["响应"].update(messages="是"))
    zs_msg = TM.ZS_QUIZ.replace('  返回 {"ok":"{result.ok}"}', "  状态 ok {result.ok}\n  消息 bot hi")
    fk = FakeC(bad={("生成", "接口", "routes/quiz.zs"): [f"=== routes/quiz.zs ===\n{TM.ZS_QUIZ}", f"=== routes/quiz.zs ===\n{zs_msg}"]}, contracts={"quiz": co})
    r, p, _ = go("c_if_msg", fk)
    f = files(r)["routes/quiz.zs"]
    ps = gens(fk, ".zs 接口助手", "routes/quiz.zs")
    check(r["fixed"] and f["生成尝试"] == 2 and "messages=是" in ps[1], "接口：约定 messages=是 但实现没有消息 → 拒", (f, r["stop"], ps[1][-300:] if len(ps) > 1 else ""))
    # 界面动作
    ui = TM.UI_Q.replace("动作 quiz_answer 远程", "动作 question_open 远程")
    fk, r, p, f, ps = bad_replies("c_ui", "界面", "ui/quiz_page.ui", f"=== ui/quiz_page.ui ===\n{ui}", ".ui 界面助手", "")
    check(r["fixed"] and f["生成尝试"] == 2 and len(ps) == 2 and "约定之外的接口动作「question_open」" in ps[1], "界面：用了约定「用接口」之外的动作 → 拒，带原话重写", (f, ps[1][-300:] if len(ps) > 1 else ""))


def t_isolation():
    print("五、文件之间互不依赖 / 回退 / 试调 / 继续构建")
    junk = "=== queries/quiz_log.sql ===\nSELECT nope FROM nowhere WHERE x = :question_id AND y = :given\n"
    fk = FakeC(bad={("生成", "查询", "queries/quiz_*.sql"): [junk]})
    r, p, out = go("c_iso", fk)
    fs = files(r)
    check(fs["queries/quiz_*.sql"]["结果"] == "失败", "查询文件失败（sql 写不成）", fs["queries/quiz_*.sql"])
    check(all(fs[f]["结果"] == "通过" for f in ("scripts/quiz_judge.zs", "routes/quiz.zs", "routes/progress.zs", "ui/quiz_page.ui", "ui/progress_page.ui")) and not any(v["结果"] == "跳过" for v in fs.values()),
          "别的文件失败不再连锁跳过：流程 / 接口 / 界面照常按约定实现并通过", {k: v["结果"] for k, v in fs.items()})
    check(fs["routes/quiz.zs"].get("试调", {}).get("跳过") and "queries/quiz_log.sql" in fs["routes/quiz.zs"]["试调"]["跳过"], "依赖的 sql 文件没写成 → 该接口这次不试调（记跳过，不算接口的错）", fs["routes/quiz.zs"].get("试调"))
    check(r["v2"]["结论"] == "部分成功" and "queries/quiz_*.sql" in r["stop"], "结论部分成功，只列失败的那个查询文件", r["stop"][:300])
    # 对照：老做法里同样的失败会让流程 / 接口 / 界面跳过
    fk = TM.Fake(bad={("生成", "查询", "queries/quiz_*.sql"): [junk]})
    r, _, _ = TM.go("c_iso_old", fk)
    check(files(r)["scripts/quiz_judge.zs"]["结果"] == "跳过", "（对照）逐文件规划的老做法：同样的失败会连锁跳过")
    # mgen_fallback
    old = os.environ.get("DSLAGENT_MODELS")
    BAD = f"=== routes/quiz.zs ===\n{TM.BAD_COND_EQ}"
    GOOD = f"=== routes/quiz.zs ===\n{TM.ZS_QUIZ}"
    try:
        os.environ["DSLAGENT_MODELS"] = dump({"mgen": "haiku", "mgen_fallback": "opus"})
        fk = FakeC(bad={("生成", "接口", "routes/quiz.zs"): [BAD, BAD, GOOD]})
        r, p, out = go("c_fb", fk)
        f = files(r)["routes/quiz.zs"]
        calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        qz = gens(fk, ".zs 接口助手", "routes/quiz.zs")
        check(r["fixed"] and f["结果"] == "通过" and f["生成尝试"] == 3 and f["回退"] == "opus" and len(qz) == 3 and fk.models[fk.prompts.index(qz[2])] == "opus" and "前两次生成都没过检查" in qz[2],
              "约定模式下 mgen 两次没过 → mgen_fallback 再生成 1 次通过（带前两次报错）", f)
        check(sum(1 for c in calls if c.get("fallback")) == 1 and next(c for c in calls if c.get("fallback"))["step"] == "mgen_fallback", "calls.json 标明回退")
    finally:
        if old is None:
            os.environ.pop("DSLAGENT_MODELS", None)
        else:
            os.environ["DSLAGENT_MODELS"] = old
    # 试调：外键 409
    ZS_FK = TM.ZS_QUIZ_FK
    ZS_OK = ZS_FK.replace("设 args.question_id = 9999", "设 args.question_id = {question_id}")
    co = contract_obj("quiz", lambda o: o["接口"][0]["调用"].append({"名": "attempt_insert", "给": ["question_id", "given", "correct"]}))
    fk = FakeC(bad={("生成", "接口", "routes/quiz.zs"): [f"=== routes/quiz.zs ===\n{ZS_FK}", f"=== routes/quiz.zs ===\n{ZS_OK}"]}, contracts={"quiz": co})
    r, p, out = go("c_trial", fk)
    f = files(r)["routes/quiz.zs"]
    qz = gens(fk, ".zs 接口助手", "routes/quiz.zs")
    check(r["fixed"] and f["生成尝试"] == 2 and "[试调不过]" in qz[1] and "FOREIGN KEY" in qz[1] and f["试调"]["调用"] >= 1, "约定模式：接口通过静态与约定比对后仍试调，外键 409 → 报错原话带回重写", (f, r["stop"], qz[1][-300:] if len(qz) > 1 else ""))
    # 整体试调一轮：不过的接口文件及点到名的流程重写 1 轮
    orig = MB.TR.run
    state = {"n": 0}

    def fake_run(root, items_by_file, rows=3):
        if len(items_by_file) >= 2 and state["n"] == 0:
            state["n"] += 1
            return {"problems": {"routes/quiz.zs": ["[试调不过] routes/quiz.zs 接口 POST /quiz/answer（入参全给）入参 {} → 500：接口出错；响应：流程 quiz_judge 出错"]}, "calls": 2, "skipped": ""}
        return {"problems": {}, "calls": 1, "skipped": ""}
    MB.TR.run = fake_run
    try:
        fk = FakeC()
        r, p, out = go("c_round", fk)
    finally:
        MB.TR.run = orig
    fs = files(r)
    check(r["fixed"] and state["n"] == 1 and fs["routes/quiz.zs"].get("试调重写") and fs["scripts/quiz_judge.zs"].get("试调重写") and not fs["routes/progress.zs"].get("试调重写"),
          "全部实现后统一试调一轮：不过的接口文件 + 报错点到名的流程 带报错重写 1 轮，其它不动", {k: v.get("试调重写") for k, v in fs.items()})
    fp = gens(fk, ".zs 流程助手", "scripts/quiz_judge.zs")
    ip = gens(fk, ".zs 接口助手", "routes/quiz.zs")
    check(len(fp) == 2 and len(ip) == 2 and "试调不过" in fp[1] and "试调不过" in ip[1], "重写提示里带试调报错原话", (len(fp), len(ip)))
    check(fs["routes/quiz.zs"]["结果"] == "通过" and (p / "routes/quiz.zs").is_file() and (p / "scripts/quiz_judge.zs").is_file(), "重写后文件在、结果通过")
    # 继续构建：沿用已冻结的约定
    bad = {("生成", "接口", "routes/progress.zs"): [f"=== routes/progress.zs ===\n{TM.BAD_COND_EQ}"]}
    d = TM.TMP / "c_resume"
    shutil.rmtree(d, ignore_errors=True)
    r1 = V.run_newproj(REQ, d / "proj", d / "out", model=FakeC(bad=bad), modular=True, contract=True)
    check(files(r1)["routes/progress.zs"]["结果"] == "失败" and files(r1)["contracts/progress.json"]["结果"] == "通过", "（准备）第一次：progress 接口失败，约定都通过")
    fk = FakeC()
    r2 = V.run_newproj(REQ, d / "proj", d / "out", model=fk, modular=True, resume=True)
    fs = files(r2)
    check(r2["fixed"] and not fk.of("接口约定助手") and fs["contracts/quiz.json"].get("沿用") and fs["contracts/progress.json"].get("沿用") and r2["v2"]["contract"] is True,
          "继续构建：约定模式沿用上次冻结的约定（不再调约定），只重做失败的文件", (r2["stop"], r2["v2"].get("contract"), fk.calls))
    check(fs["routes/progress.zs"]["结果"] == "通过" and fs["routes/progress.zs"].get("上次失败"), "失败的接口文件带上次失败原因重做通过")


def t_from_plan():
    print("六、--from-plan / CLI")
    d1 = TM.TMP / "fp_old"
    shutil.rmtree(d1, ignore_errors=True)
    r1 = V.run_newproj(REQ, d1 / "proj", d1 / "out", model=TM.Fake(), modular=True)
    out1 = d1 / "out"
    d2 = TM.TMP / "fp_new"
    shutil.rmtree(d2, ignore_errors=True)
    fk = FakeC()
    r2 = V.run_newproj(REQ, d2 / "proj", d2 / "out", model=fk, modular=True, contract=True, from_plan=str(out1))
    out2 = d2 / "out"
    check(r1["fixed"] and r2["fixed"] and not fk.of("项目架构师") and not fk.of("项目架构助手"), "from-plan：不再调顶层规划 / 层次×模块，新目录里全流程成功", (r2["stop"], fk.calls[:6]))
    check((out2 / "PLAN.md").read_text(encoding="utf-8") == (out1 / "PLAN.md").read_text(encoding="utf-8") and (out2 / "LAYERS.md").read_text(encoding="utf-8") == (out1 / "LAYERS.md").read_text(encoding="utf-8")
          and json.loads((out2 / "top.json").read_text(encoding="utf-8")) == json.loads((out1 / "top.json").read_text(encoding="utf-8")), "新目录里的 PLAN.md / LAYERS.md / top.json 与旧运行一致")
    check(r2["v2"]["从已有规划"]["目录"] == str(out1) and (d2 / "proj/routes/quiz.zs").is_file() and r2["v2"]["contract"] is True and "contracts/quiz.json" in files(r2), "记录里写明从哪个目录读的规划；约定模式照常")
    check(r2["calls"] < r1["calls"] + 2 and (out1 / "result.json").is_file(), "旧目录不被改动（result.json 仍在）")
    # 没有 top.json / split.json：按 RESUME.md 的还原法（result.json + calls/）
    d3 = TM.TMP / "fp_old2"
    shutil.copytree(d1, d3)
    for n in ("top.json", "split.json"):
        (d3 / "out" / n).unlink()
    lp = MB.load_plan(d3 / "out", REQ)
    check(lp["top"]["构建顺序"] == ["quiz", "progress"] and set(lp["split"]["模块"]) == {"quiz", "progress"} and lp["restored"], "没有 top.json / split.json → 从 result.json 与 calls/ 还原", lp["restored"])
    lp0 = MB.load_plan(out1, REQ)
    check(lp0["restored"] == ["top.json / split.json"] and lp0["split"]["规则表"] == {"R1": TM.R1, "R2": TM.R2}, "有 top.json / split.json 直接读")
    # 读不到
    d4 = TM.TMP / "fp_bad"
    shutil.rmtree(d4, ignore_errors=True)
    r4 = V.run_newproj(REQ, d4 / "proj", d4 / "out", model=FakeC(), modular=True, contract=True, from_plan=str(TM.TMP / "nope"))
    check(not r4["fixed"] and "从已有规划开始" in r4["stop"] and not (d4 / "proj/routes").exists(), "旧目录读不到 → 直接失败，不写新项目", r4["stop"])
    r5 = V.run_newproj(REQ, d4 / "proj", d4 / "out", model=FakeC(), modular=True, resume=True, from_plan=str(out1))
    check(not r5["fixed"] and "不能和 --resume" in r5["stop"], "from-plan 与 resume 不能同用")
    # CLI
    from tools.dslagent import __main__ as M
    seen = {}
    real = V.run_newproj
    V.run_newproj = lambda req, project, out, **kw: seen.update(kw) or {"fixed": True, "calls": 0, "cost": 0, "seconds": 0, "stop": "", "changed_files": []}
    try:
        rq = TM.TMP / "cli_req2.txt"
        rq.write_text("需求", encoding="utf-8")
        base = ["newproj", "--modular"]
        tail = [str(rq), str(TM.TMP / "cli_p2"), "--out", str(TM.TMP / "cli_o2")]
        M.main(base + tail)
        check(seen.get("modular") is True and "contract" not in seen and "from_plan" not in seen, "CLI --modular 缺省：不传 contract（= 默认先约定接口）", seen)
        seen.clear()
        M.main(base + ["--no-contract"] + tail)
        check(seen.get("contract") is False, "CLI --no-contract → run_newproj(contract=False)", seen)
        seen.clear()
        M.main(base + ["--from-plan", str(out1)] + tail)
        check(seen.get("from_plan") == str(out1) and seen.get("modular") is True, "CLI --from-plan DIR → run_newproj(from_plan=DIR)", seen)
        for bad in (["newproj", "--from-plan", "x"] + tail, ["newproj", "--no-contract"] + tail, base + ["--from-plan", "x", "--resume"] + tail):
            try:
                M.main(bad)
                ok = False
            except SystemExit:
                ok = True
            check(ok, f"CLI 非法组合被拒：{' '.join(bad[1:4])}")
    finally:
        V.run_newproj = real
    import inspect
    sig = inspect.signature(real).parameters
    check(sig["contract"].default is None and sig["from_plan"].default is None, "run_newproj 新参数 contract / from_plan（缺省 None：modular 默认约定模式）")
    check((ROOT / "tools/dslagent/packs/newproj/prompts/sys_mcontract.md").is_file() and "{" in (ROOT / "tools/dslagent/packs/newproj/prompts/sys_mcontract.md").read_text(encoding="utf-8"), "sys_mcontract.md 提示词在，带 JSON 示例")


def main():
    try:
        t_validate()
        t_compare()
        t_full()
        t_reject()
        t_isolation()
        t_from_plan()
    finally:
        shutil.rmtree(TM.TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
