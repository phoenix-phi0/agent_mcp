# -*- coding: utf-8 -*-
"""问JSON 的「格式」后缀：附格式说明、检查、不对就重问、重问用完报错。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_ask_json_format.py

  一、各类型通过 / 不通过：文本 数字 是否 列表 枚举，可选字段，多余字段，非对象
  二、重问：重问后成功、重问提示里有具体问题和上次的回复、重问用完报错（行号、
      问题列表、最后一次回复）、「重问 N 次」、非法 JSON 也重问
  三、语法：提示词里的「格式」不被误认、类型写错报错、和 附 / 用 一起用
  四、兼容：不带「格式」的旧写法照旧走 chat_json，提示词不变
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import DSLEngine                         # noqa: E402
from tools.mock import MockClient                   # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(script, replies, workdir=None):
    """按顺序回 replies，返回 (输出或报错文本, 客户端)。"""
    m = MockClient(replies=replies, offline=True)
    try:
        out = DSLEngine(m, workdir=workdir, verbose=False).run(script)
    except Exception as e:
        out = f"{type(e).__name__}: {e}"
    return out.strip(), m


def sent(m, i=-1):
    """第 i 次调用发出去的消息内容列表。"""
    return [x["content"] for x in m.calls[i]["messages"]]


def one(fmt, reply):
    """只问一次（重问 0 次），返回输出。"""
    return run(f"问JSON r = 问 格式 {fmt} 重问 0 次\n打印 {{r}}", [reply])[0]


def main():
    print("一、类型")
    check(one("a:文本", '{"a":"好"}') == '{"a":"好"}', "文本通过")
    out = one("a:文本", '{"a":""}')
    check("a 应该是非空的文本" in out, f"空文本不通过：{out[:60]}")
    check("应该是非空的文本" in one("a:文本", '{"a":3}'), "数字不算文本")
    check(one("a:数字", '{"a":3}') == '{"a":3}', "数字通过")
    check(one("a:数字", '{"a":"2.5"}') == '{"a":2.5}', "数字字符串转成数字存回")
    check(one("a:数字", '{"a":" 7 "}') == '{"a":7}', "整数字符串转成 int")
    check("a 应该是数字" in one("a:数字", '{"a":"三"}'), "转不了的不通过")
    check("a 应该是数字" in one("a:数字", '{"a":true}'), "布尔不算数字")
    check(one("a:是否", '{"a":true}') == '{"a":true}', "布尔通过")
    out, _ = run("问JSON r = 问 格式 a:是否 b:是否 c:是否\n打印 {r.a}{r.b}{r.c}",
                 ['{"a":"是","b":"false","c":"True"}'])
    check(out == "是否是", f"是/否/true/false 字符串转成布尔，插值出 是/否：{out}")
    check("a 应该是 true 或 false" in one("a:是否", '{"a":"也许"}'), "别的字符串不通过")
    check(one("a:列表", '{"a":[1,2]}') == '{"a":[1,2]}', "列表通过")
    check("a 应该是列表" in one("a:列表", '{"a":"1,2"}'), "字符串不算列表")
    check(one("a:合格|重做", '{"a":" 合格 "}') == '{"a":"合格"}', "枚举去首尾空白后通过")
    out = one("action:合格|重做", '{"action":"基本合格"}')
    check("action 只能是 合格 或 重做，你回了 基本合格" in out, f"枚举不通过：{out[:80]}")
    check("只能是 A、B 或 C" in one("x:A|B|C", '{"x":"D"}'), "三个可选值的说法")
    check(one("a:文本 note?:文本", '{"a":"x"}') == '{"a":"x"}', "可选字段缺了不算错")
    check("note 应该是非空的文本" in one("a:文本 note?:文本", '{"a":"x","note":5}'),
          "可选字段存在就按类型查")
    for v in ('""', '"   "', '" \\n\\t"', "null"):
        check(one("a:文本 note?:文本", '{"a":"x","note":%s}' % v) == '{"a":"x"}',
              f"可选文本是 {v} 算没给、去掉这个键")
    check(one("a:文本 n?:数字 l?:列表 k?:是|否", '{"a":"x","n":"","l":" ","k":null}')
          == '{"a":"x"}', "可选的数字/列表/枚举空串或 null 也算没给")
    out, m = run("问JSON r = 读片段 格式 action:读|改 file?:文本 old?:文本 new?:文本\n"
                 "打印 {r.action}",
                 ['{"action":"读","file":"","old":"","new":"  "}', '{"action":"改"}'])
    check(out == "读" and len(m.calls) == 1, f"可选字段空串不触发重问：{out} / {len(m.calls)}")
    check("a 应该是非空的文本" in one("a:文本 note?:文本", '{"a":"  ","note":""}'),
          "必填文本是纯空白仍判错")
    check("应该是非空的文本" in one("a:文本", '{"a":""}'), "必填文本空串仍判错")
    check("缺少字段 a" in one("a:文本", '{"b":"x"}'), "必填缺了报缺少字段")
    check("缺少字段 a" in one("a:文本", '{"a":null}'), "必填是 null 也算缺")
    check(one("a:文本", '{"a":"x","extra":{"k":1}}') == '{"a":"x","extra":{"k":1}}',
          "多余字段不报错、原样留着")
    check("你回的是列表" in one("a:文本", '[{"a":"x"}]'), "列表不是对象")
    check("你回的是字符串" in one("a:文本", '"x"'), "字符串不是对象")
    check(one("a:文本", '```json\n{"a":"x"}\n```') == '{"a":"x"}', "容忍代码围栏")

    print("二、重问")
    out, m = run("问JSON r = 判断 格式 action:合格|重做 reason:文本\n打印 {r.action}/{r.reason}",
                 ['{"action":"基本合格"}', '{"action":"合格","reason":"对"}'])
    check(out == "合格/对", f"重问后成功：{out}")
    check(len(m.calls) == 2, f"问了两次：{len(m.calls)}")
    msgs = sent(m, 1)
    check(msgs[1] == '{"action":"基本合格"}', "重问带上了上次的回复（assistant）")
    check(m.calls[1]["messages"][1]["role"] == "assistant", "上次的回复是 assistant 消息")
    check("action 只能是 合格 或 重做，你回了 基本合格；缺少字段 reason" in msgs[2],
          f"重问提示里有具体问题：{msgs[2][:80]}")

    out, m = run("设 x = 1\n问JSON r = 判断 格式 action:合格|重做\n打印 到不了",
                 ['{"action":"差"}'] * 5)
    check(len(m.calls) == 3, f"默认重问 2 次，总共 3 次：{len(m.calls)}")
    check(out.startswith("ModelOutputError") and "第 2 行：问JSON 格式不对：" in out,
          f"用完报错带行号（模型输出错，不再是普通 DSLError）：{out[:60]}")
    check("action 只能是 合格 或 重做，你回了 差" in out, "报错里有问题列表")
    check('最后一次回复：{"action":"差"}' in out, "报错里有最后一次回复")
    check("到不了" not in out, "脚本停了")

    out, m = run("问JSON r = 判断 格式 a:文本 重问 4 次\n打印 {r.a}",
                 ['{}', '{}', '{}', '{}', '{"a":"第五次"}'])
    check(out == "第五次" and len(m.calls) == 5, f"重问 4 次：{out} / {len(m.calls)}")
    out, m = run("问JSON r = 判断 格式 a:文本 重问 0 次\n打印 {r.a}", ['{}', '{"a":"x"}'])
    check("格式不对" in out and len(m.calls) == 1, "重问 0 次：只问一次")
    out, _ = run("问JSON r = 判断 格式 a:文本 重问 6 次", ['{"a":"x"}'])
    check("最多 5 次" in out, f"重问超过 5 次报错：{out[:60]}")

    out, m = run("问JSON r = 判断 格式 a:文本\n打印 {r.a}", ["好的，我想想", '{"a":"x"}'])
    check(out == "x" and len(m.calls) == 2, "非法 JSON 也重问")
    check("回复不是合法 JSON" in sent(m, 1)[2], "重问提示说了不是合法 JSON")
    out, _ = run("问JSON r = 判断 格式 a:文本", ["胡说"] * 3)
    check("问JSON 格式不对：回复不是合法 JSON；最后一次回复：胡说" in out,
          f"一直非法 JSON 最后报错：{out[:80]}")

    print("五、确定性修复（只补末尾的 } / ]）")
    out = run("问JSON r = 问 格式 a:文本 b:列表 重问 0 次\n打印 {r.a}", ['{"a":"好","b":[1,2]']) [0]
    check(out == "好", f"少一个 }} → 补齐后通过：{out!r}")
    out = run("问JSON r = 问 格式 a:文本 b:列表 重问 0 次\n打印 {r.a}", ['{"a":"有 } 在里面","b":[{"x":1}'])[0]
    check(out == "有 } 在里面", f"少 ] 和 }} 两个、字符串里含 }} 不误判：{out!r}")
    out, m = run("问JSON r = 问 格式 a:文本 重问 1 次\n打印 {r.a}", ['{"a":"好"} ]', '{"a":"二"}'])
    check(out == "二" and "回复不是合法 JSON（" in sent(m, 1)[2] and "Extra data" in sent(m, 1)[2],
          "修不好 → 重问提示里带解析报错原文")
    print("三、语法")
    out, m = run("问JSON r = 请注意格式 要规范\n打印 {r.a}", ['{"a":"x"}'])
    check(out == "x" and m.calls[0]["type"] == "chat_json"
          and m.calls[0]["prompt"] == "请注意格式 要规范",
          "「注意格式 要规范」是提示词正文")
    out, m = run("问JSON r = 按这个格式 写 一段\n打印 {r.a}", ['{"a":"x"}'])
    check(m.calls[0]["type"] == "chat_json" and m.calls[0]["prompt"] == "按这个格式 写 一段",
          "「格式」不在词首也不认")
    out, m = run("问JSON r = 输出 格式 要规范 a:文本\n打印 {r.a}", ['{"a":"x"}'])
    check(m.calls[0]["type"] == "chat_json"
          and m.calls[0]["prompt"] == "输出 格式 要规范 a:文本",
          "「格式」后面有不是 名字:类型 的词就不认")
    out, m = run("问JSON r = 统一格式 格式 a:文本\n打印 {r.a}", ['{"a":"x"}'])
    check(out == "x" and sent(m, 0)[0].startswith("统一格式\n\n输出格式："),
          "正文里有「格式」、末尾的格式后缀照认")
    out, _ = run("问JSON r = 问 格式 a:整数", ['{"a":1}'])
    check("类型「整数」不认识" in out, f"类型写错报错：{out[:60]}")
    out, m = run("问JSON r = 问 格式 a:文本 用 快\n打印 {r.a}", ['{"a":"x"}'])
    check(out == "x" and m.calls[0]["tier"] == "快", "格式后面跟 用 快")
    d = Path(__file__).resolve().parent / "_fmt_tmp"
    d.mkdir(exist_ok=True)
    (d / "ctx.md").write_text("上下文内容", encoding="utf-8")
    for line in ("问JSON r = 问 附 ctx.md 格式 a:文本", "问JSON r = 问 格式 a:文本 附 ctx.md"):
        out, m = run(line + "\n打印 {r.a}", ['{"a":"x"}'], workdir=d)
        p = sent(m, 0)[0]
        check(out == "x" and "上下文内容" in p and "输出格式：" in p and "附" not in p,
              f"附 和 格式 两种顺序都行：{line}")
    (d / "ctx.md").unlink()
    d.rmdir()
    out, m = run("设 fmt = 格式 a:文本\n问JSON r = 问 {fmt}\n打印 {r.a}", ['{"a":"x"}'])
    check(m.calls[0]["type"] == "chat_json", "变量值里的「格式 a:文本」不当后缀")

    print("四、格式说明和旧写法")
    out, m = run("问JSON r = 判断这句 格式 result:自然|不自然 reason:文本 n?:数字\n打印 {r.result}",
                 ['{"result":"自然","reason":"ok"}'])
    p = sent(m, 0)[0]
    check(p.startswith("判断这句\n\n输出格式：只输出一个 JSON 对象"), "格式说明附在提示词末尾")
    check('- result：只能是 "自然"、"不自然" 之一' in p, "说明里有枚举可选值")
    check("- reason：文本（非空字符串）" in p, "说明里有类型")
    check("- n：数字；可选，没有就不写这个字段" in p, "说明里标了可选")
    check('示例：{"result": "自然", "reason": "……", "n": 0}' in p, "说明里有示例 JSON")

    out, m = run("问JSON d = 提取意图\n打印 {d.a}", ['{"a":"x"}'])
    check(out == "x" and m.calls[0]["type"] == "chat_json"
          and m.calls[0]["prompt"] == "提取意图" and len(m.calls) == 1,
          "旧写法照旧走 chat_json，提示词不加东西")
    out, m = run("问JSON d = 提取意图", ["胡说"])
    check("合法 JSON" in out and "格式不对" not in out and len(m.calls) == 1,
          "旧写法解析失败照旧直接报错、不重问")
    out, m = run("问JSON d = 结果 重问 2 次\n打印 {d.a}", ['{"a":"x"}'])
    check(m.calls[0]["prompt"] == "结果 重问 2 次", "没有「格式」时「重问 N 次」是正文")

    print(f"\n通过 {passed}，失败 {failed}")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
