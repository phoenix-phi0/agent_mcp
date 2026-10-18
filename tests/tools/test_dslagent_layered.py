# -*- coding: utf-8 -*-
"""newproj --layered（三级规划：确认分层 → 确认文件 → 每个文件单独规划再生成）＋引擎修复 A（JSON 文本里的 {x.y} 能取到）＋ B（被杀的 claude 调用费用不再记 0）。不调真模型。

    .venv/bin/python tests/tools/test_dslagent_layered.py
"""
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="dslagent_ly_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ.pop("NEWPROJ_FORCE_SUBPROCESS", None)
os.environ.pop("NEWPROJ_COST_CAP", None)

from tools.dslagent import engines, v2 as V      # noqa: E402

DEFS = ROOT / "tools/dslagent/verbs/newproj/defs"
sys.path.insert(0, str(DEFS))
import _layer as L      # noqa: E402,F401
import _params as P      # noqa: E402

PASS = FAIL = 0
REQ = "做一个答题：有题目，作答要记录；交答案时按库里记的题判对错并写作答记录。"
ENT_Q = "实体 question 题目\n  字段 title 文本 必填 题干\n  字段 answer 文本 必填 答案\n结束\n"
ENT_A = "实体 attempt 作答\n  字段 question_id 整数 必填 索引 关联 question 题目\n  字段 given 文本 必填 作答\n  字段 correct 整数 必填 默认 0 对错\n结束\n"
SQL_A = "INSERT INTO attempt(question_id, given, correct) SELECT :question_id, :given, CASE WHEN q.answer = :given THEN 1 ELSE 0 END FROM question q WHERE q.id = :question_id\n"
ZS_A = ("接口 POST /attempt/answer 动作 attempt_answer\n  用包 db http common\n  事务 app.db\n    设 n = 写库表 app.db attempt_log {request}\n  结束\n"
        "  返回 {\"ok\":\"1\"}\n结束\n")
UI_A = ("界面 表单 答题页\n  分组 区 竖排\n    字段 given 作答\n    动作 attempt_answer 远程 提交 交答案\n  结束\n结束\n")
RULE1 = "交答案时按库里记的题判对错，不信前端传的答案"


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))




import _lstep as S      # noqa: E402

LAYERS4 = ["实体", "查询", "接口", "界面"]


def layers_obj(**kw):
    p = {"模板": "full", "角色": [], "规则": [{"号": "R1", "文": RULE1}], "层": list(LAYERS4)}
    p.update(kw)
    return p


def fitem(layer, path, ent, rules=(), deps=(), what="x"):
    return {"层": layer, "路径": path, "实体": ent, "作用": what, "规则": list(rules), "依赖": list(deps)}


def files_obj(**kw):
    fs = [fitem("实体", "entities/question.entity", "question", what="题目"),
          fitem("实体", "entities/attempt.entity", "attempt", deps=["entities/question.entity"], what="作答"),
          fitem("查询", "queries/attempt_*.sql", "attempt", ["R1"], ["entities/attempt.entity"], "写作答"),
          fitem("接口", "routes/attempt.zs", "attempt", ["R1"], ["entities/attempt.entity", "queries/attempt_*.sql"], "交答案"),
          fitem("界面", "ui/quiz.ui", "attempt", [], ["routes/attempt.zs"], "答题页")]
    return {"文件": fs, **kw}


def dump(o):
    return json.dumps(o, ensure_ascii=False)


# ------------------------------------------------------------------ 一、确认分层

def t_layers():
    print("一、确认分层（校验）")
    r = S.validate_layers(dump(layers_obj()), REQ)
    check(r["ok"] and r["层"] == LAYERS4 and r["规则表"] == {"R1": RULE1} and r["模板"] == "full", "合法分层", r)
    r = S.validate_layers(dump({"模板": "full", "角色": [], "规则": [], "层": ["实体"]}))
    check(r["ok"] and r["层"] == ["实体"], "纯数据项目可以只有实体层（没有规则）", r)
    r = S.validate_layers("```json\n" + dump(layers_obj()) + "\n```")
    check(r["ok"], "带围栏的 JSON 能解析")
    r = S.validate_layers(dump(layers_obj(层=["界面", "实体", "接口"])))
    check(r["ok"] and r["层"] == ["实体", "接口", "界面"], "层按固定顺序整理（实体 查询 接口 界面）", r)

    def bad(want, msg, req="", **kw):
        r = S.validate_layers(dump(layers_obj(**kw)), req)
        e = "；".join(r["errors"])
        check(not r["ok"] and want in e, msg, e)
    bad("模板「x」不对", "模板不在 default/full/private", 模板="x")
    bad("模板必须是 private", "有角色但模板不是 private", 角色=["teacher"])
    bad("必须给「角色」", "需求提到登录但没给角色", req="要登录，老师才能导入题目")
    r = S.validate_layers(dump(layers_obj(模板="private", 角色=["teacher", "student"])), "要登录")
    check(r["ok"] and r["角色模板"] == "private", "private + 角色放行")
    bad("规则号「R1」重复", "规则号重复", 规则=[{"号": "R1", "文": "a"}, {"号": "R1", "文": "b"}])
    bad("两个都不能空", "规则号为空", 规则=[{"号": "", "文": "a"}])
    bad("两个都不能空", "规则文为空", 规则=[{"号": "R1", "文": ""}])
    bad("层「库」不对", "层不在候选里", 层=["实体", "库"])
    bad("必须包含「实体」", "层里没有实体", 层=["查询"])
    bad("「层」里有重复项", "层重复", 层=["实体", "实体"])
    bad("至少要有「查询」或「接口」", "有规则却没有查询 / 接口层", 层=["实体", "界面"])
    bad("要是文本列表", "层不是列表", 层="实体")
    check(not S.validate_layers("不是 JSON")["ok"], "不是 JSON → 不过")
    bad("角色「Bad」要是英文小写", "角色名不合规", 模板="private", 角色=["Bad"])


# ------------------------------------------------------------------ 二、确认文件

def vf(obj, layers=LAYERS4, rules=None, **kw):
    r = S.validate_files(dump(obj), layers, {"R1": RULE1} if rules is None else rules, **kw)
    return r["ok"], "\n".join(r["errors"]), r


