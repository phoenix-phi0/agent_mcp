# -*- coding: utf-8 -*-
"""值里的全角空格（U+3000）字节级保留；语句分隔照旧认它（K45）。

    .venv/bin/python tests/dsl/test_fullwidth_space.py

背景：引擎曾在整行上把 U+3000 换成半角空格（dsl_core.normalize），字面量
值一起遭殃——课文标题「《{t}》　{l}　第{n}课」运行出来分隔全成了半角
（kg_v4 reading.head，kg_K44 §9-1）。修复后：

  · 值里的 U+3000 原样保留（设/返回/打印/执行参数/{名 或 默认}）；
  · 语句结构上的分隔照旧认 U+3000（str.split() 本来就当它空白，
    partition(" ") 的地方换 split_ws_once）——「打印　甲」还是「打印 甲」；
  · ASCII 空格行为一字不变；键=值 的空白校验（K16a）不受影响。
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl import DSLEngine, DSLError    # noqa: E402

U3 = "\u3000"
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(script, params=None):
    """跑脚本，回输出（打印的内容）。"""
    return DSLEngine(workdir=WS).run(script, params=params)


def run_ret(script, params=None):
    """跑脚本，回「返回」交出的 (值, 状态码)。"""
    eng = DSLEngine(workdir=WS)
    eng.run(script, params=params)
    return eng.returned


def make_workspace():
    ws = Path(tempfile.mkdtemp(prefix="fullwidth_"))
    (ws / "queries").mkdir()
    (ws / "queries" / "add.sql").write_text(
        "INSERT INTO note(title, body) VALUES(:title, :body)\n", encoding="utf-8")
    (ws / "queries" / "by_title.sql").write_text(
        "SELECT id, title, body FROM note WHERE title = :title LIMIT 1\n", encoding="utf-8")
    con = sqlite3.connect(ws / "app.db")
    con.executescript("CREATE TABLE note(id INTEGER PRIMARY KEY, title TEXT, body TEXT);")
    con.commit()
    con.close()
    (ws / "verbs" / "demo").mkdir(parents=True)
    (ws / "verbs" / "db").symlink_to(ROOT / "verbs" / "db")
    (ws / "verbs" / "common").symlink_to(ROOT / "verbs" / "common")
    (ws / "verbs" / "demo" / "_verbs.py").write_text(
        'def register(reg, workspace):\n'
        '    @reg.verb("两个参数")\n'
        '    def 试试(甲: str = "", 乙: str = "") -> str:\n'
        '        return f"甲=[{甲}] 乙=[{乙}]"\n'
        '    @reg.verb("造一个内部含全角空格的值")\n'
        '    def 造全角值() -> str:\n'
        '        return "新\\u3000品"\n', encoding="utf-8")
    (ws / "scripts").mkdir()
    (ws / "scripts" / "sub.zs").write_text(
        "打印 msg=[{msg}]\n", encoding="utf-8")
    return ws


WS = make_workspace()


def main():
    # --- 值里的 U+3000 字节级保留 ---
    v, _ = run_ret(f"设 s = 甲{U3}乙\n返回 {{s}}")
    check(v == f"甲{U3}乙" and U3.encode() in v.encode("utf-8")
          and b" " not in v.encode("utf-8"), f"设 纯文本值保留 U+3000：{v!r}")

    v, _ = run_ret(f"设 t = 教材\n设 l = N5\n"
                   f"设 head = 《{{t}}》{U3}{{l}}{U3}第1课（L1）\n返回 {{head}}")
    check(v == f"《教材》{U3}N5{U3}第1课（L1）", f"带变量展开的标题保留 U+3000（kg_v4 head 场景）：{v!r}")

    v, _ = run_ret(f"设 t = 甲{U3}乙\n设 s = 前缀{{t}}后缀\n返回 {{s}}")
    check(v == f"前缀甲{U3}乙后缀", f"变量值透传原样：{v!r}")

    v = run(f"打印 甲{U3}乙")
    check(v == f"甲{U3}乙", f"打印 值保留 U+3000：{v!r}")

    v, _ = run_ret(f"返回 甲{U3}乙")
    check(v == f"甲{U3}乙", f"返回 字面量保留 U+3000：{v!r}")

    # 值首尾的 U+3000 照旧被剪（strip 语义不变，首尾空白不属于值）
    v, _ = run_ret(f"设 s = {U3}甲{U3}\n返回 [{{s}}]")
    check(v == "[甲]", f"值首尾 U+3000 照旧剪掉：{v!r}")

    # --- {名 或 默认}：默认值是值，保留；{名 或} 取空照旧 ---
    v, _ = run_ret(f"设 s = {{无 或 甲{U3}乙}}\n返回 {{s}}")
    check(v == f"甲{U3}乙", f"或 默认值保留 U+3000：{v!r}")
    v, _ = run_ret(f"设 s = {{无{U3}或}}\n返回 [{{s}}]")
    check(v == [], f"{{名 或}} 全角空格写法取空（[] 是合法 JSON，按结构交出）：{v!r}")
    v, _ = run_ret("设 s = {无 或 甲 乙}\n返回 {s}")
    check(v == "甲 乙", f"或 ASCII 对照不变：{v!r}")

    v, _ = run_ret(f"设 x = 5\n设 y = 计算 {{x{U3}或{U3}0}} + 1\n返回 {{y}}")
    check(str(v) == "6", f"计算 里 {{名　或　默认}} 全角写法照常：{v!r}")
    v, _ = run_ret(f"设 y = 计算 {{无{U3}或{U3}7}} + 1\n返回 {{y}}")
    check(str(v) == "8", f"计算 里全角 或 取默认值：{v!r}")

    # --- 返回 尾部 全角空格+状态码：状态码照常识别 ---
    got = run_ret(f"设 s = 乙\n返回 {{s}}{U3}404")
    check(got == ("乙", 404), f"返回 状态码识别不受影响：{got!r}")

    # --- 语句结构分隔照旧认 U+3000（与改前一致）---
    v = run("打印　甲")
    check(v == "甲", f"动词与参数间全角空格照常：{v!r}")

    v = run(f"执行 scripts/sub.zs msg=你好{U3}世界")
    check(v == f"msg=[你好{U3}世界]", f"执行 参数值保留 U+3000：{v!r}")

    # 字面量值里的空白照旧是分隔（语句结构行为，U+3000 同 ASCII）
    try:
        run(f"用包 demo\n设 x = 试试 甲=一 乙=二{U3}三")
        check(False, "字面量键=值值里的 U+3000 照旧被切开（参数过多报错）")
    except DSLError:
        check(True, "字面量键=值值里的 U+3000 照旧被切开（参数过多报错）")
    # 值要带空白就装进变量（文档写法）：{变量} 里的 U+3000 原样到动词
    v = run(f"用包 demo\n设 t = 造全角值\n设 x = 试试 甲=一 乙={{t}}\n打印 {{x}}")
    check(v == f"甲=[一] 乙=[新{U3}品]", f"键=值 经{{变量}}透传 U+3000：{v!r}")
    v = run("用包 demo\n设 x = 试试 甲=一 二\n打印 {x}")
    check(v == "甲=[一] 乙=[二]", f"键=值 后跟字面量位置参数照常（ASCII 对照）：{v!r}")

    # --- K16a：db 键=值 的空白校验不受影响 ---
    try:
        run("用包 db\n设 n = 写库 app.db add title=新 品 body=正文\n")
        check(False, "db 字面量值含 ASCII 空格照旧报错")
    except DSLError:
        check(True, "db 字面量值含 ASCII 空格照旧报错")
    try:
        run(f"用包 db\n设 n = 写库 app.db add title=新{U3}品 body=正文\n")
        check(False, "db 字面量值含 U+3000 照旧被切开报错")
    except DSLError:
        check(True, "db 字面量值含 U+3000 照旧被切开报错")

    # db {变量}：内部 U+3000 合法、存进去的是 U+3000，回查一致
    out = run(f"用包 db demo\n"
              f"设 t = 造全角值\n"
              f"设 n = 写库 app.db add title={{t}} body=正文\n"
              f"设 行 = 查一行 app.db by_title title={{t}}\n"
              f"打印 [{{n}}|{{行.title}}]")
    check(out == f"[1|新{U3}品]", f"db 值内部 U+3000 照常且字节一致：{out!r}")

    print("----")
    if failed:
        print(f"通过 {passed}，失败 {failed}")
        sys.exit(1)
    print(f"通过 {passed}，失败 0")


if __name__ == "__main__":
    main()
