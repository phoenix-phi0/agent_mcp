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


def run_import(quiet: bool = False) -> int:
    """跑导入。**导入逻辑在 .zs 里，不在这儿**——这个函数只是把接口调起来。

    routes/kg_import2.zs   节点、条目、边、对照
    routes/word_import.zs  单词

    早先这两样是 Python（tools/kg_dag.py、tools/word_import.py），因为
    引擎缺两件东西：遍历拿不到下标（逐条报错说不出第几条）、可选字段缺了
    会留成 {项.after} 字面量写进库。两样都补上之后（「序号 i」和
    「{名 或}」），导入就是「读 JSONL + 遍历 + 写库」，DSL 能表达。

    不起服务也能调：Flask 的测试客户端直接打路由，跟起服务走的是同一段
    代码，不会出现「命令行导的和接口导的行为不一样」。
    """
    sys.path.insert(0, str(ROOT))
    from gen.project import make_app

    say = (lambda *a: None) if quiet else print
    app, _ = make_app(PROJ, real=False)
    c = app.test_client()

    r = c.post("/kg/import2", json={"form": {}}).get_json() or {}
    say(f"图：节点 {r.get('nodes')}，条目 {r.get('items')}，"
        f"边 {r.get('edges')}（已存在 {r.get('existing')}，"
        f"拒绝 {r.get('rejected')}），对照 {r.get('contrast')}")
    if r.get("note"):
        say("  " + r["note"].strip())

    # 词表可以有多份：words.jsonl 是从题库抽的（中文释义），
    # words_jlpt.jsonl 来自 OpenJLPT（CC BY-SA 4.0，释义是英文）。
    # 来源不同就分开放文件，将来要换掉某一批也不牵连另一批。
    files = sorted(CONTENT.glob("words*.jsonl"))
    if files:
        for f in files:
            w = c.post("/word/import2",
                       json={"form": {"file": f"content/{f.name}"}}).get_json() or {}
            say(f"单词 {f.name}：新增 {w.get('new')}，更新 {w.get('updated')}，"
                f"跳过 {w.get('skipped')}，没挂知识点 {w.get('no_point')}")
            if w.get("note"):
                say("  " + w["note"].strip()[:200])
    else:
        say("没有 words*.jsonl，跳过单词导入")
    return 0

def setup(quiet: bool = False) -> int:
    sys.path.insert(0, str(ROOT))
    from gen.project import build, ensure_db

    say = (lambda *a: None) if quiet else print

    say(ensure_db(PROJ))
    ensure_learn_index()
    run_import(quiet)

    for line in build(PROJ):
        say(line)
    return 0


def do_import() -> int:
    return run_import()


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
