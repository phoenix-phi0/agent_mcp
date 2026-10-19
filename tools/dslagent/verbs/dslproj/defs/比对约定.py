"""比对约定：实际的函数头（名字 / 公开与否 / 入参顺序与可选）、依赖、接口（只调约定里那个函数）、表（entities 里有对应实体）与 contracts/<模块>.md 是否一致。
例如 设 d = 比对约定 graph      返回 {一致: 是|否, 差异: 文本（一行一条）, 条数}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 比对约定(模块: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _ctx as X
    if X.dry():
        return {"一致": "是", "差异": "", "条数": 0}
    P, _, c, mods = X.load(WORKSPACE, 模块)
    r = P.compare(Path(WORKSPACE), 模块.strip(), c, mods)
    return {"一致": "是" if r["一致"] else "否", "差异": "\n".join(r["差异"]), "条数": len(r["差异"])}
