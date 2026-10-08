# -*- coding: utf-8 -*-
"""循环：当 … 最多 N 次 / 重复 N 次 [计数 i] / 跳出 / 继续。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_loop_while.py

  一、当：真 / 假 / 跑满上限（{loop_full}、trace）/ 组合条件 / 上限用变量 / 上限非法 / 不写上限
  二、重复：次数、计数变量、0 次、非法
  三、跳出 / 继续：三种循环里、嵌套只管最内层、循环外报错带行号（运行前就报）
  四、混用：返回、执行子脚本、事务（跳出算提交）、问JSON（假模型）、逐项
  五、空跑与检查：假模型试跑、未闭合块、dslagent 白名单 / 补结束 / 空跑、示例 fixtures/loop_check.zs
  六、兼容与性能：以「当」「重复」开头的词不误判、1000 轮简单循环的耗时
"""

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import DSLEngine                         # noqa: E402
from tools.dsl import make_verbs                    # noqa: E402
from tools.dsl_core import split_head               # noqa: E402
from tools.mock import MockClient                   # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "loop_check.zs"
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(script, replies=None, workdir=None, verbs=None):
    """返回 (输出或报错文本, 引擎)。"""
    m = MockClient(replies=replies, offline=True)
    eng = DSLEngine(m, workdir=workdir, verbose=False, verbs=verbs)
    try:
        out = eng.run(script)
    except Exception as e:
        out = f"{type(e).__name__}: {e}"
    return out.strip(), eng


def out_of(script, **kw):
    return run(script, **kw)[0]


def test_while():
    print("一、当")
    out, eng = run("设 n = 0\n当 {n} 小于 3 最多 10 次\n  设 n = 计算 {n} + 1\n  打印 {n}\n结束\n打印 满={loop_full}")
    check(out == "1\n2\n3\n满=否", f"条件为真时跑、变假就停，正常结束 loop_full=否：{out!r}")
    check(any("当 第 3 轮" in t for t in eng.trace) and any("当 结束（条件不成立，跑了 3 轮）" in t for t in eng.trace),
          f"trace 里有每轮和结束：{eng.trace}")

    out = out_of("设 n = 5\n当 {n} 小于 3 最多 10 次\n  打印 进来了\n结束\n打印 完")
    check(out == "完", f"一开始就不成立，一轮不跑：{out!r}")

    out, eng = run("设 n = 0\n当 {n} 小于 100 最多 4 次\n  设 n = 计算 {n} + 1\n结束\n打印 n={n} 满={loop_full}\n打印 后面照常")
    check(out == "n=4 满=是\n后面照常", f"跑满上限不报错、接着往下，loop_full=是：{out!r}")
    check(any("跑满 4 轮上限" in t for t in eng.trace), f"trace 记跑满：{eng.trace[-1:]}")

    out = out_of("设 n = 0\n设 x = 甲\n当 ( {n} 小于 5 且 非 {x} 等于 乙 ) 或 {n} 等于 99 最多 10 次\n"
                 "  设 n = 计算 {n} + 1\n  如果 {n} 等于 2\n    设 x = 乙\n  结束\n结束\n打印 {n}")
    check(out == "2", f"条件含 且/或/非/括号，每轮重新求值：{out!r}")

    out = out_of("设 v = 包含 等于 或 (\n设 n = 0\n当 {v} 不等于 停 最多 3 次\n  设 n = 计算 {n} + 1\n结束\n打印 {n}")
    check(out == "3", f"变量值里有 等于/或/括号 不影响结构（先解析结构再展开）：{out!r}")

    out = out_of("设 lim = 3\n设 n = 0\n当 {n} 小于 100 最多 {lim} 次\n  设 n = 计算 {n} + 1\n结束\n打印 {n}")
    check(out == "3", f"上限用 {{变量}}：{out!r}")
    out = out_of("设 n = 0\n当 {n} 小于 100 最多 {lim 或 2} 次\n  设 n = 计算 {n} + 1\n结束\n打印 {n}")
    check(out == "2", f"上限用 {{变量 或 默认}}：{out!r}")
    out = out_of("设 n = 0\n当 {n} 小于 100 最多 5次\n  设 n = 计算 {n} + 1\n结束\n打印 {n}")
    check(out == "5", f"「5次」贴着写也认：{out!r}")

    for lim, why in (("0", "0"), ("1001", "超过 1000"), ("-2", "负数"), ("三", "不是数字"), ("{nope}", "未定义变量"),
                     ("2.5", "小数")):
        out = out_of(f"打印 前\n当 1 等于 1 最多 {lim} 次\n  打印 x\n结束")
        check("第 2 行" in out and "次数要是 1–1000 的整数" in out, f"上限{why}报错带行号：{out[:90]}")

    out = out_of("打印 前\n当 1 等于 1\n  打印 x\n结束")
    check(out.startswith("DSLError") and "第 2 行" in out and "必须写上限" in out and "最多 N 次" in out,
          f"不写上限是语法错误，提示写法：{out[:100]}")
    check("前" not in out.split("：", 1)[0], "运行之前就报（「打印 前」没执行）")
    out = out_of("当 最多 3 次\n结束")
    check("「当」后面要跟条件" in out, f"没有条件报错：{out[:60]}")
    out = out_of("当 {a} 等于 最多 3 次\n结束")
    check("看不懂的条件" in out, f"条件残缺照「如果」的规矩报：{out[:70]}")
    out = out_of("当 1 等于 1 最多 3 次\n  打印 x\n否则\n  打印 y\n结束")
    check("循环里不能直接写「否则」" in out, f"当 里写否则报错：{out[:60]}")


