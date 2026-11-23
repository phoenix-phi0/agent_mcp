"""流程里给 Muse 的模型接口：角色卡 model 写 "muse"，流程停在这一步，Muse 自己取请求、干活、交结果。

和 cli:muse（tools/muse_backend.py）的区别：cli:muse 把 Muse 当成一个慢模型——编排往 mbatch 投提示词、
干等回复、格式不对整条重投（每次重新排队）。model=muse 是让流程直接停给 Muse：
  1. 受控运行（workflow_ctl）走到这张卡的步骤就停下（reason=muse，同 HUMAN 卡），
     真跑时往 musebatch 队列投一条任务（tools/musebatch.py，和 mbatch 一样只存不跑）。
  2. 本机轮询看到 queued 就唤醒 Muse：claim → 照提示词做 → set_task 写回结果（当场校验，合格就交进流程）。
     这个模块是底层（musebatch 用它取请求、交结果）；在阿里云上也可以不经队列直接：
       python -m tools.muse_flow queue                 列出在等 Muse 的步骤
       python -m tools.muse_flow show <run>            这一步的完整请求：system、prompt、schema、cwd、venv、test_cmd
       （在 cwd 里按 system / prompt 干活）
       python -m tools.muse_flow submit <run> --step N --attempt A --file result.json
                                                       交结果：当场按这一步的格式校验，不合格打印逐条问题、退出码 1，
                                                       改了接着交，不用重新排队；合格打印「已交」，流程在后台往下走
来源记 mcp:muse。不交、交不上：流程一直停在这一步，人可以在查看器或 MCP 上换卡 / 换模型再执行。

退出码：0 成功；1 结果不合格或参数错；2 这一步已经不等 Muse 了（别人交了、退回了、中止了）。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTOR = "mcp:muse"
# 给 Muse 看的请求里带这些键（pending 里还有编排内部用的，不给）
SHOW_KEYS = ("step", "attempt", "max_attempts", "name", "node", "card", "role", "format", "cwd", "venv", "test_cmd",
             "system", "prompt", "schema", "notes", "last_error", "card_error")


class MuseFlowError(Exception):
    pass


class NotWaiting(MuseFlowError):
    pass


def _run_path(run):
    p = Path(run)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    if ROOT not in p.parents or p.parent.name != "runs" or p.suffix != ".json" or not p.is_file():
        raise MuseFlowError(f"不是项目里 runs/ 下的运行记录：{run}")
    return p


def _rel(p):
    return Path(p).resolve().relative_to(ROOT).as_posix()


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def waiting(run, step=None, attempt=None):
    """这条运行现在停在等 Muse 的步骤上就返回 pending，否则 NotWaiting。"""
    p = _run_path(run)
    t = _load(p)
    pend = t.get("pending") or {}
    if t.get("status") != "waiting" or pend.get("reason") != "muse" or pend.get("phase", "before") != "before":
        where = f"（现在是 {t.get('status')}" + (f"，停在第 {pend.get('step')} 步等 {pend.get('reason')}" if pend else "") + "）"
        raise NotWaiting(f"{_rel(p)} 没有在等 Muse{where}")
    if step is not None and int(step) != pend.get("step"):
        raise NotWaiting(f"{_rel(p)} 现在停在第 {pend.get('step')} 步，不是第 {step} 步")
    if attempt is not None and int(attempt) != pend.get("attempt", 1):
        raise NotWaiting(f"{_rel(p)} 第 {pend.get('step')} 步现在是第 {pend.get('attempt', 1)} 次，不是第 {attempt} 次")
    return p, t, pend


def request(run, step=None, attempt=None):
    """给 Muse 的完整请求。cwd 是绝对路径（Muse 直接 cd 进去）。"""
    p, t, pend = waiting(run, step, attempt)
    out = {"run": _rel(p), "workflow": t.get("workflow")}
    out.update({k: pend[k] for k in SHOW_KEYS if k in pend})
    out.setdefault("attempt", 1)
    if pend.get("cwd"):
        out["cwd"] = str((Path(t.get("workdir") or ROOT / "workflow_demo") / pend["cwd"]).resolve())
        if pend.get("venv"):
            out["python"] = str(Path(out["cwd"]) / ".venv" / "bin" / "python")
    return out


def submit(run, result, step=None, attempt=None, client=None, wait=False):
    """交这一步的结果。不合格：MuseFlowError（带逐条问题，流程不动，可以改了再交）。"""
    from tools import workflow_ctl as wc
    p, _, pend = waiting(run, step, attempt)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError as e:
            raise MuseFlowError(f"结果不是 JSON：{e}") from None
    if not isinstance(result, dict):
        raise MuseFlowError("结果必须是 JSON 对象")
    if pend.get("schema"):
        # 当场校验：逐条列出所有问题（不只前 5 条），流程原地不动，改了再交
        from tools.wf_submit import coerce, validate
        result = coerce(pend["schema"], result)       # 数组 / 对象写成了 JSON 字符串：解开再校验
        bad = validate(pend["schema"], result)
        if bad:
            from tools.wf_submit import wrong_level_hint
            hint = wrong_level_hint(pend["schema"], result)
            lines = chr(10).join("  - " + e for e in bad)
            raise MuseFlowError((hint + chr(10) if hint else "") + "结果不符合格式 " + str(pend.get("format"))
                                + "，共 " + str(len(bad)) + " 条问题：" + chr(10) + lines)
    try:
        return wc.submit(p, result=result, step=pend["step"], wait=wait, client=client, actor=ACTOR)
    except wc.ControlError as e:
        raise MuseFlowError(str(e)) from None


def queue(workdir=None):
    """在等 Muse 的步骤（所有运行）。"""
    wd = Path(workdir) if workdir else ROOT / "workflow_demo"
    out = []
    for f in sorted((wd / "runs").glob("*.json")):
        try:
            t = _load(f)
        except (OSError, ValueError):
            continue
        pend = t.get("pending") or {}
        if t.get("status") == "waiting" and pend.get("reason") == "muse" and pend.get("phase", "before") == "before":
            out.append({"run": _rel(f), "step": pend.get("step"), "attempt": pend.get("attempt", 1),
                        "name": pend.get("name"), "card": pend.get("card"), "format": pend.get("format"),
                        "updated": t.get("updated")})
    return out


def notify(run):
    """运行停在等 Muse 的步骤上：往 musebatch 队列投一条任务（同一步同一次只投一条）。返回 job_id 或 None。"""
    from tools import musebatch
    return musebatch.post(run)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools.muse_flow", description="流程里给 Muse 的接口")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("queue", help="列出在等 Muse 的步骤")
    sh = sub.add_parser("show", help="这一步的完整请求")
    sh.add_argument("run")
    sh.add_argument("--step", type=int)
    sh.add_argument("--attempt", type=int)
    sm = sub.add_parser("submit", help="交结果（当场校验）")
    sm.add_argument("run")
    sm.add_argument("--step", type=int, required=True)
    sm.add_argument("--attempt", type=int)
    sm.add_argument("--file", help="结果 JSON 文件；不给就从标准输入读")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "queue":
            print(json.dumps(queue(), ensure_ascii=False, indent=2))
        elif a.cmd == "show":
            print(json.dumps(request(a.run, a.step, a.attempt), ensure_ascii=False, indent=2))
        else:
            text = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
            st = submit(a.run, text, a.step, a.attempt)
            print(f"已交：{st['run']} 第 {a.step} 步，流程接着往下走（现在 {st['status']}）")
    except NotWaiting as e:
        print(f"不用做了：{e}")
        return 2
    except (MuseFlowError, OSError) as e:
        print(f"没交上：{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
