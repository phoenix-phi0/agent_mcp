#!/usr/bin/env python
"""kg_v4 数据初始化：把旧 kg/content/ 的内容和题库转成 v4 导入格式，经 v4 自己的导入接口灌进 app.db。

固化 K59（知识点→前置边→条目→对照→课文系列/课文→单词）、K61/K62（题库，题干换行转义版）的做法。
不占端口：用 gen.project.make_app 的 Flask 测试客户端在进程内调接口，导入走的是和教师页面同一批接口。

用法（仓库根目录或任意目录都行，解释器用仓库的 .venv）：
  .venv/bin/python kg_v4/setup/init_data.py [项目目录]
      [--content 旧内容目录] [--quiz 题库目录] [--重导]
      [--teacher 用户名 [--teacher-name 显示名] [--teacher-password-env 环境变量名]]

不写死任何口令。--teacher 建教师账号时，口令从环境变量读（默认变量名 KG_TEACHER_PASSWORD），
没设环境变量且在终端里就提示输入；两者都没有就报错，不会建出没口令的账号。
账号走 v4 的做法：account_user 直插，password_hash 用 tools.auth.hash_password（scrypt）。

可重复运行（行为选择：按类别「库里已有就跳过」，加 --重导 才再灌一遍）：
  理由：导入接口多数是按编号更新、课文是按系列清空重灌，再灌一遍会覆盖老师在页面上改过的内容，
  所以默认不碰已有数据；--重导 时前置边已存在的会被接口拒绝并计入「已存在」，不算失败。
  学习记录、账号、老师设定从不清、不删。
退出码：0 成功；1 导入有拒收或条数与预期不符；2 参数/路径错误。
"""
import argparse
import collections
import getpass
import io
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()


def _find_repo():
    """引擎仓库根（有 gen/project.py 的那层）：先从本脚本往上找，再看当前目录往上。
    脚本被拷到别处（比如临时目录）时，在仓库根目录下执行也能找到。"""
    for start in (HERE.parent, Path.cwd().resolve()):
        for d in (start, *start.parents):
            if (d / "gen" / "project.py").is_file():
                return d
    sys.exit("找不到引擎仓库（要有 gen/project.py）：请在仓库根目录下执行")


REPO = _find_repo()
sys.path.insert(0, str(REPO))

DEFAULT_PROJECT = HERE.parents[1]
DEFAULT_CONTENT = REPO / "kg" / "content"
DEFAULT_QUIZ = REPO / "workspace" / "japanese" / "content" / "bunpou" / "题库"

# 默认内容（旧 kg/content/ + 仓库内题库）灌完应有的条数，K59/K61 的口径
EXPECTED = collections.OrderedDict([
    ("kg_point", 69), ("kg_edge", 112), ("kg_item", 192), ("kg_contrast", 20),
    ("lesson_series", 1), ("lesson_text", 125), ("lesson_item_link", 129),
    ("vocab_word", 8105), ("quiz_question", 466),
])

SERIES = {
    "series_code": "hanabira", "series_name": "hanabira 语法",
    "intro": "hanabira.org 的日语语法库，按中国学习者重写成中文讲解，N5–N1 共 125 课。",
    "source": "hanabira.org", "license": "CC BY 4.0", "sort_order": "0",
}


