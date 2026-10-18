# -*- coding: utf-8 -*-
"""newproj --modular（顶层规划 → 层次×模块 → 按层逐层构建，modbuild.py）。不调真模型。

    .venv/bin/python tests/tools/test_dslagent_modbuild.py
"""
import copy
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="dslagent_mb_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ.pop("NEWPROJ_FORCE_SUBPROCESS", None)
os.environ.pop("NEWPROJ_COST_CAP", None)

from tools.dslagent import modbuild as MB, v2 as V      # noqa: E402

PASS = FAIL = 0
REQ = "做一个答题：有题目，作答要记录；交答案时按库里记的题判对错并写作答记录；另有进度模块，看进度时按得分算掌握。"
ENT_Q = "实体 question 题目\n  字段 title 文本 必填 题干\n  字段 answer 文本 必填 答案\n结束\n"
ENT_A = "实体 attempt 作答\n  字段 question_id 整数 必填 索引 关联 question 题目\n  字段 given 文本 必填 作答\n  字段 correct 整数 必填 默认 0 对错\n结束\n"
ENT_M = "实体 mastery 掌握\n  字段 question_id 整数 必填 索引 关联 question 题目\n  字段 score 整数 必填 默认 0 得分\n结束\n"
SQL_A = "INSERT INTO attempt(question_id, given, correct) SELECT :question_id, :given, CASE WHEN q.answer = :given THEN 1 ELSE 0 END FROM question q WHERE q.id = :question_id\n"
ZS_FLOW = ("# 判一道题并写作答记录。谁调：routes/quiz.zs、routes/progress.zs。入参 question_id given；出参 ok n\n用包 db\n"
           "设 args.question_id = {question_id}\n设 args.given = {given}\n设 n = 写库表 app.db quiz_log {args}\n返回 {\"ok\":\"1\",\"n\":\"{n}\"}\n")
ZS_QUIZ = ("接口 POST /quiz/answer 动作 quiz_answer\n  用包 db http common\n"
           "  设 result = 执行 scripts/quiz_judge.zs question_id={question_id} given={given}\n  返回 {\"ok\":\"{result.ok}\"}\n结束\n")
ZS_PROG = ("接口 POST /progress/recheck 动作 progress_recheck\n  用包 db http common\n"
           "  设 result = 执行 scripts/quiz_judge.zs question_id={question_id} given={given}\n  返回 {\"ok\":\"{result.ok}\"}\n结束\n")
UI_Q = "界面 表单 答题页\n  分组 区 竖排\n    字段 given 作答\n    动作 quiz_answer 远程 提交 交答案\n  结束\n结束\n"
UI_P = "界面 表单 进度页\n  分组 区 竖排\n    字段 given 作答\n    动作 progress_recheck 远程 提交 重判\n  结束\n结束\n"
R1, R2 = "交答案时按库里记的题判对错，不信前端传的答案", "看进度时按得分算掌握"


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def dump(o):
    return json.dumps(o, ensure_ascii=False)


def top_obj():
    return {"目标": "答题并看掌握进度", "使用者": {"角色": [], "人数": "多人"},
            "主流程": [{"名": "学生做题", "角色": "", "步骤": ["做题", "交答案", "看进度"], "经过模块": ["quiz", "progress"]}],
            "模块": [{"名": "quiz", "说明": "题库与判题", "依赖": []}, {"名": "progress", "说明": "掌握进度", "依赖": ["quiz"]}],
            "共用流程": [{"流程名": "quiz_judge", "归属模块": "quiz", "被用于": ["progress"]}],
            "横切": {"账号与权限": "无账号", "调模型": [{"处": "讲解", "包": "common"}], "后台任务": [], "内容数据导入": "无", "全局约束": ["老库只加表加列"]},
            "构建顺序": ["quiz", "progress"]}


def split_obj():
    return {"模板": "full", "角色": [], "层": {"数据": "实体", "查询": "sql", "流程": "共用流程", "接口": "接口", "界面": "页面"}, "全局约束": ["老库只加表加列"],
            "模块": [
                {"名": "quiz", "规则": [R1], "数据": ["question", "attempt"],
                 "流程": [{"名": "quiz_judge", "作用": "判题写记录", "用于": ["quiz", "progress"], "调流程": []}],
                 "接口": [{"文件": "quiz", "作用": "交答案"}], "界面": [{"名": "quiz_page", "作用": "答题页"}],
                 "能力": ["db", "http", "common"], "缺口": [{"事": "语音朗读", "办法": "待补", "用动词": []}]},
                {"名": "progress", "规则": [R2], "数据": ["mastery"], "流程": [],
                 "接口": [{"文件": "progress", "作用": "重判"}], "界面": [{"名": "progress_page", "作用": "进度页"}],
                 "能力": ["db", "http"], "缺口": []}]}


CAPS = MB.capabilities()
PACKS = set(CAPS)


def vtop(mut=None, **kw):
    o = top_obj()
    if mut:
        mut(o)
    return MB.validate_top(dump(o), PACKS, kw.get("task", ""))


def vsplit(mut=None, top=None, **kw):
    o = split_obj()
    if mut:
        mut(o)
    t = top or MB.validate_top(dump(top_obj()), PACKS)["top"]
    return MB.validate_split(dump(o), t, CAPS, kw.get("task", ""))


def has(r, want):
    return (not r["ok"]) and any(want in e for e in r["errors"])


# ------------------------------------------------------------------ 0 能力清单

