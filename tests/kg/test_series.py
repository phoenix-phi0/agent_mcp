# -*- coding: utf-8 -*-
"""教材系列：series / learner_pref / lesson_point，按系列导入、按系列过滤。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_series.py

新教材的课只映射到已有的知识点（item_lesson / lesson_point），不新建知识点。
这里用 content/series/_example（2 课，格式示例）在临时库里当「第二套教材」。

  一、老库：迁移只加补上 lesson.series（默认 hanabira）、lesson.seq 和三张新表，
      老课一行不少、全是 hanabira
  二、种子：导入后 series 表里有 hanabira（名称、来源、许可）
  三、_example 导入：报告的课数、映射到条目 / 知识点数；故意引用不存在的条目、
      知识点的一行整行拒收、进报告，绝不新建 item / node；系列编号不合规、
      没有文件的系列报错
  四、按系列清空：重导 _example 不动 hanabira，重导 hanabira 不动 _example；
      学习记录一行不动
  五、教材页：系列下拉只列 sort ≥ 0 的；切换写偏好、列表只列当前系列；
      伪造的系列不认（对照：合法的能切）；抬头「第{seq}课」/「N5 第46课」
  六、lesson_ref / lesson_find：「第N课」只在当前系列认（有 seq 按 seq）；
      找课先当前系列，找不到全库兜底并标系列名；课号哪个系列的都认
  七、按课练：新系列的课用映射的条目、知识点出题；映射的点下没题时友好提示；
      hanabira 的课照旧只出本课打了标的题
  八、老师：知道当前系列（提示词里有），「讲讲第2课」讲当前系列的第2课，
      链接带正确课号；兜底到别的系列时链接文字标系列名
  九、hanabira 回归：教材列表、读课、请老师讲解、按课练跟加系列之前一样
"""

import json
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws     # noqa: E402
from kg.__main__ import BANK, read_bank                        # noqa: E402
from tools.mock import MockClient                              # noqa: E402

passed = failed = 0
EXAMPLE = ROOT / "kg" / "content" / "series" / "_example"


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


def write_jsonl(p: Path, rows: list):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def intent(kind="讲解", keywords=(), level=""):
    return json.dumps({"intent": kind, "keywords": list(keywords), "level": level,
                       "kind": "", "grade": "否"}, ensure_ascii=False)


INTENTS = {
    "讲讲第2课": intent(),
    "讲讲第46课": intent(),
    "讲讲N5第46课": intent(level="N5"),
    "ようだ怎么用": intent(keywords=["ようだ"]),
    "てから怎么用": intent(keywords=["てから"]),
    "教材里有什么": intent("教材"),
}


def handler(prompt, system):
    if "意图分类器" in (system or ""):
        said = prompt.split("学习者的消息：")[-1].strip()
        return INTENTS.get(said, intent())
    return "老师的回答"


