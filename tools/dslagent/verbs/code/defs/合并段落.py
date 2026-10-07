"""定位.zs 专用：模型在定位时直接给了 edits（action=改）时，把 edits 涉及的文件并进 segs，
交给 读改测.zs 作为后续轮次要读的范围。例如 设 sg = 合并段落 {pre} {d}
edits 里的文件：≤500 行并整份，更长的按 old 所在行 ±25 行并入。返回「文件:起-止,…」文本。"""

import json
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 合并段落(段落: str = "", 改法: str = "") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _locate5 as L
    from _sandbox import is_test_rel
    root = Path(WORKSPACE).resolve()
    seg = "" if str(段落 or "").strip() in ("", "无") else str(段落)
    m = L.parse_segs(root, seg)
    try:
        e = 改法 if isinstance(改法, dict) else json.loads(改法)
    except (TypeError, json.JSONDecodeError):
        e = {}
    for ed in (e.get("edits") or []) if isinstance(e, dict) else []:
        if not isinstance(ed, dict):
            continue
        rel = str(ed.get("file") or ed.get("path") or "").strip()
        lines = L.file_lines(root, rel)
        if not lines or is_test_rel(rel):
            continue
        if len(lines) <= L.WHOLE_MAX:
            m.setdefault(rel, []).append((1, len(lines)))
            continue
        old = str(ed.get("old") or "")
        first = old.splitlines()[0].strip() if old.strip() else ""
        hit = next((i for i, l in enumerate(lines, 1) if first and first in l), None)
        if hit:
            m.setdefault(rel, []).append((max(1, hit - 25), min(len(lines), hit + 25)))
    return L.fmt_segs(root, m) if m else seg
