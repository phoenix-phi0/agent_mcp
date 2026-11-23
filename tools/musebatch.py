# -*- coding: utf-8 -*-
"""MuseBatch：流程里交给 Muse 的步骤，用和 mbatch 一样的方式排队、认领、写回。

和 mbatch 一样只存任务、不起执行器：编排流程停在 model=muse 的卡上时（见 workflow_ctl._advance），
post() 在 ~/.musebatch/jobs/<job_id>/ 建一个 job.json，状态 queued。本机的轮询（同 mbatch-watchdog，
看这个目录）一有 queued 就唤醒 Muse；Muse claim → 照提示词做 → set_task 写回。

和 mbatch 不同的地方：
  - 一个任务就是流程里的一步（job.json 里多一个 flow：run、step、attempt、card、format），只有一条 task。
    提示词是这一步的完整请求：角色说明和技能、工作目录、任务、要交的 JSON Schema。cwd 是这一步的项目目录。
  - set_task(job_id, 0, output=结果 JSON) 当场按这一步的格式校验：
      不合格 → 抛 MuseBatchError，逐条列出问题，什么都不写，任务还是 running：改了再调；
      合格   → 交进流程（来源 mcp:muse），这条 done、整批 done，流程在后台接着往下走。不用再调 finish。
    status="failed" 写失败原因：整批 failed，流程停在这一步不动（人可以换卡、换模型）。
  - claim 前、post 时都核对流程还在不在等这一步：别人交了、退回了、中止了，就把任务取消（claim 报「不用做了」）。

## 对外接口（跟 mbatch 对得上）

    from tools import musebatch as mb
    mb.describe()                    # 概况
    mb.queued()                      # 排队等认领的（轮询用）
    mb.jobs() / mb.status(id)        # 最近的任务 / 一个任务的详情
    mb.claim(id)                     # 认领：queued -> running（流程已经不等了：取消并报错）
    mb.set_task(id, 0, output="…")   # 写回结果：当场校验，合格就交进流程
    mb.set_task(id, 0, error="…", status="failed")
    mb.finish(id) / mb.cancel(id) / mb.reclaim(id) / mb.reclaim_stuck()
    mb.post(run)                     # 流程这边调：停在 Muse 的步骤上就投一条（同一步同一次只投一条）

MCP（agent_mcp_aliyun 的 tool_call，同 mbatch.*）：musebatch.queued / claim / set_task / status / … 都在白名单里。
命令行：python -m tools.musebatch <queued|jobs|status|claim|set_task|cancel|reclaim_stuck> …
"""
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = Path(os.environ.get("MUSEBATCH_HOME") or Path.home() / ".musebatch" / "jobs")
ACTIVE = ("queued", "running")


class MuseBatchError(Exception):
    pass


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _dir(job_id):
    return JOBS / job_id


