# -*- coding: utf-8 -*-
"""「键=值」的值运行时含空白 → 该报错的报错，不再静默截断（K16a）。

    .venv/bin/python tests/dsl/test_kv_space.py

背景：db 包的 查询/查一行/查一值/写库 的参数是按空格切开了再传进来的，
「title=你好 世界」里的「世界」会被当成下一个参数——早先这不报错：

  · 多出来的词不带 =：报「参数要写成 名=值」，但不说哪个键、怎么改；
  · 多出来的词带 =（正文里有「E=mc2」这类）：被当成另一个参数，SQL 用不到
    就被悄悄丢掉——「公式 E=mc2」存成了「公式」；
  · 值整个是 {变量} 且值里有**首尾**空白：被 v.strip() 悄悄剪掉，跟 写库表
    （不剪）存的不一致，查询撞到别的行（教材导入同一文件去重失效的根因）。

db 包的报错带原因和改法（值可能含空格的装进对象用
查询表/查一行表/查一值表/写库表）。

**内部**空格/换行不拦：值整个是 {变量} 时切分发生在展开之前，值是完整的
（kg_v4 记作答的时间戳 at={at} 就是「2026-01-01 09:00:00」，一直工作）——
只有首尾空白会被 strip 剪掉、造成不一致，才报。

一般动词（键是声明过的参数名）的 键=值 后面跟字面量位置参数**不拦**：
「推理 规则=x 无 是 是」是正式写法（test_verb_params 专门守着），引擎区分
不了它和「值里有空格被切开」，这类只能靠 写法说明 约定用 {变量}。

不出错的按引用写法不动：{变量} 整个写在键=值 的值里（一般动词）、
执行/调用/后台执行 的参数（CALL_PARAM_RE 支持值里带空格）、
结构传参（写库表，整个字典可以带 SQL 用不到的字段）——本测试都守着。
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl import DSLEngine, DSLError          # noqa: E402
from tools.dslagent import loadcheck as LC         # noqa: E402
from tools.verbs import VerbRegistry               # noqa: E402
from tools.dsl_core import RESERVED                # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def make_workspace():
    ws = Path(tempfile.mkdtemp(prefix="kvspace_"))
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
    # 用包 只认工作目录下的 verbs/，把仓库的 db、common 链接进来
    (ws / "verbs" / "db").symlink_to(ROOT / "verbs" / "db")
    (ws / "verbs" / "common").symlink_to(ROOT / "verbs" / "common")
    (ws / "verbs" / "demo" / "_verbs.py").write_text(
        'def register(reg, workspace):\n'
        '    @reg.verb("两个参数")\n'
        '    def 试试(甲: str = "", 乙: str = "") -> str:\n'
        '        return f"甲=[{甲}] 乙=[{乙}]"\n'
        '    @reg.verb("造一个内部含空格的值")\n'
        '    def 造空格值() -> str:\n'
        '        return "你好 世界"\n'
        '    @reg.verb("造一个尾随空白的值")\n'
        '    def 造尾空白值() -> str:\n'
        '        return "第一行\\n第二行\\n"\n', encoding="utf-8")
    (ws / "scripts").mkdir()
    (ws / "scripts" / "sub.zs").write_text(
        "打印 msg=[{msg}]\n", encoding="utf-8")
    return ws


def run(ws, script, params=None):
    eng = DSLEngine(workdir=ws)
    return eng.run(script, params=params)


def main():
    ws = make_workspace()
    SUGGEST = "查一行表"

    # --- db 键=值：字面量带空格在源头被切开 → 报错，消息带行号、建议 ---
    try:
        run(ws, "用包 db\n设 n = 写库 app.db add title=你好 世界 body=正文\n")
        check(False, "db 字面量值含空格应当报错")
    except DSLError as e:
        m = str(e)
        check("第 2 行" in m, f"db 字面量值含空格报错带行号：{m[:50]}…")
        check(SUGGEST in m, "db 字面量值含空格报错带结构传参建议")

    # 多出来的词带 = ：早先被当成另一个参数、SQL 用不到就静默丢弃
    try:
        run(ws, "用包 db\n设 n = 写库 app.db add title=公式 E=mc2 body=说明\n")
        check(False, "db 值含空格挤出「词=值」应当报错")
    except DSLError as e:
        check("用不到的参数：E" in str(e), f"多余的「词=值」报「用不到的参数」：{str(e)[:40]}…")

    # --- db 键=值：{变量} 值**首尾**有空白 → 报错（早先被 strip 悄悄剪掉）---
    try:
        run(ws, "用包 db demo\n"
                "设 t = 造尾空白值\n"
                "设 行 = 查一行 app.db by_title title={t}\n")
        check(False, "db {变量}值首尾有空白应当报错")
    except DSLError as e:
        m = str(e)
        check("title" in m and "第 3 行" in m and "首尾" in m,
              f"db {{变量}}值首尾空白报错带键名、行号、原因：{m[:60]}…")
        check(SUGGEST in m, "db 值首尾空白报错带建议")

    # --- **内部**空格不拦：值整个是 {变量} 时切在展开之前，值是完整的 ---
    out = run(ws, "用包 db demo\n"
                  "设 t = 造空格值\n"
                  "设 n = 写库 app.db add title={t} body=正文\n"
                  "设 行 = 查一行 app.db by_title title={t}\n"
                  "打印 [{n}|{行.title}]")
    check(out == "[1|你好 世界]", f"内部空格照常工作（含回读一致）：{out}")

    # --- 值无空格 → 照常 ---
    out = run(ws, "用包 db\n"
                  "设 n = 写库 app.db add title=无空格 body=正文一行\n"
                  "设 行 = 查一行 app.db by_title title=无空格\n"
                  "打印 [{n}|{行.title}]")
    check(out == "[1|无空格]", f"值无空格照常工作：{out}")

    # --- 结构传参（写库表/查一行表）值含空格/换行 → 照常，逐字一致；
    #     整个字典带 SQL 用不到的字段也是正常写法（早先的「多余参数」检查不碰它）---
    ws2 = make_workspace()
    out = run(ws2, "用包 db demo\n"
                  "设 t = 造空格值\n"
                  "设 d.title = {t}\n"
                  "设 b = 造尾空白值\n"
                  "设 d.body = {b}\n"
                  "设 n = 写库表 app.db add {d}\n"
                  "设 行 = 查一行表 app.db by_title {d}\n"
                  "打印 [{n}|{行.title}|{行.body}]")
    check(out == "[1|你好 世界|第一行\n第二行\n]",
          f"写库表/查一行表 空格换行逐字一致：{out!r}")

    # --- 一般动词：键=值 后面跟字面量位置参数是合法写法（推理 规则=x 无 是 是
    #     的形式），不能拦——引擎区分不了它和「值里有空格被切开」---
    out = run(ws, "用包 demo\n"
                  "设 x = 试试 甲=一 二\n"
                  "打印 {x}")
    check(out == "甲=[一] 乙=[二]", f"键=值 后跟字面量位置参数照常（推理 式写法）：{out}")

    # 键=值 后面跟整个 {变量} 是合法旧写法（按引用），不动
    out = run(ws, "用包 demo\n"
                  "设 t = 造空格值\n"
                  "设 x = 试试 甲=一 {t}\n"
                  "打印 {x}")
    check(out == "甲=[一] 乙=[你好 世界]", f"键=值 后跟 {{变量}} 照常：{out}")

    # 键=值 的值整个是 {变量}（按引用）→ 照常（值里有空格也不报）
    out = run(ws, "用包 demo\n"
                  "设 t = 造空格值\n"
                  "设 x = 试试 甲={t} 乙=二\n"
                  "打印 {x}")
    check(out == "甲=[你好 世界] 乙=[二]", f"键=值 值按引用含空格照常：{out}")

    # --- 执行 的参数（CALL_PARAM_RE）：值里带空格本来就支持，不动 ---
    out = run(ws, "执行 scripts/sub.zs msg=你好 世界")
    check(out == "msg=[你好 世界]", f"执行 的值含空格照常：{out}")

    # --- 加载检查：合法写法（含 键=值 后跟字面量位置参数）不报 ---
    reg = VerbRegistry(reserved=RESERVED)
    reg.load_pack(ws / "verbs" / "demo", workspace=ws)
    probs = LC.check_verb_calls(["设 x = 试试 甲=一 二", "设 y = 试试 甲=一 {t}"],
                                reg, "t")
    check(len(probs) == 0, f"加载检查不报合法写法：{probs}")

    print("----")
    if failed:
        print(f"通过 {passed}，失败 {failed}")
        sys.exit(1)
    print(f"通过 {passed}，失败 0")


if __name__ == "__main__":
    main()
