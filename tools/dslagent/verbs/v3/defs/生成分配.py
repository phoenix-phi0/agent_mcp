"""生成分配：从 plan/top.zs 按依赖分层生成 plan/build.zs（一层一行 做模块组 甲,乙；程序生成，不调模型）。返回 {path, content}。
例如 生成分配
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 生成分配() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL, scaffold as SF
    c = X.ctx()
    try:
        top = PL.current_top(c)
    except ValueError as e:
        X.fail(e)
    rel = SF.gen_build(c.project, top)
    c.log("分配", 路径=rel)
    return {"path": rel, "content": SF.build_text(top)}
