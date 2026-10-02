# -*- coding: utf-8 -*-
"""把翻好的中文释义合回词表。

    cd /home/ysc/mcp && .venv/bin/python kg/content/translate/merge.py
    cd /home/ysc/mcp && .venv/bin/python kg/content/translate/merge.py --试

读这个目录下所有 `*.zh.tsv`（翻译产出），跟同名的 `.tsv`（原文）逐条核对，
全部通过才写回 kg/content/words_jlpt.jsonl。

## 为什么要核对而不是直接合

回填靠编号对齐，错一个就串行——而串行之后每条词都配了别人的释义，
看起来还挺正常，很难发现。所以宁可拒绝整批：

  行数不一样        → 整批不收（漏行或多行）
  编号对不上        → 整批不收（顺序被改过）
  中文列是空的      → 那一条不收
  中文里还有英文字母 → 那一条不收（多半没翻）
  中文里有平假名片假名 → 那一条不收（原文抄进去了）

通过的才写。没翻的批次会列出来。
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORDS = HERE.parent / "words_jlpt.jsonl"

LATIN = re.compile(r"[A-Za-z]")
KANA = re.compile(r"[\u3040-\u30ff]")


def main() -> int:
    dry = "--试" in sys.argv
    src_files = sorted(f for f in HERE.glob("*.tsv") if not f.name.endswith(".zh.tsv"))
    if not src_files:
        print("这个目录下没有待翻译的 .tsv")
        return 1

    good, waiting, rejected = {}, [], []
    for src in src_files:
        zh = src.with_suffix(".zh.tsv")
        if not zh.is_file():
            waiting.append(src.name)
            continue

        def rows(p, cols):
            out = []
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.startswith("#"):
                    continue
                parts = line.split("\t")
                out.append(parts + [""] * (cols - len(parts)))
            return out

        a, b = rows(src, 4), rows(zh, 2)
        if len(a) != len(b):
            rejected.append(f"{zh.name}：行数对不上（原 {len(a)}，译 {len(b)}）")
            continue
        bad = [i for i, (x, y) in enumerate(zip(a, b), 1) if x[0].strip() != y[0].strip()]
        if bad:
            rejected.append(f"{zh.name}：第 {bad[:3]} 行编号对不上，整批不收")
            continue

        for (wid, kanji, kana, en), (_, cn) in zip(a, b):
            cn = cn.strip()
            if not cn:
                rejected.append(f"{zh.name} 编号 {wid}：中文是空的")
            elif LATIN.search(cn):
                rejected.append(f"{zh.name} 编号 {wid}：中文里有英文字母「{cn[:20]}」")
            elif KANA.search(cn):
                rejected.append(f"{zh.name} 编号 {wid}：中文里有假名「{cn[:20]}」")
            else:
                good[int(wid)] = cn

    print(f"可用的译文 {len(good)} 条")
    if waiting:
        print(f"还没翻的 {len(waiting)} 批：{'、'.join(waiting[:8])}"
              + ("…" if len(waiting) > 8 else ""))
    if rejected:
        print(f"没通过检查的 {len(rejected)} 处：")
        for r in rejected[:15]:
            print("  " + r)
    if not good:
        return 1

    # 词表里按 id 找不到，所以用 汉字+假名 当键——跟导入器认同一个词的方式一致
    import sqlite3
    con = sqlite3.connect(HERE.parent.parent / "app.db")
    key = {}
    for wid, kanji, kana in con.execute("SELECT id, kanji, kana FROM word"):
        key[wid] = (kanji or "", kana)
    con.close()

    rows = [json.loads(l) for l in WORDS.read_text(encoding="utf-8").splitlines() if l.strip()]
    index = {(r["kanji"], r["kana"]): r for r in rows}
    hit = 0
    for wid, cn in good.items():
        k = key.get(wid)
        if k and k in index:
            # 等级标记留着，它有用；只把英文换成中文
            m = re.match(r"(\[N\d\]\s*)", index[k]["meaning"])
            index[k]["meaning"] = (m.group(1) if m else "") + cn
            hit += 1
    print(f"对上并替换 {hit} 条")

    if dry:
        print("（试跑，没写文件）")
        return 0
    WORDS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                     encoding="utf-8")
    print(f"写回 {WORDS.name}。接着跑 py -m kg import 入库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
