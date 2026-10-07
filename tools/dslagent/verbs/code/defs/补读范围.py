"""读改测.zs 专用：模型说「要改但手里没有原文」并给了 need（「文件:起-止」或关键标识）时，把缺的部分并进 segs。
例如 设 bk = 补读范围 {segs} {need} {reason}
need 是「文件:起-止」/文件名 → 整个区间没被已读的段覆盖就并入（只看两端会漏掉中间的空洞）；
否则当关键标识：整句先精确搜一次，再从 need + reason 里抽标识（含文件名）精确搜，
每处命中分别判断：没读到的命中处取「行号 ±25」（文件名＝整文件，≤500 行才并）；一处读到了不代表别处也读到了。
返回 {segs, added（没补到就空）, note}
"""

import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
PER_ID = 2      # 每个标识最多补读几处命中


def 补读范围(段落: str = "", 需要: str = "", 线索: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _locate5 as L
    from _sandbox import is_test_rel
    root = Path(WORKSPACE).resolve()
    need = str(需要 or "").strip()
    if need == "无":
        need = ""
    m = L.parse_segs(root, 段落)
    added, how = [], []
    # 1) need 本身就是段落
    want = L.parse_segs(root, need) if re.search(r"\w+\.py", need) else {}
    for rel, iv in want.items():
        if is_test_rel(rel):
            continue
        for a, b in iv:
            if not L.covered_range(m, rel, a, b):
                m.setdefault(rel, []).append((max(1, a - 5), b + 5))
                added.append(f"{rel}:{a}-{b}" if (a, b) != (1, len(L.file_lines(root, rel))) else rel)
                how.append(need)
    # 2) 当关键标识
    if not added:
        cands = []
        if need and len(need) <= 40 and "\n" not in need:
            hits = L.find(root, need)
            if hits and len(hits) <= L.MAX_HITS:
                cands.append((need, "整句", hits))
        cands += [x for x in L.ids_from(root, need + "\n" + str(线索 or "")) if x[0] != need]
        for tok, kind, hits in cands[:L.TOP]:
            if kind == "文件":
                if hits[0][0] in m:
                    continue
                todo = hits[:1]
            else:
                todo = [h for h in hits if not L.covered(m, *h)][:PER_ID]
            got = [g for g in (L.add_around(root, m, rel, ln) for rel, ln in todo) if g]
            if got:
                added += got
                how.append(tok)
    segs = L.fmt_segs(root, m) if added else str(段落 or "")
    L.log(root, {"verb": "补读范围", "need": need[:200], "added": added, "how": how, "segs_out": segs[:300]})
    note = f"已按 {'、'.join(dict.fromkeys(how))} 补读 {'、'.join(added)}" if added else f"没能按「{need[:60]}」补读到新内容"
    return {"segs": segs, "added": ",".join(added), "note": note}
