# -*- coding: utf-8 -*-
"""单词默写：routes/dictation.zs、scripts/dictation_pick.zs、japanese 包的「判默写」。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_dictation.py

临时工作区（照 kg 搭，不导内容），单词手工插几条，不碰 kg/app.db。

  一、判默写（直接调动词）：平/片假名互通、全半角、去空白句号、汉字或假名都对、
      同义词（意思完全一样）也对、意思只差等级前缀也算一样、同读音不同意思的
      判错并说出写的是哪个词、看汉字写读音只认读音、同汉字另一个读音（意思不同
      判错并提示「另一个读法」、意思相同算对）、空答案判错、参数坏了抛
  二、出题过滤：意思空的、五十音、活用形、「X 的…」说明、量词音变、です/ます
      不出；「[N1] 的确」这种照出；看汉字写读音只出有汉字且汉字≠假名的；等级过滤
  三、一轮：10 个、不重复，出够了 dphase=end、错词表；Enter 交两次只算一次；
      空答案 400 不记；两个方向的卡面
  四、错词本：答错进本；不看提示连续答对 2 次出本；看了提示答对不算；按方向分开；
      按等级筛；练错词只出本里的；本空时 dphase=empty；进度页的统计和链接
  五、不写 attempt / mastery / score；别的学习者不串；老库补表不动已有表
"""

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, make_ws          # noqa: E402
from kg.__main__ import ensure_new_tables              # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def load_judge():
    from tools.verbs import _import_file
    m = _import_file(ROOT / "verbs/japanese/defs/判默写.py", "_verb_test_judge")
    return m.判默写


NODES = [("noun", "名词"), ("verb-groups", "动词"), ("hiragana", "平假名"),
         ("katakana", "片假名"), ("causative", "使役形"), ("counters-sound", "量词音变"),
         ("teineigo", "丁宁语")]

# (kanji, kana, meaning, point)
WORDS = [
    ("会う", "あう", "[N5] 见面", "verb-groups"),
    ("逢う", "あう", "[N5] 见面", "verb-groups"),
    ("合う", "あう", "[N4] 合适", "verb-groups"),
    ("一日", "いちにち", "[N5] 一天", "noun"),
    ("一日", "ついたち", "[N5] 一号", "noun"),
    (None, "テレビ", "[N5] 电视", "noun"),
    ("いただく", "いただく", "吃/喝/领受（谦让语）", "noun"),
    ("如何にも", "いかにも", "[N1] 的确；实在", "noun"),
]
FILLER_N3 = [(f"字{i}", f"じ{chr(0x3042 + i)}", f"[N3] 意思{i}", "noun") for i in range(12)]
EXCLUDED = [
    (None, "あ", "", "hiragana"),
    (None, "ア", None, "katakana"),
    ("憎ませる", "にくませる", "憎む 的使役形", "causative"),
    ("一本", "いっぽん", "促音＋ぽ", "counters-sound"),
    (None, "ございます", "ある 的郑重说法", "teineigo"),
    (None, "です", "判断句的礼貌形", "teineigo"),
    ("無意", "むい", "", "noun"),
]