def t_files():
    print("二、确认文件（校验）")
    ok, e, r = vf(files_obj())
    check(ok and len(r["files"]) == 5, "合法文件清单", e)
    check(r["files"][2]["依赖"][0] == "entities/attempt.entity" and r["files"][3]["依赖"][0] == "entities/attempt.entity", "查询 / 接口文件自动补上主实体的实体文件依赖")

    def bad(obj, want, msg, **kw):
        ok, e, _ = vf(obj, **kw)
        check(not ok and want in e, msg, e)

    o = files_obj()
    o["文件"][0]["路径"] = "entities/other.entity"
    bad(o, "命名：", "实体文件路径与实体名不符")
    o = files_obj()
    o["文件"][2]["路径"] = "queries/attempt_log.sql"
    bad(o, "queries/attempt_*.sql", "查询层路径必须写成 queries/<实体>_*.sql")
    o = files_obj()
    o["文件"][3]["路径"] = "routes/other.zs"
    bad(o, "routes/attempt.zs 或 routes/attempt_<后缀>.zs", "接口文件命名不合规")
    o = files_obj()
    o["文件"][3]["路径"] = "routes/attempt_extra.zs"
    o["文件"][4]["依赖"] = ["routes/attempt_extra.zs"]
    ok, e, _ = vf(o)
    check(ok, "routes/<实体>_<后缀>.zs 放行", e)
    o = files_obj()
    o["文件"][4]["路径"] = "views/x.ui"
    bad(o, "ui/<英文小写名>.ui", "界面文件命名不合规")
    o = files_obj()
    o["文件"].append(dict(o["文件"][1]))
    bad(o, "路径「entities/attempt.entity」重复", "路径重复")
    o = files_obj()
    o["文件"][2]["实体"] = "ghost"
    o["文件"][2]["路径"] = "queries/ghost_*.sql"
    bad(o, "没有 entities/ghost.entity", "查询用到的实体没有实体文件")
    o = files_obj()
    o["文件"][1]["依赖"] = ["entities/nope.entity"]
    bad(o, "依赖：", "依赖不存在的文件")
    o = files_obj()
    o["文件"][2]["依赖"] = ["routes/attempt.zs"]
    bad(o, "不能依赖更高层", "查询依赖接口（更高层）→ 不过")
    o = files_obj()
    o["文件"][0]["依赖"] = ["entities/attempt.entity"]
    bad(o, "排在后面", "同层依赖排在后面的文件 → 不过")
    o = files_obj()
    o["文件"][2]["依赖"] = ["queries/attempt_*.sql"]
    bad(o, "不能依赖自己", "依赖自己")
    o = files_obj()
    o["文件"][2]["规则"] = []
    o["文件"][3]["规则"] = []
    bad(o, "规则 R1", "规则没有分到任何查询 / 接口文件")
    o = files_obj()
    o["文件"][0]["规则"] = ["R1"]
    o["文件"][2]["规则"] = []
    o["文件"][3]["规则"] = []
    bad(o, "规则 R1", "规则只分给实体文件不算（要查询 / 接口）")
    o = files_obj()
    o["文件"][2]["规则"] = ["R9"]
    bad(o, "规则号「R9」没在第一步", "规则号不在规则表")
    o = files_obj()
    o["文件"][4]["层"] = "视图"
    bad(o, "不在已确认的层", "层不在已确认的层里")
    bad(files_obj(), "本批只列", "本批不允许的层", allow=["实体", "查询"])
    ok, e, r = vf({"文件": files_obj()["文件"][:3]}, allow=["实体", "查询"], final=False, rules={"R1": RULE1})
    check(ok and len(r["files"]) == 3, "分批：非最后一批不查规则覆盖，只列允许的层", e)
    ok, e, r2 = vf({"文件": files_obj()["文件"][3:]}, allow=["接口", "界面"], known=r["files"])
    check(ok, "分批：后一批的依赖可以指向前一批已接受的文件，规则覆盖按全体算", e)
    bad({"文件": files_obj()["文件"][3:]}, "依赖：", "分批：依赖没列过的文件 → 不过", allow=["接口", "界面"])
    # 无 60 上限
    many = [fitem("实体", f"entities/e{i}.entity", f"e{i}") for i in range(70)]
    ok, e, r = vf({"文件": many}, layers=["实体"], rules={})
    check(ok and len(r["files"]) == 70, "70 个文件不被拒（没有 60 个上限）", e)
    # 报错按类汇总
    o = files_obj()
    o["文件"][4]["路径"] = "views/x.ui"
    o["文件"][1]["依赖"] = ["entities/nope.entity"]
    o["文件"][2]["规则"] = []
    o["文件"][3]["规则"] = []
    ok, e, r = vf(o)
    cats = [x.split("：")[0] for x in r["errors"]]
    check(not ok and cats == ["命名", "依赖", "规则"], "报错按类汇总（命名 / 依赖 / 规则 各一行）", r["errors"])
    ok, e, _ = vf(files_obj(), tpl="private")
    check(ok, "private 模板正常")
    o = {"文件": [fitem("实体", "entities/user.entity", "user")]}
    bad(o, "user 实体由 gen 生成", "private 不许列 user", layers=["实体"], rules={}, tpl="private")
    check(not S.validate_files("不是 JSON", LAYERS4, {})["ok"] and not S.validate_files("{}", LAYERS4, {})["ok"], "不是 JSON / 没有「文件」→ 不过")


# ------------------------------------------------------------------ 三、单文件规划校验

def t_plans():
    print("三、单文件规划（校验）")
    p, e = S.plan_entity(dump({"字段": [{"名": "title", "类型": "文本"}], "关联": [], "约束": []}), set())
    check(not e and p["字段"][0]["名"] == "title", "实体计划合法", e)
    p, e = S.plan_entity(dump({"字段": [{"名": "q_id"}], "关联": ["question"]}), {"tag"})
    check(e and "关联「question」不是本文件依赖的" in e[0], "实体关联不在依赖里 → 不过", e)
    p, e = S.plan_entity(dump({"字段": [{"名": "id"}]}), set())
    check(e and "不能叫 id" in e[0], "字段叫 id → 不过")
    p, e = S.plan_entity(dump({"字段": []}), set())
    check(e and "非空列表" in e[0], "字段为空 → 不过")

    ok = {"sql": [{"名": "attempt_log", "参数": ["a"], "说明": "x", "规则": ["R1"]}]}
    p, e = S.plan_query(dump(ok), "attempt", ["R1"], {"question_one"})
    check(not e, "查询计划合法", e)
    for nm, want, msg in (("zz_log", "要以「attempt_」开头", "sql 名没有实体前缀"), ("attempt_list", "与 gen 自动生成的重名", "与 gen 五条重名"),
                          ("attempt_old", "项目里已经有了", "与已有 sql 重名")):
        o = {"sql": [{"名": nm, "参数": [], "规则": ["R1"]}]}
        p, e = S.plan_query(dump(o), "attempt", ["R1"], {"attempt_old"})
        check(e and want in "；".join(e), msg, e)
    o = {"sql": [{"名": "attempt_log", "参数": [], "规则": []}]}
    p, e = S.plan_query(dump(o), "attempt", ["R1"], set())
    check(e and "规则 R1 没有落到" in e[0], "分到的规则没有落到任何 sql → 不过", e)
    o = {"sql": [{"名": "attempt_a", "参数": [], "规则": ["R1"]}, {"名": "attempt_a", "参数": [], "规则": []}]}
    p, e = S.plan_query(dump(o), "attempt", ["R1"], set())
    check(e and "重复" in "；".join(e), "sql 名重复")

    base = {"接口": [{"路径": "/attempt/answer", "动作": "attempt_answer", "角色": "", "入参": ["given"], "用sql": ["attempt_log"], "规则": ["R1"], "说明": "x"}], "新sql": []}

    def pi(o, **kw):
        a = dict(ent="attempt", assigned=["R1"], roles=[], taken_paths={"/attempt/list"}, taken_acts={"attempt_list"}, avail={"attempt_log", "attempt_insert"})
        a.update(kw)
        return S.plan_iface(dump(o), a["ent"], a["assigned"], a["roles"], a["taken_paths"], a["taken_acts"], a["avail"])
    p, e = pi(base)
    check(not e and p["接口"][0]["用sql"] == ["attempt_log"], "接口计划合法", e)
    o = json.loads(dump(base))
    o["接口"][0]["用sql"] = ["ghost_sql"]
    p, e = pi(o)
    check(e and "用sql「ghost_sql」不存在" in "；".join(e), "用sql 引用不存在的 sql → 不过", e)
    o["新sql"] = [{"名": "ghost_sql", "参数": []}]
    p, e = pi(o)
    check(e and "只能放 queries/attempt_*.sql" in "；".join(e), "新sql 不是主实体前缀 → 不过", e)
    o["新sql"] = [{"名": "attempt_extra", "参数": ["x"]}]
    o["接口"][0]["用sql"] = ["attempt_extra"]
    p, e = pi(o)
    check(not e and p["新sql"][0]["名"] == "attempt_extra", "用sql 引用本文件「新sql」放行", e)
    o["新sql"] = [{"名": "attempt_log", "参数": []}]
    p, e = pi(o)
    check(e and "已经存在" in "；".join(e), "新sql 与已有 sql 重名 → 不过", e)
    o = json.loads(dump(base))
    o["接口"][0]["路径"] = "/attempt/list"
    p, e = pi(o)
    check(e and "已被占用" in "；".join(e), "接口路径与已有 / gen 路径重复 → 不过", e)
    o = json.loads(dump(base))
    o["接口"][0]["动作"] = "attempt_list"
    p, e = pi(o)
    check(e and "动作名「attempt_list」已被占用" in "；".join(e), "动作名重复 → 不过")
    o = json.loads(dump(base))
    o["接口"][0]["角色"] = "teacher"
    p, e = pi(o)
    check(e and "不在项目角色" in "；".join(e), "角色不在项目角色里 → 不过")
    p, e = pi(o, roles=["teacher", "student"])
    check(not e, "角色在项目角色里放行", e)
    o = json.loads(dump(base))
    del o["接口"][0]["入参"]
    p, e = pi(o)
    check(e and "要有「入参」" in "；".join(e), "没有入参 → 不过")
    o = json.loads(dump(base))
    o["接口"][0]["规则"] = []
    p, e = pi(o)
    check(e and "规则 R1 没有落到任何接口" in "；".join(e), "分到的规则没落到接口 → 不过")

    p, e = S.plan_ui(dump({"页面": [{"名": "答题页", "用接口": ["/attempt/answer"], "字段": ["given"]}]}), {"/attempt/answer"})
    check(not e, "界面计划合法", e)
    p, e = S.plan_ui(dump({"页面": [{"名": "答题页", "用接口": ["/nope/x"], "字段": []}]}), {"/attempt/answer"})
    check(e and "用接口「/nope/x」不存在" in e[0], "界面引用不存在的接口 → 不过", e)
    p, e = S.plan_ui(dump({"页面": []}), set())
    check(e, "页面为空 → 不过")
    v = verb_mod("校验分层清单")
    check(v(dump({"模板": "full"}))["ok"] == "否", "旧动词 校验分层清单 仍在（layered.py 不再用）")


