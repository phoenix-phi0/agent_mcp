"""派代理：按 tools/dslagent/roles.zs 登记的角色调一次模型（roles.dispatch_agent 的 .zs 入口）。
假模型跑时走 ctx.M 的 backend（跟别的 v3 调用共用一份假回复），真跑时走 engines.call；花费并入 ctx 的花费上限。
返回 {result, status, reason, role, model, cost, calls, secs}。
例如 设 r = 派代理 角色=logic_check 任务=检查这份约定有没有逻辑漏洞 入参={"约定": 文本}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 派代理(角色: str, 任务: str = "", 入参: dict = None, 格式: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent import roles as R
    c = X.ctx()
    c.guard()

    def backend(spec, system, user, timeout):
        if c.M.real:
            from tools.dslagent import engines as EG
            return EG.call(spec, system, user, timeout)
        return c.M.backend(system, user, f"v3_agent_{角色}", timeout, model=spec["spec"])

    r = R.dispatch_agent(角色, 任务, 入参, 格式 or None, out_dir=c.out, backend=backend, parent_id=str(c.out))
    with c.lock:
        c.module_cost += r.get("cost") or 0.0
    c.log("派代理", 角色=角色, 状态=r["status"], 原因=(r.get("reason") or "")[:200], 花费=r.get("cost"))
    c.guard()
    return r
