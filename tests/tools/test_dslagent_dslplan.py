# -*- coding: utf-8 -*-
"""modular：规划产出改用 DSL 写（plandsl.py 规划文件 plan/top.zs、plan/layers.zs；skeleton.py 约定骨架文件）。不调真模型。

    .venv/bin/python tests/tools/test_dslagent_dslplan.py

一、规划文件解析：正常 / 各种报错带行号与原行 / 与 JSON 解析结果等价 / 渲染回读
二、骨架解析：四类文件的约定提取、`#@` 行被引擎忽略（真加载 + 真调用）、校验规则全部用骨架跑通
三、冻结与比对：快照、约定部分被改动被拒、占位没换被拒
四、填骨架全流程（假模型）：规划文件落盘、骨架先落盘、实现换掉占位、继续构建读快照、手改规划文件
"""
import copy
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_dslagent_modbuild as TM      # noqa: E402
import test_dslagent_contract as TC      # noqa: E402
from tools.dslagent import contract as C, modbuild as MB, plandsl as PD, skeleton as SK, trial as TR, v2 as V      # noqa: E402

PASS = FAIL = 0
dump = TM.dump


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  ✓ " if cond else "  ✗ ") + msg + ("" if cond or extra == "" else f"\n      {str(extra)[:1500]}"))


def ln(text, needle):
    """needle 所在行的行号（1 起）。"""
    return next(i for i, l in enumerate(text.splitlines(), 1) if needle in l)


def perr(fn, text):
    try:
        fn(text)
        return ""
    except PD.PlanError as e:
        return str(e)


TOP_DSL = """# 顶层规划
项目 让学生做题、看掌握进度
  使用者 teacher student 多人
  横切 账号 private 模板，学生不能自己注册，账号由教师创建
  横切 调模型 common 开放题讲解
  横切 后台任务 每晚汇总
  横切 导入 题库从 jsonl 导入
  约束 老库只加表加列
结束
模块 quiz 题库、出题、判题
模块 progress 掌握进度统计 依赖 quiz
共用流程 quiz_judge 归 quiz 用于 progress
主流程 学生做题 student 经过 quiz progress
  步骤 选课 做题 交答案
  步骤 看进度
结束
主流程 老师看全班 - 经过 progress
  步骤 看全班进度
结束
构建顺序 quiz progress
"""

LAYERS_DSL = """模板 full
层 数据 实体
层 查询 sql
约束 老库只加表加列
模块 quiz
  规则 交答案时按库里记的题判对错
  规则 看进度时按得分算掌握
  数据 question attempt
  流程 quiz_judge 用于 quiz progress 作用 判题写记录，用于 之类的词不碍事
  接口 quiz 交答案
  界面 quiz_page 答题页
  能力 db http common
  缺口 待补 事 语音朗读
  缺口 sql 动词 写库表 事 题目选项打乱
结束
"""


