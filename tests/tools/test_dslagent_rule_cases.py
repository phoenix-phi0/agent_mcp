# -*- coding: utf-8 -*-
"""规则反例：v2.check 拒绝每个反例、接受对应的正例；整理版示例与自检里的「对照写法」都能过 v2.check。不调模型。

    .venv/bin/python tests/tools/test_dslagent_rule_cases.py

fixture 小项目：tests/tools/fixtures/rule_proj（pkg/calc.py 等）。
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.dslagent import packs, plan as P, v2  # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures" / "rule_proj"
PACK = packs.current()
CL = "\n#清单\n改 pkg/calc.py:add\n"
H = "用包 common text code\n预算 调用 4 秒 300\n"
E1 = ("\n#改法 e1\n@@ 改 pkg/calc.py\n<<<<<<< 原文\ndef add(a, b):\n    return a + b\n=======\n"
      "def add(a, b):\n    return b + a\n>>>>>>> 新文\n")

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n    {extra}" if extra else ""))


def run(script):
    with tempfile.TemporaryDirectory() as w:
        return v2.check(FX, Path(w), script, "t", PACK)[0]


# 名字: (反例整份脚本, 正例整份脚本)
CASES = {
    "首词 import 被当动词": (H + "设 h = import json 放到函数里\n终止 成功 ok" + CL,
                       H + "设 h = 做法：import json 放到函数里\n终止 成功 ok" + CL),
    "首词 只改 被当动词": (H + "设 s = 只改 pkg/calc.py 的 div\n终止 成功 ok" + CL,
                      H + "设 s = 范围：只改 pkg/calc.py 的 div\n终止 成功 ok" + CL),
    "预算 写 0": ("用包 common text code\n预算 调用 0 秒 300\n终止 成功 ok" + CL,
                H + "终止 成功 ok" + CL),
    "缺 预算 头": ("用包 common text code\n终止 成功 ok" + CL,
                H + "终止 成功 ok" + CL),
    "提示词里换行": (H + "问JSON v = 判断下一步\n格式 action:改|停 reason:文本\n终止 成功 ok" + CL,
                 H + "问JSON v = 判断下一步 格式 action:改|停 reason:文本\n终止 成功 ok" + CL),
    "#改法 段里混语句": (H + "终止 成功 ok" + E1 + "设 res = 改文件 {e1}\n" + CL,
                    H + "设 res = 改文件 {e1}\n终止 成功 ok" + E1 + CL),
    "说明文字单独成行": (H + "接下来用 派任务 改另外两个文件\n终止 成功 ok" + CL,
                    H + "# 接下来用 派任务 改另外两个文件\n终止 成功 ok" + CL),
}


def t_pairs():
    print("一、反例被拒、正例通过")
    for name, (bad, good) in CASES.items():
        pb, pg = run(bad), run(good)
        check(bool(pb), f"{name}：反例被拒", "反例居然通过了")
        check(not pg, f"{name}：正例通过", pg)


def t_example():
    print("二、整理版示例与自检里的对照写法")
    ex = (P.PKG / "lib" / "示例_分支规划.zs").read_text(encoding="utf-8")
    p = run(ex)
    check(not p, "lib/示例_分支规划.zs 通过 v2.check", p)
    tips = (P.PKG / "agents" / "shared" / "tips_plan.md").read_text(encoding="utf-8")
    m = re.search(r"^\s*- 对：(.+)$", tips, re.M)
    check(bool(m), "自检里写有「对照写法」")
    if m:
        # 一行里用全角空格隔开多个写法；每个都放进最小脚本里验证
        for stmt in [s.strip() for s in m.group(1).split("　") if s.strip()]:
            if stmt.startswith("设 h = {d.reason}"):
                stmt = "设 d.reason = x\n" + stmt
            p = run(H + stmt + "\n终止 成功 ok" + CL)
            check(not p, f"对照写法通过：{stmt[:40]}", p)
    bad = re.search(r"^\s*- 错：(.+)$", tips, re.M)
    if bad:
        for stmt in [s.strip() for s in bad.group(1).split("　") if s.strip()]:
            check(bool(run(H + stmt + "\n终止 成功 ok" + CL)), f"自检里的错误写法被拒：{stmt[:40]}")


def main():
    t_pairs()
    t_example()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
