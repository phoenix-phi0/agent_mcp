# -*- coding: utf-8 -*-
"""掌握得分：score 表和 /score/* 三个接口，以及已有的库补建这张表。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_score.py

  一、记一次打分：一行，分值存成整数
  二、改分是再记一行，当前分取最新；同一秒打两次，取后一次
  三、范围：0 和 100 收，101、-1、4.5、abc、空格都拒，一行都不留
  四、知识点不存在：404，不留数据
  五、当前分：每个点一行、按人分开、能只看一个点、没打过的不出现
  六、历史：从早到晚全部给出
  七、不影响掌握和解锁：打 100 分，mastery 一行不多、可学列表不变
  八、学习者默认 me
  九、不截断：69 个点都打分、一个点打 120 次，全部拿得到
  十、补建表：已有的库里没有 score，补上；别的表一行不动；建出来的跟
      新建的库一模一样；再跑一次什么都不做

  按做题自动打分（queries/score_calc.sql、scripts/score_update.zs）：
  十一、答题后自动写入：/learn/answer 一次一行，分值跟参考实现一致
  十二、示例表：直接造作答序列（含进阶题、基础题），回填出的分逐个对上
  十三、分变了才记：同分不重复记行（全对 20 道之后分封顶，再对不加行）
  十四、方向：最近错题让分下降、连对让分上升；难度权重生效
  十五、回填 /score/rebuild：只补「有作答、没得分」的点，不改旧行；再调
        一次补 0 行；给 learner 只补这个人
  十六、不同学习者不串；得分和「已掌握」的对比（得分 ≥ 80 跟计数达标线
        哪里不一样）
"""

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


# 打分的参考实现（跟 scripts/score_update.zs 的默认参数一致），用来对答案。
# seq 从早到晚，每项 (对错, 难度)。
DECAY, WINDOW, PRIOR_RIGHT, PRIOR_WRONG, HARD_RIGHT, EASY_WRONG = 0.85, 20, 0.25, 1.25, 1.3, 1.3


def ref_score(seq):
    hit = tot = 0.0
    for k, (ok, diff) in enumerate(reversed(seq[-WINDOW:])):
        w = DECAY ** k
        if ok and diff == "进阶":
            w *= HARD_RIGHT
        if not ok and diff == "基础":
            w *= EASY_WRONG
        hit += w * ok
        tot += w
    x = 100 * (hit + PRIOR_RIGHT) / (tot + PRIOR_RIGHT + PRIOR_WRONG)
    return int(x + 0.5)       # SQLite 的 round：.5 远离 0（分数非负）


def seq_of(text):
    """'1' 基础对、'0' 基础错、'H' 进阶对、'h' 进阶错、'n' 不是题库的题（对），'x'（错）"""
    m = {"1": (1, "基础"), "0": (0, "基础"), "H": (1, "进阶"), "h": (0, "进阶"),
         "n": (1, None), "x": (0, None)}
    return [m[ch] for ch in text]


# 示例表：场景、作答序列（从早到晚）、该得的分
EXAMPLES = [
    ("1对", "1", 50),
    ("1错", "0", 9),
    ("3对", "111", 69),
    ("5对0错", "11111", 76),
    ("7对0错", "1111111", 79),
    ("8对0错", "11111111", 80),
    ("8对2错（错在最前）", "0011111111", 73),
    ("8对2错（错在中间）", "1111001111", 65),
    ("8对2错（错在最近）", "1111111100", 51),
    ("10题对6（对错交错）", "1010110110", 44),
    ("10题对6（前4错后6对）", "0000111111", 61),
    ("10题对6（前6对后4错）", "1111110000", 31),
    ("之前10对、最近3连错", "1111111111000", 44),
    ("12对", "1" * 12, 83),
    ("20对", "1" * 20, 84),
    ("30对（只看最近20次）", "1" * 30, 84),
    ("8对（全是进阶题）", "H" * 8, 84),
    ("1错（进阶题）", "h", 10),
    ("8对后错1道进阶", "11111111h", 66),
    ("8对后错1道基础", "111111110", 63),
    ("8对（不是题库的题，权重1）", "n" * 8, 80),
]


