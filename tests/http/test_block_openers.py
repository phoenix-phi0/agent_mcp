# -*- coding: utf-8 -*-
"""接口脚本里的块识别：凡是引擎里开块的关键字，切接口块时都要算一层。

    cd /workspace/agent_mcp && .venv/bin/python tests/http/test_block_openers.py

  一、INNER_OPENERS 与 dsl_core 的 BLOCK_OPENERS 同口径（每个开块关键字及其内部名都在）
  二、「当 … 最多 N 次」「重复 N 次」写在接口里：切出的块带完整的循环体和后面的语句，
      不再报「块没有对应的结束」；循环能跑出结果
  三、嵌套（遍历里套重复、当里套如果）、几种别名写法
  四、对照：缺结束的接口仍报「没有对应的结束」
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                                      # noqa: E402
from tools.dsl import DSLEngine, DSLError                    # noqa: E402
from tools.dsl_core import BLOCK_OPENERS, KEYWORDS           # noqa: E402
from tools.dsl_http import INNER_OPENERS, split_endpoints    # noqa: E402
from tools.mock import MockClient                            # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REG = packs.registry(["common", "text"], ROOT, cache=False)


def endpoint(script):
    eps, _ = split_endpoints(script, Path("t.zs"))
    return eps


def run_body(ep):
    e = DSLEngine(client=MockClient(offline=True), workdir=ROOT, verbose=False,
                  verbs=REG, verbs_root=packs.verbs_root())
    e.run(ep.script)
    return e


def main():
    print("一、口径")
    missing = [k for k, v in KEYWORDS.items() if v in BLOCK_OPENERS and k not in INNER_OPENERS]
    check(not missing, f"KEYWORDS 里开块的关键字都在 INNER_OPENERS（缺 {missing}）")
    check(BLOCK_OPENERS <= INNER_OPENERS, "内部名 while/repeat/… 也在")
    check({"当", "重复"} <= INNER_OPENERS, "「当」「重复」在")

    print("二、当 / 重复 写在接口里")
    src = ("接口 POST /w\n  设 n = 0\n  当 {n} 小于 3 最多 5 次\n"
           "    设 n = 计算 {n} + 1\n  结束\n  返回 {\"n\":\"{n}\"}\n结束\n"
           "\n接口 POST /after\n  返回 1\n结束\n")
    eps = endpoint(src)
    check(len(eps) == 2, f"两个接口都切出来（{len(eps)}）")
    check(eps[0].body[-1].strip().startswith("返回"), "「当」块后面的返回还在接口体里")
    e = run_body(eps[0])
    check(e.vars.get("n") in (3, "3"), f"当循环跑了 3 轮（n={e.vars.get('n')!r}）")

    src = ("接口 POST /r\n  设 n = 0\n  重复 4 次 计数 i\n"
           "    设 n = 计算 {n} + 2\n  结束\n  返回 {\"n\":\"{n}\"}\n结束\n")
    eps = endpoint(src)
    check(len(eps) == 1 and eps[0].body[-1].strip().startswith("返回"), "重复块后面的返回还在")
    e = run_body(eps[0])
    check(e.vars.get("n") in (8, "8"), f"重复 4 次（n={e.vars.get('n')!r}）")

    print("三、嵌套与别名")
    src = ("接口 POST /m\n  设 n = 0\n  设 xs = 解析JSON [1,2]\n"
           "  遍历 x 于 {xs}\n    重复 3 次\n      如果 {x} 等于 1\n        设 n = 计算 {n} + 1\n"
           "      结束\n    结束\n  结束\n"
           "  当 {n} 小于 10 最多 20 次\n    如果 {n} 小于 5\n      设 n = 计算 {n} + 2\n"
           "    否则\n      设 n = 计算 {n} + 3\n    结束\n  结束\n"
           "  返回 {\"n\":\"{n}\"}\n结束\n")
    eps = endpoint(src)
    check(len(eps) == 1 and eps[0].body[-1].strip().startswith("返回"), "嵌套后接口体完整")
    e = run_body(eps[0])
    check(e.vars.get("n") in (11, "11"), f"嵌套结果（n={e.vars.get('n')!r}）")
    src = ("接口 POST /a\n  设 n = 0\n  while {n} 小于 2 最多 5 次\n    设 n = 计算 {n} + 1\n  end\n"
           "  repeat 2 次\n    设 n = 计算 {n} + 1\n  end\n  返回 1\n结束\n")
    eps = endpoint(src)
    check(len(eps) == 1 and eps[0].body[-1].strip() == "返回 1", "while / repeat / end 别名写法")

    print("四、对照：缺结束照样报错")
    try:
        endpoint("接口 POST /x\n  当 {n} 小于 3 最多 5 次\n    设 n = 1\n结束\n")
        check(False, "缺结束没报错")
    except DSLError as ex:
        check("没有对应的「结束」" in str(ex), f"缺结束报错：{ex}")

    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
