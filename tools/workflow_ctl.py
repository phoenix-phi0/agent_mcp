# -*- coding: utf-8 -*-
"""编排的外部控制接口：每个任务节点怎么跑，由外部决定。

一次受控编排 = 过程记录 runs/<id>.json + 控制文件 runs/<id>.ctl（+ 后台日志 runs/<id>.log）。

进度只存在过程记录里。每次往下走，都把入口脚本（run.zs）从头再跑一遍：已有结果的
任务节点直接用记录里的结果（回放，不调模型），走到第一个没有结果的节点，按控制文件决定：

  1. submitted 里有这一步    → 用外部交来的结果，往下走
  2. go 里有这一步           → 用内置执行器跑（可带模型、角色卡覆盖）
  3. mode=auto，角色不在 stop_roles → 按默认跑（models/roles 里的长期覆盖照样生效）
  4. 否则停下：状态 waiting，pending 里是这一步的完整请求（角色卡、模型、系统提示、提示词）

所以进程被杀、机器重启都不丢进度。暂停 = 把 mode 改回 step：正在跑的那一步跑完就停。
条件、跳转次数、遍历位置只取决于变量和各步结果，回放出来的状态和原来一样；回放时逐步
核对行号、节点名、角色、任务，对不上（脚本或输入改过）就报错，不会悄悄走偏。

注意：回放和 rewind 只管记录里的结果，agent 在 work/ 下写的文件不会跟着撤回。

接口（都返回 status() 的摘要）：
  start(workdir, entry, mode, stop_roles, models, roles)   开始，停在第一个节点（auto 则后台往下跑）
  status(run, detail)        当前状态；detail=True 带每步结果和 pending 的系统提示/提示词
  submit(run, result)        交回当前这一步的结果（外部自己执行的）
  execute(run, model, role)  用内置执行器跑当前这一步，可临时换模型/角色卡（后台）
  pause(run) / resume(run)   改 mode；resume 在停着时顺带往下跑（后台）
  configure(run, stop_roles, models, roles)   长期覆盖：某角色以后都用哪个模型 / 哪张卡
  rewind(run, step)          丢掉第 step 步及以后的结果，停在第 step 步
  abort(run)                 杀掉后台进程，状态 aborted
  list_runs(workdir)

控制文件只由这些接口函数写；后台进程只读它。
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_MODES = ("step", "auto")
_CARD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class WorkflowPause(BaseException):
    """停在一个节点上等外部。继承 BaseException：不被 DSL 引擎当成普通错误包装。"""
    wf_pause = True


class ControlError(Exception):
    pass


def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dump(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _side(trace, ext):
    trace = Path(trace)
    return trace.with_name(trace.name[:-len(".json")] + ext)


class _Control:
    """交给 _workflow.run 的控制器（engine._wf_control）。"""

    def __init__(self, cfg, trace=None, rewind=None, force_step=False, orders=True):
        self.cfg = cfg
        self.force_step = force_step
        # orders=False：不理 submitted/go 里的旧指令，只回放并停下（_settle 用，免得重放上次的 execute）
        self.orders = orders
        self.path = Path(trace) if trace else None
        self.old = _load(trace) if trace else None
        self.replay = {}
        self.failed = {}            # 第几步 → 以前失败的尝试（保留在记录里，不回放结果）
        for e in (self.old or {}).get("events", []):
            if e.get("type") != "task" or "step" not in e:
                continue
            if rewind is not None and e["step"] >= rewind:
                continue
            if e.get("status") == "ok":
                self.replay[e["step"]] = e
            elif e.get("status") == "error":
                self.failed.setdefault(e["step"], []).append(e)
        self.claimed = False

    def claim(self):
        if self.claimed:
            raise ControlError("一个入口脚本里只能有一次受控的编排执行")
        self.claimed = True

    def attach(self, trace):
        if trace.path is None:
            raise ControlError("空跑不能受外部控制")
        self.path = trace.path

    def pause(self):
        return WorkflowPause()

    def _current(self):
        f = _side(self.path, ".ctl") if self.path else None
        return _load(f) if f and f.is_file() else self.cfg

    def decide(self, req):
        out = self._decide(req)
        out["failed"] = self.failed.get(req["step"], [])
        return out

    def _decide(self, req):
        k = req["step"]
        old = self.replay.get(k)
        if old is not None:
            was = (old.get("line"), old.get("name"), old.get("default_role", old.get("role")), old.get("task"))
            now = (req["line"], req["name"], req["role"], req["task"])
            if was != now:
                raise ControlError(f"第 {k} 步回放对不上（脚本或输入改过？）："
                                   f"记录是 {was[1]}/{was[2]}，现在是 {now[1]}/{now[2]}")
            return {"action": "replay", "event": old}
        cfg = self._current()
        key = str(k)
        if not self.orders:
            return {"action": "wait", "model": cfg.get("models", {}).get(req["role"]),
                    "role": cfg.get("roles", {}).get(req["role"])}
        if key in cfg.get("submitted", {}):
            return {"action": "result", "result": cfg["submitted"][key]}
        plan = {"model": cfg.get("models", {}).get(req["role"]),
                "role": cfg.get("roles", {}).get(req["role"])}
        if key in cfg.get("go", {}):
            go = cfg["go"][key]
            return {"action": "run", "by": "execute",
                    "model": go.get("model") or plan["model"], "role": go.get("role") or plan["role"]}
        if (not self.force_step and cfg.get("mode") == "auto"
                and req["role"] not in cfg.get("stop_roles", [])):
            return {"action": "run", "by": "auto", **plan}
        return {"action": "wait", **plan}


# ---- 内部：推进、后台进程 ----

def _advance(trace, cfg, client=None, rewind=None, force_step=False, workdir=None, orders=True):
    """从头跑一遍入口脚本，回放到第一个没结果的节点，按控制文件决定。返回记录路径。"""
    from tools.dsl import DSLEngine
    ctl = _Control(cfg, trace, rewind, force_step, orders)
    wd = Path(workdir) if workdir else Path(ctl.old["workdir"])
    kw = dict(workdir=wd, verbs_root=ROOT / "verbs", verbose=False)
    if client is not None:
        kw["client"] = client
    engine = DSLEngine(**kw)
    engine._wf_control = ctl
    try:
        engine.run_file(cfg["entry"])
    except WorkflowPause:
        pass
    except Exception:
        if ctl.path is None:      # 编排还没开始就错了：没有记录可看，原样抛
            raise
    return ctl.path


def _alive(cfg):
    pid = cfg.get("worker")
    if not pid:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    state = stat.rsplit(")", 1)[-1].split()[0]
    return state != "Z" and b"workflow_ctl" in cmd


def _spawn(trace):
    cf = _side(trace, ".ctl")
    t = _load(trace)
    t.update(status="running", updated=_stamp())
    _dump(trace, t)
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    with open(_side(trace, ".log"), "a", encoding="utf-8") as log:
        log.write(f"\n=== {_stamp()} advance\n")
        log.flush()
        proc = subprocess.Popen([sys.executable, "-m", "tools.workflow_ctl", "advance", str(trace)],
                                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
    cfg = _load(cf)
    cfg["worker"] = proc.pid
    _dump(cf, cfg)


def _continue(trace, wait, client):
    if wait or client is not None:
        _advance(trace, _load(_side(trace, ".ctl")), client)
    else:
        _spawn(trace)


def _open(run):
    p = Path(run)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    if ROOT not in p.parents or p.parent.name != "runs" or p.suffix != ".json" or not p.is_file():
        raise ControlError(f"不是编排记录：{run}")
    cf = _side(p, ".ctl")
    if not cf.is_file():
        raise ControlError(f"这份记录不是受控编排（没有 {cf.name}）：{run}")
    return p, cf, _load(cf), _load(p)


def _idle(cfg):
    if _alive(cfg):
        raise ControlError("后台还在跑，先等它停下（pause 后等当前这步跑完）或 abort")


def _settle(p, cfg, t, client=None):
    """出错、被打断、中止过的记录：先回放一遍停到第一个没结果的节点，再接受 submit/execute。"""
    if t.get("status") in ("error", "interrupted", "aborted", "running") and not _alive(cfg):
        _advance(p, cfg, client, force_step=True, orders=False)
        return _load(p)
    return t


def _pending(t, step):
    pend = t.get("pending")
    if t.get("status") != "waiting" or not pend:
        raise ControlError(f"现在没有停在节点上（状态 {t.get('status')}）")
    if step is not None and int(step) != pend["step"]:
        raise ControlError(f"现在停在第 {pend['step']} 步，不是第 {step} 步")
    return pend


def _log(cfg, op, **kw):
    cfg.setdefault("history", []).append({"at": _stamp(), "op": op, **kw})


def _prune(cfg, keep_below):
    """去掉 >= keep_below 步的 submitted/go，免得回退后旧指令又生效。"""
    for key in ("submitted", "go"):
        cfg[key] = {k: v for k, v in cfg.get(key, {}).items() if int(k) < keep_below}


def _check_model(model):
    if model is None:
        return None
    from tools import config
    # parse_model 对裸名字很宽容（会当别名或默认模型），外部覆盖一律要求写全「通道:提供方/模型」
    if not isinstance(model, str) or ":" not in model or "/" not in model:
        raise ControlError(f"模型名无效：{model}（要写全，如 cli:goose/glm-5.3）")
    try:
        config.parse_model(model)
    except Exception as e:
        raise ControlError(f"模型名无效：{model}（{e}）") from e
    return model


def _check_card(card):
    if card is not None and not _CARD.fullmatch(card):
        raise ControlError(f"角色卡名无效：{card}")
    return card


def _check_maps(models, roles):
    for k, v in (models or {}).items():
        _check_card(k)
        _check_model(v)
    for k, v in (roles or {}).items():
        _check_card(k)
        _check_card(v)


def _rel(p):
    p = Path(p)
    return str(p.relative_to(ROOT)) if ROOT in p.parents else str(p)


# ---- 接口 ----

def start(workdir, entry="run.zs", mode="step", stop_roles=(), models=None, roles=None,
          wait=False, client=None):
    wd = Path(workdir)
    if not wd.is_absolute():
        wd = ROOT / wd
    wd = wd.resolve()
    if ROOT not in wd.parents:
        raise ControlError(f"工作目录要在项目里：{workdir}")
    ep = (wd / entry).resolve()
    if wd not in ep.parents:
        raise ControlError(f"入口脚本越出工作目录：{entry}")
    if not (wd / entry).is_file():
        raise ControlError(f"入口脚本不存在：{wd / entry}")
    if mode not in _MODES:
        raise ControlError(f"mode 只能是 {_MODES}")
    _check_maps(models, roles)
    for r in stop_roles:
        _check_card(r)
    cfg = {"entry": entry, "mode": mode, "stop_roles": list(stop_roles), "models": dict(models or {}),
           "roles": dict(roles or {}), "submitted": {}, "go": {}, "worker": None, "history": []}
    _log(cfg, "start", mode=mode)
    # 第一遍只走到第一个节点就停，不调模型；有了记录文件再按 mode 往下走
    trace = _advance(None, cfg, client, force_step=True, workdir=wd)
    if trace is None:
        raise ControlError("入口脚本跑完了，没有执行编排")
    _dump(_side(trace, ".ctl"), cfg)
    if mode == "auto" and _load(trace).get("status") == "waiting":
        _continue(trace, wait, client)
    return status(trace)


def status(run, detail=False):
    p = Path(run)
    if not p.is_absolute():
        p = ROOT / p
    p, cf, cfg, t = _open(p)
    alive = _alive(cfg)
    st = t.get("status")
    if st == "running" and not alive:
        st = "interrupted"          # 记录说在跑，进程却没了：被杀或机器重启，resume 可接着走
    steps = []
    for e in t.get("events", []):
        if e.get("type") != "task":
            continue
        row = {k: e.get(k) for k in ("step", "name", "role", "status", "model", "seconds")}
        for k in ("default_role", "source", "model_override", "error"):
            if e.get(k):
                row[k] = e[k]
        if detail and "result" in e:
            row["result"] = e["result"]
        steps.append(row)
    out = {"run": _rel(p), "workflow": t.get("workflow"), "status": st, "error": t.get("error"),
           "mode": cfg.get("mode"), "stop_roles": cfg.get("stop_roles", []),
           "models": cfg.get("models", {}), "roles": cfg.get("roles", {}),
           "worker_alive": alive, "resumes": t.get("resumes", 0), "steps": steps}
    pend = t.get("pending") if t.get("status") == "waiting" else None
    if pend:
        out["pending"] = pend if detail else {k: v for k, v in pend.items() if k not in ("system", "prompt", "schema")}
    return out


def submit(run, result, step=None, wait=None, client=None):
    p, cf, cfg, t = _open(run)
    _idle(cfg)
    pend = _pending(_settle(p, cfg, t, client), step)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError as e:
            raise ControlError(f"结果不是 JSON：{e}") from e
    if not isinstance(result, dict):
        raise ControlError("结果必须是 JSON 对象")
    if pend.get("schema"):
        # 外部交的结果和模型用 submit 工具交的走同一个校验：流程里每一步的形状都是确定的
        from tools.wf_submit import validate
        bad = validate(pend["schema"], result)
        if bad:
            raise ControlError(f"结果不符合格式 {pend.get('format')}：" + "；".join(bad[:5]))
    _prune(cfg, pend["step"])
    cfg["submitted"][str(pend["step"])] = result
    _log(cfg, "submit", step=pend["step"])
    _dump(cf, cfg)
    _continue(p, cfg["mode"] == "step" if wait is None else wait, client)
    return status(p)


def execute(run, model=None, role=None, step=None, wait=False, client=None):
    p, cf, cfg, t = _open(run)
    _idle(cfg)
    _check_model(model)
    _check_card(role)
    pend = _pending(_settle(p, cfg, t, client), step)
    _prune(cfg, pend["step"])
    cfg["go"][str(pend["step"])] = {"model": model, "role": role}
    _log(cfg, "execute", step=pend["step"], model=model, role=role)
    _dump(cf, cfg)
    _continue(p, wait, client)
    return status(p)


def pause(run):
    p, cf, cfg, _ = _open(run)
    cfg["mode"] = "step"
    _log(cfg, "pause")
    _dump(cf, cfg)
    return status(p)


def resume(run, wait=False, client=None):
    p, cf, cfg, t = _open(run)
    cfg["mode"] = "auto"
    _log(cfg, "resume")
    _dump(cf, cfg)
    st = status(p)["status"]
    if not _alive(cfg) and st in ("waiting", "interrupted", "error", "aborted"):
        _continue(p, wait, client)
    return status(p)


def configure(run, stop_roles=None, models=None, roles=None):
    """None = 不改；传 {} / [] = 清空。只影响还没跑的节点。"""
    p, cf, cfg, _ = _open(run)
    _check_maps(models, roles)
    if stop_roles is not None:
        for r in stop_roles:
            _check_card(r)
        cfg["stop_roles"] = list(stop_roles)
    if models is not None:
        cfg["models"] = dict(models)
    if roles is not None:
        cfg["roles"] = dict(roles)
    _log(cfg, "configure", stop_roles=stop_roles, models=models, roles=roles)
    _dump(cf, cfg)
    return status(p)


def rewind(run, step, client=None):
    p, cf, cfg, _ = _open(run)
    _idle(cfg)
    step = int(step)
    if step < 1:
        raise ControlError("step 从 1 开始")
    _prune(cfg, step)
    _log(cfg, "rewind", step=step)
    _dump(cf, cfg)
    _advance(p, cfg, client, rewind=step, force_step=True)
    return status(p)


def abort(run):
    p, cf, cfg, t = _open(run)
    if _alive(cfg):
        pid = cfg["worker"]
        try:
            os.killpg(pid, signal.SIGTERM)
            for _ in range(50):
                if not _alive(cfg):
                    break
                time.sleep(0.1)
            else:
                os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        t = _load(p)
    for e in t.get("events", []):
        if e.get("type") == "task" and e.get("status") in ("running", "waiting"):
            e["status"] = "aborted"
    t.pop("pending", None)
    t.update(status="aborted", error="外部中止", finished=_stamp(), updated=_stamp())
    _dump(p, t)
    _log(cfg, "abort")
    _dump(cf, cfg)
    return status(p)


def list_runs(workdir):
    wd = Path(workdir)
    if not wd.is_absolute():
        wd = ROOT / wd
    out = []
    for cf in sorted((wd / "runs").glob("*.ctl")):
        trace = cf.with_name(cf.name[:-len(".ctl")] + ".json")
        if trace.is_file():
            s = status(trace)
            out.append({k: s.get(k) for k in ("run", "workflow", "status", "mode")}
                       | {"step": (s.get("pending") or {}).get("step"), "done_steps": sum(
                           1 for x in s["steps"] if x["status"] == "ok")})
    return out


def _main(argv):
    if len(argv) == 2 and argv[0] == "advance":
        trace = Path(argv[1])
        _advance(trace, _load(_side(trace, ".ctl")))
        print(f"{_stamp()} 停下：{_load(trace).get('status')}", flush=True)
        return 0
    print("用法：python -m tools.workflow_ctl advance <runs/xxx.json>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
