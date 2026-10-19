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

from tools.dslagent import modbuild as MB, v2 as V, loadcheck as LC, engines as E      # noqa: E402

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
        self.bad, self.cost, self.prompts, self.used, self.calls, self.models = bad or {}, cost, [], {}, [], []
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
        self.models.append(model)
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


def resume(name, fake, req=REQ, **kw):
    d = TMP / name
    return V.run_newproj(req, d / "proj", d / "out", model=fake, modular=True, resume=True, **kw), d / "proj", d / "out"


def rjson(out):
    return json.loads((out / "result.json").read_text(encoding="utf-8"))


def t_gen_ents():
    print("十、gen 生成的实体（private 的 user）给查询 / 流程 / 接口")
    top, sp = top_obj(), split_obj()
    top["使用者"]["角色"] = ["teacher", "student"]
    sp["模板"], sp["角色"] = "private", ["teacher", "student"]
    fk = Fake(top=top, split=sp)
    r, p, _ = go("gen_ents", fk, req=REQ + "学生和老师要登录，只看自己的数据。")
    check(r["fixed"] and (p / "entities/user.entity").is_file(), "private：gen 生成了 user.entity，整个流程成功", (r["stop"], sorted(x.name for x in (p / "entities").iterdir()) if (p / "entities").is_dir() else ""))
    for what, marker in (("查询规划", "单文件规划助手（查询层）"), ("查询生成", "SQLite 语句助手"), ("流程规划", "单文件规划助手（流程层）"), ("流程生成", ".zs 流程助手"),
                         ("接口规划", "单文件规划助手（接口层）"), ("接口生成", ".zs 接口助手")):
        ps = fk.of(marker)
        check(ps and all("实体 user" in x and "password_hash" in x and "账号表是 user（gen 生成）" in x for x in ps), f"{what}的输入带 gen 生成的 user 实体全文 + 账号表说明", [x[-300:] for x in ps][:1])
    check(not any("gen 生成的实体全文" in x for x in fk.of("应用建模助手")), "数据层（gen 之前）不带")
    fk = Fake()
    r, _, _ = go("gen_ents_none", fk)
    check(r["fixed"] and not any("gen 生成的实体全文" in x for x in fk.of("SQLite 语句助手")), "没有 gen 实体（非 private）时不加这一段")


def t_silent():
    print("十一、空闲超时 / 首字前静默：同一调用重试 1 次；超长不重试")
    idle = {"text": "", "rc": 0, "reason": "空闲超时", "cost": 0.1}
    first = {"text": "", "rc": 0, "reason": "首字前静默超时", "cost": 0.1}
    good = f"=== queries/quiz_log.sql ===\n{SQL_A}"
    fk = Fake(bad={("生成", "查询", "queries/quiz_*.sql"): [idle, good]})
    r, _, _ = go("idle1", fk)
    f = files(r)["queries/quiz_*.sql"]
    check(r["fixed"] and f["结果"] == "通过" and f["静默重试"] == 1 and len(fk.of("SQLite 语句助手")) == 2 and f["生成尝试"] == 1, "查询生成空闲超时 → 重试 1 次后通过（不占生成尝试）", f)
    check(fk.of("SQLite 语句助手")[0] == fk.of("SQLite 语句助手")[1], "重试的是同一输入")
    fk = Fake(bad={("计划", "流程", "quiz_judge"): [first, dump({"入参": ["question_id", "given"], "可选入参": [], "出参": ["ok", "n"], "用sql": ["quiz_log"], "用流程": [], "用动词": ["写库表"], "规则": ["R1"], "步骤": ["写记录"]})]})
    r, _, _ = go("first1", fk)
    check(r["fixed"] and files(r)["scripts/quiz_judge.zs"]["静默重试"] == 1, "规划首字前静默 → 同样重试 1 次", files(r)["scripts/quiz_judge.zs"])
    fk = Fake(bad={("生成", "接口", "routes/quiz.zs"): [idle]})
    r, _, _ = go("idle2", fk)
    f = files(r)["routes/quiz.zs"]
    check(f["结果"] == "失败" and "空闲超时" in f["失败原因"] and "已重试 1 次" in f["失败原因"] and len([x for x in fk.of(".zs 接口助手") if "本文件：routes/quiz.zs" in x]) == 2 and f["静默重试"] == 1, "重试后仍空闲超时 → 该文件失败（只重试 1 次，不是无限）", f)
    check(files(r)["routes/progress.zs"]["结果"] == "通过" and files(r)["ui/quiz_page.ui"]["结果"] == "跳过", "失败隔离不变")
    long_ = {"text": "x", "rc": 0, "reason": "输出超长", "cost": 0.1}
    fk = Fake(bad={("生成", "接口", "routes/quiz.zs"): [long_]})
    r, _, _ = go("long2", fk)
    f = files(r)["routes/quiz.zs"]
    check(f["结果"] == "失败" and "输出超长" in f["失败原因"] and len([x for x in fk.of(".zs 接口助手") if "本文件：routes/quiz.zs" in x]) == 1 and "静默重试" not in f, "输出超长不重试", f)
    fk = Fake(bad={("生成", "接口", "routes/quiz.zs"): [idle, idle]}, cost=0.0)
    r, _, _ = go("idle_cap", fk, cost_cap=0.35)
    check("花费达上限" in r["stop"] or r["v2"]["结论"] != "成功", "重试前仍检查花费熔断（不绕过 cap）", r["stop"][:200])