def rows_of(db, sql, *args):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="score_")))
    import_graph(ws)
    c = client(ws)
    db = ws / "app.db"

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def rows(sql, *args):
        return rows_of(db, sql, *args)

    def now(who="u1", point=""):
        st, body = post("/score/now", learner=who, point=point)
        return {r["code"]: r for r in (body.get("lists") or {}).get("scores", [])}

    def count():
        return rows("SELECT count(*) n FROM score")[0]["n"]

    cols = [r["name"] for r in rows("PRAGMA table_info(mastery)")]
    check("score" not in cols, f"mastery 回到原样，没有 score 列：{cols}")

    print("一、记一次打分")
    st, body = post("/score/add", learner="u1", point="hiragana", value="70")
    check(st == 200, f"打 70 分：{st} {body.get('error', '')}")
    r = rows("SELECT * FROM score")
    check(len(r) == 1 and r[0]["learner"] == "u1" and r[0]["point"] == "hiragana",
          f"记了一行：{r}")
    check(r and r[0]["value"] == 70 and isinstance(r[0]["value"], int),
          f"分值存成整数 70：{r[0]['value']!r}" if r else "分值存成整数")
    check(r and r[0]["at"], f"打分时间由库填了：{r[0]['at'] if r else None}")
    local = rows("SELECT datetime('now','localtime') t")[0]["t"]
    check(r and r[0]["at"][:13] == local[:13],
          f"是本地时间，跟列的默认值一致（不是 UTC）：{r[0]['at'] if r else None} / 现在 {local}")
    cur = (body.get("lists") or {}).get("scores") or []
    check(len(cur) == 1 and cur[0]["value"] == 70 and cur[0]["label"],
          f"返回这个点的当前分，带名称：{cur}")
    msgs = [m.get("text") for m in body.get("messages") or []]
    check(any("70" in (t or "") for t in msgs), f"有提示：{msgs}")

    print("二、改分")
    post("/score/add", learner="u1", point="hiragana", value="85")
    check(count() == 2, "改分是再记一行，旧的留着")
    n = now()
    check(n["hiragana"]["value"] == 85 and n["hiragana"]["times"] == 2,
          f"当前分取最新：{n['hiragana']['value']}，一共 {n['hiragana']['times']} 次")
    # 两次紧挨着打，几乎一定在同一秒里——at 一样，要靠 id 分先后
    post("/score/add", learner="u1", point="katakana", value="10")
    post("/score/add", learner="u1", point="katakana", value="90")
    ats = [x["at"] for x in rows("SELECT at FROM score WHERE point='katakana' ORDER BY id")]
    check(now()["katakana"]["value"] == 90,
          f"同一秒打两次，取后打的那次：{now()['katakana']['value']}（at {ats}）")

    print("三、范围")
    before = count()
    for ok in ("0", "100", "007"):
        st, body = post("/score/add", learner="r", point="hiragana", value=ok)
        check(st == 200, f"{ok!r} 收下：{st} {body.get('error', '')}")
    check([x["value"] for x in rows("SELECT value FROM score WHERE learner='r' ORDER BY id")]
          == [0, 100, 7], "存成 0、100、7")
    mid = count()
    for bad in ("101", "-1", "4.5", "abc", " 50", "50 ", "1e2", "0x10", "1000"):
        st, body = post("/score/add", learner="r", point="hiragana", value=bad)
        check(st == 400, f"{bad!r} 被拒：{st} {body.get('error', '')}")
    st, body = post("/score/add", learner="r", point="hiragana")
    check(st == 400 and "缺分数" in (body.get("error") or ""), f"不给分数：{st} {body.get('error')}")
    check(count() == mid, f"被拒的一行都没留下（{count() - mid} 行）")
    check(mid - before == 3, "对照：合法的三次都写进去了")

    print("四、知识点不存在")
    before = count()
    st, body = post("/score/add", learner="u1", point="no-such", value="50")
    check(st == 404 and "没有这个知识点" in (body.get("error") or ""), f"{st} {body.get('error')}")
    st, body = post("/score/add", learner="u1", value="50")
    check(st == 404, f"不给 point：{st}")
    check(count() == before, "不留数据")

    print("五、当前分")
    post("/score/add", learner="u2", point="hiragana", value="30")
    check(now("u1")["hiragana"]["value"] == 85 and now("u2")["hiragana"]["value"] == 30,
          "按人分开：u1 是 85、u2 是 30")
    only = now("u1", "katakana")
    check(list(only) == ["katakana"], f"给 point 只看那一个：{list(only)}")
    check("dakuon" not in now("u1"), "没打过分的点不出现（不是 0 分）")
    check(set(now("u1")) == {"hiragana", "katakana"}, f"u1 打过的两个点：{sorted(now('u1'))}")
    check(now("nobody") == {}, "没打过分的人：空")

    print("六、历史")
    st, body = post("/score/history", learner="u1", point="hiragana")
    hist = [h["value"] for h in (body.get("lists") or {}).get("history", [])]
    check(hist == [70, 85], f"从早到晚：{hist}")
    st, body = post("/score/history", learner="u1", point="katakana")
    hist = [h["value"] for h in (body.get("lists") or {}).get("history", [])]
    check(hist == [10, 90], f"同一秒的两次也按先后：{hist}")
    st, body = post("/score/history", learner="u1")
    check(st == 400, f"不给 point：{st} {body.get('error')}")

    print("七、不影响掌握和解锁")
    st, body = post("/learn/next", learner="u7")
    nxt_before = [x["code"] for x in (body.get("lists") or {}).get("next", [])]
    post("/score/add", learner="u7", point="hiragana", value="100")
    check(not rows("SELECT 1 FROM mastery WHERE learner='u7'"), "打 100 分，mastery 一行不多")
    st, body = post("/learn/next", learner="u7")
    nxt_after = [x["code"] for x in (body.get("lists") or {}).get("next", [])]
    check(nxt_after == nxt_before, f"可学列表不变：{nxt_after}")

    print("八、学习者默认 me")
    st, body = post("/score/add", point="hiragana", value="60")
    check(st == 200 and rows("SELECT learner FROM score ORDER BY id DESC LIMIT 1")[0]["learner"] == "me",
          "不传 learner 记在 me 名下")
    st, body = post("/score/now")
    got = {r["code"]: r["value"] for r in (body.get("lists") or {}).get("scores", [])}
    check(got == {"hiragana": 60}, f"不传 learner 查的也是 me：{got}")
    st, body = post("/score/history", point="hiragana")
    check([h["value"] for h in (body.get("lists") or {}).get("history", [])] == [60],
          "历史也是 me 的")
    st, body = post("/score/add", learner="", point="hiragana", value="65")
    check(rows("SELECT learner FROM score ORDER BY id DESC LIMIT 1")[0]["learner"] == "me",
          "learner 传空串也当成 me")

    print("九、不截断")
    codes = [r["code"] for r in rows("SELECT code FROM node")]
    for code in codes:
        post("/score/add", learner="big", point=code, value="50")
    check(len(now("big")) == len(codes), f"{len(codes)} 个点都打分，当前分 {len(now('big'))} 条")
    for i in range(120):
        post("/score/add", learner="many", point="hiragana", value=str(i % 101))
    st, body = post("/score/history", learner="many", point="hiragana")
    hist = (body.get("lists") or {}).get("history", [])
    check(len(hist) == 120, f"一个点打 120 次，历史 {len(hist)} 条")
    check(now("many")["hiragana"]["value"] == 119 % 101, "当前分是最后一次")

    print("十、补建表")
    from kg.__main__ import ensure_new_tables
    old = Path(tempfile.mkdtemp(prefix="newtab_")) / "app.db"
    shutil.copy(db, old)
    con = sqlite3.connect(old)
    con.execute("DROP TABLE score")          # 加 score 实体之前建的库就是这样
    con.execute("INSERT INTO mastery(learner, point, right, total, mastered)"
                " VALUES ('keep', 'hiragana', 3, 4, 0)")
    con.commit()
    con.close()

    def schema(p):
        return {r["name"]: r["sql"] for r in rows_of(
            p, "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")}

    def counts(p):
        return {t: rows_of(p, f"SELECT count(*) n FROM {t}")[0]["n"]
                for t in ("node", "item", "prereq", "contrast", "word", "attempt", "mastery")}

    s0, n0 = schema(old), counts(old)
    made = ensure_new_tables(old, ws / "entities")
    check(made == ["score"], f"补建了：{made}")
    s1 = schema(old)
    check(all(s1.get(k) == v for k, v in s0.items()), "已有的表和索引，建表语句一个字没变")
    check(counts(old) == n0, f"已有的表一行没动：{n0}")
    check(rows_of(old, "SELECT right, total FROM mastery WHERE learner='keep'")
          == [{"right": 3, "total": 4}], "学习记录原样在")
    fresh = schema(db)
    new_parts = {k: v for k, v in s1.items() if k not in s0}
    check(new_parts == {k: v for k, v in fresh.items()
                        if k == "score" or k.startswith("idx_score_")},
          f"补建的表和索引跟新建的库一模一样：{sorted(new_parts)}")
    check(ensure_new_tables(old, ws / "entities") == [], "再跑一次什么都不做")
    con = sqlite3.connect(old)
    con.execute("INSERT INTO score(learner, point, value, at)"
                " VALUES ('x', 'hiragana', 50, datetime('now','localtime'))")
    con.commit()
    con.close()
    check(rows_of(old, "SELECT value FROM score") == [{"value": 50}], "补建的表能用")
    missing = Path(tempfile.mkdtemp(prefix="newtab_")) / "none.db"
    check(ensure_new_tables(missing, ws / "entities") == [] and not missing.exists(),
          "库不存在时不建库、不报错")

    auto_scoring(ws, c, db)

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0



