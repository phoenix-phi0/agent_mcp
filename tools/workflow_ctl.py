# -*- coding: utf-8 -*-
"""编排的外部控制接口：每个任务节点怎么跑，由外部决定。

一次受控编排 = 过程记录 runs/<id>.json + 控制文件 runs/<id>.ctl（+ 后台日志 runs/<id>.log）。

进度只存在过程记录里。每次往下走，都把入口脚本（run.zs）从头再跑一遍：已有结果的
任务节点直接用记录里的结果（回放，不调模型），走到第一个没有结果的节点，按控制文件决定：

  1. submitted 里有这一步    → 用外部交来的结果，往下走
  2. go 里有这一步           → 用内置执行器跑（可带模型、角色卡覆盖）
  3. mode=auto，未命中 confirm_before 规则 → 按默认跑（models/roles 里的长期覆盖照样生效）
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
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_MODES = ("step", "auto")
_CARD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_RULE = re.compile(r"^[\w\-·.]{1,80}\*?$")
_CTL_LOCKS = threading.local()
_ACTOR = re.compile(r"(?:viewer|workflow_ctl|mcp:[\w.\-]{1,64})")


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


@contextmanager
def _ctl_lock(run):
    """锁独立文件；每个线程按规范路径计数，允许同线程嵌套调用写接口。"""
    trace = Path(run)
    if not trace.is_absolute():
        trace = ROOT / trace
    trace = trace.resolve()
    if ROOT not in trace.parents or trace.parent.name != "runs" or trace.suffix != ".json" or not trace.is_file():
        raise ControlError(f"不是编排记录：{run}")
    path = _side(trace, ".ctl.lock")
    held = getattr(_CTL_LOCKS, "held", None)
    if held is None:
        held = _CTL_LOCKS.held = {}
    if path in held:
        held[path] += 1
        try:
            yield
        finally:
            held[path] -= 1
        return
    # 不同线程分别 open，flock 因而会互斥；不能共享同一个文件描述符。
    with path.open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        held[path] = 1
        try:
            yield
        finally:
            del held[path]
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _rules(cfg, which):
    if which in ("before", "confirm_before"):
        return cfg.get("confirm_before", cfg.get("stop_roles", []))
    return cfg.get("confirm_after", [])


def _match(rules, names):
    for rule in rules:
        if any(name is not None and (name == rule or
               (rule.endswith("*") and name.startswith(rule[:-1]))) for name in names):
            return rule
    return None


def _check_rules(rules):
    if not isinstance(rules, (list, tuple)):
        raise ControlError(f"确认规则无效：{rules!r}")
    for rule in rules:
        if not isinstance(rule, str) or (rule != "*" and not _RULE.fullmatch(rule)):
            raise ControlError(f"确认规则无效：{rule!r}")


def _check_max_attempts(max_attempts):
    if max_attempts is not None and (type(max_attempts) is not int or not 1 <= max_attempts <= 50):
        raise ControlError(f"max_attempts 无效：{max_attempts!r}")


def _before_setting(stop_roles, confirm_before):
    if stop_roles is not None and confirm_before is not None and stop_roles != confirm_before:
        raise ControlError("两个是同一个设置，只给一个")
    rules = confirm_before if confirm_before is not None else stop_roles
    if rules is not None:
        _check_rules(rules)
        return list(rules)
    return None


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
        self.held = {}              # 第几步 → 最近一次等待结束后确认的结果
        self.carry = {}             # 第几步 → 以前失败或被打回的尝试（只保留，不回放结果）
        self.failed = self.carry    # 兼容旧调用方
        for e in (self.old or {}).get("events", []):
            if e.get("type") != "task" or "step" not in e:
                continue
            if rewind is not None and e["step"] >= rewind:
                continue
            if e.get("status") == "ok":
                self.replay[e["step"]] = e
            elif e.get("status") == "review":
                self.held[e["step"]] = e
            elif e.get("status") in ("error", "rejected"):
                self.carry.setdefault(e["step"], []).append(e)
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
        out["carry"] = self.carry.get(req["step"], [])
        out["failed"] = out["carry"]
        return out

    @staticmethod
    def _revised(event, revisions):
        """只补尚未应用的修订；始终保留模型最初交回的结果。"""
        existing = event.get("revisions", [])
        rev = max((r.get("rev", 0) for r in existing), default=0)
        newer = sorted((r for r in revisions if r.get("rev", 0) > rev), key=lambda r: r["rev"])
        if not newer:
            return {"result": event["result"], "revise": None}
        return {"result": newer[-1]["result"],
                "revise": {"result_model": event.get("result_model", event["result"]),
                           "revisions": existing + newer}}

    def _decide(self, req):
        k = req["step"]
        cfg = self._current()
        key = str(k)
        attempt = len(self.carry.get(k, [])) + 1
        meta = {"attempt": attempt, "max_attempts": cfg.get("max_attempts", 4),
                "notes": cfg.get("notes", {}).get(key, []), "confirm": [],
                "reason": None, "after": False, "revise": None}
        plan = {"model": cfg.get("models", {}).get(req["role"]),
                "role": cfg.get("roles", {}).get(req["role"])}
        go = cfg.get("go", {}).get(key, {})
        names = {req["name"], req["role"], go.get("role") or plan["role"]}
        meta["after"] = _match(_rules(cfg, "after"), names) is not None

        def after(use_role):
            matched = _match(_rules(cfg, "after"), {req["name"], req["role"], use_role})
            return {"after": matched is not None, "reason": "rule:" + matched if matched else None}

        def rejected_run(verdict, previous):
            use_role = verdict.get("role") or plan["role"]
            return {**meta, "action": "run", "by": "reject", "role": use_role,
                    "model": verdict.get("model") or plan["model"], "previous": previous,
                    "attempt": len(self.carry.get(k, [])) + 1, **after(use_role)}

        old = self.replay.get(k)
        if old is not None:
            was = (old.get("line"), old.get("name"), old.get("default_role", old.get("role")), old.get("task"))
            now = (req["line"], req["name"], req["role"], req["task"])
            if was != now:
                raise ControlError(f"第 {k} 步回放对不上（脚本或输入改过？）："
                                   f"记录是 {was[1]}/{was[2]}，现在是 {now[1]}/{now[2]}")
            return {**meta, "action": "replay", "event": old,
                    "notes": old.get("notes", []), "confirm": old.get("confirm", []),
                    **self._revised(old, cfg.get("revisions", {}).get(key, []))}
        held = self.held.get(k)
        verdict = cfg.get("after", {}).get(key, {})
        if held is not None:
            held_meta = {**meta, **after(held.get("role")), "attempt": held.get("attempt", 1), "event": held}
            if self.orders and verdict.get("attempt") == held.get("attempt", 1):
                confirm = {"phase": "after", "action": verdict.get("action"),
                           "actor": verdict.get("actor", "workflow_ctl"), "at": verdict.get("at")}
                if verdict.get("action") == "approve":
                    revised = self._revised(held, cfg.get("revisions", {}).get(key, []))
                    confirm["revised"] = revised["revise"] is not None
                    return {**held_meta, "action": "release", **revised, "confirm": [confirm]}
                if verdict.get("action") == "reject":
                    note = next((n for n in reversed(meta["notes"]) if n.get("kind") == "reject"), {})
                    rejected = {**held, "status": "rejected",
                                "confirm": held.get("confirm", []) + [confirm],
                                "reject": {"text": note.get("text", ""), "actor": confirm["actor"],
                                           "at": confirm["at"], "next_role": verdict.get("role"),
                                           "next_model": verdict.get("model")}}
                    self.carry.setdefault(k, []).append(rejected)
                    del self.held[k]
                    return rejected_run(verdict, held["result"])
            return {**held_meta, "action": "hold"}
        if not self.orders:
            reason = "error" if (self.old or {}).get("status") == "error" else "interrupted"
            return {**meta, "action": "wait", "model": cfg.get("models", {}).get(req["role"]),
                    "role": cfg.get("roles", {}).get(req["role"]), "reason": reason}
        if key in cfg.get("submitted", {}):
            # submitted 继续存原结果，来源从既有 history 取，兼容旧控制文件的形状。
            submitted = next((h for h in reversed(cfg.get("history", []))
                              if h.get("op") == "submit" and h.get("step") == k), {})
            actor = submitted.get("actor", "workflow_ctl")
            return {**meta, "action": "result", "result": cfg["submitted"][key], "actor": actor, "after": False,
                    "confirm": [{"phase": "before", "action": "submit", "actor": actor,
                                 "at": submitted.get("at") or _stamp()}]}
        if verdict.get("action") == "reject" and verdict.get("attempt") == attempt - 1:
            rejected = next((e for e in reversed(self.carry.get(k, [])) if e.get("status") == "rejected"), None)
            if rejected is not None:
                return rejected_run(verdict, rejected["result"])
        if key in cfg.get("go", {}):
            if "attempt" not in go or go["attempt"] == attempt:
                # 历史说明继续带进提示词；确认动作只记本次尝试新追加的说明。
                confirm = [{"phase": "before", "action": "note", "actor": n["actor"], "at": n["at"]}
                           for n in meta["notes"] if n.get("kind") == "add" and n.get("attempt") == attempt]
                return {**meta, "action": "run", "by": "execute",
                        "model": go.get("model") or plan["model"], "role": go.get("role") or plan["role"],
                        "confirm": confirm + [{"phase": "before", "action": "run", "role": go.get("role"),
                                     "model": go.get("model"), "actor": go.get("actor", "workflow_ctl"),
                                     "at": go.get("at") or _stamp()}],
                        **after(go.get("role") or plan["role"])}
        matched = _match(_rules(cfg, "before"), names)
        if cfg.get("mode") == "step" or self.force_step:
            return {**meta, "action": "wait", "reason": "step", **plan}
        if matched is not None:
            return {**meta, "action": "wait", "reason": "rule:" + matched, **plan}
        return {**meta, "action": "run", "by": "auto", **plan, **after(go.get("role") or plan["role"])}


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
    with _ctl_lock(trace):
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
    """去掉 >= keep_below 步的 submitted/go/notes/after/revisions，免得回退后旧指令和说明又生效。"""
    for key in ("submitted", "go", "notes", "after", "revisions"):
        if key in ("after", "revisions") and key not in cfg:
            continue
        cfg[key] = {k: v for k, v in cfg.get(key, {}).items() if int(k) < keep_below}


def _check_note(note):
    if note is None:
        return
    if not isinstance(note, str) or not note.strip():
        raise ControlError("说明必须是非空字符串")
    if len(note) > 4000:
        raise ControlError("说明最多 4000 字")
    try:
        note.encode("utf-8")
    except UnicodeEncodeError as e:
        raise ControlError("说明必须是有效的 UTF-8 字符串") from e


def _check_actor(actor):
    if not isinstance(actor, str) or not _ACTOR.fullmatch(actor):
        raise ControlError(f"来源无效：{actor!r}")


def _check_model(model):
    if model is None:
        return None
    from tools import config
    # parse_model 对裸名字很宽容（会当别名或默认模型），外部覆盖一律要求写全「通道:提供方/模型」
    if not isinstance(model, str) or ":" not in model or "/" not in model:
        raise ControlError(f"模型名无效：{model}（要写全，如 cli:goose/glm-5.3）")
    try:
        model.encode("utf-8")
        config.parse_model(model)
    except Exception as e:
        raise ControlError(f"模型名无效：{model}（{e}）") from e
    return model


def _check_card(card):
    if card is not None and (not isinstance(card, str) or not _CARD.fullmatch(card)):
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

def start(workdir, entry="run.zs", mode="step", stop_roles=None, models=None, roles=None,
          wait=False, client=None, confirm_before=None, actor="workflow_ctl",
          confirm_after=None, max_attempts=None):
    _check_actor(actor)
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
    before = _before_setting(stop_roles, confirm_before)
    if confirm_after is not None:
        _check_rules(confirm_after)
    _check_max_attempts(max_attempts)
    if before is None:
        before = []
    cfg = {"entry": entry, "mode": mode, "confirm_before": before, "stop_roles": before,
           "confirm_after": list(confirm_after or []), "max_attempts": 4 if max_attempts is None else max_attempts,
           "models": dict(models or {}),
           "roles": dict(roles or {}), "submitted": {}, "go": {}, "worker": None, "history": []}
    _log(cfg, "start", mode=mode, actor=actor,
         confirm_after=cfg["confirm_after"], max_attempts=cfg["max_attempts"])
    # 第一遍只走到第一个节点就停，不调模型；有了记录文件再按 mode 往下走
    trace = _advance(None, cfg, client, force_step=True, workdir=wd)
    if trace is None:
        raise ControlError("入口脚本跑完了，没有执行编排")
    with _ctl_lock(trace):
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
        row["attempt"] = e.get("attempt", 1)
        if "actor" in e:
            row["actor"] = e["actor"]
        else:
            # 模型事件的结束后裁决来源保存在 confirm；普通开始前确认不补来源。
            after = next((c for c in reversed(e.get("confirm", [])) if c.get("phase") == "after"), None)
            if after is not None and "actor" in after:
                row["actor"] = after["actor"]
        row["revised"] = bool(e.get("revisions"))
        for k in ("default_role", "source", "model_override", "error", "actor", "confirm"):
            if e.get(k):
                row[k] = e[k]
        if detail and "result" in e:
            row["result"] = e["result"]
        steps.append(row)
    out = {"run": _rel(p), "workflow": t.get("workflow"), "status": st, "error": t.get("error"),
           "mode": cfg.get("mode"), "confirm_before": _rules(cfg, "before"),
           "stop_roles": _rules(cfg, "before"), "confirm_after": _rules(cfg, "confirm_after"),
           "max_attempts": cfg.get("max_attempts", 4),
           "models": cfg.get("models", {}), "roles": cfg.get("roles", {}),
           "worker_alive": alive, "resumes": t.get("resumes", 0), "steps": steps}
    pend = t.get("pending") if t.get("status") == "waiting" else None
    if pend:
        pend = {"phase": "before", "reason": "step", "attempt": 1, **pend}
        out["pending"] = pend if detail else {k: v for k, v in pend.items() if k not in ("system", "prompt", "schema")}
    return out


def _check_result(pend, result):
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
    try:
        json.dumps(result, ensure_ascii=False).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError) as e:
        raise ControlError("结果必须是有效的 UTF-8 JSON 对象") from e
    return result


def _check_phase(pend, phase, attempt=None):
    if pend.get("phase", "before") != phase:
        if phase == "before":
            raise ControlError("这一步在等结束后确认，用 approve / reject")
        raise ControlError("这一步在等开始前确认，用 execute / submit")
    if attempt is not None and attempt != pend.get("attempt", 1):
        raise ControlError(f"结果已经换了（现在是第 {pend.get('attempt', 1)} 次），刷新后再确认")


def submit(run, result, step=None, wait=None, client=None, actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, t = _open(run)
        _idle(cfg)
        pend = _pending(_settle(p, cfg, t, client), step)
        _check_phase(pend, "before")
        result = _check_result(pend, result)
        _prune(cfg, pend["step"])
        cfg["submitted"][str(pend["step"])] = result
        _log(cfg, "submit", step=pend["step"], actor=actor)
        _dump(cf, cfg)
    _continue(p, cfg["mode"] == "step" if wait is None else wait, client)
    return status(p)


def execute(run, model=None, role=None, step=None, wait=False, client=None, note=None, actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, t = _open(run)
        _idle(cfg)
        # 已经停下时先检查阶段；恢复旧记录前先拒绝非法参数，避免失败请求改写记录。
        if t.get("status") == "waiting":
            _check_phase(_pending(t, step), "before")
        elif (t.get("pending") or {}).get("phase") == "after":
            _check_phase(t["pending"], "before")
        _check_model(model)
        _check_card(role)
        _check_note(note)
        t = _settle(p, cfg, t, client)
        pend = _pending(t, step)
        _check_phase(pend, "before")
        key = str(pend["step"])
        attempt = 1 + sum(e.get("type") == "task" and e.get("step") == pend["step"]
                          and e.get("status") in ("error", "rejected") for e in t.get("events", []))
        notes = list(cfg.get("notes", {}).get(key, []))
        _prune(cfg, pend["step"])
        at = _stamp()
        if note is not None:
            notes.append({"kind": "add", "text": note, "attempt": attempt, "actor": actor, "at": at})
        if notes:
            cfg["notes"][key] = notes
        cfg["go"][key] = {"model": model, "role": role, "attempt": attempt, "actor": actor, "at": at}
        _log(cfg, "execute", step=pend["step"], model=model, role=role, actor=actor)
        _dump(cf, cfg)
    _continue(p, wait, client)
    return status(p)


def approve(run, result=None, note=None, step=None, attempt=None, wait=None, client=None,
            actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, t = _open(run)
        _idle(cfg)
        pend = _pending(_settle(p, cfg, t, client), step)
        _check_phase(pend, "after", attempt)
        if result is not None:
            result = _check_result(pend, result)
        _check_note(note)
        key = str(pend["step"])
        at = _stamp()
        current_attempt = pend.get("attempt", 1)
        if result is not None and (json.dumps(result, sort_keys=True, ensure_ascii=False)
                                   != json.dumps(pend["result"], sort_keys=True, ensure_ascii=False)):
            revisions = cfg.setdefault("revisions", {}).setdefault(key, [])
            revisions.append({"rev": max((r["rev"] for r in revisions), default=0) + 1,
                              "kind": "approve", "attempt": current_attempt, "result": result,
                              "actor": actor, "at": at, "note": note})
        cfg.setdefault("after", {})[key] = {"attempt": current_attempt, "action": "approve",
                                             "actor": actor, "at": at}
        _log(cfg, "approve", step=pend["step"], attempt=current_attempt, actor=actor)
        _dump(cf, cfg)
    _continue(p, cfg["mode"] == "step" if wait is None else wait, client)
    return status(p)


def reject(run, note, model=None, role=None, step=None, attempt=None, wait=False, client=None,
           actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, t = _open(run)
        _idle(cfg)
        pend = _pending(_settle(p, cfg, t, client), step)
        _check_phase(pend, "after", attempt)
        if not isinstance(note, str) or not note.strip():
            raise ControlError("打回要写意见")
        _check_note(note)
        current_attempt = pend.get("attempt", 1)
        maximum = cfg.get("max_attempts", 4)
        if current_attempt >= maximum:
            raise ControlError(f"第 {pend['step']} 步已经跑了 {current_attempt} 次（上限 {maximum}），"
                               "不能再打回：可以改了再通过，或者 configure(max_attempts=…) 调高")
        _check_model(model)
        _check_card(role)
        key = str(pend["step"])
        at = _stamp()
        cfg.setdefault("notes", {}).setdefault(key, []).append(
            {"kind": "reject", "text": note, "attempt": current_attempt, "actor": actor, "at": at})
        cfg.setdefault("after", {})[key] = {"attempt": current_attempt, "action": "reject",
                                             "model": model, "role": role, "actor": actor, "at": at}
        _log(cfg, "reject", step=pend["step"], attempt=current_attempt, model=model, role=role, actor=actor)
        _dump(cf, cfg)
    _continue(p, wait, client)
    return status(p)


def pause(run, actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, _ = _open(run)
        cfg["mode"] = "step"
        _log(cfg, "pause", actor=actor)
        _dump(cf, cfg)
    return status(p)


def resume(run, wait=False, client=None, actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, t = _open(run)
        cfg["mode"] = "auto"
        _log(cfg, "resume", actor=actor)
        _dump(cf, cfg)
    st = status(p)["status"]
    if not _alive(cfg) and st in ("waiting", "interrupted", "error", "aborted"):
        _continue(p, wait, client)
    return status(p)


def configure(run, stop_roles=None, models=None, roles=None, confirm_before=None, actor="workflow_ctl",
              confirm_after=None, max_attempts=None):
    """None = 不改；传 {} / [] = 清空。只影响还没跑的节点。"""
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, _ = _open(run)
        _check_maps(models, roles)
        before = _before_setting(stop_roles, confirm_before)
        if confirm_after is not None:
            _check_rules(confirm_after)
        _check_max_attempts(max_attempts)
        if before is not None:
            cfg["confirm_before"] = before
            cfg["stop_roles"] = before
        if confirm_after is not None:
            cfg["confirm_after"] = list(confirm_after)
        if max_attempts is not None:
            cfg["max_attempts"] = max_attempts
        if models is not None:
            cfg["models"] = dict(models)
        if roles is not None:
            cfg["roles"] = dict(roles)
        _log(cfg, "configure", stop_roles=before, confirm_before=before, models=models, roles=roles,
             confirm_after=confirm_after, max_attempts=max_attempts, actor=actor)
        _dump(cf, cfg)
    return status(p)


def rewind(run, step, client=None, actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
        p, cf, cfg, _ = _open(run)
        _idle(cfg)
        step = int(step)
        if step < 1:
            raise ControlError("step 从 1 开始")
        _prune(cfg, step)
        _log(cfg, "rewind", step=step, actor=actor)
        _dump(cf, cfg)
    _advance(p, cfg, client, rewind=step, force_step=True)
    return status(p)


def abort(run, actor="workflow_ctl"):
    _check_actor(actor)
    with _ctl_lock(run):
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
        t.update(status="aborted", error=f"外部中止（{actor}）", finished=_stamp(), updated=_stamp())
        _dump(p, t)
        _log(cfg, "abort", actor=actor)
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