# ------------------------------------------------------------------ 四、三级流程（假模型）

ENT_PLAN = {"question": {"字段": [{"名": "title", "类型": "文本", "说明": "题干"}, {"名": "answer", "类型": "文本", "说明": "答案"}], "关联": [], "约束": []},
            "attempt": {"字段": [{"名": "question_id", "类型": "整数"}, {"名": "given", "类型": "文本"}, {"名": "correct", "类型": "整数"}], "关联": ["question"], "约束": []}}
QPLAN = {"sql": [{"名": "attempt_log", "参数": ["question_id", "given"], "说明": "写作答", "规则": ["R1"]}]}
IPLAN = {"接口": [{"路径": "/attempt/answer", "动作": "attempt_answer", "角色": "", "入参": ["question_id", "given"], "用sql": ["attempt_log"], "规则": ["R1"], "说明": "交答案"}], "新sql": []}
UPLAN = {"页面": [{"名": "答题页", "说明": "答题", "用接口": ["/attempt/answer", "/question/list"], "字段": ["given"]}]}


class Fake:
    """按提示词里的角色标记认出是哪一步、哪个文件。bad = {键: [回复…]} 覆盖默认回复（用完回最后一个）：
    ("分层",) ("清单", "实体、查询、…") ("计划", 路径) ("生成", 路径) ("核对",)。files 按 allow 文本（'、'.join(本批层)）给每批清单。"""

    def __init__(self, layers=None, files=None, bad=None, cost=0.0, plans=None, ents=None, gen_zs=None):
        self.layers = layers or layers_obj()
        self.files = files or {"实体、查询、接口、界面": files_obj()}
        self.bad, self.cost, self.prompts, self.used, self.calls = bad or {}, cost, [], {}, []
        self.plans = {"实体": dict(ENT_PLAN), "查询": QPLAN, "接口": IPLAN, "界面": UPLAN}
        self.plans.update(plans or {})
        self.ents = dict(ents or {"question": ENT_Q, "attempt": ENT_A})
        self.gen_zs = gen_zs or {}

    def pick(self, key, default):
        if key in self.bad:
            seq = self.bad[key]
            i = self.used.get(key, 0)
            self.used[key] = i + 1
            return seq[min(i, len(seq) - 1)]
        return default

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.prompts.append(user)
        self.calls.append(tag)
        text = self.reply(user)
        return text if isinstance(text, dict) else {"text": text, "cost": self.cost}

    def of(self, marker):
        return [p for p in self.prompts if marker in p]

    def reply(self, user):
        if "项目分层确认助手" in user:
            return self.pick(("分层",), dump(self.layers))
        if "文件清单助手" in user:
            allow = re.search(r"本批只列这几层：(\S+)", user).group(1)
            return self.pick(("清单", allow), dump(self.files[allow]))
        if "单文件规划助手" in user:
            layer = re.search(r"本层：(\S+)", user).group(1)
            item = json.loads(re.search(r"本文件项：(\{.*?\})\n分配的规则", user, re.S).group(1))
            plan_ = self.plans[layer]
            if layer == "实体":
                plan_ = plan_[item["实体"]]
            elif isinstance(plan_, dict) and item["路径"] in plan_:
                plan_ = plan_[item["路径"]]
            return self.pick(("计划", item["路径"]), dump(plan_))
        if "应用建模助手" in user:
            rel = re.search(r"本文件：(\S+)", user).group(1)
            n = rel.split("/")[-1].split(".")[0]
            return self.pick(("生成", rel), f"=== {rel} ===\n{self.ents[n]}")
        if "SQLite 语句助手" in user:
            n = re.search(r"本实体：(\w+)", user).group(1)
            rel = re.search(r"本文件：(\S+)", user).group(1)
            return self.pick(("生成", rel), f"=== queries/{n}_log.sql ===\n{SQL_A}")
        if ".zs 接口助手" in user:
            rel = re.search(r"本文件：(\S+)", user).group(1)
            return self.pick(("生成", rel), self.gen_zs.get(rel) or f"=== {rel} ===\n{ZS_A}")
        if ".ui 界面助手" in user:
            rel = re.search(r"本文件：(\S+)", user).group(1)
            return self.pick(("生成", rel), f"=== {rel} ===\n{UI_A}")
        if "需求核对员" in user:
            rules = json.loads(re.search(r"规则：(\[.*?\]) 本功能sql", user, re.S).group(1))
            ok = dump([{"序号": i, "规则": r, "实现": "是", "依据": "attempt_answer"} for i, r in enumerate(rules, 1)])
            return self.pick(("核对",), ok)
        return "?"


def go(name, fake, req=REQ, **kw):
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    return V.run_newproj(req, d / "proj", d / "out", model=fake, layered=True, **kw), d / "proj", d / "out"


def files(r):
    return {f["文件"]: f for f in r["v2"].get("文件", [])}


FULL = "实体、查询、接口、界面"


