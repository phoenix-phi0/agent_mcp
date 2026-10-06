# -*- coding: utf-8 -*-
"""判对错、拆选项、判默写挪进 .zs 之后，跟旧的 Python 实现逐条对照。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_rules_equiv.py           # 抽样（run_all 跑这个）
    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_rules_equiv.py --全部    # 全部题、全部词

旧实现原样留在 tests/kg/legacy_rules.py（取自挪之前的提交）。新实现是
verbs/quiz/defs/判作答.zs、判对错.zs、拆选项.zs 和 verbs/japanese/defs/判默写.zs，
经引擎调（invoke_verb，跟接口里「设 x = 判对错 {judge_args}」同一条路）。

数据是真的：kg/app.db 只读打开（uri mode=ro），一行不写。

  一、判对错：question 表每道题 × 各种作答（对的、错的、大小写全角、带句号、
      空、选项原文……），可接受按库里原样传（NULL 时传接口实际会传的那个
      「{key.accept}」字面量，也传 None）；接续题的作答再按「填空」题型判一遍，
      覆盖填空的规则。n2n3 旧题库的填空题也判
  二、判题（读题库文件的那个，quiz 包的 Python 动词经 判作答.zs）：输出文本跟旧的一样
  三、拆选项：每道题 × 每个 seq 种子（learner|code|seq）的打乱结果，加上答完之后
      标对错（选了 A–D、小写、空）
  四、判默写：能出的词（dictation_pick.sql 的 pool）两个方向 × 作答（汉字、假名、
      片假名、半角片假名、带空白句号、同义词、同读音异义词、同汉字另一个读法、空），
      候选用 dictation_near.sql 现查

结果要求逐条一致，不一致的列出来（最多 20 条）。
"""

import json
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import tests.kg.legacy_rules as old       # noqa: E402
from tools import packs                   # noqa: E402
from tools.dsl import invoke_verb         # noqa: E402

FULL = "--全部" in sys.argv[1:]
# 抽样时每 STEP 道题 / 个词取一个，seq 只取前几个
STEP = 1 if FULL else 15
SEQS = range(0, 31) if FULL else range(0, 3)
MARK_SEQS = range(0, 4) if FULL else range(0, 1)

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


REG = packs.registry(["common", "text", "quiz", "japanese"], ROOT, cache=False)


def new(name, arg):
    return invoke_verb(REG, name, arg, workdir=ROOT, verbs_root=packs.verbs_root())


def call(fn, arg):
    """结果或异常的类型名：两边都抛也算一致。"""
    try:
        return fn(arg)
    except Exception as e:  # noqa: BLE001 —— 对照的是「抛没抛」
        return ("抛错", type(e).__name__)


def compare(name, cases, old_fn, new_fn):
    """逐条比，返回 (条数, 不一致列表)。"""
    bad = []
    for arg in cases:
        a, b = call(old_fn, arg), call(new_fn, arg)
        if isinstance(a, tuple) and isinstance(b, tuple):
            continue        # 都抛（旧的 ValueError，新的经引擎是 DSLError）
        if a != b:
            bad.append((arg, a, b))
    return len(cases), bad


def show_bad(bad):
    for arg, a, b in bad[:20]:
        print(f"      {json.dumps(arg, ensure_ascii=False)[:200]}")
        print(f"        旧 {json.dumps(a, ensure_ascii=False)[:200]}")
        print(f"        新 {json.dumps(b, ensure_ascii=False)[:200]}")


def fw(s: str) -> str:
    """半角 ASCII 换成全角（Ｃ、。这种）。"""
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in s)


def kata(s: str) -> str:
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def halfwidth_kata(s: str) -> str:
    """平假名 → 半角片假名（NFKC 会变回全角片假名）。"""
    table = {unicodedata.normalize("NFKC", chr(c)): chr(c) for c in range(0xFF66, 0xFF9E)}
    return "".join(table.get(c, c) for c in kata(s))


def options_of(stem: str) -> dict:
    out = {}
    for line in stem.splitlines():
        m = old._OPTION_RE.match(line)
        if m:
            out[unicodedata.normalize("NFKC", m.group(1)).upper()] = m.group(2).strip()
    return out


