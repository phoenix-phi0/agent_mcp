# -*- coding: utf-8 -*-
"""教材导入（管理侧「教材导入」页）：routes/textbook_import.zs、scripts/import_*.zs、
entities/textbook_import.entity，加上它用到的通用能力（存文件的类型和大小、
doc 包「读文档」、text 包「切章节」、引擎的「后台执行」）。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_textbook_import.py

临时工作区（照 kg 搭，导入知识点、hanabira 课文、题目），不碰 kg/app.db、
kg/content。模型是离线的假客户端（handler 按块标题回 JSON），后台执行用
tools.dsl.wait_background 等跑完。教材全是测试里现造的几行字，不是真教材。

  一、上传校验：缺系列代号 / 显示名、代号不合格、hanabira、前缀被占 → 400 一句话；
      类型不对（.exe）、扩展名和文件头对不上（假 pdf、假 docx）、空文件、超过
      20MB → 400，不建任务、不存文件；对照：合格的 md 能建
  二、取文本：现造的 md / docx（标题样式变成 # ）/ pdf（pypdf 取得出字）/ 扫描版
      pdf（没有文字层 → 报要 OCR）/ 加了 BOM 和 GBK 的 txt；切章节按「第N课」切、
      目录短于 200 字丢掉、超长的按段落再切
  三、解析（假模型）：每块一次平衡档调用；提示词里有块内容、候选清单（条目和
      知识点）、改写要求（不勾就没有）；等级范围预筛候选；抽出的课写进草稿；
      不存在的编号被丢掉、记进 dropped，问题提示里有；孤课有提示；没认出课的块
      完成并说明；模型抛错 → 块出错「模型没有回应」，回 JSON 不对 → 出错；重试
      单块后完成；进度 running 跑完变 0
  四、审阅：改字段（例句不是 JSON 数组 400）、加映射（下拉、输入编号；库里没有
      400、绝不新建）、去掉映射、通过 / 驳回、全部通过有映射的课（孤课不动）
  五、确认导入：没有通过的课 400；写 content/series/<code>/lessons.jsonl（README
      的格式，items/points 是数组）和 series.jsonl（hanabira 那行原样）；入库，
      报告 lessons/links/points；草稿里塞一个库里没有的编号 → 那行拒收、进报告
      和拒收表；教材页下拉出现新系列、课文表是它的课；读一课有映射的条目
  六、系列冲突：同代号新任务不勾覆盖 400、勾了能导；同一任务再导一次照常
  七、删除任务只删草稿，课还在；撤下系列：hanabira 400；撤下后库里这个系列的课、
      映射清空、series.sort=-1、下拉里没有、选过它的学习者回到 hanabira（偏好
      那行不动）、series.jsonl 那行 sort=-1、lessons.jsonl 变空、课文挪到
      lessons.withdrawn.jsonl；之后再确认导入能重新上架
  八、hanabira 一课不少、映射一条不少；学习记录（attempt、mastery、score、对话、
      偏好……）全程一行没动
  九、老库补表：没有 import_ 三张表的库，「迁移 只加」补上，原有的行还在
"""

import io
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws   # noqa: E402
from kg.__main__ import BANK, read_bank                       # noqa: E402
from tools.dsl import wait_background                         # noqa: E402
from tools.migrate import migrate_additive                    # noqa: E402
from tools.mock import MockClient                             # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


# ----------------------------------------------------------------------
# 现造的小文档
# ----------------------------------------------------------------------

def make_pdf(pages) -> bytes:
    """最小的 PDF：每页几行 ASCII 字（Helvetica）。空列表的页没有文字层。"""
    objects = {1: "<< /Type /Catalog /Pages 2 0 R >>",
               3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    kids, num = [], 4
    for lines in pages:
        page_no, cont_no = num, num + 1
        num += 2
        kids.append(f"{page_no} 0 R")
        stream = ("BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines)
                  + " ET") if lines else "0 0 m 10 10 l S"
        objects[page_no] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                            "/Resources << /Font << /F1 3 0 R >> >> "
                            f"/Contents {cont_no} 0 R >>")
        objects[cont_no] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    out = b"%PDF-1.4\n"
    offsets = {}
    for i in sorted(objects):
        offsets[i] = len(out)
        out += f"{i} 0 obj\n{objects[i]}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for i in sorted(objects):
        out += f"{offsets[i]:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return out