def test_repeat():
    print("二、重复")
    out = out_of("重复 3 次\n  打印 嗨\n结束")
    check(out == "嗨\n嗨\n嗨", f"固定次数：{out!r}")
    out = out_of("重复 3 次 计数 i\n  打印 {i}\n结束\n打印 后={i}")
    check(out == "1\n2\n3\n后=3", f"计数从 1 开始：{out!r}")
    out = out_of("设 k = 2\n重复 {k} 次 计数 i\n  打印 {i}\n结束")
    check(out == "1\n2", f"次数用变量：{out!r}")
    out = out_of("设 k = 0\n重复 {k} 次\n  打印 进来了\n结束\n打印 完")
    check(out == "完", f"0 次一轮不跑：{out!r}")
    for n in ("-1", "1001", "两", "{nope}"):
        out = out_of(f"重复 {n} 次\n  打印 x\n结束")
        check("第 1 行" in out and "次数要是 0–1000 的整数" in out, f"非法次数「{n}」报错：{out[:80]}")
    out = out_of("打印 前\n重复 3\n  打印 x\n结束")
    check("第 2 行" in out and "重复 N 次" in out, f"没写「次」是语法错误：{out[:80]}")
    out = out_of("重复 2 次 计数 a-b\n结束")
    check("非法变量名" in out, f"计数变量名非法报错：{out[:60]}")


