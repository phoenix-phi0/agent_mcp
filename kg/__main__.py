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
# 语法题库：每个等级一个 jsonl，沿用旧题库格式（见 verbs/quiz/_verbs.py）
BANK = ROOT / "workspace" / "japanese" / "content" / "bunpou" / "题库"


def read_bank(bank: Path) -> list:
    """读题库目录下所有 jsonl，原样返回每一行。目录不在返回空列表。

    坏行不跳过、直接抛：题库是这边生成的，坏一行说明生成出了问题，
    悄悄少几道题比报错难查。
    """
    import json
    rows = []
    for f in sorted(Path(bank).glob("*.jsonl")) if Path(bank).is_dir() else []:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise SystemExit(f"{f.name} 第 {n} 行不是合法 JSON：{e}")
    return rows


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


def ensure_new_tables(db: Path = None, entities: Path = None) -> list:
    """实体里新加了表、库里还没有的，建出来。返回这次建了哪些表。

    ensure_db 只在库不存在时建表——已有的库里不会凭空多出新实体的表，接口
    一查就是 no such table。重新生成建表语句又会先 DROP 全部表，而 attempt /
    mastery / score 是真学习记录，不能走那条路。

    所以这里只做最保守的一件事：拿实体渲染出来的建表语句，**只执行库里还
    没有的那些表**（连同它们的索引）。已有的表一律不碰——不删、不改列、
    不补列。实体里给已有的表加了字段，这里不管，那得另写 ALTER。

    建表语句从实体渲染，不手抄：手抄的跟新建库渲染出来的哪怕差一点（类型、
    默认值、外键），一边正常一边出怪问题，很难查。

    db / entities 不给就是本项目的；测试传临时的。
    """
    import re
    import sqlite3
    sys.path.insert(0, str(ROOT))
    from tools.entity import render_sql

    db = Path(db) if db else PROJ / "app.db"
    entities = Path(entities) if entities else PROJ / "entities"
    if not db.is_file():
        return []
    text = "\n\n".join(f.read_text(encoding="utf-8")
                       for f in sorted(entities.glob("*.entity")))

    # 渲染结果是「DROP 一串 + CREATE TABLE 一串 + CREATE INDEX 一串」，
    # 按语句切开，只挑 CREATE 的。DROP 一句都不执行。
    tables, indexes = {}, {}
    for stmt in re.split(r";\s*\n", render_sql(text, strict=True)):
        body = "\n".join(l for l in stmt.splitlines()
                         if l.strip() and not l.strip().startswith("--")).strip()
        m = re.match(r"CREATE TABLE (\w+)", body)
        if m:
            tables[m.group(1)] = body.replace(
                "CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
            continue
        m = re.match(r"CREATE INDEX .* ON (\w+)\(", body, re.S)
        if m:
            indexes.setdefault(m.group(1), []).append(body)

    con = sqlite3.connect(db)
    try:
        have = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        made = [t for t in tables if t not in have]
        for t in made:
            con.execute(tables[t])
            for ix in indexes.get(t, []):
                con.execute(ix)
        con.commit()
        return made
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

    # 课文挂在条目上（外键），所以排在 kg/import2 之后。文件不在就跳过：
    # 课文是后加的，没有它整个项目照样能跑。
    if (CONTENT / "lessons.jsonl").is_file():
        r = c.post("/lesson/import", json={"form": {}})
        d = r.get_json() or {}
        if r.status_code != 200:
            say(f"课文导入失败（{r.status_code}），库里的课文没动：{d.get('error') or d}")
        else:
            say(f"课文 {d.get('lessons')} 课，挂接 {d.get('links')} 条"
                f"（没挂上 {d.get('failed')}，没挂到任何条目的课 {d.get('orphans')}）")
            if d.get("note"):
                say("  " + d["note"].strip()[:300])
    else:
        say("没有 lessons.jsonl，跳过课文导入")

    # 语法题库。源文件在本项目之外（workspace/ 下，quiz 包也读它），.zs 的
    # 读JSONL 只能读项目目录里的文件，所以这里读出来放进请求——只读文件，
    # 不动内容，怎么进库在 routes/quiz.zs。题目挂在条目上，排在条目之后。
    rows = read_bank(BANK)
    if rows:
        r = c.post("/quiz/import", json={"form": {"rows": rows}})
        d = r.get_json() or {}
        if r.status_code != 200:
            say(f"题目导入失败（{r.status_code}），库里的题没动：{d.get('error') or d}")
        else:
            say(f"题目 {d.get('questions')} 道（条目对不上没进库的 {d.get('skipped')}）")
            if d.get("note"):
                say("  " + d["note"].strip()[:300])
    else:
        say(f"没有题库（{BANK}），跳过题目导入")

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
    made = ensure_new_tables()
    if made:
        say(f"  已有的库里补建了表：{'、'.join(made)}")
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
