# -*- coding: utf-8 -*-
"""语法题库：数据本身 + 判题（尤其是新加的「接续」题型）。

    cd /home/ysc/mcp && .venv/bin/python tests/quiz/test_bunpou.py

  一、数据：每行合法、id 唯一、课程和文件名一致；选择题题干里有 A–D 四个
      互不相同的选项、答案在 A–D；接续题有答案、可接受是列表
  二、和 kg 对得上：课文、条目编号都在 kg 的数据文件里
  三、动词能读：列课程、题目数、挑题（挑出来的不带答案）
  四、选择题判题：对的判对、错的判错（对照）
  五、接续题判题：标准答案对、可接受写法对、句号和全角空格不影响；
      **只差词尾的错答必须判错**（填空题那套去送假名的宽松规则不能漏进来）
  六、旧题库不受影响：n2n3 的填空题照样允许多写送假名
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def load_verbs():
    """加载 quiz 包，拿到动词函数。跟引擎「用包 quiz」是同一个 register。

    用真的动词表：判题的规则在 defs/判作答.zs 里，判题要经同一张表去调它。
    """
    from tools.dsl import RESERVED
    from tools.verbs import VerbRegistry
    ws = ROOT / "workspace" / "japanese"
    reg = VerbRegistry(reserved=RESERVED)
    reg.load_pack(ROOT / "verbs" / "quiz", workspace=ws)
    assert not reg.warnings, reg.warnings
    return {n: reg.resolve(n)[1] for n in reg.names() if reg.kind_of(n) == "python"}


def main():
    bank = ROOT / "workspace" / "japanese" / "content" / "bunpou" / "题库"
    files = sorted(bank.glob("*.jsonl"))
    rows = []
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                q = json.loads(line)
                q["_file"] = f.stem
                rows.append(q)

    print("一、数据")
    check([f.stem for f in files] == ["bunpou_n1", "bunpou_n2", "bunpou_n3", "bunpou_n4", "bunpou_n5"],
          f"五个等级各一个文件：{[f.stem for f in files]}")
    check(len(rows) == 466, f"共 {len(rows)} 题")
    ids = [q["id"] for q in rows]
    check(len(ids) == len(set(ids)), "id 唯一")
    check(all(q["课程"] == q["_file"] and q["id"].split("-")[0] == q["课程"] for q in rows),
          "课程和文件名、id 前缀一致（取题靠 id 第一段找文件）")
    bad = []
    for q in rows:
        if q["题型"] == "选择":
            lines = q["题干"].split("\n")
            opts = [l[3:] for l in lines if l[:3] in ("A. ", "B. ", "C. ", "D. ")]
            if len(opts) != 4 or len(set(opts)) != 4 or q["答案"] not in ("A", "B", "C", "D"):
                bad.append(q["id"])
        elif q["题型"] == "接续":
            if not q["答案"] or not isinstance(q.get("可接受", []), list) or "＿＿＿" not in q["题干"]:
                bad.append(q["id"])
        else:
            bad.append(q["id"])
    check(not bad, f"选择题四个不同选项、答案在 A–D；接续题有答案和空：{bad[:5]}")
    kinds = {}
    for q in rows:
        kinds[q["考点"]] = kinds.get(q["考点"], 0) + 1
    check(kinds == {"挖空": 247, "意思": 125, "接续": 72, "找错句": 22}, f"各考点题数：{kinds}")

    print("二、和 kg 对得上")
    kg = ROOT / "kg" / "content"
    lessons = {json.loads(l)["code"] for l in (kg / "lessons.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    items = {json.loads(l)["code"] for l in (kg / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    check(all(q["课文"] in lessons for q in rows), "课文编号都在 lessons.jsonl 里")
    check(all(q["条目"] in items for q in rows), "条目编号都在 items.jsonl 里")
    links = {(d["item"], d["lesson"]) for d in
             (json.loads(l) for l in (kg / "item_lessons.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    check(all((q["条目"], q["课文"]) in links for q in rows), "每题的条目确实挂着那一课")

    v = load_verbs()
    B = "content/bunpou/题库"

    print("三、动词能读")
    lc = v["列课程"](B)
    check("bunpou_n5（132题）" in lc and "bunpou_n1（10题）" in lc, f"列课程：{lc}")
    check(v["题目数"](B, "bunpou_n3", "") == "96", "按课程数题")
    check(v["题目数"](B, "", "接续") == "72", "按考点数题")
    picked = v["挑题"](B, "5", "bunpou_n4", "")
    check(picked.count("第") >= 5 and "答案" not in picked and "解析" not in picked,
          "挑题只给题干，不带答案和解析")

    print("四、选择题判题")
    q = next(q for q in rows if q["题型"] == "选择")
    wrong = next(c for c in "ABCD" if c != q["答案"])
    check(v["判题"](B, q["id"], q["答案"]).startswith("○"), f"{q['id']} 答 {q['答案']}：判对")
    check(v["判题"](B, q["id"], f"选{q['答案'].lower()}").startswith("○"), "写成「选b」这种也认")
    check(v["判题"](B, q["id"], wrong).startswith("✗"), f"答 {wrong}：判错（对照）")

    print("五、接续题判题")
    def J(qid, ans):
        return v["判题"](B, qid, ans).startswith("○")
    q = next(q for q in rows if q["id"] == "bunpou_n2-063-接续-1")   # 乗らざるを得なかった
    check(J(q["id"], "乗らざるを得なかった"), "标准答案：对")
    check(J(q["id"], "乗らざるをえなかった"), "可接受写法（得→え）：对")
    check(J(q["id"], "乗らざるを得なかった。"), "多写句号：对")
    check(J(q["id"], "　乗らざるを得なかった "), "前后有全角/半角空格：对")
    check(not J(q["id"], "乗るざるを得なかった"), "接续错（乗る）：错")
    check(not J(q["id"], "乗らざるを得ない"), "时态错（没变过去）：错")
    check(not J(q["id"], "乗"), "只写汉字：错（填空题规则会判对，这里不能）")
    check(not J(q["id"], ""), "空答：错")
    q = next(q for q in rows if q["id"] == "bunpou_n4-019-接续-1")   # 働かされた
    check(J(q["id"], "働かされた") and J(q["id"], "働かせられた"), "使役被动两种写法都对")
    check(not J(q["id"], "働かれた"), "写成普通被动「働かれた」：错（去掉词尾都是「働」）")
    check(not J(q["id"], "働かせた"), "写成使役「働かせた」：错")
    q = next(q for q in rows if q["id"] == "bunpou_n4-100-接续-1")
    check(J(q["id"], "先生だと思う") and J(q["id"], "先生だと思います"), "简体、敬体都列了的题两种都对")
    check(not J(q["id"], "先生と思う"), "漏了「だ」：错")
    res = v["判题"](B, "bunpou_n2-063-接续-1", "乗るざるを得なかった")
    check("正确答案是 乗らざるを得なかった" in res and "解析" not in res[:2], f"判错时给出正确答案和解析：{res[:60]}")

    print("六、旧题库不受影响")
    old = "content/n2n3/题库"
    check(v["判题"](old, "fukushi_02-08-漢字", "速").startswith("○"), "n2n3 填空：标准答案对")
    check(v["判题"](old, "fukushi_02-08-漢字", "速やか").startswith("○"), "n2n3 填空：多写送假名照样对")
    check(v["判题"](old, "fukushi_02-08-漢字", "早").startswith("✗"), "n2n3 填空：写错字判错")
    check(v["判题"](old, "fukushi_02-01-意味", "C").startswith("○"), "n2n3 选择题照常")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
