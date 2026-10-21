"""加载检查：服务启动时「接口出错」那一类问题（条件看不懂、变量名非法、遍历写法不对、业务函数调用不对……）现在就查，只报属于这个模块的文件
（services/<模块>.zs、routes/<模块>*.zs）的问题。
例如 设 c = 加载检查 graph      返回 {ok: 是|否, problems: 文本（一行一条）, count}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 加载检查(模块: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _ctx as X
    if X.dry():
        return {"ok": "是", "problems": "", "count": 0}
    P, _, _, mods = X.load(WORKSPACE, 模块)
    probs = P.load_problems(Path(WORKSPACE), 模块.strip(), mods)
    return {"ok": "否" if probs else "是", "problems": "\n".join(probs), "count": len(probs)}