def t_caps():
    print("零、能力清单（程序提取）")
    check({"db", "http", "common", "data", "text", "auth", "quiz", "kg", "japanese", "doc"} <= PACKS and "probe" not in PACKS, "verbs/ 下的包都提取到（不含 probe）", sorted(PACKS))
    db = {v["名"]: v for v in CAPS["db"]}
    check("查一行表" in db and "写库表" in db and "库" in db["查询"]["参数"] and "查询" in db["查询"]["说明"] or db["查询"]["说明"], "db 包：动词名 / 参数 / 一句话说明", db.get("查询"))
    check(all(v["说明"] for v in CAPS["common"]), "common 包每个动词都有说明")
    check(any(v["名"] == "判作答" for v in CAPS["quiz"]), ".zs 写的脚本动词（quiz/defs）也在清单里")
    md = MB.cap_markdown(CAPS)
    check("## db" in md and "`写库表(" in md, "capabilities.md 渲染", md[:200])
    check("参数一" not in MB.cap_text(CAPS, {"db"}) and "[,k=v…]" in MB.cap_text(CAPS, {"db"}), "参数一…参数八压成 [,k=v…]")
    check(MB.cap_text(CAPS, {"db"}, brief=True).startswith("db: "), "brief 只列动词名")
    d = TMP / "fakeverbs"
    (d / "demo").mkdir(parents=True)
    (d / "demo" / "_verbs.py").write_text('def register(reg, workspace):\n    @reg.verb("打个招呼。例如 打招呼 小明")\n    def 打招呼(名字: str, 次数: str = "1") -> str:\n        return "hi"\n', encoding="utf-8")
    (d / "demo" / "再见.zs").write_text("# 说再见\n用包 common\n返回 bye\n", encoding="utf-8")
    c = MB.capabilities(d)
    check(list(c) == ["demo"] and {v["名"] for v in c["demo"]} == {"打招呼", "再见"}, "自定义 verbs 目录：python 动词 + .zs 动词", c)
    dm = {v["名"]: v for v in c["demo"]}
    check(dm["打招呼"]["说明"].startswith("打个招呼") and dm["打招呼"]["参数"] == ["名字", "次数"] and dm["再见"]["说明"] == "说再见", "说明取装饰器描述 / 脚本首行注释", c)


# ------------------------------------------------------------------ 1 顶层规划

def t_top():
    print("一、顶层规划校验")
    r = vtop()
    check(r["ok"] and r["top"]["构建顺序"] == ["quiz", "progress"] and r["top"]["共用流程"][0]["归属模块"] == "quiz", "合法顶层规划", r["errors"])
    check(MB.validate_top("```json\n" + dump(top_obj()) + "\n```", PACKS)["ok"], "带围栏的 JSON 能解析")
    check(not MB.validate_top("不是 JSON", PACKS)["ok"], "不是 JSON → 不过")

    def cyc(o):
        o["模块"][0]["依赖"] = ["progress"]
    check(has(vtop(cyc), "依赖成环"), "模块依赖成环 → 拒")

    def self_dep(o):
        o["模块"][0]["依赖"] = ["quiz"]
    check(has(vtop(self_dep), "依赖了自己"), "依赖自己 → 拒")

    def unknown_dep(o):
        o["模块"][1]["依赖"] = ["nope"]
    check(has(vtop(unknown_dep), "不在模块表里"), "依赖不在模块表里 → 拒")

    def order(o):
        o["构建顺序"] = ["progress", "quiz"]
    check(has(vtop(order), "不是依赖的拓扑序"), "构建顺序不是拓扑序 → 拒")

    def missing_order(o):
        o["构建顺序"] = ["quiz"]
    check(has(vtop(missing_order), "恰好包含全部模块"), "构建顺序少模块 → 拒")

    def flow_mod(o):
        o["主流程"][0]["经过模块"] = ["quiz", "ghost"]
    check(has(vtop(flow_mod), "经过的模块「ghost」不存在"), "主流程经过不存在的模块 → 拒")

    def not_dep(o):
        o["模块"][1]["依赖"] = []
    check(has(vtop(not_dep), "没有依赖归属方"), "共用流程的使用方不依赖归属方 → 拒")

    def bad_owner(o):
        o["共用流程"][0]["归属模块"] = "ghost"
    check(has(vtop(bad_owner), "归属模块「ghost」不是已知模块"), "共用流程归属模块未知 → 拒")

    def bad_user(o):
        o["共用流程"][0]["被用于"] = ["ghost"]
    check(has(vtop(bad_user), "使用方「ghost」不是已知模块"), "共用流程使用方未知 → 拒")

    def bad_pack(o):
        o["横切"]["调模型"] = [{"处": "x", "包": "nopack"}]
    check(has(vtop(bad_pack), "包「nopack」不存在"), "横切里调模型的包不存在 → 拒")

    def dup(o):
        o["模块"].append({"名": "quiz", "说明": "", "依赖": []})
    check(has(vtop(dup), "模块名「quiz」重复"), "模块名重复 → 拒")

    def badname(o):
        o["模块"][0]["名"] = "Quiz"
    check(has(vtop(badname), "要是英文小写 snake"), "模块名不合规 → 拒")

    def ppl(o):
        o["使用者"]["人数"] = "很多"
    check(has(vtop(ppl), "人数"), "人数不是 单人/多人 → 拒")
    check(has(vtop(task="学生登录后做题，老师才能导入"), "必须给出"), "需求提到登录却没给角色 → 拒")

    def trans(o):          # 间接依赖也算依赖
        o["模块"].append({"名": "report", "说明": "报告", "依赖": ["progress"]})
        o["共用流程"].append({"流程名": "quiz_text", "归属模块": "quiz", "被用于": ["report"]})
        o["构建顺序"] = ["quiz", "progress", "report"]
    check(vtop(trans)["ok"], "使用方间接依赖归属方也行")
    md = MB.plan_md(r["top"])
    check(all(s in md for s in ("## 主流程", "## 模块依赖", "## 共用流程归属", "## 横切", "## 构建顺序", "quiz_judge")), "PLAN.md 含目标 / 主流程 / 依赖 / 横切 / 构建顺序", md[:300])


# ------------------------------------------------------------------ 2 层次 × 模块