def make_docx(paras) -> bytes:
    """最小的 docx：[(样式, 文字)]，样式 Heading1 / Heading2 / ''。"""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = []
    for style, text in paras:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body.append(f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>")
    body.append("<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表头甲</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>表头乙</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")
    doc = (f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{w}"><w:body>'
           + "".join(body) + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


BOOK_MD = """# 测试教材（现造的，不是真教材）

目录：第1课、第2课、第3课

## 第1课 てから

讲做完一件事再做另一件。原文讲解甲。

## 第2课 たい

讲想做什么。原文讲解乙。

## 第3课 ながら

讲一边一边。原文讲解丙。

## 第4课 练习

练习题，没有新语法。
"""


# ----------------------------------------------------------------------
# 假模型
# ----------------------------------------------------------------------

class Brain:
    """按块标题回 JSON。fail 里的标题抛错（模型超时），badjson 里的回乱码。"""

    def __init__(self):
        self.fail = set()
        self.badjson = set()
        self.calls = []

    def __call__(self, prompt, system):
        import re
        m = re.search(r"块标题「(.*?)」", prompt)
        title = m.group(1) if m else ""
        self.calls.append({"title": title, "prompt": prompt, "system": system or ""})
        if title in self.fail:
            raise RuntimeError("claude 超过 90 秒没有返回\n第二行细节")
        if title in self.badjson:
            return "好的，下面是结果：没有 JSON"
        if "てから" in title:
            ls = [{"seq": 1, "title": "〜てから", "level": "N5", "summary": "做完再做",
                   "explanation": "模型改写的讲解一。", "formation": "动词て形 + から",
                   "examples": [{"jp": "宿題をしてから遊びます。", "zh": "做完作业再玩。"}],
                   "items": ["te-kara", "no-such-item"], "points": ["f-time"],
                   "confidence": 0.9, "reason": "讲的就是てから"}]
        elif "たい" in title:
            ls = [{"seq": "2", "title": "〜たい", "level": "n5", "summary": "想做",
                   "explanation": "模型改写的讲解二。", "formation": "",
                   "examples": [{"jp": "水が飲みたい。", "zh": "想喝水。"}],
                   "items": [], "points": ["f-desire"], "confidence": 80, "reason": "愿望"}]
        elif "ながら" in title:
            ls = [{"seq": 3, "title": "〜ながら", "level": "N9", "summary": "一边一边",
                   "explanation": "模型改写的讲解三。", "examples": [],
                   "items": ["nagara-fake"], "points": ["nope-node"],
                   "confidence": 0.3, "reason": "清单里没找到"}]
        else:
            ls = []
        return json.dumps({"lessons": ls}, ensure_ascii=False)


# ----------------------------------------------------------------------

def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="textbook_import_")))
    import_graph(ws)
    c0 = client(ws)
    assert c0.post("/lesson/import", json={"form": {}}).status_code == 200
    r = c0.post("/quiz/import", json={"form": {"rows": read_bank(BANK)}})
    assert r.status_code == 200, r.get_json()
    db = ws / "app.db"

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def val(sql, *args):
        r = rows(sql, *args)
        return list(r[0].values())[0] if r else None

    # 学习记录：先放几行，最后整表比对
    con = sqlite3.connect(db)
    con.execute("INSERT INTO mastery(learner, point, level) VALUES('me', 'f-time', 2)") \
        if "level" in [r[1] for r in con.execute("PRAGMA table_info(mastery)")] else None
    con.execute("INSERT INTO chat_message(learner, role, content) VALUES('me', 'user', '你好')")
    con.execute("INSERT INTO learner_pref(learner, series) VALUES('me', 'hanabira')")
    con.commit()
    con.close()
    LEARN = ("attempt", "mastery", "score", "quiz_state", "chat_message", "word_attempt",
             "dictation_state", "learner_pref")

    def learning():
        return {t: rows(f"SELECT * FROM {t} ORDER BY rowid") for t in LEARN}
    learn0 = learning()
    hb0 = (val("SELECT count(*) FROM lesson WHERE series = 'hanabira'"),
           val("SELECT count(*) FROM item_lesson il JOIN lesson l ON l.code = il.lesson "
               "WHERE l.series = 'hanabira'"))
    series_seed0 = (ws / "content/series.jsonl").read_text(encoding="utf-8")

    from gen.project import make_app
    app, router = make_app(ws, real=False)
    brain = Brain()
    router.client_factory = lambda: MockClient(handler=brain, offline=True)
    c = app.test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def upload(form, name, data):
        payload = {"action": "import_create", "form": form}
        files = {"payload": json.dumps(payload, ensure_ascii=False)}
        if name is not None:
            files["document"] = (io.BytesIO(data), name)
        r = c.post("/import/create", data=files, content_type="multipart/form-data")
        return r.status_code, (r.get_json(silent=True) or {})

    def uploads_n():
        d = ws / "uploads"
        return len(list(d.iterdir())) if d.is_dir() else 0

    base = {"series": "mnn", "label": "测试 教材", "source": "测试里现造", "license": "自用",
            "prefix": "mnn", "lesson_level": "全部", "rewrite": True, "overwrite": False}

    # ---------------- 一、上传校验 ----------------
    print("一、上传校验")
    md = BOOK_MD.encode()
    cases = [
        ({**base, "series": ""}, "a.md", md, "系列代号"),
        ({**base, "label": ""}, "a.md", md, "显示名"),
        ({**base, "series": "MNN"}, "a.md", md, "小写字母开头"),
        ({**base, "series": "_hide"}, "a.md", md, "小写字母开头"),
        ({**base, "series": "hanabira"}, "a.md", md, "hanabira"),
        ({**base, "prefix": "hb"}, "a.md", md, "已经被别的系列用了"),
        ({**base, "prefix": "m-n"}, "a.md", md, "课号前缀只能"),
        (base, "a.exe", md, "文件类型不支持"),
        (base, "a.pdf", b"just text, not a pdf", "对不上"),
        (base, "a.docx", b"plain text", "对不上"),
        (base, "a.md", b"", "空文件"),
        (base, "a.md", b"\x00\x01binary", "二进制"),
        (base, "a.md", b"x" * (20 * 1024 * 1024 + 10), "文件太大"),
        (base, None, b"", "没收下"),
    ]
    for form, name, data, want in cases:
        st, body = upload(form, name, data)
        check(st == 400 and want in (body.get("error") or ""),
              f"{name or '没带文件'}（series={form['series']!r} prefix={form['prefix']!r}）"
              f"→ 400「{want}」：{st} {(body.get('error') or '')[:60]}")
    check(val("SELECT count(*) FROM import_job") == 0 and uploads_n() == 0,
          "不合格的一个任务都没建、一个文件都没存")
    st, body = upload({**base}, "scan.pdf", make_pdf([[], []]))
    check(st == 400 and "OCR" in (body.get("error") or "") and "扫描版" in body["error"],
          f"扫描版 PDF（没有文字层）→ 400 要 OCR、暂不支持：{body.get('error')}")
    check(val("SELECT count(*) FROM import_job") == 0, "扫描版也没建任务")

    # ---------------- 二、取文本 ----------------
    print("二、取文本、切章节")
    import importlib.util
    spec = importlib.util.spec_from_file_location("doc_verbs", ROOT / "verbs/doc/_verbs.py")
    docmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(docmod)
    tmp = Path(tempfile.mkdtemp(prefix="docs_"))
    (tmp / "a.md").write_bytes(md)
    d = docmod.read_document(tmp / "a.md")
    check(d["kind"] == "md" and not d["error"] and "第2课 たい" in d["text"]
          and d["paragraphs"] == 10 and d["pages"] == 0,
          f"md：取到全文，段落数 {d['paragraphs']}")
    (tmp / "b.docx").write_bytes(make_docx([("Heading1", "测试教材"), ("Heading2", "第1课 てから"),
                                            ("", "讲解甲"), ("2", "第2课 たい"), ("", "讲解乙")]))
    d = docmod.read_document(tmp / "b.docx")
    check(not d["error"] and "# 测试教材" in d["text"] and "## 第1课 てから" in d["text"]
          and "## 第2课 たい" in d["text"] and "表头甲 | 表头乙" in d["text"],
          f"docx：标题样式变成 # 、表格拼成一行：{d['text'][:80]!r}")
    (tmp / "c.pdf").write_bytes(make_pdf([["Lesson 1 te-kara", "Do A then B."],
                                          ["Lesson 2 tai", "Want to do."]]))
    d = docmod.read_document(tmp / "c.pdf")
    check(not d["error"] and d["pages"] == 2 and "Lesson 2 tai" in d["text"],
          f"pdf：2 页，取到字：{d['text'][:60]!r}")
    (tmp / "d.pdf").write_bytes(make_pdf([[], [], []]))
    d = docmod.read_document(tmp / "d.pdf")
    check("OCR" in d["error"] and d["pages"] == 3 and not d["text"],
          f"扫描版 pdf：报要 OCR，不给一堆空页：{d['error']}")
    (tmp / "e.txt").write_bytes("﻿第1课 甲\n内容".encode("utf-8"))
    (tmp / "f.txt").write_bytes("第1课 乙\n内容".encode("gbk"))
    check(docmod.read_document(tmp / "e.txt")["text"].startswith("第1课 甲")
          and docmod.read_document(tmp / "f.txt")["text"].startswith("第1课 乙"),
          "txt：带 BOM 的 UTF-8、GBK 都认")
    (tmp / "g.docx").write_bytes(b"PK\x03\x04broken")
    check("不是有效的 Word" in docmod.read_document(tmp / "g.docx")["error"], "坏 docx 报一句人话")

    spec = importlib.util.spec_from_file_location("cut", ROOT / "verbs/text/defs/切章节.py")
    cut = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cut)
    chunks = cut.切章节(BOOK_MD, "6000")
    check([x["title"] for x in chunks] == ["第1课 てから", "第2课 たい", "第3课 ながら", "第4课 练习"],
          f"按「第N课」切成 4 块，开头的目录短、丢掉：{[x['title'] for x in chunks]}")
    long = "## 第1课 长\n\n" + "\n\n".join("段" * 150 for _ in range(10))
    parts = cut.切章节(long, "500")
    check(len(parts) > 1 and all(p["chars"] <= 500 for p in parts) and parts[1]["title"].endswith("（续2）"),
          f"超过上限的块按段落再切：{[p['title'] for p in parts][:3]}")
    check([x["title"] for x in cut.切章节("# 书\n\n## A\nx\n\n## B\ny")] == ["A", "B"],
          "没有「第N课」时按 Markdown 标题切（只有一个的书名那级跳过）")

    # ---------------- 三、解析 ----------------
    print("三、解析（假模型）")
    st, body = upload(base, "book.md", md)
    check(st == 200 and body.get("go") == "#教材导入?job=1", f"合格的 md 建任务，跳到审阅页：{st} {body}")
    check(uploads_n() == 1 and (ws / "uploads").is_dir(),
          f"文件存进项目的 uploads/（.gitignore 里有）；扫描版那次存下的文件已经删掉：{uploads_n()} 个")
    check(wait_background(30), "后台跑完")
    job = rows("SELECT * FROM import_job WHERE id = 1")[0]
    check(job["series"] == "mnn" and job["label"] == "测试 教材" and job["rewrite"] == 1
          and job["overwrite"] == 0 and job["file_name"] == "book.md" and job["doc_kind"] == "md",
          f"任务记下了表单：series/label/rewrite/文件名：{job['label']} {job['rewrite']} {job['file_name']}")
    chunk_rows = rows("SELECT * FROM import_chunk WHERE job = 1 ORDER BY seq")
    check([x["chunk_status"] for x in chunk_rows] == ["完成"] * 4, f"4 块都完成：{[x['chunk_status'] for x in chunk_rows]}")
    check(len(brain.calls) == 4, f"一块一次模型调用：{len(brain.calls)}")
    p1 = next(x for x in brain.calls if "てから" in x["title"])
    check("原文讲解甲" in p1["prompt"] and "条目 te-kara｜てから｜属于 f-time" in p1["prompt"]
          and "知识点 f-desire｜" in p1["prompt"] and "版权要求" in p1["prompt"]
          and "绝对不要自己编编号" in p1["prompt"]
          and "这 11 个键，一个都不能少" in p1["prompt"] and "不要省略这两个键" in p1["prompt"],
          "提示词里有块内容、候选清单（条目、知识点）、改写要求、不许编编号、每课 11 个键都要有"
          "（真模型试过：不点名就整个漏掉 items/points）")
    check("日语教材编辑" in p1["system"], "系统提示词是教材编辑")
    drafts = rows("SELECT * FROM import_lesson WHERE job = 1 ORDER BY seq")
    check([d["title"] for d in drafts] == ["〜てから", "〜たい", "〜ながら"],
          f"抽出 3 课草稿（练习块没课）：{[d['title'] for d in drafts]}")
    d1, d2, d3 = drafts
    check(json.loads(d1["items"]) == ["te-kara"] and json.loads(d1["points"]) == ["f-time"]
          and "no-such-item" in (d1["dropped"] or "") and "丢掉了库里没有的编号" in (d1["issues"] or ""),
          f"不存在的条目丢掉、记下来：items={d1['items']} dropped={d1['dropped']}")
    check(d1["draft_level"] == "N5" and d1["confidence"] == 90 and d1["review"] == "待审"
          and json.loads(d1["examples"])[0]["zh"] == "做完作业再玩。",
          "等级、把握（0.9 → 90）、例句、待审")
    check(d2["draft_level"] == "N5" and d2["seq"] == 2 and d2["confidence"] == 80
          and json.loads(d2["points"]) == ["f-desire"], "等级小写 n5 认、课序字符串 \"2\" 认、把握 80 照存")
    check(d3["draft_level"] is None and json.loads(d3["items"]) == [] and json.loads(d3["points"]) == []
          and "等级没认出" in d3["issues"] and "没映射到已有条目或知识点" in d3["issues"]
          and "nagara-fake" in d3["dropped"] and "nope-node" in d3["dropped"],
          f"等级 N9 存空、两个编号都不存在 → 孤课：{d3['issues']} / {d3['dropped']}")
    check(val("SELECT count(*) FROM item WHERE code IN ('no-such-item', 'nagara-fake')") == 0
          and val("SELECT count(*) FROM node WHERE code = 'nope-node'") == 0,
          "绝不新建条目、知识点")
    c4 = chunk_rows[3]
    check(c4["chunk_status"] == "完成" and "没认出课" in (c4["error"] or ""),
          f"没认出课的块：完成，说一句：{c4['error']}")
    st, body = post("/import/load", job="1")
    sj = (body.get("state") or {}).get("job") or {}
    lists = body.get("lists") or {}
    check(st == 200 and sj.get("running") == 0 and sj.get("lesson_n") == 3
          and "解析完了" in sj.get("progress", "") and len(lists.get("import_drafts") or []) == 3
          and len(lists.get("import_chunks") or []) == 4,
          f"审阅页：进度跑完、3 课、4 块：{sj.get('progress')}")
    st, body = post("/import/home")
    jl = (body.get("lists") or {}).get("import_jobs") or []
    check(st == 200 and jl and jl[0]["job_state"].startswith("待审 3 课")
          and jl[0]["href"].endswith("?job=1") and (body.get("form") or {}).get("rewrite") in (True, "true"),
          f"首页任务表一行，进度「{jl[0]['job_state'] if jl else ''}」；表单改写默认勾上")

    # 出错和重试：另一个任务，不改写、等级范围 N1
    brain.calls.clear()
    brain.fail = {"第2课 たい"}
    brain.badjson = {"第3课 ながら"}
    st, body = upload({**base, "series": "tmp2", "prefix": "tmpb", "rewrite": False,
                       "lesson_level": "N1"}, "b.md", md)
    check(st == 200 and wait_background(30), f"第二个任务（不改写、等级 N1）：{st}")
    ch = {x["title"]: x for x in rows("SELECT * FROM import_chunk WHERE job = 2")}
    check(ch["第2课 たい"]["chunk_status"] == "出错"
          and ch["第2课 たい"]["error"].startswith(
              "模型没有回应：模型调用失败：claude 超过 90 秒没有返回")
          and "第二行" not in ch["第2课 たい"]["error"],
          f"模型抛错 → 块出错，一句人话：{ch['第2课 たい']['error']}")
    check(ch["第3课 ながら"]["chunk_status"] == "出错" and "不是要的JSON" in ch["第3课 ながら"]["error"],
          f"回的不是 JSON → 块出错：{ch['第3课 ながら']['error']}")
    p2 = next(x for x in brain.calls if "てから" in x["title"])
    check("版权要求" not in p2["prompt"] and "可以沿用原文" in p2["prompt"], "没勾改写：提示词里没有改写要求")
    n_all = p1["prompt"].count("\n条目 ") + p1["prompt"].count("】条目 ")
    n_n1 = p2["prompt"].count("\n条目 ") + p2["prompt"].count("】条目 ")
    check(0 < n_n1 < n_all and "te-kara" not in p2["prompt"],
          f"等级范围 N1 预筛候选条目：{n_n1} < 全部 {n_all}，N5 的 te-kara 不在")
    st, body = post("/import/load", job="2")
    sj = body["state"]["job"]
    check(sj["failed"] == 2 and "出错 2 块" in sj["progress"], f"进度里说出错 2 块：{sj['progress']}")
    brain.fail = set()
    brain.badjson = set()
    cid = ch["第2课 たい"]["id"]
    st, body = post("/import/chunk_retry", job="2", chunk_id=str(cid))
    check(st == 200 and wait_background(30), f"重试一块：{st}")
    one = rows("SELECT * FROM import_chunk WHERE id = ?", cid)[0]
    check(one["chunk_status"] == "完成" and one["tries"] == 2 and not one["error"],
          f"重试后完成，次数 2：{one['chunk_status']} {one['tries']}")
    check(val("SELECT count(*) FROM import_lesson WHERE chunk = ?", cid) == 1, "这块的课进了草稿")
    st, _ = post("/import/chunk_retry", job="2", chunk_id=str(cid))
    wait_background(30)
    check(val("SELECT count(*) FROM import_lesson WHERE chunk = ?", cid) == 1,
          "同一块重试两次：先删这块上次的草稿，不重复")
    st, body = post("/import/chunk_retry", job="2", chunk_id="9999")
    check(st == 404, f"没有这一块 → 404：{st}")

    # ---------------- 四、审阅 ----------------
    print("四、审阅")
    st, body = post("/import/load", draft=str(d1["id"]))
    sd = (body.get("state") or {}).get("draft") or {}
    maps = (body.get("lists") or {}).get("draft_maps") or []
    opts = (body.get("lists") or {}).get("map_options") or []
    check(st == 200 and sd.get("title") == "〜てから" and (body.get("form") or {}).get("title") == "〜てから"
          and "draft" not in (body.get("form") or {}) and sd.get("back", "").endswith("?job=1"),
          "编辑页：字段填回表单（不放 draft 键），有回审阅页的地址")
    check([(m["map_kind"], m["map_code"]) for m in maps] == [("条目", "te-kara"), ("知识点", "f-time")]
          and any(o["value"] == "f-desire" for o in opts) and any(o["value"] == "te-kara" for o in opts),
          f"映射表、可选清单：{[(m['map_kind'], m['map_code']) for m in maps]}，选项 {len(opts)} 个")
    st, body = post("/import/draft_save", draft=str(d3["id"]), title="〜ながら（改）", draft_level="N4",
                    seq="3", summary="一边…一边…", explanation="改过的讲解", formation="ます形 + ながら",
                    examples="不是 JSON")
    check(st == 400 and "JSON 数组" in body.get("error", ""), f"例句不是 JSON 数组 → 400：{body.get('error')}")
    ex = json.dumps([{"jp": "音楽を聞きながら歩く。", "zh": "边听音乐边走。"}], ensure_ascii=False)
    st, body = post("/import/draft_save", draft=str(d3["id"]), title="〜ながら（改）", draft_level="N4",
                    seq="3", summary="一边…一边…", explanation="改过的讲解", formation="ます形 + ながら",
                    examples=ex)
    d3b = rows("SELECT * FROM import_lesson WHERE id = ?", d3["id"])[0]
    check(st == 200 and d3b["title"] == "〜ながら（改）" and d3b["draft_level"] == "N4"
          and d3b["examples"] == ex and "等级没认出" not in (d3b["issues"] or "")
          and (body.get("state") or {}).get("draft_note") == "保存了。",
          f"保存字段，问题重算（等级有了）：{d3b['issues']}")
    st, body = post("/import/map_add", draft=str(d3["id"]), map_typed="no-such-code", map_add="")
    check(st == 400 and "库里没有编号" in body.get("error", ""), f"输入库里没有的编号 → 400：{body.get('error')}")
    st, body = post("/import/map_add", draft=str(d3["id"]), map_typed="", map_add="")
    check(st == 400, "什么都没选 → 400")
    st, body = post("/import/map_add", draft=str(d3["id"]), map_typed="", map_add="f-time")
    st2, body2 = post("/import/map_add", draft=str(d3["id"]), map_typed="te-kara", map_add="f-desire")
    d3c = rows("SELECT * FROM import_lesson WHERE id = ?", d3["id"])[0]
    check(st == 200 and st2 == 200 and json.loads(d3c["points"]) == ["f-time"]
          and json.loads(d3c["items"]) == ["te-kara"]
          and "没映射到" not in (d3c["issues"] or ""),
          f"下拉选知识点、输入条目编号（输入的优先）：items={d3c['items']} points={d3c['points']}")
    check((body2.get("form") or {}) == {"map_add": "", "map_typed": ""},
          "加映射后只清空两个加映射的框，不冲掉正在改的字段")
    post("/import/map_add", draft=str(d3["id"]), map_typed="te-kara", map_add="")
    check(json.loads(rows("SELECT items FROM import_lesson WHERE id = ?", d3["id"])[0]["items"]) == ["te-kara"],
          "同一个编号加两次只有一个")
    st, body = post("/import/map_remove", draft=str(d3["id"]), map_code="te-kara")
    d3d = rows("SELECT * FROM import_lesson WHERE id = ?", d3["id"])[0]
    check(st == 200 and json.loads(d3d["items"]) == [] and json.loads(d3d["points"]) == ["f-time"]
          and [m["map_code"] for m in body["lists"]["draft_maps"]] == ["f-time"],
          "去掉一个映射，映射表回刷")
    check(val("SELECT count(*) FROM item") == val("SELECT count(*) FROM item") and
          val("SELECT count(*) FROM node WHERE code = 'no-such-code'") == 0, "加映射不新建")

    # 通过 / 驳回：审阅页行上（带 draft，地址里有 job）
    st, body = post("/import/draft_reject", job="1", draft=str(d2["id"]))
    check(st == 200 and rows("SELECT review FROM import_lesson WHERE id = ?", d2["id"])[0]["review"] == "驳回"
          and (body.get("state") or {}).get("job", {}).get("rejected") == 1,
          "驳回一课，审阅页回刷")
    # 编辑页（地址里只有 draft）
    st, body = post("/import/draft_pass", draft=str(d2["id"]))
    check(st == 200 and rows("SELECT review FROM import_lesson WHERE id = ?", d2["id"])[0]["review"] == "通过"
          and (body.get("state") or {}).get("draft", {}).get("review") == "通过",
          "编辑页上通过，编辑页回刷")
    post("/import/draft_reject", job="1", draft=str(d2["id"]))
    # 孤课：先把 d3 的映射清掉，看「全部通过有映射的课」不动它
    post("/import/map_remove", draft=str(d3["id"]), map_code="f-time")
    st, body = post("/import/pass_mapped", job="1")
    rv = {r["id"]: r["review"] for r in rows("SELECT id, review FROM import_lesson WHERE job = 1")}
    check(st == 200 and rv[d1["id"]] == "通过" and rv[d2["id"]] == "驳回" and rv[d3["id"]] == "待审"
          and "通过了：1 课" in (body.get("state") or {}).get("job_note", ""),
          f"全部通过有映射的课：只通过待审且有映射的（孤课、驳回的不动）：{rv}")
    post("/import/map_add", draft=str(d3["id"]), map_typed="te-kara", map_add="")
    post("/import/draft_pass", job="1", draft=str(d3["id"]))
    post("/import/draft_pass", job="1", draft=str(d2["id"]))

    # ---------------- 五、确认导入 ----------------
    print("五、确认导入")
    st, body = post("/import/confirm", job="2")
    check(st == 400 and "还没有通过的课" in body.get("error", ""), f"没有通过的课 → 400：{body.get('error')}")
    # 模拟「审阅之后条目被删」：草稿里塞一个库里没有的编号，导入时那一行拒收
    con = sqlite3.connect(db)
    con.execute("UPDATE import_lesson SET points = '[\"f-desire\", \"gone-node\"]' WHERE id = ?", (d2["id"],))
    con.commit()
    con.close()
    st, body = post("/import/confirm", job="1")
    sj = (body.get("state") or {}).get("job") or {}
    lf = ws / "content/series/mnn/lessons.jsonl"
    check(st == 200 and lf.is_file(), f"确认导入：{st} {body.get('error') or ''}")
    lines = [json.loads(x) for x in lf.read_text(encoding="utf-8").splitlines() if x.strip()]
    check([x["code"] for x in lines] == ["mnn-001", "mnn-002", "mnn-003"]
          and all(x["series"] == "mnn" for x in lines)
          and isinstance(lines[0]["items"], list) and lines[0]["items"] == ["te-kara"]
          and lines[0]["points"] == ["f-time"] and lines[2]["level"] == "N4"
          and json.loads(lines[0]["examples"])[0]["jp"] == "宿題をしてから遊びます。"
          and lines[1]["seq"] == 2 and set(lines[0]) >= {"code", "series", "level", "seq", "title",
                                                         "summary", "explanation", "formation",
                                                         "examples", "items", "points"},
          f"lessons.jsonl 按 README 的格式（items/points 是数组，examples 是 JSON 文本）：{[x['code'] for x in lines]}")
    seeds = [json.loads(x) for x in (ws / "content/series.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    check(seeds[0] == json.loads(series_seed0.splitlines()[0])
          and seeds[-1]["code"] == "mnn" and seeds[-1]["label"] == "测试 教材" and seeds[-1]["sort"] == 1
          and seeds[-1]["source"] == "测试里现造" and seeds[-1]["license"] == "自用",
          f"series.jsonl：hanabira 那行原样，新系列一行（sort 1）：{seeds[-1]}")
    rep = json.loads(rows("SELECT report FROM import_job WHERE id = 1")[0]["report"])
    check(str(rep["lessons"]) == "2" and str(rep["rejected"]) == "1" and str(rep["links"]) == "2"
          and str(rep["points"]) == "1",
          f"导入报告：2 课进库、拒收 1 行、条目映射 2、知识点 1：{rep}")
    rj = (body.get("lists") or {}).get("import_rejected") or []
    check(len(rj) == 1 and rj[0]["code"] == "mnn-002" and "gone-node" in rj[0]["reason"]
          and "拒收 1 行" in sj.get("report_note", "") and sj.get("textbook") == "#%E6%95%99%E6%9D%90",
          f"审阅页显示报告和拒收清单：{sj.get('report_note')} / {rj}")
    check(val("SELECT count(*) FROM lesson WHERE series = 'mnn'") == 2
          and val("SELECT count(*) FROM lesson WHERE code = 'mnn-002'") == 0,
          "库里 2 课，拒收的那课没进")
    st, body = post("/lesson/list", series="mnn")
    opts = [o["value"] for o in body["lists"]["series_options"]]
    check("mnn" in opts and [l["code"] for l in body["lists"]["lessons"]] == ["mnn-001", "mnn-003"]
          and body["state"]["series_head"] == "测试 教材",
          f"教材页：下拉出现新系列，选了它课文表是它的课：{opts}")
    st, body = post("/lesson/one", lesson="mnn-001")
    check(st == 200 and body["state"]["reading"]["title"] == "〜てから"
          and [i["code"] for i in body["lists"]["lesson_items"]] == ["te-kara", "f-time"],
          "读一课：标题、映射的条目、直接挂的知识点都在")
    post("/import/draft_reject", job="1", draft=str(d2["id"]))
    st, body = post("/import/confirm", job="1")
    check(st == 200 and val("SELECT count(*) FROM lesson WHERE series = 'mnn'") == 2,
          "同一任务审阅后再导一次：不算系列冲突，按系列清空重灌")

    # ---------------- 六、系列冲突 ----------------
    print("六、系列冲突")
    st, body = upload({**base}, "again.md", md)
    check(st == 400 and "覆盖已有系列" in body.get("error", ""), f"同代号新任务不勾覆盖 → 400：{body.get('error')}")
    st, body = upload({**base, "overwrite": True}, "again.md", md)
    check(st == 200 and wait_background(30), "勾上覆盖就能建")
    job3 = val("SELECT max(id) FROM import_job")
    check(rows("SELECT overwrite FROM import_job WHERE id = ?", job3)[0]["overwrite"] == 1, "任务记下了覆盖")

    # ---------------- 七、删除任务、撤下系列 ----------------
    print("七、删除任务、撤下系列")
    st, body = post("/import/job_delete", job=str(job3))
    check(st == 200 and body.get("go") == "#教材导入"
          and val("SELECT count(*) FROM import_job WHERE id = ?", job3) == 0
          and val("SELECT count(*) FROM import_chunk WHERE job = ?", job3) == 0
          and val("SELECT count(*) FROM import_lesson WHERE job = ?", job3) == 0
          and val("SELECT count(*) FROM lesson WHERE series = 'mnn'") == 2,
          "删除任务：三张草稿表的行没了，已导入的课还在，回首页")
    st, body = post("/import/series_withdraw", manage="hanabira")
    check(st == 400, f"hanabira 不能撤：{body.get('error')}")
    st, body = post("/import/series_withdraw", manage="nope")
    check(st == 404, "没有的系列 → 404")
    con = sqlite3.connect(db)
    con.execute("UPDATE learner_pref SET series = 'mnn' WHERE learner = 'me'")
    con.commit()
    con.close()
    learn0 = learning()   # 偏好改成 mnn 之后再比
    st, body = post("/import/home")
    sl = (body.get("lists") or {}).get("import_series") or []
    check([(x["code"], x["series_state"]) for x in sl] == [("mnn", "在用")]
          and sl[0]["href"].endswith("?manage=mnn") and sl[0]["lesson_n"] == 2,
          f"首页系列表（不含 hanabira）：在用、2 课，链接到 ?manage=：{sl}")
    st, body = post("/import/load", manage="mnn")
    sv = (body.get("state") or {}).get("series_view") or {}
    check(sv.get("can_withdraw") == 1 and "2 课" in sv.get("head", ""), f"系列页：{sv.get('head')}")
    n_file = len([x for x in lf.read_text(encoding="utf-8").splitlines() if x.strip()])
    st, body = post("/import/series_withdraw", manage="mnn")
    sv = (body.get("state") or {}).get("series_view") or {}
    check(st == 200 and val("SELECT count(*) FROM lesson WHERE series = 'mnn'") == 0
          and val("SELECT count(*) FROM item_lesson WHERE lesson LIKE 'mnn-%'") == 0
          and val("SELECT count(*) FROM lesson_point WHERE lesson LIKE 'mnn-%'") == 0
          and val("SELECT sort FROM series WHERE code = 'mnn'") == -1
          and "撤下了" in sv.get("note", ""),
          f"撤下：课和映射清空、sort=-1：{sv.get('note')}")
    seeds = [json.loads(x) for x in (ws / "content/series.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    wf = ws / "content/series/mnn/lessons.withdrawn.jsonl"
    check([s["sort"] for s in seeds if s["code"] == "mnn"] == [-1]
          and not [x for x in lf.read_text(encoding="utf-8").splitlines() if x.strip()]
          and wf.is_file() and len(wf.read_text(encoding="utf-8").splitlines()) == n_file,
          "文件：series.jsonl 那行 sort=-1，lessons.jsonl 空了，课文挪到 lessons.withdrawn.jsonl")
    st, body = post("/lesson/list")
    check("mnn" not in [o["value"] for o in body["lists"]["series_options"]]
          and body["state"]["series_head"] == "hanabira 语法",
          "下拉里没有它了；选过它的学习者回到 hanabira")
    check(rows("SELECT series FROM learner_pref WHERE learner = 'me'")[0]["series"] == "mnn",
          "学习者的偏好那行没动（重新上架就回去）")
    r = client(ws).post("/lesson/import", json={"form": {"series": "mnn"}}).get_json()
    check(str(r.get("lessons")) == "0" and val("SELECT sort FROM series WHERE code = 'mnn'") == -1,
          "撤下后按系列重导（启动时会做）：0 课，仍然隐藏——课不会自己回来")
    st, body = post("/import/confirm", job="1")
    check(st == 200 and val("SELECT count(*) FROM lesson WHERE series = 'mnn'") == 2
          and val("SELECT sort FROM series WHERE code = 'mnn'") == 1,
          "再确认导入一次：重新上架（sort 回到 1）")
    st, body = post("/import/series_withdraw", manage="mnn")
    check(st == 200, "再撤下（留着最后比学习记录）")

    # ---------------- 八、hanabira、学习记录 ----------------
    print("八、hanabira、学习记录")
    hb1 = (val("SELECT count(*) FROM lesson WHERE series = 'hanabira'"),
           val("SELECT count(*) FROM item_lesson il JOIN lesson l ON l.code = il.lesson "
               "WHERE l.series = 'hanabira'"))
    check(hb1 == hb0, f"hanabira 课数、映射数没变：{hb0} → {hb1}")
    check(learning() == learn0, "学习记录（attempt、mastery、score、对话、偏好……）一行没动")

    # ---------------- 九、老库补表 ----------------
    print("九、老库补表")
    old = Path(tempfile.mkdtemp(prefix="old_kg_"))
    shutil.copy(db, old / "app.db")
    con = sqlite3.connect(old / "app.db")
    for t in ("import_lesson", "import_chunk", "import_job", "import_view"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.commit()
    n_lesson = con.execute("SELECT count(*) FROM lesson").fetchone()[0]
    con.close()
    migrate_additive(old / "app.db", ws / "entities")
    con = sqlite3.connect(old / "app.db")
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check({"import_job", "import_chunk", "import_lesson"} <= names
          and con.execute("SELECT count(*) FROM lesson").fetchone()[0] == n_lesson,
          "没有草稿表的老库：迁移只加补上三张表，原有的课还在")
    con.close()

    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