def answers_for(qtype: str, answer: str, accept: list, stem: str) -> list:
    if qtype == "选择":
        opts = options_of(stem)
        wrong = [k for k in "ABCD" if k != answer]
        return ([answer, answer.lower(), fw(answer), fw(answer.lower()), f"选{answer.lower()}",
                 f"{answer}。", f"答案是 {answer}", f"（{fw(answer)}）", f" {answer} ", "", " ", "。",
                 "E", "x", opts.get(answer, ""), "あ"] + wrong + [w.lower() for w in wrong[:1]])
    alts = [answer] + [str(a) for a in accept]
    out = []
    for a in alts:
        # 原样、带句号、带空白、全角、片假名、少一个字、多一个送假名、只写汉字
        out += [a, a + "。", a + "。。", " " + a + " ", "　" + a + "　", fw(a), kata(a), a[:-1], a + "る",
                "".join(c for c in a if not "ぁ" <= c <= "ゟ")]
    out += ["", "。", " ", answer[:1]]
    return out


def main():
    con = sqlite3.connect(f"file:{ROOT / 'kg' / 'app.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    t0 = time.time()

    questions = [dict(r) for r in con.execute(
        "SELECT code, qtype, stem, answer, accept FROM question ORDER BY code")]
    print(f"题 {len(questions)} 道，{'全部' if FULL else f'每 {STEP} 道取一'}")
    sample = questions[::STEP]

    print("一、判对错")
    cases = []
    for q in sample:
        accept = json.loads(q["accept"]) if q["accept"] else []
        for given in answers_for(q["qtype"], q["answer"], accept, q["stem"]):
            for acc in ([q["accept"]] if q["accept"] else ["{key.accept}", None]):
                cases.append({"题型": q["qtype"], "答案": q["answer"], "可接受": acc, "作答": given})
                if q["qtype"] == "接续":
                    cases.append({"题型": "填空", "答案": q["answer"], "可接受": acc, "作答": given})
    # n2n3 旧题库：真的填空题（允许多写送假名的那套）
    bank_rows = []
    for f in sorted((ROOT / "workspace/japanese/content/n2n3/题库").glob("*.jsonl")):
        bank_rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    for q in bank_rows[::STEP]:
        for given in answers_for(q.get("题型", ""), str(q.get("答案", "")), q.get("可接受") or [],
                                 q.get("题干", "")):
            cases.append({"题型": q.get("题型", ""), "答案": str(q.get("答案", "")),
                          "可接受": q.get("可接受"), "作答": given})
    cases += [{"题型": "选择", "答案": "C"}, {"题型": "接续", "答案": "x", "可接受": "x。", "作答": "x"},
              {"题型": "接续", "答案": "x", "可接受": [1, "y"], "作答": "1"}, "不是JSON", {"题型": "选择"}]
    n, bad = compare("判对错", cases, old.判对错, lambda a: new("判对错", a))
    check(not bad, f"判对错 {n} 条，不一致 {len(bad)} 条")
    show_bad(bad)

    print("二、判题（读题库文件，quiz 包的 Python 动词经 判作答.zs）")
    ws = ROOT / "workspace" / "japanese"
    reg_q = packs.registry(["quiz"], ws, cache=False)
    judge_file = reg_q.resolve("判题")[1]

    def old_judge(q, given):
        # 旧 _judge 的输出格式，规则用旧实现
        标准, 解析 = str(q.get("答案", "")), str(q.get("解析", ""))
        if str(q.get("题型", "")) == "选择":
            对, 提取 = old._judge_choice(标准, given)
            你的 = f"你选了 {提取}" if 提取 else "没看出你选的是哪个选项"
        elif str(q.get("题型", "")) == "接续":
            对, 提取 = old._judge_exact(标准, q.get("可接受"), given)
            你的 = f"你写的是「{提取}」" if 提取 else "没看出你的作答"
        else:
            对, 提取 = old._judge_fill(标准, given)
            你的 = f"你写的是「{提取}」" if 提取 else "没看出你的作答"
        return f"○ 答对了\n{解析}" if 对 else f"✗ 再看看\n{你的}，正确答案是 {标准}。\n{解析}"

    file_cases = []
    for bank, rows in (("content/bunpou/题库", None), ("content/n2n3/题库", bank_rows)):
        if rows is None:
            rows = []
            for f in sorted((ws / bank).glob("*.jsonl")):
                rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        for q in rows[::STEP * 3]:
            for given in answers_for(q.get("题型", ""), str(q.get("答案", "")), q.get("可接受") or [],
                                     q.get("题干", ""))[:8]:
                file_cases.append((bank, q, given))
    bad = [(f"{b} {q['id']} {g!r}", old_judge(q, g), judge_file(b, q["id"], g))
           for b, q, g in file_cases if old_judge(q, g) != judge_file(b, q["id"], g)]
    check(not bad, f"判题 {len(file_cases)} 条，输出文本不一致 {len(bad)} 条")
    show_bad(bad)

    print("三、拆选项")
    cases = []
    for q in sample:
        base = {"题干": q["stem"], "题型": q["qtype"]}
        cases.append(dict(base))
        cases.append(dict(base, 答案=q["answer"], 选了="A"))          # 没种子：字母不变
        for seq in SEQS:
            cases.append(dict(base, 种子=f"me|{q['code']}|{seq}"))     # 出题：quiz_pick.zs
        for seq in MARK_SEQS:
            for chosen in ("A", "B", "C", "D", "c", "", "Ｂ"):
                cases.append(dict(base, 答案=q["answer"], 选了=chosen,  # 判题：quiz.zs
                                  种子=f"other|{q['code']}|{seq}"))
    cases += ["不是JSON", {"题干": "A. x\nB. y", "题型": "选择", "种子": "s", "答案": "b", "选了": "a"},
              {"题干": "  题面  \r\nＡ．甲\r\nB：乙  \n\n", "题型": "选择", "种子": "s"}]
    n, bad = compare("拆选项", cases, old.拆选项, lambda a: new("拆选项", a))
    check(not bad, f"拆选项 {n} 条，不一致 {len(bad)} 条")
    show_bad(bad)

    print("四、判默写")
    pool = {}
    for direction in ("meaning", "reading"):
        pool[direction] = [r[0] for r in con.execute("""
            SELECT w.id FROM word w
            WHERE trim(coalesce(w.meaning, '')) <> ''
              AND coalesce(w.point, '') NOT IN ('hiragana', 'katakana', 'youon', 'dakuon',
                  'potential', 'volitional', 'imperative', 'causative', 'causative-passive',
                  'counters-sound')
              AND (:direction = 'meaning'
                   OR (trim(coalesce(w.kanji, '')) <> '' AND w.kanji <> w.kana))
              AND trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5)
                            ELSE w.meaning END) <> ''
              AND ' ' || trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5)
                                   ELSE w.meaning END) NOT GLOB '*[^ ] 的*'
              AND trim(CASE WHEN w.meaning GLOB '[[]N[1-5]]*' THEN substr(w.meaning, 5)
                            ELSE w.meaning END) NOT LIKE '%的礼貌形'
            ORDER BY w.id""", {"direction": direction})]
    print(f"  能出的词：看中文写日语 {len(pool['meaning'])}，看汉字写读音 {len(pool['reading'])}"
          f"（{'全部' if FULL else f'每 {STEP} 个取一'}）")
    word_sql = (ROOT / "kg/queries/dictation_word.sql").read_text(encoding="utf-8")
    near_sql = (ROOT / "kg/queries/dictation_near.sql").read_text(encoding="utf-8")
    cases = []
    kinds = {}
    for direction, ids in pool.items():
        for wid in ids[::STEP]:
            p = {"word": str(wid), "direction": direction}
            w = dict(con.execute(word_sql, p).fetchone())
            near = [dict(r) for r in con.execute(near_sql, p)]
            word = {k: w[k] for k in ("kanji", "kana", "meaning")}
            answers = {"kanji": [w["kanji"]], "kana": [w["kana"], " " + w["kana"] + "。"],
                       "片假名": [kata(w["kana"]), halfwidth_kata(w["kana"])], "空": ["", " 。"]}
            for c in near:
                bare = old._meaning(c["meaning"])
                if bare == w["bare"]:
                    answers.setdefault("同义词", []).extend([c["kanji"], c["kana"]])
                elif c["kana"] == w["kana"]:
                    answers.setdefault("同读音异义", []).append(c["kanji"] or c["kana"])
                if c["kanji"] and c["kanji"] == w["kanji"] and c["kana"] != w["kana"]:
                    answers.setdefault("另一个读法", []).append(c["kana"])
            for kind, xs in answers.items():
                for x in xs:
                    if x is None:
                        continue
                    kinds[kind] = kinds.get(kind, 0) + 1
                    cases.append({"方向": direction, "作答": x, "词": word, "候选": near})
    cases += ["不是JSON", {"方向": "x", "作答": "a", "词": {"kana": "あ"}},
              {"方向": "meaning", "作答": "a", "词": {}},
              {"方向": "meaning", "作答": "あ", "词": json.dumps({"kana": "あ"}), "候选": "[]"}]
    print(f"  作答：{'、'.join(f'{k} {v}' for k, v in kinds.items())}")
    n, bad = compare("判默写", cases, old.判默写, lambda a: new("判默写", a))
    check(not bad, f"判默写 {n} 条，不一致 {len(bad)} 条")
    show_bad(bad)

    con.close()
    print(f"\n用时 {time.time() - t0:.0f} 秒")
    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