def t_plan():
    print("一、规划文件解析")
    o = PD.parse_top(TOP_DSL)
    check(o["目标"] == "让学生做题、看掌握进度" and o["使用者"] == {"角色": ["teacher", "student"], "人数": "多人"} and [m["名"] for m in o["模块"]] == ["quiz", "progress"]
          and o["模块"][1]["依赖"] == ["quiz"] and o["模块"][0]["说明"] == "题库、出题、判题" and o["共用流程"] == [{"流程名": "quiz_judge", "归属模块": "quiz", "被用于": ["progress"]}], "顶层：项目块 / 模块 / 依赖 / 共用流程", o)
    check(o["主流程"][0]["步骤"] == ["选课", "做题", "交答案", "看进度"] and o["主流程"][1]["角色"] == "" and o["横切"]["调模型"] == [{"处": "开放题讲解", "包": "common"}]
          and o["横切"]["后台任务"] == ["每晚汇总"] and o["横切"]["内容数据导入"] == "题库从 jsonl 导入" and o["横切"]["全局约束"] == ["老库只加表加列"] and o["构建顺序"] == ["quiz", "progress"],
          "顶层：主流程步骤可多行、角色 - = 不限、横切各项、构建顺序")
    check(PD.parse_top("```\n" + TOP_DSL + "```") == o, "围栏包着也能读；# 整行注释忽略")
    r = MB.validate_top(o, TM.PACKS)
    check(r["ok"] and r["top"]["横切"]["账号与权限"].startswith("private 模板"), "解析结果交给 validate_top 校验通过", r["errors"])
    # 与 JSON 路径等价
    jt = MB.validate_top(dump(TM.top_obj()), TM.PACKS)["top"]
    dt = MB.validate_top(PD.parse_top(PD.render_top(TM.top_obj())), TM.PACKS)["top"]
    check(jt == dt, "同一份顶层规划：DSL 解析校验结果 == JSON 解析校验结果", (jt, dt))
    js = MB.validate_split(dump(TM.split_obj()), jt, TM.CAPS)["split"]
    ds = MB.validate_split(PD.parse_layers(PD.render_layers(TM.split_obj())), jt, TM.CAPS)["split"]
    check(js == ds, "同一份层次×模块：DSL 解析校验结果 == JSON 解析校验结果")
    check(MB.validate_split(PD.parse_layers(PD.render_layers(js)), jt, TM.CAPS)["split"] == js and PD.parse_top(PD.render_top(jt)) == PD.parse_top(PD.render_top(PD.parse_top(PD.render_top(jt)))),
          "规范化后的 split 渲染成 DSL 再读回，校验结果不变（from-plan 转换靠它）")
    # 报错带行号与原行
    e = perr(PD.parse_top, TOP_DSL.replace("模块 progress", "模快 progress"))
    check(f"plan/top.zs 第 {ln(TOP_DSL, '模块 progress')} 行" in e and "「模快 progress 掌握进度统计 依赖 quiz」" in e and "不认识的关键字" in e, "未知关键字：报行号 + 原行", e)
    e = perr(PD.parse_top, TOP_DSL.replace("  使用者 teacher student 多人", "  使用者 teacher student"))
    check(f"第 {ln(TOP_DSL, '使用者')} 行" in e and "最后一项要是 单人 或 多人" in e, "使用者缺人数", e)
    e = perr(PD.parse_top, TOP_DSL.replace("结束\n模块 quiz", "模块 quiz", 1))
    check("项目块没有「结束」" in e or "项目块里只能写" in e, "项目块没收尾 → 报错", e)
    e = perr(PD.parse_top, TOP_DSL.replace("  横切 导入 题库从 jsonl 导入", "  横切 乱写 x"))
    check(f"第 {ln(TOP_DSL, '导入')} 行" in e and "横切 后面只能是" in e, "横切后面写错", e)
    e = perr(PD.parse_top, TOP_DSL + "结束\n")
    check("多余的「结束」" in e and f"第 {len(TOP_DSL.splitlines()) + 1} 行" in e, "多余的结束", e)
    e = perr(PD.parse_top, TOP_DSL.replace("共用流程 quiz_judge 归 quiz 用于 progress", "共用流程 quiz_judge quiz progress"))
    check("共用流程 写法" in e and f"第 {ln(TOP_DSL, '共用流程')} 行" in e, "共用流程缺 归", e)
    e = perr(PD.parse_top, TOP_DSL.replace("主流程 学生做题 student 经过 quiz progress", "主流程 学生做题 student quiz progress"))
    check("主流程 写法" in e, "主流程缺 经过", e)
    e = perr(PD.parse_top, TOP_DSL.replace("构建顺序 quiz progress\n", ""))
    check("缺少「构建顺序" in e, "缺构建顺序", e)
    e = perr(PD.parse_top, "构建顺序 a\n")
    check("缺少「项目" in e, "缺项目块", e)
    e = perr(PD.parse_top, TOP_DSL.replace("  步骤 看全班进度", "  经过 x"))
    check("主流程块里只能写 步骤" in e, "主流程块里写了别的", e)
    # 语义错误仍由 validate_top 报（DSL 解析只管语法）
    o2 = PD.parse_top(TOP_DSL.replace("模块 quiz 题库、出题、判题", "模块 quiz 题库、出题、判题 依赖 progress"))
    r = MB.validate_top(o2, TM.PACKS)
    check(not r["ok"] and any("依赖成环" in x for x in r["errors"]), "语法对、语义错（依赖成环）→ validate_top 报", r["errors"])
    # layers
    lo = PD.parse_layers(LAYERS_DSL)
    q = lo["模块"][0]
    check(lo["模板"] == "full" and lo["层"] == {"数据": "实体", "查询": "sql"} and lo["全局约束"] == ["老库只加表加列"] and q["规则"] == ["交答案时按库里记的题判对错", "看进度时按得分算掌握"]
          and q["数据"] == ["question", "attempt"] and q["能力"] == ["db", "http", "common"], "层次：模板 / 层 / 约束 / 规则每行一条 / 数据 / 能力", lo)
    check(q["流程"] == [{"名": "quiz_judge", "作用": "判题写记录，用于 之类的词不碍事", "用于": ["quiz", "progress"], "调流程": []}] and q["接口"] == [{"文件": "quiz", "作用": "交答案"}]
          and q["界面"] == [{"名": "quiz_page", "作用": "答题页"}] and q["缺口"] == [{"事": "语音朗读", "办法": "待补", "用动词": []}, {"事": "题目选项打乱", "办法": "sql", "用动词": ["写库表"]}],
          "层次：流程（作用写最后）/ 接口 / 界面 / 缺口（动词 + 事）")
    e = perr(PD.parse_layers, LAYERS_DSL.replace("模板 full\n", ""))
    check("缺少「模板" in e, "layers 缺模板", e)
    e = perr(PD.parse_layers, LAYERS_DSL.replace("缺口 待补 事 语音朗读", "缺口 待补 语音朗读"))
    check(f"第 {ln(LAYERS_DSL, '缺口 待补')} 行" in e and "缺口 写法" in e and "「缺口 待补 语音朗读」" in e, "缺口缺 事", e)
    e = perr(PD.parse_layers, LAYERS_DSL.replace("  能力 db http common", "  乱写 x"))
    check("模块块里只能写" in e and f"第 {ln(LAYERS_DSL, '能力')} 行" in e, "模块块里写了别的", e)
    e = perr(PD.parse_layers, LAYERS_DSL.replace("模块 quiz\n", "模块 quiz 多余\n"))
    check("模块 后面只写模块名" in e, "模块行多写了东西", e)
    e = perr(PD.parse_layers, LAYERS_DSL.rstrip("\n").rsplit("\n", 1)[0] + "\n")
    check("没有「结束」" in e, "模块块没收尾", e)
    check(perr(PD.parse_layers, LAYERS_DSL.replace("流程 quiz_judge 用于", "流程 quiz_judge 作用 x 用于 y").replace("，用于 之类的词不碍事", "")) == "", "流程行里 作用 之后的词全算作用文字")
    # 提示词
    pr = ROOT / "tools/dslagent/packs/newproj/prompts"
    for n, kw in (("top", "共用流程"), ("split", "缺口")):
        t = (pr / f"sys_m{n}.md").read_text(encoding="utf-8")
        ex = t.split("```")[1]
        check("完整示例" in t and kw in ex and ("plan/top.zs" if n == "top" else "plan/layers.zs") in t, f"sys_m{n}.md：语法说明 + 完整示例")
        (PD.parse_top if n == "top" else PD.parse_layers)(ex)
        check(True, f"sys_m{n}.md 里的示例本身能被解析器读通")