# ---------------------------------------------------------------- 转换（K59）
def _read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def convert_content(content):
    """旧 kg/content/*.jsonl → v4 导入文本（竖线/制表符分隔）。返回 {文件名: 文本}。"""
    c = Path(content)
    kg = _read_jsonl(c / "kg.jsonl")
    items = _read_jsonl(c / "items.jsonl")
    contrasts = _read_jsonl(c / "contrast.jsonl")
    links = _read_jsonl(c / "item_lessons.jsonl")
    lessons = _read_jsonl(c / "lessons.jsonl")
    words = _read_jsonl(c / "words.jsonl") + _read_jsonl(c / "words_jlpt.jsonl")

    def block(lines):
        return "\n".join(lines) + "\n"

    def examples(s):
        try:
            arr = json.loads(s)
        except Exception:
            return s
        return "@@".join(f"{e['jp']}^^{e['zh']}" for e in arr)

    by_lesson = collections.defaultdict(list)
    for x in sorted(links, key=lambda r: (r["lesson"], r["rank"])):
        by_lesson[x["lesson"]].append(x["item"])
    lesson_lines = [
        "|".join([x["code"], x["level"], x["title"], x["summary"], x["explanation"], x["formation"],
                  examples(x["examples"]), "0", x.get("source_title", ""),
                  str(int(x["code"].rsplit("-", 1)[1])), ",".join(by_lesson[x["code"]]), ""])
        for x in lessons
    ]
    return {
        "points.txt": block(f"{x['id']}|{x['label']}" for x in kg),
        "edges.tsv": block(f"{p}\t{x['id']}" for x in kg for p in x["prereq"]),
        "items.txt": block(f"{x['code']}|{x['label']}|{x['point']}|{x.get('form', '')}|{x['after']}" for x in items),
        "contrasts.txt": block(f"{x['a']}|{x['b']}" for x in contrasts),
        "lessons.txt": block(lesson_lines),
        "words.txt": block(f"{x['kanji']}|{x['kana']}|{x['meaning']}|{x['point']}" for x in words),
    }


# ---------------------------------------------------------------- 转换（K61/K62）
CATS = {"挖空", "意思", "接续", "找错句"}
OPT = re.compile(r"^([A-Z])\.\s*(.*)$")


def convert_quiz(quiz_dir, db):
    """题库 bunpou_n*.jsonl → /quiz/import 文本。条目编号要在库里（所以放在条目导入之后）。
    题干各行用字面 \\n 连接，原有反斜杠写成两个（导入时还原成真换行，见 contracts/quiz.md）。
    返回 (文本, 跳过列表, 警告列表)。"""
    import glob
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        items = {r[0] for r in con.execute("select code from kg_item")}
        lessons = {r[0] for r in con.execute("select code from lesson_text")}
    finally:
        con.close()
    lines, skipped, warn, seen = [], [], [], set()
    for f in sorted(glob.glob(os.path.join(str(quiz_dir), "bunpou_n*.jsonl"))):
        base = os.path.basename(f)
        for ln, raw in enumerate(open(f, encoding="utf-8"), 1):
            if not raw.strip():
                continue
            try:
                r = json.loads(raw)
            except Exception:
                skipped.append((base, ln, "", "JSON解析失败")); continue
            qid = r.get("id", "")

            def skip(why):
                skipped.append((base, ln, qid, why))
            miss = [k for k in ("id", "课程", "考点", "题干", "答案", "条目") if not str(r.get(k, "")).strip()]
            if miss:
                skip("字段缺失:" + ",".join(miss)); continue
            if qid in seen:
                skip("题号重复"); continue
            seen.add(qid)
            m = re.fullmatch(r"bunpou_n([1-5])", r["课程"])
            if not m:
                skip("课程名无法取等级"); continue
            level = "N" + m.group(1)
            if r["考点"] not in CATS:
                skip("考点不在枚举:" + r["考点"]); continue
            stem_lines, opts = [], []
            for t in r["题干"].split("\n"):
                mo = OPT.match(t.strip())
                if mo and (opts or mo.group(1) == "A"):
                    if mo.group(1) != chr(65 + len(opts)):
                        skip("选项字母不连续"); opts = None; break
                    opts.append(mo.group(2).strip())
                else:
                    stem_lines.append(t.strip())
            if opts is None:
                continue
            ans = r["答案"].strip()
            if r["题型"] == "选择":
                if len(opts) < 2:
                    skip("选择题拆不出选项"); continue
                if ans.upper() not in [chr(65 + i) for i in range(len(opts))]:
                    skip("答案字母不在选项里:" + ans); continue
                ans = ans.upper()
            elif opts:
                skip("非选择题却有选项行"); continue
            if r["条目"] not in items:
                skip("条目编号在v4库不存在:" + r["条目"]); continue
            if r.get("课文") and r["课文"] not in lessons:
                warn.append((qid, "课文编号在v4库不存在:" + r["课文"]))
            stem = "\\n".join(s.replace("\\", "\\\\") for s in stem_lines if s)
            acc = "^".join(a.strip() for a in r.get("可接受", []) if a.strip())
            expl = " ".join(r.get("解析", "").split("\n"))
            fields = [qid, r["课程"], level, r["考点"], stem, "^".join(opts), ans, acc, expl, r["条目"]]
            if any("|" in x or "\n" in x for x in fields):
                skip("字段含 | 或换行"); continue
            lines.append("|".join(fields))
    return "\n".join(lines) + "\n", skipped, warn