def t_split():
    print("二、层次×模块校验")
    r = vsplit()
    s = r["split"]
    check(r["ok"] and s["层"] == ["数据", "查询", "流程", "接口", "界面"] and s["规则表"] == {"R1": R1, "R2": R2}, "合法层次×模块；层按固定顺序、规则全局编号", r["errors"])
    check(s["模块"]["quiz"]["规则号"] == ["R1"] and s["模块"]["progress"]["规则号"] == ["R2"] and s["模块"]["progress"]["依赖"] == ["quiz"], "规则号按构建顺序编，依赖取自顶层")
    check(s["模块"]["quiz"]["能力"][:3] == ["db", "http", "common"] and "db" in s["模块"]["progress"]["能力"], "能力自动补 db/http/common")

    def extra(o):
        o["模块"].append({"名": "ghost", "规则": [], "数据": ["g"], "流程": [], "接口": [], "界面": [], "能力": [], "缺口": []})
    check(has(vsplit(extra), "不许多出模块"), "多出顶层没有的模块 → 拒")

    def less(o):
        o["模块"].pop()
    check(has(vsplit(less), "不许少模块"), "少了顶层的模块 → 拒")

    def role(o):
        o["模板"], o["角色"] = "private", ["teacher"]
    check(has(vsplit(role), "与顶层规划的使用者.角色"), "角色与顶层不一致 → 拒")

    def acct(o):
        o["模板"], o["角色"] = "private", ["student"]
        o["模块"][0]["数据"].append("user")
    t = top_obj()
    t["使用者"]["角色"] = ["student"]
    tt = MB.validate_top(dump(t), PACKS)["top"]
    check(has(vsplit(acct, top=tt), "账号表"), "private 时列 user 账号实体 → 拒")

    def acct2(o):
        o["模板"], o["角色"] = "private", ["student"]
    check(vsplit(acct2, top=tt)["ok"], "private + 角色一致放行")

    def cross(o):
        o["模块"][1]["数据"].append("attempt")
    check(has(vsplit(cross), "实体「attempt」重复"), "实体跨模块 → 拒")

    def pack(o):
        o["模块"][0]["能力"].append("nopack")
    check(has(vsplit(pack), "能力「nopack」不是现有包"), "不存在的包 → 拒")

    def verb(o):
        o["模块"][0]["缺口"] = [{"事": "朗读", "办法": "sql", "用动词": ["朗读全文"]}]
    check(has(vsplit(verb), "「朗读全文」不在能力清单里"), "缺口用不存在的动词搪塞 → 拒")

    def way(o):
        o["模块"][1]["缺口"] = [{"事": "x", "办法": "流程", "用动词": []}]
    check(has(vsplit(way), "本模块没有流程"), "缺口办法写流程但本模块没有流程 → 拒")

    def way2(o):
        o["模块"][0]["缺口"] = [{"事": "x", "办法": "魔法", "用动词": []}]
    check(has(vsplit(way2), "办法「魔法」只能是"), "缺口办法不在 sql/流程/待补 → 拒")

    def shared_wrong(o):
        fl = o["模块"][0]["流程"].pop()
        o["模块"][1]["流程"].append(fl)
        o["模块"][1]["接口"][0]["文件"] = "progress"
    check(has(vsplit(shared_wrong), "应放在顶层规定的归属模块 quiz"), "共用流程放错模块 → 拒")

    def bad_use(o):
        o["模块"][0]["流程"][0]["用于"] = ["quiz", "nofile"]
    check(has(vsplit(bad_use), "不是任何模块的接口文件"), "流程用于不存在的接口文件 → 拒")

    def unused(o):
        o["模块"][0]["流程"][0]["用于"] = []
    check(has(vsplit(unused), "没有接口用它"), "流程没人用 → 拒")

    def not_shared(o):
        o["模块"][1]["流程"] = [{"名": "prog_calc", "作用": "算", "用于": ["quiz"], "调流程": []}]
    check(has(vsplit(not_shared), "不能给模块 quiz 的接口"), "非共用流程给别的模块的接口用 → 拒")

    def calls_other(o):
        o["模块"][1]["流程"] = [{"名": "prog_calc", "作用": "算", "用于": ["progress"], "调流程": ["quiz_judge"]}]
    check(vsplit(calls_other)["ok"], "流程调顶层规定给本模块用的共用流程 → 放行")

    def calls_priv(o):
        o["模块"][0]["流程"].append({"名": "quiz_inner", "作用": "内部", "用于": ["quiz"], "调流程": []})
        o["模块"][1]["流程"] = [{"名": "prog_calc", "作用": "算", "用于": ["progress"], "调流程": ["quiz_inner"]}]
    check(has(vsplit(calls_priv), "只能调本模块的"), "流程调别的模块的私有流程 → 拒（调用方向按顶层依赖）")

    def loop(o):
        o["模块"][0]["流程"] = [{"名": "fa", "作用": "", "用于": ["quiz"], "调流程": ["fb"]}, {"名": "fb", "作用": "", "用于": [], "调流程": ["fa"]}]
        o["模块"][0]["流程"][0]["用于"] = ["quiz"]
        o["模块"][0]["流程"][1]["用于"] = ["quiz"]
    t2 = top_obj()
    t2["共用流程"] = []
    check(has(vsplit(loop, top=MB.validate_top(dump(t2), PACKS)["top"]), "流程互调成环"), "流程互调成环 → 拒")

    def bad_file(o):
        o["模块"][0]["接口"][0]["文件"] = "other"
    check(has(vsplit(bad_file), "要叫 quiz 或 quiz_<后缀>"), "接口文件名不以模块名起头 → 拒")

    def no_data(o):
        o["模块"][0]["数据"], o["模块"][1]["数据"] = [], []
    check(has(vsplit(no_data), "至少要有一个实体"), "没有任何实体 → 拒")

    def layer(o):
        o["层"] = {"数据": "x", "魔法": "y"}
    check(has(vsplit(layer), "层「魔法」不对"), "层不在候选里 → 拒")

    def layer2(o):
        del o["层"]["流程"]
    check(has(vsplit(layer2), "用到了「流程」层"), "模块用到的层没在「层」里列 → 拒")
    md = MB.layers_md(MB.validate_top(dump(top_obj()), PACKS)["top"], s)
    check(all(x in md for x in ("## 层次", "## 模块 × 层", "quiz_judge", "R1", "老库只加表加列")), "LAYERS.md 含层次表 / 模块×层表 / 规则 / 全局约束", md[:300])


# ------------------------------------------------------------------ 静态检查 / 调用核对

