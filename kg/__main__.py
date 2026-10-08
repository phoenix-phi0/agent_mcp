# -*- coding: utf-8 -*-
"""知识图谱项目的启动入口。

    py -m kg              建库 + 导入 + 编译 + 起服务
    py -m kg setup        只做前三步，不起服务
    py -m kg import       只导入（知识点、条目、对照、单词）
    py -m kg --port 8200  参数透传给 gen run
    py -m kg --mock       模拟模式（也可设 KG_MOCK=1）；默认是真模型
    py -m kg --登录       多人模式（也可设 KG_LOGIN=1）：要登录，学习记录按账号分开
    py -m kg 建教师 <用户名> [--显示名 X]   建教师账号（交互输密码，不回显）
    py -m kg 改密 <用户名>                   改任何账号的密码（交互输入）
    py -m kg 并入 me <用户名>                把单人模式 me 的学习记录归到这个账号
                          （这三个命令都能加 --库 别的库.db，测试用临时库）
    py -m kg --help / py -m kg 建教师 --help  帮助（不建库、不起服务）

桌面入口：双击 app.pyw（学生端 /）或 teacher.pyw（教师端 /teacher，等于
app.pyw --教师 / --teacher，也可设 KG_TEACHER=1）。两个都默认单人模式。

中文子命令和选项都有英文别名，两种写法等价（对照表见下面的 COMMANDS / OPTIONS）：
建教师 create-teacher、改密 passwd、并入 merge；--显示名 --display-name、
--库 --db、--密码环境变量 --password-env、--登录 --login、--安全cookie
--secure-cookie、--不开浏览器 --no-browser、--标题 --title、--入口 --entry。
进来先把英文换成中文（canonical），后面的代码只认中文。

## 单人模式和多人模式

默认单人：不用登录，learner 是 me（app.pyw、py -m kg、gen run kg 都是）。
`--登录` / KG_LOGIN=1 开多人：除了登录接口都要登录，learner 是登录的用户名，
管理侧（教材导入、学生管理、各种导入）只许教师。怎么做到的见 routes/auth.zs
和 tools/dsl_http.py 的「认证」一节。

账号：教师只能在这里用命令行建（建教师），学生由教师在「学生管理」页建，学生
不能自己注册。密码交互输入、不回显；测试和脚本用 `--密码环境变量 变量名`，从
那个环境变量读（不在命令行上写密码，免得进 shell 历史和进程列表）。

多人模式默认也只监听 127.0.0.1；`--host 0.0.0.0` 时启动日志醒目提示：明文 http
下密码和 cookie 能被同网段的人截走，对外要放在 https 反向代理后面并加
`--安全cookie`（或 KG_SECURE_COOKIE=1）。

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


# 页面标题。教师端（「端 教师」的界面，拆到 /teacher）是「日语学习·教师端」
TITLE = "日语学习"

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

    # 别的教材系列：content/series/<code>/lessons.jsonl，每个系列单独导（按系列
    # 清空重灌，互不牵连）。下划线开头的（_example）是格式示例，不进正式导入。
    # 格式见 content/series/README.md。
    for f in sorted((CONTENT / "series").glob("*/lessons.jsonl")):
        code = f.parent.name
        if code.startswith("_") or code == "hanabira":
            continue
        r = c.post("/lesson/import", json={"form": {"series": code}})
        d = r.get_json() or {}
        if r.status_code != 200:
            say(f"系列 {code} 导入失败（{r.status_code}），库里这个系列没动：{d.get('error') or d}")
        else:
            say(f"系列 {code}：课文 {d.get('lessons')} 课，映射到条目 {d.get('links')}、"
                f"知识点 {d.get('points')}，拒收 {d.get('rejected')} 行")
            if d.get("note"):
                say("  " + d["note"].strip()[:300])

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

    for line in build(PROJ, title=TITLE):
        say(line)
    return 0


def do_import() -> int:
    return run_import()


# ----------------------------------------------------------------------
# 英文别名：中文是正名，英文是别名
# ----------------------------------------------------------------------

COMMANDS = {"建教师": "create-teacher", "改密": "passwd", "并入": "merge"}
OPTIONS = {"--显示名": "--display-name", "--库": "--db", "--密码环境变量": "--password-env",
           "--登录": "--login", "--安全cookie": "--secure-cookie",
           "--不开浏览器": "--no-browser", "--标题": "--title", "--入口": "--entry"}
# 后面跟一个值的选项：值原样留着，不当选项换（用户名、标题叫 --db 也不误伤）
VALUED = {"--显示名", "--库", "--密码环境变量", "--标题", "--入口", "--host", "--port"}
_EN_COMMANDS = {en: zh for zh, en in COMMANDS.items()}
_EN_OPTIONS = {en: zh for zh, en in OPTIONS.items()}


def canonical_options(argv: list) -> list:
    """选项的英文别名换成中文（--db x → --库 x，--db=x → --库 x），别的原样。"""
    out, skip = [], False
    for a in argv:
        if skip:
            out.append(a)
            skip = False
            continue
        head, eq, val = a.partition("=")
        zh = _EN_OPTIONS.get(head, head)
        if eq and zh in VALUED:
            out += [zh, val]  # --库=x 拆成 --库 x：手写的 _opt 只认分开写
            continue
        if zh.startswith("--"):
            a = zh + eq + val
            skip = not eq and zh in VALUED
        out.append(a)
    return out


def canonical(argv: list) -> list:
    """整条命令行：开头的子命令和后面的选项都换成中文正名。"""
    if argv and argv[0] in _EN_COMMANDS:
        argv = [_EN_COMMANDS[argv[0]]] + argv[1:]
    return argv[:1] + canonical_options(argv[1:]) if argv and not argv[0].startswith("-") \
        else canonical_options(argv)


def parse_login(argv: list, environ=None) -> tuple:
    """多人模式：(login, secure_cookie, 去掉 --登录/--安全cookie 之后的参数)。
    `py -m kg` 和 app.pyw 共用。默认单人（不登录）；--登录 或 KG_LOGIN 非空且不是 0
    才要求登录。--安全cookie / KG_SECURE_COOKIE 让登录 cookie 只走 https。
    """
    environ = os.environ if environ is None else environ
    argv = canonical_options(argv)  # app.pyw 直接调这里：--login 也认
    on = lambda k: environ.get(k, "") not in ("", "0")
    login = "--登录" in argv or on("KG_LOGIN")
    secure = "--安全cookie" in argv or on("KG_SECURE_COOKIE")
    return login, secure, [a for a in argv if a not in ("--登录", "--安全cookie")]


# 只有桌面入口 app.pyw 认：打开 /teacher 而不是 /。py -m kg 不认（浏览器里自己开 /teacher）
APP_OPTIONS = {"--教师": "--teacher"}


def parse_teacher(argv: list, environ=None) -> tuple:
    """教师端：(teacher, 去掉 --教师/--teacher 之后的参数)。app.pyw / teacher.pyw 用。
    --教师、--teacher 或 KG_TEACHER 非空且不是 0。只管开哪一页，登录不登录照旧看 --登录。
    """
    environ = os.environ if environ is None else environ
    flags = set(APP_OPTIONS) | set(APP_OPTIONS.values())
    teacher = any(a in flags for a in argv) or environ.get("KG_TEACHER", "") not in ("", "0")
    return teacher, [a for a in argv if a not in flags]


def login_line(login: bool) -> str:
    if login:
        return "登录：多人模式（--登录 / KG_LOGIN）——要登录，学习记录按账号分开，管理侧只许教师"
    return "登录：单人模式——不用登录，学习记录都记在 me 名下"


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


# ----------------------------------------------------------------------
# 账号：建教师、改密、并入 me
# ----------------------------------------------------------------------


def _db_path(argv: list) -> Path:
    """--库 别的库（测试用临时库）；不给是 kg/app.db。"""
    other = _opt(argv, "--库")
    return Path(other) if other else PROJ / "app.db"


def _db(path: Path):
    import sqlite3
    sys.path.insert(0, str(ROOT))
    if Path(path) == PROJ / "app.db":
        # 库不存在就建、已有的只加不改：user 表是后加的，老库靠这一步补上
        from gen.project import ensure_db
        ensure_db(PROJ)
    elif not Path(path).is_file():
        raise SystemExit(f"没有这个库：{path}")
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _opt(argv: list, name: str) -> str:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
        raise SystemExit(f"{name} 后面要跟一个值")
    return ""


def _positional(argv: list) -> list:
    """去掉 --选项 和它们的值之后剩下的参数。"""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
        elif a in ("--显示名", "--密码环境变量", "--库"):
            skip = True
        elif not a.startswith("--"):
            out.append(a)
    return out


def _ask_password(argv: list, environ=None) -> str:
    """新密码：--密码环境变量 X 就从环境变量 X 读（测试用），否则交互输两次、不回显。"""
    import getpass
    from tools.auth import MIN_PASSWORD
    environ = os.environ if environ is None else environ
    var = _opt(argv, "--密码环境变量")
    if var:
        pw = environ.get(var, "")
        if not pw:
            raise SystemExit(f"环境变量 {var} 是空的")
    else:
        pw = getpass.getpass("密码：")
        if getpass.getpass("再输一次：") != pw:
            raise SystemExit("两次输入不一样，没改")
    if len(pw) < MIN_PASSWORD:
        raise SystemExit(f"密码至少 {MIN_PASSWORD} 位")
    return pw


def make_teacher(argv: list, environ=None) -> int:
    """py -m kg 建教师 <用户名> [--显示名 X] [--密码环境变量 X]"""
    sys.path.insert(0, str(ROOT))
    from tools.auth import USERNAME_RE, hash_password
    argv = canonical_options(argv)
    args = _positional(argv)
    name = args[0].strip() if args else ""
    if not USERNAME_RE.match(name):
        print("用法：py -m kg 建教师 <用户名> [--显示名 X]（用户名只能用字母、数字、汉字和 _ . @ -）")
        return 2
    label = _opt(argv, "--显示名")
    con = _db(_db_path(argv))
    try:
        if con.execute("SELECT 1 FROM user WHERE username = ?", (name,)).fetchone():
            print(f"{name} 已经有了（要改密码用：py -m kg 改密 {name}）")
            return 1
        pw = _ask_password(argv, environ)
        con.execute("INSERT INTO user(username, password_hash, display_name, role, disabled)"
                    " VALUES (?, ?, ?, 'teacher', 0)", (name, hash_password(pw), label or None))
        con.commit()
    finally:
        con.close()
    print(f"建好了教师 {name}。多人模式启动：py -m kg --登录")
    return 0


def change_password(argv: list, environ=None) -> int:
    """py -m kg 改密 <用户名> [--密码环境变量 X]：教师、学生都能改（本机管理员用）。"""
    sys.path.insert(0, str(ROOT))
    from tools.auth import hash_password
    argv = canonical_options(argv)
    args = _positional(argv)
    name = args[0].strip() if args else ""
    if not name:
        print("用法：py -m kg 改密 <用户名>")
        return 2
    con = _db(_db_path(argv))
    try:
        if not con.execute("SELECT 1 FROM user WHERE username = ?", (name,)).fetchone():
            print(f"没有 {name} 这个账号")
            return 1
        pw = _ask_password(argv, environ)
        con.execute("UPDATE user SET password_hash = ? WHERE username = ?",
                    (hash_password(pw), name))
        con.commit()
    finally:
        con.close()
    print(f"{name} 的密码改好了（已经登录着的不会被踢下线，令牌到期前仍有效）")
    return 0


def learner_tables(con) -> list:
    """库里所有带 learner 列的表：学习记录、偏好、对话、做题进度……按表名排。"""
    names = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        " ORDER BY name")]
    return [t for t in names
            if any(c[1] == "learner" for c in con.execute(f'PRAGMA table_info("{t}")'))]


def merge_me(argv: list) -> int:
    """py -m kg 并入 me <用户名>：把单人模式下 me 的学习记录归到一个账号。

    以后从单人转多人用。先整库备份（app.db.merge_时间.bak，*.bak 不进 git），
    再在一个事务里把所有带 learner 列的表里 learner = 'me' 的行改成这个用户名。
    这个账号已经有任何学习记录就不做：quiz_state、learner_pref 每人一行、
    mastery 每人每点一行，两边都有的话合不到一起，得人来定留哪份。
    """
    import sqlite3
    import time
    argv = canonical_options(argv)
    args = _positional(argv)
    if len(args) != 2 or args[0] != "me":
        print("用法：py -m kg 并入 me <用户名>")
        return 2
    name = args[1].strip()
    db = _db_path(argv)
    con = _db(db)
    try:
        if not con.execute("SELECT 1 FROM user WHERE username = ?", (name,)).fetchone():
            print(f"没有 {name} 这个账号（先在学生管理页建，或 py -m kg 建教师）")
            return 1
        tables = learner_tables(con)
        mine = {t: con.execute(f'SELECT count(*) FROM "{t}" WHERE learner = ?', ("me",)).fetchone()[0]
                for t in tables}
        theirs = {t: con.execute(f'SELECT count(*) FROM "{t}" WHERE learner = ?', (name,)).fetchone()[0]
                  for t in tables}
        if not any(mine.values()):
            print("me 名下没有学习记录，不用合并")
            return 0
        if any(theirs.values()):
            busy = "、".join(f"{t} {n} 行" for t, n in theirs.items() if n)
            print(f"{name} 已经有学习记录（{busy}），没合并：两边的进度合不到一起，要人来定")
            return 1
        bak = db.with_name(f"{db.name}.merge_{time.strftime('%Y%m%d_%H%M%S')}.bak")
        dst = sqlite3.connect(bak)
        try:
            con.backup(dst)
        finally:
            dst.close()
        print(f"已备份：{bak}")
        with con:
            for t in tables:
                if mine[t]:
                    con.execute(f'UPDATE "{t}" SET learner = ? WHERE learner = ?', (name, "me"))
        for t in tables:
            if mine[t]:
                print(f"  {t}：{mine[t]} 行")
    finally:
        con.close()
    print(f"me 的学习记录归到了 {name}。单人模式下 me 从头开始。")
    return 0


HELP = {
    "": """用法：py -m kg [子命令] [选项]          中文、英文写法等价

