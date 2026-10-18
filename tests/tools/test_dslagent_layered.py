# -*- coding: utf-8 -*-
"""newproj --layered（分层逐实体生成）＋引擎修复 A（JSON 文本里的 {x.y} 能取到）＋ B（被杀的 claude 调用费用不再记 0）。不调真模型。

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
import _layer as L      # noqa: E402
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


def plan(**kw):
    p = {"模板": "full", "角色": [], "规则": [{"号": "R1", "文": RULE1}],
         "实体": [{"名": "attempt", "说明": "作答", "关联": ["question"]}, {"名": "question", "说明": "题目", "关联": []}],
         "查询": [{"实体": "attempt", "sql": [{"名": "attempt_log", "参数": ["question_id", "given"], "说明": "写作答"}], "规则": ["R1"]}],
         "接口": [{"实体": "attempt", "文件": "routes/attempt.zs", "规则": ["R1"],
                 "接口": [{"路径": "/attempt/answer", "动作": "attempt_answer", "入参": ["question_id", "given"], "用sql": ["attempt_log"], "说明": "交答案"}]}],
         "界面": [{"文件": "ui/quiz.ui", "实体": "attempt", "用接口": ["/attempt/answer", "/question/list"]}]}
    p.update(kw)
    return p


def verr(p, req=""):
    r = L.validate(json.dumps(p, ensure_ascii=False), req)
    return r["ok"], "；".join(r["errors"]), r


# ------------------------------------------------------------------ 一、校验分层清单

def t_validate():
    print("一、校验分层清单")
    ok, e, r = verr(plan())
    check(ok and r["实体"][0]["名"] == "question" and r["实体"][1]["名"] == "attempt", "合法清单；实体按关联拓扑序（question 在 attempt 前）", e)
    check(r["数量"] == 2 + 1 + 1 + 1 and r["调用上限"] == 2 + 2 * (2 + 1 + 1) + 6, "文件数 5；调用上限 = 2 + 实体/查询/界面各 2 + 有规则的接口 6", (r["数量"], r["调用上限"]))

    def bad(p, want, msg, req=""):
        ok, e, _ = verr(p, req)
        check(not ok and want in e, msg, e)

    bad(plan(实体=[{"名": "a", "关联": ["b"]}, {"名": "b", "关联": ["a"]}], 查询=[], 接口=[], 界面=[], 规则=[]), "有环", "实体关联成环 → 不过")
    bad(plan(实体=[{"名": "a", "关联": ["zz"]}], 查询=[], 接口=[], 界面=[], 规则=[]), "关联「zz」不在实体列表", "关联不存在的实体")
    bad(plan(实体=[{"名": "Bad Name"}]), "要是英文小写 snake", "实体名不合规")
    bad(plan(实体=[{"名": "question"}, {"名": "question"}]), "实体「question」重复", "实体重名")
    q = plan()
    q["查询"][0]["sql"][0]["名"] = "zz_log"
    bad(q, "要以实体名「attempt_」开头", "sql 名没有实体前缀")
    q = plan()
    q["查询"][0]["sql"].append({"名": "attempt_log", "参数": []})
    bad(q, "sql 名「attempt_log」重复", "sql 名重复")
    q = plan()
    q["查询"][0]["sql"][0]["名"] = "attempt_list"
    bad(q, "与 gen 自动生成的重名", "sql 名与 gen 自带五条重名")
    q = plan()
    q["接口"][0]["文件"] = "routes/other.zs"
    bad(q, "命名不合规", "接口文件名不是 routes/<实体>.zs|_*.zs")
    q = plan()
    q["接口"][0]["文件"] = "routes/attempt_extra.zs"
    ok, e, _ = verr(q)
    check(ok, "routes/<实体>_<后缀>.zs 放行", e)
    q = plan()
    q["接口"].append(dict(q["接口"][0]))
    bad(q, "接口文件「routes/attempt.zs」重复", "路径重复（文件）")
    q = plan()
    q["接口"][0]["接口"].append({"路径": "/attempt/answer", "动作": "x2", "入参": [], "用sql": []})
    bad(q, "接口路径「/attempt/answer」重复", "接口路径重复")
    q = plan()
    q["接口"][0]["接口"][0]["路径"] = "/attempt/list"
    bad(q, "与 gen 自动生成的 CRUD 路径冲突", "接口路径与 gen CRUD 冲突")
    q = plan()
    q["接口"][0]["接口"][0]["用sql"] = ["nope_sql"]
    bad(q, "用sql「nope_sql」不在「查询」层里", "用sql 不在查询层")
    q = plan()
    q["接口"][0]["接口"][0]["用sql"] = ["attempt_insert", "question_one"]
    ok, e, _ = verr(q)
    check(ok, "用sql 可以用 gen 自带的 <实体>_insert / _one", e)
    q = plan()
    q["界面"][0]["用接口"] = ["/nope/x"]
    bad(q, "用接口「/nope/x」不在「接口」层里", "用接口不在接口层")
    q = plan()
    q["界面"][0]["文件"] = "views/x.ui"
    bad(q, "界面文件「views/x.ui」命名不合规", "ui 文件名不合规")
    q = plan()
    q["接口"][0]["规则"] = []
    q["查询"][0]["规则"] = []
    bad(q, "规则 R1", "有规则没分配到任何查询或接口项")
    q = plan()
    q["查询"][0]["规则"] = ["R9"]
    bad(q, "规则号「R9」没在顶层", "分配了不存在的规则号")
    q = plan()
    del q["接口"][0]["接口"][0]["入参"]
    bad(q, "要有「入参」", "接口没写入参")
    bad(plan(角色=["teacher"]), "模板必须是 private", "有角色但模板不是 private")
    bad(plan(), "必须给「角色」", "需求提到登录但没给角色", req="要登录，老师才能导入题目")
    ok, e, _ = verr(plan(模板="private", 角色=["teacher", "student"]), "要登录")
    check(ok, "private + 角色放行", e)
    bad(plan(实体=[{"名": "user"}], 模板="private", 角色=["t"], 查询=[], 接口=[], 界面=[], 规则=[]), "user 实体由 gen 生成", "private 清单里不许列 user")
    bad(plan(实体=[]), "「实体」不能为空", "没有实体")
    r = L.validate("```json\n" + json.dumps(plan(), ensure_ascii=False) + "\n```")
    check(r["ok"], "带围栏的 JSON 能解析")
    check(not L.validate("不是 JSON")["ok"], "不是 JSON → 不过")
    v = verb_mod("校验分层清单")
    r = v(json.dumps(plan(), ensure_ascii=False), REQ)
    check(r["ok"] == "是" and r["errors"] == "" and r["调用上限"], "动词外壳：ok=是，errors 为空", r)
    r = v(json.dumps(plan(实体=[]), ensure_ascii=False))
    check(r["ok"] == "否" and "实体" in r["errors"], "动词外壳：errors 用「；」连接成文本", r)


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


# ------------------------------------------------------------------ 三、分层流程（假模型）

class Fake:
    """按提示词里的角色标记认出是哪一层、哪个文件；bad={(文件, 层): [回复…]} 覆盖默认回复（用完回最后一个）。cost：每次调用记的花费。"""

    def __init__(self, plans=None, bad=None, cost=0.0, extra_ents=None):
        self.plans = list(plans or [plan()])
        self.bad, self.cost, self.prompts, self.used, self.calls = bad or {}, cost, [], {}, []
        self.ents = dict(extra_ents or {"question": ENT_Q, "attempt": ENT_A})

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

    def reply(self, user):
        if "项目分层规划助手" in user:
            return self.pick(("清单", "plan"), json.dumps(self.plans.pop(0) if len(self.plans) > 1 else self.plans[0], ensure_ascii=False))
        if "应用建模助手" in user:
            n = re.search(r'本实体：\{"名": "(\w+)"', user).group(1)
            return self.pick((f"entities/{n}.entity", "ent"), f"=== entities/{n}.entity ===\n{self.ents[n]}")
        if "SQLite 语句助手" in user:
            n = re.search(r"本实体：(\w+)", user).group(1)
            return self.pick((f"queries/{n}_*.sql", "sql"), f"=== queries/{n}_log.sql ===\n{SQL_A}")
        if ".zs 接口助手" in user:
            rel = re.search(r"本文件：(\S+)", user).group(1)
            return self.pick((rel, "zs"), f"=== {rel} ===\n{ZS_A}")
        if ".ui 界面助手" in user:
            rel = re.search(r"本文件：(\S+)", user).group(1)
            return self.pick((rel, "ui"), f"=== {rel} ===\n{UI_A}")
        if "需求核对员" in user:
            rules = json.loads(re.search(r"规则：(\[.*?\]) 本功能sql", user, re.S).group(1))
            ok = json.dumps([{"序号": i, "规则": r, "实现": "是", "依据": "attempt_answer"} for i, r in enumerate(rules, 1)], ensure_ascii=False)
            return self.pick(("核对", "chk"), ok)
        return "?"


def go(name, fake, req=REQ, **kw):
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    return V.run_newproj(req, d / "proj", d / "out", model=fake, layered=True, **kw), d / "proj", d / "out"


def files(r):
    return {f["文件"]: f for f in r["v2"].get("文件", [])}


def t_flow():
    print("三、分层流程：成功 / 多个 .entity / 记录")
    fk = Fake(cost=0.01)
    r, p, out = go("ok", fk)
    fs = files(r)
    check(r["fixed"] and r["v2"]["结论"] == "成功" and r["v2"]["layered"] is True, "全过 = 成功", (r["stop"], r["v2"].get("结论")))
    check(r["calls"] == 1 + 2 + 1 + 2 + 1 + 1 - 1 + 0 or r["calls"] == 8, "调用数：清单 1 + 实体 2 + 查询 1 + 接口 1 + 核对 1 + 界面 1 = 7", r["calls"])
    check((p / "entities/question.entity").is_file() and (p / "entities/attempt.entity").is_file() and not (p / "entities/app.entity").exists(),
          "多个 .entity：一个实体一个文件（attempt 排在 question 前也能建库）", sorted(str(x.relative_to(p)) for x in (p / "entities").glob("*")))
    check((p / "app.db").is_file() and (p / "queries/attempt_log.sql").is_file() and (p / "ui/quiz.ui").is_file(), "建库、sql、ui 落盘")
    zs = (p / "routes/attempt.zs").read_text(encoding="utf-8")
    check("/attempt/list" in zs and "/attempt/answer" in zs, "routes/attempt.zs 是 gen 的 CRUD 文件，接口追加在后面不覆盖", zs[:200])
    check(set(fs) == {"entities/question.entity", "entities/attempt.entity", "queries/attempt_*.sql", "routes/attempt.zs", "ui/quiz.ui"}, "v2.文件 逐文件记录", sorted(fs))
    a = fs["routes/attempt.zs"]
    check(a["层"] == "接口" and a["实体"] == "attempt" and a["结果"] == "通过" and a["尝试"] == 1 and a["重写"] == 0 and a["未实现规则"] == [] and a["核对"] == 1,
          "接口文件记层 / 实体 / 结果 / 尝试 / 重写 / 核对", a)
    check(r["v2"]["预算"]["max_calls"] == L.validate(json.dumps(plan(), ensure_ascii=False))["调用上限"], "预算 = 清单通过后按文件数算的上限", r["v2"]["预算"])
    rows = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check(len(rows) == r["calls"] and all(c["cost"] == 0.01 for c in rows) and abs(r["cost"] - 0.01 * r["calls"]) < 1e-9, "calls.json 逐次记花费", (r["cost"], rows[:1]))
    check({c.get("file") for c in rows} >= {"entities/question.entity", "routes/attempt.zs", "ui/quiz.ui"}, "calls.json 每次调用标了文件", [c.get("file") for c in rows])
    # 输入内容
    ent_prompt = next(x for x in fk.prompts if "应用建模助手" in x and '本实体：{"名": "attempt"' in x)
    check("实体 question 题目" in ent_prompt.split("已写好的被关联实体全文")[1], "实体层：关联实体 question 的全文进了 attempt 的输入", ent_prompt[-300:])
    q_first = next(x for x in fk.prompts if "应用建模助手" in x)
    check('本实体：{"名": "question"' in q_first, "拓扑序：先写 question")
    zs_prompt = next(x for x in fk.prompts if ".zs 接口助手" in x)
    check("INSERT INTO attempt" in zs_prompt.split("用sql 涉及的 sql 全文")[1] and RULE1 in zs_prompt and "入参" in zs_prompt, "接口层输入：用sql 的 sql 全文（不是摘要）＋分配的规则＋接口项", zs_prompt[-500:])
    ui_prompt = next(x for x in fk.prompts if ".ui 界面助手" in x)
    check("attempt_answer" in ui_prompt and "question_id" in ui_prompt and "/question/list" in ui_prompt, "界面层输入：用接口对应的动作 / 入参（含 gen 的 CRUD 路径）", ui_prompt[-500:])
    sql_prompt = next(x for x in fk.prompts if "SQLite 语句助手" in x)
    check("实体 question" in sql_prompt and "实体 attempt" in sql_prompt and RULE1 in sql_prompt, "查询层输入：该实体及关联实体全文＋分配的规则")
    rj = json.loads((out / "result.json").read_text(encoding="utf-8"))
    check(rj["v2"]["文件"] and rj["v2"]["结论"] == "成功", "写进 result.json")

    r, p, _ = go("empty_proj_calls", Fake(plans=[plan(规则=[], 查询=[{"实体": "attempt", "sql": [{"名": "attempt_log", "参数": ["question_id", "given"]}], "规则": []}],
                                                  接口=[{"实体": "attempt", "文件": "routes/attempt.zs", "规则": [],
                                                       "接口": [{"路径": "/attempt/answer", "动作": "attempt_answer", "入参": ["question_id", "given"], "用sql": ["attempt_log"]}]}])]))
    check(r["fixed"] and r["calls"] == 6, "接口没有规则 → 不调核对：6 次", (r["stop"], r["calls"]))


def t_fail():
    print("四、清单重写 / 文件重写 / 失败撤回 / 依赖跳过 / 超长 / 熔断")
    bad_plan = plan()
    bad_plan["查询"][0]["sql"][0]["名"] = "zz_log"
    fk = Fake(plans=[bad_plan, plan()])
    r, _, _ = go("plan_rw", fk)
    second = [x for x in fk.prompts if "项目分层规划助手" in x][1]
    check(r["fixed"] and "要以实体名「attempt_」开头" in second.split("上次的报错：")[1], "清单不过 → 带报错重写 1 次后通过", (r["stop"], second[-200:]))
    r, _, _ = go("plan_bad", Fake(plans=[bad_plan]))
    check(not r["fixed"] and "分层清单两次都没过" in r["stop"] and r["v2"]["结论"] == "失败" and r["calls"] == 2, "清单两次不过 → 失败（2 次调用）", (r["stop"], r["calls"]))

    # 实体重写 1 次
    fk = Fake(bad={("entities/question.entity", "ent"): ["=== entities/question.entity ===\n实体 question 题目\n  字段 title 乱写 必填 题干\n结束\n", f"=== entities/question.entity ===\n{ENT_Q}"]})
    r, p, _ = go("ent_rw", fk)
    f = files(r)["entities/question.entity"]
    check(r["fixed"] and f["尝试"] == 2 and f["重写"] == 1 and "乱写" in [x for x in fk.prompts if "应用建模助手" in x][1], "实体校验不过 → 带报错重写 1 次", f)
    # 一个文件定义了两个实体
    two = f"=== entities/question.entity ===\n{ENT_Q}\n{ENT_A}"
    fk = Fake(bad={("entities/question.entity", "ent"): [two, f"=== entities/question.entity ===\n{ENT_Q}"]})
    r, _, _ = go("ent_two", fk)
    check(r["fixed"] and "只能定义实体 question" in [x for x in fk.prompts if "应用建模助手" in x][1], "一个实体文件定义了别的实体 → 不过")

    # 实体 question 两次都坏 → attempt 跳过 → 查询 / 接口 / 界面 跳过；没有任何实体 → 失败
    badq = "=== entities/question.entity ===\n不是实体\n"
    fk = Fake(bad={("entities/question.entity", "ent"): [badq]})
    r, p, _ = go("ent_fail", fk)
    fs = files(r)
    check(not r["fixed"] and fs["entities/question.entity"]["结果"] == "失败" and fs["entities/attempt.entity"]["结果"] == "跳过"
          and "依赖的实体没写成" in fs["entities/attempt.entity"]["失败原因"] and "没有一个实体写成" in r["stop"], "唯一可写的实体链全失败 → 失败并说明", (r["stop"], fs))

    # 两个独立实体：一个坏了，另一个及其上层照常做，坏的那条链跳过
    pl2 = plan(实体=[{"名": "question", "关联": []}, {"名": "attempt", "关联": []}])
    pl2["接口"][0]["接口"][0]["用sql"] = ["attempt_log"]
    pl2["界面"][0]["用接口"] = ["/attempt/answer"]
    pl2["查询"][0]["sql"][0]["参数"] = ["given"]
    pl2["接口"][0]["接口"][0]["入参"] = ["given"]
    badent = "=== entities/question.entity ===\n不是实体\n"
    fk = Fake(plans=[pl2], bad={("entities/question.entity", "ent"): [badent],
                                                ("queries/attempt_*.sql", "sql"): ["=== queries/attempt_log.sql ===\nINSERT INTO attempt(given) VALUES (:given)\n"]},
              extra_ents={"question": ENT_Q, "attempt": "实体 attempt 作答\n  字段 given 文本 必填 作答\n  字段 correct 整数 必填 默认 0 对错\n结束\n"})
    r, p, _ = go("ent_partial", fk)
    fs = files(r)
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and "部分成功" in r["stop"] and "entities/question.entity" in r["stop"], "一个实体失败 → 部分成功并列出", r["stop"])
    check(fs["entities/attempt.entity"]["结果"] == "通过" and fs["routes/attempt.zs"]["结果"] == "通过" and fs["ui/quiz.ui"]["结果"] == "通过" and not (p / "entities/question.entity").exists(),
          "独立的实体及其上层继续做完；失败文件已撤回", {k: v["结果"] for k, v in fs.items()})

    # 依赖跳过：attempt 的 sql 两次不过 → 接口 / 界面 跳过
    badsql = "=== queries/attempt_log.sql ===\nSELECT nope FROM attempt WHERE a = :question_id AND b = :given\n"
    fk = Fake(bad={("queries/attempt_*.sql", "sql"): [badsql]})
    r, p, _ = go("sql_fail", fk)
    fs = files(r)
    check(fs["queries/attempt_*.sql"]["结果"] == "失败" and fs["routes/attempt.zs"]["结果"] == "跳过" and fs["ui/quiz.ui"]["结果"] == "跳过"
          and "queries/attempt_*.sql" in fs["routes/attempt.zs"]["失败原因"] and "routes/attempt.zs" in fs["ui/quiz.ui"]["失败原因"], "查询失败 → 依赖它的接口、界面跳过并记原因", {k: (v["结果"], v["失败原因"][:60]) for k, v in fs.items()})
    check(r["calls"] == 1 + 2 + 2 and not (p / "queries/attempt_log.sql").exists() and r["v2"]["结论"] == "部分成功" and "因依赖失败跳过" in r["stop"], "跳过的文件不调模型；失败的 sql 没落盘", (r["calls"], r["stop"]))

    # sql 名 / 参数与清单不符
    fk = Fake(bad={("queries/attempt_*.sql", "sql"): [f"=== queries/attempt_log.sql ===\nINSERT INTO attempt(question_id, given) VALUES (:question_id, :given, :extra)\n",
                                                      f"=== queries/attempt_log.sql ===\n{SQL_A}"]})
    r, _, _ = go("sql_params", fk)
    second = [x for x in fk.prompts if "SQLite 语句助手" in x][1]
    check(r["fixed"] and "参数与清单不符" in second and "extra" in second, "sql 参数与清单不符 → 检查不过，带报错重写", second[-300:])
    fk = Fake(bad={("queries/attempt_*.sql", "sql"): [f"=== queries/attempt_log.sql ===\n{SQL_A}=== queries/attempt_more.sql ===\nSELECT 1\n", f"=== queries/attempt_log.sql ===\n{SQL_A}"]})
    r, _, _ = go("sql_extra", fk)
    check(r["fixed"] and "多写了清单里没有的 sql" in [x for x in fk.prompts if "SQLite 语句助手" in x][1], "多写清单没有的 sql → 不过")

    # 接口：参数核对不过 → 带点名的报错重写；写盘前的 CRUD 文件被还原
    zs_bad = ("=== routes/attempt.zs ===\n接口 POST /attempt/answer 动作 attempt_answer\n  用包 db http common\n  设 given = 1\n"
              "  事务 app.db\n    设 n = 写库表 app.db attempt_log {request}\n  结束\n  返回 {\"ok\":\"1\"}\n结束\n")
    pl3 = plan()
    pl3["接口"][0]["接口"][0]["入参"] = ["question_id"]        # given 没有来源
    fk = Fake(plans=[pl3], bad={("routes/attempt.zs", "zs"): [zs_bad, f"=== routes/attempt.zs ===\n{ZS_A.replace('{request}', '{p}').replace('  事务', '  设 p.question_id = {question_id}' + chr(10) + '  设 p.given = 1' + chr(10) + '  事务')}"]})
    r, p, _ = go("zs_params", fk)
    second = [x for x in fk.prompts if ".zs 接口助手" in x][1]
    a = files(r)["routes/attempt.zs"]
    check(r["fixed"] and a["尝试"] == 2 and "参数核对不过" in second and "given" in second and "/attempt/answer" in second, "接口缺参数来源 → 参数核对不过，报错点名接口 / 参数后重写", second[-500:])
    check((p / "routes/attempt.zs").read_text(encoding="utf-8").count("接口 POST /attempt/list") == 1, "重写后 CRUD 部分仍在、没重复追加")
    fk = Fake(plans=[pl3], bad={("routes/attempt.zs", "zs"): [zs_bad]})
    r, p, _ = go("zs_params2", fk)
    check(files(r)["routes/attempt.zs"]["结果"] == "失败" and "/attempt/answer" not in (p / "routes/attempt.zs").read_text(encoding="utf-8") and "/attempt/list" in (p / "routes/attempt.zs").read_text(encoding="utf-8"),
          "两次都缺来源 → 该文件失败，撤回成原来的 gen CRUD 文件", files(r)["routes/attempt.zs"])

    # 规则核对：重写 1 次仍未实现 → 记未实现，部分成功
    no = json.dumps([{"序号": 1, "规则": RULE1, "实现": "否", "依据": "没判题"}], ensure_ascii=False)
    fk = Fake(bad={("核对", "chk"): [no]})
    r, p, _ = go("rule_no", fk)
    a = files(r)["routes/attempt.zs"]
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and a["结果"] == "通过" and a["未实现规则"] == ["R1：" + RULE1] and a["核对"] == 2 and a["尝试"] == 2,
          "规则核对：重写 1 次仍未实现 → 记未实现规则，结论部分成功（文件保留）", a)
    check("以下业务规则没有实现" in [x for x in fk.prompts if ".zs 接口助手" in x][1] and "没判题" in [x for x in fk.prompts if ".zs 接口助手" in x][1], "未实现规则带进重写提示词")
    ok = json.dumps([{"序号": 1, "规则": RULE1, "实现": "是", "依据": "x"}], ensure_ascii=False)
    fk = Fake(bad={("核对", "chk"): [no, ok]})
    r, _, _ = go("rule_rw", fk)
    check(r["fixed"] and files(r)["routes/attempt.zs"]["核对"] == 2, "规则核对：重写后通过 → 成功")

    # 超长 / 被杀 = 该文件失败，不终止，不重试
    killed = {"text": "", "rc": -9, "cost": 0.3}
    fk = Fake(bad={("routes/attempt.zs", "zs"): [killed]})
    r, p, _ = go("killed", fk)
    a = files(r)["routes/attempt.zs"]
    zs_calls = sum(1 for x in fk.prompts if ".zs 接口助手" in x)
    check(a["结果"] == "失败" and "模型没有完成输出" in a["失败原因"] and zs_calls == 1, "被杀（rc=-9）→ 该接口文件失败，不重试", (a, zs_calls))
    check(files(r)["ui/quiz.ui"]["结果"] == "跳过" and files(r)["entities/attempt.entity"]["结果"] == "通过" and r["v2"]["结论"] == "部分成功" and abs(r["cost"] - 0.3) < 1e-9,
          "运行没终止：其余文件照做，依赖它的界面跳过；被杀调用的花费计入", (r["stop"], r["cost"]))
    long = {"text": "x" * 10, "rc": 0, "reason": "输出超长", "cost": 0.2}
    fk = Fake(bad={("ui/quiz.ui", "ui"): [long]})
    r, _, _ = go("overlong", fk)
    check(files(r)["ui/quiz.ui"]["结果"] == "失败" and "输出超长" in files(r)["ui/quiz.ui"]["失败原因"] and sum(1 for x in fk.prompts if ".ui 界面助手" in x) == 1, "输出超长 → 该界面文件失败，不重试")

    # 花费熔断
    fk = Fake(cost=1.0)
    r, p, _ = go("cap", fk, cost_cap=3.5)
    fs = files(r)
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and r["stop"].startswith("部分成功：花费达上限") and r["calls"] == 4, "花费熔断：累计 ≥ 上限就不再调模型（清单 + 2 实体 + 1 次，共 4 次）", (r["stop"], r["calls"], r["cost"]))
    check((p / "entities/question.entity").is_file() and (p / "entities/attempt.entity").is_file() and fs["routes/attempt.zs"]["结果"] == "未做" and fs["ui/quiz.ui"]["结果"] == "未做",
          "熔断后已写文件保留，后面的文件记「未做」", {k: v["结果"] for k, v in fs.items()})
    os.environ["NEWPROJ_COST_CAP"] = "2.5"
    try:
        r, _, _ = go("cap_env", Fake(cost=1.0))
        check(r["stop"].startswith("部分成功：花费达上限") and r["calls"] == 3, "环境变量 NEWPROJ_COST_CAP 同样生效", (r["stop"], r["calls"]))
    finally:
        os.environ.pop("NEWPROJ_COST_CAP", None)
    r, _, _ = go("nocap", Fake(cost=1.0))
    check(r["fixed"] and r["cost"] >= 7, "不设上限 = 不限", (r["stop"], r["cost"]))
    # codex 只记调用数
    old = os.environ.get("DSLAGENT_MODELS")
    os.environ["DSLAGENT_MODELS"] = json.dumps({"sub": "codex:gpt-6-luna:medium"})
    try:
        r, _, _ = go("codex", Fake(cost=0.0), cost_cap=0.01)
        check(r["fixed"] and r["v2"]["codex调用"] == r["calls"] and r["cost"] == 0, "codex 调用花费记 0、只记调用数；熔断按 Claude 侧花费算所以不触发", (r["stop"], r["v2"].get("codex调用")))
    finally:
        os.environ.pop("DSLAGENT_MODELS", None) if old is None else os.environ.__setitem__("DSLAGENT_MODELS", old)
    # 总调用上限
    r, _, _ = go("budget", Fake(plans=[plan()]), max_calls=1)
    check(not r["fixed"] and "总模型调用已满" in r["stop"] and r["calls"] == 1, "显式给的 max_calls 也是上限：用完 → 停下并说明", (r["stop"], r["calls"]))


def t_dry_cli():
    print("五、走通 / 登记 / CLI")
    r, p, _ = go("dry", Fake())
    check(r["fixed"] and all(f["结果"] == "通过" for f in r["v2"]["文件"]), "假模型空跑：五层全部走通")
    from tools.dslagent import __main__ as M, packs
    np_ = packs.pick("newproj")
    check({"校验分层清单", "参数核对"} <= set(np_.EXTRA_VERBS) and np_.TEMPLATE.is_file() and np_.SPLIT_TEMPLATE.is_file(), "新动词登记；旧模板（newproj.zs / newproj_split.zs）仍在")
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
    # 旧 split / 旧模板入口不受影响（签名）
    import inspect
    sig = inspect.signature(V.run_newproj).parameters
    check(sig["split"].default is False and sig["layered"].default is False and sig["cost_cap"].default is None, "run_newproj 新参数缺省不改旧行为")
    old = os.environ.get("DSLAGENT_MODELS")
    os.environ["DSLAGENT_MODELS"] = json.dumps({"sub": "codex:gpt-6-luna:medium"})
    try:
        r, out = go("routes", Fake())[0], TMP / "routes/out"
        rows = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        check(all(c.get("engine") == "codex" and c.get("effort") == "medium" for c in rows), "DSLAGENT_MODELS.sub 对 layered 的全部调用生效", rows[:1])
    finally:
        os.environ.pop("DSLAGENT_MODELS", None) if old is None else os.environ.__setitem__("DSLAGENT_MODELS", old)


# ------------------------------------------------------------------ 六、修复 A：JSON 文本里的 {x.y}

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
        t_validate()
        t_params()
        t_flow()
        t_fail()
        t_dry_cli()
        t_fix_a()
        t_fix_b()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