def test_break_continue():
    print("三、跳出 / 继续")
    out = out_of("遍历 x 于 1，2，3，4\n  如果 {x} 等于 2\n    继续\n  结束\n  如果 {x} 等于 4\n    跳出\n  结束\n  打印 {x}\n结束\n打印 完")
    check(out == "1\n3\n完", f"遍历里 继续 / 跳出：{out!r}")
    out = out_of("重复 5 次 计数 i\n  如果 {i} 等于 2\n    继续\n  结束\n  如果 {i} 等于 4\n    跳出\n  结束\n  打印 {i}\n结束")
    check(out == "1\n3", f"重复里 继续 / 跳出：{out!r}")
    out, eng = run("设 n = 0\n当 1 等于 1 最多 9 次\n  设 n = 计算 {n} + 1\n  如果 {n} 小于 3\n    继续\n  结束\n"
                   "  打印 {n}\n  跳出\n结束\n打印 满={loop_full}")
    check(out == "3\n满=否", f"当 里 继续 / 跳出，跳出不算跑满：{out!r}")
    check(any("当 结束（跳出" in t for t in eng.trace) and any(t.endswith("跳出") for t in eng.trace),
          f"trace 记跳出：{eng.trace[-2:]}")

    out = out_of("重复 2 次 计数 i\n  遍历 x 于 a，b，c\n    如果 {x} 等于 b\n      跳出\n    结束\n    打印 {i}{x}\n  结束\n"
                 "  打印 外{i}\n结束")
    check(out == "1a\n外1\n2a\n外2", f"嵌套时 跳出 只结束最内层：{out!r}")
    out = out_of("当 1 等于 1 最多 2 次\n  重复 3 次 计数 j\n    如果 {j} 等于 2\n      继续\n    结束\n    打印 {j}\n  结束\n结束")
    check(out == "1\n3\n1\n3", f"嵌套时 继续 只跳最内层：{out!r}")
    out = out_of("逐项 x 于 a，b，c\n  如果 {x} 等于 b\n    跳出\n  结束\n  打印 {x}!\n结束")
    check(out == "── a ──\na!\n── b ──", f"逐项 里也认：{out!r}")

    out = out_of("打印 前\n跳出")
    check(out.startswith("DSLError") and "第 2 行" in out and "只能写在循环" in out,
          f"循环外 跳出 报错带行号：{out[:80]}")
    out = out_of("设 a = 1\n如果 {a} 等于 2\n  继续\n结束")
    check("第 3 行" in out and "「继续」只能写在循环" in out, f"不会走到的分支里写在循环外，运行前也报：{out[:80]}")
    out = out_of("重复 2 次\n结束\n如果 1 等于 1\n  跳出\n结束")
    check("第 4 行" in out, f"循环已经结束之后写的 跳出 报错：{out[:60]}")
    out = out_of("重复 2 次\n  跳出 吧\n结束")
    check("「跳出」后面不能跟别的" in out, f"跳出 后面带字报错：{out[:60]}")


def test_mixed():
    print("四、混用")
    out, eng = run("重复 5 次 计数 i\n  如果 {i} 等于 3\n    返回 到{i}了\n  结束\n  打印 {i}\n结束\n打印 不该到这")
    check(out == "1\n2" and eng.returned == ("到3了", 200), f"返回 在循环里结束整个脚本：{out!r} {eng.returned}")

    d = Path(tempfile.mkdtemp(dir=Path.home() / ".cache"))
    try:
        (d / "sub.zs").write_text("设 n = 0\n当 1 等于 1 最多 50 次\n  设 n = 计算 {n} + 1\n"
                                  "  如果 {n} 等于 {stop}\n    跳出\n  结束\n结束\n返回 {n}\n", encoding="utf-8")
        (d / "bad.zs").write_text("打印 子\n跳出\n", encoding="utf-8")
        out, eng = run("遍历 s 于 2，4\n  设 r = 执行 sub.zs stop={s}\n  打印 {r}\n  如果 {r} 等于 2\n    继续\n  结束\n"
                       "  打印 后\n结束", workdir=d)
        check(out == "2\n4\n后", f"执行 子脚本：子脚本里的循环和 跳出 只管自己，父脚本的 继续 照常：{out!r}")
        check(any(t.startswith("  第") for t in eng.trace), "子脚本的 trace 缩进记在父脚本这份里")
        out = out_of("重复 2 次\n  执行 bad.zs\n结束", workdir=d)
        check("第 2 行" in out and "只能写在循环" in out and "子" not in out.split("DSLError")[0],
              f"子脚本自己没套循环，写 跳出 报错（不会跳出父脚本的循环）：{out[:80]}")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    log = []
    verbs = make_verbs()

    @verbs.verb("", name="事务开始")
    def _b(库=""):
        log.append("开始")
        return ""

    @verbs.verb("", name="事务提交")
    def _c():
        log.append("提交")
        return ""

    @verbs.verb("", name="事务回滚")
    def _r():
        log.append("回滚")
        return ""

    @verbs.verb("", name="记")
    def _w(x=""):
        log.append(x)
        return ""

    out = out_of("重复 3 次 计数 i\n  事务 a.db\n    记 {i}\n    如果 {i} 等于 2\n      跳出\n    结束\n    记 {i}b\n  结束\n结束\n打印 完",
                 verbs=verbs)
    check(out == "完" and log == ["开始", "1", "1b", "提交", "开始", "2", "提交"],
          f"事务里跳出：提交、结束外层循环：{log}")
    log.clear()
    out = out_of("事务 a.db\n  重复 3 次 计数 i\n    如果 {i} 等于 2\n      继续\n    结束\n    记 {i}\n  结束\n结束",
                 verbs=verbs)
    check(log == ["开始", "1", "3", "提交"], f"循环在事务里，继续 不影响事务：{log}")

    replies = ['{"action":"再来","reason":"差一点"}', '{"action":"再来","reason":"还差"}', '{"action":"好了","reason":"对了"}']
    out, eng = run("设 ok = 否\n设 k = 0\n当 {ok} 等于 否 最多 5 次\n  设 k = 计算 {k} + 1\n"
                   "  问JSON v = 看第 {k} 次 格式 action:再来|好了 reason:文本\n  打印 {k}:{v.reason}\n"
                   "  如果 {v.action} 等于 好了\n    设 ok = 是\n  结束\n结束\n打印 共 {k} 次", replies=replies)
    check(out == "1:差一点\n2:还差\n3:对了\n共 3 次" and len(eng.client.calls) == 3,
          f"问JSON（假模型）在循环里，每轮一问：{out!r}")


