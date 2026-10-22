# -*- coding: utf-8 -*-
"""「执行」先找正在跑的脚本文件的同级目录，再找工作目录。

    .venv/bin/python tests/dsl/test_sibling_exec.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl import DSLEngine, DSLError   # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def w(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def eng(work):
    return DSLEngine(workdir=work, verbose=False)


with tempfile.TemporaryDirectory() as d:
    d = Path(d).resolve()
    work, tools = d / "proj", d / "tools"
    work.mkdir()
    # 同级目录里的脚本，workdir 里没有
    w(tools / "main.zs", "设 r = 执行 sib.zs\n返回 {r}\n")
    w(tools / "sib.zs", "返回 同级\n")
    e = eng(work); e.run_file(tools / "main.zs")
    check(e.returned and e.returned[0] == "同级", "同级脚本能被执行（workdir 里没有）")

    # 冲突：同级优先
    w(work / "sib.zs", "返回 工作目录\n")
    e = eng(work); e.run_file(tools / "main.zs")
    check(e.returned[0] == "同级", "同名冲突时同级优先")

    # 同级没有，回退 workdir
    w(tools / "main2.zs", "设 r = 执行 only_work.zs\n返回 {r}\n")
    w(work / "only_work.zs", "返回 来自workdir\n")
    e = eng(work); e.run_file(tools / "main2.zs")
    check(e.returned[0] == "来自workdir", "同级没有时回退 workdir")

    # 子脚本里再执行：同级 = 子脚本自己的目录
    w(tools / "main3.zs", "设 r = 执行 sub/child.zs\n返回 {r}\n")
    w(tools / "sub" / "child.zs", "设 r = 执行 leaf.zs\n返回 {r}\n")
    w(tools / "sub" / "leaf.zs", "返回 子目录叶子\n")
    w(tools / "leaf.zs", "返回 上层叶子\n")
    e = eng(work); e.run_file(tools / "main3.zs")
    check(e.returned[0] == "子目录叶子", "子脚本里再执行：同级是子脚本自己的目录")

    # .. 越界报错
    w(d / "outside.zs", "返回 外面\n")
    w(tools / "main4.zs", "设 r = 执行 ../outside.zs\n返回 {r}\n")
    e = eng(work)
    try:
        e.run_file(tools / "main4.zs"); ok = False; msg = ""
    except DSLError as ex:
        ok, msg = True, str(ex)
    check(ok and "越界" in msg, f"同级目录用 .. 跳出去：报错（{msg[:30]}）")

    # 字符串脚本：没有同级目录，行为不变
    e = eng(work); e.run("设 r = 执行 sib.zs\n返回 {r}\n")
    check(e.returned[0] == "工作目录", "字符串脚本只走 workdir")
    e = eng(work)
    try:
        e.run("设 r = 执行 nope.zs\n"); ok = False; msg = ""
    except DSLError as ex:
        ok, msg = True, str(ex)
    check(ok and "找不到脚本" in msg, "字符串脚本找不到：照旧报找不到脚本")

print(f"\n{passed} 通过, {failed} 失败")
sys.exit(1 if failed else 0)
