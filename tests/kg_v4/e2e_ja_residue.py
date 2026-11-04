#!/usr/bin/env python3
"""日语界面中文残留检查（K191）：ja 账号遍历所有界面、浮层、空状态、报错提示，查还带中文的文字。

默认（进 run_all）：自建裁小的临时库 + 造数，起临时端口，全遍历，残留不在白名单就失败。
扫描（--data 目录 --port 8188 --out x.tsv --deep）：拷一份真实数据，多点按钮、多交非法值，
结果写 tsv（页面、位置、文字、类别），只报告不看白名单（--no-whitelist）。

判定规则（is_residue）。文字先去掉造数记号（「造数」开头的词）和库里日语科目的内容，再看：
  H1 含日文里没有的字（不能编码成 shift_jis，如 这们过还对错）→ 残留；
  H2 含假名，但也含中文虚词（没有 已经 可以 什么 怎么 一下 的话）→ 残留；
  H3 不含假名、含汉字（学生管理、全部）→ 残留候选；
不算残留：
  - 词表 i18n/ja.tsv 的译文本身（保存→保存 这种同形词，词表就是译者确认过的）；
  - 白名单 tests/kg_v4/ja_residue_whitelist.tsv（每条写理由）；
  - 含假名且不触发 H1、H2（就是日文）。

静态检查（不用浏览器，同样算失败）：
  S1 services、routes 里「报错 码 整串文字」都要在词表里；
  S2 带插值的报错，文字前后要有 lang 判断（同函数 ja 分支）或者进白名单；
  S3 .ui 里的标签、提示都要在词表里（或者是日文同形，进白名单）；
  S4 引擎模板里 tfmt 的键都要在词表里。

收文字用页面里常驻的轮询（350ms 一次，连续两次都在才记，翻译有 120ms 防抖），
所以几秒就消失的提示条也收得到；对话框（alert、confirm）另外记。
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
from e2e_walk import REPO, REPO_PY, build_workspace, free_port, start_server, stop_server  # noqa: E402

WHITELIST = HERE.parent / "ja_residue_whitelist.tsv"
PW = "k191-scan-temp"       # 只进自建的临时库
MARK = "造数"
KANA = re.compile(r"[぀-ヿ]")
HAN = re.compile(r"[㐀-鿿]")
ZH_WORDS = re.compile(r"没有|已经|可以|什么|怎么|一下|的话")
TOKEN = re.compile(r"zz bad!|" + MARK + r"[^\s，。、：；（）()「」『』\[\]【】/·]*")


def only_jp_chars(text):
    """True = 每个汉字都能编码成 shift_jis（日文里有这个字）。"""
    for ch in text:
        if HAN.match(ch):
            try:
                ch.encode("shift_jis")
            except UnicodeEncodeError:
                return False
    return True


def rule_of(text):
    """返回 H1/H2/H3 或空串（不算）。"""
    if not HAN.search(text):
        return ""
    if not only_jp_chars(text):
        return "H1"
    if KANA.search(text):
        return "H2" if ZH_WORDS.search(text) else ""
    return "H3"


def load_dict(root):
    d = {}
    for line in (root / "i18n" / "ja.tsv").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        k, v = line.split("\t")[:2]
        d[k] = v
    return d


def load_whitelist():
    exact, regex = {}, []
    if not WHITELIST.exists():
        return exact, regex
    for no, line in enumerate(WHITELIST.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) != 4 or not p[3].strip():
            raise SystemExit(f"白名单第 {no} 行要四列（exact|regex、文字、类别、理由），理由不能空：{line!r}")
        if p[0] == "exact":
            exact[p[1]] = (p[2], p[3])
        elif p[0] == "regex":
            regex.append((re.compile(p[1], re.S), p[2], p[3]))
        else:
            raise SystemExit(f"白名单第 {no} 行第一列只能是 exact 或 regex：{line!r}")
    return exact, regex


def whitelisted(text, wl):
    exact, regex = wl
    if text in exact:
        return exact[text]
    for rx, cat, why in regex:
        if rx.fullmatch(text):
            return (cat, why)
    return None


# ---------- 静态检查 ----------
def static_checks(root, dic, wl):
    """返回 [(位置, 文字, 类别)]。"""
    out = []
    for d in ("services", "routes"):
        for f in sorted((root / d).glob("*.zs")):
            lines = f.read_text(encoding="utf-8").splitlines()
            for no, line in enumerate(lines, 1):
                m = re.match(r"\s*报错 (\d{3}) (.+)$", line)
                if not m or not HAN.search(m.group(2)):
                    continue
                msg = m.group(2).strip()
                if KANA.search(msg):      # 已经是日文（ja 分支）
                    continue
                if "{" not in msg:
                    if msg not in dic and not whitelisted(msg, wl):
                        out.append((f"静态:报错:{f.stem}:{no}", msg, "b" if d else "a"))
                else:
                    # 带插值：往上 3 行内要有判 ja 的分支，否则就是只有中文
                    around = "\n".join(lines[max(0, no - 7):no + 1])
                    if "ja" not in around and not whitelisted(msg, wl):
                        out.append((f"静态:报错插值:{f.stem}:{no}", msg, "b"))
    # S4 引擎带插值的文案（tfmt）键都要在词表里
    tpl = (REPO / "templates" / "frontend" / "app.js.j2").read_text(encoding="utf-8")
    for key in re.findall(r"""tfmt\(["']([^"']+)["']""", tpl):
        key = key.replace("\\u3000", "\u3000")
        if key not in dic:
            out.append(("静态:引擎文案", key, "e"))
    sys.path.insert(0, str(REPO))
    try:
        from tools.ui import parse_ui               # 用引擎自己的解析，不另写一遍
    except ImportError:                             # 跑 playwright 的解释器可能没装引擎依赖
        return out
    for f in sorted((root / "ui").glob("*.ui")):
        try:
            tree = parse_ui(f.read_text(encoding="utf-8"))
        except Exception as e:      # 解析不了不是本检查的事，test_project 会报
            out.append((f"静态:ui:{f.name}", f"解析失败 {e}", "e"))
            continue
        roots = tree if isinstance(tree, list) else getattr(tree, "screens", [tree])
        for r in roots:
            for n in r.walk():
                if n.kind in ("界面", "浮层", "分组", "区域", "布局", "列表"):
                    # 界面名、分组名是否显示看模板；有标题的走动态扫描
                    names = []
                else:
                    names = [getattr(n, "label", "") or "", getattr(n, "hint", "") or ""]
                for t in names:
                    t = str(t).strip()
                    if t and HAN.search(t) and t not in dic and not whitelisted(t, wl):
                        out.append((f"静态:ui:{f.name}", t, "a"))
    return out


# ---------- 造数 ----------
ACCOUNT_CODE = (
    "import json,sqlite3,sys,time;sys.path.insert(0,%r);"
    "from tools.auth import hash_password;"
    "now=time.strftime('%%Y-%%m-%%d %%H:%%M:%%S');"
    "con=sqlite3.connect(sys.argv[1]);"
    "h=hash_password(sys.argv[2]);"
    "[con.execute('INSERT INTO account_user(username,password_hash,display_name,role,disabled,created_at,lang) "
    "VALUES(?,?,?,?,0,?,?)',(u,h,dn,role,now,lang)) for u,dn,role,lang in json.loads(sys.argv[3])];"
    "con.commit();con.close()" % str(REPO))

U_OWNER, U_EDIT, U_PUBLIC = "k191_owner", "k191_edit", "k191_pub"
U_STU, U_EMPTY = "k191_stu", "k191_empty"
AT = "2026-09-30 10:00:00"


def ins(c, table, **kw):
    cols = ",".join(kw)
    c.execute(f"INSERT INTO {table}({cols}) VALUES({','.join('?' * len(kw))})", tuple(kw.values()))
    return c.execute("select last_insert_rowid()").fetchone()[0]


def ensure_python(c):
    """真实数据里已有 Python 科目；裁小的库没有，造一个最小的（内容和译文都有）。"""
    r = c.execute("select id from subject_info where code='python'").fetchone()
    if r:
        return r[0]
    sid = ins(c, "subject_info", code="python", name="Python 编程", intro="", kind="general",
              caps='{"kg":1,"quiz":1,"progress":1,"tutor":1}', levels="入门,基础,进阶", qtypes="choice,fill",
              visibility="private", owner=U_OWNER, status="active", created_at=AT, updated_at=AT)
    ins(c, "kg_point", code="python.p1", title="变量", subject_id=sid)
    ins(c, "kg_point", code="python.p2", title="函数", subject_id=sid)
    ins(c, "kg_edge", pre_code="python.p1", point_code="python.p2", subject_id=sid)
    ins(c, "kg_item", code="python.i1", name="赋值", point_code="python.p1", after_form="", prev_code="", subject_id=sid)
    ins(c, "lesson_series", code="python.core_v1", name="Python 从零入门", intro="通过 13 课学习 Python 基础。",
        source="", license="", sort_order=100, subject_id=sid)
    ins(c, "lesson_text", code="python.lesson01", level="入门", title="第一课", summary="变量入门", explain="## 讲解\n正文",
        connection="", examples="[]", examples_edited=0, orig_title="", series_code="python.core_v1", seq=1, subject_id=sid)
    ins(c, "lesson_item_link", lesson_code="python.lesson01", item_code="python.i1", subject_id=sid)
    ins(c, "lesson_point_link", lesson_code="python.lesson01", point_code="python.p1", subject_id=sid)
    no = (c.execute("select coalesce(max(question_no),9000) from quiz_question").fetchone()[0] or 9000) + 1
    ins(c, "quiz_question", question_no=no, course="python", level="入门", category="选择", stem="选择正确的赋值",
        options='{"A":"a=1","B":"a==1"}', answer="A", accepted="", explain="赋值用等号", item_code="python.i1", subject_id=sid)
    tr = [("subject_info", "python", "name", "Python プログラミング"), ("kg_point", "python.p1", "title", "変数"),
          ("kg_point", "python.p2", "title", "関数"), ("kg_item", "python.i1", "name", "代入"),
          ("lesson_series", "python.core_v1", "name", "Python ゼロから入門"),
          ("lesson_series", "python.core_v1", "intro", "全 13 課で Python の基礎を学びます。"),
          ("lesson_text", "python.lesson01", "title", "第一課"), ("lesson_text", "python.lesson01", "summary", "変数の入門"),
          ("lesson_text", "python.lesson01", "explain", "## 解説\n本文"),
          ("quiz_question", str(no), "stem", "正しい代入を選んでください"), ("quiz_question", str(no), "explain", "代入は等号を使います")]
    for tbl, key, field, text in tr:
        c.execute("INSERT OR IGNORE INTO subject_content_translation(tbl,row_key,field,lang,text,updated_at) VALUES(?,?,?,?,?,?)",
                  (tbl, key, field, "ja", text, AT))
    return sid


def seed_names(db, src):
    """1 号科目的名字译文：正式库是上线时写的，副本和新库都按 setup/names_ja.tsv 补。"""
    c = sqlite3.connect(db)
    for line in (src / "setup" / "names_ja.tsv").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            tbl, key, field, text = line.split("\t")
            c.execute("INSERT OR IGNORE INTO subject_content_translation(tbl,row_key,field,lang,text,updated_at) VALUES(?,?,?,?,?,?)",
                      (tbl, key, field, "ja", text, AT))
    c.commit()
    c.close()


def seed(db):
    subprocess.run([str(REPO_PY), "-c", ACCOUNT_CODE, str(db), PW, json.dumps([
        (U_OWNER, U_OWNER, "teacher", "ja"), (U_EDIT, U_EDIT, "teacher", "ja"), (U_PUBLIC, U_PUBLIC, "teacher", "ja"),
        (U_STU, U_STU, "student", "ja"), (U_EMPTY, U_EMPTY, "student", "ja")])], check=True, cwd=REPO)
    c = sqlite3.connect(db)
    py = ensure_python(c)
    # 第三个科目：什么内容都没有，看空状态
    empty = ins(c, "subject_info", code="k191_empty", name=MARK + "空科目", intro="", kind="general",
                caps='{"kg":1,"quiz":1,"progress":1,"tutor":1}', levels="入门,基础,进阶", qtypes="choice,fill",
                visibility="private", owner=U_OWNER, status="active", created_at=AT, updated_at=AT)
    # 第四个：停用的草稿，看科目管理的状态文字和撤销/启用按钮
    ins(c, "subject_info", code="k191_draft", name=MARK + "草稿科目", intro="", kind="language",
        caps='{"vocab":1,"dictation":1,"lesson":1,"levels":1,"jp_judge":1,"textbook_import":1}', levels="N5,N4,N3,N2,N1", qtypes="choice,fill",
        visibility="public", owner=U_OWNER, status="draft", created_at=AT, updated_at=AT)
    ids = {"py": py, "empty": empty, "subjects": {}}
    for sid in (1, py, empty):
        ins(c, "subject_teacher", subject_id=sid, teacher=U_OWNER, role="owner", created_at=AT)
        if sid != empty:
            ins(c, "subject_teacher", subject_id=sid, teacher=U_EDIT, role="editor", created_at=AT)
        ins(c, "subject_student", subject_id=sid, learner=U_EMPTY, assigned_by=U_OWNER, status="active", created_at=AT)
        if sid != empty:
            ins(c, "subject_student", subject_id=sid, learner=U_STU, assigned_by=U_OWNER, status="active", created_at=AT)
    for sid in (1, py):
        ids["subjects"][sid] = seed_subject(c, sid)
    c.commit()
    c.close()
    return ids


def draft_result(kind, st):
    """已执行、部分执行、已撤销的草稿有结果：造真实形状，页面才走到逐条结果的分支。"""
    if st not in ("done", "partial", "undone"):
        return ""
    one = lambda **k: dict({"display_name": MARK, "label": MARK, "relay_id": 1, "setting_id": 1, "error": MARK}, **k)
    if kind == "quiz_add":
        return json.dumps({"question_nos": "1,2"})
    if kind == "relay_add":
        return json.dumps({"items": [one(ok=1), one(ok=0), one(ok=1, undo="deleted"), one(ok=1, undo="disabled")]})
    return json.dumps({"items": [one(ok=1, type="point"), one(ok=0), one(ok=1, existed=1), one(ok=1, undo="deleted")]})


def seed_subject(c, sid):
    p = c.execute("select code from kg_point where subject_id=? order by id limit 1", (sid,)).fetchone()
    point = p[0] if p else ""
    it = c.execute("select code from kg_item where subject_id=? order by id limit 1", (sid,)).fetchone()
    item = it[0] if it else ""
    q = c.execute("select question_no from quiz_question where subject_id=? order by id limit 1", (sid,)).fetchone()
    qno = q[0] if q else 1
    les = c.execute("select code, series_code from lesson_text where subject_id=? order by id limit 1", (sid,)).fetchone()
    lesson = les[0] if les else ""
    series = les[1] if les else ""
    r = {"point": point, "item": item, "lesson": lesson, "series": series}
    # 作答、掌握、得分（两个点：一个达标、一个没达标）
    for i, ok in enumerate((1, 0, 0)):
        ins(c, "progress_answer", learner=U_STU, point_code=point, question_no=qno, correct=ok, answer="A", at=f"2026-09-2{i} 10:00:00", subject_id=sid)
    ins(c, "progress_mastery", learner=U_STU, point_code=point, right_count=1, total_count=3, mastered=0, updated_at=AT, subject_id=sid)
    ins(c, "progress_score", learner=U_STU, point_code=point, score=42, at="2026-09-20 10:00:00", subject_id=sid)
    ins(c, "progress_score", learner=U_STU, point_code=point, score=51, at="2026-09-21 10:00:00", subject_id=sid)
    # 默写错词（日语科目才有单词）
    w = c.execute("select id from vocab_word order by id limit 1").fetchone()
    if w:
        for direction in ("zh2jp", "jp2kana"):
            ins(c, "dictation_attempt", learner=U_STU, word_id=w[0], direction=direction, answer="x", correct=0, hinted=0, at=AT, subject_id=sid)
    # 问老师对话：各种意图
    last = 0
    for i, intent in enumerate(("explain", "quiz", "progress", "textbook", "chat")):
        ins(c, "tutor_message", learner=U_STU, role="user", content=f"{MARK}问题{i}", intent=intent, lesson_code="", link="", links="", summary_round="", at=f"2026-09-2{i} 09:00:00", subject_id=sid)
        last = ins(c, "tutor_message", learner=U_STU, role="teacher", content=f"{MARK}回答{i}", intent=intent, lesson_code=lesson, link="", links='[{"label":"' + MARK + '链接","url":"#x"}]', summary_round="", at=f"2026-09-2{i} 09:00:01", subject_id=sid)
    r["chat"] = last
    ins(c, "report_summary", student=U_STU, summary=MARK + "学情总结", author=U_OWNER, created_at=AT, subject_id=sid)
    # 设定：三种 + 个人和全班 + 只用于下一条 + 停用
    notes = []
    for kind, stu, once, en in (("memory", U_STU, 0, 1), ("note", U_STU, 1, 1), ("card", U_STU, 0, 0), ("memory", "", 0, 1), ("note", "", 1, 1), ("card", "", 0, 0)):
        notes.append(ins(c, "teacher_rules_setting", kind=kind, student=stu, keywords=MARK + "词", content=MARK + "设定", enabled=en, once=once, version=1, author=U_OWNER, updated_at=AT, subject_id=sid))
    r["note"] = notes[0]
    r["class_note"] = notes[3]
    relays = []
    for urg, tone, dl, en, stu in (("urgent", "teacher", "", 1, U_STU), ("low", "ai", "2020-01-01", 1, U_STU), ("normal", "teacher", "", 0, U_STU),
                                   ("urgent", "teacher", "", 1, ""), ("low", "ai", "2020-01-01", 1, ""), ("normal", "ai", "", 0, "")):
        relays.append(ins(c, "teacher_rules_relay", urgency=urg, tone=tone, must_info=MARK + "传达", facts=MARK + "事实", keywords=MARK + "词", rounds=3, deadline=dl, student=stu, enabled=en, author=U_OWNER, updated_at=AT, subject_id=sid))
    r["relay"] = relays[0]
    ins(c, "teacher_rules_relay_state", relay_id=relays[0], student=U_STU, rounds_done=3, finished=1, confirmed=1, updated_at=AT)
    ins(c, "teacher_rules_relay_state", relay_id=relays[3], student=U_STU, rounds_done=1, finished=0, confirmed=0, updated_at=AT)
    ins(c, "teacher_rules_relay_state", relay_id=relays[4], student=U_STU, rounds_done=3, finished=1, confirmed=0, updated_at=AT)
    ins(c, "teacher_rules_setting_use", reply_id=last, student=U_STU, setting_ids=f"{notes[0]},{notes[1]},99999", setting_versions="1,1,1", at=AT, subject_id=sid)
    ins(c, "teacher_rules_relay_use", reply_id=last, student=U_STU, relay_ids=f"{relays[0]},99998", at=AT, subject_id=sid)
    # 教师助手：对话、各种草稿、附件、材料（负责人和协作都造）
    drafts = []
    for t in (U_OWNER, U_EDIT):
        for i in range(2):
            ins(c, "teacher_assist_message", teacher=t, role="user", content=f"{MARK}提问{i}", intent="chat", student="", point="", status="ok", at=AT, subject_id=sid)
            ins(c, "teacher_assist_message", teacher=t, role="assistant", content=f"{MARK}回答{i}", intent="chat", student="", point="", status="ok", at=AT, subject_id=sid)
        for kind in ("quiz_add", "relay_add", "setting_save", "kg_add"):
            for st in ("pending", "running", "done", "partial", "failed", "discarded", "undoing", "undone"):
                drafts.append(ins(c, "teacher_assist_draft", teacher=t, subject_id=sid, kind=kind, title=MARK + "草稿", payload="{}", preview=MARK + "预览", snapshot="{}", result=draft_result(kind, st), status=st, claim="", error=MARK + "错误" if st == "failed" else "", source_msg_id=0, replaces_id=0, created_at=AT, decided_at=AT, undone_at=""))
        ins(c, "teacher_assist_file", teacher=t, subject_id=sid, name=MARK + "附件.txt", ext="txt", size=2048, path="", pages=1, chars=12, text=MARK, stats="{}", rows=0, status="ok", attached=1, created_at=AT, last_used_at=AT)
        ins(c, "teacher_assist_file", teacher=t, subject_id=sid, name=MARK + "附件2.csv", ext="csv", size=20, path="", pages=0, chars=12, text=MARK, stats="{}", rows=3, status="ok", attached=0, created_at=AT, last_used_at=AT)
        for kind in ("lesson_plan", "exercise", "handout", "report"):
            for st in ("draft", "saved"):
                m = ins(c, "teacher_assist_material", teacher=t, subject_id=sid, kind=kind, title=MARK + "材料", content=MARK + "内容", status=st, source_msg_id=0, file_id=0, created_at=AT, updated_at=AT)
                r.setdefault("material", m)
    r["draft"] = drafts[0]
    r["drafts"] = drafts[:32]
    # 教材导入：任务（每种状态）、块（每种状态）、草稿课（每种状态）
    jobs = []
    for st in ("处理中", "待审", "已导入", "失败", "已撤下"):
        jobs.append(ins(c, "textbook_import_task", series_code=f"k191s{sid}{len(jobs)}", series_name=MARK + "系列", source=MARK + "来源", license="CC", code_prefix=f"k191s{sid}{len(jobs)}", file_name=MARK + "文件.md", raw_text=f"{MARK}{sid}{len(jobs)}", status=st, fail_reason=MARK + "原因" if st == "失败" else "", report='{"imported":1,"rejected":[{"code":"x","reason":"' + MARK + '"}]}' if st == "已导入" else "", display_title=MARK + "标题", created_at=AT, lesson_level="全部", rewrite=1, overwrite=0, subject_id=sid))
    job = jobs[1]
    r["job"] = job
    r["jobs"] = jobs
    chunk = 0
    for i, st in enumerate(("待处理", "处理中", "完成", "失败")):
        chunk = ins(c, "textbook_import_chunk", task_id=job, seq=i + 1, title=MARK + "块", content=MARK, status=st, fail_reason=MARK + "原因" if st == "失败" else "", retry_count=1)
    level = "N5" if sid == 1 else "入门"
    dr = 0
    for i, st in enumerate(("待审", "通过", "驳回", "待审")):
        dr = ins(c, "textbook_import_draft", task_id=job, chunk_id=chunk, code=f"k191d{sid}{i}", level=level, title=MARK + "课", summary=MARK, explain=MARK, connection=MARK, examples='[{"jp":"あ","zh":"' + MARK + '"}]', examples_edited=0, orig_title=MARK, seq=i + 1, item_codes=item if i != 3 else "", point_codes=point if i != 3 else "", status=st, display_title=MARK + "课", confidence=80 - i * 30, dropped_codes="k191_gone" if i == 0 else "", reason=MARK + "理由")
        r.setdefault("import_draft", dr)
    return r


# ---------- 浏览器 ----------
COLLECT = r"""
(() => {
  if (window.__k191) return;
  const seen = new Map();      // 文字 -> 位置
  let prev = new Set();
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  function now() {
    const out = new Map();
    const add = (t, where) => { t = (t || '').trim(); if (t) out.set(t, where); };
    if (!document.body) return out;
    add(document.title, 'title');
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const p = n.parentElement;
      if (!p || ['SCRIPT', 'STYLE', 'OPTION'].includes(p.tagName) || !vis(p) || p.closest('.nav-lang')) continue;
      const cell = p.closest('th') ? '表头' : p.closest('td') ? '表格' : p.closest('.toast,.toast-no') ? '提示条'
        : p.closest('button') ? '按钮' : p.closest('label') ? '标签' : p.closest('nav') ? '顶栏' : p.closest('.overlay') ? '浮层' : '文字';
      add(n.nodeValue, cell);
    }
    for (const e of document.querySelectorAll('input,textarea')) {
      if (!vis(e)) continue;
      if (e.placeholder) add(e.placeholder, 'placeholder');
      if (!['password', 'file', 'radio', 'checkbox'].includes(e.type) && e.value) add(e.value, '输入框的值');
    }
    for (const e of document.querySelectorAll('[title]')) if (vis(e)) add(e.title, 'title属性');
    for (const e of document.querySelectorAll('select')) if (vis(e)) for (const o of e.options) add(o.textContent, '下拉选项');
    return out;
  }
  window.__k191 = setInterval(() => {
    const cur = now();
    for (const [t, w] of cur) if (prev.has(t) && !seen.has(t)) seen.set(t, w);
    prev = new Set(cur.keys());
  }, 350);
  window.__k191_drain = () => { const a = [...seen.entries()]; seen.clear(); return a; };
})();
"""


class Scan:
    def __init__(self, base, dic, wl, content, deep):
        self.base, self.dic, self.wl, self.content, self.deep = base, dic, wl, content, deep
        self.jpset = set(dic.values())
        self.hits = {}        # 文字 -> {"where": set, "pages": set}
        self.states = 0
        self.pages = set()
        self.last_tag = "启动"

    def reset(self, p):
        try:
            p.evaluate("window.__k191_drain && window.__k191_drain()")
        except Exception:
            pass

    def clean(self, t):
        """去掉造数记号；剩下的才是要判断的。"""
        return TOKEN.sub("", t).strip()

    def record(self, page, where, text):
        t = self.clean(text)
        if not t or not HAN.search(t) or t in self.jpset:
            return
        self.hits.setdefault(text if t == text else t, {"where": set(), "pages": set(), "orig": text})
        h = self.hits[t]
        h["where"].add(where)
        h["pages"].add(page)

    def drain(self, p, tag):
        try:
            for t, w in p.evaluate("window.__k191_drain ? window.__k191_drain() : []"):
                self.record(tag, w, t)
        except Exception:
            pass     # 页面正在跳转，下一轮再收

    def settle(self, p, ms=700):
        try:
            p.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        p.wait_for_timeout(ms)

    def go(self, p, tag, screen, params=None, shot=None):
        """按地址开一个状态，收文字。"""
        h = "#" + quote(screen)
        if params:
            h += "?" + "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in params.items())
        self.pages.add(screen + ("?" + ",".join(params) if params else ""))
        self.states += 1
        self.drain(p, self.last_tag)     # 上一个状态还没收走的归上一个，不算到这里
        p.evaluate("h => { location.hash = h }", h)
        self.settle(p, 300)
        self.reset(p)                    # 切换时还在屏上的旧内容不算这个状态的
        self.settle(p)
        self.drain(p, tag)
        self.last_tag = tag
        if shot:
            p.screenshot(path=shot, full_page=True)
        return h

    def poke(self, p, tag, h, bad=False):
        """把这个状态上的按钮都点一下（按文字去重，危险的跳过）。bad=True 先往输入框填非法值。"""
        def buttons():
            return p.evaluate("""() => [...document.querySelectorAll('form.screen button, .screen button, .overlay button, main button, table button')]
              .filter(b => { const r = b.getBoundingClientRect(); return r.width > 0 && !b.disabled && !b.closest('nav') })
              .map((b, i) => ({t: b.textContent.trim(), danger: /danger|del/.test(b.className)}))""")
        done = set()
        for _ in range(14):
            todo = [b for b in buttons() if b["t"] and b["t"] not in done and not b["danger"]]
            if not todo:
                return
            b = todo[0]
            done.add(b["t"])
            if bad:
                p.evaluate("""() => { for (const e of document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=date]), textarea')) {
                   if (e.readOnly || e.disabled) continue; const r = e.getBoundingClientRect(); if (!r.width) continue;
                   e.value = e.type === 'number' ? '-1' : 'zz bad!'; e.dispatchEvent(new Event('input', {bubbles: true})); } }""")
            try:
                p.locator("button:visible", has_text=b["t"]).first.click(timeout=2500, no_wait_after=True)
            except Exception:
                continue
            self.settle(p, 700)
            self.drain(p, tag + "·点" + b["t"][:10])
            cur = p.evaluate("location.hash")
            if cur != h:
                p.evaluate("h => { location.hash = h }", h)
                self.settle(p, 500)


def login(p, base, user, end=""):
    p.goto(base + end, wait_until="domcontentloaded")
    p.wait_for_selector("form.screen", timeout=20000)
    p.locator('form.screen input:not([type="password"])').first.fill(user)
    p.locator('form.screen input[type="password"]').first.fill(PW)
    p.locator("form.screen button").first.click()
    p.wait_for_function("u => { const e = document.querySelector('.nav-user-name'); return e && e.textContent.trim() === u }", arg=user, timeout=20000)


def switch_subject(p, sid):
    sel = p.locator("select.nav-subject")
    if sel.count() and sel.input_value() != str(sid):
        with p.expect_navigation(timeout=20000):
            sel.select_option(value=str(sid))
        p.wait_for_load_state("domcontentloaded")
        p.wait_for_timeout(800)


def overlays_of(root):
    """从 .ui 读：界面 → [浮层]。新加的浮层自动进遍历。"""
    out = {}
    for f in sorted((root / "ui").glob("*.ui")):
        cur = None
        for line in f.read_text(encoding="utf-8").splitlines():
            m = re.match(r"界面 \S+ (\S+)", line)
            if m:
                cur = m.group(1)
                out.setdefault(cur, [])
            m = re.match(r"\s+浮层 (\S+)", line)
            if m and cur:
                out[cur].append(m.group(1))
    return out


def teacher_states(r, stu, empty):
    """教师端每个界面的状态：(界面, 参数)。浮层另外由 overlays_of 补，这里给浮层要的 id。"""
    return [
        ("学情", None), ("学情", {"student": stu}), ("学情", {"student": empty}), ("学情", {"student": "nobody_k191"}),
        ("学情", {"student": stu, "chat_kw": "造数zzz"}),
        ("教师助手", None), ("学生管理", None), ("科目管理", None), ("AI老师设定", None),
        ("教材导入", None), ("教材导入", {"job": r["job"]}), ("教材导入", {"job": 999999}),
        ("教材导入", {"draft": r["import_draft"]}), ("教材导入", {"draft": 999999}),
        ("教材导入", {"manage": r["series"] or "none"}), ("教材导入", {"manage": "nobody_series"}),
        ("课文查看", None), ("课文查看", {"code": r["lesson"] or "none"}), ("课文查看", {"code": "nobody_lesson"}),
        ("教学材料", None), ("图谱管理", None),
    ]


OVERLAY_PARAMS = {
    "编辑学生设定": lambda r, s, sid: {"student": s, "note_id": r["note"]},
    "编辑学生传达": lambda r, s, sid: {"student": s, "relay_id": r["relay"]},
    "问老师全文": lambda r, s, sid: {"student": s, "chat_id": r["chat"]},
    "学生传达记录": lambda r, s, sid: {"student": s, "message_id": r["chat"]},
    "编辑科目": lambda r, s, sid: {"subj_id": sid},
    "科目成员": lambda r, s, sid: {"subj_id": sid},
    "编辑设定": lambda r, s, sid: {"note_id": r["class_note"]},
    "编辑传达": lambda r, s, sid: {"relay_id": r["relay"]},
    "传达记录": lambda r, s, sid: {"message_id": r["chat"]},
    "确认删除任务": lambda r, s, sid: {"job": r["job"]},
    "确认撤下": lambda r, s, sid: {"manage": r["series"] or "none"},
    "编辑材料": lambda r, s, sid: {"mat_id": r["material"]},
    "导出材料": lambda r, s, sid: {"mat_id": r["material"]},
    "草稿详情": lambda r, s, sid: {"draft_id": r["draft"]},
    "编辑知识点": lambda r, s, sid: {"kgp_orig": r["point"]},
    "编辑条目": lambda r, s, sid: {"kgi_orig": r["item"]},
    "节点详情": lambda r, s, sid: {"code": r["point"]},
}


def walk_teacher(sc, p, user, sid, r, ovl, stu, empty, poke):
    tag0 = f"教师{user[5:]}/科目{sid}"
    switch_subject(p, sid)
    sc.drain(p, tag0 + "/顶栏")
    # 导航每个入口点一下：开在这里顺带核对导航能点
    names = p.eval_on_selector_all("nav a[href='#']", "els => els.map(e => e.textContent.trim())")
    for n in names:
        if n in ("中文", "日本語"):
            continue
        try:
            p.locator("nav a[href='#']", has_text=n).first.click(timeout=3000)
        except Exception:
            continue
        sc.settle(p, 600)
        sc.drain(p, tag0 + "/导航" + n)
    teacher_screens = {s for s, _ in teacher_states(r, stu, empty)}
    for screen, params in teacher_states(r, stu, empty):
        tag = f"{tag0}/{screen}" + ("?" + ",".join(f"{k}={v}" for k, v in params.items()) if params else "")
        h = sc.go(p, tag, screen, params)
        if poke:
            sc.poke(p, tag, h)
            if sc.deep:
                sc.poke(p, tag + "·非法值", h, bad=True)
    for screen in sorted(teacher_screens):
        for ov in ovl.get(screen, []):
            mk = OVERLAY_PARAMS.get(ov)
            params = dict(mk(r, stu, sid)) if mk else {}
            params["浮层"] = ov
            tag = f"{tag0}/{screen}/浮层{ov}"
            h = sc.go(p, tag, screen, params)
            # 新建（不带 id）的浮层也开一下，选项和提示可能不一样
            if len(params) > 1:
                sc.go(p, tag + "(新建)", screen, {"浮层": ov})
            if poke and sc.deep:
                sc.go(p, tag, screen, params)
                sc.poke(p, tag + "·点", h, bad=True)
    # 草稿详情：各种类型和状态（待确认、已写入、失败、已撤销……）
    for d in (r["drafts"] if sc.full else r["drafts"][:8]):
        sc.go(p, f"{tag0}/教师助手/草稿详情{d}", "教师助手", {"浮层": "草稿详情", "draft_id": d})
    # 教材导入各种状态的任务
    for j in (r["jobs"] if sc.full else r["jobs"][:2]):
        sc.go(p, f"{tag0}/教材导入/任务{j}", "教材导入", {"job": j})


def walk_student(sc, p, user, sid, r, ovl, poke):
    tag0 = f"学生{user[5:]}/科目{sid}"
    switch_subject(p, sid)
    sc.drain(p, tag0 + "/顶栏")
    states = [("问老师", None), ("做题", None), ("默写", None), ("教材", None), ("知识图谱", None), ("学习进度", None),
              ("做题", {"mode": "review"}), ("默写", {"source": "review"})]
    if r:
        states += [("教材", {"lesson": r["lesson"] or "none"}), ("教材", {"lesson": "nobody_lesson"}),
                   ("做题", {"lesson": r["lesson"] or "none"}), ("知识图谱", {"浮层": "节点详情", "code": r["point"] or "none"})]
    for screen, params in states:
        tag = f"{tag0}/{screen}" + ("?" + ",".join(params) if params else "")
        h = sc.go(p, tag, screen, params)
        if poke:
            sc.poke(p, tag, h)
    if not poke:
        return
    # 做题一轮：开始 → 答 → 下一题……直到一轮结束（end 分支、总结按钮）
    sc.go(p, f"{tag0}/做题", "做题")
    for i in range(14):
        try:
            btns = p.locator(".screen button:visible")
            n = btns.count()
            if n == 0:
                break
            # 下一题优先，其次选项，其次开始
            texts = [btns.nth(j).inner_text().strip() for j in range(n)]
            pick = None
            for want in ("次の問題", "下一题"):
                if want in texts:
                    pick = texts.index(want)
            if pick is None:
                opts = [j for j, t in enumerate(texts) if re.match(r"^[A-D]\b|^[A-D][.．、 ]", t)]
                pick = opts[0] if opts else (texts.index("開始") if "開始" in texts else 0)
            btns.nth(pick).click(timeout=3000)
        except Exception:
            break
        sc.settle(p, 500)
        sc.drain(p, f"{tag0}/做题一轮")


def login_flow(sc, browser, base):
    ctx = browser.new_context(locale="ja-JP", viewport={"width": 1280, "height": 900})
    p = ctx.new_page()
    p.add_init_script(COLLECT)
    dialogs(sc, p, "未登录")
    for end, tag in (("", "未登录/学生端登录"), ("/teacher", "未登录/教师端登录")):
        p.goto(base + end, wait_until="domcontentloaded")
        p.wait_for_selector("form.screen", timeout=20000)
        sc.pages.add("登录" + end)
        sc.states += 1
        sc.settle(p)
        sc.drain(p, tag)
        btn = p.locator("form.screen button").first
        btn.click()                               # 空提交
        sc.settle(p)
        sc.drain(p, tag + "·空提交")
        p.locator('form.screen input:not([type="password"])').first.fill("nobody_k191")
        p.locator('form.screen input[type="password"]').first.fill("wrong-pass")
        btn.click()                               # 错口令
        sc.settle(p)
        sc.drain(p, tag + "·错口令")
    # 换端拒绝：学生账号登教师端，教师账号登学生端
    for u, end, tag in ((U_STU, "/teacher", "学生登教师端"), (U_OWNER, "", "教师登学生端")):
        c2 = browser.new_context(locale="ja-JP", viewport={"width": 1280, "height": 900})
        q = c2.new_page()
        q.add_init_script(COLLECT)
        q.goto(base + end, wait_until="domcontentloaded")
        q.wait_for_selector("form.screen", timeout=20000)
        q.locator('form.screen input:not([type="password"])').first.fill(u)
        q.locator('form.screen input[type="password"]').first.fill(PW)
        q.locator("form.screen button").first.click()
        sc.settle(q, 1500)
        sc.drain(q, "未登录/" + tag)
        c2.close()
    ctx.close()


def password_flow(sc, p, tag):
    p.evaluate("location.hash = encodeURIComponent('改密码')")
    sc.settle(p)
    sc.drain(p, tag + "/改密码")
    sc.pages.add("改密码")
    btn = p.locator("form.screen button:visible").first
    if btn.count():
        btn.click()
        sc.settle(p)
        sc.drain(p, tag + "/改密码·空提交")
        pws = p.locator('form.screen input[type="password"]')
        for i in range(pws.count()):
            pws.nth(i).fill("wrong-old" if i == 0 else f"short{i}")
        btn.click()
        sc.settle(p)
        sc.drain(p, tag + "/改密码·非法值")


def dialogs(sc, p, tag):
    def on(d):
        sc.record(tag, "对话框", d.message)
        d.dismiss()
    p.on("dialog", on)


def api_errors(sc, browser, base, ids):
    """后端报错直接打接口（ja 教师账号）：页面上按钮挡住的非法组合也试一遍，看 message。"""
    ctx = browser.new_context(locale="ja-JP")
    p = ctx.new_page()
    p.add_init_script(COLLECT)
    login(p, base, U_OWNER, "/teacher")
    cases = [
        ("/kg/manage/point/save", {"kgp_code": "BAD CODE", "kgp_title": ""}),
        ("/kg/manage/point/delete", {"kgp_orig": "nobody"}),
        ("/kg/manage/item/save", {"kgi_code": "BAD", "kgi_name": ""}),
        ("/kg/manage/edge/add", {"edge_pre": "x", "edge_point": "x"}),
        ("/kg/manage/contrast/add", {"ct_a": "x", "ct_b": ""}),
        ("/subject/manage/save", {"subj_code": "BAD CODE", "subj_name": ""}),
        ("/subject/manage/assign", {"subj_id": "999999", "assign_learners": "nobody"}),
        ("/teacher_rules/note/save", {"note_kind": "", "note_content": ""}),
        ("/teacher_rules/relay/save", {"relay_point": ""}),
        ("/teacher_assist/draft/confirm", {"draft_id": "999999"}),
        ("/teacher_assist/draft/undo", {"draft_id": "999999"}),
        ("/teacher_assist/material/save", {"mat_id": "999999"}),
        ("/account/student/create", {"username": "", "password": "1"}),
        ("/account/student/reset", {"reset_user": "nobody", "new_password": "1"}),
        ("/account/lang", {"lang": "xx"}),
        ("/textbook_import/task/create", {"series": "BAD CODE"}),
    ]
    p.goto(base + "/teacher", wait_until="domcontentloaded")
    for path, form in cases:
        r = p.evaluate("""async ([u, f]) => { const r = await fetch(u, {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({form: f})}); let d = {}; try { d = await r.json() } catch (e) {} ; return [r.status, d.error || ''] }""", [path, form])
        if r[1]:
            # 接口回的是中文原文，前端按词表整串翻译：这里按翻译后的看
            text = sc.dic.get(r[1], r[1])
            sc.record(f"接口{r[0]}:{path}", "报错message", text)
    ctx.close()


def category(text, where, content):
    if where.startswith("静态:报错"):
        return "b"
    if text in content["names"]:
        return "c"
    if re.search(r"\d", text) or "：" in text:
        return "b"
    return "a"


def content_filter(db):
    """库里日语科目（1 号）的内容：讲解、题目、词义都是中文，设计 D3 只翻 Python，算数据。"""
    c = sqlite3.connect(db)
    words, titles = set(), set()
    for sql in ("select summary from lesson_text where subject_id=1", "select connection from lesson_text where subject_id=1",
                "select orig_title from lesson_text where subject_id=1",
                "select stem from quiz_question where subject_id=1", "select explain from quiz_question where subject_id=1"):
        for (t,) in c.execute(sql):
            if t and HAN.search(t):
                words.add(t.strip())
    for (examples,) in c.execute("select examples from lesson_text where subject_id=1"):
        for example in (examples or "").split("@@"):
            for part in example.split("^^"):
                if part.strip():
                    words.add(part.strip())
    for sql in ("select title from kg_point where subject_id=1", "select name from kg_item where subject_id=1",
                "select title from lesson_text where subject_id=1"):
        for (t,) in c.execute(sql):
            if t and HAN.search(t):
                titles.add(t.strip())
    meanings = set()
    for (t,) in c.execute("select meaning from vocab_word"):
        if t:
            meanings.add(re.sub(r"^\[N[1-5]\]\s*", "", t).strip())
    people = {r[0] for r in c.execute("select display_name from account_user") if r[0] and HAN.search(r[0])}
    translated = {r[0].strip() for r in c.execute("select text from subject_content_translation where lang='ja'") if r[0]}
    for (t,) in c.execute("select options from quiz_question where subject_id=1"):
        for o in (t or "").split("^"):
            if HAN.search(o):
                words.add(o.strip())
    manage = set()
    for sql in ("select title from kg_point", "select name from kg_item", "select name from subject_info",
                "select name from lesson_series", "select title from lesson_text", "select summary from lesson_text"):
        for (t,) in c.execute(sql):
            if t and HAN.search(t):
                manage.add(t.strip())
    names = {r[0] for r in c.execute("select name from subject_info")} | {r[0] for r in c.execute("select name from lesson_series")}
    explain = [r[0] for r in c.execute("select explain from lesson_text where subject_id=1 and explain is not null")]
    c.close()
    return {"words": words, "titles": sorted(titles, key=len, reverse=True), "meanings": meanings, "people": people, "translated": translated, "translated_short": sorted({x for x in translated if 2 <= len(x) <= 40 and "\n" not in x}, key=len, reverse=True), "translated_all": "\n".join(translated), "names": names, "explain": explain, "manage": sorted(manage, key=len, reverse=True)}


def without(text, words):
    """把 words 里出现在 text 里的词去掉（长的先去），剩下的再判。"""
    for w in words:
        if w in text:
            text = text.replace(w, "")
    return text


def data_rest(text, pages, where, content, dic=None):
    """去掉数据之后还剩什么；返回空串表示整串都是数据。
    - 账号显示名：哪都算数据；
    - 日语科目（1 号）的内容：设计 D3 只翻 Python，只在日语科目页面上才算；
    - 单词的中文义：只在默写、知识点详情和学情页才算（别处的「全部」「保存」不能靠撞词义过关）；
    - 编辑用的原文：图谱管理、教材导入映射，以及编辑浮层输入框里的值（K182 约定：译文只给展示路径）。"""
    t = without(text, content["people"])
    if not rule_of(t) or t in content["translated"]:
        return ""
    # 词表有这个键：tdom 会替换（CPU 忙时可能晚一拍被扫到），输入框的值例外（tdom 不改 value）
    if dic and t in dic and where - {"输入框的值"}:
        return ""
    # 只用来判断：译文词去掉后什么都不剩就是日文；剩了不改 t（集合 既是译文词也是 创建集合 的一部分）
    if any(w in t for w in content["translated_short"]):
        rest = re.sub(r"第\d+課|入門|基礎|応用|必要", "", without(t, content["translated_short"]))
        if not rule_of(rest.strip(" ・/（）()〔〕「」《》、，。：·　")):
            return ""
    if len(t) >= 3 and t in content["translated_all"]:
        return ""
    only_jp = all("科目1/" in p or "科目" not in p for p in pages)
    manage = all(MANAGE_PAGE.search(p) for p in pages)
    edit_value = where == {"输入框的值"} and all("浮层编辑" in p or "批量" in p or "科目管理" in p or "浮层导出" in p for p in pages)
    if edit_value:
        return ""
    if manage:
        t = without(t, content["manage"])
    if only_jp:
        if t in content["words"] or (len(t) >= 4 and any(t in e for e in content["explain"])):
            return ""
        if t.endswith("…") and any(w.startswith(t[:-1]) for w in content["words"]):
            return ""
        t = without(t, content["titles"])
        if "\n" in t and "ポイント：" in t:     # 题目解析：日语科目的解析是中文数据，外壳是日文
            return ""
    if only_jp and re.search(r"默写|节点详情|学情", ",".join(pages)):
        bare = re.sub(r"^(意味：|\[N[1-5]\]\s*)", "", t)
        if bare in content["meanings"] or re.sub(r"^.*【[^】]*】", "", bare).strip() in content["meanings"]:
            return ""
        bare2 = re.sub(r"^(正解：)?\S*\s?", "", t)
        if bare2 in content["meanings"]:
            return ""
    if t != text or manage or only_jp:
        t = without(t, SHELL)
    t = t.strip(" ・/（）()〔〕「」《》、，。：·")
    return t if rule_of(t) else ""


MANAGE_PAGE = re.compile(r"图谱管理|教材导入|マップ管理|教材インポート|浮层编辑知识点|浮层编辑条目|草稿详情")
# 去掉数据之后，外壳里只剩汉字的日文词（項目、必要）不算残留：词表右列 + 引擎的 必要：
SHELL = ("項目", "知識ポイント", "必要", "前提辺", "対照")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="真实数据目录（拷一份用；不给就自建裁小的库）")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--out", help="结果写到这个 tsv（页面、位置、文字、类别）")
    ap.add_argument("--full", action="store_true", help="全量：每种账号每个科目都走全，按钮都点（慢，修前修后扫描用）；默认精简，进 run_all")
    ap.add_argument("--deep", action="store_true", help="在 --full 基础上再往输入框填非法值点一遍（更慢）")
    ap.add_argument("--no-whitelist", action="store_true", help="不套白名单，列全（改前扫描用）")
    ap.add_argument("--shots", help="截图前缀")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：这个解释器没装 playwright")
        return 2
    src = REPO / "kg_v4"
    dic = load_dict(src)
    wl = load_whitelist() if not a.no_whitelist else ({}, [])
    tmp = Path(tempfile.mkdtemp(prefix="k191_scan_", dir="/tmp"))
    proc = None
    log = open(tmp / "server.log", "wb")
    t0 = time.time()
    fails = []
    rows = []
    sc = None
    try:
        static = static_checks(src, dic, wl)
        for where, text, cat in static:
            rows.append((where, "静态", text, cat))
        if a.data:
            proj = tmp / "kg_v4"
            shutil.copytree(a.data, proj, ignore=shutil.ignore_patterns(".auth_secret", "sessions", "__pycache__", "*.bak-*", "web"))
            for d in "contracts entities queries routes scripts services ui setup i18n".split():
                if (proj / d).exists():
                    shutil.rmtree(proj / d)
                shutil.copytree(src / d, proj / d)
            (proj / "plan").mkdir(exist_ok=True)
            shutil.copy(src / "plan" / "top.zs", proj / "plan" / "top.zs")
        else:
            proj = build_workspace(tmp, src)
        ids = seed(proj / "app.db")
        seed_names(proj / "app.db", src)
        content = content_filter(proj / "app.db")
        port = a.port or free_port()
        base = f"http://127.0.0.1:{port}"
        proc = start_server(proj, port, log)
        ovl = overlays_of(src)
        print("服务已起", base, "造数完成", round(time.time() - t0), "秒", flush=True)
        sc = Scan(base, dic, wl, content, a.deep)
        sc.full = a.full or a.deep
        a.full = sc.full
        with sync_playwright() as pw:
            kw = {"executable_path": "/usr/bin/google-chrome"} if Path("/usr/bin/google-chrome").exists() else {"channel": "chrome"}
            browser = pw.chromium.launch(**kw)
            login_flow(sc, browser, base)
            print("登录页 完成", round(time.time() - t0), flush=True)
            py, emp = ids["py"], ids["empty"]

            def page_for(user, end):
                ctx = browser.new_context(locale="ja-JP", viewport={"width": 1440, "height": 900})
                p = ctx.new_page()
                p.add_init_script(COLLECT)
                dialogs(sc, p, user)
                login(p, base, user, end)
                p.wait_for_timeout(600)
                return p
            # 负责教师：两个科目（点按钮）+ 空科目（只看）
            p = page_for(U_OWNER, "/teacher")
            walk_teacher(sc, p, U_OWNER, 1, ids["subjects"][1], ovl, U_STU, U_EMPTY, poke=True)
            print("负责教师 日语 完成", sc.states, round(time.time() - t0), flush=True)
            walk_teacher(sc, p, U_OWNER, py, ids["subjects"][py], ovl, U_STU, U_EMPTY, poke=a.full)
            print("负责教师 Python 完成", sc.states, round(time.time() - t0), flush=True)
            empty_r = dict(ids["subjects"][py], job=0, jobs=[], drafts=[], import_draft=0, series="", lesson="", draft=0)
            if a.full:
                walk_teacher(sc, p, U_OWNER, emp, empty_r, ovl, U_STU, U_EMPTY, poke=False)
            else:
                switch_subject(p, emp)
                for st in ("学情", "教师助手", "AI老师设定", "教材导入", "课文查看", "教学材料", "图谱管理"):
                    sc.go(p, f"教师owner/科目{emp}/{st}", st)
            password_flow(sc, p, "教师")
            p.context.close()
            print("负责教师 空科目 完成", sc.states, round(time.time() - t0), flush=True)
            # 协作教师：只看（按钮差异看页面文字），公共只读教师看日语科目
            if a.full:
                p = page_for(U_EDIT, "/teacher")
                walk_teacher(sc, p, U_EDIT, 1, ids["subjects"][1], ovl, U_STU, U_EMPTY, poke=False)
                walk_teacher(sc, p, U_EDIT, py, ids["subjects"][py], ovl, U_STU, U_EMPTY, poke=False)
                p.context.close()
                p = page_for(U_PUBLIC, "/teacher")
                walk_teacher(sc, p, U_PUBLIC, 1, ids["subjects"][1], ovl, U_STU, U_EMPTY, poke=False)
                p.context.close()
            else:
                p = page_for(U_EDIT, "/teacher")
                for st in ("科目管理", "图谱管理", "AI老师设定"):
                    sc.go(p, f"教师edit/科目{py}/{st}", st)
                p.context.close()
            print("协作、公共 完成", sc.states, round(time.time() - t0), flush=True)
            # 学生：有数据、没数据
            p = page_for(U_STU, "")
            walk_student(sc, p, U_STU, 1, ids["subjects"][1], ovl, poke=True)
            walk_student(sc, p, U_STU, py, ids["subjects"][py], ovl, poke=True)   # 精简模式也点：学生端 Python 是主要入口
            password_flow(sc, p, "学生")
            if a.shots:
                p.screenshot(path=a.shots + "_student.png", full_page=True)
            p.context.close()
            p = page_for(U_EMPTY, "")
            if a.full:
                walk_student(sc, p, U_EMPTY, 1, None, ovl, poke=False)
                walk_student(sc, p, U_EMPTY, py, None, ovl, poke=False)
            walk_student(sc, p, U_EMPTY, emp, None, ovl, poke=False)
            p.context.close()
            print("学生 完成", sc.states, round(time.time() - t0), flush=True)
            api_errors(sc, browser, base, ids)
            browser.close()
    except Exception:
        import traceback
        fails.append("扫描中途异常：" + traceback.format_exc()[-1500:])
    finally:
        stop_server(proc)
        log.close()
    # 判定
    keep = {}
    dlist = []
    if sc:
        for t, h in sc.hits.items():
            rule = rule_of(t)
            if not rule:
                continue
            # 只出现在日语科目页面上的内容才豁免成数据
            if not data_rest(t, h["pages"], h["where"], content, dic):
                keep.setdefault("data", []).append(t)
                dlist.append((",".join(sorted(h["pages"]))[:200], ",".join(sorted(h["where"])), t, "d/数据"))
                continue
            w = whitelisted(t, wl)
            if w:
                keep.setdefault("wl", []).append(t)
                dlist.append((",".join(sorted(h["pages"]))[:200], ",".join(sorted(h["where"])), t, "d/白名单：" + w[1]))
                continue
            rows.append((",".join(sorted(h["pages"], key=lambda x: bool(MANAGE_PAGE.search(x))))[:400], ",".join(sorted(h["where"])), t, category(t, "", content) + "/" + rule))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("页面\t位置\t文字\t类别\n")
            for pg, w, t, cat in sorted(rows, key=lambda x: (x[0].split(",")[0], x[2])) + sorted(dlist, key=lambda x: (x[3], x[2])):
                f.write(f"{pg}\t{w}\t{t.replace(chr(9), ' ').replace(chr(10), ' ⏎ ')}\t{cat}\n")
    n_pages = len(sc.pages) if sc else 0
    print(f"状态 {sc.states if sc else 0} 个、不同页面 {n_pages} 个；残留 {len(rows)} 条；"
          f"日语科目数据豁免 {len(keep.get('data', []))}；白名单 {len(keep.get('wl', []))}；用时 {round(time.time() - t0)} 秒", flush=True)
    for r in rows[:60]:
        print("  残留:", r[2][:80], "|", r[0][:60])
    if proc is not None and (tmp / "server.log").exists():
        log_text = (tmp / "server.log").read_text(encoding="utf-8", errors="replace")
        print("服务日志 Traceback", log_text.count("Traceback"), "500:", log_text.count('" 500 '))
    if not a.keep:
        (tmp / "kg_v4" / ".auth_secret").unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("临时目录留着", tmp)
    for f in fails:
        print("失败：", f)
    return 1 if (fails or rows) else 0


if __name__ == "__main__":
    sys.exit(main())
