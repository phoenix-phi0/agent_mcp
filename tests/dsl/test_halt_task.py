# -*- coding: utf-8 -*-
"""分支式规划用的语句和动词：终止 / 派任务 / 并行派任务，加上条件里常用的取值。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_halt_task.py

  一、终止：主脚本（循环、如果里）、状态用变量、写错状态运行前就报、子脚本（调用方拿到 {状态, 原因, 停在}）
  二、派任务：成功、入参按「文件:起-止」读出附上、格式不对重答 1 次、两次都不对返回 格式不合格、
      状态/原因/结果字段的校验、模型出错、空跑不调模型
  三、并行派任务：顺序同输入、并发上限（缺省 3、可配）、一项失败不拖垮整组、空跑
  四、条件取值：列表长度 认列表变量、{r.状态 或 默认}、计数重试的写法
"""

import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import DSLEngine                         # noqa: E402
from tools.mock import MockClient                   # noqa: E402

VERBS = ROOT / "verbs"
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def engine(handler=None, workdir=None):
    m = MockClient(handler=handler or (lambda p, s=None: "嗯"), offline=True)
    return DSLEngine(m, workdir=workdir, verbose=False, verbs_root=VERBS), m


def run(script, handler=None, workdir=None, dry=False):
    """返回 (输出或报错文本, 引擎, 假客户端)。"""
    eng, m = engine(handler, workdir)
    eng.dry_run = dry
    try:
        out = eng.run(script)
    except Exception as e:
        out = f"{type(e).__name__}: {e}"
    return out.strip(), eng, m


def reply(result, state="成功", reason=""):
    return json.dumps({"result": result, "status": state, "reason": reason}, ensure_ascii=False)


def test_halt(tmp):
    print("一、终止")
    out, eng, _ = run("设 i = 0\n当 {i} 小于 9 最多 9 次\n  设 i = 计算 {i} + 1\n  如果 {i} 等于 3\n"
                      "    终止 超出预期 跑到第{i}轮\n  结束\n  打印 第{i}轮\n结束\n打印 不该到这")
    check(out == "第1轮\n第2轮\n[终止] 超出预期：跑到第3轮（停在 第 5 行）", f"循环和如果里终止整个流程，后面不跑：{out!r}")
    check(eng.halted == {"status": "超出预期", "reason": "跑到第3轮", "at": "第 5 行"}, f"engine.halted：{eng.halted}")
    check(eng.returned == (eng.halted, 200), "returned 同步成 {status, reason, at}")

    out, eng, _ = run("设 s = 失败\n终止 {s} 原因里 有空格")
    check(eng.halted and eng.halted["status"] == "失败" and eng.halted["reason"] == "原因里 有空格",
          f"状态可以是变量，原因保留空格：{eng.halted}")
    out, eng, _ = run("设 s = 完蛋\n终止 {s} x")
    check("「终止」的状态只能是" in out and "完蛋" in out, f"变量展开后不是三个状态之一报错：{out}")
    out, eng, _ = run("打印 甲\n如果 1 等于 2\n  终止 完成 x\n结束")
    check(out.startswith("DSLError: 第 3 行") and "甲" not in out, f"写错的状态在没走到的分支里也运行前就报：{out}")
    out, eng, _ = run("终止")
    check("写法" in out, f"没写状态报错：{out}")
    out, eng, _ = run("打印 甲\n打印 乙")
    check(eng.halted is None and out == "甲\n乙", "不终止时 halted 是 None")
    out, eng, _ = run("终止 成功")
    check(eng.halted == {"status": "成功", "reason": "", "at": "第 1 行"}, f"原因可以不写：{eng.halted}")

    (tmp / "sub.zs").write_text("打印 子里\n遍历 k 于 1，2\n  如果 {k} 等于 2\n    终止 失败 子任务{x}出错\n  结束\n结束\n返回 不该到这",
                                encoding="utf-8")
    out, eng, _ = run("设 r = 执行 sub.zs x=7\n打印 拿到 {r.status}|{r.reason}|{r.at}\n打印 接着走", workdir=tmp)
    check(out == "拿到 失败|子任务7出错|sub.zs 第 4 行\n接着走", f"子脚本终止：调用方拿到 {{status, reason, at}}，接着往下走：{out!r}")
    check(eng.halted is None, "子脚本终止不算调用方终止")
    out, eng, _ = run("设 r = 执行 sub.zs x=7\n如果 {r.status} 不等于 成功\n  终止 {r.status} 上游：{r.reason}\n结束\n打印 不该到这",
                      workdir=tmp)
    check(eng.halted == {"status": "失败", "reason": "上游：子任务7出错", "at": "第 3 行"},
          f"调用方按子脚本的状态自己终止：{eng.halted}")
    out, eng, _ = run("执行 sub.zs x=1\n打印 后面", workdir=tmp)
    check("后面" in out and "Error" not in out, f"不接返回值时也不是异常：{out!r}")