def test_migrate():
    print("一、老库补列补表")
    from tools.entity import render_sql
    from tools.migrate import migrate_additive
    ents = ROOT / "kg" / "entities"
    text = "\n\n".join(f.read_text(encoding="utf-8") for f in sorted(ents.glob("*.entity"))
                       if f.name != "series.entity")
    # 加系列之前的样子：lesson 没有 series / seq，没有 lesson_point
    old = text.replace("  字段 series 文本 必填 默认 hanabira 索引 系列\n", "") \
              .replace("  字段 seq 整数 课序\n", "")
    old = re.sub(r"实体 lesson_point .*?结束\n", "", old, flags=re.S)
    check("series" not in re.search(r"实体 lesson 课文.*?结束", old, re.S).group(0)
          and "实体 lesson_point" not in old, "对照：拼出来的老实体里 lesson 没有 series，也没有 lesson_point")
    tmp = Path(tempfile.mkdtemp(prefix="series_mig_"))
    db = tmp / "app.db"
    con = sqlite3.connect(db)
    con.executescript(render_sql(old, strict=True))
    con.execute("INSERT INTO lesson(code, level, title, summary, explanation) "
                "VALUES ('hb-n5-046', 'N5', 't', 's', 'e')")
    con.execute("INSERT INTO node(code, label) VALUES ('tai', 'たい')")
    con.execute("INSERT INTO attempt(learner, point, item, correct) VALUES ('k', 'tai', 'q1', 1)")
    con.commit()
    con.close()
    cols = {r["name"] for r in rows_of(db, "PRAGMA table_info(lesson)")}
    check("series" not in cols and "seq" not in cols, f"老库没有 series / seq：{sorted(cols)}")
    r = migrate_additive(db, ents)
    check({"lesson.series", "lesson.seq"} <= set(r["columns"]), f"补了列：{r['columns']}")
    check({"series", "learner_pref", "lesson_point"} <= set(r["tables"]), f"补了表：{r['tables']}")
    got = rows_of(db, "SELECT code, series, seq FROM lesson")
    check(got == [{"code": "hb-n5-046", "series": "hanabira", "seq": None}],
          f"老课一行不少，series 默认 hanabira、seq 空：{got}")
    info = {r["name"]: r for r in rows_of(db, "PRAGMA table_info(lesson)")}
    check(info["series"]["notnull"] == 1 and info["series"]["dflt_value"] == "'hanabira'",
          f"series 非空、默认 'hanabira'：{info['series']}")
    check(rows_of(db, "SELECT count(*) n FROM attempt")[0]["n"] == 1, "学习记录原样")
    r2 = migrate_additive(db, ents)
    check(not r2["columns"] and not r2["tables"], "再跑一次什么都不补（幂等）")