def _load(job_id):
    try:
        return json.loads((_dir(job_id) / "job.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MuseBatchError(f"没有这个任务：{job_id}") from None


def _save(d):
    f = _dir(d["id"]) / "job.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


def _all():
    if not JOBS.is_dir():
        return []
    out = []
    for jd in sorted(JOBS.iterdir(), reverse=True):
        if (jd / "job.json").is_file():
            out.append(_load(jd.name))
    return out


def _brief(d):
    done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
    return {"id": d["id"], "name": d["name"], "status": d["status"], "progress": f"{done}/{len(d['tasks'])}",
            "created": d["created"], "flow": d.get("flow")}


def _cancel(d, why):
    d["status"] = "cancelled"
    d["finished"] = _now()
    d["note"] = why
    for t in d["tasks"]:
        if t["status"] in ("pending", "running"):
            t["status"] = "cancelled"
    _save(d)


def _still_waiting(d):
    """流程还停在这个任务那一步、那一次上吗。不在：返回原因。"""
    from tools import muse_flow as mf
    f = d["flow"]
    try:
        mf.waiting(ROOT / f["run"], f["step"], f["attempt"])
        return None
    except mf.MuseFlowError as e:
        return str(e)


# ---- 投任务（流程这边）----

def _prompt(req, job_id):
    py = sys.executable
    parts = [req.get("system") or "", ""]
    if req.get("cwd"):
        env = f"【工作环境】这一步在阿里云这台机器的项目目录 {req['cwd']} 里做：读写的文件都在这个目录里，不要改目录以外的东西。"
        if req.get("python"):
            env += f"项目用自己的虚拟环境：命令里写 {req['python']}（如 {req['python']} -m pytest）。"
        if req.get("test_cmd"):
            env += f"这次流程的测试命令（在项目目录里跑）：{req['test_cmd']}。"
        parts += [env, ""]
    from tools.wf_submit import shape_hint
    hint = shape_hint(req["schema"]).replace("submit 的参数", "写回的结果") if req.get("schema") else ""
    parts += [req.get("prompt") or "", "",
              f"【怎么交】{hint}这是编排运行 {req['run']} 的第 {req['step']} 步（{req.get('name') or ''}，第 {req['attempt']} 次）。"
              f"做完后把结果（一个按上面 JSON Schema 的 JSON 对象）写回：musebatch.set_task(\"{job_id}\", 0, output=<结果 JSON 文本>)，"
              f"命令行是 cd {ROOT} && {py} -m tools.musebatch set_task {job_id} 0 --file <结果文件>。"
              f"不合格会当场报错、逐条列出问题，什么都没写：照着改了再写回。合格就交进流程了，不用再调 finish。"
              f"做不了就写 status=\"failed\" 和原因（命令行加 --failed --error 原因）。"]
    return "\n".join(parts).strip()


def post(run):
    """流程停在等 Muse 的步骤上：投一条任务（同一步同一次已经有没取消的就不投），返回 job_id 或 None。
    顺手把流程已经不等了的 queued / running 任务取消掉。"""
    from tools import muse_flow as mf
    sweep()
    try:
        req = mf.request(run)
    except mf.MuseFlowError:
        return None
    key = {"run": req["run"], "step": req["step"], "attempt": req["attempt"]}
    for d in _all():
        f = d.get("flow") or {}
        if d["status"] != "cancelled" and {k: f.get(k) for k in key} == key:
            return None
    from tools.zcode_tool import UnsafeWorkdirError, check_workdir
    try:
        cwd = check_workdir(req.get("cwd") or str(ROOT))
    except UnsafeWorkdirError as e:
        raise MuseBatchError(f"cwd 不能用：{e}") from None
    now = datetime.now()
    job_id = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}" + uuid.uuid4().hex[:4]
    _dir(job_id).mkdir(parents=True)
    d = {"id": job_id, "name": f"流程 {Path(req['run']).stem} 第{req['step']}步 {req.get('name') or ''}".strip(),
         "mode": "isolated", "cwd": cwd, "status": "queued", "created": _now(), "started": None, "finished": None,
         "pid": None, "executor": "muse", "claimed_by": None, "claimed_at": None,
         "options": {"executor": "muse"},
         "flow": dict(key, card=req.get("card"), format=req.get("format"), name=req.get("name")),
         "tasks": [{"prompt": _prompt(req, job_id), "outfile": "", "status": "pending", "output": "", "error": "",
                    "seconds": None, "engine_used": "muse"}]}
    _save(d)
    return job_id


def sweep():
    """流程已经不等了（别人交了、退回了、中止了）的 queued / running 任务：取消。返回取消的 job_id。"""
    out = []
    for d in _all():
        if d["status"] in ACTIVE and d.get("flow"):
            why = _still_waiting(d)
            if why:
                _cancel(d, "流程已经不等这一步了：" + why)
                out.append(d["id"])
    return out


# ---- 查（跟 mbatch 一样）----

def queued(limit=20):
    out = []
    for d in _all():
        if d["status"] == "queued":
            out.append({"job_id": d["id"], "name": d["name"], "created": d["created"], "task_count": len(d["tasks"]),
                        "prompts": [(t.get("prompt") or "")[:300] for t in d["tasks"]], "flow": d.get("flow")})
            if len(out) >= limit:
                break
    return out


def jobs(limit=10):
    return [_brief(d) for d in _all()[:limit]]


def job_for(run, step, attempt=1):
    """查看器用：这条运行这一步这一次的任务（最新一条没取消的），只给 id、状态、认领时间；没有返回 None。
    run 是相对项目根的路径（同 flow.run）。"""
    for d in _all():                                   # 新的在前
        f = d.get("flow") or {}
        if (f.get("run") == run and f.get("step") == step and f.get("attempt", 1) == (attempt or 1)
                and d["status"] != "cancelled"):
            return {"job": d["id"], "status": d["status"], "claimed_at": d.get("claimed_at"),
                    "created": d.get("created"), "finished": d.get("finished"),
                    "error": (d["tasks"][0].get("error") or "")[:300] if d["status"] == "failed" else ""}
    return None


def describe():
    """人话版的概况（同 mbatch.describe）。"""
    lines = ["执行端：Muse（轮询认领；编排流程里 model=muse 的步骤）", f"任务目录：{JOBS}"]
    js = jobs(5)
    lines.append(f"最近 {len(js)} 个任务" if js else "还没有任务")
    for j in js:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:6} {j['name'][:40]}")
    return "\n".join(lines)


def status(job_id, full=False):
    d = _load(job_id)
    d["progress"] = _brief(d)["progress"]
    if not full:
        for t in d["tasks"]:
            for k in ("prompt", "output"):
                v = t.get(k) or ""
                if len(v) > 500:
                    t[k] = v[:500] + f"…（还有 {len(v) - 500} 字）"
    return d


# ---- 认领 / 写回（Muse 用）----

def claim(job_id):
    d = _load(job_id)
    if d["status"] != "queued":
        raise MuseBatchError(f"认领不了：{job_id} 现在是 {d['status']}，不是 queued")
    why = _still_waiting(d)
    if why:
        _cancel(d, "流程已经不等这一步了：" + why)
        raise MuseBatchError(f"不用做了：{why}（已取消 {job_id}）")
    d.update(status="running", started=_now(), claimed_by="muse", claimed_at=_now())
    for t in d["tasks"]:
        if t["status"] == "pending":
            t["status"] = "running"
    _save(d)
    return d


