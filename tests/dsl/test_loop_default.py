# -*- coding: utf-8 -*-
"""循环序号和取值默认值。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_loop_default.py

这两样是为了让导入这类脚本能用 .zs 写。早先只能用 Python，理由正是：

  **逐条报错要说第几条**——遍历拿不到下标，几百行的文件里不说行号等于没报。
  **可选字段缺了会留成字面量**——`{项.after}` 取不到时原样保留，那串
  「{项.after}」会被当成值写进库。

原样保留是有意的（拼写错时看得见），所以不改默认行为，而是给一个显式的
写法：`{项.after 或 }`。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(script: str) -> str:
    """跑一段 .zs，返回输出。放在项目根：工作目录决定动词包往哪找。"""
    p = ROOT / "_t_loop.zs"
    p.write_text(script, encoding="utf-8")
    try:
        r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "tools.dsl",
                            str(p)], cwd=ROOT, capture_output=True, text=True)
        return r.stdout + r.stderr
    finally:
        p.unlink(missing_ok=True)


def main():
    print("一、序号")
    out = run("""用包 common
遍历 项 于 甲，乙，丙 序号 i
  打印 {i}:{项}
结束
""")
    check("1:甲" in out and "2:乙" in out and "3:丙" in out,
          f"从 1 开始数：{[l for l in out.splitlines() if ':' in l][:3]}")

    out = run("""用包 common
遍历 外 于 A，B 序号 i
  遍历 内 于 1，2 序号 j
    打印 {i}{外}{j}{内}
  结束
结束
""")
    check(all(x in out for x in ("1A11", "1A22", "2B11", "2B22")),
          "嵌套时内外各叫各的，不互相覆盖")

    out = run("""用包 common
遍历 项 于 甲，乙
  打印 {项}
结束
""")
    check("甲" in out and "乙" in out and "序号" not in out,
          "不写序号照旧能跑")

    print("\n二、取值默认值")
    out = run("""用包 common
设 有.a = 甲
打印 1={有.a 或 兜底}
打印 2={有.b 或 兜底}
打印 3={没有的 或 兜底}
打印 4=[{有.b 或}]
打印 5={有.b}
""")
    check("1=甲" in out, "有值时用原值")
    check("2=兜底" in out, "键不存在时用默认")
    check("3=兜底" in out, "变量不存在时用默认")
    check("4=[]" in out, "不写默认值就取空")
    check("5={有.b}" in out, "不写「或」照旧原样保留（拼写错时看得见）")

    out = run("""用包 common
设 甲或乙 = 好
打印 {甲或乙}
""")
    check("好" in out and "{甲或乙}" not in out,
          "变量名里带「或」字不受影响（「或」两边要有空格才算分隔）")

    print("\n三、设进变量时也认（这条最容易漏）")
    out = run("""用包 common
设 有.a = 甲
设 表 = 一，二
设 后 = {有.b 或}
打印 后=[{后}]
设 后2 = {有.b 或 默认}
打印 后2={后2}
设 原 = {表 或}
遍历 x 于 {原}
  打印 项:{x}
结束
""")
    check("后=[]" in out, "取空之后变量确实存在（不是原样保留）")
    check("后2=默认" in out, "带默认值设进变量")
    check("项:一" in out and "项:二" in out,
          "结构没被压成文本——整个参数是变量引用时要保留原对象")

    out = run("""用包 common
设 空 = {没有的 或}
遍历 y 于 {空}
  打印 不该出现
结束
打印 完
""")
    check("不该出现" not in out and "完" in out, "空的遍历零次，不报错")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