def main():
    test_migrate()

    ws = make_ws(Path(tempfile.mkdtemp(prefix="series_")))
    import_graph(ws)
    db = ws / "app.db"
    from gen.project import make_app
    app, router = make_app(ws, real=False)
    mock = MockClient(handler=handler, offline=True)
    router.client_factory = lambda: mock
    c = app.test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def rows(sql, *args):
        return rows_of(db, sql, *args)

    def n(sql, *args):
        return rows(sql, *args)[0]["n"]

    print("二、种子")
    st, rep = post("/lesson/import")
    check(st == 200 and rep.get("series") == "hanabira" and rep.get("lessons") == "125",
          f"不给 series 就是 hanabira，125 课：{st} {rep.get('series')} {rep.get('lessons')}")
    s = rows("SELECT * FROM series")
    check(s == [{"code": "hanabira", "label": "hanabira 语法",
                 "description": s[0]["description"] if s else None,
                 "source": "hanabira.org", "license": "CC BY 4.0", "sort": 0}],
          f"series 表里是 hanabira：{s}")
    check(n("SELECT count(*) n FROM lesson WHERE series = 'hanabira'") == 125, "现有 125 课都是 hanabira")
    r = c.post("/quiz/import", json={"form": {"rows": read_bank(BANK)}})
    assert r.status_code == 200, r.get_json()

    # 学习记录先放几行，最后看导入有没有碰它们
    con = sqlite3.connect(db)
    con.execute("INSERT INTO attempt(learner, point, item, correct) VALUES ('k','tai','q1',1)")
    con.execute("INSERT INTO mastery(learner, point, right, total, mastered) VALUES ('k','tai',1,1,0)")
    con.execute("INSERT INTO score(learner, point, value) VALUES ('k','hiragana',40)")
    con.commit()
    con.close()
    keep = {t: rows(f"SELECT * FROM {t}") for t in ("attempt", "mastery", "score")}

    def hb_rows():
        return {"lesson": rows("SELECT * FROM lesson WHERE series = 'hanabira' ORDER BY code"),
                "item_lesson": rows("SELECT * FROM item_lesson WHERE lesson IN "
                                    "(SELECT code FROM lesson WHERE series = 'hanabira') ORDER BY id")}
    hb_before = hb_rows()

    # hanabira 回归的基准：加 _example 之前的列表、读课、按课练
    st, base_list = post("/lesson/list")
    st, base_one = post("/lesson/one", lesson="hb-n4-118")

    print("三、_example 导入")
    ex = read_jsonl(EXAMPLE / "lessons.jsonl")
    check(len(ex) == 2 and all(d["series"] == "_example" for d in ex), "示例文件 2 课，series 都是 _example")
    # make_ws 拷了整个 content/，示例已经在了；照样拷一遍，不依赖这一点
    shutil.copytree(EXAMPLE, ws / "content" / "series" / "_example", dirs_exist_ok=True)
    # 测试库里给 _example 一行系列（sort 1，进下拉）；正式的 series.jsonl 里没有它
    seeds = read_jsonl(ws / "content" / "series.jsonl")
    check([d["code"] for d in seeds] == ["hanabira"], "正式的种子里只有 hanabira，没有 _example")
    write_jsonl(ws / "content" / "series.jsonl",
                seeds + [{"code": "_example", "label": "示例教材", "sort": 1},
                         {"code": "hidden", "label": "藏起来的", "sort": -1}])
    bad = dict(ex[0], code="_example-009", seq=9, items=["te-kara", "no-such-item"],
               points=["no-such-node"])
    wrong_series = dict(ex[0], code="_example-010", seq=10, series="hanabira")
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", ex + [bad, wrong_series])
    items_n = n("SELECT count(*) n FROM item")
    nodes_n = n("SELECT count(*) n FROM node")
    st, rep = post("/lesson/import", series="_example")
    check(st == 200, f"导入 _example：{st} {rep.get('error', '')}")
    check(rep.get("lessons") == "2" and rep.get("links") == "1" and rep.get("points") == "1",
          f"报告：2 课，映射到条目 1、知识点 1：{rep.get('lessons')} / {rep.get('links')} / {rep.get('points')}")
    rj = rep.get("rejected_rows") or []
    check(rep.get("rejected") == "2" and [x["row"] for x in rj] == [3, 4],
          f"拒收 2 行（第 3、4 行）：{rep.get('rejected')} {[x.get('row') for x in rj]}")
    check(rj and rj[0]["code"] == "_example-009" and "no-such-item" in rj[0]["reason"]
          and "no-such-node" in rj[0]["reason"] and "te-kara" not in rj[0]["reason"],
          f"拒收理由点名不存在的条目和知识点（存在的 te-kara 不算）：{rj[:1]}")
    check(len(rj) > 1 and "series" in rj[1]["reason"], f"series 跟正在导入的不一致也拒收：{rj[1:]}")
    check(n("SELECT count(*) n FROM lesson WHERE code IN ('_example-009', '_example-010')") == 0
          and n("SELECT count(*) n FROM item_lesson WHERE lesson = '_example-009'") == 0,
          "拒收的整行不进库：课没有、它引用的存在的条目（te-kara）也没挂")
    check(n("SELECT count(*) n FROM item") == items_n and n("SELECT count(*) n FROM node") == nodes_n
          and not rows("SELECT 1 FROM item WHERE code = 'no-such-item'")
          and not rows("SELECT 1 FROM node WHERE code = 'no-such-node'"),
          "绝不新建条目、知识点")
    got = rows("SELECT code, series, seq FROM lesson WHERE series = '_example' ORDER BY code")
    check(got == [{"code": "_example-001", "series": "_example", "seq": 1},
                  {"code": "_example-002", "series": "_example", "seq": 2}], f"进库的两课：{got}")
    check(rows("SELECT item, rank FROM item_lesson WHERE lesson = '_example-001'") == [{"item": "te-kara", "rank": 1}]
          and rows("SELECT point FROM lesson_point WHERE lesson = '_example-002'") == [{"point": "f-desire"}],
          "映射：001 → 条目 te-kara，002 → 知识点 f-desire")
    check("第3行" in (rep.get("note") or "") and rep.get("orphans") == "0", f"note 里也写着：{rep.get('note')}")
    st, body = post("/lesson/import", series="../etc")
    check(st == 400, f"系列编号带 ../：400 {body.get('error')}")
    st, body = post("/lesson/import", series="nope")
    check(st == 404 and "content/series/nope/lessons.jsonl" in (body.get("error") or ""),
          f"没有文件的系列：404 {body.get('error')}")

    print("四、按系列清空")
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", ex)
    st, rep = post("/lesson/import", series="_example")
    check(st == 200 and rep.get("rejected") == "0" and rep.get("lessons") == "2", "修好文件重导：2 课、没有拒收")
    check(hb_rows() == hb_before and n("SELECT count(*) n FROM lesson WHERE series = 'hanabira'") == 125,
          "重导 _example：hanabira 的课和挂接一行不动")
    one = dict(ex[0])
    one.pop("points")
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", [one])
    post("/lesson/import", series="_example")
    check(n("SELECT count(*) n FROM lesson WHERE series = '_example'") == 1
          and n("SELECT count(*) n FROM lesson_point") == 0
          and n("SELECT count(*) n FROM lesson WHERE series = 'hanabira'") == 125,
          "_example 只剩 1 课：它的课、lesson_point 跟着少，hanabira 照旧 125")
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", ex)
    post("/lesson/import", series="_example")
    st, rep = post("/lesson/import")
    check(st == 200 and n("SELECT count(*) n FROM lesson WHERE series = '_example'") == 2
          and n("SELECT count(*) n FROM lesson_point") == 1
          and n("SELECT count(*) n FROM item_lesson WHERE lesson LIKE '\\_example%' ESCAPE '\\'") == 1,
          "重导 hanabira：_example 的课和映射一行不动")
    check({t: rows(f"SELECT * FROM {t}") for t in keep} == keep, "导入好几轮，attempt / mastery / score 原样")
    dup = dict(ex[0], code="hb-n5-046")
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", ex + [dup])
    st, body = post("/lesson/import", series="_example")
    check(st >= 400 and n("SELECT count(*) n FROM lesson WHERE series = '_example'") == 2
          and rows("SELECT series FROM lesson WHERE code = 'hb-n5-046'") == [{"series": "hanabira"}],
          f"撞了 hanabira 的课号：整个回滚，两边都原样：{st}")
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", ex)

    print("五、教材页")
    st, body = post("/lesson/list")
    opts = (body.get("lists") or {}).get("series_options")
    check(opts == [{"value": "hanabira", "label": "hanabira 语法"}, {"value": "_example", "label": "示例教材"}],
          f"下拉只列 sort ≥ 0 的，按 sort 排（hidden 不在）：{opts}")
    ls = (body.get("lists") or {}).get("lessons") or []
    check(len(ls) == 125 and all(x["code"].startswith("hb-") for x in ls)
          and (body.get("state") or {}).get("series_head") == "hanabira 语法"
          and (body.get("form") or {}).get("series") == "hanabira",
          f"没选过：hanabira 的 125 课，顶栏写着系列名：{len(ls)} {(body.get('state') or {}).get('series_head')}")
    check(not rows("SELECT * FROM learner_pref"), "只看列表不写偏好")
    st, body = post("/lesson/list", series="hidden")
    check(not rows("SELECT * FROM learner_pref") and (body.get("form") or {}).get("series") == "hanabira",
          "sort < 0 的系列不认，偏好不写")
    st, body = post("/lesson/list", series="no-such")
    check(not rows("SELECT * FROM learner_pref"), "伪造的系列编号不认")
    st, body = post("/lesson/list", series="_example")
    ls = (body.get("lists") or {}).get("lessons") or []
    check([x["code"] for x in ls] == ["_example-001", "_example-002"],
          f"对照：切到 _example，列表只剩这个系列的课：{[x['code'] for x in ls]}")
    check(rows("SELECT learner, series FROM learner_pref") == [{"learner": "me", "series": "_example"}],
          "切换写进偏好（learner me）")
    check((body.get("state") or {}).get("series_head") == "示例教材"
          and (body.get("state") or {}).get("lesson_count") == "共2课"
          and (body.get("form") or {}).get("series") == "_example", "顶栏系列名、课数、表单跟着变")
    check([x["qcount"] for x in ls][0] > 0 and [x["qcount"] for x in ls][1] > 0,
          f"新系列的课题数按映射算：{[x['qcount'] for x in ls]}")
    st, body = post("/lesson/list")
    check(len((body.get("lists") or {}).get("lessons") or []) == 2, "之后不带 series 进页面：还是 _example（按偏好）")
    st, body = post("/lesson/list", series="_example", learner="other")
    st, body = post("/lesson/list", learner="third")
    check(len((body.get("lists") or {}).get("lessons") or []) == 125, "偏好按学习者存：别人没选过还是 hanabira")
    st, body = post("/lesson/one", lesson="_example-002")
    rd = (body.get("state") or {}).get("reading") or {}
    check(rd.get("head") == "《示例：想做某事》　N5　第2课（_example-002）" and rd.get("series_label") == "示例教材",
          f"有 seq：抬头「第2课」、带系列名：{rd.get('head')} {rd.get('series_label')}")
    items = (body.get("lists") or {}).get("lesson_items") or []
    check(items and items[0]["code"] == "f-desire", f"直接挂的知识点列在条目表里：{items}")
    check(len((body.get("lists") or {}).get("lessons") or []) == 2, "读课顺带的课文表是当前系列的")
    st, body = post("/lesson/one", lesson="hb-n5-046")
    rd = (body.get("state") or {}).get("reading") or {}
    check(rd.get("head") == "《动词 て います》　N5　第46课（hb-n5-046）" and rd.get("series_label") == "hanabira 语法",
          f"没有 seq（hanabira）：照旧「N5 第46课」，别的系列的课照样能读：{rd.get('head')}")

    print("六、lesson_ref / lesson_find")

    def ref(msg, learner="me", level=""):
        return _q("lesson_ref", message=msg, learner=learner, level=level)[0]

    def _q(name, **args):
        sql = (ws / "queries" / f"{name}.sql").read_text(encoding="utf-8")
        names = set(re.findall(r"(?<![:\w]):([^\W\d]\w*)", sql))
        return rows_of_named(db, sql, {k: str(args.get(k, "")) for k in names})

    def find(msg, keywords=(), learner="me", quiz=0, pin=""):
        return _q("lesson_find", message=msg, keywords=json.dumps(list(keywords), ensure_ascii=False),
                  learner=learner, quiz=quiz, pin=pin, level="")

    r = ref("讲讲第2课")
    check(r["code"] == "_example-002" and r["asked"] == 1, f"当前 _example：「第2课」按课序认：{r}")
    r = ref("讲讲第46课")
    check(r["code"] == "" and r["asked"] == 1, f"当前 _example：「第46课」不去 hanabira 里认：{r}")
    r = ref("讲讲N5第46课", learner="third", level="N5")
    check(r["code"] == "hb-n5-046", f"对照：hanabira 的人「N5 第46课」照旧认：{r['code']}")
    r = ref("讲讲N5第46课", level="N5")
    check(r["code"] == "", f"当前 _example：提到等级也不去 hanabira 里按课号末尾认：{r}")
    r = ref("讲讲第2课", learner="third")
    check(r["code"] == "" , f"hanabira 的人「第2课」不认到 _example 的课序上：{r}")
    r = ref("讲一下 hb-n4-118")
    check(r["code"] == "hb-n4-118" and r["asked"] == 1, f"课号哪个系列的都认：{r['code']}")
    r = ref("讲一下 _example-001", learner="third")
    check(r["code"] == "_example-001" and r["asked"] == 1, f"新系列的课号也认（不写死 hb-）：{r['code']}")
    r = ref("hb-n9-999 是什么")
    check(r["code"] == "" and r["asked"] == 1, f"课号样子但没有这一课：asked=1、认不出：{r}")
    r = ref("今天天气不错")
    check(r["asked"] == 0, "对照：没指名课 asked=0")
    f = find("てから怎么用", ["てから"])
    check(f and f[0]["code"] == "_example-001" and f[0]["other"] == 0 and f[0]["tag"] == "",
          f"当前 _example：先找当前系列：{[(x['code'], x['tag']) for x in f]}")
    f = find("てから怎么用", ["てから"], learner="third")
    check(f and f[0]["code"].startswith("hb-") and all(x["series"] == "hanabira" for x in f),
          f"对照：hanabira 的人找到 hanabira 的课：{[x['code'] for x in f]}")
    f = find("ようだ怎么用", ["ようだ"])
    check(f and f[0]["code"] == "hb-n4-118" and f[0]["other"] == 1 and f[0]["tag"] == "（hanabira 语法）",
          f"当前系列找不到：全库兜底，标系列名：{[(x['code'], x['tag']) for x in f]}")
    f = find("てから怎么用", ["てから"], pin="hb-n5-047")
    check(f and f[0]["code"] == "hb-n5-047", f"pin 的课不管哪个系列都排第一：{[x['code'] for x in f]}")

    print("七、按课练")
    te_kara_q = {r["code"] for r in rows("SELECT code FROM question WHERE item = 'te-kara'")}
    desire_q = {r["code"] for r in rows("SELECT q.code FROM question q JOIN item i ON i.code = q.item "
                                        "WHERE i.point = 'f-desire'")}
    check(te_kara_q and desire_q, f"题库里 te-kara、f-desire 下有题：{len(te_kara_q)} / {len(desire_q)}")
    st, body = post("/quiz/lesson", lesson="_example-001")
    card = (body.get("state") or {}).get("card") or {}
    check(st == 200 and card.get("code") in te_kara_q, f"_example-001（映射 te-kara）出的是 te-kara 的题：{card.get('code')}")
    st, body = post("/quiz/lesson", lesson="_example-002")
    card = (body.get("state") or {}).get("card") or {}
    check(st == 200 and card.get("code") in desire_q,
          f"_example-002（直接挂 f-desire）出的是这个知识点下条目的题：{card.get('code')}")
    st, body = post("/lesson/one", lesson="_example-002")
    rd = (body.get("state") or {}).get("reading") or {}
    check(rd.get("qcount") == len(desire_q) and unquote(rd.get("practice", "")) == "#做题?lesson=_example-002",
          f"读课的题数、「练这一课」按映射：{rd.get('qcount')} {unquote(rd.get('practice', ''))}")
    noq = rows("SELECT code FROM node WHERE code NOT IN (SELECT i.point FROM item i JOIN question q ON q.item = i.code) LIMIT 1")[0]["code"]
    nq = dict(ex[1], code="_example-003", seq=3, points=[noq])
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", ex + [nq])
    post("/lesson/import", series="_example")
    st, body = post("/quiz/lesson", lesson="_example-003")
    check(st == 404 and "映射的知识点下还没有题" in (body.get("error") or ""),
          f"映射的点（{noq}）下没题：友好提示：{st} {body.get('error')}")
    st, body = post("/quiz/lesson", lesson="hb-n4-118")
    card = (body.get("state") or {}).get("card") or {}
    mine = {r["code"] for r in rows("SELECT code FROM question WHERE lesson = 'hb-n4-118'")}
    check(st == 200 and card.get("code") in mine, f"hanabira 的课照旧出本课打了标的题：{card.get('code')}")
    write_jsonl(ws / "content" / "series" / "_example" / "lessons.jsonl", ex)
    post("/lesson/import", series="_example")

    print("八、老师")

    def send(text="", learner="me", lesson=None):
        form = {"content": text, "learner": learner}
        if lesson is not None:
            form["lesson"] = lesson
        mock.calls.clear()
        r = c.post("/teacher/send", json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    def last(body):
        m = body.get("messages") or []
        return m[-1] if m else {}

    def links(body):
        return [(unquote(x["href"]), x["text"]) for x in last(body).get("links") or []]

    def answer_prompt():
        p = [x["prompt"] for x in mock.calls if "意图分类器" not in (x.get("system") or "")]
        return p[-1] if p else ""

    st, body = send("讲讲第2课")
    lk = links(body)
    check(st == 200 and ("#教材?lesson=_example-002", "读课文：《示例：想做某事》") in lk
          and any(h == "#做题?lesson=_example-002" for h, _ in lk),
          f"当前 _example：「讲讲第2课」讲 _example-002，链接带课号：{lk}")
    check("示例教材" in answer_prompt() and "示例：想做某事" in answer_prompt(),
          "提示词里有当前系列名和这一课的正文")
    st, body = send("ようだ怎么用")
    lk = links(body)
    check(any(h == "#教材?lesson=hb-n4-118" and "（hanabira 语法）" in t for h, t in lk),
          f"兜底到 hanabira 的课：链接文字标系列名：{lk}")
    st, body = send("", lesson="hb-n5-046")
    lk = links(body)
    check(any(h == "#教材?lesson=hb-n5-046" and t.endswith("（hanabira 语法）") for h, t in lk),
          f"请老师讲别的系列的课：照讲，链接标系列名：{lk}")
    st, body = send("教材里有什么")
    p = answer_prompt()
    catalog = p.split("课文目录（按等级分组，只有标题）：【")[1].split("】")[0] if "课文目录" in p else ""
    check(catalog.startswith("教材：示例教材") and "示例：做完再做" in catalog and "动词 て います" not in catalog,
          f"「教材」意图：目录只列当前系列：{catalog[:80]}")
    st, body = send("讲讲N5第46课", learner="third")
    lk = links(body)
    check(("#教材?lesson=hb-n5-046", "读课文：《动词 て います》") in lk or
          any(h == "#教材?lesson=hb-n5-046" and t == "读课文：《动词 て います》" for h, t in lk),
          f"hanabira 的人：「讲讲第46课」照旧，链接文字不带系列名：{lk}")

    print("九、hanabira 回归")
    st, now_list = post("/lesson/list", learner="third")
    check((now_list.get("lists") or {}).get("lessons") == (base_list.get("lists") or {}).get("lessons")
          and (now_list.get("state") or {}).get("lesson_count") == (base_list.get("state") or {}).get("lesson_count"),
          "教材列表跟导入 _example 之前一模一样")
    st, now_one = post("/lesson/one", lesson="hb-n4-118", learner="third")
    check((now_one.get("state") or {}).get("reading") == (base_one.get("state") or {}).get("reading")
          and (now_one.get("lists") or {}).get("lesson_items") == (base_one.get("lists") or {}).get("lesson_items")
          and (now_one.get("lists") or {}).get("examples") == (base_one.get("lists") or {}).get("examples"),
          "读课（抬头、讲解、例句、条目、练习地址）一模一样")
    lessons_hb = [r["code"] for r in rows("SELECT code FROM lesson WHERE series = 'hanabira'")]
    diff = []
    for code in lessons_hb:
        a = rows("SELECT count(*) n FROM question WHERE lesson = ?", code)[0]["n"]
        b = _q("lesson_scope", lesson=code)[0]["n"]
        if a != b:
            diff.append(code)
    check(not diff, f"每一课的题数还是题库里打了这一课标的题数：{diff[:3]}")
    check({t: rows(f"SELECT * FROM {t}") for t in keep} == keep, "最后：学习记录一行没动")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


def rows_of_named(db, sql, args):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