# ---------------------------------------------------------------- 灌库
def counts(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in EXPECTED}
    finally:
        con.close()


class Importer:
    def __init__(self, client):
        self.c = client
        self.bad = 0

    def upload(self, path, name, text, form=None):
        t = time.time()
        data = dict(form or {})
        data["file"] = (io.BytesIO(text.encode("utf-8")), name)
        r = self.c.post(path, data=data, content_type="multipart/form-data")
        body = r.get_data(as_text=True)
        print(f"  POST {path} -> {r.status_code}（{time.time() - t:.1f}s）{body[:160]}")
        if r.status_code != 200:
            self.bad += 1
        return r

    def edges(self, text):
        ok = dup = bad = 0
        for ln in text.splitlines():
            a, b = ln.split("\t")
            r = self.c.post("/kg/edge/add", json={"pre_code": a, "point_code": b})
            if r.status_code == 200:
                ok += 1
            elif "已存在" in r.get_data(as_text=True):
                dup += 1
            else:
                bad += 1
                print(f"    边 {a}->{b} 被拒 {r.status_code} {r.get_data(as_text=True)[:80]}")
        print(f"  POST /kg/edge/add -> 成功 {ok}、已存在 {dup}、拒收 {bad}")
        self.bad += bad


def make_teacher(root, user, display, pw):
    from tools.auth import hash_password
    con = sqlite3.connect(root / "app.db")
    try:
        if con.execute("select 1 from account_user where username=?", (user,)).fetchone():
            print(f"教师账号 {user} 已存在，没动（不改口令）")
            return
        con.execute("INSERT INTO account_user(username,password_hash,display_name,role,disabled,created_at) "
                    "VALUES(?,?,?,?,0,?)", (user, hash_password(pw), display or user, "teacher",
                                            time.strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        print(f"建了教师账号 {user}")
    finally:
        con.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="kg_v4 数据初始化（旧 kg 内容 + 题库 → v4 app.db）")
    ap.add_argument("project", nargs="?", default=str(DEFAULT_PROJECT), help="项目目录（默认 kg_v4/）")
    ap.add_argument("--content", default=str(DEFAULT_CONTENT), help="旧内容目录（默认仓库内 kg/content/）")
    ap.add_argument("--quiz", default=str(DEFAULT_QUIZ), help="题库目录（默认仓库内 workspace/japanese/content/bunpou/题库/）")
    ap.add_argument("--重导", dest="again", action="store_true", help="库里已有数据的类别也再灌一遍（默认跳过）")
    ap.add_argument("--teacher", default="", help="顺带建教师账号（用户名）")
    ap.add_argument("--teacher-name", default="", help="教师显示名（默认同用户名）")
    ap.add_argument("--teacher-password-env", default="KG_TEACHER_PASSWORD", help="放教师口令的环境变量名")
    a = ap.parse_args(argv)

    root, content, quiz = Path(a.project).resolve(), Path(a.content), Path(a.quiz)
    if not (root / "entities").is_dir() or not (root / "routes").is_dir():
        print(f"不是项目目录（缺 entities/ routes/）：{root}"); return 2
    if not (content / "kg.jsonl").is_file():
        print(f"旧内容目录不对（缺 kg.jsonl）：{content}"); return 2
    have_quiz = quiz.is_dir() and any(quiz.glob("bunpou_n*.jsonl"))
    if not have_quiz:
        print(f"题库目录没有 bunpou_n*.jsonl，题库这步会跳过：{quiz}")
    pw = ""
    if a.teacher:
        pw = os.environ.get(a.teacher_password_env, "")
        if not pw and sys.stdin.isatty():
            pw = getpass.getpass(f"教师 {a.teacher} 的口令：")
        if not pw:
            print(f"要建教师账号，但环境变量 {a.teacher_password_env} 没设、也不在终端里；不建无口令账号。"); return 2

    from gen.project import ensure_db, make_app
    print("数据库：")
    print(ensure_db(root))
    db = root / "app.db"
    if a.teacher:
        make_teacher(root, a.teacher, a.teacher_name, pw)

    # 不登录模式（单人）：导入接口的「角色 teacher」不校验，不需要账号；不占端口
    app, _router = make_app(root, real=False, login=False)
    imp = Importer(app.test_client())
    before = counts(db)
    print("灌库前：", dict(before))

    def todo(*tables):
        """这一类要不要灌：库里这些表都是空，或者给了 --重导。"""
        if a.again or all(before[t] == 0 for t in tables):
            return True
        print("  已有数据，跳过（要覆盖加 --重导）：" + "、".join(f"{t}={before[t]}" for t in tables))
        return False

    t0 = time.time()
    txt = convert_content(content)
    print("转换（K59）：", {k: len(v.splitlines()) for k, v in txt.items()})
    print("1 知识点"); todo_pt = todo("kg_point")
    if todo_pt:
        imp.upload("/kg/import/points", "points.txt", txt["points.txt"])
    print("2 前置边")
    if todo("kg_edge"):
        imp.edges(txt["edges.tsv"])
    print("3 条目")
    if todo("kg_item"):
        imp.upload("/kg/import/items", "items.txt", txt["items.txt"])
    print("4 对照")
    if todo("kg_contrast"):
        imp.upload("/kg/import/contrasts", "contrasts.txt", txt["contrasts.txt"])
    print("5 课文系列/课文（含课文-条目映射）")
    if todo("lesson_series", "lesson_text"):
        imp.upload("/lesson/import", "lessons.txt", txt["lessons.txt"], SERIES)
    print("6 单词")
    if todo("vocab_word"):
        imp.upload("/vocab/import", "words.txt", txt["words.txt"])
    print("7 题库（换行转义版）")
    if have_quiz and todo("quiz_question"):
        qtxt, skipped, warn = convert_quiz(quiz, db)
        print(f"  转换：{len(qtxt.splitlines())} 题，跳过 {len(skipped)}，警告 {len(warn)}")
        for s in skipped[:5]:
            print("    跳过", s)
        imp.upload("/quiz/import", "quiz_import.txt", qtxt)

    after = counts(db)
    print(f"\n各类条数（用时 {time.time() - t0:.1f}s）：")
    default_dirs = content.resolve() == DEFAULT_CONTENT.resolve() and quiz.resolve() == DEFAULT_QUIZ.resolve()
    off = []
    for t, n in after.items():
        mark = ""
        if default_dirs:
            mark = "  =预期" if n == EXPECTED[t] else f"  ≠预期 {EXPECTED[t]}"
            if n != EXPECTED[t]:
                off.append(t)
        print(f"  {t:18s}{n:6d}{mark}")
    if imp.bad or off:
        print(f"有问题：接口拒收/出错 {imp.bad} 处；条数不符 {off}")
        return 1
    print("完成。上线或起服务前再跑一次 ensure_db（gen run 会自动跑；直接用 make_app 起服务不会补索引）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
