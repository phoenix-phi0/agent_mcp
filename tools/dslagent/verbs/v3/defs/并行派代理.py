"""并行派代理：一批 派代理 调用并发跑（roles.parallel_dispatch_agents 的 .zs 入口），并发数由
DSLAGENT_AGENT_CONCURRENCY 控制（缺省 4），共用同一份调度层账本（plan/agents.jsonl）；与单个 派代理 一样带项目目录等参数，执行方式=v2 的角色（如 modify_module）也能跑。
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

    backend, v2_backend = X.agent_backends(c)
    from tools.dslagent.v3 import modrun as MR
    results = R.parallel_dispatch_agents(组 or [], out_dir=c.out, backend=backend, parent_id=str(c.out),
                                         project=c.project, module_cmd=MR.base_cmd(c), v2_backend=v2_backend, mlog=c.M)
    cost = sum(r.get("cost") or 0.0 for r in results)
    with c.lock:
        c.module_cost += cost
    c.log("派代理", 事件="并行派代理", 条数=len(results), 花费=cost)
    c.guard()
    return results
