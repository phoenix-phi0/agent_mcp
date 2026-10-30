# -*- coding: utf-8 -*-
"""遍历 JSON 列表文本。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_each_json_list.py

`设 x = []` 存成文本 "[]"；遍历时 JSON 列表文本要按列表走，
不能按逗号拆（空列表多跑一轮、`[1,2]` 被拆碎）。解析不了的照旧按逗号拆。
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
    script = script.replace("用包 common", "用包 common text data", 1)
    p = ROOT / "_t_eachjson.zs"
    p.write_text(script, encoding="utf-8")
    try:
        r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "tools.dsl",
                            str(p)], cwd=ROOT, capture_output=True, text=True)
        return r.stdout + r.stderr
    finally:
        p.unlink(missing_ok=True)


def lines(out, tag):
    return [l.strip() for l in out.splitlines() if l.strip().startswith(tag)]


def main():
    out = run("""用包 common
设 x = []
遍历 a 于 {x}
  打印 R:{a}
结束
打印 END
""")
    check(not lines(out, "R:") and "END" in out, f"空列表 0 轮：{out.strip()[:80]!r}")

    out = run("""用包 common
设 x = [1,2]
遍历 a 于 {x}
  打印 R:{a}
结束
""")
    check(lines(out, "R:") == ["R:1", "R:2"], f"[1,2] 两轮值 1、2：{lines(out, 'R:')}")

    out = run("""用包 common
设 x = [{"k":1}]
遍历 a 于 {x}
  打印 R:{a.k}
结束
""")
    check(lines(out, "R:") == ["R:1"], f"对象列表 {{a.k}}=1：{lines(out, 'R:')}")

    out = run("""用包 common
设 x = []
设 x = 列表加项 {x} 甲
设 x = 列表加项 {x} 乙
遍历 a 于 {x}
  打印 R:{a}
结束
""")
    check(lines(out, "R:") == ["R:甲", "R:乙"], f"列表加项照旧：{lines(out, 'R:')}")

    out = run("""用包 common
遍历 a 于 甲，乙
  打印 R:{a}
结束
""")
    check(lines(out, "R:") == ["R:甲", "R:乙"], f"「甲，乙」照旧拆：{lines(out, 'R:')}")

    out = run("""用包 common
设 x = [出错]xx，乙
遍历 a 于 {x}
  打印 R:{a}
结束
""")
    check(lines(out, "R:") == ["R:[出错]xx", "R:乙"], f"[出错]xx，乙 照旧按逗号拆：{lines(out, 'R:')}")

    print(f"\n通过 {passed}/{passed + failed}")
    sys.exit(1 if failed else 0)


main()
