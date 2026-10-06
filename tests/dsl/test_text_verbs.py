# -*- coding: utf-8 -*-
"""text 包的通用字符串动词，和从 Python 调 .zs 动词（invoke_verb / packs.call_verb）。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_text_verbs.py

  一、每个动词直接调：归一化、转平假名、稳定打乱、取字母、转大写、替换、相等、
      截取、挑行、列表加项；common 的报错
  二、在脚本里用：参数切在展开之前（值里有空格没事）、结构当 JSON 文本传进去
      再拿回结构、相等 不怕空值和「为空」这种词
  三、稳定打乱跟早先「拆选项」里那段打乱（sha256 当种子）完全一样
  四、.zs 动词从 Python 调：invoke_verb、packs.call_verb；.zs 动词里问模型直接报错
"""

import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                                # noqa: E402
from tools.dsl import DSLEngine, DSLError, invoke_verb  # noqa: E402
from tools.mock import MockClient                      # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REG = packs.registry(["common", "text"], ROOT, cache=False)


def v(name, *args):
    return invoke_verb(REG, name, *args, workdir=ROOT, verbs_root=packs.verbs_root())


def raises(fn) -> bool:
    try:
        fn()
    except (ValueError, DSLError):
        return True
    return False


def run(script: str, **vars_) -> DSLEngine:
    e = DSLEngine(client=MockClient(offline=True), workdir=ROOT, verbose=False,
                  verbs=packs.registry(["common", "text"], ROOT, cache=False),
                  verbs_root=packs.verbs_root())
    e.vars.update(vars_)
    e.run(script)
    return e