子命令：
  （不写）                            建库 + 导入 + 编译 + 起服务
  setup                               只建库、导入、编译，不起服务
  import                              只导入（知识点、条目、对照、单词）
  建教师 / create-teacher <用户名>     建教师账号
  改密 / passwd <用户名>               改任何账号的密码
  并入 / merge me <用户名>             把单人模式 me 的学习记录归到这个账号

起服务的选项（其余原样交给 gen run）：
  --登录 / --login                    多人模式，要登录（也可设 KG_LOGIN=1）
  --安全cookie / --secure-cookie      登录 cookie 只走 https（也可设 KG_SECURE_COOKIE=1）
  --不开浏览器 / --no-browser         起服务后不开浏览器
  --标题 / --title X                  页面标题，默认「日语学习」
  --入口 / --entry X                  入口界面
  --mock / --real                     模拟 / 真模型（默认真模型；也可设 KG_MOCK=1）
  --host H / --port N                 监听地址和端口

桌面入口（app.pyw）另认：
  --教师 / --teacher                  开教师端 /teacher（也可设 KG_TEACHER=1；
                                      双击 teacher.pyw 一样）。默认单人模式，多人加 --登录，
                                      先 py -m kg create-teacher <用户名> 建教师账号

各子命令的选项：py -m kg <子命令> --help""",
    "建教师": """用法：py -m kg 建教师 <用户名> [选项]
      py -m kg create-teacher <用户名> [options]