def sk_text(o):
    return TC.skeleton_text(o)


def extract_all(text):
    files, e1 = SK.split_files(text)
    obj, e2 = SK.extract(files)
    return files, obj, e1 + e2


def t_skeleton():
    print("二、骨架解析")
    o = TC.contract_obj("quiz")
    files, obj, errs = extract_all(sk_text(o))
    check(not errs and set(files) == {"queries/quiz_log.sql", "scripts/quiz_judge.zs", "routes/quiz.zs", "ui/quiz_page.ui"}, "四类骨架文件都落在真实路径上", (list(files), errs))
    v_dict = C.validate_contract(o, TC.uctx("quiz"))["contract"]
    v_skel = C.validate_contract(obj, TC.uctx("quiz"))
    check(v_skel["ok"] and v_skel["contract"] == v_dict, "骨架提取出的约定 == 现在 contracts.json 的内容（同一份约定，dict 与骨架两条路校验结果一致）", v_skel["errors"])
    sq = files["queries/quiz_log.sql"]
    check(sq.splitlines()[0] == "-- 参数: question_id 必填, given 必填" and "-- 返回: 写入" in sq and "-- 作用: 写作答记录" in sq and sq.rstrip().endswith("-- 待实现"), "sql 骨架：头部固定格式注释 + 正文 -- 待实现", sq)
    fl = files["scripts/quiz_judge.zs"]
    check("#@ 入参 question_id given" in fl and "#@ 出参 ok n" in fl and "#@ 写 attempt" in fl and "#@ 调用 sql quiz_log question_id=… given=…" in fl and "#@ 动词 写库表" in fl and "#@ 错误 " in fl and fl.rstrip().endswith('返回 {"error":"未实现"}'),
          "流程骨架：#@ 入参 / 出参 / 写 / 调用 / 动词 / 错误 + 一行占位", fl)
    rt = files["routes/quiz.zs"]
    check(rt.startswith("接口 POST /quiz/answer 动作 quiz_answer\n") and "  #@ 请求 question_id given" in rt and "  #@ 调用 scripts/quiz_judge.zs question_id=… given=…" in rt and "  #@ 响应 state.ok" in rt
          and "  #@ 错误 404 题目不存在" in rt and '  返回 {"error":"未实现"} 501' in rt and rt.rstrip().endswith("结束"), "接口骨架：真实头行 + #@ 请求 / 调用 / 响应 / 错误 + 占位 + 结束", rt)
    ui = files["ui/quiz_page.ui"]
    check(ui.startswith("#@ 用接口 /quiz/answer\n#@ 字段 given\n") and "界面 自定义 quiz_page" in ui, "界面骨架：#@ 用接口 / 字段 + 最小页面", ui)
    # 可选参数两种写法、响应、messages
    o2 = TC.contract_obj("quiz", lambda x: [x["sql"][0].update(参数=TC.Pm("question_id", "given", opt=["given"])), x["接口"][0]["响应"].update(messages="是", lists=["opts"])])
    o2["流程"][0]["调"][0]["给"] = ["question_id"]
    _, ob2, e2 = extract_all(sk_text(o2))
    r2 = C.validate_contract(ob2, TC.uctx("quiz"))
    check(not e2 and r2["ok"] and r2["contract"]["sql"][0]["参数"][1] == {"名": "given", "要求": "可选"} and r2["contract"]["接口"][0]["响应"] == {"state": ["ok"], "lists": ["opts"], "messages": "是"}, "可选参数（必填 / 可选）、响应 lists / messages 解析", (e2, r2["errors"]))
    o3 = TC.contract_obj("quiz", lambda x: x["流程"][0].update(入参=TC.Pm("question_id", "given", "level", opt=["level"])))
    t3 = sk_text(o3)
    check("#@ 入参 question_id given level?" in t3 and C.validate_contract(extract_all(t3)[1], TC.uctx("quiz"))["ok"], "流程入参 level? = 可选")
    # 解析报错带文件与行
    t = sk_text(o).replace("接口 POST /quiz/answer 动作 quiz_answer", "接口 GET /quiz/answer 动作 quiz_answer")
    check(any("方法一律 POST" in x and "routes/quiz.zs 第 1 行" in x for x in extract_all(t)[2]), "接口头行方法不是 POST → 报行号与原行", extract_all(t)[2])
    t = sk_text(o).replace("接口 POST /quiz/answer 动作 quiz_answer", "接口 POST /quiz/answer")
    check(any("接口头行要写成" in x for x in extract_all(t)[2]), "接口头行缺动作名", extract_all(t)[2])
    t = sk_text(o).replace("-- 返回: 写入\n", "")
    check(any("缺 `-- 返回: …`" in x for x in extract_all(t)[2]), "sql 头部缺返回行", extract_all(t)[2])
    t = sk_text(o).replace("#@ 出参 ok n\n", "")
    check(any("缺 `#@ 出参" in x for x in extract_all(t)[2]), "流程缺出参行", extract_all(t)[2])
    t = sk_text(o).replace("  #@ 请求 question_id given\n", "")
    check(any("缺 `#@ 请求" in x for x in extract_all(t)[2]), "接口缺请求行", extract_all(t)[2])
    t = sk_text(o).replace("#@ 调用 sql quiz_log", "#@ 调用 quiz_log")
    check(any("调用 要写成" in x for x in extract_all(t)[2]), "调用写法不对", extract_all(t)[2])
    t = sk_text(o).replace("=== ui/quiz_page.ui ===", "=== docs/quiz_page.md ===")
    check(any("文件路径「docs/quiz_page.md」不对" in x for x in extract_all(t)[2]), "路径不在四类目录 → 报")
    check(SK.split_files("没有分隔块")[1] and any("写了两遍" in x for x in SK.split_files("=== a ===\nx\n=== a ===\ny\n")[1]), "没有 === 路径 === 块 / 同一文件写两遍 → 报")


