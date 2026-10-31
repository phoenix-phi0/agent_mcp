"""派代理：按 tools/dslagent/roles.zs 登记的角色调一次模型（roles.dispatch_agent 的 .zs 入口）。
假模型跑时走 ctx.M 的 backend（跟别的 v3 调用共用一份假回复），真跑时走 engines.call；花费并入 ctx 的花费上限。
v3 change2 / fix2 的 --impl-model / --brief 只作用于 modify_module：--impl-model 顶替它的默认模型；--brief 时先在 out/brief/ 写本模块实现简报
（v3/brief.section_for：只列本轮要改的函数），用环境变量 DSLAGENT_BRIEF_FILE 交给 v2 子进程（packs/dslproj 的 materials() / fix_input() 读）。
两个都没给 = 行为同旧。
返回 {result, status, reason, role, model, cost, calls, secs}。
例如 设 r = 派代理 角色=logic_check 任务=检查这份约定有没有逻辑漏洞 入参={"约定": 文本}
"""
import json
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
IMPL_ROLE = "modify_module"


def _brief_env(c, module, task):
    """--brief：写 out/brief/<模块>_<n>.json（{模块, 正文}）→ {DSLAGENT_BRIEF_FILE: 路径}；没有可附的内容 → None（不加这一节）。"""
    from tools.dslagent.v3 import brief as B
    try:
        text = B.section_for(c.project, module, task)
    except Exception as e:  # noqa: BLE001  简报只是提醒：生成出错记日志，照常派
        c.log("实现简报", 模块=module, 状态="出错", 原因=f"{type(e).__name__}: {e}"[:300])
        return None
    if not text.strip():
        c.log("实现简报", 模块=module, 状态="没有可附的内容")
        return None
    d = c.out / "brief"
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob(f"{module}_*.json"))) + 1
    f = d / f"{module}_{n}.json"
    f.write_text(json.dumps({"模块": module, "正文": text}, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / f"{module}_{n}.md").write_text(text + "\n", encoding="utf-8")
    c.log("实现简报", 模块=module, 状态="已附", 文件=str(f), 字数=len(text))
    return {B.ENV_FILE: str(f)}


def 派代理(角色: str, 任务: str = "", 入参: dict = None, 格式: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent import roles as R
    c = X.ctx()
    c.guard()

    backend, v2_backend = X.agent_backends(c, f"v3_agent_{角色}")
    from tools.dslagent.v3 import modrun as MR
    extra = {}
    if 角色 == IMPL_ROLE:
        if getattr(c, "impl_model", None):
            extra["model"] = c.impl_model
        module = str((入参 or {}).get("模块") or "").strip()
        if getattr(c, "brief", False) and module:
            env = _brief_env(c, module, 任务)
            if env:
                extra["env"] = env
    r = R.dispatch_agent(角色, 任务, 入参, 格式 or None, out_dir=c.out, backend=backend, parent_id=str(c.out),
                         project=c.project, module_cmd=MR.base_cmd(c), v2_backend=v2_backend, mlog=c.M,
                         v2_calls=getattr(c, "module_calls", None), **extra)
    with c.lock:
        c.module_cost += r.get("cost") or 0.0
    c.log("派代理", 角色=角色, 状态=r["status"], 原因=(r.get("reason") or "")[:200], 花费=r.get("cost"),
          **({"模型": r.get("model")} if extra.get("model") else {}))
    c.guard()
    return r