def t_checks():
    print("三、流程层动词检查 / 接口调 scripts 核对 / 跨模块限制")
    vp, packs = MB.verb_packs(CAPS), PACKS
    ok = MB.check_zs(ZS_FLOW, "scripts/quiz_judge.zs", vp, packs, False)
    check(ok == [], "合法流程脚本通过", ok)
    bad = ZS_FLOW.replace("写库表 app.db quiz_log {args}", "魔法写入 app.db quiz_log {args}")
    e = MB.check_zs(bad, "scripts/x.zs", vp, packs, False)
    check(any("动词「魔法写入」不在能力清单里" in x for x in e), "用了能力清单里没有的动词 → 不过", e)
    e = MB.check_zs(ZS_FLOW.replace("用包 db\n", "用包 common\n"), "scripts/x.zs", vp, packs, False)
    check(any("属于包 db，但这里没写 用包 db" in x for x in e), "动词的包没 用包 → 不过", e)
    e = MB.check_zs(ZS_FLOW.replace("用包 db", "用包 nopack"), "scripts/x.zs", vp, packs, False)
    check(any("包「nopack」不存在" in x for x in e), "用包写了不存在的包 → 不过", e)
    e = MB.check_zs("用包 db\n如果 {a} 等于 1\n  设 b = 2\n", "scripts/x.zs", vp, packs, False)
    check(any("没有「结束」配对" in x for x in e), "块没配对 → 不过", e)
    e = MB.check_zs("用包 db\n设 b = 2\n结束\n", "scripts/x.zs", vp, packs, False)
    check(any("多余的「结束」" in x for x in e), "多余的结束 → 不过", e)
    e = MB.check_zs("设 b = 2\n", "scripts/x.zs", vp, packs, False)
    check(any("要是 用包" in x for x in e), "第一行没有 用包 → 不过", e)
    e = MB.check_zs("用包 db\n设 flag = 否\n设 r = 计算 {a} + 1\n设 x = {a}\n遍历 row 于 {rows}\n  打印 {row}\n结束\n", "scripts/x.zs", vp, packs, False)
    check(e == [], "字面量 / 关键字右值 / 遍历块不误报", e)
    e = MB.check_zs(ZS_QUIZ, "routes/quiz.zs", vp, packs, True)
    check(e == [], "接口文件：块内 用包 + 执行 通过", e)
    e = MB.check_zs(ZS_QUIZ.replace("  用包 db http common\n", "  用包 common\n").replace("返回", "响应 lists {g}\n  返回"), "routes/quiz.zs", vp, packs, True)
    check(any("动词「响应」属于包 http" in x for x in e), "接口块里用了 http 的动词却没 用包 http → 不过", e)

    info = {"quiz_judge": {"模块": "quiz", "入参": ["question_id", "given"], "可选入参": ["window"], "出参": ["ok"], "文件": "scripts/quiz_judge.zs"},
            "prog_calc": {"模块": "progress", "入参": ["learner"], "可选入参": [], "出参": ["x"], "文件": "scripts/prog_calc.zs"}}
    acc = {"quiz_judge"}
    check(MB.check_calls(ZS_QUIZ, "routes/quiz.zs", info, acc) == [], "调用入参齐全 → 通过")
    e = MB.check_calls(ZS_QUIZ.replace(" given={given}", ""), "routes/quiz.zs", info, acc)
    check(any("缺少入参 given" in x for x in e), "少给必填入参 → 不过", e)
    e = MB.check_calls(ZS_QUIZ.replace("given={given}", "given={given} bogus=1"), "routes/quiz.zs", info, acc)
    check(any("多给了它没声明的键 bogus" in x for x in e), "多给未声明的键 → 不过", e)
    check(MB.check_calls(ZS_QUIZ.replace("given={given}", "given={given} window={w 或 5 天}"), "routes/quiz.zs", info, acc) == [], "可选入参 / 含空格的 {x 或 y} 值能解析")
    e = MB.check_calls(ZS_QUIZ.replace("quiz_judge", "ghost"), "routes/quiz.zs", info, acc)
    check(any("scripts/ghost.zs 不存在" in x for x in e), "调用不存在的 scripts → 不过", e)
    e = MB.check_calls(ZS_QUIZ.replace("quiz_judge", "prog_calc").replace("question_id={question_id} given={given}", "learner={u}"), "routes/quiz.zs", info, acc)
    check(any("属于别的模块" in x for x in e), "跨模块调用不在可调范围 → 不过（只调依赖模块里顶层规定的流程）", e)
    bg = "接口 POST /x 动作 x\n  用包 db http\n  后台执行 scripts/quiz_judge.zs question_id={a} given={b} on_error=scripts/fail.zs\n结束\n"
    e = MB.check_calls(bg, "routes/x.zs", info, acc)
    check(any("on_error 指向的 scripts/fail.zs 不存在" in x for x in e) and not any("多给" in x for x in e), "后台执行：on_error 要存在，且不算入参", e)
    check(MB.check_calls(bg, "routes/x.zs", info, acc, on_disk={"scripts/fail.zs"}) == [], "on_error 脚本在磁盘上 → 通过")
    e = MB.check_sql_scope("接口 POST /x 动作 x\n  设 r = 查一行 app.db other_sql a={a}\n结束\n", "routes/x.zs", {"quiz_log"})
    check(any("sql「other_sql」不在本模块和依赖模块" in x for x in e), "引用不在可用范围的 sql → 不过", e)

    # 计划校验
    flows = {"quiz_judge": {"入参": ["question_id", "given"], "可选入参": []}}
    ip = {"接口": [{"路径": "/p/a", "动作": "p_a", "角色": "", "入参": ["question_id", "given"], "用sql": [], "用流程": ["quiz_judge"],
                  "调用": {"quiz_judge": ["question_id", "given"]}, "规则": ["R2"], "说明": "x"}]}
    p, e = MB.plan_ifaces(dump(ip), [], {"R2"}, set(), set(), set(), flows, ["quiz_judge"])
    check(not e, "接口计划合法", e)
    ip2 = copy.deepcopy(ip)
    ip2["接口"][0]["调用"] = {"quiz_judge": ["question_id"]}
    p, e = MB.plan_ifaces(dump(ip2), [], {"R2"}, set(), set(), set(), flows, [])
    check(any("缺入参 ['given']" in x for x in e), "接口计划里调用缺入参 → 不过", e)
    ip3 = copy.deepcopy(ip)
    ip3["接口"][0]["用流程"] = ["prog_calc"]
    p, e = MB.plan_ifaces(dump(ip3), [], {"R2"}, set(), set(), set(), flows, [])
    check(any("不能用" in x for x in e), "接口计划用了不可调的流程 → 不过", e)
    p, e = MB.plan_ifaces(dump(ip), [], {"R2"}, set(), set(), set(), flows, ["quiz_judge", "other"])
    check(any("流程「other」给本文件用" in x for x in e), "层次×模块规定本文件用的流程没出现 → 不过", e)
    fp = {"入参": ["a"], "可选入参": [], "出参": ["ok"], "用sql": ["nosql"], "用流程": [], "用动词": ["魔法"], "规则": ["R9"], "步骤": ["x"]}
    p, e = MB.plan_flow(dump(fp), {"R1"}, {"quiz_log"}, set(), {"写库表"}, [])
    check(any("用sql「nosql」不存在" in x for x in e) and any("用动词「魔法」" in x for x in e) and any("规则「R9」" in x for x in e), "流程计划：不存在的 sql / 动词 / 规则 → 不过", e)
    p, e = MB.plan_flow(dump({**fp, "用sql": [], "用动词": [], "规则": []}), {"R1"}, set(), {"f2"}, set(), ["f2"])
    check(any("用流程里要写上" in x or "「用流程」里要写上" in x for x in e), "层次×模块里声明要调的流程，计划里要写上", e)
    p, e = MB.plan_entities(dump({"实体": [{"名": "question", "字段": [{"名": "t", "类型": "文本"}], "关联": [], "约束": []}]}), ["question", "attempt"], [])
    check(any("恰好是" in x for x in e), "实体计划：和模块「数据」列的不一致 → 不过", e)
    p, e = MB.plan_entities(dump({"实体": [{"名": "mastery", "字段": [{"名": "score", "类型": "整数"}], "关联": ["question"], "约束": []}]}), ["mastery"], ["question"])
    check(any("要有字段 question_id" in x for x in e), "实体计划：有关联就要有 <实体>_id 字段", e)
    p, e = MB.plan_sqls(dump({"sql": [{"名": "other_x", "参数": ["a"], "规则": []}]}), "quiz", set(), set(), set())
    check(any("要以「quiz_」开头" in x for x in e), "sql 计划：名字要以模块名开头", e)
    p, e = MB.plan_sqls(dump({"sql": []}), "quiz", set(), set(), set())
    check(not e and p == {"sql": []}, "sql 计划可以为 []")