def vs(m, edit, **over):
    """骨架文本上直接改（模型会犯的错），再解析 + 校验。返回 (解析错误, validate 结果)。"""
    base = sk_text(TC.contract_obj(m))
    text = edit(base)
    _f, obj, errs = extract_all(text)
    if errs:
        return errs, {"ok": False, "errors": []}
    return [], C.validate_contract(obj, TC.uctx(m, **over))


def t_rules_on_skeleton():
    print("   -- 约定校验规则全部用骨架跑通")

    def bad(m, edit, want, msg, **over):
        pe, r = vs(m, edit, **over)
        ok = any(want in x for x in pe + r["errors"])
        check(ok and not r["ok"], msg, (pe, r["errors"]))
    bad("quiz", lambda t: t.replace("-- 用列: attempt.question_id attempt.given", "-- 用列: attempt.nope"), "没有列「nope」", "引用不存在：sql 用列不在实体里 → 拒")
    bad("quiz", lambda t: t.replace("-- 表: attempt", "-- 表: ghost"), "表「ghost」", "引用不存在：sql 的表 → 拒")
    bad("quiz", lambda t: t.replace("#@ 调用 sql quiz_log question_id=… given=…", "#@ 调用 sql ghost_sql"), "「ghost_sql」不存在", "引用不存在：流程调的 sql → 拒")
    bad("quiz", lambda t: t.replace("#@ 用接口 /quiz/answer", "#@ 用接口 /nope"), "用的接口「/nope」不存在", "引用不存在：界面用的接口 → 拒")
    bad("quiz", lambda t: t.replace("#@ 调用 scripts/quiz_judge.zs question_id=… given=…", "#@ 调用 scripts/quiz_judge.zs question_id=…"), "缺必填参数 ['given']", "参数不覆盖：接口少给必填 → 拒")
    bad("quiz", lambda t: t.replace("#@ 调用 scripts/quiz_judge.zs question_id=… given=…", "#@ 调用 scripts/quiz_judge.zs question_id=… given=… zz=…"), "多给了它没约定的键 ['zz']", "参数多给 → 拒")
    bad("quiz", lambda t: t.replace("#@ 调用 sql quiz_log question_id=… given=…", "#@ 调用 sql quiz_log question_id=…"), "缺必填参数 ['given']", "参数不覆盖：流程少给 sql 必填 → 拒")
    bad("quiz", lambda t: t.replace("  #@ 调用 scripts/quiz_judge.zs question_id=… given=…\n", "  #@ 调用 scripts/quiz_judge.zs question_id=… given=…\n  #@ 调用 sql attempt_insert question_id=…\n"), "缺必填参数", "参数不覆盖：调 gen 自带 sql 同样核对 → 拒")
    bad("quiz", lambda t: t.replace("#@ 调用 sql quiz_log question_id=… given=…", "#@ 调用 sql quiz_log question_id=… given=…\n#@ 调用 scripts/quiz_judge.zs question_id=… given=…"), "成环", "流程调自己 → 成环，拒")
    bad("quiz", lambda t: t.replace("#@ 调用 sql quiz_log question_id=… given=…", "#@ 调用 sql quiz_log question_id=… given=…\n#@ 调用 scripts//quiz/answer.zs"), "越层", "越层：流程调接口 → 拒")
    bad("progress", lambda t: t.replace("  #@ 调用 scripts/quiz_judge.zs question_id=… given=…", "  #@ 调用 scripts/quiz_judge.zs question_id=… given=…"), "别的模块的流程「quiz_judge」", "非法跨模块：顶层没规定给本模块用 → 拒", flows_ext={})
    bad("quiz", lambda t: t.replace("#@ 动词 写库表", "#@ 动词 魔法写入"), "「魔法写入」不在能力清单里", "未知动词 → 拒")
    bad("quiz", lambda t: re.sub(r"(#@ 规则 R1|-- 规则: R1)", lambda m: m.group(1).replace("R1", "") if False else ("-- 规则: 无" if m.group(1).startswith("--") else "#@ 规则"), t), "规则 R1 没有落在任何约定项上", "规则未落地 → 拒")
    bad("quiz", lambda t: t.replace("-- 规则: R1", "-- 规则: R9"), "不是分给本模块的规则", "规则号不是本模块的 → 拒")
    bad("quiz", lambda t: t.replace("=== scripts/quiz_judge.zs ===", "=== scripts/extra_flow.zs ==="), "不在层次×模块给本模块定的流程里", "多出流程 → 拒")
    bad("quiz", lambda t: t.replace("=== routes/quiz.zs ===", "=== routes/other.zs ==="), "不在层次×模块给本模块定的接口文件里", "接口文件不在计划里 → 拒")
    bad("quiz", lambda t: t.replace("=== queries/quiz_log.sql ===", "=== queries/log_x.sql ==="), "要以「quiz_」开头", "sql 名没带模块前缀 → 拒")
    bad("quiz", lambda t: t.replace("=== queries/quiz_log.sql ===", "=== queries/attempt_list.sql ==="), "gen 自动生成的重名", "sql 与 gen 重名 → 拒")
    bad("quiz", lambda t: t.replace("角色 student", "角色 student") if False else t.replace("接口 POST /quiz/answer 动作 quiz_answer", "接口 POST /quiz/answer 动作 quiz_answer 角色 admin"), "不在项目角色", "角色不在项目角色里 → 拒")
    bad("quiz", lambda t: t, "已被占用", "接口路径与已有重复 → 拒", taken_paths={"/quiz/answer"})
    bad("quiz", lambda t: t.replace("  #@ 错误 404 题目不存在", "  #@ 错误 500 x"), "要是 4xx", "业务错误码不是 4xx → 拒")
    bad("quiz", lambda t: t.replace("#@ 出参 ok n", "#@ 出参 无"), "出参不能空", "流程出参空 → 拒")
    bad("quiz", lambda t: t.replace("#@ 写 attempt", "#@ 写 ghost"), "写的表「ghost」", "流程写的表不存在 → 拒")
    bad("quiz", lambda t: t.replace("-- 参数: question_id 必填, given 必填", "-- 参数: question_id 必填, given 随便"), "只能是 必填 或 可选", "参数要求不是 必填/可选 → 拒")
    bad("progress", lambda t: t.replace("  #@ 调用 scripts/quiz_judge.zs question_id=… given=…\n", ""), "规定流程「quiz_judge」给接口文件「progress」用", "层次×模块规定要用的流程，接口没调 → 拒")
    pe, r = vs("progress", lambda t: t, quiz=None)
    check(r["ok"], "progress 调 quiz 的共用流程（顶层允许）→ 通过", (pe, r["errors"]))
    # 加载检查：真项目上跑骨架
    q = C.validate_contract(TC.contract_obj("quiz"), TC.uctx("quiz"))["contract"]
    check(SK.render(q, {"/quiz/answer": "quiz_answer"}) == SK.render(q, {"/quiz/answer": "quiz_answer"}), "渲染稳定（同一约定同一骨架）")


