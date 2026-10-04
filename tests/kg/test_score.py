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

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