# ------------------------------------------------------------------ 四、全流程（假模型）

class Fake:
    """按提示词里的角色标记认出是哪一步、哪个文件。bad = {键: [回复…]} 覆盖默认回复（用完回最后一个）：
    ("顶层",) ("拆分",) ("计划", 层, 名) ("生成", 层, 名) ("核对",)。"""

    def __init__(self, bad=None, cost=0.0, top=None, split=None, ents=None):
        self.bad, self.cost, self.prompts, self.used, self.calls = bad or {}, cost, [], {}, []
        self.top, self.split = top or top_obj(), split or split_obj()
        self.ents = ents or {"quiz": ENT_Q + "\n" + ENT_A, "progress": ENT_M}

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
        mod = lambda: re.search(r'"模块": "(\w+)"', user).group(1)      # noqa: E731
        file = lambda: re.search(r"本文件：(\S+)", user).group(1)        # noqa: E731
        if "项目架构师" in user:
            return self.pick(("顶层",), dump(self.top))
        if "项目架构助手" in user:
            return self.pick(("拆分",), dump(self.split))
        if "单文件规划助手（数据层）" in user:
            m = mod()
            ents = {"quiz": [{"名": "question", "字段": [{"名": "title", "类型": "文本"}, {"名": "answer", "类型": "文本"}], "关联": [], "约束": []},
                             {"名": "attempt", "字段": [{"名": "question_id", "类型": "整数"}, {"名": "given", "类型": "文本"}, {"名": "correct", "类型": "整数"}], "关联": ["question"], "约束": []}],
                    "progress": [{"名": "mastery", "字段": [{"名": "question_id", "类型": "整数"}, {"名": "score", "类型": "整数"}], "关联": ["question"], "约束": []}]}[m]
            return self.pick(("计划", "数据", m), dump({"实体": ents}))
        if "单文件规划助手（查询层）" in user:
            m = mod()
            sq = {"quiz": [{"名": "quiz_log", "参数": ["question_id", "given"], "说明": "写作答", "规则": ["R1"]}], "progress": []}[m]
            return self.pick(("计划", "查询", m), dump({"sql": sq}))
        if "单文件规划助手（流程层）" in user:
            return self.pick(("计划", "流程", "quiz_judge"), dump({"入参": ["question_id", "given"], "可选入参": [], "出参": ["ok", "n"], "用sql": ["quiz_log"], "用流程": [],
                                                              "用动词": ["写库表"], "规则": ["R1"], "步骤": ["写记录"]}))
        if "单文件规划助手（接口层）" in user:
            f = file()
            ia = {"routes/quiz.zs": {"路径": "/quiz/answer", "动作": "quiz_answer", "入参": ["question_id", "given"], "规则": ["R1"]},
                  "routes/progress.zs": {"路径": "/progress/recheck", "动作": "progress_recheck", "入参": ["question_id", "given"], "规则": ["R2"]}}[f]
            a = {**ia, "角色": "", "用sql": [], "用流程": ["quiz_judge"], "调用": {"quiz_judge": ["question_id", "given"]}, "说明": "x"}
            return self.pick(("计划", "接口", f), dump({"接口": [a]}))
        if "单文件规划助手（界面层）" in user:
            name = re.search(r'本页：\{"名": "(\w+)"', user).group(1)
            path = "/quiz/answer" if name == "quiz_page" else "/progress/recheck"
            return self.pick(("计划", "界面", name), dump({"页面": [{"名": name, "说明": "x", "用接口": [path], "字段": ["given"]}]}))
        if "应用建模助手" in user:
            f = file()
            return self.pick(("生成", "数据", f), f"=== {f} ===\n{self.ents[Path(f).stem]}")
        if "SQLite 语句助手" in user:
            f = file()
            return self.pick(("生成", "查询", f), f"=== queries/quiz_log.sql ===\n{SQL_A}")
        if ".zs 流程助手" in user:
            f = file()
            return self.pick(("生成", "流程", f), f"=== {f} ===\n{ZS_FLOW}")
        if ".zs 接口助手" in user:
            f = file()
            return self.pick(("生成", "接口", f), f"=== {f} ===\n{ZS_QUIZ if f == 'routes/quiz.zs' else ZS_PROG}")
        if ".ui 界面助手" in user:
            f = file()
            return self.pick(("生成", "界面", f), f"=== {f} ===\n{UI_Q if 'quiz' in f else UI_P}")
        if "需求核对员" in user:
            rules = json.loads(re.search(r"规则：(\[.*?\]) 本功能sql", user, re.S).group(1))
            ok = dump([{"序号": i, "规则": r, "实现": "是", "依据": "x"} for i, r in enumerate(rules, 1)])
            return self.pick(("核对",), ok)
        return "?"