def real_project(name, **kw):
    """假模型跑一遍（骨架先落盘；流程 / 接口实现都失败 → 骨架留在磁盘上），返回 (结果, 项目目录, 输出目录)。"""
    junk = f"=== scripts/quiz_judge.zs ===\n{TM.BAD_COND_EQ}"
    junk_u = f"=== ui/quiz_page.ui ===\n界面 表单 答题页\n  字段 given 作答\n结束\n"
    junk_r = f"=== routes/quiz.zs ===\n{TM.BAD_COND_EQ}"
    fk = TC.FakeC(bad={("生成", "流程", "scripts/quiz_judge.zs"): [junk], ("生成", "接口", "routes/quiz.zs"): [junk_r], ("生成", "界面", "ui/quiz_page.ui"): [junk_u]}, **kw)
    r, p, out = TC.go(name, fk)
    return r, p, out, fk


def t_engine_ignores():
    print("   -- #@ 行引擎当注释忽略（真加载、真调用）")
    r, p, out, fk = real_project("e1")
    fs = TC.files(r)
    check(fs["scripts/quiz_judge.zs"]["结果"] == "失败" and fs["routes/quiz.zs"]["结果"] == "失败" and fs["ui/quiz_page.ui"]["结果"] == "失败", "（准备）流程 / 接口 / 界面实现都失败 → 骨架留在磁盘")
    z = (p / "scripts/quiz_judge.zs").read_text(encoding="utf-8")
    ro = (p / "routes/quiz.zs").read_text(encoding="utf-8")
    check("#@ 入参" in z and SK.is_skeleton(z) and "#@ 请求" in ro and SK.is_skeleton(ro) and SK.is_skeleton((p / "ui/quiz_page.ui").read_text(encoding="utf-8")), "磁盘上是带 #@ 头的骨架（流程 / 接口 / 界面）")
    probs = MB.LC.check_project(p)
    check(probs == [], "整个项目（含骨架）按服务启动方式加载：零问题 —— #@ 行没有被当成语句", probs)
    q = C.validate_contract(TC.contract_obj("quiz"), TC.uctx("quiz"))["contract"]
    items = MB.C.derive_iface(q["接口"])["接口"]
    res = TR.run(p, {"routes/quiz.zs": items})
    flat = TR.problems_flat(res)
    check(res["calls"] >= 1 and any("501" in x or "未实现" in x for x in flat), "真调用骨架接口：返回 501 {error:未实现}（不是加载错误）", (res, flat))
    ui = (p / "ui/quiz_page.ui").read_text(encoding="utf-8")
    from tools import ui as UIM
    try:
        UIM.parse(ui) if hasattr(UIM, "parse") else None
        ok = True
    except Exception as e:      # noqa: BLE001
        ok = str(e)
    check(ok is True, "界面骨架能被 ui 解析器编译（#@ 行忽略）", ok)


