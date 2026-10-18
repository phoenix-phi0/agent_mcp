# -*- coding: utf-8 -*-
"""tools/dslagent/plan_autofix.py：计划检查不过时程序先自动修三类机械错误。不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_autofix.py

  一、赋值右边首词不是动词（R5）：改成「词：其余」；Python 语句且作为 运行代码 参数 → 「_=0;词 其余」，真能被 运行代码 执行
  二、说明句行 → 注释；派任务 参数过多 → 中间文本并入新增的 设 _logicN
  三、不该修的不修：合法计划（lib 示例 + 历史上首次通过的计划）原样不变；别的报错、无法唯一判定的写法不动；#改法 / #清单 段不碰
  四、接进 v2.run：修好就不走 plan_fix 并记录；没修好把「修过的计划 + 剩余报错」交给 plan_fix；DSLAGENT_AUTOFIX=0 关闭
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_dslagent_v2 as T                   # noqa: E402  复用它的假项目 / 计划 / 假模型

ROOT, V, TMP = T.ROOT, T.V, T.TMP
from tools.dslagent import packs                # noqa: E402
from tools.dslagent import plan_autofix as AF   # noqa: E402

PASS = FAIL = 0
PACK = packs.current()
PROJ = T.make_proj("af_proj")


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def rc(script):
    return V.check(PROJ, TMP / "af_dry", script, T.TASK, PACK)


def fix(body, **kw):
    """T.plan(body) 先 check，不过就 autofix。返回 (原计划, 原问题, 新计划, 记录, 剩余问题)。"""
    s = T.plan(body, **kw)
    p0 = rc(s)[0]
    s2, fx, p1, *_ = AF.autofix(s, p0, rc)
    return s, p0, s2, fx, p1


def changed_lines(a, b):
    return [(x, y) for x, y in zip(a.splitlines(), b.splitlines()) if x != y]


TAIL = "\n设 res = 改文件 {e1}\n终止 成功 好\n"


def t_assign():
    print("一、赋值右边")
    s, p0, s2, fx, p1 = fix("设 logic = 将入参里的检查改为使用 tools.safepath 公共模块" + TAIL)
    check("没有名为「将入参里的检查改为使用」的动词" in p0, "原计划确实报「没有名为…的动词」", p0)
    check(not p1 and len(fx) == 1 and fx[0]["类型"] == "赋值右边:文本", "修完检查通过，记 1 处", (p1, fx))
    check(fx[0]["原文"] == "设 logic = 将入参里的检查改为使用 tools.safepath 公共模块"
          and fx[0]["新文"] == "设 logic = 将入参里的检查改为使用：tools.safepath 公共模块" and fx[0]["行号"] == 3, "记录行号 / 原文 / 新文", fx)
    check(len(changed_lines(s, s2)) == 1, "只动这一行")

    s, p0, s2, fx, p1 = fix("设 a = 修改 甲\n设 b = 创建 乙 丙\n设 c = 分别修改两个 jobs 接口" + TAIL)
    check(not p1 and [x["行号"] for x in fx] == [3, 4, 5], "同一份计划里多处：逐处修，直到通过", (p1, fx))

    s, p0, s2, fx, p1 = fix("设 code = import os, sys\n设 r = 运行代码 {code}\n设 res = 改文件 {e1}\n终止 成功 好\n")
    check(not p1 and fx and fx[0]["类型"] == "赋值右边:Python代码" and fx[0]["新文"] == "设 code = _=0;import os, sys", "import 且作为 运行代码 参数 → 前面加 _=0;", (p1, fx))
    from tools.dslagent.engine import AgentEngine
    from tools.mock import MockClient
    eng = AgentEngine(client=MockClient(handler=lambda p, system=None: "x", offline=True), workdir=PROJ, verbose=False, verbs_root=V.VERBS)
    eng.run("用包 common text code\n设 code = _=0;import os, sys\n设 r = 运行代码 {code}\n打印 RAN={r.ran}")
    check("RAN=是" in "\n".join(eng.output), "改后的代码真能被 运行代码 执行", eng.output)

    s, p0, s2, fx, p1 = fix("设 code = from os import path\n设 note = {code}\n设 res = 改文件 {e1}\n终止 成功 好\n")
    check(fx and fx[0]["类型"] == "赋值右边:文本", "import / from 但没作为 运行代码 的参数 → 当文本（加冒号）", fx)

    # 子脚本写在主脚本后面（#改法 之后的子脚本也归各自的段）
    s = T.plan("执行 _plan/辅助.zs" + TAIL).replace("\n#改法 e1", "\n#子脚本 辅助.zs\n设 t = 把这里改成加法 之类\n\n#改法 e1")
    p0 = rc(s)[0]
    s2, fx, p1, *_ = AF.autofix(s, p0, rc)
    check("没有名为「把这里改成加法」的动词" in p0 and not p1 and fx and fx[0]["原文"] == "设 t = 把这里改成加法 之类"
          and "设 t = 把这里改成加法：之类" in s2, "子脚本里的赋值行同样修", (p0, p1, fx))


def t_prose_dispatch():
    print("二、说明句行 / 派任务参数过多")
    s, p0, s2, fx, p1 = fix("修改 pkg/util.py 里的 double 函数" + TAIL)
    check("认不出的语句" in p0 and not p1 and fx[0]["类型"] == "说明句行" and fx[0]["新文"] == "# 修改 pkg/util.py 里的 double 函数",
          "说明句行 → 注释", (p0, p1, fx))
    s, p0, s2, fx, p1 = fix("  将这个文件改成加法" + TAIL)
    check(not p1 and s2.splitlines()[2] == "  # 将这个文件改成加法", "保留缩进", s2)

    body = ("设 inp = 文件：pkg/util.py:1-3\n设 fmt = edits:列表,说明:文本\n"
            "设 r = 派任务 改写 {inp} 按要求把 double 改为加法 保持行为 {fmt}\n"
            "如果 {r.状态} 不等于 成功\n  终止 失败 子任务没完成\n结束\n设 res = 改文件 {r.结果}\n终止 成功 好\n")
    s, p0, s2, fx, p1 = fix(body)
    check("最多接受 4 个参数" in p0 and not p1 and fx and fx[0]["类型"] == "派任务参数过多", "格式是已定义为 字段:类型 的 {变量}：修好", (p0, p1, fx))
    check("设 _logic1 = 逻辑：按要求把 double 改为加法 保持行为" in s2 and "设 r = 派任务 改写 {inp} {_logic1} {fmt}" in s2, "中间文本并入 _logic1，原位置换成 {_logic1}", s2)
    body2 = body.replace("{fmt}\n", "edits:列表,说明:文本\n").replace("设 fmt = edits:列表,说明:文本\n", "")
    s, p0, s2, fx, p1 = fix(body2)
    check(not p1 and "{_logic1} edits:列表,说明:文本" in s2, "末尾直接写 字段:类型 也认", (p1, s2))
    s, p0, s2, fx, p1 = fix(body.replace("设 inp = ", "设 _logic1 = 占位\n设 inp = "))
    check(not p1 and "设 _logic2 = 逻辑：" in s2, "_logic1 已被占用 → 用 _logic2", s2)
    s, p0, s2, fx, p1 = fix(body.replace("设 fmt = edits:列表,说明:文本\n", "设 fmt = 随便\n"))
    check(s2 == s and not fx and "最多接受 4 个参数" in p1, "末尾不是 格式（{变量} 没定义成 字段:类型）→ 不修", (fx, p1))
    s, p0, s2, fx, p1 = fix(body.replace("{fmt}\n", "收尾\n"))
    check(s2 == s and not fx, "末尾既不是 字段:类型 也不是格式变量 → 不修", fx)
    s, p0, s2, fx, p1 = fix("设 jobs = 解析JSON []\n设 rs = 并行派任务 {jobs} 3 多余 参数 edits:列表\n设 res = 改文件 {e1}\n终止 成功 好\n")
    check(s2 == s and not fx and p0, "并行派任务 参数多了 → 不修（留给 plan_fix）", (fx, p0))


def t_untouched():
    print("三、不该修的不修")
    lib = (ROOT / "tools" / "dslagent" / "lib" / "示例_分支规划.zs").read_text(encoding="utf-8")
    fx_dir = HERE / "fixtures" / "autofix_ok"
    plans = sorted(fx_dir.glob("*.zs"))
    check(len(plans) >= 5, f"历史上首次通过的计划夹具 {len(plans)} 份")
    for name, s in [("lib/示例_分支规划.zs", lib)] + [(p.name, p.read_text(encoding="utf-8")) for p in plans]:
        calls = []
        s2, fx, p1, *_ = AF.autofix(s, "", lambda x: calls.append(x) or ("", None, None, None))
        check(s2 == s and not fx and not calls, f"没有报错时原样不变、不重新 check：{name}")
    _, _, s2, fx, _ = fix("设 h = 线索：改 foo 为 bar\n设 n = 3 个\n设 x = {res.msg} 待核实\n设 k = 解析JSON []\n设 t = 匹配 abc a" + TAIL)
    check(not fx, "合法的文本 / 数字 / {变量} 开头 / 动词开头的赋值，check 过了就不动", fx)

    # 别的报错一概不动
    for label, body in [("缺 预算", None), ("白名单外动词", "设 x = 查表 a b" + TAIL)]:
        s = T.plan("终止 成功 好\n").replace("预算 调用 4 秒 300\n", "") if body is None else T.plan(body)
        p0 = rc(s)[0]
        s2, fx, p1, *_ = AF.autofix(s, p0, rc)
        check(p0 and s2 == s and not fx or (label == "白名单外动词" and fx), f"其它报错不动：{label}", (p0, fx))

    # 报错行指到 #改法 段内：不碰
    s = T.plan("终止 成功 好\n")
    n = len(s.splitlines())
    bad = s.replace("    return x + x\n", "    return x + x\n设 q = 修改 foo bar\n")
    mainl, nmain, subs, sec = AF._segments(bad)
    q_idx = next(i for i, l in enumerate(bad.splitlines()) if l.startswith("设 q = "))
    check(q_idx in sec, "段内行被识别为段内")
    err = f"用假模型空跑报错：DSLError: 第 {mainl.index(q_idx) + 1} 行：没有名为「修改」的动词。"
    check(AF._apply_one(bad, err, ()) is None, "报错行号指到 #改法 段内的行 → 不修")
    s2, fx, *_ = AF.autofix(bad, err, lambda x: (err, None, None, None))
    check(s2 == bad and not fx, "autofix 对段内行原样返回")

    # 修主脚本时，段内文本一字不动
    body = "设 logic = 将入参改为使用 tools.safepath" + TAIL
    s = T.plan(body)
    s2 = AF.autofix(s, rc(s)[0], rc)[0]
    check(s.split("#改法", 1)[1] == s2.split("#改法", 1)[1], "#改法 / #清单 段修前修后逐字相同")
    # 已知动词不当文本改
    check(AF.fix_assign("设 x = 匹配 a b", 0, "匹配") is None and AF.fix_assign("设 x = {a} 其余", 0, "{a}") is None, "已知动词 / {变量} 开头：fix_assign 不动")
    check(AF.fix_assign("设 x = 线索：改 foo", 0, "线索：改") is None, "首词带冒号（本来就是文本）：不动")


def t_flow():
    print("四、接进 v2.run")
    bad = T.plan("设 logic = 将入参改为使用 tools.safepath 公共模块\n" + T.PLAN_OK.split("预算 调用 4 秒 300\n", 1)[1].split("\n#改法")[0].strip("\n"))
    f = T.Fake(plan=bad)
    r, p, out = T.go("af_ok", f)
    v = r["v2"]
    check(r["reply"]["状态"] == "成功" and f.tags() == ["plan", "bound"] and not v["重写"], "修好 → 不走 plan_fix，照常执行验收", (r["reply"], f.tags()))
    fx = v["检查"][0].get("自动修复")
    check(fx and fx[0]["类型"] == "赋值右边:文本" and {"类型", "行号", "原文", "新文"} <= set(fx[0]) and "没有名为" in v["检查"][0]["问题"],
          "result.json 的 v2.检查[0].自动修复 记 类型/行号/原文/新文", v["检查"])
    check(v.get("自动修复") and v["自动修复"][0].startswith("自动修复：第 1 版计划 1 处"), "v2.自动修复 有一句话记录", v.get("自动修复"))
    check((out / "plan_v1.orig.zs").read_text(encoding="utf-8").strip() == bad.strip() and "使用：tools.safepath" in (out / "plan.zs").read_text(encoding="utf-8"),
          "原计划留作 plan_v1.orig.zs，plan.zs 是修过的")
    saved = json.loads((out / "result.json").read_text(encoding="utf-8"))
    check(saved["v2"]["检查"][0]["自动修复"] == fx, "写进 result.json")

    # 修了一部分、还有别的错 → plan_fix 看到的是修过的版本和剩余报错
    bad2 = T.plan("设 logic = 将入参改为使用 tools.safepath 公共模块\n打印 你好\n")
    f = T.Fake(plan=bad2, plan_fix=T.PLAN_OK)
    r, p, out = T.go("af_part", f)
    fxu = next(u for t, _, u in f.log if t == "plan_fix")
    check(r["reply"]["状态"] == "成功" and r["v2"]["重写"] and "使用：tools.safepath" in fxu and "没有打印「结论" in fxu and "没有名为" not in fxu,
          "没修完 → plan_fix 的输入是修过的计划 + 剩余报错", fxu[:600])
    ck = r["v2"]["检查"][0]
    check(ck.get("自动修复") and "没有打印「结论" in ck.get("自动修复后问题", "") and "没有名为" in ck["问题"], "记录里有原问题和自动修复后的剩余问题", ck)

    # 开关
    os.environ["DSLAGENT_AUTOFIX"] = "0"
    try:
        f = T.Fake(plan=bad, plan_fix=T.PLAN_OK)
        r, p, out = T.go("af_off", f)
    finally:
        del os.environ["DSLAGENT_AUTOFIX"]
    check(f.tags()[:2] == ["plan", "plan_fix"] and "自动修复" not in r["v2"]["检查"][0] and not (out / "plan_v1.orig.zs").exists(),
          "DSLAGENT_AUTOFIX=0：不自动修，走 plan_fix", f.tags())


def main():
    try:
        t_assign()
        t_prose_dispatch()
        t_untouched()
        t_flow()
    finally:
        T.shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