def set_task(job_id, index=0, output="", error="", status="done", seconds=None, client=None, wait=False):
    """写回结果。done：当场校验，不合格抛 MuseBatchError（什么都不写，改了再调）；合格交进流程。
    failed：记下原因，整批 failed，流程不动。client / wait 只给测试用（在当前进程里接着跑流程）。"""
    if status not in ("done", "failed"):
        raise MuseBatchError(f"set_task 的 status 只能是 done / failed，收到：{status!r}")
    d = _load(job_id)
    if d["status"] != "running":
        raise MuseBatchError(f"写不了：{job_id} 现在是 {d['status']}（要先 claim；结束了的不能再写）")
    try:
        t = d["tasks"][index]
    except IndexError:
        raise MuseBatchError(f"没有第 {index} 条任务，一共 {len(d['tasks'])} 条") from None
    if status == "failed":
        t.update(status="failed", error=error or "（没写原因）", output=output or "")
        d.update(status="failed", finished=_now())
        _save(d)
        return {"ok": True, "status": "failed", "note": "记下了，流程停在这一步等人处理"}
    from tools import muse_flow as mf
    f = d["flow"]
    try:
        st = mf.submit(ROOT / f["run"], output, step=f["step"], attempt=f["attempt"], client=client, wait=wait)
    except mf.NotWaiting as e:
        _cancel(d, f"流程已经不等这一步了：{e}")
        raise MuseBatchError(f"不用交了：{e}（已取消 {job_id}）") from None
    except mf.MuseFlowError as e:
        raise MuseBatchError(f"没交上，什么都没写，改了再 set_task：{e}") from None
    t.update(status="done", output=output if isinstance(output, str) else json.dumps(output, ensure_ascii=False),
             error="", seconds=seconds)
    d.update(status="done", finished=_now())
    _save(d)
    pend = st.get("pending") or {}
    return {"ok": True, "status": "done", "flow": st.get("status"),
            "next": {k: pend.get(k) for k in ("step", "name", "reason")} if pend else None}


def finish(job_id):
    """跟 mbatch 对得上：还在 running 的按 failed 结算（没写回结果）。set_task 合格时已经结束了。"""
    d = _load(job_id)
    if d["status"] not in ACTIVE:
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    for t in d["tasks"]:
        if t["status"] in ("pending", "running"):
            t.update(status="failed", error=(t.get("error") or "") + "（结束时还没写结果）")
    d.update(status="failed", finished=_now())
    _save(d)
    return {"job_id": job_id, "status": "failed"}


def cancel(job_id):
    d = _load(job_id)
    if d["status"] not in ACTIVE:
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    _cancel(d, "手动取消")
    return {"job_id": job_id, "status": "cancelled"}


def reclaim(job_id):
    d = _load(job_id)
    if d["status"] != "running":
        raise MuseBatchError(f"退回不了：{job_id} 现在是 {d['status']}，不是 running")
    d.update(status="queued", started=None, claimed_by=None, claimed_at=None)
    for t in d["tasks"]:
        if t["status"] == "running":
            t["status"] = "pending"
    _save(d)
    return {"job_id": job_id, "status": "queued"}


def reclaim_stuck(older_than_secs=1800):
    """认领超过 older_than_secs 还没写回的退回 queued（同 mbatch.reclaim_stuck）；流程已经不等的直接取消。"""
    now = datetime.now()
    out = []
    for d in _all():
        if d["status"] != "running" or not d.get("claimed_at"):
            continue
        try:
            age = (now - datetime.fromisoformat(d["claimed_at"]).replace(tzinfo=None)).total_seconds()
        except ValueError:
            continue
        if age >= older_than_secs:
            why = _still_waiting(d) if d.get("flow") else None
            if why:
                _cancel(d, "流程已经不等这一步了：" + why)
            else:
                reclaim(d["id"])
            out.append(d["id"])
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m tools.musebatch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("queued")
    j = sub.add_parser("jobs")
    j.add_argument("limit", nargs="?", type=int, default=10)
    for name in ("status", "claim", "cancel", "finish", "reclaim"):
        sub.add_parser(name).add_argument("job_id")
    s = sub.add_parser("set_task")
    s.add_argument("job_id")
    s.add_argument("index", nargs="?", type=int, default=0)
    s.add_argument("--file", help="结果 JSON 文件；不给就从标准输入读")
    s.add_argument("--failed", action="store_true")
    s.add_argument("--error", default="")
    sub.add_parser("reclaim_stuck")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "queued":
            out = queued()
        elif a.cmd == "jobs":
            out = jobs(a.limit)
        elif a.cmd == "status":
            out = status(a.job_id, full=True)
        elif a.cmd == "set_task":
            if a.failed:
                out = set_task(a.job_id, a.index, error=a.error, status="failed")
            else:
                text = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
                out = set_task(a.job_id, a.index, output=text)
        elif a.cmd == "reclaim_stuck":
            out = reclaim_stuck()
        else:
            out = globals()[a.cmd](a.job_id)
    except (MuseBatchError, OSError) as e:
        print(f"musebatch: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
