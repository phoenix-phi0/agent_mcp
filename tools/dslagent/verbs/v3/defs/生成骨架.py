"""生成骨架：从冻结的约定生成 entities/<m>.entity（表）、services/<m>.zs（函数头 + 伪代码注释 + 报错 未实现）、routes/<m>.zs（接口头 + 调用）。
已存在的文件不覆盖（续跑安全），只有从没通过过的模块、约定 hash 比生成骨架时变了才重写（判据见 scaffold.gen_skeleton）；新生成的文件要过加载检查，不过 终止 失败。返回 {created, existing, created_count}。
例如 生成骨架
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 生成骨架() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL, scaffold as SF
    c = X.ctx()
    try:
        r = SF.gen_skeleton(c.project, PL.current_top(c), never_built=lambda n: n not in c.load_state().get("模块", {}))
    except ValueError as e:
        X.fail(e)
    c.log("骨架", 新建=r["新建"], 已有=len(r["已有"]), 加载检查问题=r["问题"][:8])
    if r["问题"]:
        X.fail("骨架生成后加载检查没过：" + "；".join(r["问题"][:5]))
    return {"created": r["新建"], "existing": r["已有"], "created_count": len(r["新建"])}
