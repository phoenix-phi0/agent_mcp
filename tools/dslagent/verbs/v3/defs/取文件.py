"""取文件：读一个文本文件，返回文本（纯程序）。路径只限需求文件和项目目录内（相对路径从项目目录算）；
「@名字」读 v3 自带的提示词（tools/dslagent/v3/prompts/名字）。读不到返回空串，原因记在 v3_log.jsonl（类=取文件）。
需求文件可能在工作目录之外，所以核查.zs 用它把需求读成文本再当入参传给 派任务。
例如 设 text = 取文件 {req_file}   设 top = 取文件 plan/top.zs   设 desc = 取文件 @audit.md
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 取文件(路径: str = "") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import audit as AU
    c = X.ctx()
    text, why = AU.read_file(c, 路径)
    if why:
        c.log("取文件", 路径=str(路径)[:200], summary=why)
    return text
