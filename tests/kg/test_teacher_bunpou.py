# -*- coding: utf-8 -*-
"""老师讲语法课：课文导出、「语法讲解」流程、给老师的说明。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_teacher_bunpou.py

分工：老师只讲，练习和判题在做题页。所以这里测的是「讲」这一半能走通、
讲完给的链接能把人送到做题页那一课：

  一、导出：每课一个 .md、一个索引；标题、讲解、例句都在；有题的课末尾是
      做题页链接（#做题?lesson=编号，界面名编过码），没题的课说还没有题
  二、重导：源里撤掉的课，对应的 .md 被删掉，别的不动
  三、链接拿去开做题页：地址里的 lesson 解出来就是那一课，载入接口出的
      正是那一课的题（链接和接口对得上，不是各写各的）
  四、「语法讲解」流程：按编号读出课文原文，链接原样在；编号不存在时报错
      而不是编内容
  五、给老师的说明：有语法教材一节，写明语法不在对话里出题批改
"""

import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import client, import_graph, make_ws   # noqa: E402
from kg.__main__ import BANK, export_lessons, read_bank       # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    src = ROOT / "kg" / "content" / "lessons.jsonl"
    lessons = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    bank = read_bank(BANK)
    counts = {}
    for q in bank:
        counts[q["课文"]] = counts.get(q["课文"], 0) + 1

    tmp = Path(tempfile.mkdtemp(prefix="teacher_"))
    ws = tmp / "workspace"                       # 老师的工作目录
    out = ws / "content" / "bunpou" / "课文"
    base = "http://127.0.0.1:8190"

    print("一、导出")
    r = export_lessons(src=src, out=out, bank=bank, base=base)
    files = sorted(p.name for p in out.glob("*.md"))
    check(r["written"] == len(lessons) and len(files) == len(lessons) + 1,
          f"{len(lessons)} 课 + 索引：{len(files)} 个文件")
    with_q = next(d for d in lessons if counts.get(d["code"]))
    text = (out / f"{with_q['code']}.md").read_text(encoding="utf-8")
    ex = json.loads(with_q["examples"])[0]
    check(with_q["title"] in text and with_q["explanation"] in text and ex["jp"] in text,
          f"{with_q['code']}：标题、讲解、例句都在")
    link = next((l for l in text.splitlines() if l.startswith("http")), "")
    check(link.startswith(base + "/#%E5%81%9A%E9%A2%98?lesson="),
          f"末尾是做题页链接，界面名编过码：{link}")
    check(f"{counts[with_q['code']]} 道题" in text, "说了这一课有几道题")
    no_q = [d for d in lessons if not counts.get(d["code"])]
    if no_q:
        t2 = (out / f"{no_q[0]['code']}.md").read_text(encoding="utf-8")
        check("还没有题" in t2 and "http" not in t2, f"没题的课（{no_q[0]['code']}）不给链接")
    idx = (out / "INDEX.md").read_text(encoding="utf-8")
    check(all(f"| {d['code']} |" in idx for d in lessons), "索引里每课都有一行")
    check("语法讲解" in idx, "索引说明了怎么讲（run_flow 语法讲解）")

    print("二、重导")
    (out / "hb-old-999.md").write_text("撤掉的课", encoding="utf-8")
    keep = (out / f"{with_q['code']}.md").stat().st_size
    r = export_lessons(src=src, out=out, bank=bank, base=base)
    check(r["removed"] == 1 and not (out / "hb-old-999.md").exists(), "源里没有的课被删掉")
    check((out / f"{with_q['code']}.md").stat().st_size == keep, "别的课原样")

    print("三、链接拿去开做题页")
    frag = urlsplit(link).fragment                     # 做题?lesson=…
    screen, _, query = unquote(frag).partition("?")
    lesson = parse_qs(query).get("lesson", [""])[0]
    check(screen == "做题" and lesson == with_q["code"], f"地址解出来：界面「{screen}」课文 {lesson}")
    kg = make_ws(tmp / "kg")
    import_graph(kg)
    c = client(kg)
    c.post("/lesson/import", json={"form": {}})
    c.post("/quiz/import", json={"form": {"rows": bank}})
    resp = c.post("/quiz/lesson", json={"form": {"lesson": lesson}})
    import sqlite3
    con = sqlite3.connect(kg / "app.db")
    cur = con.execute("SELECT q.lesson FROM quiz_state s JOIN question q ON q.code = s.current"
                      " WHERE s.learner = 'me'").fetchone()
    con.close()
    check(resp.status_code == 200 and cur and cur[0] == lesson,
          f"载入接口出的正是那一课的题：{resp.status_code} {cur}")

    print("四、「语法讲解」流程")
    from agents.flows import make_flow_tools
    from tools.mock import MockClient
    reg = make_flow_tools(ws, client=MockClient(), flows_dir=ROOT / "flows",
                          verbs_dir=ROOT / "verbs")
    got = reg.call("run_flow", {"name": "语法讲解",
                                "params": json.dumps({"课文": with_q["code"]}, ensure_ascii=False)})
    check(got.startswith(text.splitlines()[0]) and link in got,
          f"读出的是课文原文，链接原样在：{got[:40]!r}")
    got = reg.call("run_flow", {"name": "语法讲解", "params": json.dumps({"课文": "hb-nope"})})
    check(got.startswith("[") and "不存在" in got, f"编号不存在：报错，不编内容：{got[:60]!r}")
    got = reg.call("list_flows", {})
    check("语法讲解" in got and "课文" in got, "老师的流程列表里有它、参数是「课文」")

    print("五、给老师的说明")
    from agents.japanese import RUNTIME_NOTE
    check("## 语法教材" in RUNTIME_NOTE and "语法讲解" in RUNTIME_NOTE, "有语法教材一节")
    check("不要在对话里自己出语法题" in RUNTIME_NOTE, "写明语法不在对话里出题批改")
    check("doushi_01" in RUNTIME_NOTE, "词汇教材那部分还在")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