def t_frozen():
    print("三、冻结与比对")
    q = C.validate_contract(TC.contract_obj("quiz"), TC.uctx("quiz"))["contract"]
    canon = SK.render(q, {"/quiz/answer": "quiz_answer"})
    snap = SK.freeze(canon)
    obj, errs = SK.thaw(snap)
    v = C.validate_contract(obj, TC.uctx("quiz"))
    check(not errs and v["ok"] and v["contract"] == q, "快照只含约定部分，读回来就是同一份约定（resume 靠它）", (errs, v["errors"]))
    check(all(("待实现" not in t and "未实现" not in t and "用包" not in t) for t in snap.values()), "快照里没有正文占位，只有头行与 #@ 行 / sql 头注释")
    sql_ok = TM.SQL_A
    full = {r: SK.freeze({r: t})[r] for r, t in canon.items()}
    impl = {"queries/quiz_log.sql": "\n".join(l for l in canon["queries/quiz_log.sql"].splitlines() if l.startswith("-- ") and "待实现" not in l) + "\n" + sql_ok,
            "scripts/quiz_judge.zs": "\n".join(l for l in canon["scripts/quiz_judge.zs"].splitlines() if l.startswith("#@")) + "\n" + TM.ZS_FLOW,
            "routes/quiz.zs": canon["routes/quiz.zs"].replace("  # 待实现\n", "").replace('  返回 {"error":"未实现"} 501', '  返回 {"ok":"1"}'),
            "ui/quiz_page.ui": "\n".join(l for l in canon["ui/quiz_page.ui"].splitlines() if l.startswith("#@")) + "\n" + TM.UI_Q}
    for rel, t in impl.items():
        check(SK.check_frozen(rel, t, snap[rel]) == [], f"填好实现、约定部分原样 → 通过：{rel}", SK.check_frozen(rel, t, snap[rel]))
    sets = [("queries/quiz_log.sql", lambda t: t.replace("-- 参数: question_id 必填, given 必填", "-- 参数: question_id 必填"), "sql 头注释改了参数"),
            ("queries/quiz_log.sql", lambda t: t.replace("-- 返回: 写入\n", ""), "sql 头注释删了返回行"),
            ("scripts/quiz_judge.zs", lambda t: t.replace("#@ 出参 ok n", "#@ 出参 ok"), "流程改了出参"),
            ("scripts/quiz_judge.zs", lambda t: t.replace("#@ 动词 写库表\n", ""), "流程删了动词行"),
            ("routes/quiz.zs", lambda t: t.replace("动作 quiz_answer", "动作 other"), "接口头行改了动作名"),
            ("routes/quiz.zs", lambda t: t.replace("  #@ 响应 state.ok", "  #@ 响应 state.ok state.extra"), "接口改了响应"),
            ("routes/quiz.zs", lambda t: t + "\n接口 POST /quiz/extra 动作 quiz_extra\n  返回 {}\n结束\n", "接口多了一个块"),
            ("ui/quiz_page.ui", lambda t: t.replace("#@ 字段 given", "#@ 字段 given extra"), "界面改了字段")]
    for rel, edit, what in sets:
        e = SK.check_frozen(rel, edit(impl[rel]), snap[rel])
        check(e and any("约定" in x for x in e), f"改动约定部分被拒：{what}", e)
    e = SK.check_frozen("queries/quiz_log.sql", canon["queries/quiz_log.sql"], snap["queries/quiz_log.sql"])
    check(len(e) == 1 and "占位" in e[0], "头部没动但占位没换成实现 → 也拒", e)
    e = SK.check_frozen("queries/quiz_log.sql", impl["queries/quiz_log.sql"].replace("-- 参数: question_id 必填, given 必填", "--  参数:   question_id   必填,  given 必填"), snap["queries/quiz_log.sql"])
    check(e == [], "只改空白不算改动（逐行比对按空白规范化）")
    # 手改过的缩进、gen 的 CRUD 块和骨架块共处一个文件
    mixed = "接口 POST /quiz/list 动作 quiz_list\n  返回 {}\n结束\n\n" + canon["routes/quiz.zs"]
    cut = SK.cut_skeleton_blocks(mixed, {"/quiz/answer"})
    check("/quiz/list" in cut and "/quiz/answer" not in cut and cut.count("结束") == 1, "cut_skeleton_blocks：只去掉约定里的骨架块，gen 的块原样留", cut)