def main():
    judge = load_judge()

    def j(direction, answer, word, near=()):
        return judge({"方向": direction, "作答": answer, "词": word, "候选": list(near)})

    au = {"kanji": "会う", "kana": "あう", "meaning": "[N5] 见面"}
    au2 = {"kanji": "逢う", "kana": "あう", "meaning": "[N5] 见面"}
    au3 = {"kanji": "合う", "kana": "あう", "meaning": "[N4] 合适"}
    tv = {"kanji": "", "kana": "テレビ", "meaning": "[N5] 电视"}
    nichi = {"kanji": "一日", "kana": "いちにち", "meaning": "[N5] 一天"}
    tachi = {"kanji": "一日", "kana": "ついたち", "meaning": "[N5] 一号"}

    print("一、判默写")
    check(j("meaning", "会う", au)["correct"] == "1", "写汉字：对")
    check(j("meaning", "あう", au)["correct"] == "1", "写平假名：对")
    check(j("meaning", "アウ", au)["correct"] == "1", "写片假名：对（片→平）")
    check(j("meaning", "ｱｳ", au)["correct"] == "1", "半角片假名：对（NFKC）")
    check(j("meaning", " あ う。", au)["correct"] == "1", "多了空白和句号：对")
    check(j("meaning", "てれび", tv)["correct"] == "1", "库里是片假名、写平假名：对")
    check(j("meaning", "ＴＶ", tv)["correct"] == "0", "写别的：错（对照）")
    r = j("meaning", "逢う", au, [au2, au3])
    check(r["correct"] == "1" and "意思一样" in r["note"], f"同义词（意思完全一样）：对，{r['note']}")
    syn = {"kanji": "遇う", "kana": "あう", "meaning": "见面"}
    check(j("meaning", "遇う", au, [syn])["correct"] == "1", "意思只差等级前缀也算一样")
    r = j("meaning", "合う", au, [au2, au3])
    check(r["correct"] == "0" and "合う" in r["note"] and "合适" in r["note"],
          f"同读音不同意思（会う 写成 合う）：错，说出写的是哪个：{r['note']}")
    r = j("meaning", "合う", au, [])
    check(r["correct"] == "0", "候选里没有它也是错")
    check(j("reading", "いちにち", nichi, [tachi])["correct"] == "1", "看汉字写读音：读音对")
    check(j("reading", "イチニチ", nichi, [tachi])["correct"] == "1", "读音写片假名也对")
    check(j("reading", "一日", nichi, [tachi])["correct"] == "0", "看汉字写读音写汉字：错")
    r = j("reading", "ついたち", nichi, [tachi])
    check(r["correct"] == "0" and "另一个读法" in r["note"], f"同汉字另一个读音、意思不同：错并提示：{r['note']}")
    same = {"kanji": "一日", "kana": "ひとひ", "meaning": "[N5] 一天"}
    r = j("reading", "ひとひ", nichi, [same, tachi])
    check(r["correct"] == "1" and "也对" in r["note"], f"同汉字另一个读音、意思相同：对：{r['note']}")
    r = j("meaning", "", au)
    check(r["correct"] == "0" and r["note"], "空答案：错")
    check(j("meaning", "  。", au)["correct"] == "0", "只有空白句号：错")
    r = judge(json.dumps({"方向": "meaning", "作答": "あう", "词": au, "候选": "[]"}, ensure_ascii=False))
    check(r["correct"] == "1", "参数是 JSON 文本也认")
    for bad in ({"方向": "x", "作答": "a", "词": au}, {"方向": "meaning", "作答": "a", "词": {}}, "不是JSON"):
        try:
            judge(bad)
            check(False, f"坏参数没抛：{bad}")
        except ValueError:
            check(True, f"坏参数抛错：{str(bad)[:30]}")

    tmp = Path(tempfile.mkdtemp(prefix="dictation_test_"))
    (tmp / "ws").mkdir()
    ws = make_ws(tmp / "ws", with_content=False)
    con = sqlite3.connect(ws / "app.db")
    con.executemany("INSERT INTO node(code, label) VALUES(?, ?)", NODES)
    con.executemany("INSERT INTO word(kanji, kana, meaning, point) VALUES(?, ?, ?, ?)",
                    WORDS + FILLER_N3 + EXCLUDED)
    con.commit()
    ids = {(r[1], r[2]): r[0] for r in con.execute("SELECT id, kanji, kana FROM word")}
    excluded_ids = {ids[(k, n)] for k, n, _, _ in EXCLUDED}
    c = client(ws)

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, r.get_json() or {}

    def st(body):
        return body.get("state") or {}

    def cur():
        row = con.execute("SELECT current_word FROM dictation_state WHERE learner = 'me'").fetchone()
        return row[0] if row else None

    def word(wid):
        return con.execute("SELECT id, kanji, kana, meaning FROM word WHERE id = ?", (wid,)).fetchone()

    def pick(learner="me", direction="meaning", level="全部", source="random", seen=""):
        sql = (ws / "queries/dictation_pick.sql").read_text(encoding="utf-8")
        row = con.execute(sql, {"learner": learner, "direction": direction, "level": level,
                                "source": source, "seen": seen}).fetchone()
        return row[0] if row else None

    def pool(direction="meaning", level="全部"):
        got, seen = [], ","
        while True:
            w = pick(direction=direction, level=level, seen=seen)
            if w is None:
                return got
            got.append(w)
            seen += f"{w},"

    print("二、出题过滤")
    p = pool()
    check(not (set(p) & excluded_ids), f"排除的词一个都不出（池里 {len(p)} 个）")
    check(len(p) == len(WORDS) + len(FILLER_N3), f"别的都能出：{len(p)}")
    check(ids[("如何にも", "いかにも")] in p, "「[N1] 的确」不是「X 的…」说明，照出")
    pr = pool("reading")
    check(ids[(None, "テレビ")] not in pr and ids[("いただく", "いただく")] not in pr,
          "看汉字写读音：没汉字的、汉字就是假名的不出")
    check(ids[("会う", "あう")] in pr and len(pr) == len(p) - 2, f"有汉字的都出：{len(pr)}")
    n5 = pool(level="N5")
    check(sorted(n5) == sorted(ids[(k, n)] for k, n, m, _ in WORDS if m.startswith("[N5]")),
          f"等级 N5 只出 [N5] 的：{len(n5)}")
    check(len(pool(level="N3")) == 12 and not pool(level="N2"), "N3 是 12 个，N2 没有")
    check(ids[("いただく", "いただく")] not in pool(level="N5"), "没有等级前缀的只在「全部」里")

    print("三、一轮")
    s, b = post("/dictation/state")
    check(s == 200 and b["form"] == {"dict_direction": "看中文写日语", "dict_level": "全部",
                                     "dict_source": "随机"}, f"进页面：默认值 {b.get('form')}")
    check("messages" not in b, "进页面不推消息")
    s, b = post("/dictation/answer", dict_answer="x")
    check(s == 400, "还没出词就交：400")
    s, b = post("/dictation/start", dict_direction="看中文写日语", dict_level="N3", dict_source="随机")
    check(s == 200 and st(b).get("dphase") == "ask", f"开始：出词 {st(b).get('dphase')}")
    card = st(b)["dcard"]
    w = word(cur())
    check(card["stem"] == w[3].replace("[N3] ", "") and card["head"] == "N3・看中文写日语",
          f"卡面：意思去掉等级前缀 + 抬头 {card['head']}「{card['stem']}」")
    check(not card["sub"] and not card["hint"], "看中文写日语没有副行，还没提示")
    s, b = post("/dictation/answer", dict_answer="")
    check(s == 400 and not con.execute("SELECT count(*) FROM word_attempt").fetchone()[0],
          "空答案：400，不记")
    seen_round, right = [], 0
    for i in range(10):
        wid = cur()
        seen_round.append(wid)
        w = word(wid)
        ok = i % 3 != 0
        s, b = post("/dictation/answer", dict_answer=w[2] if ok else "ちがう")
        right += ok
        d = st(b).get("dcard", {})
        if i == 0:
            check(s == 200 and st(b)["dphase"] == "done" and d["verdict"].startswith("✗"),
                  f"答错：{d.get('verdict')}")
            check(d["right"] == f"正确：{w[1]}【{w[2]}】{w[3][5:]}" and d["mine"] == "你写的：ちがう",
                  f"批改：{d['right']} / {d['mine']}")
            s2, b2 = post("/dictation/answer", dict_answer=w[2])
            check(s2 == 400, "同一个再交：400")
        if i == 1:
            check(d["verdict"].startswith("○"), f"答对：{d['verdict']}")
        s, b = post("/dictation/next")
    check(len(set(seen_round)) == 10, f"一轮 10 个不重复：{len(set(seen_round))}")
    check(st(b).get("dphase") == "end", f"出够 10 个：dphase={st(b).get('dphase')}")
    check(f"答对 {right} 个，共 10 个" in st(b).get("dround", {}).get("text", ""),
          f"本轮成绩：{st(b).get('dround')}")
    wrong_rows = (b.get("lists") or {}).get("round_wrong") or []
    check(len(wrong_rows) == 10 - right and all("【" in r["label"] for r in wrong_rows)
          and all(r["mine"] == "ちがう" for r in wrong_rows), f"错词表 {len(wrong_rows)} 行：{wrong_rows[:1]}")
    n_att = con.execute("SELECT count(*) FROM word_attempt").fetchone()[0]
    check(n_att == 10, f"word_attempt 10 行（交两次只算一次）：{n_att}")

    # 只有 12 个 N3 词：第二轮出完 12 个之前也不会重复；N2 没有词
    s, b = post("/dictation/start", dict_direction="看中文写日语", dict_level="N2", dict_source="随机")
    check(s == 404 and "没有" in (b.get("error") or ""), f"N2 没有词：404 {b.get('error')}")
    s, b = post("/dictation/start", dict_direction="看中文写日语", dict_level="N3", dict_source="随机")
    first = cur()
    check(first not in seen_round, "随机：没练过的词优先（12 个里还有 2 个没练过）")

    print("三之二、看汉字写读音")
    s, b = post("/dictation/start", dict_direction="看汉字写读音", dict_level="N5", dict_source="随机")
    card = st(b)["dcard"]
    w = word(cur())
    check(card["stem"] == w[1] and card["sub"] == "意思：" + w[3][5:] and card["head"] == "N5・看汉字写读音",
          f"卡面：汉字 + 意思 {card['stem']} / {card['sub']}")
    s, b = post("/dictation/hint")
    hint = st(b)["dcard"]["hint"]
    check(f"「{w[2][0]}」" in hint and f"一共 {len(w[2])} 个字" in hint, f"提示：{hint}")
    s, b = post("/dictation/answer", dict_answer=w[2])
    check(st(b)["dcard"]["verdict"].startswith("○") and "提示" in st(b)["dcard"]["verdict"],
          f"看了提示答对：{st(b)['dcard']['verdict']}")
    last = con.execute("SELECT direction, correct, hinted FROM word_attempt ORDER BY id DESC").fetchone()
    check(last == ("reading", 1, 1), f"记 reading、correct=1、hinted=1：{last}")
    s, b = post("/dictation/next")
    check(con.execute("SELECT hinted FROM dictation_state").fetchone()[0] == 0, "下一个：提示清掉")
    s, b = post("/dictation/state")
    check(b["form"]["dict_direction"] == "看汉字写读音" and b["form"]["dict_level"] == "N5",
          "再进页面：顶栏是上次选的")

    print("四、错词本")
    con.execute("DELETE FROM word_attempt")
    con.commit()
    a, nichi_id = ids[("会う", "あう")], ids[("一日", "いちにち")]

    def book(direction="meaning", level="全部", learner="me"):
        s, b = post("/dictation/book", direction=direction, level=level, learner=learner)
        return [r["word"] for r in (b.get("lists") or {}).get("book") or []]

    def attempt(wid, correct, direction="meaning", hinted=0):
        con.execute("INSERT INTO word_attempt(learner, word, direction, answer, correct, hinted)"
                    " VALUES('me', ?, ?, 'x', ?, ?)", (wid, direction, correct, hinted))
        con.commit()

    check(book() == [], "没作答：错词本空（对照）")
    attempt(a, 1)
    check(book() == [], "只答对过：不进本")
    attempt(a, 0)
    check(book() == [a], "答错：进本")
    check(book("reading") == [], "另一个方向不算")
    attempt(a, 1)
    check(book() == [a], "答对 1 次：还在")
    attempt(a, 1, hinted=1)
    check(book() == [a], "看了提示答对：不算")
    attempt(a, 1)
    check(book() == [], "不看提示连续答对 2 次：出本")
    attempt(a, 0)
    check(book() == [a], "又错：又进本")
    attempt(nichi_id, 0, direction="reading")
    check(book("reading") == [nichi_id] and book() == [a], "按方向分开")
    attempt(ids[("合う", "あう")], 0)
    check(set(book()) == {a, ids[("合う", "あう")]} and book(level="N4") == [ids[("合う", "あう")]],
          "按等级筛：N4 只有 合う")
    check(book(learner="other") == [], "别的学习者看不到")
    for _ in range(3):
        s, b = post("/dictation/start", dict_direction="看中文写日语", dict_level="全部", dict_source="错词复习")
        check(cur() in (a, ids[("合う", "あう")]), f"错词复习只出本里的：{cur()}")
    s, b = post("/dictation/answer", dict_answer="あう")
    s, b = post("/dictation/next")
    s, b = post("/dictation/answer", dict_answer="あう")
    s, b = post("/dictation/next")
    check(st(b).get("dphase") == "end", f"本里 2 个，出完就结束：{st(b).get('dphase')}")
    s, b = post("/dictation/start", dict_direction="看中文写日语", dict_level="N3", dict_source="错词复习")
    check(s == 200 and st(b).get("dphase") == "empty" and "错词本是空的" in st(b).get("dempty", ""),
          f"N3 错词本空：dphase=empty，{st(b).get('dempty', '')[:20]}…")
    s, b = post("/dictation/random")
    check(st(b).get("dphase") == "ask" and b["form"]["dict_source"] == "随机", "随机练一轮：出词，题源回到随机")
    s, b = post("/dictation/load", source="review", direction="reading", level="全部")
    check(st(b).get("dphase") == "ask" and cur() == nichi_id and b["form"]["dict_source"] == "错词复习"
          and b["form"]["dict_direction"] == "看汉字写读音", "载入 source=review&direction=reading：练读音的错词")
    s, b = post("/dictation/wrong")
    check(st(b).get("dphase") == "ask" and cur() == nichi_id, "练错词：方向照这一轮的")

    # 会う、合う 在错词复习里各答对 1 次（还差 1 次），一日 读音错着：3 个词、本里 3 个
    s, b = post("/progress/page")
    d = (b.get("state") or {}).get("dictation") or {}
    check("练过 3 个词" in d.get("text", "") and "错词本 3 个" in d.get("text", "") and "source=review" in d.get("link", ""),
          f"进度页：{d.get('text')} {d.get('link')}")
    s, b = post("/progress/page", learner="other")
    d = (b.get("state") or {}).get("dictation") or {}
    check("练过 0 个词" in d.get("text", "") and "source=review" not in d.get("link", "x"),
          f"没练过：{d.get('text')} {d.get('link')}")

    print("五、不碰学习记录")
    for t in ("attempt", "mastery", "score"):
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        check(n == 0, f"{t} 没有行：{n}")
    old = Path(tempfile.mkdtemp(prefix="dictation_old_")) / "app.db"
    o = sqlite3.connect(old)
    o.execute("CREATE TABLE attempt (id INTEGER PRIMARY KEY, learner TEXT, point TEXT, correct INTEGER)")
    o.execute("INSERT INTO attempt(learner, point, correct) VALUES('me', 'noun', 1)")
    o.commit()
    made = ensure_new_tables(old, ws / "entities")
    check("word_attempt" in made and "dictation_state" in made and "attempt" not in made, f"补建：{made}")
    check(o.execute("SELECT count(*) FROM attempt").fetchone()[0] == 1, "已有表的数据还在")
    o.close()
    con.close()
    # 自己 mkdtemp 的两个目录自己清掉（/tmp 满过）
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(old.parent, ignore_errors=True)

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
