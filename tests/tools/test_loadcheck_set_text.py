# -*- coding: utf-8 -*-
"""加载检查：严格模式下「设」右值以词+空格开头被当成动词调用（K29a）。

运行时（tools/dsl.py _exec_block 的 set 分支）：右值首词不是 执行/调用/计算、
是已注册动词就走动词调用，否则当文本——严格模式（有「用包」）下再经
_check_unknown_verb 确认：首词满足 VERB_LIKE_RE（无空格和 {}=/\\:：）、不是
关键字、不是数字、而动词表里没有 → 报「没有名为…的动词」。文本文案写成
「按 {level} 等级给你出题」「已掌握 {n} / {m}」就撞上，而且运行到那行才炸。

这里验证 loadcheck.check_set_unknown_verbs 与运行时同一口径：该报的报、
不该报的不报。不调模型。

    .venv/bin/python tests/tools/test_loadcheck_set_text.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.dslagent import loadcheck as LC  # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n    {extra}" if extra else ""))


def reg_common():
    """common 包的动词表（报错、当前时间…）。包不存在时 reg 为空也行：报的用例用「按」。"""
    return LC.load_verbs(tempfile.mkdtemp(), ["common"])


def t_hit():
    print("一、动词形态 + 未注册 → 报")
    reg = reg_common()
    lines = ["用包 common", "设 reply = 按 {level} 等级给你出题"]
    probs = LC.check_set_unknown_verbs(lines, reg, "services/tutor.zs 函数 出题")
    check(len(probs) == 1, "「设 reply = 按 {level} …」报一条", str(probs))
    hit = probs[0] if probs else ""
    check("第 2 行" in hit and "「按」" in hit, "文案写清行号和词", hit)
    check("没有名为" in hit, "文案与运行时同款（没有名为…的动词）", hit)
    # 运行时同样认的形态：首词带逗号、句号也算（VERB_LIKE_RE 不排它们）
    probs = LC.check_set_unknown_verbs(
        ["用包 common", "设 s = 已掌握 {n} / {m} 个知识点"], reg, "x")
    check(len(probs) == 1 and "「已掌握」" in probs[0], "「设 s = 已掌握 …」报", str(probs))


def t_registered():
    print("二、已注册动词 → 不报（引擎走 _do_verb，到不了文本赋值）")
    reg = reg_common()
    lines = ["用包 common", "设 e = 报错 测试", "设 t = 当前时间"]
    probs = LC.check_set_unknown_verbs(lines, reg, "x")
    check(not probs, "报错 / 当前时间 不报", str(probs))


def t_not_verb_like():
    print("三、不像动词的右值 → 不报")
    reg = reg_common()
    lines = [
        "用包 common",
        "设 x = {a} 等级",                              # 首词带 { → 不是动词形态
        "设 link = /quiz?mode=free&level={level}",      # 以 / 开头
        "设 eq = a=b",                                  # 带 =
        "设 n = 2024 年",                               # 首词是数字
        "设 w = 明天",                                  # 单词、没参数
        "设 m = 执行 x.zs 后 调用 y",                   # 关键字开头
    ]
    probs = LC.check_set_unknown_verbs(lines, reg, "x")
    check(not probs, "七种不像动词调用的写法都不报", str(probs))


def t_loose_mode():
    print("四、非严格模式文件 → 不报（没「用包」，检查不开）")
    root = Path(tempfile.mkdtemp())
    d = root / "scripts"
    d.mkdir()
    f = d / "loose.zs"
    f.write_text("设 reply = 按 {level} 等级给你出题\n", encoding="utf-8")
    probs = LC._check_file_verbs(root, f, False)
    check(not probs, "没有「用包」的脚本文件不报", str(probs))


def t_call_like():
    print("五、业务函数 / 脚本调用、计算 → 不报（引擎先分派）")
    reg = reg_common()
    lines = [
        "用包 common",
        "设 ov = 调用 progress.取概览 learner={learner}",
        "设 r = 执行 helper.zs a=1",
        "设 n = 计算 {a} * 100 / {b}",
    ]
    probs = LC.check_set_unknown_verbs(lines, reg, "x")
    check(not probs, "调用 / 执行 / 计算 的右值不报", str(probs))


def main():
    t_hit()
    t_registered()
    t_not_verb_like()
    t_loose_mode()
    t_call_like()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
