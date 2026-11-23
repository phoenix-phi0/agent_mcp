"""Muse 当模型用：模型名 cli:muse。

Muse 不是 API，是一个轮询 mbatch 队列的执行端（本机的 mbatch-watchdog 每 120 秒看一次阿里云上的
~/.mbatch/jobs，有 queued 的任务就唤醒 Muse；Muse 认领、自己做、把最后的回复写回）。
所以「调 Muse」= 往 mbatch 投一条任务 → 等它被认领、做完 → 取回回复。

- complete()：纯问答（「问」里写 用 cli:muse），回复原样返回。
- submit()：编排里按格式交（角色卡 model=cli:muse）。提示词末尾要求「最后的回复只写一个 JSON 对象」，
  取回后按这一步的格式校验，不合格带着错误重投（默认最多 2 次：每次都要排队、慢）。
  agentic（卡里写了 agentic.cwd）时任务的 cwd 就是项目目录，提示词里写明在哪个目录干活、用哪个虚拟环境。

两段超时：
  - 认领：投进去以后多久没被认领就取消、报错（DSL_MUSE_CLAIM_WAIT，默认 900 秒；轮询是 120 秒一次，
    15 分钟还没认领多半是本机的轮询没开或 Muse 不在线）。
  - 做完：认领以后多久没写回就取消、报错（agentic.timeout，纯问答 DSL_MUSE_TIMEOUT，默认 1800 秒）。
取消只改状态，已经在做的那条由 Muse 自己看到 cancelled 后停下（见 mbatch.cancel）。
"""
import json
import os
import time
from pathlib import Path

from . import mbatch

CLAIM_WAIT = int(os.environ.get("DSL_MUSE_CLAIM_WAIT") or 900)
DEFAULT_TIMEOUT = int(os.environ.get("DSL_MUSE_TIMEOUT") or 1800)
POLL = float(os.environ.get("DSL_MUSE_POLL") or 10)
MAX_TRIES = int(os.environ.get("DSL_MUSE_TRIES") or 2)

ASK_JSON = ("\n\n【怎么交结果】做完以后，你最后的回复只写一个 JSON 对象，就是这一步的结果，"
            "按下面的 JSON Schema（不要代码围栏、不要前后的说明文字，这条回复会被程序直接解析）。"
            "不要调用 submit 之类的工具交结果，也不要把结果只写进文件。\nJSON Schema：\n")


class MuseError(Exception):
    pass


def _sleep(seconds):          # 测试里换掉
    time.sleep(seconds)


def run_job(prompt, cwd=None, timeout=None, name="muse", claim_wait=None, poll=None):
    """投一条任务给 Muse，等它做完，返回 (回复文字, 用量)。认领或做完超时、做失败、被取消：MuseError。"""
    timeout = int(timeout if timeout is not None else DEFAULT_TIMEOUT)
    claim_wait = int(claim_wait if claim_wait is not None else CLAIM_WAIT)
    poll = POLL if poll is None else poll
    try:
        job = mbatch.submit([prompt], name=name, cwd=str(cwd) if cwd else None, timeout=timeout)
    except mbatch.MBatchError as e:
        raise MuseError(f"投不进 mbatch：{e}") from None
    jid = job["job_id"]
    t0 = time.time()
    claimed_at = None
    while True:
        d = mbatch.status(jid, full=True)
        st = d["status"]
        now = time.time()
        if st == "running" and claimed_at is None:
            claimed_at = now
        if st not in ("queued", "running"):
            break
        if st == "queued" and now - t0 > claim_wait:
            mbatch.cancel(jid)
            raise MuseError(f"Muse {claim_wait} 秒没有认领任务 {jid}（本机的 mbatch-watchdog 轮询可能没开，"
                            f"或 Muse 不在线），已取消")
        if st == "running" and now - claimed_at > timeout:
            mbatch.cancel(jid)
            raise MuseError(f"Muse 认领后 {timeout} 秒没写回任务 {jid}，已取消")
        _sleep(poll)
    task = d["tasks"][0]
    usage = {"backend": "muse", "job": jid, "seconds": round(time.time() - t0, 1),
             "wait_claim": round((claimed_at or time.time()) - t0, 1)}
    if st == "cancelled":
        raise MuseError(f"任务 {jid} 被取消了")
    if st != "done" or task.get("status") != "done":
        raise MuseError(f"Muse 没做成任务 {jid}（{st}）：{(task.get('error') or task.get('output') or '')[:300]}")
    out = (task.get("output") or "").strip()
    if not out:
        raise MuseError(f"Muse 做完了任务 {jid}，但回复是空的")
    return out, usage


def last_json(text):
    """回复里最后一个完整的 JSON 对象（允许前后有文字或 ```json 围栏）。找不到返回 None。"""
    text = text.strip()
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    dec = json.JSONDecoder()
    found = None
    i = text.find("{")
    while i != -1:
        try:
            v, end = dec.raw_decode(text, i)
            if isinstance(v, dict):
                found = v
            i = text.find("{", end)
        except ValueError:
            i = text.find("{", i + 1)
    return found


def _err_text(e):
    if isinstance(e, dict):
        return f"{e.get('path', '')}：{e.get('message', '')}"
    return str(e)


def _where(agentic):
    if not agentic:
        return ""
    cwd = Path(agentic["cwd"])
    s = (f"【工作环境】这一步在阿里云这台机器的项目目录 {cwd} 里做：先 cd 进去，读写的文件都在这个目录里，"
         f"不要改目录以外的东西。")
    if agentic.get("venv"):
        vpy = cwd / ".venv" / "bin" / "python"
        s += f"项目用自己的虚拟环境：命令里写 {vpy}（如 {vpy} -m pytest、{vpy} -m pip install -r requirements.txt）。"
    return s + "\n\n"


def complete(prompt, system, timeout=None):
    text = f"{system}\n\n{prompt}" if system else prompt
    out, _ = run_job(text, timeout=timeout, name="muse 问答")
    return out


def submit(prompt, system, schema, agentic=None, max_tries=None, timeout=None, name="muse 编排"):
    """按格式交：返回 (已校验的结果 dict, 用量)。max_tries 次都不合格：MuseError（带最后的错误）。"""
    from . import wf_submit
    tries = max(1, int(max_tries or MAX_TRIES))
    timeout = (agentic or {}).get("timeout") or timeout or DEFAULT_TIMEOUT
    cwd = (agentic or {}).get("cwd")
    base = f"{system}\n\n{_where(agentic)}{prompt}{ASK_JSON}{json.dumps(schema, ensure_ascii=False)}"
    feedback = ""
    errors = []
    usage = {"backend": "muse", "tries": 0, "jobs": [], "seconds": 0.0}
    for n in range(1, tries + 1):
        out, u = run_job(base + feedback, cwd=cwd, timeout=timeout, name=f"{name}（第 {n} 次）")
        usage["tries"] = n
        usage["jobs"].append(u["job"])
        usage["seconds"] = round(usage["seconds"] + u["seconds"], 1)
        result = last_json(out)
        errors = ["回复里找不到 JSON 对象"] if result is None else wf_submit.validate(schema, result)
        if not errors:
            return result, usage
        feedback = ("\n\n【上一次交的不合格，重交】上一次的回复末尾：\n" + out[-800:]
                    + "\n问题：" + "；".join(_err_text(e) for e in errors[:8])
                    + "\n这次照上面的要求只回一个合格的 JSON 对象。")
    raise MuseError(f"Muse {tries} 次都没有按格式交：" + "；".join(_err_text(e) for e in errors[:5]))
