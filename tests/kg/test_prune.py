# -*- coding: utf-8 -*-
"""对账脚本 kg/prune.py：清掉库里有、文件里已经没有的条目和对照。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_prune.py

它删的是 kg/app.db 里的东西，那个库里有真学习记录，所以单独测。早先的
版本没测试，漏查了「对照引用着条目」——拆条目时把 ga-kedo、node-kara 删了，
contrast.jsonl 里还有一对指着它们。

在临时工作区里往库里塞几种「拆条目之后留下的旧数据」：

  old-a ← old-b      旧条目，old-b 的 after 指着 old-a：要级联删干净
  old-c              旧条目，被一对旧对照（文件里没有）引用：先删对照，再删它
  old-d              旧条目，mastery 里有学习记录：不删，报出来
  old-e              旧条目，被文件里还在的对照引用：不删，报出来
  hiragana ↔ ghost   文件里有、库里没有的对照（ghost 不存在）：报出来

  一、只看：什么都不删，返回 1
  二、真删：该删的删了、该挡的挡住了，现有数据一条没少
  三、干净的库：返回 0
"""

import contextlib
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import import_graph, make_ws   # noqa: E402
from kg.prune import main as prune                    # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(ws, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = prune(list(argv), root=ws)
    return code, buf.getvalue()


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="prune_")))
    import_graph(ws)
    db = ws / "app.db"

    def q(sql, *args):
        con = sqlite3.connect(db)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def items():
        return {c for c, in q("SELECT code FROM item")}

    def pairs():
        return set(q("SELECT a, b FROM contrast"))

    print("三、干净的库（先测：导入完什么都不该动）")
    code, out = run(ws)
    check(code == 0 and "库和文件一致" in out, f"刚导入完：返回 {code}")
    real_items, real_pairs = items(), pairs()

    # 塞旧数据
    con = sqlite3.connect(db)
    con.executescript("""
      INSERT INTO item(code, label, point, form, after) VALUES
        ('old-a', '旧A', 'hiragana', NULL, ''),
        ('old-b', '旧B', 'hiragana', NULL, 'old-a'),
        ('old-c', '旧C', 'hiragana', NULL, ''),
        ('old-d', '旧D', 'hiragana', NULL, ''),
        ('old-e', '旧E', 'hiragana', NULL, '');
      INSERT INTO contrast(a, b) VALUES ('old-c', 'zz-gone'), ('hiragana', 'old-e');
      INSERT INTO mastery(learner, point, right, total, mastered) VALUES ('u', 'old-d', 1, 2, 0);
    """)
    con.commit()
    con.close()
    # hiragana↔old-e 留在文件里（所以 old-e 删不得）；再加一对写错的 hiragana↔ghost
    src = ws / "content" / "contrast.jsonl"
    with src.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"a": "old-e", "b": "hiragana"}) + "\n")
        f.write(json.dumps({"a": "hiragana", "b": "ghost"}) + "\n")

    print("一、只看")
    before_items, before_pairs = items(), pairs()
    code, out = run(ws)
    check(code == 1, f"有没对上的，返回 1：{code}")
    check(items() == before_items and pairs() == before_pairs, "一行没删")
    check("old-a" in out and "old-b" in out and "old-c" in out, "旧条目都列出来了")
    check("ghost 不存在" in out, "文件里那对写错的对照指出了是哪头不存在")
    check("--删" in out, "提示加 --删")

    print("二、真删")
    code, out = run(ws, "--删")
    now = items()
    check("old-a" not in now and "old-b" not in now,
          "old-b 指着 old-a 的级联：两条都删干净（删到不动为止）")
    check(("old-c", "zz-gone") not in pairs(), "文件里没有的对照删了")
    check("old-c" not in now, "old-c 的对照先删掉，它就自由了，也删了")
    check("old-d" in now and "mastery" in out, "old-d 有学习记录，没删，报了原因")
    check("old-e" in now and "对照" in out and ("hiragana", "old-e") in pairs(),
          "old-e 被文件里还在的对照引用着，没删，对照也还在")
    check(code == 1 and "ghost" in out, f"还剩没解决的（old-d、old-e、ghost），返回 1：{code}")
    check(real_items <= now, f"现有条目一条没少：{len(real_items & now)}/{len(real_items)}")
    check(real_pairs <= pairs(), f"现有对照一对没少：{len(real_pairs & pairs())}/{len(real_pairs)}")
    check(q("SELECT count(*) FROM mastery WHERE point='old-d'")[0][0] == 1, "学习记录原样在")

    print("三、干净的库")
    # 把挡路的处理掉，再跑一遍应该就一致了
    con = sqlite3.connect(db)
    con.execute("DELETE FROM mastery WHERE point = 'old-d'")
    con.commit()
    con.close()
    src.write_text("".join(l + "\n" for l in src.read_text(encoding="utf-8").splitlines()
                           if "old-e" not in l and "ghost" not in l), encoding="utf-8")
    code, out = run(ws, "--删")
    check("old-d" not in items() and "old-e" not in items(),
          "引用处理掉之后，old-d、old-e 都删了")
    check(code == 0 and "库和文件一致" in out, f"返回 0：{code}")
    check(items() == real_items and pairs() == real_pairs, "回到刚导入完的样子")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
