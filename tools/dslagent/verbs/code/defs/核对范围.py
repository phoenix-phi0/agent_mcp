"""plan5 定位.zs 专用：模型选「读这些」后，确认要读的范围里有没有它自己提到的关键标识；不在就精确搜索补读「行号 ±25」。
例如 设 ck = 核对范围 {segs} {clue} {hits} {task}
线索＝模型的 reason + 运行输出；当轮搜索被截断（结果以「[搜索] 共 N 条命中」开头）时，任务描述也一起抽标识。
返回 {segs: 合并后的段落, added: 补读的段（没补就空）, note: 「已按 X 补读 文件:起-止」, ids: 抽到的标识, trunc: 是/否}
"""

import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 核对范围(段落: str = "", 线索: str = "", 搜索结果: str = "", 任务: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _locate5 as L
    root = Path(WORKSPACE).resolve()
    trunc = str(搜索结果 or "").startswith("[搜索] 共")
    text = str(线索 or "") + ("\n" + str(任务 or "") if trunc else "")
    ids = [x for x in L.ids_from(root, text) if x[1] != "文件"]
    m = L.parse_segs(root, 段落)
    added, notes = [], []
    for tok, kind, hits in ids:
        if any(L.covered(m, rel, ln) for rel, ln in hits):
            continue
        pick = [h for h in hits if h[0] in m] or hits      # 命中在已选文件里的优先（那多半就是模型说的那处）
        got = [L.add_around(root, m, rel, ln) for rel, ln in pick[:2]]
        got = [g for g in got if g]
        if got:
            added += got
            notes.append(f"已按 {tok} 补读 {'、'.join(got)}")
    segs = L.fmt_segs(root, m) if added else str(段落 or "")
    rec = {"verb": "核对范围", "segs_in": str(段落)[:200], "ids": [f"{t}({k},{len(h)})" for t, k, h in ids],
           "trunc": trunc, "added": added, "segs_out": segs[:300]}
    L.log(root, rec)
    return {"segs": segs, "added": ",".join(added), "note": "；".join(notes),
            "ids": "、".join(t for t, _, _ in ids), "trunc": "是" if trunc else "否"}