def go(name, fake, req=REQ, **kw):
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    return V.run_newproj(req, d / "proj", d / "out", model=fake, modular=True, **kw), d / "proj", d / "out"


def files(r):
    return {f["文件"]: f for f in r["v2"].get("文件", [])}


def t_full():
    print("四、假模型全流程：逐层顺序 / 构建顺序 / 产物")
    fk = Fake()
    r, p, out = go("full", fk)
    fs = files(r)
    check(r["fixed"] and r["v2"]["结论"] == "成功" and not r["stop"], "全流程成功", (r["stop"], {k: v["结果"] for k, v in fs.items()}))
    order = [f["文件"] for f in r["v2"]["文件"]]
    want = ["entities/quiz.entity", "entities/progress.entity", "queries/quiz_*.sql", "queries/progress_*.sql", "scripts/quiz_judge.zs", "routes/quiz.zs", "routes/progress.zs", "ui/quiz_page.ui", "ui/progress_page.ui"]
    got = [x for x in order if x in want]
    check(got == [w for w in want if w in got] and len(got) == 9, "逐层顺序：数据 → 查询 → 流程 → 接口 → 界面；层内按构建顺序（quiz 先于 progress）", order)
    layers = [f["层"] for f in r["v2"]["文件"]]
    check(layers == sorted(layers, key=["数据", "查询", "流程", "接口", "界面"].index), "文件记录按层单调（每层做完再进下一层）", layers)
    q = fs["scripts/quiz_judge.zs"]
    check(q["层"] == "流程" and q["模块"] == "quiz" and q["规划尝试"] == 1 and q["生成尝试"] == 1 and q["失败原因"] == "" and q["未实现规则"] == [], "每文件记 层 / 模块 / 结果 / 尝试 / 失败原因 / 未实现规则", q)
    check(fs["queries/progress_*.sql"]["结果"] == "通过" if "queries/progress_*.sql" in fs else True, "progress 没有定制 sql 也能过")
    for rel in ("entities/quiz.entity", "entities/progress.entity", "queries/quiz_log.sql", "scripts/quiz_judge.zs", "routes/quiz.zs", "routes/progress.zs", "ui/quiz_page.ui", "ui/progress_page.ui"):
        if not (p / rel).is_file():
            check(False, f"产物缺 {rel}")
    check((p / "scripts/quiz_judge.zs").read_text(encoding="utf-8").startswith("# 判一道题") and "scripts/quiz_judge.zs" in (p / "routes/progress.zs").read_text(encoding="utf-8"), "流程在 scripts/，两个模块的接口都调同一份共用流程")
    check(all((out / n).is_file() for n in ("capabilities.md", "PLAN.md", "LAYERS.md", "result.json", "calls.json")), "输出目录有 capabilities.md / PLAN.md / LAYERS.md / result.json / calls.json", sorted(x.name for x in out.iterdir()))
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    v2 = res["v2"]
    check(v2["modular"] is True and v2["顶层规划"]["构建顺序"] == ["quiz", "progress"] and v2["层次"]["规则表"] == {"R1": R1, "R2": R2} and v2["清单"]["文件数"] == 9, "result.json v2 带 顶层规划 / 层次 / 清单", {k: v2.get(k) for k in ("modular", "清单")})
    # 调用数：顶层 1 + 拆分 1 + 数据 2×(规划+生成) + 查询 quiz 2 + progress 1(规划) + 流程 2 + 核对 1 + 接口 2×(2+核对) + 界面 2×2
    check(r["calls"] == 2 + 4 + 3 + 3 + 3 + 3 + 4 or r["calls"] > 20, "调用数合理", r["calls"])
    check(len(fk.of("需求核对员")) == 3, "有规则的流程 / 接口各核对一次（流程 R1、quiz 接口 R1、progress 接口 R2）", len(fk.of("需求核对员")))
    ents_prompt = fk.of("应用建模助手")
    check(len(ents_prompt) == 2 and "实体 question" in ents_prompt[1], "progress 的实体生成能看到依赖模块 quiz 的实体全文", ents_prompt[-1][-600:])
    ip = fk.of(".zs 接口助手")
    check("quiz_judge" in ip[0] and "question_id" in ip[0] and "能力清单" in ip[0], "接口生成拿到流程签名 / 全文和能力清单", ip[0][-900:])
    check(ROOT.joinpath("tools/dslagent/packs/newproj/prompts/sys_mtop.md").is_file(), "新提示词 sys_mtop.md 在")
    return fk, r


