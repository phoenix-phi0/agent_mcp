"""v3 动词共用：取运行上下文、把致命错误变成「终止」。"""
from tools.dsl_core import ScriptHalt


def ctx():
    from tools.dslagent.v3.core import ctx_of
    return ctx_of()


def fail(reason):
    raise ScriptHalt("失败", str(reason), "")


def numbered(problems):
    return "\n".join(f"{i}. {p}" for i, p in enumerate(problems, 1))


def agent_backends(c, tag=None):
    """派代理 / 并行派代理 共用：→ (backend, v2_backend)；tag 缺省按模型 / 角色名拼。假模型跑时 v2_backend 不起子进程，用假回复当 v2 的结果（回复非空 = 验收通过）；真跑为 None。"""
    def backend(spec, system, user, timeout):
        if c.M.real:
            from tools.dslagent import engines as EG
            return EG.call(spec, system, user, timeout)
        return c.M.backend(system, user, tag or f"v3_agent_{spec['spec']}", timeout, model=spec["spec"])

    v2_backend = None
    if not c.M.real:
        def v2_backend(spec, req):
            r = c.M.backend("", req["task"], tag or f"v3_agent_{req['role']}", req["timeout"], model=spec)
            r = r if isinstance(r, dict) else {"text": str(r)}
            return {"fixed": bool(not r.get("reason") and (r.get("text") or "").strip()), "stop": r.get("reason") or "",
                    "cost": r.get("cost") or 0.0, "sec": r.get("sec") or 0.0, "calls": 1, "started": not r.get("reason"), "files": []}
    return backend, v2_backend


def top_or_none(c):
    """全量回归 / 接口冒烟 用：没有 plan/top.zs → None（调用方跳过）；top.zs 在但读不过 / 检查不过 → 终止 失败（不能当没有代码）。"""
    from tools.dslagent.v3 import planning as PL
    if not c.top_path().is_file():
        return None
    try:
        return PL.current_top(c)
    except ValueError as e:
        fail(f"plan/top.zs 有问题，检查没法跑：{e}")