def t_full():
    print("四、填骨架全流程（假模型）")
    fk = TC.FakeC()
    r, p, out = TC.go("f1", fk)
    fs = TC.files(r)
    check(r["fixed"] and r["v2"]["结论"] == "成功", "全流程成功", (r["stop"], {k: v["结果"] for k, v in fs.items()}))
    check((out / "plan/top.zs").is_file() and (out / "plan/layers.zs").is_file() and not (out / "top.json").exists() and not (out / "split.json").exists() and (out / "PLAN.md").is_file() and (out / "LAYERS.md").is_file(),
          "规划文件 plan/top.zs、plan/layers.zs 是源头；PLAN.md / LAYERS.md 由程序生成；不再写 top.json / split.json")
    top_p = [u for u in fk.prompts if "项目架构师" in u][0]
    check(PD.parse_top((out / "plan/top.zs").read_text(encoding="utf-8")) == PD.parse_top(PD.render_top(TM.top_obj())), "落盘的 plan/top.zs 就是模型写的 DSL 文本")
    cj = json.loads((out / "contracts.json").read_text(encoding="utf-8"))
    fz = json.loads((out / "contracts_frozen.json").read_text(encoding="utf-8"))
    check(set(cj) == {"quiz", "progress"} and set(fz) == {"quiz", "progress"} and "routes/quiz.zs" in fz["quiz"] and "待实现" not in json.dumps(fz, ensure_ascii=False)
          and "由骨架文件生成" in (out / "CONTRACTS.md").read_text(encoding="utf-8"), "contracts.json / CONTRACTS.md 由骨架生成；contracts_frozen.json 存约定部分快照")
    cp = fk.of("接口约定助手")
    check(len(cp) == 2 and "=== queries/quiz_log.sql ===" in cp[0] and "#@ 入参" in cp[0] and "本模块要写的流程" in cp[0], "约定提示词：骨架格式示例 + 本模块要写的流程 / 接口文件 / 页", cp[0][-1200:])
    check("=== scripts/quiz_judge.zs ===" in cp[1] and "#@ 出参 ok n" in cp[1] and "app.db quiz_log" not in cp[1], "依赖模块的约定以骨架头部给下游（没有实现）", cp[1][-1500:])
    z = (p / "scripts/quiz_judge.zs").read_text(encoding="utf-8")
    ro = (p / "routes/quiz.zs").read_text(encoding="utf-8")
    sq = (p / "queries/quiz_log.sql").read_text(encoding="utf-8")
    check(not SK.is_skeleton(z + ro + sq) and "#@ 出参 ok n" in z and "接口 POST /quiz/answer 动作 quiz_answer" in ro and "  #@ 请求 question_id given" in ro and "-- 返回: 写入" in sq and "写库表" in z,
          "实现＝填骨架：占位换成实现，约定部分（#@ / sql 头注释 / 接口头行）原样保留在最终文件里", (z, ro, sq))
    ip = fk.of(".zs 接口助手")[0]
    check("骨架文件（" in ip and "=== routes/quiz.zs ===" in ip and "#@ 响应 state.ok" in ip and "骨架头部，不给实现" in ip and "写库表 app.db quiz_log" not in ip, "填骨架提示词：本文件骨架全文 + 被调流程骨架头部（不给实现）", ip[-1500:])
    # 约定部分被改 → 拒 → 带原话重写（回复里自带一份被篡改的头，假模型的 fill 只对没有头的回复接头）
    # 假模型的 fill 会接上约定头；要演示「被改」，直接让回复里带一份被篡改的头并让 fill 不接（头里已有 #@ 行时 fill 仍会重复接，所以用无法被 fill 认出的方式：改成别的路径写法）
    sql_bad = "=== queries/quiz_log.sql ===\n" + "-- 参数: question_id 必填\n-- 返回: 写入\n-- 作用: 篡改\n-- 表: attempt\n-- 用列: 无\n-- 规则: R1\n" + TM.SQL_A
    fk = TC.FakeC(bad={("生成", "查询", "queries/quiz_*.sql"): [sql_bad, f"=== queries/quiz_log.sql ===\n{TM.SQL_A}"]})
    r, p, out = TC.go("t_sql", fk)
    f = TC.files(r)["queries/quiz_*.sql"]
    ps = TC.gens(fk, "SQLite 语句助手", "queries/quiz_*.sql")
    check(r["fixed"] and f["生成尝试"] == 2 and "约定部分" in ps[1], "sql：回复里头注释被改（参数少一个、作用改了）→ 拒", (f, ps[1][-600:] if len(ps) > 1 else ps))
    fk = TC.FakeC(bad={("生成", "流程", "scripts/quiz_judge.zs"): [TM.ZS_FLOW and f"=== scripts/quiz_judge.zs ===\n#@ 入参 question_id\n#@ 出参 ok n\n{TM.ZS_FLOW}", f"=== scripts/quiz_judge.zs ===\n{TM.ZS_FLOW}"]})
    r, p, out = TC.go("t_flow", fk)
    ps = TC.gens(fk, ".zs 流程助手", "scripts/quiz_judge.zs")
    check(r["fixed"] and len(ps) == 2 and "约定" in ps[1] and "#@" in ps[1], "流程：回复里 #@ 行被删改（fill 补上缺的之前先带了错的）→ 拒或带约定报错", ps[1][-600:] if len(ps) > 1 else ps)
    # 占位没换
    sk_only = "=== scripts/quiz_judge.zs ===\n# 待实现\n用包 common\n返回 {\"ok\":\"1\",\"n\":\"1\"}\n"
    fk = TC.FakeC(bad={("生成", "流程", "scripts/quiz_judge.zs"): [sk_only, f"=== scripts/quiz_judge.zs ===\n{TM.ZS_FLOW}"]})
    r, p, out = TC.go("t_place", fk)
    ps = TC.gens(fk, ".zs 流程助手", "scripts/quiz_judge.zs")
    check(r["fixed"] and len(ps) == 2 and "留着「待实现」占位" in ps[1], "流程：占位注释没换掉 → 拒", ps[1][-400:] if len(ps) > 1 else ps)