def test_check():
    print("五、空跑与检查")
    from tools.dslagent import plan as P
    from tools.dslagent.engine import AgentEngine

    script = FIXTURE.read_text(encoding="utf-8")
    cont = '{"action":"继续","reason":"还没好"}'
    out, eng = run(script, replies=[cont, cont, '{"action":"完成","reason":"好了"}'])
    check(out.endswith("结论：修好 共 3 轮") and "第 3 轮：执行一步，上轮反馈：还没好" in out,
          f"示例：第 3 轮完成：{out.splitlines()[-1:]}")
    out, eng = run(script, replies=[cont])
    check(out.endswith("结论：没修好 6 轮还没完成") and len(eng.client.calls) == 6,
          f"示例：一直继续，跑满 6 轮停下：{out.splitlines()[-1:]}")
    out, _ = run(script, replies=[cont, '{"action":"放弃","reason":"没法改"}'])
    check("放弃：没法改" in out and out.endswith("结论：需要更多信息 第 2 轮放弃"), f"示例：放弃时跳出：{out.splitlines()[-2:]}")

    check(P.whitelist_check(script, {}) == [], f"dslagent 白名单接受：{P.whitelist_check(script, {})}")
    proj = Path(tempfile.mkdtemp(dir=Path.home() / ".cache"))
    try:
        (proj / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        err, ncalls, dout = P.dry_run(proj, proj.parent / (proj.name + "_dry"), script, {}, "任务", lambda d, s: {}, None)
        check(err == "" and ncalls >= 1 and "结论：" in dout, f"dslagent 假模型空跑通过：err={err!r} 调用 {ncalls} 次")
        err, _, _ = P.dry_run(proj, proj.parent / (proj.name + "_dry"), "打印 x\n继续\n打印 结论：修好", {}, "任务",
                              lambda d, s: {}, None)
        check("第 2 行" in err and "只能写在循环" in err, f"dslagent 空跑报循环外的 继续：{err[:80]}")
    finally:
        shutil.rmtree(proj, ignore_errors=True)
        shutil.rmtree(proj.parent / (proj.name + "_dry"), ignore_errors=True)

    fixed, n, note = P.autoclose("用包 common\n当 {a} 等于 1 最多 3 次\n  重复 2 次\n    打印 x")
    check(n == 2 and fixed.endswith("    打印 x\n  结束\n结束"), f"dslagent 补末尾「结束」认 当 / 重复：{note}")
    fixed, n, _ = P.autoclose("当 {a} 等于 1 最多 3 次\n打印 x")
    check(n == 0, "块在中间没闭合（缩进回退）不补")

    out = out_of("当 1 等于 1 最多 3 次\n  打印 x")
    check("第 1 行的块没有对应的「结束」" in out, f"当 未闭合报错：{out[:60]}")
    out = out_of("重复 2 次\n  如果 1 等于 1\n    打印 x\n结束")
    check("第 1 行的块没有对应的「结束」" in out, f"重复 里少一个 结束 报错：{out[:60]}")
    out = out_of("重复 2 次\n  打印 x\n结束\n结束")
    check("第 4 行：多余的「结束」" in out, f"多一个 结束 报错：{out[:60]}")

    eng = AgentEngine(client=MockClient(offline=True), verbose=False)
    eng.run("重复 2 次 计数 i\n  打印 {i}\n结束")
    check(eng.output == ["1", "2"], "AgentEngine（dslagent 运行期白名单）放行新循环")

    # 命令行用的是真客户端，脚本里不能有「问」
    p = ROOT / "_t_loop_trace.zs"
    p.write_text("重复 2 次 计数 i\n  打印 {i}\n结束\n", encoding="utf-8")
    try:
        r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "tools.dsl", str(p), "--trace"],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    finally:
        p.unlink(missing_ok=True)
    check(r.returncode == 0 and "[trace] 第 1 行：重复 第 2/2 轮" in r.stderr and r.stdout.split() == ["1", "2"],
          f"命令行 --trace 把 trace 打到 stderr：{[l for l in r.stderr.splitlines() if 'trace' in l]} {r.stdout.split()}")