def t_flow():
    print("四、三级流程：成功 / 记录 / 各步输入")
    fk = Fake(cost=0.01)
    r, p, out = go("ok", fk)
    fs = files(r)
    check(r["fixed"] and r["v2"]["结论"] == "成功" and r["v2"]["layered"] is True, "全过 = 成功", (r["stop"], r["v2"].get("结论")))
    # 分层 1 + 清单 1 + question(规划+生成 2) + attempt(2) + 查询(2) + 接口(规划 1 + 生成 1 + 核对 1) + 界面(2)
    check(r["calls"] == 1 + 1 + 2 + 2 + 2 + 3 + 2, "调用数：分层 1 + 清单 1 + 实体 2×2 + 查询 2 + 接口 3 + 界面 2 = 13", r["calls"])
    check(set(fs) == {"entities/question.entity", "entities/attempt.entity", "queries/attempt_*.sql", "routes/attempt.zs", "ui/quiz.ui"}, "v2.文件 逐文件记录", sorted(fs))
    a = fs["routes/attempt.zs"]
    check(a["层"] == "接口" and a["实体"] == "attempt" and a["结果"] == "通过" and a["规划尝试"] == 1 and a["生成尝试"] == 1 and a["重写"] == 0
          and a["未实现规则"] == [] and a["核对"] == 1 and "尝试" not in a, "接口文件记 规划尝试 / 生成尝试 / 重写 / 核对 / 未实现规则", a)
    check(all(f["规划尝试"] == 1 and f["生成尝试"] == 1 for f in fs.values()), "每个文件都记了规划尝试和生成尝试")
    lay = r["v2"]["清单"]
    check(lay["模式"] == "全量" and lay["层"] == LAYERS4 and lay["文件数"] == 5 and lay["规则数"] == 1 and len(lay["批次"]) == 1, "清单记录：模式 / 层 / 文件数 / 批次", lay)
    check((p / "entities/question.entity").is_file() and (p / "app.db").is_file() and (p / "queries/attempt_log.sql").is_file() and (p / "ui/quiz.ui").is_file(), "实体、建库、sql、ui 落盘")
    zs = (p / "routes/attempt.zs").read_text(encoding="utf-8")
    check("/attempt/list" in zs and "/attempt/answer" in zs, "routes/attempt.zs 是 gen 的 CRUD 文件，接口追加在后面不覆盖")
    rows = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check(len(rows) == r["calls"] and abs(r["cost"] - 0.01 * r["calls"]) < 1e-9, "calls.json 逐次记花费")
    check({c.get("file") for c in rows} >= {"分层确认", "entities/question.entity", "routes/attempt.zs", "ui/quiz.ui"}, "calls.json 每次调用标了所属文件 / 步骤", [c.get("file") for c in rows])
    check(r["v2"]["预算"]["max_calls"] >= r["calls"], "总调用上限随文件数放宽", r["v2"]["预算"])
    # 各步输入
    first = fk.prompts[0]
    check("项目分层确认助手" in first and RULE1 not in first.split("需求：")[0], "第一步只给需求，不带细节")
    fl = fk.of("文件清单助手")[0]
    check("已确认分层" in fl and "本批只列这几层：实体、查询、接口、界面" in fl and RULE1 in fl, "第二步输入 = 已确认分层 + 规则表 + 本批层", fl[-300:])
    ep = [x for x in fk.of("单文件规划助手") if "本层：实体" in x and "entities/attempt.entity" in x][0]
    check("实体 question 题目" in ep.split("已写好的被关联实体全文")[1], "实体规划输入：依赖实体 question 的全文（真实存在）", ep[-300:])
    ip = [x for x in fk.of("单文件规划助手") if "本层：接口" in x][0]
    check("INSERT INTO attempt" in ip and "attempt_log" in ip and RULE1 in ip and "/attempt/list" in ip, "接口规划输入：已有 sql 全文 + 规则 + 已被占用的路径（gen CRUD）", ip[-700:])
    up = [x for x in fk.of("单文件规划助手") if "本层：界面" in x][0]
    check("/attempt/answer" in up and "attempt_answer" in up and "/question/list" in up, "界面规划输入：依赖接口文件里的接口 + gen CRUD 路径", up[-600:])
    g = fk.of(".zs 接口助手")[0]
    check("单文件计划" in g and "attempt_log" in g and "INSERT INTO attempt" in g.split("用sql 里已有 sql 的全文")[1], "接口生成输入：单文件计划 + 用到的 sql 全文")
    rj = json.loads((out / "result.json").read_text(encoding="utf-8"))
    check(rj["v2"]["文件"] and rj["v2"]["结论"] == "成功", "写进 result.json")

    # 接口没有规则 → 不调核对
    lay = layers_obj(规则=[], 层=["实体", "查询", "接口", "界面"])
    fo = files_obj()
    for f in fo["文件"]:
        f["规则"] = []
    q2 = {"sql": [{"名": "attempt_log", "参数": ["question_id", "given"], "说明": "写作答", "规则": []}]}
    i2 = json.loads(dump(IPLAN))
    i2["接口"][0]["规则"] = []
    r, _, _ = go("norules", Fake(layers=lay, files={FULL: fo}, plans={"查询": q2, "接口": i2}))
    check(r["fixed"] and r["calls"] == 12, "接口没有规则 → 不调核对：12 次", (r["stop"], r["calls"]))

    # 纯数据：只有实体层，没有 gen 之外的任何层
    r, p, _ = go("dataonly", Fake(layers={"模板": "full", "角色": [], "规则": [], "层": ["实体"]}, files={"实体": {"文件": files_obj()["文件"][:2]}}))
    check(r["fixed"] and r["calls"] == 1 + 1 + 4 and not (p / "ui/quiz.ui").exists(), "只确认实体层：只建实体（+gen），共 6 次调用", (r["stop"], r["calls"]))

    # 没有 60 上限：35 个实体全做
    many = {"文件": [fitem("实体", f"entities/e{i}.entity", f"e{i}") for i in range(35)]}
    ents = {f"e{i}": f"实体 e{i} 实体{i}\n  字段 name 文本 必填 名称\n结束\n" for i in range(35)}
    plans = {"实体": {f"e{i}": {"字段": [{"名": "name", "类型": "文本"}], "关联": []} for i in range(35)}}
    r, p, _ = go("many", Fake(layers={"模板": "full", "角色": [], "规则": [], "层": ["实体"]}, files={"实体": many}, ents=ents, plans=plans))
    check(r["fixed"] and len(files(r)) == 35 and r["v2"]["清单"]["模式"] == "全量", "35 个文件（> 30、没有 60 上限）：只有一个层组，不分批，全部建成", (r["stop"], len(files(r))))


def t_layer_retry():
    print("五、分层 / 文件清单 重写")
    bad = layers_obj(层=["库"])
    fk = Fake(bad={("分层",): [dump(bad), dump(layers_obj())]})
    r, _, _ = go("layer_rw", fk)
    second = fk.of("项目分层确认助手")[1]
    check(r["fixed"] and "层「库」不对" in second.split("上次的报错：")[1], "分层校验不过 → 带报错重写，通过", (r["stop"], second[-200:]))
    fk = Fake(bad={("分层",): [dump(bad)]})
    r, _, _ = go("layer_bad", fk)
    check(not r["fixed"] and "分层确认三次都没过" in r["stop"] and r["calls"] == 3 and r["v2"]["结论"] == "失败", "分层三次不过 → 失败（3 次调用）", (r["stop"], r["calls"]))
    fk = Fake(bad={("分层",): [dump(layers_obj(角色=["t"])), dump(layers_obj(角色=["t"], 模板="private"))]}, layers=layers_obj())
    go("layer_role", fk)
    p2 = fk.of("项目分层确认助手")
    check(len(p2) >= 2 and "模板必须是 private" in p2[1].split("上次的报错：")[1], "有角色但不是 private → 带报错重写")

    o = files_obj()
    o["文件"][4]["路径"] = "views/x.ui"
    o["文件"][2]["规则"] = []
    o["文件"][3]["规则"] = []
    fk = Fake(bad={("清单", FULL): [dump(o), dump(files_obj())]})
    r, _, _ = go("files_rw", fk)
    second = fk.of("文件清单助手")[1].split("上次的报错：")[1]
    check(r["fixed"] and "命名：" in second and "规则：" in second and second.count("\n") >= 1, "文件清单不过 → 报错按类汇总，带进重写", second[:300])
    check(len(r["v2"]["清单"]["批次"]) == 1 and r["v2"]["清单"]["批次"][0]["尝试"] == 2, "清单步骤记了尝试次数")
    fk = Fake(bad={("清单", FULL): [dump(o)]})
    r, p, _ = go("files_bad", fk)
    check(not r["fixed"] and "文件清单三次都没过" in r["stop"] and len(fk.of("文件清单助手")) == 3 and not (p / "entities").exists(), "文件清单三次不过 → 失败，没建任何文件", (r["stop"], r["calls"]))


def t_batch():
    print("六、分批")
    A = FULL
    f_all = files_obj()
    f_a = {"文件": f_all["文件"][:3]}
    f_b = {"文件": [f_all["文件"][3]]}
    f_c = {"文件": [f_all["文件"][4]]}
    batches = {"实体、查询": f_a, "接口": f_b, "界面": f_c, A: f_all}
    old = os.environ.get("NEWPROJ_LAYERED_BATCH")
    os.environ["NEWPROJ_LAYERED_BATCH"] = "3"
    try:
        fk = Fake(files=batches)
        r, p, out = go("batch", fk)
        lay = r["v2"]["清单"]
        check(r["fixed"] and lay["模式"] == "分批" and "改分批" in lay["分批原因"] and len(lay["批次"]) == 3, "全量清单 5 个 > 3 → 改分批：先实体＋查询，再接口，再界面", (r["stop"], lay))
        check(fk.of("文件清单助手")[0].count("本批只列这几层：实体、查询、接口、界面") == 1 and "本批只列这几层：接口" in fk.of("文件清单助手")[1]
              and "本批只列这几层：界面" in fk.of("文件清单助手")[2], "三次清单的本批层依次是 全量 / 接口 / 界面（实体＋查询沿用全量清单里已通过的部分，不重列）")
        b2 = fk.of("文件清单助手")[1]
        check("attempt_log" in b2 and "项目现状" in b2 and "entities/attempt.entity" in b2, "接口层清单看到的是真实存在的 sql 和已有文件", b2[-500:])
        check(set(files(r)) == set(f["路径"] for f in f_all["文件"]) and all(f["结果"] == "通过" for f in files(r).values()), "分批建完五个文件")
        # 全量清单被杀 → 改分批重列实体＋查询
        fk = Fake(files=batches, bad={("清单", A): [{"text": "", "rc": -9, "cost": 0.1}]})
        r, _, _ = go("batch_killed", fk)
        lay = r["v2"]["清单"]
        check(r["fixed"] and lay["模式"] == "分批" and "没列完" in lay["分批原因"] and len(fk.of("文件清单助手")) == 4, "全量清单被杀 / 超长 → 改分批重列（不再重试全量）", (r["stop"], lay["分批原因"]))
        # 批 2 清单列不出来 → 部分成功，前面的文件保留
        fk = Fake(files=batches, bad={("清单", "接口"): [dump({"文件": [fitem("接口", "routes/zz.zs", "zz")]})]})
        r, p, _ = go("batch_b2fail", fk)
        check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and "接口层的文件清单没列成" in r["stop"] and (p / "queries/attempt_log.sql").is_file(), "后一批清单三次不过 → 部分成功，已建的文件保留", r["stop"])
    finally:
        os.environ.pop("NEWPROJ_LAYERED_BATCH", None) if old is None else os.environ.__setitem__("NEWPROJ_LAYERED_BATCH", old)
    # 没设阈值时 5 个文件不分批
    r, _, _ = go("nobatch", Fake(files=batches))
    check(r["fixed"] and r["v2"]["清单"]["模式"] == "全量", "文件数没超 30 → 全量，不分批")


