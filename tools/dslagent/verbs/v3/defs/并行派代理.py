"""并行派代理：一批 派代理 调用并发跑（roles.parallel_dispatch_agents 的 .zs 入口），并发数由
DSLAGENT_AGENT_CONCURRENCY 控制（缺省 4），共用同一份调度层账本（plan/agents.jsonl）。
返回结果列表，顺序与 组 一致。
例如 设 rs = 并行派代理 组=[{"角色": "logic_check", "任务": "…", "入参": {"约定": 文本}}, …]
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 并行派代理(组: list) -> list:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent import roles as R
    c = X.ctx()
    c.guard()

    def backend(spec, system, user, timeout):
        if c.M.real:
            from tools.dslagent import engines as EG
            return EG.call(spec, system, user, timeout)
        return c.M.backend(system, user, f"v3_agent_{spec['spec']}", timeout, model=spec["spec"])

    results = R.parallel_dispatch_agents(组 or [], out_dir=c.out, backend=backend, parent_id=str(c.out))
    cost = sum(r.get("cost") or 0.0 for r in results)
    with c.lock:
        c.module_cost += cost
    c.log("派代理", 事件="并行派代理", 条数=len(results), 花费=cost)
    c.guard()
    return results