def test_dispatch(tmp):
    print("二、派任务")
    (tmp / "pkg").mkdir(exist_ok=True)
    (tmp / "pkg" / "a.py").write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
    seen = []

    def ok(prompt, system=None):
        seen.append(prompt)
        return reply({"note": "看过了", "edits": []})
    script = ("用包 common\n设 desc = 检查a文件：第二三行\n设 inp.src = pkg/a.py:2-3\n设 inp.hint = 第三行可疑\n"
              "设 logic = 要求：只看入参\n设 r = 派任务 {desc} {inp} {logic} note:文本,edits:列表\n"
              "打印 {r.status}|{r.reason}|{r.result.note}")
    out, eng, m = run(script, ok, workdir=tmp)
    check(out == "成功||看过了", f"成功：拿到 {{result, status, reason}}：{out!r}")
    p = seen[0] if seen else ""
    check("   2| line2" in p and "   3| line3" in p and "line1" not in p and "line4" not in p,
          "入参「文件:起-止」由动词读出那几行（带行号）附上")
    check("第三行可疑" in p and "要求：只看入参" in p and "检查a文件：第二三行" in p, "任务描述、处理逻辑、文本入参都在提示里")
    check("note" in p and "edits" in p and "超出预期" in p, "提示里有回复格式（结果字段、三种状态）")

    n = {"i": 0}

    def bad_then_ok(prompt, system=None):
        n["i"] += 1
        return "我觉得可以" if n["i"] == 1 else reply({"note": "第二次"})
    out, eng, m = run("用包 common\n设 r = 派任务 做事 无 无 note:文本\n打印 {r.status}|{r.result.note}", bad_then_ok)
    check(out == "成功|第二次" and n["i"] == 2, f"不是 JSON → 重答 1 次后合格：{out!r}（调用 {n['i']} 次）")
    second = m.calls[-1]
    msgs = second.get("messages") or []
    check(len(msgs) == 3 and msgs[1]["content"] == "我觉得可以" and "不合格" in msgs[2]["content"],
          "重答时带上上次的回复和问题")

    n["i"] = 0

    def always_bad(prompt, system=None):
        n["i"] += 1
        return reply("文本而不是对象", "成功")
    out, eng, m = run("用包 common\n设 r = 派任务 做事 无 无 note:文本\n打印 {r.status}|{r.reason}|{r.问题}", always_bad)
    check(out.startswith("失败|格式不合格|") and "result 应该是一个对象" in out and n["i"] == 2,
          f"两次都不合格 → 状态=失败 原因=格式不合格，只问 2 次：{out!r}（调用 {n['i']} 次）")

    for bad, why in ((reply("x", "完成"), "状态不在三个里"), (reply("x", "失败", ""), "失败没写原因"),
                     (reply({"note": 3}, "成功"), "结果字段类型不对"), (reply({}, "成功"), "缺结果字段"),
                     (json.dumps({"status": "成功"}), "缺结果")):
        n["i"] = 0

        def h(prompt, system=None, bad=bad):
            n["i"] += 1
            return bad
        fmt = "note:文本" if "note" in bad or "{}" in bad else ""
        out, _, _ = run(f"用包 common\n设 r = 派任务 做事 无 无 {fmt}\n打印 {{r.status}}|{{r.reason}}", h)
        check(out == "失败|格式不合格" and n["i"] == 2, f"{why} → 重答后仍不合格：{out!r}")

    out, _, _ = run("用包 common\n设 r = 派任务 做事\n打印 {r.status}|{r.reason}|{r.result}",
                    lambda p, s=None: reply("", "超出预期", "前提不成立"))
    check(out == "失败|格式不合格|", f"没给格式时结果要非空文本：{out!r}")
    out, _, _ = run("用包 common\n设 r = 派任务 做事\n打印 {r.status}|{r.reason}|{r.result}",
                    lambda p, s=None: reply("文件不存在", "超出预期", "前提不成立"))
    check(out == "超出预期|前提不成立|文件不存在", f"超出预期带原因：{out!r}")

    def boom(prompt, system=None):
        raise TimeoutError("等了 180 秒")
    out, _, _ = run("用包 common\n设 r = 派任务 做事\n打印 {r.status}|{r.reason}", boom)
    check(out == "失败|模型没有回应：等了 180 秒", f"模型出错 → 状态=失败，脚本不崩：{out!r}")
    out, _, _ = run("用包 common\n设 r = 派任务 做事 无 无 note:文字\n打印 {r.status}|{r.reason}")
    check(out.startswith("失败|回复格式写错了"), f"格式写错 → 失败：{out!r}")

    out, eng, m = run("用包 common\n设 r = 派任务 做事 无 无 edits:列表,note:文本,act:改|停\n打印 {r}", dry=True)
    got = json.loads(out) if out.startswith("{") else {}
    check(not m.calls and got.get("status") == "成功" and got.get("result", {}).get("edits") == []
          and got["result"].get("act") == "改" and got.get("空跑") is True,
          f"空跑：不调模型，给结构合法的假结果：{out}")

    eng, m = engine(lambda p, s=None: reply("好"))
    eng.system = "固定系统提示"
    eng.model = "mock-x"
    eng.run("用包 common\n设 r = 派任务 做事")
    c = m.calls[-1] if m.calls else {}
    first = (c.get("messages") or [{}])[0]
    check(c.get("type") == "chat_messages" and first.get("role") == "system"
          and first.get("content") == "固定系统提示" and c.get("model") == "mock-x",
          f"沿用引擎的客户端、系统提示和模型（同 问JSON 的通道）：{c.get('type')} {first.get('role')} {c.get('model')}")


