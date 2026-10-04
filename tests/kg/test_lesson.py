# -*- coding: utf-8 -*-
"""课文：lesson / item_lesson 两张表，/lesson/import 和 /item/lessons。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_lesson.py

  一、数据文件本身：每行是合法 JSON、必填字段齐、编号不重复、例句是
      合法 JSON 且每句有日文和中文、挂接两头都指得到
  二、导入：课数、挂接数跟文件一致，没有挂不上的、没有孤课；例句原样
      进库（拿出来能解析、跟文件一致）；changed 是整数
  三、重导是整表重灌：再导一次数目不变；映射文件删一行，库里那条也没了
  四、挂接拼错：那一行不挂、报告里说得出是第几行，别的照常进库
  五、课文文件坏了（缺编号、编号重复）：整个导入回滚，库里原来的课一条不少
  六、/item/lessons：按 rank 排；没挂课的条目给空列表；不存在的条目 404；
      不给 item 400
  七、学习记录不受影响：导入课文前后 attempt / mastery / score 一行不动
  八、prune 删条目时连带删它的挂接，不留指向空处的行
"""

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws   # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def rows_of(db, sql, *args):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def read_jsonl(p: Path) -> list:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    content = ROOT / "kg" / "content"
    lessons = read_jsonl(content / "lessons.jsonl")
    links = read_jsonl(content / "item_lessons.jsonl")
    items = {d["code"] for d in read_jsonl(content / "items.jsonl")}

    print("一、数据文件")
    codes = [d.get("code") for d in lessons]
    check(len(lessons) > 0 and len(codes) == len(set(codes)),
          f"{len(lessons)} 课，编号不重复")
    need = ("code", "level", "title", "summary", "explanation")
    bad = [d.get("code") for d in lessons if not all((d.get(k) or "").strip() for k in need)]
    check(not bad, f"必填字段齐：{bad[:5]}")
    check(all(d["level"] in ("N5", "N4", "N3", "N2", "N1") for d in lessons), "等级都是 N5–N1")
    bad_ex = []
    for d in lessons:
        try:
            ex = json.loads(d["examples"])
            if not ex or not all(e.get("jp") and e.get("zh") for e in ex):
                bad_ex.append(d["code"])
        except (ValueError, TypeError):
            bad_ex.append(d["code"])
    check(not bad_ex, f"例句都是合法 JSON，每句有日文和中文：{bad_ex[:5]}")
    import re
    meta = [d["code"] for d in lessons
            if re.search(r"英文|原讲解|原句|原文", d["summary"] + d["explanation"])]
    check(not meta, f"讲解里没有混进核对时的批注（英文、原讲解……）：{meta}")
    check(not [d for d in lessons if re.search(r"[A-Za-z]{4,}", d["title"])],
          "标题里没有残留英文（Verb、Noun、罗马音）")
    dangling = [(l["item"], l["lesson"]) for l in links
                if l["item"] not in items or l["lesson"] not in set(codes)]
    check(not dangling, f"挂接两头都指得到：{dangling[:5]}")
    pairs = [(l["item"], l["lesson"]) for l in links]
    check(len(pairs) == len(set(pairs)), "挂接没有重复的对")
    check(not set(codes) - {l["lesson"] for l in links}, "每一课都挂到了条目上")

    ws = make_ws(Path(tempfile.mkdtemp(prefix="lesson_")))
    import_graph(ws)
    c = client(ws)
    db = ws / "app.db"

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def rows(sql, *args):
        return rows_of(db, sql, *args)

    def n(table):
        return rows(f"SELECT count(*) n FROM {table}")[0]["n"]

    # 学习记录先放几行，最后看导入有没有碰它们
    con = sqlite3.connect(db)
    con.execute("INSERT INTO attempt(learner, point, item, correct) VALUES ('k','tai','q1',1)")
    con.execute("INSERT INTO mastery(learner, point, right, total, mastered) VALUES ('k','tai',1,1,0)")
    con.execute("INSERT INTO score(learner, point, value) VALUES ('k','hiragana',40)")
    con.commit()
    con.close()
    keep = {t: rows(f"SELECT * FROM {t}") for t in ("attempt", "mastery", "score")}

    print("二、导入")
    st, body = post("/lesson/import")
    check(st == 200, f"导入：{st} {body.get('error', '')}")
    check(body.get("lessons") == str(len(lessons)) and n("lesson") == len(lessons),
          f"课数一致：报告 {body.get('lessons')}，库里 {n('lesson')}，文件 {len(lessons)}")
    check(body.get("links") == str(len(links)) and n("item_lesson") == len(links),
          f"挂接一致：报告 {body.get('links')}，库里 {n('item_lesson')}，文件 {len(links)}")
    check(body.get("failed") == "0" and body.get("orphans") == "0",
          f"没有挂不上的、没有孤课：{body.get('failed')} / {body.get('orphans')}")
    src = {d["code"]: d for d in lessons}
    got = {r["code"]: r for r in rows("SELECT * FROM lesson")}
    diff = [k for k in src if json.loads(got[k]["examples"]) != json.loads(src[k]["examples"])]
    check(not diff, f"例句原样进库：{diff[:3]}")
    diff = [k for k in src if got[k]["explanation"] != src[k]["explanation"]]
    check(not diff, f"讲解原样进库（含引号、括号、全角符号）：{diff[:3]}")
    check(all(isinstance(r["changed"], int) for r in got.values())
          and sum(r["changed"] for r in got.values()) == sum(d["changed"] for d in lessons),
          "changed 存成整数、跟文件一致")

    print("三、重导是整表重灌")
    post("/lesson/import")
    check(n("lesson") == len(lessons) and n("item_lesson") == len(links), "再导一次，数目不变")
    short = links[1:]
    (ws / "content" / "item_lessons.jsonl").write_text(
        "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in short), encoding="utf-8")
    st, body = post("/lesson/import")
    gone = links[0]
    check(n("item_lesson") == len(short)
          and not rows("SELECT 1 FROM item_lesson WHERE item=? AND lesson=?",
                       gone["item"], gone["lesson"]),
          f"映射删一行，库里那条也没了：{gone['item']}→{gone['lesson']}")

    print("四、挂接拼错")
    broken = [{"item": "no-such-item", "lesson": links[0]["lesson"], "rank": 1},
              {"item": links[0]["item"], "lesson": "hb-nope", "rank": 1}] + links
    (ws / "content" / "item_lessons.jsonl").write_text(
        "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in broken), encoding="utf-8")
    st, body = post("/lesson/import")
    check(st == 200 and body.get("failed") == "2", f"两行没挂上：{st} failed={body.get('failed')}")
    note = body.get("note") or ""
    check("第1行" in note and "no-such-item" in note and "第2行" in note and "hb-nope" in note,
          f"报告说得出是第几行、哪一对：{note[:120]}")
    check(n("item_lesson") == len(links), "别的照常进库")

    print("五、课文文件坏了")
    good = n("lesson")
    lp = ws / "content" / "lessons.jsonl"
    orig = lp.read_text(encoding="utf-8")
    nocode = dict(lessons[0], code="")
    lp.write_text(orig + json.dumps(nocode, ensure_ascii=False) + "\n", encoding="utf-8")
    st, body = post("/lesson/import")
    check(st >= 400, f"缺编号：导入失败 {st} {body.get('error', '')}")
    check(n("lesson") == good and n("item_lesson") == len(links),
          f"整个回滚，库里的课一条不少：{n('lesson')} / {n('item_lesson')}")
    lp.write_text(orig + json.dumps(lessons[0], ensure_ascii=False) + "\n", encoding="utf-8")
    st, body = post("/lesson/import")
    check(st >= 400, f"编号重复：导入失败 {st} {body.get('error', '')}")
    check(n("lesson") == good, "也回滚了")
    lp.write_text(orig, encoding="utf-8")
    st, body = post("/lesson/import")
    check(st == 200 and n("lesson") == good, "文件修好之后照常导入（对照）")

    print("六、/item/lessons")
    multi = {}
    for l in links:
        multi.setdefault(l["item"], []).append((l["rank"], l["lesson"]))
    item, want = max(multi.items(), key=lambda kv: len(kv[1]))
    st, body = post("/item/lessons", item=item)
    ls = (body.get("lists") or {}).get("lessons") or []
    check(st == 200 and [x["code"] for x in ls] == [c for _, c in sorted(want)],
          f"{item} 挂 {len(want)} 课，按 rank 排：{[x['code'] for x in ls]}")
    check(ls and all(ls[0].get(k) for k in ("title", "summary", "explanation", "examples")),
          "带标题、一句话、讲解、例句")
    st, body = post("/item/lessons", item="tai")
    ex = json.loads(((body.get("lists") or {}).get("lessons") or [{}])[0].get("examples") or "[]")
    check(ex and ex[0]["jp"] and ex[0]["zh"], f"例句拿出来能解析：{ex[:1]}")
    bare = sorted(items - set(multi))[0]
    st, body = post("/item/lessons", item=bare)
    check(st == 200 and (body.get("lists") or {}).get("lessons") == [],
          f"没挂课的条目（{bare}）：空列表，不是报错")
    st, body = post("/item/lessons", item="no-such")
    check(st == 404 and "没有这个条目" in (body.get("error") or ""), f"不存在的条目：{st}")
    st, body = post("/item/lessons")
    check(st == 400, f"不给 item：{st} {body.get('error')}")

    print("七、学习记录不受影响")
    check({t: rows(f"SELECT * FROM {t}") for t in keep} == keep,
          "导入课文好几轮之后，attempt / mastery / score 原样")

    print("八、prune 连带删挂接")
    from kg import prune
    root = Path(tempfile.mkdtemp(prefix="prune_lesson_"))
    shutil.copytree(ws / "content", root / "content")
    shutil.copy(db, root / "app.db")
    victim = links[0]["item"]
    ip = root / "content" / "items.jsonl"
    kept = [l for l in ip.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l)["code"] != victim]
    ip.write_text("\n".join(kept) + "\n", encoding="utf-8")
    con = sqlite3.connect(root / "app.db")
    con.execute("DELETE FROM attempt WHERE point = ?", (victim,))
    con.execute("DELETE FROM mastery WHERE point = ?", (victim,))
    con.execute("UPDATE item SET after = NULL WHERE after = ?", (victim,))
    con.execute("DELETE FROM contrast WHERE a = ? OR b = ?", (victim, victim))
    con.commit()
    con.close()
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        prune.main(["--删"], root=root)
    left = rows_of(root / "app.db", "SELECT count(*) n FROM item_lesson WHERE item = ?", victim)[0]["n"]
    gone = not rows_of(root / "app.db", "SELECT 1 FROM item WHERE code = ?", victim)
    check(gone and left == 0, f"删掉 {victim} 后它的挂接也没了（剩 {left} 行）")
    others = rows_of(root / "app.db", "SELECT count(*) n FROM item_lesson")[0]["n"]
    check(others == n("item_lesson") - sum(1 for l in links if l["item"] == victim),
          f"别的挂接一条没少：{others}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
