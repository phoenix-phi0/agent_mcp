"""读文件原文：不加行号，≤200000 字。路径在项目根下；「pack:名字.md」读 newproj 模板自带的提示词。返回 {ok, text}。
例如 设 p = 读原文 pack:sys_ent.md   然后用 {p.text}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
MAX_CHARS = 200000


def 读原文(路径: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    rel = str(路径 or "").strip().strip("'\"")
    if rel.startswith(G.PACK_PREFIX):
        p, err = G.sandbox_resolve(G.PROMPTS, rel[len(G.PACK_PREFIX):])
    else:
        p, err = G.sandbox_resolve(WORKSPACE, rel)
    if err:
        return {"ok": "否", "text": "", "msg": err}
    if not p.is_file():
        return {"ok": "否", "text": "", "msg": f"[读原文] {rel} 不是文件或不存在"}
    try:
        t = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {"ok": "否", "text": "", "msg": f"[读原文] {rel} 读不了：{e}"}
    if len(t) > MAX_CHARS:
        return {"ok": "否", "text": "", "msg": f"[读原文] {rel} 超过 {MAX_CHARS} 字（{len(t)}）"}
    if rel.startswith(G.PACK_PREFIX):
        import _tplset
        t = _tplset.fill(t)
    return {"ok": "是", "text": t}