def test_parallel():
    print("三、并行派任务")
    lock = threading.Lock()
    state = {"now": 0, "max": 0}

    def slow(prompt, system=None):
        k = int(prompt.split("任务")[2].split("号")[0]) if "号" in prompt else 0
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.05 * (7 - k))          # 前面的慢、后面的快：完成顺序和输入相反
        with lock:
            state["now"] -= 1
        return reply(f"r{k}")

    def jobs(n):
        return "\n".join(["设 jobs = 解析JSON []"]
                         + [f"设 job.任务 = 任务{i}号\n设 jobs = 列表加项 {{jobs}} {{job}}" for i in range(1, n + 1)])
    t0 = time.time()
    out, _, m = run("用包 common text\n" + jobs(6) + "\n设 rs = 并行派任务 {jobs} 2\n遍历 r 于 {rs}\n  打印 {r.result}\n结束", slow)
    check(out == "r1\nr2\nr3\nr4\nr5\nr6", f"结果顺序同输入：{out!r}")
    check(state["max"] == 2, f"并发上限 2：最多同时 {state['max']} 个")
    state.update(now=0, max=0)
    out, _, _ = run("用包 common text\n" + jobs(6) + "\n设 rs = 并行派任务 {jobs}\n设 n = 列表长度 {rs}\n打印 {n}", slow)
    check(out == "6" and state["max"] == 3, f"缺省并发 3：最多同时 {state['max']} 个，{out}")
    check(time.time() - t0 < 3, "确实是并行（总耗时远小于串行）")

    def mixed(prompt, system=None):
        if "坏" in prompt:
            raise RuntimeError("挂了")
        return reply("好")
    out, _, _ = run("用包 common text\n设 jobs = 解析JSON []\n设 jobs = 列表加项 {jobs} 好任务\n"
                    "设 jobs = 列表加项 {jobs} 坏任务\n设 jobs = 列表加项 {jobs} 好任务二\n"
                    "设 rs = 并行派任务 {jobs}\n遍历 r 于 {rs}\n  打印 {r.status}\n结束", mixed)
    check(out == "成功\n失败\n成功", f"一项失败不拖垮整组，文本项当任务描述：{out!r}")
    out, _, m = run("用包 common text\n" + jobs(3) + "\n设 rs = 并行派任务 {jobs} 2\n设 n = 列表长度 {rs}\n打印 {n} {rs.0.status}",
                    slow, dry=True)
    check(out == "3 成功" and not m.calls, f"空跑不调模型：{out!r}")
    out, _, _ = run("用包 common\n设 rs = 并行派任务 [] 2\n设 n = 列表长度 {rs}\n打印 {n}")
    check(out == "0", f"空列表返回空列表：{out!r}")


