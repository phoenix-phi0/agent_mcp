"""带行号读文件片段，一次可读多段。例如 设 r = 读片段 {r.arg}

arg 写法：多个片段用逗号/分号分隔，每段「文件:起-止」，也认「文件 起 止」「文件:起」。
plan3：只写「文件」= 读整个文件（≤500 行整份返回；更长的给前 120 行 + 「文件共 N 行，太长请指定区间」+ def/class 行号清单）；
「文件:全文」= 整个文件全部行（不受 500 / 120 行限制，每个文件 ≤80000 字；补改用）；
没写文件名的段（「40-60」）沿用前一段的文件；每段字数上限 25000。
v6：片段打上步号（笔记状态 step+1）和函数清单，收起时按「最近 3 步/钉住/点名」决定；
读回被收起的旧片段记 reread_ref，超过 2 次写提示。
v4：每段单独设上限（≤200 行、≤6000 字），被截的段标明「（第 N 行后省略，需要再读 文件:N+1-M）」。
读到的片段记进笔记状态的【代码】区，同文件同区间再读时替换旧的；返回给脚本的文本只用于 trace。
"""

import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 读片段(文件: str = "", 起行: str = "", 止行: str = "") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _notes
    arg = " ".join(str(x) for x in (文件, 起行, 止行) if str(x or "").strip())
    if not arg.strip():
        return "[读片段] 没给文件"
    st = _notes.load(WORKSPACE)
    import _read
    out, got = _read.read_into(st, Path(WORKSPACE).resolve(), arg)
    st["latest"] = got
    _notes.save(WORKSPACE, st)
    return "\n\n".join(out)
