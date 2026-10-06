# -*- coding: utf-8 -*-
"""知识图谱项目的启动入口。

    py -m kg              建库 + 导入 + 编译 + 起服务
    py -m kg setup        只做前三步，不起服务
    py -m kg import       只导入（知识点、条目、对照、单词）
    py -m kg --port 8200  参数透传给 gen run
    py -m kg --mock       模拟模式（也可设 KG_MOCK=1）；默认是真模型

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

import os
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent
ROOT = PROJ.parent
CONTENT = PROJ / "content"
# 语法题库：每个等级一个 jsonl，沿用旧题库格式（见 verbs/quiz/_verbs.py）
BANK = ROOT / "workspace" / "japanese" / "content" / "bunpou" / "题库"


# 课文导出给日语老师（agents/japanese.py）读：老师的工作目录是 workspace/japanese，
# 它的「语法讲解」流程读这里的 .md。课文的源头仍是 content/lessons.jsonl，这些
# 文件每次 setup 重新生成，别手改。
LESSON_OUT = ROOT / "workspace" / "japanese" / "content" / "bunpou" / "课文"
# 做题页的地址。老师讲完一课给的「去做题」链接用它；kg 服务的端口见
# routes/kg.zs 的「服务 8190-8199」，被占了往后挪的话设这个环境变量
KG_URL = os.environ.get("KG_URL", "http://127.0.0.1:8190")


def quiz_link(lesson: str, base: str = None) -> str:
    """做题页按课文出题的地址：#做题?lesson=…。界面名编码，复制粘贴不出错。"""
    from urllib.parse import quote
    return f"{(base or KG_URL).rstrip('/')}/#{quote('做题')}?lesson={quote(lesson)}"


def export_lessons(src: Path = None, out: Path = None, bank: list = None,
                   base: str = None) -> dict:
    """把课文写成老师能读的 .md，每课一个，外加一个索引。返回 {写了几课, 删了几个}。

    只管 out 目录里的文件：源里已经没有的课，对应的 .md 删掉——不删的话老师
    会讲一课已经撤掉的内容。
    """
    import json
    src = Path(src) if src else CONTENT / "lessons.jsonl"
    out = Path(out) if out else LESSON_OUT
    if not src.is_file():
        return {"written": 0, "removed": 0}
    lessons = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    counts = {}
    for q in (bank if bank is not None else read_bank(BANK)):
        if q.get("课文"):
            counts[q["课文"]] = counts.get(q["课文"], 0) + 1

    out.mkdir(parents=True, exist_ok=True)
    keep = set()
    rows = []
    for d in lessons:
        code = d["code"]
        n = counts.get(code, 0)
        try:
            examples = json.loads(d.get("examples") or "[]")
        except ValueError:
            examples = []
        parts = [f"# {d['title']}（{d['level']}，课文编号 {code}）", "", d.get("summary") or ""]
        if d.get("formation"):
            parts += ["", "## 接续", "", d["formation"]]
        parts += ["", "## 讲解", "", d.get("explanation") or ""]
        if examples:
            parts += ["", "## 例句", ""]
            for e in examples:
                parts.append(f"- {e.get('jp', '')}")
                if e.get("zh"):
                    parts.append(f"  {e['zh']}")
        parts += ["", "## 练习", ""]
        if n:
            parts += [f"这一课有 {n} 道题，在做题页做（判题和学习记录都在那边）：",
                      quiz_link(code, base)]
        else:
            parts += ["这一课还没有题。"]
        parts += ["", "（课文改写自 hanabira.org 的语法讲解，CC BY 4.0）", ""]
        (out / f"{code}.md").write_text("\n".join(parts), encoding="utf-8")
        keep.add(f"{code}.md")
        rows.append(f"| {code} | {d['level']} | {d['title']} | {d.get('summary') or ''} | {n} |")

    index = ["# 语法课文索引", "",
             "每课一个文件，文件名就是课文编号。讲解用 run_flow(\"语法讲解\", {\"lesson\": \"编号\"})。",
             "学习者问到某个语法时，在这张表里按标题找编号。", "",
             "| 课文编号 | 等级 | 标题 | 一句话 | 题数 |", "|---|---|---|---|---|"] + rows + [""]
    (out / "INDEX.md").write_text("\n".join(index), encoding="utf-8")
    keep.add("INDEX.md")

    removed = 0
    for f in out.glob("*.md"):
        if f.name not in keep:
            f.unlink()
            removed += 1
    return {"written": len(lessons), "removed": removed}


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

    # 课文给老师一份：老师只讲课，讲完给做题页的链接，练习和判题在做题页
    e = export_lessons(bank=rows)
    say(f"课文导出给老师 {e['written']} 课（删掉已撤的 {e['removed']} 个），"
        f"在 {LESSON_OUT.relative_to(ROOT)}，做题链接指向 {KG_URL}")

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

    # 库不存在就建；已有的库按实体只加不改（routes/kg.zs 里的「迁移 只加」，
    # 引擎做，见 tools/migrate.py）：attempt / mastery / score 是真学习记录，
    # 后加的表、列、索引补上，已有的表一律不重建
    say(ensure_db(PROJ))
    run_import(quiet)

    for line in build(PROJ):
        say(line)
    return 0


def do_import() -> int:
    return run_import()


def parse_mode(argv: list, environ=None) -> tuple:
    """是否模拟：(mock, 去掉 --mock/--real 之后的参数)。`py -m kg` 和 app.pyw 共用。

    默认真模型；--mock 或 KG_MOCK 非空且不是 0 才是模拟。
    """
    environ = os.environ if environ is None else environ
    mock = "--mock" in argv or environ.get("KG_MOCK", "") not in ("", "0")
    return mock, [a for a in argv if a not in ("--mock", "--real")]


def mode_label(mock: bool) -> str:
    """模式的短说明，窗口标题用：「模拟」或「真模型：平衡=cli:claude/sonnet …」。不碰 key。"""
    if mock:
        return "模拟"
    sys.path.insert(0, str(ROOT))
    from tools import config
    parts = []
    for tier in config.load().get("tiers") or {}:
        try:
            spec = config.resolve_spec(tier)
            parts.append(f"{tier}={spec[0].canonical if spec else config.resolve_model(tier)}")
        except Exception as e:  # 解析不了照样启动，只是这一行提示出来
            parts.append(f"{tier}=解析失败（{type(e).__name__}）")
    return "真模型：" + "  ".join(parts)


def mode_line(mock: bool) -> str:
    """启动时打印的一行：当前是真模型还是模拟。只写模型名，不碰 key。"""
    if mock:
        return "模式：模拟（--mock / KG_MOCK）——问老师的回复不是真模型"
    return "模式：" + mode_label(mock)


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
    # 默认真模型（跟 gen run 相反）：问老师要真回答。--mock 或 KG_MOCK=1 切回
    # 模拟，测试和不想花额度时用
    mock, extra = parse_mode(extra)
    print(mode_line(mock))
    print()
    return gen_main(["run", str(PROJ)] + ([] if mock else ["--real"]) + extra)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
