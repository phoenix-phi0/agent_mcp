# -*- coding: utf-8 -*-
"""知识图谱项目的启动入口。

    py -m kg              建库 + 导入 + 画图 + 编译 + 起服务
    py -m kg setup        只做前四步，不起服务
    py -m kg import       只导入（知识点和单词）
    py -m kg svg          只重画图
    py -m kg --port 8200  参数透传给 gen run

`gen run` 只管建库、编译、起服务。这个项目另有三件事在那条路之外：

  **导入**：建完库是空的，知识点和单词都要导进去。早先只能起服务之后打
  接口，或者手写一段 Python——同样的代码写过三遍。

  **画图**：web/kg.svg 是从库里画的，导入新节点之后不重画，页面上就还是
  旧的。所以顺序必须是「导入完再画图」。

  **顺序**：画图在编译之前——编译会整个重写 web/。目前它不会删掉 kg.svg，
  但依赖「恰好不删」不可靠，不如先画后编。

导入是幂等的：节点按编号、词按「汉字+假名」认，重复导入是更新不是新增，
所以每次启动都导一遍是安全的，省得改完数据文件忘了导。
"""

import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent
ROOT = PROJ.parent
CONTENT = PROJ / "content"


def ensure_learn_index() -> None:
    """mastery 每人每个知识点只该有一行。

    .entity 表达不了多列唯一，而 mastery_bump 的 ON CONFLICT(learner, point)
    要靠这个索引才认得出「同一行」——没有它，每答一题都会新增一行，汇总
    永远是 1/1，而且不报错。边和对照的唯一索引也是这么补的。
    """
    import sqlite3
    db = PROJ / "app.db"
    if not db.is_file():
        return
    con = sqlite3.connect(db)
    try:
        if con.execute("SELECT name FROM sqlite_master WHERE type='table'"
                       " AND name='mastery'").fetchone():
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_mastery"
                        " ON mastery(learner, point)")
            con.commit()
    finally:
        con.close()


def setup(quiet: bool = False) -> int:
    sys.path.insert(0, str(ROOT))
    from gen.project import build, ensure_db
    from tools.kg_dag import format_report, import_file
    from tools.kg_svg import load, render
    from tools.word_import import format_report as word_report
    from tools.word_import import import_words

    say = (lambda *a: None) if quiet else print

    say(ensure_db(PROJ))
    ensure_learn_index()

    db, qdir = PROJ / "app.db", PROJ / "queries"
    say(format_report(import_file(db, qdir, CONTENT / "kg.jsonl")))

    words = CONTENT / "words.jsonl"
    if words.is_file():
        say(word_report(import_words(db, qdir, words)))
    else:
        say(f"没有 {words.name}，跳过单词导入")

    nodes = load(db)
    if nodes:
        svg = PROJ / "web" / "kg.svg"
        svg.parent.mkdir(parents=True, exist_ok=True)
        svg.write_text(render(nodes), encoding="utf-8")
        say(f"画图：web/kg.svg（{len(nodes)} 个节点）")
    else:
        # 库是空的（导入失败、或者数据文件还没放好）。画图会在算最长链时
        # 对空列表求 max 抛异常，说的是别的事，查起来绕。
        say("库里没有知识点，跳过画图")

    for line in build(PROJ):
        say(line)
    return 0


def do_import() -> int:
    sys.path.insert(0, str(ROOT))
    from tools.kg_dag import format_report, import_file
    from tools.word_import import format_report as word_report
    from tools.word_import import import_words

    db, qdir = PROJ / "app.db", PROJ / "queries"
    print(format_report(import_file(db, qdir, CONTENT / "kg.jsonl")))
    words = CONTENT / "words.jsonl"
    if words.is_file():
        print(word_report(import_words(db, qdir, words)))
    else:
        print(f"没有 {words.name}，跳过单词导入")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv and not argv[0].startswith("-") else "run"

    if cmd == "svg":
        sys.path.insert(0, str(ROOT))
        from tools.kg_svg import main as svg_main
        return svg_main()
    if cmd == "import":
        return do_import()
    if cmd == "setup":
        return setup()

    code = setup()
    if code:
        return code
    sys.path.insert(0, str(ROOT))
    from gen.project import main as gen_main
    # 除了开头那个子命令，其余参数（--port 之类）原样交给 gen run
    extra = argv[1:] if (argv and not argv[0].startswith("-")) else argv
    print()
    return gen_main(["run", str(PROJ)] + extra)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