def test_compat_perf():
    print("六、兼容与性能")
    check(split_head("当前 = 1")[0] == "当前" and split_head("重复率 x")[0] == "重复率"
          and split_head("继续学习 x")[0] == "继续学习", "「当前」「重复率」「继续学习」这类词不当关键字")
    check(split_head("当 {a} 等于 1 最多 2 次")[0] == "while" and split_head("跳出")[0] == "break",
          "「当」「跳出」单独成词才是关键字")
    out = out_of("设 当前 = 甲\n打印 {当前}\n打印 当 我们 继续 重复 跳出")
    check(out == "甲\n当 我们 继续 重复 跳出", f"变量名、打印内容里的这些字不受影响：{out!r}")
    out = out_of("遍历 x 于 a，b 序号 i\n  打印 {i}{x}\n结束")
    check(out == "1a\n2b", "旧的 遍历 行为不变")

    t0 = time.time()
    out, eng = run("设 n = 0\n当 {n} 小于 1000 最多 1000 次\n  设 n = 计算 {n} + 1\n结束\n打印 {n} {loop_full}")
    dt = time.time() - t0
    check(out == "1000 否" and dt < 5, f"当 1000 轮：{dt:.2f} 秒")
    t0 = time.time()
    out, eng = run("设 s = 0\n重复 1000 次 计数 i\n  如果 {i} 大于 500\n    继续\n  结束\n  设 s = 计算 {s} + {i}\n结束\n打印 {s}")
    dt = time.time() - t0
    check(out == "125250" and dt < 5, f"重复 1000 轮带 如果 / 继续：{dt:.2f} 秒")
    out, eng = run("重复 1000 次\n  重复 3 次\n  结束\n结束")
    check(len(eng.trace) == 2001 and "后面的不记了" in eng.trace[-1], f"trace 封顶 2000 条：{len(eng.trace)}")


def main():
    for t in (test_while, test_repeat, test_break_continue, test_mixed, test_check, test_compat_perf):
        t()
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