def t_perfile():
    print("七、单文件规划 / 生成 / 失败 / 跳过")
    # 规划引用不存在的 sql → 带报错重写
    badi = json.loads(dump(IPLAN))
    badi["接口"][0]["用sql"] = ["ghost_sql"]
    fk = Fake(bad={("计划", "routes/attempt.zs"): [dump(badi), dump(IPLAN)]})
    r, _, _ = go("plan_ghost", fk)
    second = [x for x in fk.of("单文件规划助手") if "本层：接口" in x][1]
    a = files(r)["routes/attempt.zs"]
    check(r["fixed"] and a["规划尝试"] == 2 and "用sql「ghost_sql」不存在" in second.split("上次的报错：")[1], "接口规划引用不存在的 sql → 被拒，带报错重写", (r["stop"], second[-250:]))
    # 规划两次都不过 → 该文件失败；生成不调；依赖它的界面跳过
    fk = Fake(bad={("计划", "routes/attempt.zs"): [dump(badi)]})
    r, p, _ = go("plan_fail", fk)
    fs = files(r)
    check(fs["routes/attempt.zs"]["结果"] == "失败" and "单文件规划两次没过" in fs["routes/attempt.zs"]["失败原因"] and not fk.of(".zs 接口助手") and fs["ui/quiz.ui"]["结果"] == "跳过"
          and r["v2"]["结论"] == "部分成功", "规划两次不过 → 文件失败、不进生成、界面跳过、部分成功", {k: v["结果"] for k, v in fs.items()})
    # 界面规划引用不存在的接口
    badu = {"页面": [{"名": "答题页", "用接口": ["/nope/x"], "字段": []}]}
    fk = Fake(bad={("计划", "ui/quiz.ui"): [dump(badu), dump(UPLAN)]})
    r, _, _ = go("plan_ui_bad", fk)
    second = [x for x in fk.of("单文件规划助手") if "本层：界面" in x][1]
    check(r["fixed"] and "用接口「/nope/x」不存在" in second, "界面规划引用不存在的接口 → 被拒重写")
    # 查询规划不合规
    badq = {"sql": [{"名": "zz_log", "参数": [], "规则": ["R1"]}]}
    fk = Fake(bad={("计划", "queries/attempt_*.sql"): [dump(badq), dump(QPLAN)]})
    r, _, _ = go("plan_q_bad", fk)
    check(r["fixed"] and "要以「attempt_」开头" in [x for x in fk.of("单文件规划助手") if "本层：查询" in x][1], "查询规划 sql 名没有实体前缀 → 被拒重写")

    # 新sql 随接口文件一起生成
    SQL_X = "SELECT COUNT(*) AS n FROM attempt WHERE question_id = :question_id\n"
    zs_x = ("接口 POST /attempt/answer 动作 attempt_answer\n  用包 db http common\n  设 n = 写库表 app.db attempt_log {request}\n  设 c = 查一行表 app.db attempt_count {request}\n  返回 {c}\n结束\n")
    ip = json.loads(dump(IPLAN))
    ip["接口"][0]["用sql"] = ["attempt_log", "attempt_count"]
    ip["新sql"] = [{"名": "attempt_count", "参数": ["question_id"], "说明": "统计"}]
    gen_x = f"=== routes/attempt.zs ===\n{zs_x}=== queries/attempt_count.sql ===\n{SQL_X}"
    fk = Fake(plans={"接口": ip}, gen_zs={"routes/attempt.zs": gen_x})
    r, p, _ = go("new_sql", fk)
    check(r["fixed"] and (p / "queries/attempt_count.sql").is_file() and "attempt_count" in (p / "routes/attempt.zs").read_text(encoding="utf-8"), "计划的「新sql」随接口文件一起生成并落盘", (r["stop"], files(r)["routes/attempt.zs"]))
    # 新sql 漏写 → 重写；仍漏 → 失败，zs 还原
    only_zs = f"=== routes/attempt.zs ===\n{zs_x}"
    fk = Fake(plans={"接口": ip}, gen_zs={"routes/attempt.zs": only_zs})
    r, p, _ = go("new_sql_miss", fk)
    a = files(r)["routes/attempt.zs"]
    check(a["结果"] == "失败" and "计划的新sql「attempt_count」没写" in a["失败原因"] and not (p / "queries/attempt_count.sql").exists()
          and "/attempt/answer" not in (p / "routes/attempt.zs").read_text(encoding="utf-8"), "新sql 漏写 → 重写一次仍漏 → 失败、zs 还原成 gen 的 CRUD 文件", a)
    # 多写计划外的 sql
    extra = f"=== routes/attempt.zs ===\n{ZS_A}=== queries/attempt_zzz.sql ===\nSELECT 1\n"
    fk = Fake(gen_zs={"routes/attempt.zs": extra})
    r, _, _ = go("sql_extra", fk)
    check(files(r)["routes/attempt.zs"]["结果"] == "失败" and "多写了计划里没有的 sql" in files(r)["routes/attempt.zs"]["失败原因"], "多写计划外的 sql → 不过")
    # 下游能用上随接口生成的 sql 和接口：界面计划里能选到 /attempt/answer
    ok = Fake(plans={"界面": UPLAN})
    r, _, _ = go("ui_paths", ok)
    check(r["fixed"], "界面规划可选的接口 = 已建好的接口 + gen CRUD")

    # 实体生成重写
    fk = Fake(bad={("生成", "entities/question.entity"): ["=== entities/question.entity ===\n实体 question 题目\n  字段 title 乱写 必填 题干\n结束\n", f"=== entities/question.entity ===\n{ENT_Q}"]})
    r, p, _ = go("ent_rw", fk)
    f = files(r)["entities/question.entity"]
    check(r["fixed"] and f["规划尝试"] == 1 and f["生成尝试"] == 2 and f["重写"] == 1 and "乱写" in fk.of("应用建模助手")[1], "实体校验不过 → 带报错重写一次（生成尝试 2）", f)
    two = f"=== entities/question.entity ===\n{ENT_Q}\n{ENT_A}"
    fk = Fake(bad={("生成", "entities/question.entity"): [two, f"=== entities/question.entity ===\n{ENT_Q}"]})
    r, _, _ = go("ent_two", fk)
    check(r["fixed"] and "只能定义实体 question" in fk.of("应用建模助手")[1], "一个实体文件定义了别的实体 → 不过")

    # 实体链失败 → 跳过；没有实体 → 失败
    badq_ = "=== entities/question.entity ===\n不是实体\n"
    fk = Fake(bad={("生成", "entities/question.entity"): [badq_]})
    r, p, _ = go("ent_fail", fk)
    fs = files(r)
    check(not r["fixed"] and fs["entities/question.entity"]["结果"] == "失败" and fs["entities/attempt.entity"]["结果"] == "跳过"
          and "依赖的文件没写成" in fs["entities/attempt.entity"]["失败原因"] and "没有一个实体写成" in r["stop"], "唯一实体链全失败 → 失败并说明", (r["stop"], fs))
    # 两个独立实体：一个坏另一个及其上层照做
    f2 = files_obj()
    f2["文件"][1]["依赖"] = []
    pl_ent = dict(ENT_PLAN)
    pl_ent["attempt"] = {"字段": [{"名": "given", "类型": "文本"}], "关联": []}
    q2 = {"sql": [{"名": "attempt_log", "参数": ["given"], "说明": "x", "规则": ["R1"]}]}
    i2 = json.loads(dump(IPLAN))
    i2["接口"][0]["入参"] = ["given"]
    sql2 = "=== queries/attempt_log.sql ===\nINSERT INTO attempt(given) VALUES (:given)\n"
    zs2 = ZS_A
    fk = Fake(files={FULL: f2}, plans={"实体": pl_ent, "查询": q2, "接口": i2}, ents={"question": ENT_Q, "attempt": "实体 attempt 作答\n  字段 given 文本 必填 作答\n  字段 correct 整数 必填 默认 0 对错\n结束\n"},
              bad={("生成", "entities/question.entity"): ["=== entities/question.entity ===\n不是实体\n"], ("生成", "queries/attempt_*.sql"): [sql2]})
    r, p, _ = go("ent_partial", fk)
    fs = files(r)
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and "entities/question.entity" in r["stop"] and fs["entities/attempt.entity"]["结果"] == "通过"
          and fs["routes/attempt.zs"]["结果"] == "通过" and not (p / "entities/question.entity").exists(), "独立的实体及其上层继续做完；失败文件已撤回", (r["stop"], {k: v["结果"] for k, v in fs.items()}))

    # 查询失败 → 接口、界面跳过，不调模型
    badsql = "=== queries/attempt_log.sql ===\nSELECT nope FROM attempt WHERE a = :question_id AND b = :given\n"
    fk = Fake(bad={("生成", "queries/attempt_*.sql"): [badsql]})
    r, p, _ = go("sql_fail", fk)
    fs = files(r)
    check(fs["queries/attempt_*.sql"]["结果"] == "失败" and fs["routes/attempt.zs"]["结果"] == "跳过" and fs["ui/quiz.ui"]["结果"] == "跳过"
          and "queries/attempt_*.sql" in fs["routes/attempt.zs"]["失败原因"] and "routes/attempt.zs" in fs["ui/quiz.ui"]["失败原因"], "查询失败 → 依赖它的接口、界面跳过并记原因", {k: (v["结果"], v["失败原因"][:50]) for k, v in fs.items()})
    check(r["calls"] == 1 + 1 + 2 + 2 + 1 + 2 and not (p / "queries/attempt_log.sql").exists() and "因依赖失败跳过" in r["stop"], "跳过的文件不调模型；失败的 sql 没落盘", (r["calls"], r["stop"]))
    fk = Fake(bad={("生成", "queries/attempt_*.sql"): [f"=== queries/attempt_log.sql ===\nINSERT INTO attempt(question_id, given) VALUES (:question_id, :given, :extra)\n", f"=== queries/attempt_log.sql ===\n{SQL_A}"]})
    r, _, _ = go("sql_params", fk)
    second = fk.of("SQLite 语句助手")[1]
    check(r["fixed"] and "参数与计划不符" in second and "extra" in second, "sql 参数与计划不符 → 不过，带报错重写")

    # 接口参数核对
    zs_bad = ("=== routes/attempt.zs ===\n接口 POST /attempt/answer 动作 attempt_answer\n  用包 db http common\n  设 given = 1\n"
              "  事务 app.db\n    设 n = 写库表 app.db attempt_log {request}\n  结束\n  返回 {\"ok\":\"1\"}\n结束\n")
    ip3 = json.loads(dump(IPLAN))
    ip3["接口"][0]["入参"] = ["question_id"]
    good = f"=== routes/attempt.zs ===\n{ZS_A.replace('{request}', '{p}').replace('  事务', '  设 p.question_id = {question_id}' + chr(10) + '  设 p.given = 1' + chr(10) + '  事务')}"
    fk = Fake(plans={"接口": ip3}, bad={("生成", "routes/attempt.zs"): [zs_bad, good]})
    r, p, _ = go("zs_params", fk)
    second = fk.of(".zs 接口助手")[1]
    check(r["fixed"] and files(r)["routes/attempt.zs"]["生成尝试"] == 2 and "参数核对不过" in second and "given" in second and "/attempt/answer" in second, "接口缺参数来源 → 参数核对不过，点名接口 / 参数后重写", second[-400:])
    check((p / "routes/attempt.zs").read_text(encoding="utf-8").count("接口 POST /attempt/list") == 1, "重写后 CRUD 部分仍在、没重复追加")
    fk = Fake(plans={"接口": ip3}, bad={("生成", "routes/attempt.zs"): [zs_bad]})
    r, p, _ = go("zs_params2", fk)
    txt = (p / "routes/attempt.zs").read_text(encoding="utf-8")
    check(files(r)["routes/attempt.zs"]["结果"] == "失败" and "/attempt/answer" not in txt and "/attempt/list" in txt, "两次缺来源 → 该文件失败，撤回成 gen 的 CRUD 文件")

    # 规则核对
    no = dump([{"序号": 1, "规则": RULE1, "实现": "否", "依据": "没判题"}])
    fk = Fake(bad={("核对",): [no]})
    r, p, _ = go("rule_no", fk)
    a = files(r)["routes/attempt.zs"]
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and a["结果"] == "通过" and a["未实现规则"] == ["R1：" + RULE1] and a["核对"] == 2 and a["生成尝试"] == 2,
          "规则核对：重写一次仍未实现 → 记未实现规则，部分成功（文件保留）", a)
    check("以下业务规则没有实现" in fk.of(".zs 接口助手")[1] and "没判题" in fk.of(".zs 接口助手")[1], "未实现规则带进重写提示词")
    ok = dump([{"序号": 1, "规则": RULE1, "实现": "是", "依据": "x"}])
    r, _, _ = go("rule_rw", Fake(bad={("核对",): [no, ok]}))
    check(r["fixed"] and files(r)["routes/attempt.zs"]["核对"] == 2, "规则核对：重写后通过 → 成功")

    # 超长 / 被杀
    killed = {"text": "", "rc": -9, "cost": 0.3}
    fk = Fake(bad={("生成", "routes/attempt.zs"): [killed]})
    r, p, _ = go("killed", fk)
    a = files(r)["routes/attempt.zs"]
    check(a["结果"] == "失败" and "模型没有完成输出" in a["失败原因"] and len(fk.of(".zs 接口助手")) == 1, "被杀（rc=-9）→ 该接口文件失败，不重试", a)
    check(files(r)["ui/quiz.ui"]["结果"] == "跳过" and files(r)["entities/attempt.entity"]["结果"] == "通过" and r["v2"]["结论"] == "部分成功" and abs(r["cost"] - 0.3) < 1e-9,
          "运行没终止：其余文件照做，依赖它的界面跳过；被杀调用的花费计入", (r["stop"], r["cost"]))
    long_ = {"text": "x" * 10, "rc": 0, "reason": "输出超长", "cost": 0.2}
    fk = Fake(bad={("计划", "ui/quiz.ui"): [long_]})
    r, _, _ = go("overlong", fk)
    f = files(r)["ui/quiz.ui"]
    check(f["结果"] == "失败" and "输出超长" in f["失败原因"] and len(fk.of("单文件规划助手")) == 5 and not fk.of(".ui 界面助手"), "单文件规划输出超长 → 该文件失败，不重试，不进生成")
    fk = Fake(bad={("生成", "ui/quiz.ui"): [long_]})
    r, _, _ = go("overlong2", fk)
    check(files(r)["ui/quiz.ui"]["结果"] == "失败" and len(fk.of(".ui 界面助手")) == 1, "生成输出超长 → 该界面文件失败，不重试")


