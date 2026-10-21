"""并行跑一组子脚本，等全部结束，返回结果列表（顺序同输入）。例如 设 rs = 并行执行 {jobs} 并发=3

列表的每项是一个子脚本：文本 "脚本名 键=值 键=值"（同「执行」，值里不能有空格），
或对象 {脚本, 参数:{键: 值}}（值可以带空格、换行、结构）。脚本名先当工作目录里的 .zs 文件找，
找不到就当脚本动词（.zs 动词）的名字，参数按动词的声明绑定（默认值生效）。并发缺省 3（1–8）。

每个子脚本独立作用域、独立子引擎（共用客户端、动词表、预算），互不影响：某项出错或「终止」不影响别的项，
全部跑完才返回。每项的结果是 {script, params, status, reason, at, returned}：
    status     成功（正常结束或「返回」了）| 失败 | 超出预期（子脚本「终止」的状态；脚本出错算 失败，原因是错误的第一行）
    returned   子脚本「返回」的值，没有「返回」就是它的输出文本
预算用完时各项按「终止 超出预期」结束，调用方下一条语句照样终止。

    设 jobs = 解析JSON []
    设 jobs = 列表加项 {jobs} 做一个模块 模块=graph
    设 rs = 并行执行 {jobs} 并发=2
    遍历 r 于 {rs}
      如果 {r.status} 不等于 成功
        打印 {r.script} 没做成：{r.reason}
      结束
    结束
"""

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tools.dsl import DSLError, background_reason, current_engine
from tools.dsl_core import CALL_PARAM_RE
from tools.verbs import as_list

DEFAULT_PARALLEL = 3
MAX_PARALLEL = 8


def _parse_job(job):
    """一项 → (脚本名, {键: 值})。"""
    if isinstance(job, dict):
        name = str(job.get("脚本") or job.get("script") or "").strip()
        params = job.get("参数") or job.get("params") or {}
        if not isinstance(params, dict):
            raise DSLError("并行执行：参数要是对象 {键: 值}")
        return name, dict(params)
    text = str(job).strip()
    name, _, tail = text.partition(" ")
    return name.strip(), {m.group(1).strip(): m.group(2).strip() for m in CALL_PARAM_RE.finditer(tail)}


def _script_of(eng, name, params):
    """→ (脚本全文, 绑好的参数)。先找工作目录里的 .zs，再找脚本动词。"""
    if not name:
        raise DSLError("并行执行：有一项没写脚本名")
    fname = name if name.endswith(".zs") else f"{name}.zs"
    try:
        path = eng._safe_path(fname)
    except Exception:  # noqa: BLE001  越出工作目录之类，当作没有这个文件
        path = None
    if path is not None and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8"), params
    if eng.verbs is not None and eng.verbs.has(name) and eng.verbs.kind_of(name) == "script":
        bound = eng.verbs.bind(name, [], list(params.items()))
        _, impl = eng.verbs.resolve(name)
        return Path(impl).read_text(encoding="utf-8"), bound
    raise DSLError(f"并行执行：找不到子脚本「{name}」（既不是工作目录里的 .zs，也不是脚本动词）")


def _run_one(eng, job):
    name, params = "", {}
    try:
        name, params = _parse_job(job)
        text, params = _script_of(eng, name, params)
        sub = eng._sub_engine()
        sub.vars.update(params)
        out = sub.run(text)
        if sub.halted is not None:
            h = sub.halted
            return {"script": name, "params": params, "status": h["status"], "reason": h["reason"], "at": h["at"], "returned": ""}
        return {"script": name, "params": params, "status": "成功", "reason": "", "at": "",
                "returned": sub.returned[0] if sub.returned else out}
    except Exception as e:  # noqa: BLE001  单项出错是结果，不能带崩整组
        return {"script": name, "params": params, "status": "失败", "reason": background_reason(e), "at": "", "returned": ""}


def 并行执行(列表: str = "", 并发: str = str(DEFAULT_PARALLEL)) -> list:
    eng = current_engine()
    jobs = as_list(列表)
    m = re.fullmatch(r"\s*(\d+)\s*", str(并发))
    n = min(max(int(m.group(1)), 1), MAX_PARALLEL) if m else DEFAULT_PARALLEL
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=min(n, len(jobs))) as ex:
        futs = [ex.submit(_run_one, eng, j) for j in jobs]
        return [f.result() for f in futs]