def test_repair():
    print("二b、回复格式确定性修复")
    S = "用包 common\n设 r = 派任务 做事 无 无 说明:文本\n打印 {r.status}|{r.result.说明}|{r.repaired}"
    good = '{"result":{"说明":"好"},"status":"成功","reason":""}'

    def once(text, script=S):
        n = {"i": 0}

        def h(prompt, system=None):
            n["i"] += 1
            return text
        out, _, m = run(script, h)
        return out, n["i"], m

    # 少一个 }：result 没闭合，status / reason 写进了 result 里
    out, n, _ = once('{"result":{"说明":"好","status":"成功","reason":""}')
    check(out == "成功|好|补括号+状态上提" and n == 1, f"少一个 }} → 补齐并把状态提到顶层，不重问：{out!r} 调用{n}")
    # 少一个 }：只差末尾
    out, n, _ = once('{"result":{"说明":"好"},"status":"成功","reason":""')
    check(out == "成功|好|补括号" and n == 1, f"只差末尾一个 }} → 补齐：{out!r}")
    # 少两个
    out, n, _ = once('{"result":{"说明":"好","列":[1,2],"status":"成功"')
    check(out == "成功|好|补括号+状态上提" and n == 1, f"少两个 }} → 补齐：{out!r}")
    # 字符串里的括号不算
    out, n, _ = once('{"result":{"说明":"有 } 和 ] 和 { 在字符串里"},"status":"成功","reason":""')
    check(out == "成功|有 } 和 ] 和 { 在字符串里|补括号" and n == 1, f"字符串里含括号不误判：{out!r}")
    # status/reason嵌在result里，括号配平
    out, n, _ = once('{"result":{"说明":"没做成","status":"失败","reason":"缺文件"}}',
                     "用包 common\n设 r = 派任务 做事 无 无 说明:文本\n打印 {r.status}|{r.reason}|{r.result.说明}|{r.repaired}")
    check(out == "失败|缺文件|没做成|状态上提" and n == 1, f"status/reason嵌在result里 → 提到顶层：{out!r}")
    # 正常回复不标 repaired
    out, n, _ = once(good, "用包 common\n设 r = 派任务 做事 无 无 说明:文本\n打印 [{r.repaired 或}]")
    check(out == "[]" and n == 1, f"正常回复不标 repaired：{out!r}")
    # 修好了照常走字段校验：类型不对仍重问
    out, n, m = once('{"result":{"说明":3,"status":"成功"')
    check(n == 2 and out.startswith("失败|"), f"修复后字段仍不合格 → 照常重问：{out!r} 调用{n}")
    # 修不好 → 重问，重问提示里有报错原文
    out, n, m = once('{"result":{"说明":"好"} ]')
    msgs = m.calls[-1].get("messages") or []
    check(n == 2 and len(msgs) == 3 and "回复不是合法 JSON（" in msgs[2]["content"] and "Expecting" in msgs[2]["content"],
          f"修不好 → 重问，提示里带解析报错原文：{msgs[2]['content'][:120] if len(msgs) > 2 else msgs}")
    # 重问仍坏 → 失败 格式不合格
    out, n, _ = once("胡说八道", "用包 common\n设 r = 派任务 做事 无 无 说明:文本\n打印 {r.status}|{r.reason}")
    check(out == "失败|格式不合格" and n == 2, f"重问仍坏 → 状态 失败、原因 格式不合格：{out!r}")
    # 重问用字段问题：缺字段会点名
    out, n, m = once('{"result":{"说明":"好"},"status":"成功","reason":""}', "用包 common\n设 r = 派任务 做事 无 无 说明:文本,数量:数字\n打印 {r.status}")
    msgs = m.calls[-1].get("messages") or []
    check(n == 2 and "缺少字段 result.数量" in msgs[2]["content"], "缺字段 → 重问提示里点名缺的字段")
    # 兼容旧键：模型仍回中文键 结果/状态/原因 → 转成英文键再走同一套流程，repaired 多记一步「旧键转换」
    out, n, _ = once('{"结果":{"说明":"好"},"状态":"成功","原因":""}')
    check(out == "成功|好|旧键转换" and n == 1, f"模型回旧中文键 → 兼容解析，转成英文键：{out!r}")
    out, n, _ = once('{"结果":{"说明":"没做成","状态":"失败","原因":"缺文件"}}',
                     "用包 common\n设 r = 派任务 做事 无 无 说明:文本\n打印 {r.status}|{r.reason}|{r.result.说明}|{r.repaired}")
    check(out == "失败|缺文件|没做成|旧键转换+状态上提" and n == 1, f"旧键嵌在「结果」里同样先转英文键、再状态上提：{out!r}")


