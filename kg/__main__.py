# -*- coding: utf-8 -*-
"""知识图谱项目的启动入口。

    py -m kg              建库 + 导入 + 编译 + 起服务
    py -m kg setup        只做前三步，不起服务
    py -m kg import       只导入（知识点、条目、对照、单词）
    py -m kg --port 8200  参数透传给 gen run

`gen run` 只管建库、编译、起服务。这个项目多一件事：**导入**。建完库是空的，
知识点、条目、对照、单词都要导进去。早先只能起服务之后打接口，或者手写一段
Python——同样的代码写过三遍。

导入顺序不是随意的：节点 → 条目 → 对照。条目的 point 指向节点（外键），
对照的两端可能是条目。

导入是幂等的：节点按编号、条目按编号、词按「汉字+假名」认，重复导入是更新
不是新增，所以每次启动都导一遍是安全的，省得改完数据文件忘了导。

图怎么画不在这里——那是「节点图」控件的事（templates/frontend/graph.j2），
.ui 里写一行 `节点图 graph` 就有。早先这里还有一步「画图」，用 Python 算
布局、生成 SVG，那是把引擎该做的事挪进了应用。
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
    from tools.word_import import format_report as word_report
    from tools.word_import import import_words

    say = (lambda *a: None) if quiet else print

    say(ensure_db(PROJ))
    ensure_learn_index()

    db, qdir = PROJ / "app.db", PROJ / "queries"

    # 顺序：节点和边 → 条目 → 对照。
    #   条目的 point 指向节点（外键），所以节点要先；
    #   对照的两端可能是条目（なければならない ↔ なくてもいい），所以对照要后。
    from tools.kg_dag import (format_contrast_report, format_items_report,
                              import_contrast, import_items)
    say(format_report(import_file(db, qdir, CONTENT / "kg.jsonl",
                                  contrast_path=False)))
    say(format_items_report(import_items(db, qdir, CONTENT / "items.jsonl")))
    say(format_contrast_report(import_contrast(db, qdir,
                                               CONTENT / "contrast.jsonl")))

    words = CONTENT / "words.jsonl"
    if words.is_file():
        say(word_report(import_words(db, qdir, words)))
    else:
        say(f"没有 {words.name}，跳过单词导入")

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
