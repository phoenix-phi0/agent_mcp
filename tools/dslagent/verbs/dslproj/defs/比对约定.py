"""比对约定：实际的函数头（名字 / 公开与否 / 入参顺序与可选）、依赖、接口（只调约定里那个函数）、表（entities 里有对应实体）、
约定里明确写出的唯一声明（「唯一」自成一词 / 紧跟逗号 / 括号里只有「唯一」/ a + b 唯一，见 packs.dslproj.contract.unique_decls）
在实体里有「唯一」旗标（多列「唯一 a b」行）与 contracts/<模块>.md 是否一致。
例如 设 d = 比对约定 graph      返回 {consistent: 是|否, diffs: 文本（一行一条）, count, hints: 提示文本（不算不一致，如声明了的内容文件没人写）}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 比对约定(模块: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _ctx as X
    if X.dry():
        return {"consistent": "是", "diffs": "", "count": 0}
    P, _, c, mods = X.load(WORKSPACE, 模块)
    r = P.compare(Path(WORKSPACE), 模块.strip(), c, mods)
    return {"consistent": "是" if r["一致"] else "否", "diffs": "\n".join(r["差异"]), "count": len(r["差异"]), "hints": "\n".join(r.get("提示", []))}