def t_resume():
    print("   -- 继续构建读快照 / 手改规划文件")
    d = TM.TMP / "rs1"
    shutil.rmtree(d, ignore_errors=True)
    bad = {("生成", "接口", "routes/progress.zs"): [f"=== routes/progress.zs ===\n{TM.BAD_COND_EQ}"]}
    r1 = V.run_newproj(TM.REQ, d / "proj", d / "out", model=TC.FakeC(bad=bad), modular=True, contract=True)
    (d / "out" / "contracts.json").write_text("{}", encoding="utf-8")      # 生成的只读产物，被破坏也不影响继续构建
    pl = (d / "out" / "plan" / "top.zs").read_text(encoding="utf-8")
    (d / "out" / "plan" / "top.zs").write_text(pl.replace("题库与判题", "手改过的说明"), encoding="utf-8")
    fk = TC.FakeC()
    r2 = V.run_newproj(TM.REQ, d / "proj", d / "out", model=fk, modular=True, resume=True)
    fs = TC.files(r2)
    check(r2["fixed"] and not fk.of("接口约定助手") and fs["contracts/quiz.skel"].get("沿用") and fs["contracts/progress.skel"].get("沿用"), "继续构建：约定读冻结快照（contracts.json 不读），不再调模型", (r2["stop"], fk.calls))
    check("手改过的说明" in (d / "out" / "PLAN.md").read_text(encoding="utf-8"), "继续构建读的是 plan/top.zs（人手改过的规划生效，PLAN.md 重新生成）")
    check(fs["routes/progress.zs"]["结果"] == "通过" and not SK.is_skeleton((d / "proj/routes/progress.zs").read_text(encoding="utf-8")) and "  #@ 请求 question_id given" in (d / "proj/routes/progress.zs").read_text(encoding="utf-8"), "失败的接口文件这次按骨架填好；约定头原样在")
    # 快照被改 → 按快照校验，不过就重新约定
    d2 = TM.TMP / "rs2"
    shutil.rmtree(d2, ignore_errors=True)
    V.run_newproj(TM.REQ, d2 / "proj", d2 / "out", model=TC.FakeC(), modular=True, contract=True)
    fz = json.loads((d2 / "out" / "contracts_frozen.json").read_text(encoding="utf-8"))
    fz["quiz"]["routes/quiz.zs"] = fz["quiz"]["routes/quiz.zs"].replace("动作 quiz_answer", "动作 ghost act")
    (d2 / "out" / "contracts_frozen.json").write_text(json.dumps(fz, ensure_ascii=False), encoding="utf-8")
    fk = TC.FakeC()
    r3 = V.run_newproj(TM.REQ, d2 / "proj", d2 / "out", model=fk, modular=True, resume=True)
    check(len(fk.of("接口约定助手")) >= 1 and TC.files(r3)["contracts/quiz.skel"].get("沿用") is None, "快照坏了（读不通 / 校验不过）→ 不沿用，重新让模型约定", (r3["stop"], fk.calls[:4]))


def main():
    try:
        t_plan()
        t_skeleton()
        t_rules_on_skeleton()
        t_engine_ignores()
        t_frozen()
        t_full()
        t_resume()
    finally:
        shutil.rmtree(TM.TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