def t_rewrite():
    print("五、检查不过带报错重写 / 失败隔离与跳过")
    bad_flow = ZS_FLOW.replace("写库表 app.db quiz_log {args}", "魔法写入 app.db quiz_log {args}")
    fk = Fake(bad={("生成", "流程", "scripts/quiz_judge.zs"): [f"=== scripts/quiz_judge.zs ===\n{bad_flow}", f"=== scripts/quiz_judge.zs ===\n{ZS_FLOW}"]})
    r, p, _ = go("rw_flow", fk)
    f = files(r)["scripts/quiz_judge.zs"]
    check(r["fixed"] and f["生成尝试"] == 2 and f["结果"] == "通过", "流程用了不存在的动词 → 带报错重写一次后通过", f)
    check("魔法写入" in fk.of(".zs 流程助手")[1] and "能力清单" in fk.of(".zs 流程助手")[1], "重写提示里带上了报错")
    bad_q = ZS_QUIZ.replace(" given={given}", "")
    fk = Fake(bad={("生成", "接口", "routes/quiz.zs"): [f"=== routes/quiz.zs ===\n{bad_q}", f"=== routes/quiz.zs ===\n{ZS_QUIZ}"]})
    r, _, _ = go("rw_iface", fk)
    f = files(r)["routes/quiz.zs"]
    check(r["fixed"] and f["生成尝试"] == 2 and "缺少入参 given" in fk.of(".zs 接口助手")[1], "接口调 scripts 少入参 → 带报错重写", f)
    # 两次都不过 → 该文件失败；依赖它的上层跳过
    fk = Fake(bad={("生成", "流程", "scripts/quiz_judge.zs"): [f"=== scripts/quiz_judge.zs ===\n{bad_flow}"]})
    r, p, _ = go("fail_flow", fk)
    fs = files(r)
    check(fs["scripts/quiz_judge.zs"]["结果"] == "失败" and not (p / "scripts/quiz_judge.zs").exists(), "流程两次生成都不过 → 失败并撤回（文件不留）", fs["scripts/quiz_judge.zs"])
    check(fs["routes/quiz.zs"]["结果"] == "跳过" and fs["routes/progress.zs"]["结果"] == "跳过" and "依赖的文件没写成" in fs["routes/quiz.zs"]["失败原因"], "依赖它的两个接口文件（含跨模块共用）跳过，不调模型", {k: v["结果"] for k, v in fs.items()})
    check(fs["ui/quiz_page.ui"]["结果"] == "跳过" and fs["entities/progress.entity"]["结果"] == "通过" and fs["queries/quiz_*.sql"]["结果"] == "通过", "下层文件和无关文件照常；界面跳过")
    check(len(fk.of(".zs 接口助手")) == 0 and len(fk.of(".ui 界面助手")) == 0, "跳过的文件没有调用模型")
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and r["stop"].startswith("部分成功") and "scripts/quiz_judge.zs" in r["stop"], "结论 部分成功，原因列出失败与跳过", r["stop"])
    # 数据层：quiz 失败 → 没有一个实体写成，整体失败
    bad_ent = "=== entities/quiz.entity ===\n实体 question 题目\n  字段 title 无此类型 必填 题干\n结束\n"
    fk = Fake(bad={("生成", "数据", "entities/quiz.entity"): [bad_ent]})
    r, _, _ = go("fail_ent", fk)
    fs = files(r)
    check(fs["entities/quiz.entity"]["结果"] == "失败" and fs["entities/progress.entity"]["结果"] == "跳过", "数据层失败 → 依赖它的模块数据跳过", {k: v["结果"] for k, v in fs.items()})
    check(r["v2"]["结论"] == "失败" and "没有一个模块的实体写成" in r["stop"], "没有一个模块的实体写成 → 整体失败，不进查询层", r["stop"])
    # progress 的实体失败：它的查询 / 接口 / 界面跳过，quiz 不受影响
    bad_m = "=== entities/progress.entity ===\n实体 mastery 掌握\n  字段 score 无此类型 必填 得分\n结束\n"
    fk = Fake(bad={("生成", "数据", "entities/progress.entity"): [bad_m]})
    r, _, _ = go("fail_ent2", fk)
    fs = files(r)
    check(fs["entities/progress.entity"]["结果"] == "失败" and fs["routes/progress.zs"]["结果"] == "跳过" and fs["ui/progress_page.ui"]["结果"] == "跳过" and fs["queries/progress_*.sql"]["结果"] == "跳过",
          "某模块实体失败 → 它的查询 / 接口 / 界面跳过", {k: v["结果"] for k, v in fs.items()})
    check(fs["routes/quiz.zs"]["结果"] == "通过" and fs["ui/quiz_page.ui"]["结果"] == "通过" and r["v2"]["结论"] == "部分成功", "quiz 模块照常建成，整体 部分成功")
    # 规划不过两次 → 该文件失败
    fk = Fake(bad={("计划", "接口", "routes/progress.zs"): [dump({"接口": [{"路径": "/progress/recheck", "动作": "progress_recheck", "入参": [], "用流程": ["ghost"], "规则": ["R2"]}]})]})
    r, _, _ = go("fail_plan", fk)
    f = files(r)["routes/progress.zs"]
    check(f["结果"] == "失败" and f["规划尝试"] == 2 and "单文件规划两次没过" in f["失败原因"] and not [p for p in fk.of(".zs 接口助手") if "本文件：routes/progress.zs" in p], "单文件规划两次不过 → 该文件失败", f)
    check(files(r)["routes/quiz.zs"]["结果"] == "通过" and files(r)["ui/progress_page.ui"]["结果"] == "跳过", "其它文件照做，同模块界面跳过")
    # 规则核对不过 → 重写一轮 → 仍缺则记未实现
    no = dump([{"序号": 1, "规则": "x", "实现": "否", "依据": ""}])
    fk = Fake(bad={("核对",): [no]})
    r, _, _ = go("unimpl", fk)
    fs = files(r)
    check(fs["routes/quiz.zs"]["结果"] == "通过" and fs["routes/quiz.zs"]["未实现规则"] and fs["routes/quiz.zs"]["核对"] == 2, "规则核对不过：重写一轮再核对，仍缺记「未实现规则」", fs["routes/quiz.zs"])
    check(r["v2"]["结论"] == "部分成功" and "规则没全部实现" in r["stop"], "有未实现规则 → 部分成功", r["stop"])
    # 规则没落到任何文件
    sp = split_obj()
    sp["模块"][1]["规则"] = [R2, "每周一发报告"]
    fk = Fake(split=sp)
    r, _, _ = go("unclaimed", fk)
    check(r["v2"]["结论"] == "部分成功" and any("每周一发报告" in x for x in r["v2"]["规则未覆盖"]), "规则没有落到任何文件 → 报出来，部分成功", (r["stop"], r["v2"].get("规则未覆盖")))