建教师账号。密码交互输两次、不回显。
  --显示名 / --display-name X         显示名
  --密码环境变量 / --password-env 变量名   从这个环境变量读密码（测试、脚本用）
  --库 / --db 路径                    别的库（测试用临时库），默认 kg/app.db""",
    "改密": """用法：py -m kg 改密 <用户名> [选项]
      py -m kg passwd <用户名> [options]

改任何账号（教师、学生）的密码。密码交互输两次、不回显。
  --密码环境变量 / --password-env 变量名   从这个环境变量读密码（测试、脚本用）
  --库 / --db 路径                    别的库（测试用临时库），默认 kg/app.db""",
    "并入": """用法：py -m kg 并入 me <用户名> [选项]
      py -m kg merge me <用户名> [options]

把单人模式 me 的学习记录归到这个账号（先整库备份；账号已有记录就不做）。
  --库 / --db 路径                    别的库（测试用临时库），默认 kg/app.db""",
    "setup": "用法：py -m kg setup\n\n只建库、导入、编译，不起服务。",
    "import": "用法：py -m kg import\n\n只导入（知识点、条目、对照、单词）。",
}


def show_help(args: list) -> int:
    print(HELP.get(args[0] if args else "", HELP[""]))
    return 0


def serve(extra: list) -> int:
    """建库 + 导入 + 编译 + 起服务。extra 是子命令之外的参数，已换成中文正名。"""
    code = setup()
    if code:
        return code
    sys.path.insert(0, str(ROOT))
    from gen.project import main as gen_main
    # 默认真模型（跟 gen run 相反）：问老师要真回答。--mock 或 KG_MOCK=1 切回
    # 模拟，测试和不想花额度时用
    mock, extra = parse_mode(extra)
    login, secure, extra = parse_login(extra)
    print(mode_line(mock))
    print(login_line(login))
    print()
    return gen_main(["run", str(PROJ)] + ([] if mock else ["--real"])
                    + (["--登录"] if login else []) + (["--安全cookie"] if secure else [])
                    + ([] if "--标题" in extra else ["--标题", TITLE])
                    + extra)


HANDLERS = {
    "import": lambda args: do_import(),
    "setup": lambda args: setup(),
    "建教师": make_teacher,
    "改密": change_password,
    "并入": merge_me,
}


def parse(argv: list) -> tuple:
    """(处理函数, 交给它的参数)。英文别名在这里换成中文，后面只认中文。

    -h / --help 不管在哪都只打帮助：不建库、不起服务。
    """
    argv = canonical(argv)
    cmd = argv[0] if argv and not argv[0].startswith("-") else ""
    if "-h" in argv or "--help" in argv:
        return show_help, [cmd if cmd in HELP else ""]
    if cmd in HANDLERS:
        return HANDLERS[cmd], argv[1:]
    # 除了开头那个子命令，其余参数（--port 之类）原样交给 gen run
    return serve, argv[1:] if cmd else argv


def main(argv: list[str]) -> int:
    handler, args = parse(argv)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