def main():
    print("一、直接调")
    check(v("归一化", "Ｃ　ｃ\t1 ") == "Cc1", "归一化：NFKC、去所有空白，大小写不动")
    check(v("归一化", "あ う。、., ") == "あう。、.,", "归一化：不给去标点，句号逗号留着")
    check(v("归一化", "あ う。、．，", "是") == "あう", "归一化 去标点=是：句号逗号（含全角）也去掉")
    check(v("归一化", "「あ」？！", "是") == "「あ」?!", "去标点只去句号逗号，别的标点留着（NFKC 后半角）")
    check(v("归一化", "ｱｳ") == "アウ", "半角片假名 NFKC 成全角")
    check(v("转平假名", "アウ・テレビー") == "あう・てれびー", "转平假名：片假名换，中点、长音符不动")
    check(v("转平假名", "ヴァヵヶ") == "ゔぁゕゖ", "转平假名：ヴ ヵ ヶ 也换（边界）")
    check(v("转平假名", "ヷヺァ漢a") == "ヷヺぁ漢a", "转平假名：ヷ ヺ 没有平假名，原样；汉字字母不动")
    check(v("稳定打乱", ["a", "b", "c", "d"], "s1") == v("稳定打乱", '["a","b","c","d"]', "s1"),
          "稳定打乱：真列表和 JSON 文本结果一样")
    check(v("稳定打乱", [1, 2, 3], "") == [1, 2, 3], "稳定打乱：种子空不打乱")
    orig = list(range(10))
    got = v("稳定打乱", orig, "x")
    check(orig == list(range(10)) and sorted(got) == orig and got != orig, f"稳定打乱：原列表不动，返回新的：{got}")
    check(raises(lambda: v("稳定打乱", "不是列表", "x")), "稳定打乱：给的不是列表就报错")
    check(v("取字母", "答案是 ｃ。") == "C" and v("取字母", "（Ｂ）") == "B" and v("取字母", "选e") == "",
          "取字母：全角、小写都认，只认 A–D")
    check(v("取字母", "") == "" and v("取字母", "bad") == "B", "取字母：空给空；取第一个 A–D（bad → B）")
    check(v("转大写", "abcあ") == "ABCあ", "转大写")
    check(v("替换", "書かせる。。", "。+$") == "書かせる", "替换：替换为不给就是删掉")
    check(v("替换", "  x y  ", r"^\s+|\s+$") == "x y", "替换：strip")
    check(v("替换", "[N4] 见面", r"^\s*\[N[1-5]\]\s*") == "见面", "替换：去等级前缀")
    check(v("替换", "憎む", "[\\u3040-\\u309f]+$") == "憎", "替换：\\u 写法的字符范围")
    check(v("替换", "a1b2", r"\d", "#") == "a#b#", "替换：给了替换为")
    check(raises(lambda: v("替换", "x", "(")), "替换：正则写错了报错")
    check(v("相等", "a b", "a b") == "是" and v("相等", "a", "a ") == "否" and v("相等", "", "") == "是",
          "相等：原样比，空白也算")
    check(v("截取", "ABCDEFGH", "3", "1") == "C" and v("截取", "ABCDEFGH", "9", "1") == "",
          "截取：从 1 数，越界给空")
    check(v("截取", "ABCD", "-1") == "D" and v("截取", "ABCD", "2") == "BCD", "截取：负数从末尾数；不给长度取到底")
    check(raises(lambda: v("截取", "ABCD", "0")) and raises(lambda: v("截取", "ABCD", "x")), "截取：0 和非整数报错")
    r = v("挑行", "题面\nA. 甲 \r\nＢ．乙\n尾", r"^\s*([A-DＡ-Ｄ])\s*[.．]\s*(.*)$")
    check(r == {"hits": [["A. 甲 ", "A", "甲 "], ["Ｂ．乙", "Ｂ", "乙"]], "rest": "题面\n尾"},
          f"挑行：匹配的行给分组，其余的行连起来（\\r\\n 也算换行）：{r}")
    check(v("挑行", "x", r"(a)?x") == {"hits": [["x", ""]], "rest": ""}, "挑行：没匹配上的组给空串")
    check(v("列表加项", "", "a") == ["a"] and v("列表加项", '["a"]', '{"k":1}') == ["a", {"k": 1}],
          "列表加项：空当空列表；JSON 对象文本按结构加")
    check(v("列表加项", [], "[注意]") == ["[注意]"] and v("列表加项", [], "{x}") == ["{x}"],
          "列表加项：长得像括号但不是 JSON 的，当文本加")
    check(raises(lambda: v("报错", "坏了")), "报错：抛出来")

    print("二、在脚本里用")
    e = run("用包 text\n设 a = 归一化 {x}\n设 same = 相等 {a} {y}\n设 blank = 相等 {z} {}\n",
            x="あ い　う", y="あいう", z="{}")
    check(e.vars["a"] == "あいう" and e.vars["same"] == "是", "值里有空格：一个参数，不错位")
    check(e.vars["blank"] == "是", "相等 {z} {}：认得出空结构（「如果 {结构} 为空」会把 {…} 当成没展开的变量）")
    e = run("用包 text\n设 opt.key = A\n设 opt.text = {t}\n设 opts = 列表加项 [] {opt}\n"
            "设 opt.key = B\n设 opts = 列表加项 {opts} {opt}\n设 n = 截取 XYZ 2 1\n", t="甲 乙")
    check(e.vars["opts"] == [{"key": "A", "text": "甲 乙"}, {"key": "B", "text": "甲 乙"}] and e.vars["n"] == "Y",
          f"结构经 JSON 文本进动词再拿回结构，后改的不影响先加的：{e.vars['opts']}")
    e = run("用包 text\n设 w = 为空\n设 s = 相等 {w} 为空\n设 m = {missing 或}\n设 e = 相等 {m} {w}\n")
    check(e.vars["s"] == "是" and e.vars["e"] == "否", "相等：值是「为空」这种词、或者是空的，都照常比")
    try:
        run("用包 common\n报错 走不下去了\n打印 不该到这")
        check(False, "脚本里报错：没抛")
    except (ValueError, DSLError) as ex:
        # 单独一行调动词时引擎不包一层，是动词抛的 ValueError；接口里照样回 500
        check("走不下去了" in str(ex), f"脚本里报错：抛出来，带着原因：{ex}")

    print("三、稳定打乱跟早先拆选项里的打乱一样")
    same = True
    for i in range(300):
        seed = f"me|bunpou_n4-{i:03d}|{i % 7}"
        items = [{"key": k, "text": k * 2} for k in "ABCD"]
        want = list(items)
        random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)).shuffle(want)
        same = same and v("稳定打乱", json.dumps(items), seed) == want
    check(same, "300 个种子，顺序逐个一样")

    print("四、.zs 动词从 Python 调")
    tmp = Path(tempfile.mkdtemp(prefix="text_verbs_"))
    pack = tmp / "verbs" / "demo"
    pack.mkdir(parents=True)
    (pack / "加括号.zs").write_text("# 加括号：给一段文字加上括号\n# 参数：文字\n"
                                     "用包 text\n设 t = 归一化 {文字}\n返回 「{t}」\n", encoding="utf-8")
    (pack / "问一下.zs").write_text("# 问一下\n# 参数：话\n问 r = {话}\n返回 {r}\n", encoding="utf-8")
    from tools.dsl import RESERVED
    from tools.verbs import VerbRegistry
    reg = VerbRegistry(reserved=RESERVED)
    reg.load_pack(pack)
    check(invoke_verb(reg, "加括号", "Ａ Ｂ", workdir=tmp, verbs_root=packs.verbs_root()) == "「AB」",
          "invoke_verb 调 .zs 动词：返回值跟脚本里拿到的一样")
    check(raises(lambda: invoke_verb(reg, "问一下", "你好", workdir=tmp)),
          "没给模型客户端：.zs 动词里问模型直接报错，不去花额度")
    got = invoke_verb(reg, "问一下", "你好", workdir=tmp, client=MockClient(replies=["好"]))
    check(got == "好", f"给了客户端就能问：{got}")
    r = packs.call_verb("判对错", {"题型": "选择", "答案": "C", "作答": "选ｃ"}, packs=["quiz"], workspace=ROOT)
    check(r == "1", f"packs.call_verb 也能调 .zs 动词（判对错）：{r}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