def auto_scoring(ws, c, db):
    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def rows(sql, *args):
        return rows_of(db, sql, *args)

    def hist(who, point="hiragana"):
        return [r["value"] for r in rows(
            "SELECT value FROM score WHERE learner = ? AND point = ? ORDER BY id", who, point)]

    # 造两道题：一道基础、一道进阶（问题表是内容表，直接插）
    item = rows("SELECT code FROM item LIMIT 1")[0]["code"]
    con = sqlite3.connect(db)
    for code, diff in (("tq-basic", "基础"), ("tq-hard", "进阶")):
        con.execute("INSERT INTO question(code, course, level, kind, difficulty, qtype, stem, answer, item)"
                    " VALUES (?, 't', 'N5', '挖空', ?, '选择', 's', 'A', ?)", (code, diff, item))
    con.commit()
    con.close()

    def put(who, text, point="hiragana"):
        """直接往流水里写一串作答（从早到晚），不走接口——模拟自动打分上线前的老记录"""
        con = sqlite3.connect(db)
        for ok, diff in seq_of(text):
            q = {"基础": "tq-basic", "进阶": "tq-hard", None: None}[diff]
            con.execute("INSERT INTO attempt(learner, point, item, correct) VALUES (?, ?, ?, ?)",
                        (who, point, q, ok))
        con.commit()
        con.close()

    print("十一、答题后自动写入")
    seq = ""
    for ok in (1, 1, 0, 1):
        before = len(hist("auto"))
        st, body = post("/learn/answer", learner="auto", point="hiragana", correct=str(ok))
        seq += "n" if ok else "x"
        want = ref_score(seq_of(seq))
        check(st == 200 and hist("auto")[-1:] == [want] and len(hist("auto")) == before + 1,
              f"答 {seq}：记了一行 {hist('auto')[-1:]}（参考 {want}），接口回 score={body.get('score')}")
    check(hist("auto") == [50, 63, 45, 55], f"四次的分：{hist('auto')}")
    check(rows("SELECT at FROM score WHERE learner='auto' ORDER BY id DESC LIMIT 1")[0]["at"],
          "打分时间由库填了")

    print("十二、示例表")
    for i, (name, text, want) in enumerate(EXAMPLES):
        put(f"ex{i}", text)
    st, body = post("/score/rebuild")
    check(st == 200 and body.get("added") == str(len(EXAMPLES)),
          f"回填补了 {body.get('added')} 行（{len(EXAMPLES)} 个场景各一行）")
    for i, (name, text, want) in enumerate(EXAMPLES):
        got = hist(f"ex{i}")
        check(got == [want] and ref_score(seq_of(text)) == want,
              f"{name}（{text}）：{got}，该是 {want}（参考实现 {ref_score(seq_of(text))}）")
    check(hist("ex0")[0] < 100, "答对 1 题不是 100")
    check(hist("ex5")[0] >= 80 and hist("ex4")[0] < 80,
          "全对 8 题到 80，7 题还不到——跟「≥8 题」的达标线对得上")

    print("十三、分变了才记")
    for _ in range(25):
        post("/learn/answer", learner="flat", point="hiragana", correct="1")
    h = hist("flat")
    n20 = rows("SELECT count(*) n FROM score WHERE learner='flat'")[0]["n"]
    check(h[-1] == 84 and len(h) < 25, f"连对 25 道：分封顶 84，只记了 {len(h)} 行：{h}")
    check(len(set(h)) == len(h), f"相邻没有同分的行：{h}")
    last = rows("SELECT id FROM score WHERE learner='flat' ORDER BY id DESC LIMIT 1")[0]["id"]
    post("/learn/answer", learner="flat", point="hiragana", correct="1")
    check(rows("SELECT count(*) n FROM score WHERE learner='flat'")[0]["n"] == n20
          and rows("SELECT max(id) m FROM score WHERE learner='flat'")[0]["m"] == last,
          "再对一道，分还是 84：不加行")
    post("/learn/answer", learner="flat", point="hiragana", correct="0")
    check(len(hist("flat")) == n20 + 1 and hist("flat")[-1] < 84,
          f"对照：错一道，分变了就记：{hist('flat')[-2:]}")

    print("十四、方向和难度")
    h = []
    for ok in "11111000":
        post("/learn/answer", learner="dir", point="hiragana", correct=ok)
        h.append(hist("dir")[-1])
    check(all(a < b for a, b in zip(h[:5], h[1:5])), f"连对：分一路上升 {h[:5]}")
    check(all(a > b for a, b in zip(h[4:], h[5:])), f"最近错题：分一路下降 {h[4:]}")
    put("easy8", "1" * 8)
    put("hard8", "H" * 8)
    put("easyx", "11111111" + "0")
    put("hardx", "11111111" + "h")
    post("/score/rebuild")
    check(hist("hard8")[0] > hist("easy8")[0], f"进阶题答对加权：全对 8 道进阶 {hist('hard8')} > 基础 {hist('easy8')}")
    check(hist("easyx")[0] < hist("hardx")[0], f"基础题答错多罚：错基础 {hist('easyx')} < 错进阶 {hist('hardx')}")

    print("十五、回填只补缺")
    # 老人 old1：两个点有作答；其中一个已经有手工记的分
    put("old1", "111", "hiragana")
    put("old1", "000", "katakana")
    post("/score/add", learner="old1", point="hiragana", value="33")
    put("old2", "1", "hiragana")
    before = rows("SELECT id, learner, point, value, at FROM score ORDER BY id")
    st, body = post("/score/rebuild", learner="old1")
    check(st == 200 and body.get("added") == "1", f"给 learner：只补 old1 缺的那个点，补了 {body.get('added')} 行")
    check(hist("old1") == [33], f"已有得分的点不碰：{hist('old1')}（作答算出来是 69）")
    check(hist("old1", "katakana") == [ref_score(seq_of("000"))], f"没得分的点补上：{hist('old1', 'katakana')}")
    check(hist("old2") == [], "别人的不补（给了 learner）")
    after = rows("SELECT id, learner, point, value, at FROM score ORDER BY id")
    check(after[:len(before)] == before, "旧行一行没改")
    st, body = post("/score/rebuild")
    check(body.get("added") == "1" and hist("old2") == [50], f"不给 learner：补所有人（old2 {hist('old2')}）")
    st, body = post("/score/rebuild")
    check(st == 200 and body.get("added") == "0", f"再调一次：补 {body.get('added')} 行")
    nobody = rows("SELECT count(*) n FROM attempt a WHERE NOT EXISTS (SELECT 1 FROM score s"
                  " WHERE s.learner = a.learner AND s.point = a.point)")[0]["n"]
    check(nobody == 0, "回填之后：每个有作答的点都有得分")

    print("十六、不同学习者不串；跟「已掌握」比")
    post("/learn/answer", learner="ua", point="dakuon", correct="1")
    post("/learn/answer", learner="ua", point="dakuon", correct="1")
    post("/learn/answer", learner="ub", point="dakuon", correct="0")
    check(hist("ua", "dakuon") == [50, 63] and hist("ub", "dakuon") == [10],
          f"同一个点：ua {hist('ua', 'dakuon')}，ub {hist('ub', 'dakuon')}——各算各的")
    # 得分 ≥ 80 和计数达标线（≥ 8 题、正确率 ≥ 80%）不一样的地方
    cases = [("8对2错（错在最近）", "1111111100"), ("之前12对、最近3连错", "1" * 12 + "000"),
             ("8对0错", "11111111"), ("5对0错", "11111"), ("8对（全是进阶题）", "H" * 8),
             ("早先6错、最近20连对", "0" * 6 + "1" * 20)]
    for i, (name, text) in enumerate(cases):
        put(f"cmp{i}", text)
    post("/score/rebuild")
    diff = []
    for i, (name, text) in enumerate(cases):
        r, t = text.count("1") + text.count("H"), len(text)
        by_count = t >= 8 and r * 100 // t >= 80
        by_score = hist(f"cmp{i}")[0] >= 80
        print(f"     {name}：{r}/{t}，计数达标线 {'掌握' if by_count else '没掌握'}，"
              f"得分 {hist(f'cmp{i}')[0]} {'≥' if by_score else '<'} 80")
        diff.append((by_count, by_score))
    check(diff[0] == (True, False) and diff[1] == (True, False),
          "最近错了的：计数线算掌握，得分不到 80")
    check(diff[2] == (True, True) and diff[3] == (False, False) and diff[4] == (True, True),
          "全对 8 道两边都算掌握，5 道两边都不算")
    check(diff[5] == (False, True), "早先错得多、最近一直对：计数线（累计正确率 76%）不算，得分算")
    check(not rows("SELECT 1 FROM mastery WHERE learner LIKE 'cmp%'"),
          "得分不碰 mastery（直接造的流水没有汇总，回填也没加）")


if __name__ == "__main__":
    sys.exit(main())