def t_plans_retry():
    print("六、顶层规划 / 层次 重写与预算")
    bad_top = top_obj()
    bad_top["模块"][0]["依赖"] = ["progress"]
    fk = Fake(bad={("顶层",): [dump(bad_top), dump(top_obj())]})
    r, _, _ = go("top_retry", fk)
    check(r["fixed"] and len(fk.of("项目架构师")) == 2 and "依赖成环" in fk.of("项目架构师")[1], "顶层规划不过 → 带报错重写，第二次通过", r["stop"])
    fk = Fake(bad={("顶层",): [dump(bad_top)]})
    r, p, _ = go("top_fail", fk)
    check(not r["fixed"] and r["v2"]["结论"] == "失败" and "顶层规划两次都没过" in r["stop"] and r["calls"] == 2, "顶层规划重写后仍不过 → 失败（共 2 次调用，不再往下）", (r["stop"], r["calls"]))
    check(not fk.of("项目架构助手") and not (p / "entities").exists(), "失败后不进入层次拆分，也不建文件")
    bad_split = split_obj()
    bad_split["模块"].pop()
    fk = Fake(bad={("拆分",): [dump(bad_split), dump(split_obj())]})
    r, _, _ = go("split_retry", fk)
    check(r["fixed"] and len(fk.of("项目架构助手")) == 2 and "不许少模块" in fk.of("项目架构助手")[1], "层次×模块与顶层不一致 → 带报错重写", r["stop"])
    fk = Fake(bad={("拆分",): [dump(bad_split)]})
    r, _, _ = go("split_fail", fk)
    check(not r["fixed"] and "层次×模块两次都没过" in r["stop"] and r["calls"] == 3, "层次×模块两次不过 → 失败（顶层 1 + 拆分 2，共 3 次）", (r["stop"], r["calls"]))
    r, _, _ = go("budget1", Fake(), max_calls=1)
    check(not r["fixed"] and "总模型调用已满" in r["stop"] and r["calls"] == 1, "显式 max_calls 是上限", (r["stop"], r["calls"]))
    r, _, _ = go("budget2", Fake(), max_calls=8)
    check(not r["fixed"] and r["calls"] == 8 and r["v2"]["结论"] == "部分成功", "调用用完 → 部分成功（已建文件保留）", (r["stop"], r["calls"]))
    fs = files(r)
    check(any(f["结果"] == "未做" for f in fs.values()) and fs["entities/quiz.entity"]["结果"] == "通过", "没轮到的文件记「未做」", {k: v["结果"] for k, v in fs.items()})


def t_cap():
    print("七、花费熔断")
    fk = Fake(cost=1.0)
    r, p, _ = go("cap", fk, cost_cap=4.5)
    fs = files(r)
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and r["stop"].startswith("部分成功：花费达上限") and r["calls"] == 5,
          "累计 ≥ 上限就不再调模型（顶层 + 拆分 + quiz 数据规划 / 生成 + progress 数据规划，共 5 次）", (r["stop"], r["calls"], r["cost"]))
    check((p / "entities/quiz.entity").is_file() and fs["routes/quiz.zs"]["结果"] == "未做" and fs["ui/progress_page.ui"]["结果"] == "未做", "熔断后已写文件保留，后面的文件记「未做」", {k: v["结果"] for k, v in fs.items()})
    os.environ["NEWPROJ_COST_CAP"] = "2.5"
    try:
        r, _, _ = go("cap_env", Fake(cost=1.0))
        check(r["stop"].startswith("部分成功：花费达上限") or "花费达上限" in r["stop"], "环境变量 NEWPROJ_COST_CAP 同样生效", (r["stop"], r["calls"]))
    finally:
        os.environ.pop("NEWPROJ_COST_CAP", None)
    r, _, _ = go("capfirst", Fake(cost=1.0), cost_cap=0.5)
    check(not r["fixed"] and r["calls"] == 1 and "花费达上限" in r["stop"], "顶层规划之后就超上限 → 不再往下（失败）", (r["stop"], r["calls"]))


def t_kill():
    print("八、被杀 / 超长 = 该文件失败不终止")
    killed = {"text": "", "rc": -9, "cost": 0.1}
    fk = Fake(bad={("生成", "接口", "routes/quiz.zs"): [killed]})
    r, _, _ = go("killed", fk)
    fs = files(r)
    check(fs["routes/quiz.zs"]["结果"] == "失败" and "模型没有完成输出" in fs["routes/quiz.zs"]["失败原因"] and len(fk.of(".zs 接口助手")) == 2, "接口生成被杀 → 该文件失败不重试（其它接口照做）", fs["routes/quiz.zs"])
    check(fs["routes/progress.zs"]["结果"] == "通过" and fs["ui/quiz_page.ui"]["结果"] == "跳过" and fs["ui/progress_page.ui"]["结果"] == "通过", "无关文件照做，依赖它的界面跳过")
    long_ = {"text": "x", "rc": 0, "reason": "输出超长", "cost": 0.1}
    fk = Fake(bad={("计划", "界面", "progress_page"): [long_]})
    r, _, _ = go("long", fk)
    f = files(r)["ui/progress_page.ui"]
    check(f["结果"] == "失败" and "输出超长" in f["失败原因"] and len(fk.of(".ui 界面助手")) == 1, "规划输出超长 → 该界面失败，不进生成", f)


def t_cli():
    print("九、CLI / 登记 / 提示词")
    from tools.dslagent import __main__ as M
    import inspect
    seen = {}
    real = V.run_newproj
    V.run_newproj = lambda req, project, out, **kw: seen.update(kw) or {"fixed": True, "calls": 0, "cost": 0, "seconds": 0, "stop": "", "changed_files": []}
    try:
        rq = TMP / "cli_req.txt"
        rq.write_text("需求", encoding="utf-8")
        M.main(["newproj", "--modular", "--cost-cap", "2.5", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(seen.get("modular") is True and seen.get("cost_cap") == 2.5 and not seen.get("layered"), "CLI newproj --modular --cost-cap → run_newproj(modular=True, cost_cap=2.5)", seen)
        seen.clear()
        M.main(["newproj", "--layered", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(seen.get("layered") is True and not seen.get("modular"), "--layered 仍走旧路径", seen)
        seen.clear()
        M.main(["newproj", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(not seen.get("modular") and not seen.get("layered"), "不带开关仍是旧模板", seen)
    finally:
        V.run_newproj = real
    sig = inspect.signature(V.run_newproj).parameters
    check(sig["modular"].default is False and sig["layered"].default is False and sig["split"].default is False, "run_newproj 新参数缺省不改旧行为")
    pr = ROOT / "tools/dslagent/packs/newproj/prompts"
    names = ["top", "split", "model", "plan_ent", "plan_sql", "plan_flow", "plan_iface", "plan_ui", "gen_ent", "gen_sql", "gen_flow", "gen_iface", "gen_ui"]
    check(all((pr / f"sys_m{n}.md").is_file() for n in names), "sys_m*.md 提示词齐全")
    for n in ("top", "split", "plan_flow", "plan_iface"):
        t = (pr / f"sys_m{n}.md").read_text(encoding="utf-8")
        check("{" in t and "\"" in t and "示例" in t or "{\"" in t, f"sys_m{n}.md 带具体 JSON 示例")


def main():
    try:
        t_caps()
        t_top()
        t_split()
        t_checks()
        t_full()
        t_rewrite()
        t_plans_retry()
        t_cap()
        t_kill()
        t_cli()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
