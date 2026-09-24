# -*- coding: utf-8 -*-
"""批量导入单词。

    from tools.word_import import import_words, format_report
    report = import_words("kg/app.db", "kg/queries", "kg/content/words.jsonl")
    print(format_report(report))

也可以在 .zs 里用：`用包 kg` 之后 `导入单词 app.db content/words.jsonl`。

## 文件格式

JSONL（一行一个）或者 JSON 数组：

    {"汉字": "食べる", "假名": "たべる", "中文": "吃", "知识点": "verb-groups"}
    {"假名": "そこ", "中文": "那里"}

汉字和知识点可以不写。英文键（kanji / kana / meaning / point）也认——
从别处导出的词表多半是英文键，为这个再转一道没必要。

## 规则

**按「汉字 + 假名」认同一个词**，重复导入是更新不是新增。同音词（はし：
桥、筷子）靠汉字区分；没有汉字的词只能靠假名，所以两个都没有汉字、假名
又相同的词会被当成同一个——那种情况本来也该合成一条。

**知识点不存在就不挂**，词照样导进来，在报告里单独列出来。不这么做的话，
一个拼错的知识点编号会让整批词都进不去；而挂错知识点比没挂更难发现。

**整批在一个事务里**：文件中途坏了全部回滚，不会导一半。单条的问题（缺
假名、知识点不存在）不算意外，照常提交。
"""

import json
import sqlite3
from pathlib import Path

# 中文键和英文键都认。值是文件里可能出现的写法。
KEYS = {
    "kanji": ("汉字", "漢字", "kanji", "word"),
    "kana": ("假名", "仮名", "kana", "reading"),
    "meaning": ("中文", "词义", "释义", "meaning", "gloss"),
    "point": ("知识点", "考点", "point", "node"),
}


class WordError(Exception):
    """文件读不了、格式不对。"""


def _pick(obj: dict, field: str) -> str:
    for k in KEYS[field]:
        v = obj.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def load_items(path) -> list:
    """读词表，返回 [(行号, 对象), ...]。JSON 数组时行号是第几个元素。"""
    p = Path(path)
    if not p.is_file():
        raise WordError(f"文件不存在：{p}")
    text = p.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        try:
            return [(i, x) for i, x in enumerate(json.loads(text), 1)]
        except json.JSONDecodeError as e:
            raise WordError(f"{p.name} 不是合法的 JSON：{e}") from e

    out = []
    for no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append((no, json.loads(line)))
        except json.JSONDecodeError as e:
            raise WordError(f"{p.name} 第 {no} 行不是合法的 JSON：{e}") from e
    return out


def _sql(qdir: Path, name: str) -> str:
    f = Path(qdir) / f"{name}.sql"
    if not f.is_file():
        raise WordError(f"缺查询文件：{f}")
    return f.read_text(encoding="utf-8")


def import_words(db, qdir, path) -> dict:
    """导入一个词表。返回报告，用 format_report 转成文字。"""
    items = load_items(path)
    qdir = Path(qdir)
    sql_find = _sql(qdir, "word_find")
    sql_insert = _sql(qdir, "word_insert")
    sql_update = _sql(qdir, "word_update")

    report = {"file": str(path), "items": len(items), "new": 0, "updated": 0,
              "skipped": [], "no_point": [], "unknown_point": []}

    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("BEGIN")
        points = {r[0] for r in con.execute("SELECT code FROM node")}

        for no, obj in items:
            if not isinstance(obj, dict):
                report["skipped"].append((no, "不是对象"))
                continue
            kana = _pick(obj, "kana")
            meaning = _pick(obj, "meaning")
            if not kana or not meaning:
                report["skipped"].append((no, "缺假名或中文"))
                continue
            kanji = _pick(obj, "kanji")
            point = _pick(obj, "point")
            if point and point not in points:
                # 词照样导，只是不挂——挂错知识点比没挂更难发现
                report["unknown_point"].append((no, kana, point))
                point = ""
            if not point:
                report["no_point"].append((no, kana))

            row = con.execute(sql_find, {"kanji": kanji, "kana": kana}).fetchone()
            args = {"kanji": kanji, "kana": kana, "meaning": meaning, "point": point}
            if row:
                con.execute(sql_update, dict(args, id=row[0]))
                report["updated"] += 1
            else:
                con.execute(sql_insert, args)
                report["new"] += 1

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return report


def format_report(r: dict) -> str:
    lines = [
        f"导入 {Path(r['file']).name}：{r['items']} 条",
        f"  新增 {r['new']}，更新 {r['updated']}"
        + (f"，跳过 {len(r['skipped'])}" if r["skipped"] else ""),
    ]
    for no, why in r["skipped"][:10]:
        lines.append(f"  [跳过] 第 {no} 条：{why}")
    if r["unknown_point"]:
        lines.append(f"  [警告] {len(r['unknown_point'])} 条的知识点不存在，没挂上：")
        for no, kana, point in r["unknown_point"][:5]:
            lines.append(f"           第 {no} 条 {kana} → {point}")
    if r["no_point"]:
        lines.append(f"  [提示] {len(r['no_point'])} 条没有知识点，"
                     f"按知识点出题时取不到它们")
    return "\n".join(lines)