def t_budget():
    print("八、熔断 / 预算 / 路由")
    fk = Fake(cost=1.0)
    r, p, _ = go("cap", fk, cost_cap=4.5)
    fs = files(r)
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and r["stop"].startswith("部分成功：花费达上限") and r["calls"] == 5,
          "花费熔断：累计 ≥ 上限就不再调模型（分层 + 清单 + question 规划 / 生成 + attempt 规划，共 5 次）", (r["stop"], r["calls"], r["cost"]))
    check((p / "entities/question.entity").is_file() and fs["routes/attempt.zs"]["结果"] == "未做" and fs["ui/quiz.ui"]["结果"] == "未做" and fs["entities/attempt.entity"]["结果"] == "未做",
          "熔断后已写文件保留，后面的文件记「未做」", {k: v["结果"] for k, v in fs.items()})
    os.environ["NEWPROJ_COST_CAP"] = "2.5"
    try:
        r, _, _ = go("cap_env", Fake(cost=1.0))
        check(r["stop"].startswith("部分成功：花费达上限") and r["calls"] == 3, "环境变量 NEWPROJ_COST_CAP 同样生效", (r["stop"], r["calls"]))
    finally:
        os.environ.pop("NEWPROJ_COST_CAP", None)
    r, _, _ = go("capfirst", Fake(cost=1.0), cost_cap=0.5)
    check(not r["fixed"] and r["calls"] == 1 and "花费达上限" in r["stop"], "第一步之后就超上限 → 清单都不列（分层确认后熔断，失败）", (r["stop"], r["calls"]))
    r, _, _ = go("nocap", Fake(cost=1.0))
    check(r["fixed"] and r["cost"] >= 13, "不设上限 = 不限", (r["stop"], r["cost"]))
    old = os.environ.get("DSLAGENT_MODELS")
    os.environ["DSLAGENT_MODELS"] = json.dumps({"sub": "codex:gpt-6-luna:medium"})
    try:
        r, _, out = go("codex", Fake(cost=0.0), cost_cap=0.01)
        rows = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        check(r["fixed"] and r["v2"]["codex调用"] == r["calls"] and r["cost"] == 0 and all(c.get("engine") == "codex" for c in rows), "codex：花费记 0、只记调用数；DSLAGENT_MODELS.sub 对全部调用生效", (r["stop"], r["v2"].get("codex调用")))
    finally:
        os.environ.pop("DSLAGENT_MODELS", None) if old is None else os.environ.__setitem__("DSLAGENT_MODELS", old)
    r, _, _ = go("budget", Fake(), max_calls=1)
    check(not r["fixed"] and "总模型调用已满" in r["stop"] and r["calls"] == 1, "显式给的 max_calls 也是上限", (r["stop"], r["calls"]))
    r, _, _ = go("budget2", Fake(), max_calls=6)
    check(not r["fixed"] and r["calls"] == 6 and r["v2"]["结论"] == "部分成功", "调用用完 → 部分成功（已建文件保留）", (r["stop"], r["calls"]))