def test_values():
    print("四、条件取值与重试写法")
    out, _, _ = run('用包 common\n设 a = 列表长度 甲,乙，丙\n设 xs = 解析JSON [{"a":"x,y"},{"b":1}]\n'
                    '设 b = 列表长度 {xs}\n设 e = 解析JSON []\n设 c = 列表长度 {e}\n打印 {a} {b} {c}')
    check(out == "3 2 0", f"列表长度：逗号文本 3、列表变量按项数（项里的逗号不算）2、空列表 0：{out!r}")
    out, _, _ = run("设 r.x = 1\n打印 [{r.状态 或 未知}][{r.状态 或}][{r.x 或 9}]\n如果 {r.状态 或 无} 等于 无\n  打印 缺省\n结束")
    check(out == "[未知][][1]\n缺省", f"结构字段缺省 {{r.状态 或 默认}}：{out!r}")
    out, _, _ = run("设 retry = 0\n设 ok = 否\n当 {ok} 等于 否 最多 5 次\n  如果 {retry} 不小于 2\n    跳出\n  结束\n"
                    "  设 retry = 计算 {retry} + 1\n  打印 第{retry}次\n结束\n如果 {retry} 大于 1 且 {retry} 小于 3\n  打印 次数={retry}\n结束")
    check(out == "第1次\n第2次\n次数=2", f"设 + 计算 计数，大于/小于/不小于 比较：{out!r}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="halt_task_"))
    try:
        test_halt(tmp)
        test_dispatch(tmp)
        test_parallel()
        test_repair()
        test_values()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
