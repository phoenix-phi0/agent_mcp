# -*- coding: utf-8 -*-
"""GSBatch 续接判定的 Drools 桥接。

tools/gsbatch.py::_run_one 的内联判定（2026-11-01 的自动续接）抽成了两份：

- _decide_local      原逻辑原样搬过来，默认用这份（不碰 java，行为不变）
- decide_drools      同一判定的 Drools 版：事实 JSON 进 tools/gsbatch_drools
                     的 GsbatchDecide，规则在 decide.drl

GSBATCH_DECIDER=drools 时用 Drools；引擎起不来（没 java、编译炸了）
回退本地实现并在返回值里标 engine="drools-fallback"——不静默，写进
任务记录能看见。两边同判由 tests/test_gsbatch_rules.py 的对照保证。
"""

import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DROOLS_DIR = HERE / "gsbatch_drools"
OUT_DIR = DROOLS_DIR / "out"
JAVA_HOME = os.environ.get("JAVA_HOME") or str(Path.home() / "opt" / "jdk-17.0.21+9")


def _m2_classpath() -> str:
    m2 = Path.home() / ".m2" / "repository"
    jars = sorted(p for p in m2.rglob("*.jar")
                  if "sources" not in p.name and "javadoc" not in p.name)
    return ":".join(str(j) for j in jars)


def decide_local(why, rc, err_text, retries, has_session, cancelled,
                 seconds_left, backoff=(30, 60, 120), resume_max=3) -> dict:
    """本地参照实现：gsbatch._run_one 内联判定的原样搬运。返回
    {"resume": bool, "gave_up": str, "wait": int}。

    seconds_left = 截止时刻 − 现在 − 候选退避秒数（≤0 就是「续了也来不及」）。
    """
    reason = None
    if why == "stall":
        reason = "流卡住"
    elif why is None and (rc != 0 or err_text) and err_text is not None:
        reason = err_text
        if reason and not _transient(reason):
            reason = None
    if not reason:
        return {"resume": False, "gave_up": "", "wait": 0, "engine": "local"}
    if not has_session:
        return {"resume": False, "gave_up": "没有会话 id，接不上", "wait": 0, "engine": "local"}
    if cancelled:
        return {"resume": False, "gave_up": "已取消", "wait": 0, "engine": "local"}
    if retries >= resume_max:
        return {"resume": False, "gave_up": f"已重试 {retries} 次，不再试", "wait": 0, "engine": "local"}
    wait_s = backoff[min(retries, len(backoff) - 1)] if backoff else 0
    if seconds_left <= 0:
        return {"resume": False, "gave_up": "剩余时间不够再续", "wait": 0, "engine": "local"}
    return {"resume": True, "gave_up": "", "wait": wait_s, "engine": "local"}


def _transient(err: str) -> bool:
    """与 tools/gsbatch.py 的 _transient 同源。绕开 import 循环
    （gsbatch 会在 decider=drools 时 import 这里），正则改从 gsbatch 取：
    先试 import，失败才退化到本地副本——两份正则不一样时对照测试会炸。
    """
    from .gsbatch import _transient as t
    return t(err)


def decide_drools(why, rc, err_text, retries, has_session, cancelled,
                  seconds_left, backoff=(30, 60, 120), resume_max=3) -> dict:
    """同一判定的 Drools 版。引擎不可用时回退 decide_local，engine 字段标记。"""
    fact = {
        "why": why, "rc": rc, "error": err_text or "",
        "has_complete": False,          # 走到判定这步的都还没拿到 complete
        "retries": retries, "has_session": has_session,
        "cancelled": cancelled, "seconds_left": seconds_left,
        "backoff": list(backoff), "resume_max": resume_max,
    }
    java = Path(JAVA_HOME) / "bin" / "java"
    cp = _m2_classpath()
    try:
        r = subprocess.run(
            [str(java), "-cp", f"{cp}:{OUT_DIR}", "GsbatchDecide"],
            input=json.dumps(fact), capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"GsbatchDecide 退出码 {r.returncode}：{r.stderr.strip()[-200:]}")
        d = json.loads(r.stdout.strip().splitlines()[-1])
        d["engine"] = "drools"
        return d
    except Exception as e:      # noqa: BLE001 —— 回退要兜住一切：没 java、超时、JSON 烂
        d = decide_local(why, rc, err_text, retries, has_session, cancelled,
                         seconds_left, backoff, resume_max)
        d["engine"] = "drools-fallback"
        d["fallback_reason"] = str(e)[:200]
        return d


def decide(why, rc, err_text, retries, has_session, cancelled,
           seconds_left, backoff=(30, 60, 120), resume_max=3) -> dict:
    """gsbatch 的入口。GSBATCH_DECIDER=drools 走 Drools，默认本地实现。"""
    if os.environ.get("GSBATCH_DECIDER") == "drools":
        return decide_drools(why, rc, err_text, retries, has_session, cancelled,
                             seconds_left, backoff, resume_max)
    return decide_local(why, rc, err_text, retries, has_session, cancelled,
                        seconds_left, backoff, resume_max)