def t_dry_cli():
    print("九、登记 / CLI")
    from tools.dslagent import __main__ as M, packs
    np_ = packs.pick("newproj")
    check({"校验分层清单", "参数核对"} <= set(np_.EXTRA_VERBS) and np_.TEMPLATE.is_file() and np_.SPLIT_TEMPLATE.is_file(), "动词登记；旧模板（newproj.zs / newproj_split.zs）仍在")
    seen = {}
    real = V.run_newproj
    V.run_newproj = lambda req, project, out, **kw: seen.update(kw) or {"fixed": True, "calls": 0, "cost": 0, "seconds": 0, "stop": "", "changed_files": []}
    try:
        rq = TMP / "cli_req.txt"
        rq.write_text("需求", encoding="utf-8")
        M.main(["newproj", "--layered", "--cost-cap", "2.5", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(seen.get("layered") is True and seen.get("cost_cap") == 2.5 and seen.get("split") is False, "CLI newproj --layered --cost-cap → run_newproj(layered=True, cost_cap=2.5)", seen)
        seen.clear()
        M.main(["newproj", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(not seen.get("layered"), "不带 --layered 仍旧路径", seen)
    finally:
        V.run_newproj = real
    import inspect
    sig = inspect.signature(V.run_newproj).parameters
    check(sig["split"].default is False and sig["layered"].default is False and sig["cost_cap"].default is None, "run_newproj 新参数缺省不改旧行为")
    pr = ROOT / "tools/dslagent/packs/newproj/prompts"
    check(all((pr / n).is_file() for n in ("sys_llayer.md", "sys_lfiles.md", "sys_lfplan.md", "sys_lent.md", "sys_lsql.md", "sys_lzs.md", "sys_lui.md")) and not (pr / "sys_lplan.md").exists(),
          "提示词：分层 / 文件 / 单文件规划各一份，旧的一次性全量清单提示词已删")
    fp = (pr / "sys_lfplan.md").read_text(encoding="utf-8")
    check(all(f"## 层：{n}" in fp for n in LAYERS4) and "新sql" in fp, "单文件规划提示词四层各有具体 JSON 示例")


def verb_mod(name, ws=TMP):
    spec = importlib.util.spec_from_file_location("_t_" + name, DEFS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.WORKSPACE = Path(ws)
    return getattr(m, name)


# ------------------------------------------------------------------ 二、参数核对

def t_params():
    print("二、参数核对（含 kg_rebuild2 的 pass_line / fall_line）")
    d = TMP / "pc"
    (d / "queries").mkdir(parents=True)
    (d / "routes").mkdir()
    (d / "queries/practice_mastery_flag.sql").write_text(
        "UPDATE mastery SET mastered = CASE WHEN 1 >= COALESCE(:pass_line, 80) THEN 1 WHEN 1 >= COALESCE(:fall_line, 60) THEN 1 ELSE 0 END WHERE owner = :current_user\n", encoding="utf-8")
    (d / "queries/practice_answer_log.sql").write_text("INSERT INTO a(x) VALUES (:answer) -- :注释里的 :ignored\n", encoding="utf-8")
    (d / "queries/q_by.sql").write_text("SELECT * FROM t WHERE k = :k AND '12:30' = '12:30'\n", encoding="utf-8")
    zs = ("接口 POST /practice/answer 动作 practice_answer 角色 student\n  用包 db http common\n  设 pass_line = 80\n  设 fall_line = 60\n"
          "  事务 app.db\n    设 a1 = 写库表 app.db practice_answer_log {request}\n    设 a5 = 写库表 app.db practice_mastery_flag {request}\n  结束\n  返回 {\"ok\":\"1\"}\n结束\n")
    f = verb_mod("参数核对", d)
    (d / "routes/practice.zs").write_text(zs, encoding="utf-8")
    r = f("routes/practice.zs", {"/practice/answer": ["answer"]})
    check(r["ok"] == "否" and "pass_line" in r["msg"] and "fall_line" in r["msg"] and "/practice/answer" in r["msg"] and "practice_mastery_flag" in r["msg"],
          "pass_line / fall_line 只 设 了变量却用 {request} 写库 → 抓到并点名接口、sql、参数", r)
    check("current_user" not in r["msg"].split("缺少参数")[1].split("（")[0], "current_user 是路由器注入的，不算缺", r["msg"])
    fix1 = zs.replace("  设 pass_line = 80\n  设 fall_line = 60\n", "  设 request.pass_line = 80\n  设 request.fall_line = 60\n")
    (d / "routes/practice.zs").write_text(fix1, encoding="utf-8")
    r = f("routes/practice.zs", {"/practice/answer": ["answer"]})
    check(r["ok"] == "是" and r["检查数"] == 2, "改成 设 request.pass_line = 80 → 通过", r)
    fix2 = zs.replace("  设 pass_line = 80\n  设 fall_line = 60\n", "  设 p.pass_line = 80\n  设 p.fall_line = 60\n  设 p.answer = {answer}\n  设 p.current_user = {current_user}\n").replace(
        "a5 = 写库表 app.db practice_mastery_flag {request}", "a5 = 写库表 app.db practice_mastery_flag {p}")
    (d / "routes/practice.zs").write_text(fix2, encoding="utf-8")
    check(f("routes/practice.zs", {"/practice/answer": ["answer"]})["ok"] == "是", "另设对象 {p} 带上 pass_line → 通过")
    named = "接口 POST /x 动作 x_a\n  用包 db http\n  设 r = 查一行 app.db q_by k={kk}\n  返回 {r}\n结束\n"
    (d / "routes/x.zs").write_text(named, encoding="utf-8")
    r = f("routes/x.zs", {"/x": ["a"]})
    check(r["ok"] == "否" and "kk" in r["msg"] and "没有来源" in r["msg"], "具名参数的值 {kk} 既不是入参也没 设 过 → 不过", r)
    (d / "routes/x.zs").write_text(named.replace("{kk}", "{a}"), encoding="utf-8")
    check(f("routes/x.zs", {"/x": ["a"]})["ok"] == "是", "值是入参 {a} → 通过（sql 里字符串 '12:30' 不算参数）")
    (d / "routes/x.zs").write_text(named.replace(" k={kk}", ""), encoding="utf-8")
    r = f("routes/x.zs", {"/x": ["a"]})
    check(r["ok"] == "否" and "缺少参数 :k" in r["msg"], "具名调用漏写 k= → 不过", r)
    (d / "routes/x.zs").write_text(named.replace("q_by", "q_nope"), encoding="utf-8")
    r = f("routes/x.zs", {"/x": ["a"]})
    check(r["ok"] == "否" and "不存在的 sql" in r["msg"], "引用不存在的 sql → 不过", r)
    (d / "routes/x.zs").write_text("接口 POST /x 动作 x_a\n  用包 db http\n  设 r = 查一行表 app.db q_by {request}\n  返回 {r}\n结束\n", encoding="utf-8")
    check(f("routes/x.zs", {"/x": ["k"]})["ok"] == "是" and f("routes/x.zs", {"/x": []})["ok"] == "否", "入参声明了 k 才算 {request} 里有 k；没声明严格判不过")
    check(f("routes/x.zs")["ok"] == "是", "完全没给接口声明时不判 {request}（宽松）")
    check(f("routes/nope.zs")["ok"] == "否" and f("../x")["ok"] == "否", "文件不存在 / 越界不抛")
    ex = "接口 POST /y 动作 y_a\n  用包 db http\n  设 r = 查一行 app.db q_by k=1\n  设 r.z = 1\n  设 w = 写库表 app.db q_by {r}\n结束\n"
    (d / "routes/x.zs").write_text(ex, encoding="utf-8")
    check(f("routes/x.zs", {"/y": []})["ok"] == "是", "查询结果行 {r}（键未知）不误判")
    (d / "routes/x.zs").write_text('接口 POST /y 动作 y_a\n  用包 db http\n  设 w = 写库表 app.db q_by {"k":"{a}"}\n结束\n', encoding="utf-8")
    check(f("routes/x.zs", {"/y": ["a"]})["ok"] == "是", "参数表是 JSON 字面量时按字面量里的键判")


def t_fix_a():
    print("六、修复 A：变量里存的是 JSON 文本时 {x.y} 取得到（kg_v2plan：写文件 {r1.结果}）")
    from tools.dsl import DSLEngine, to_text
    ws = TMP / "fixa"
    ws.mkdir()
    M = V.Model(TMP / "fixa_out", backend=lambda *a, **k: "x")
    e = V._engine_cls()(client=V.Client(M), workdir=ws, verbose=False, verbs_root=V.VERBS, scripts={})
    e.gate, e.project, e.tests = {}, ws, []
    e.vars["rs"] = [{"结果": {"files": [{"file": "out/a.txt", "content": "你好"}]}, "状态": "成功"}]
    e.run("用包 common text code\n设 r1 = 取字段 {rs} 0\n设 w1 = 写文件 {r1.结果}\n打印 {w1.ok}")
    check(e.output[-1] == "是" and (ws / "out/a.txt").read_text(encoding="utf-8") == "你好", "取字段 返回 JSON 文本，{r1.结果} 钻进去后 写文件 成功（原来 {r1.结果} 原样留着被当 JSON 解析失败）", e.output)
    e2 = DSLEngine(workdir=ws, verbose=False, verbs_root=ROOT / "verbs")
    e2.vars.update(d={"a": [1, 2], "b": {"c": "x"}}, t='{"a":[1,2],"b":{"c":"x"}}', s="普通文本 {不是json}", bad="{坏的")
    check(e2.expand("{d.a}") == "[1,2]" and e2.expand("{d.b}") == '{"c":"x"}', "字典 / 列表代入文本 = 紧凑 JSON（ensure_ascii=False），不是 Python repr")
    check(e2.expand("{t.b.c}") == "x" and e2.expand("{t.a.1}") == "2", "JSON 文本变量支持点号路径和下标")
    check(e2.expand("{s.x}") == "{s.x}" and e2.expand("{bad.x}") == "{bad.x}" and e2.expand("{t.nope}") == "{t.nope}", "不是 JSON 的文本 / 路径不存在 → 照旧原样保留（看得见拼错）")
    e2.vars["u"] = {"内容": "你好"}
    check(e2.expand("{u}") == '{"内容":"你好"}' and "\\u" not in e2.expand("{u}"), "中文不转义成 \\uXXXX")
    e2.run("设 n = {t.b.c 或 默认}\n设 m = {s.x 或 缺省}\n打印 {n} {m}")
    check(e2.output[-1] == "x 缺省", "「或 默认值」对 JSON 文本变量也生效", e2.output)


# ------------------------------------------------------------------ 七、修复 B：被杀的调用费用

FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, sys, time
sys.stdin.read()
def out(o): print(json.dumps(o, ensure_ascii=False), flush=True)
out({"type": "system", "subtype": "init"})
out({"type": "stream_event", "event": {"type": "message_start", "message": {"usage": {"input_tokens": 1000, "cache_creation_input_tokens": 2000, "cache_read_input_tokens": 10000, "output_tokens": 1}}}})
out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "部分输出" * 150}}})
time.sleep(30)
'''


def t_fix_b():
    print("七、修复 B：被杀（rc=-9）的 claude 调用按流里 usage 估费用，不再记 0")
    fake = TMP / "fake_claude.py"
    fake.write_text(FAKE_CLAUDE, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    os.environ["CBATCH_CLAUDE"] = str(fake)
    try:
        r = engines.call_claude("sys", "user", timeout=3, model="sonnet")
    finally:
        os.environ.pop("CBATCH_CLAUDE", None)
    # 输入 1000×3 + 缓存写(2000, 5m 估)×3.75 + 读 10000×0.3 = 3000+7500+3000 = 13500 → $0.0135；输出 600 字 / 1.5 = 400 token × 15 = 6000 → $0.006
    check(r["rc"] != 0 and r["cost"] > 0 and r.get("cost_est") is True, "被杀的调用 cost > 0 且标 cost_est", {k: r[k] for k in ("rc", "cost", "usage")})
    check(abs(r["cost"] - 0.0195) < 1e-6, "按 message_start 的 usage ＋ 已流出字数估：$0.0195", r["cost"])
    check(r["usage"]["input"] == 1000 and r["usage"]["cache_read"] == 10000, "usage 也不再是 None", r["usage"])
    c, u = engines.estimate_cost("claude-opus-5", {"input_tokens": 1000000}, 1000000)
    check(abs(c - 30.0) < 1e-6, "opus 价格：输入 $5/M + 输出 $25/M", c)
    c, _ = engines.estimate_cost("sonnet", None, None, 0)
    check(c == 0, "什么都没收到记 0")
    # 经 Model 进 calls.json / result 的花费
    out = TMP / "fixb_out"
    M = V.Model(out, backend=lambda s, u, tag, timeout, **kw: {"text": "", "rc": -9, "cost": 0.0123, "cost_est": True, "usage": None})
    try:
        M._text(M._call("s", "u", "dsl01"))
    except RuntimeError:
        pass
    check(abs(M.cost - 0.0123) < 1e-9 and M.log[-1].get("cost_est") == 1 and M.log[-1]["failed"], "Model 记账带上估算值并标 cost_est；失败照旧抛", M.log)
    # 正常调用的 total_cost_usd 不受影响
    normal = r"""#!/usr/bin/env python3
import json, sys
sys.stdin.read()
print(json.dumps({"type": "stream_event", "event": {"type": "message_start", "message": {"usage": {"input_tokens": 5}}}}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "result": "好", "total_cost_usd": 0.5, "usage": {"input_tokens": 5, "output_tokens": 2}}), flush=True)
"""
    f2 = TMP / "fake_claude2.py"
    f2.write_text(normal, encoding="utf-8")
    f2.chmod(f2.stat().st_mode | stat.S_IEXEC)
    os.environ["CBATCH_CLAUDE"] = str(f2)
    try:
        r = engines.call_claude("sys", "user", timeout=10, model="sonnet")
    finally:
        os.environ.pop("CBATCH_CLAUDE", None)
    check(r["cost"] == 0.5 and not r.get("cost_est"), "正常结束仍用 CLI 报的 total_cost_usd", r)




def main():
    try:
        t_layers()
        t_files()
        t_plans()
        t_params()
        t_flow()
        t_layer_retry()
        t_batch()
        t_perfile()
        t_budget()
        t_dry_cli()
        t_fix_a()
        t_fix_b()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