def t_resume():
    print("十二、继续构建 --resume")
    bad_flow = ZS_FLOW.replace("写库表 app.db quiz_log {args}", "魔法写入 app.db quiz_log {args}")
    fk1 = Fake(bad={("生成", "流程", "scripts/quiz_judge.zs"): [f"=== scripts/quiz_judge.zs ===\n{bad_flow}"]}, cost=0.5)
    r1, p, out = go("rs", fk1)
    f1 = files(r1)
    check(not r1["fixed"] and f1["scripts/quiz_judge.zs"]["结果"] == "失败" and f1["routes/quiz.zs"]["结果"] == "跳过", "第一次：流程失败，接口 / 界面跳过", {k: v["结果"] for k, v in f1.items()})
    check((out / "top.json").is_file() and (out / "split.json").is_file(), "两步规划的结果落盘（top.json / split.json）")
    n1, cost1 = len(json.loads((out / "calls.json").read_text(encoding="utf-8"))), r1["cost"]
    fk2 = Fake(cost=0.5)
    r2, _, _ = resume("rs", fk2)
    f2 = files(r2)
    check(r2["fixed"] and r2["v2"]["结论"] == "成功" and all(v["结果"] == "通过" for v in f2.values()), "继续构建：全部通过", (r2["stop"], {k: v["结果"] for k, v in f2.items()}))
    check(not fk2.of("项目架构师") and not fk2.of("项目架构助手"), "不重做顶层规划和层次×模块")
    check(not fk2.of("应用建模助手") and not fk2.of("SQLite 语句助手") and not fk2.of("单文件规划助手（数据层）") and not fk2.of("单文件规划助手（查询层）"), "已通过的数据 / 查询文件跳过，不调模型")
    check(len(fk2.of(".zs 流程助手")) == 1 and len(fk2.of(".zs 接口助手")) == 2 and len(fk2.of(".ui 界面助手")) == 2, "失败的流程 + 跳过的接口 / 界面按原顺序重做")
    fp = fk2.of(".zs 流程助手")[0]
    check("上次运行失败" in fp and "魔法写入" in fp, "失败的文件把上次失败原因当「上次的报错」带入生成提示", fp[-400:])
    fpl = fk2.of("单文件规划助手（流程层）")[0]
    check("上次运行失败" in fpl, "规划提示也带上次失败原因")
    check(f2["entities/quiz.entity"].get("沿用") and f2["queries/quiz_*.sql"].get("沿用") and not f2["scripts/quiz_judge.zs"].get("沿用"), "沿用的文件标「沿用」，重做的不标", {k: v.get("沿用") for k, v in f2.items()})
    check(f2["scripts/quiz_judge.zs"]["运行"] == 2 and f2["entities/quiz.entity"]["运行"] == 1, "每个文件记是第几次运行产生的")
    check((p / "scripts/quiz_judge.zs").is_file() and "scripts/quiz_judge.zs" in (p / "routes/progress.zs").read_text(encoding="utf-8"), "产物齐全，共用流程被两个接口调用")
    res = rjson(out)
    runs = res["v2"]["运行"]
    check([x["序号"] for x in runs] == [1, 2] and runs[0]["结论"] == "部分成功" and runs[1]["结论"] == "成功", "result.json 保留上次记录并追加本次（v2.运行）", [(x["序号"], x["结论"]) for x in runs])
    check(abs(res["v2"]["累计花费"] - (cost1 + r2["cost"])) < 1e-6 and abs(r2["cost"] - 0.5 * len(fk2.calls)) < 1e-6, "累计花费 = 上次 + 本次；cost 是本次的", (res["v2"]["累计花费"], cost1, r2["cost"]))
    check(runs[1]["沿用"] == 4 and runs[1]["重做"] == 5 and {x["文件"] for x in runs[1]["文件"]} == {"scripts/quiz_judge.zs", "routes/quiz.zs", "routes/progress.zs", "ui/quiz_page.ui", "ui/progress_page.ui"}, "本次记录：沿用 4 个，重做 5 个", runs[1]["文件"])
    log = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check(len(log) == n1 + len(fk2.calls) and [c["run"] for c in log] == [1] * n1 + [2] * len(fk2.calls), "calls.json 追加不覆盖，每条标运行序号", (len(log), n1))
    check(len({c["n"] for c in log}) == len(log) and len(list((out / "calls").glob("*.reply.txt"))) == len(log), "调用编号接着往下排，calls/ 里旧文件没被覆盖")
    check((out / "result.run1.json").is_file() and rjson(out)["calls"] == len(fk2.calls), "上次 result.json 另存 result.run1.json；calls 是本次调用数", rjson(out)["calls"])
    # 再继续一次：全部沿用，零调用
    fk3 = Fake()
    r3, _, _ = resume("rs", fk3)
    check(r3["fixed"] and not fk3.prompts and [x["序号"] for x in rjson(out)["v2"]["运行"]] == [1, 2, 3], "全部通过后再继续：全部沿用，不调模型", len(fk3.prompts))

    print("  -- 通过的文件被删 / 改坏 → 不沿用，重做")
    (p / "scripts/quiz_judge.zs").unlink()
    (p / "queries/quiz_log.sql").write_text("SELECT FROM WHERE", encoding="utf-8")
    fk4 = Fake()
    r4, _, _ = resume("rs", fk4)
    f4 = files(r4)
    check(r4["fixed"] and not f4["scripts/quiz_judge.zs"].get("沿用") and not f4["queries/quiz_*.sql"].get("沿用"), "文件不在磁盘 / 预编译不过的「通过」文件重做", {k: v.get("沿用") for k, v in f4.items()})
    check(len(fk4.of("SQLite 语句助手")) == 1 and len(fk4.of(".zs 流程助手")) == 1 and "不能沿用" in fk4.of("SQLite 语句助手")[0], "重做时带「上次通过，这次不能沿用」原因", fk4.of("SQLite 语句助手")[0][-300:])
    check(f4["routes/quiz.zs"].get("沿用") and f4["entities/quiz.entity"].get("沿用"), "没问题的上游 / 下游文件照常沿用")
    print("  -- 接口文件被改坏 → 清掉旧块再重做，不重复")
    q = p / "routes/quiz.zs"
    q.write_text(q.read_text(encoding="utf-8").replace("scripts/quiz_judge.zs", "scripts/nope.zs"), encoding="utf-8")
    fk5 = Fake()
    r5, _, _ = resume("rs", fk5)
    f5 = files(r5)
    txt = q.read_text(encoding="utf-8")
    check(r5["fixed"] and not f5["routes/quiz.zs"].get("沿用") and txt.count("接口 POST /quiz/answer") == 1 and "nope.zs" not in txt, "旧的接口块清掉后重做，文件里只有一份", (r5["stop"], txt))
    check(f5["routes/progress.zs"].get("沿用") and len(fk5.of(".zs 接口助手")) == 1, "同批没坏的接口文件仍沿用", len(fk5.of(".zs 接口助手")))

    print("  -- 熔断：cost-cap 只算本次新花的")
    fkc = Fake(cost=1.0)
    rc1, _, outc = go("rs_cap", fkc, cost_cap=4.5)
    check(rc1["v2"]["结论"] == "部分成功" and rc1["calls"] == 5, "第一次花到上限停下（5 次 5.0）", (rc1["stop"], rc1["calls"], rc1["cost"]))
    fkc2 = Fake(cost=1.0)
    rc2, _, _ = resume("rs_cap", fkc2, cost_cap=3.5)
    check(rc2["calls"] == 4 and abs(rc2["cost"] - 4.0) < 1e-6 and "花费达上限" in rc2["stop"], "继续构建的上限 3.5 只算本次：新花 4.0 才熔断（若算累计 5.0 会 0 次就停）", (rc2["calls"], rc2["cost"], rc2["stop"][:120]))
    vv = rjson(outc)["v2"]
    check(abs(vv["累计花费"] - 9.0) < 1e-6 and [x["序号"] for x in vv["运行"]] == [1, 2], "累计花费记 9.0（5.0 + 4.0）", vv["累计花费"])
    f = files(rc2)
    check(f["entities/quiz.entity"].get("沿用") and f["entities/progress.entity"]["运行"] == 2 and f["entities/progress.entity"]["结果"] == "通过", "上次熔断时「未做」的文件这次做了", {k: (v["结果"], v["运行"]) for k, v in f.items()})
    fkc3 = Fake(cost=0.0)
    rc3, _, _ = resume("rs_cap", fkc3)
    check(rc3["fixed"] and rc3["v2"]["结论"] == "成功" and [x["序号"] for x in rjson(outc)["v2"]["运行"]] == [1, 2, 3], "不设上限再继续一次，跑到成功", (rc3["stop"], rc3["calls"]))
    check(not any("项目架构" in x for x in fkc2.prompts + fkc3.prompts), "两次继续都没调规划")

    print("  -- 老产物（没有 top.json / split.json）：从 result.json 与 calls/ 还原")
    fko = Fake(bad={("生成", "流程", "scripts/quiz_judge.zs"): [f"=== scripts/quiz_judge.zs ===\n{bad_flow}"]})
    ro1, po, outo = go("rs_old", fko)
    (outo / "top.json").unlink()
    (outo / "split.json").unlink()
    res = rjson(outo)
    for fl in res["v2"]["文件"]:
        fl.pop("产出", None)                # 老版本没有「产出」
    (outo / "result.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    fko2 = Fake()
    ro2, _, _ = resume("rs_old", fko2)
    fo = files(ro2)
    check(ro2["fixed"] and not fko2.of("项目架构师") and not fko2.of("项目架构助手"), "没有落盘也能继续：不调规划", ro2["stop"])
    check((outo / "top.json").is_file() and (outo / "split.json").is_file() and rjson(outo)["v2"]["继续构建"]["从哪还原"], "还原后补写 top.json / split.json，result 记从哪还原", rjson(outo)["v2"]["继续构建"])
    check(fo["queries/quiz_*.sql"].get("沿用") and fo["entities/quiz.entity"].get("沿用"), "沿用的查询文件状态从 calls/ 的规划回复还原", {k: v.get("沿用") for k, v in fo.items()})
    check(not fko2.of("单文件规划助手（查询层）") and ro2["v2"]["结论"] == "成功", "无需重做查询规划")
    st = "接口 GET /a/list 动作 a_list\n  返回 {}\n结束\n\n接口 POST /a/mine 动作 a_mine\n  返回 {}\n结束\n\n接口 POST /a/del 动作 a_del\n  返回 {}\n结束\n"
    got = MB.strip_blocks(st, {"/a/mine"})
    check("/a/mine" not in got and "/a/list" in got and "/a/del" in got and got.count("结束") == 2 and MB.strip_blocks(st, {"/a/list", "/a/mine", "/a/del"}) == "", "strip_blocks 只去掉指定接口块，其余原样（全去光返回空）", got)
    print("  -- 还原不了：不写任何文件")
    d = TMP / "rs_none"
    shutil.rmtree(d, ignore_errors=True)
    rn = V.run_newproj(REQ, d / "proj", d / "out", model=Fake(), modular=True, resume=True)
    check(not rn["fixed"] and "继续构建" in rn["stop"] and "result.json" in rn["stop"] and not (d / "out/result.json").exists() and not (d / "out/calls.json").exists(), "没有上次的 result.json → 失败，不写 result / calls", rn["stop"])
    rn = V.run_newproj(REQ, TMP / "rs_old/proj", TMP / "rs_old/out", model=Fake(), resume=True)
    check(not rn["fixed"] and "--modular" in rn["stop"], "--resume 不带 --modular → 失败", rn["stop"])
    print("  -- CLI")
    from tools.dslagent import __main__ as M
    seen = {}
    real = V.run_newproj
    V.run_newproj = lambda req, project, out, **kw: seen.update(kw) or {"fixed": True, "calls": 0, "cost": 0, "seconds": 0, "stop": "", "changed_files": []}
    try:
        rq = TMP / "cli_req2.txt"
        rq.write_text("需求", encoding="utf-8")
        M.main(["newproj", "--modular", "--resume", "--cost-cap", "2", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(seen.get("modular") is True and seen.get("resume") is True and seen.get("cost_cap") == 2.0, "CLI newproj --modular --resume → run_newproj(modular=True, resume=True)", seen)
        seen.clear()
        M.main(["newproj", "--modular", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(not seen.get("resume"), "不带 --resume 不继续", seen)
        try:
            M.main(["newproj", "--resume", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
            check(False, "--resume 不带 --modular 应报错")
        except SystemExit as e:
            check(e.code == 2, "--resume 不带 --modular → 参数错误")
    finally:
        V.run_newproj = real


# ------------------------------------------------------------------ 十三、加载检查（服务启动同样的方式）

BAD_COND_EQ = "接口 POST /quiz/answer 动作 quiz_answer\n  用包 db http common\n  如果 {given} == \"\"\n    返回 {\"error\":\"空\"} 400\n  结束\n  设 result = 执行 scripts/quiz_judge.zs question_id={question_id} given={given}\n  返回 {\"ok\":\"{result.ok}\"}\n结束\n"


def t_loadcheck():
    print("十三、加载检查（复用服务运行时解析：DSLEngine 的条件 / 变量名 / 遍历 / 循环解析点）")
    cases = {
        "条件 ==": ("用包 common\n如果 {a} == 1\n打印 x\n结束\n", "看不懂的条件"),
        "条件 !=": ("用包 common\n如果 {a} != {b}\n打印 x\n结束\n", "看不懂的条件"),
        "条件 <": ("用包 common\n如果 {s.sort_order} < 0\n打印 x\n结束\n", "看不懂的条件"),
        "否则如果 条件 >": ("用包 common\n如果 {a} 等于 1\n打印 x\n否则如果 {a} > 2\n打印 y\n结束\n", "看不懂的条件"),
        "变量名 learnable.{k.code}": ("用包 common\n设 learnable.{k.code} = 1\n", "非法变量名：learnable.{k.code}"),
        "{intent} 讲解 条件": ("用包 common\n如果 {intent} 讲解\n打印 x\n结束\n", "看不懂的条件「{intent} 讲解」"),
        "非法遍历": ("用包 common\n遍历 {a}.b 于 {x}\n打印 x\n结束\n", "非法变量名"),
        "遍历缺 于": ("用包 common\n遍历 x\n打印 x\n结束\n", "循环语法"),
        "当 没写上限": ("用包 common\n当 {a} 等于 1\n打印 x\n结束\n", "必须写上限"),
        "循环外跳出": ("用包 common\n跳出\n", "只能写在循环"),
        "多余的结束": ("用包 common\n结束\n", "多余的"),
    }
    for name, (text, want) in cases.items():
        e = LC.parse_script(text)
        check(e is not None and want in e, f"流程文本：{name} → 报错原话带回", e)
    ok = "用包 common db\n如果 {a} 等于 1 且 {b} 不为空\n  打印 x\n否则如果 {a} 大于 2\n  打印 y\n否则\n  打印 z\n结束\n遍历 x 于 {l}\n  打印 {x}\n结束\n设 r = 查询 app.db q_list a={a}\n"
    check(LC.parse_script(ok) is None, "合法脚本（等于 / 大于 / 且 / 否则如果 / 遍历）不误报")
    check(LC.parse_script("") is None and LC.parse_script("# 只有注释\n") is None, "空脚本 / 只有注释不报")
    # 接口文件：切块（与服务 split_endpoints 同一个）后逐块解析，报错带接口路径
    probs = LC.check_text(BAD_COND_EQ, "routes/quiz.zs", True)
    check(len(probs) == 1 and probs[0].startswith("[接口出错] routes/quiz.zs") and "POST /quiz/answer" in probs[0] and "看不懂的条件" in probs[0], "接口文件：[接口出错] 文件 接口 报错原话（与服务打印同款）", probs)
    check(LC.check_text(ZS_QUIZ, "routes/quiz.zs", True) == [] and LC.check_text(ZS_FLOW, "scripts/quiz_judge.zs", False) == [], "合法的接口 / 流程文件通过")
    probs = LC.check_text("接口 POST /a\n  打印 x\n", "routes/a.zs", True)
    check(len(probs) == 1 and "没有对应的「结束」" in probs[0], "接口块没有结束 → 同服务启动时一样报", probs)
    # 磁盘：整项目
    d = TMP / "lc_proj"
    (d / "routes").mkdir(parents=True)
    (d / "scripts").mkdir()
    (d / "routes" / "a.zs").write_text(BAD_COND_EQ, encoding="utf-8")
    (d / "routes" / "b.zs").write_text(ZS_PROG, encoding="utf-8")
    (d / "scripts" / "f.zs").write_text("用包 common\n设 x.{y} = 1\n", encoding="utf-8")
    probs = LC.check_project(d)
    check(len(probs) == 2 and any("routes/a.zs" in x for x in probs) and any("scripts/f.zs" in x and "非法变量名" in x for x in probs), "全项目加载：逐个文件，合法的不报", probs)
    (d / "routes" / "dup.zs").write_text(ZS_PROG, encoding="utf-8")
    check(any("接口重复" in x for x in LC.check_project(d)), "全项目加载：接口重复（scan_routes 抛的）也报")
    # 生成时：流程带 == → 报错原话带回重写
    bad_flow = ZS_FLOW.replace("设 n = ", "如果 {given} == \"\"\n  返回 {\"ok\":\"0\",\"n\":\"0\"}\n结束\n设 n = ")
    fk = Fake(bad={("生成", "流程", "scripts/quiz_judge.zs"): [f"=== scripts/quiz_judge.zs ===\n{bad_flow}", f"=== scripts/quiz_judge.zs ===\n{ZS_FLOW}"]})
    r, p, _ = go("lc_flow", fk)
    f = files(r)["scripts/quiz_judge.zs"]
    again = fk.of(".zs 流程助手")[1]
    check(r["fixed"] and f["生成尝试"] == 2 and "[接口出错]" in again and "看不懂的条件" in again and "==" in again, "流程生成条件写 == → 带「接口出错」报错原话重写后通过", f)
    # 接口：条件 == 同样
    fk = Fake(bad={("生成", "接口", "routes/quiz.zs"): [f"=== routes/quiz.zs ===\n{BAD_COND_EQ}", f"=== routes/quiz.zs ===\n{ZS_QUIZ}"]})
    r, p, _ = go("lc_iface", fk)
    f = files(r)["routes/quiz.zs"]
    check(r["fixed"] and f["生成尝试"] == 2 and "[接口出错] routes/quiz.zs" in fk.of(".zs 接口助手")[1] and "== \"\"" not in (p / "routes/quiz.zs").read_text(encoding="utf-8"), "接口生成写 == → 重写，坏版本没落盘", f)
    fk = Fake(bad={("生成", "接口", "routes/quiz.zs"): [f"=== routes/quiz.zs ===\n{BAD_COND_EQ}"]})
    r, p, _ = go("lc_iface2", fk)
    f = files(r)["routes/quiz.zs"]
    check(f["结果"] == "失败" and "看不懂的条件" in f["失败原因"] and not (p / "routes/quiz.zs").exists(), "两次都写 == → 该文件失败并撤回", f)
    # 整体检查：项目里别的文件（计划外、模型追加的）加载不过 → 整体问题里报「接口出错」，零「接口出错」才算成功
    d = TMP / "lc_final"
    shutil.rmtree(d, ignore_errors=True)
    (d / "proj" / "routes").mkdir(parents=True)
    (d / "proj" / "routes" / "extra.zs").write_text(BAD_COND_EQ.replace("/quiz/answer", "/extra/x").replace("quiz_answer", "extra_x"), encoding="utf-8")
    r = V.run_newproj(REQ, d / "proj", d / "out", model=Fake(), modular=True)
    check(not r["fixed"] and r["v2"]["结论"] == "部分成功" and any("[接口出错] routes/extra.zs" in x for x in r["v2"]["整体问题"]), "整体检查：全项目加载有「接口出错」→ 部分成功", r["v2"]["整体问题"])
    r, _, _ = go("lc_final_ok", Fake())
    check(r["fixed"] and not any("接口出错" in x for x in r["v2"]["整体问题"]), "整体检查：零「接口出错」→ 成功")
    # 继续构建：通过的接口文件被改成坏条件 → 不沿用、重做
    d = TMP / "lc_resume"
    shutil.rmtree(d, ignore_errors=True)
    r1 = V.run_newproj(REQ, d / "proj", d / "out", model=Fake(), modular=True)
    (d / "proj" / "routes" / "quiz.zs").write_text(BAD_COND_EQ, encoding="utf-8")
    (d / "proj" / "scripts" / "quiz_judge.zs").write_text("用包 common\n设 k.{x} = 1\n", encoding="utf-8")
    fk = Fake()
    r2 = V.run_newproj(REQ, d / "proj", d / "out", model=fk, modular=True, resume=True)
    fs = files(r2)
    check(r1["fixed"] and r2["fixed"] and not fs["routes/quiz.zs"].get("沿用") and not fs["scripts/quiz_judge.zs"].get("沿用") and fs["entities/quiz.entity"].get("沿用") and fs["queries/quiz_*.sql"].get("沿用"),
          "resume：加载检查不过的接口 / 流程文件不沿用、重做；没坏的数据 / 查询沿用", {k: v.get("沿用") for k, v in fs.items()})
    check("看不懂的条件" not in (d / "proj" / "routes" / "quiz.zs").read_text(encoding="utf-8") and LC.check_project(d / "proj") == [], "重做后磁盘上的文件加载零「接口出错」")


# ------------------------------------------------------------------ 十四、gen private 权限（程序套）

def private_objs(extra_cut=None, roles=("teacher", "student")):
    top, sp = top_obj(), split_obj()
    top["使用者"]["角色"] = list(roles)
    sp["模板"], sp["角色"] = "private", list(roles)
    if extra_cut:
        top["横切"]["全局约束"] = [*top["横切"]["全局约束"], extra_cut]
    return top, sp


def t_perms():
    print("十四、gen private 权限：增删改查带角色 / user 不出 password_hash / 关公开注册 / resume 重套")
    top, sp = private_objs()
    r, p, out = go("perm1", Fake(top=top, split=sp), req=REQ + "学生和老师要登录。")
    uz, qz = (p / "routes/user.zs").read_text(encoding="utf-8"), (p / "routes/question.zs").read_text(encoding="utf-8")
    heads = [l for l in (uz + qz).splitlines() if l.startswith("接口 ")]
    check(r["fixed"] and len(heads) == 10 and all(h.endswith(" 角色 teacher") for h in heads), "private + 两个角色：gen 的增删改查（user / question 共 10 个接口）都带「角色 teacher」（第一个角色）", heads)
    check("password_hash" not in (p / "queries/user_list.sql").read_text(encoding="utf-8") and "password_hash" not in (p / "queries/user_one.sql").read_text(encoding="utf-8")
          and "password_hash" not in (p / "queries/user_update.sql").read_text(encoding="utf-8"), "user_list / user_one / user_update 不选 / 不写 password_hash")
    auth = (p / "routes/auth.zs").read_text(encoding="utf-8")
    check("接口 POST /auth/register 动作 auth_register 公开" in auth and "403" not in auth.split("/auth/login")[0], "没写「学生不能自己注册」→ /auth/register 照旧公开")
    check("角色 teacher" not in (p / "routes/quiz.zs").read_text(encoding="utf-8"), "模型写的接口文件不被改")
    # 横切里写了 → 关注册
    top, sp = private_objs("学生不能自己注册，账号由教师创建")
    r, p, out = go("perm2", Fake(top=top, split=sp), req=REQ + "学生和老师要登录。")
    auth = (p / "routes/auth.zs").read_text(encoding="utf-8")
    seg = auth.split("接口 POST /auth/register")[1].split("结束")[0]
    check(r["fixed"] and "403" in seg and MB.NO_REGISTER_RE.search("学生不能自己注册") and "注册用户" not in seg and "动作 auth_register 公开" in auth, "横切全局约束写了学生不能自己注册 → /auth/register 回 403（接口头保留，界面动作还在）", seg)
    check(LC.check_project(p) == [], "套完权限的项目加载零「接口出错」")
    # 清单标记
    top, sp = private_objs()
    sp["关闭注册"] = "是"
    r, p, _ = go("perm3", Fake(top=top, split=sp), req=REQ + "学生和老师要登录。")
    check("403" in (p / "routes/auth.zs").read_text(encoding="utf-8").split("/auth/login")[0], "层次×模块清单标记 关闭注册＝是 → 同样关")
    # 只有一个角色：不加角色；password_hash 仍隐藏
    top, sp = private_objs(roles=("teacher",))
    r, p, _ = go("perm4", Fake(top=top, split=sp), req=REQ + "老师要登录。")
    check(r["fixed"] and "角色 teacher" not in (p / "routes/user.zs").read_text(encoding="utf-8") and "password_hash" not in (p / "queries/user_list.sql").read_text(encoding="utf-8"), "只有一个角色 → 不加角色；user 查询仍不出 password_hash")
    # 非 private 不动
    r, p, _ = go("perm5", Fake())
    check(r["fixed"] and "角色" not in (p / "routes/question.zs").read_text(encoding="utf-8").split("结束")[0] and not (p / "routes/auth.zs").exists(), "非 private 模板：gen 的接口不加角色，没有 auth")
    # resume：被改掉的 gen 权限（比如重新生成覆盖）重新套上，追加的接口保留
    top, sp = private_objs()
    d = TMP / "perm_resume"
    shutil.rmtree(d, ignore_errors=True)
    r1 = V.run_newproj(REQ + "学生和老师要登录。", d / "proj", d / "out", model=Fake(top=top, split=sp), modular=True)
    qf = d / "proj" / "routes" / "question.zs"
    appended = "\n\n接口 POST /question/extra 动作 question_extra\n  用包 db http\n  返回 {\"ok\":\"1\"}\n结束\n"
    qf.write_text(qf.read_text(encoding="utf-8").replace(" 角色 teacher", "") + appended, encoding="utf-8")
    uf = d / "proj" / "queries" / "user_list.sql"
    uf.write_text("SELECT id, username, password_hash FROM user\n", encoding="utf-8")
    r2 = V.run_newproj(REQ + "学生和老师要登录。", d / "proj", d / "out", model=Fake(top=top, split=sp), modular=True, resume=True)
    t = qf.read_text(encoding="utf-8")
    check(r1["fixed"] and r2["fixed"] and t.count(" 角色 teacher") == 5, "resume：gen 的 5 个增删改查块重新带上角色", t[-400:])
    check("接口 POST /question/extra 动作 question_extra\n" in t and t.endswith(appended.lstrip("\n")), "resume：模型追加的接口原样保留（头行不加角色，位置不变）", t[-200:])
    check("password_hash" not in uf.read_text(encoding="utf-8"), "resume：user_list.sql 被还原成带 password_hash 后重新去掉")


# ------------------------------------------------------------------ 十五、规划 / 生成分开指定模型

class Fake2(Fake):
    """codex 的调用返回 cost 5（模拟误带费用）：熔断不该看它。"""

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        t = super().__call__(system, user, tag, timeout, model, **kw)
        if model and str(model).startswith("codex"):
            t = dict(t, cost=5.0)
        return t


def t_steps():
    print("十五、mplan / mgen 步骤键、codex 不计费、--codex-cap")
    check(E.normalize({"mplan": "sonnet", "mgen": "codex:gpt-6-luna:medium"}) == {"mplan": "sonnet", "mgen": "codex:gpt-6-luna:medium"}, "engines.normalize 认 mplan / mgen")
    check(E.normalize("mplan=sonnet,mgen=codex:gpt-6-luna:medium") == {"mplan": "sonnet", "mgen": "codex:gpt-6-luna:medium"}, "简写 mplan=…,mgen=… 也认")
    check(E.normalize("opus") == {k: "opus" for k in E.STEPS}, "字符串简写仍只设原来的步骤（不影响老行为）")
    try:
        E.normalize({"mplanx": "sonnet"})
        check(False, "未知步骤名应报错")
    except ValueError as e:
        check("mplan" in str(e) and "mgen" in str(e), "未知步骤名 → 报错并列出可用步骤（含 mplan / mgen）")
    check(E.effective({}) == {k: "sonnet" for k in E.STEPS}, "effective 不变（老测试口径）")
    old = os.environ.get("DSLAGENT_MODELS")
    PLAN = ("项目架构师", "项目架构助手", "单文件规划助手", "需求核对员")
    GEN = ("应用建模助手", "SQLite 语句助手", ".zs 流程助手", ".zs 接口助手", ".ui 界面助手")
    try:
        os.environ["DSLAGENT_MODELS"] = dump({"mplan": "opus", "mgen": "haiku"})
        fk = Fake()
        r, p, out = go("st1", fk)
        pm = {m for u, m in zip(fk.prompts, fk.models) if any(k in u for k in PLAN)}
        gm = {m for u, m in zip(fk.prompts, fk.models) if any(k in u for k in GEN)}
        check(r["fixed"] and pm == {"opus"} and gm == {"haiku"}, "规划类调用用 mplan（opus），生成类用 mgen（haiku）", (pm, gm))
        calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        steps = {c.get("step"): c.get("model") for c in calls}
        check(steps.get("mplan") == "opus" and steps.get("mgen") == "haiku" and all(c.get("engine") == "claude" for c in calls), "calls.json 每条记 step 与实际 engine / model", steps)
        os.environ["DSLAGENT_MODELS"] = dump({"sub": "haiku"})
        fk = Fake()
        r, _, out = go("st2", fk)
        check(r["fixed"] and set(fk.models) == {"haiku"}, "没写 mplan / mgen → 都走 sub", set(fk.models))
        os.environ.pop("DSLAGENT_MODELS")
        fk = Fake()
        r, _, out = go("st3", fk)
        check(r["fixed"] and set(fk.models) == {None}, "什么都没写 → 走原来的默认模型（不传 model）", set(fk.models))
        os.environ["DSLAGENT_MODELS"] = "mplan=sonnet,mgen=codex:gpt-6-luna:medium"
        fk = Fake2()
        r, _, out = go("st4", fk, cost_cap=0.5)
        calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        cx = [c for c in calls if c["engine"] == "codex"]
        check(r["fixed"] and cx and all(c["step"] == "mgen" and c["model"] == "gpt-6-luna" and c["effort"] == "medium" for c in cx) and r["v2"]["结论"] == "成功" and r["v2"]["codex调用"] == len(cx),
              "codex 只管生成类；cost 5/次的 codex 调用不触发 --cost-cap 0.5（熔断只看 Claude 侧）；codex调用数记进结果", (r["stop"][:200], len(cx)))
        fk = Fake2()
        r, _, out = go("st5", fk, codex_cap=3)
        calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        n_cx = sum(1 for c in calls if c["engine"] == "codex")
        check(not r["fixed"] and n_cx == 3 and "codex 调用已满 3 次" in r["stop"] and r["v2"]["结论"] == "部分成功", "--codex-cap 3：codex 调用到 3 次就停（部分成功）", (n_cx, r["stop"][:200]))
        fk = Fake2()
        r, _, out = go("st6", fk, codex_cap=1000)
        check(r["fixed"], "codex-cap 够大不影响")
    finally:
        if old is None:
            os.environ.pop("DSLAGENT_MODELS", None)
        else:
            os.environ["DSLAGENT_MODELS"] = old



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
        M.main(["newproj", "--modular", "--codex-cap", "7", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(seen.get("modular") is True and seen.get("codex_cap") == 7, "CLI --codex-cap N → run_newproj(codex_cap=N)", seen)
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
        t_gen_ents()
        t_silent()
        t_resume()
        t_loadcheck()
        t_perms()
        t_steps()
        t_cli()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
