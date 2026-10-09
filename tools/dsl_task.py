# -*- coding: utf-8 -*-
"""派子任务：「派任务」「并行派任务」两个动词的实现（verbs/common/defs 里只是薄壳）。

一个子任务 = 任务描述 + 入参 + 处理逻辑 + 回复格式字段，交给模型做一件事，
回复固定是 {结果, 状态, 原因}：

    结果   格式给了字段（改法:列表,说明:文本）就是带这些字段的对象，没给就是非空文本
    状态   只能是 成功 / 失败 / 超出预期（同「终止」的三个状态）
    原因   状态不是成功时必须写；成功时可以空

模型走调用它的那个引擎：同一个客户端（api / cli 通道、llm_router 的并发上限）、
同一个系统提示、「模型 X」设的模型和温度——跟「问JSON」一样，所以缓存设置也一样。
回复不合格（不是 JSON、缺字段、状态不对、结果字段类型不对）带着问题重答 1 次，
还不合格不抛错，返回 状态=失败 原因=格式不合格（问题 里是哪儿不对）；模型那头出错
（超时、进程退出）也是 状态=失败。子任务失败是流程里的正常分支，不该让脚本崩掉。

入参：动词拿到的是文本（结构是 JSON 文本）。
    JSON 对象 {名: 值}   每个值单独附上，名字当小标题
    JSON 数组            每项单独附上
    别的                 按逗号拆成几项
每一项是「文件:起-止」「文件:行」或工作目录里存在的文件名时，由动词读出那几行
（带「  12| 」行号前缀，最多 MAX_LINES 行）附上；别的原样附上。

空跑（引擎的 dry_run，dslagent 规划检查时开着）：不调模型，给一个结构合法的假结果
（状态=成功，结果按格式字段填占位值），带 空跑=是。
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .dsl_core import HALT_STATES, to_text

STATES = HALT_STATES
DEFAULT_PARALLEL = 3
MAX_PARALLEL = 8
MAX_LINES = 400
FORMAT_BAD = "格式不合格"
# 文件:起-止 / 文件:行 / 文件（带扩展名）
FILE_REF_RE = re.compile(r"^([^\s:,，]+\.[A-Za-z0-9_]+)(?::(\d+)(?:-(\d+))?)?$")
_REASK = ("你上次的回复不合格：{}。请改正后重新输出：只输出一个 JSON 对象，"
          "顶层字段 结果、状态、原因，不要代码围栏，不要任何解释。")


def parse_format(fmt) -> list:
    """「改法:列表,说明:文本 置信?:数字」→ 问JSON 同款字段表。空 → []。"""
    from .dsl_model import _split_format
    text = to_text(fmt).strip()
    if not text:
        return []
    tokens = [t for t in re.split(r"[\s,，、]+", text) if t]
    _, spec, _ = _split_format("x 格式 " + " ".join(tokens), 0)
    if spec is None:
        raise ValueError(f"看不懂的回复格式「{text}」，写法：字段:类型,字段?:类型"
                         f"（类型 文本 数字 是否 列表 A|B|C）")
    return spec


def _read_ref(workdir: Path, ref: str):
    """「文件:起-止」读出带行号的那几行；不是文件引用返回 None。"""
    m = FILE_REF_RE.match(ref.strip())
    if not m:
        return None
    root = Path(workdir).resolve()
    p = (root / m.group(1)).resolve()
    if p != root and root not in p.parents:
        return f"[读不到 {ref}：越出工作目录]"
    if not p.is_file():
        return None if m.group(2) is None else f"[读不到 {ref}：文件不存在]"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    a = int(m.group(2) or 1)
    b = int(m.group(3) or (m.group(2) or len(lines)))
    a, b = max(a, 1), min(b, len(lines))
    if b - a + 1 > MAX_LINES:
        b = a + MAX_LINES - 1
    body = "\n".join(f"{i:4d}| {lines[i - 1]}" for i in range(a, b + 1))
    return f"（{m.group(1)} 第 {a}-{b} 行，共 {len(lines)} 行）\n{body}"


def collect_inputs(inputs, workdir) -> list:
    """入参 → [(小标题, 内容)]。见模块说明。"""
    if isinstance(inputs, (dict, list)):
        data = inputs
    else:
        text = to_text(inputs).strip()
        if not text:
            return []
        data = None
        if text.startswith(("{", "[")):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
        if data is None:
            data = [x.strip() for x in re.split(r"[,，]", text) if x.strip()]
    pairs = list(data.items()) if isinstance(data, dict) else \
        [(str(i), v) for i, v in enumerate(data if isinstance(data, list) else [data], 1)]
    out = []
    for name, value in pairs:
        got = _read_ref(workdir, value) if isinstance(value, str) else None
        title = name if isinstance(data, dict) else (value if got is not None else f"第 {name} 项")
        out.append((title, got if got is not None else to_text(value)))
    return out


def _format_desc(spec: list) -> tuple:
    """回复格式说明，和示例里的「结果」。"""
    from .dsl_model import _KIND_DESC, _KIND_SAMPLE
    if not spec:
        return "文本（非空，写清楚做了什么、得到了什么）", "……"
    lines, sample = ["对象，字段："], {}
    for name, optional, kind, options in spec:
        desc = ("只能是 " + "、".join(f"\"{o}\"" for o in options) + " 之一"
                if options else _KIND_DESC[kind])
        if optional:
            desc += "；可选"
        lines.append(f"    - {name}：{desc}")
        sample[name] = options[0] if options else _KIND_SAMPLE[kind]
    return "\n".join(lines), sample


def build_prompt(task, inputs: list, logic, spec: list) -> str:
    result_desc, sample = _format_desc(spec)
    parts = [f"【子任务】\n{to_text(task).strip()}"]
    if to_text(logic).strip():
        parts.append(f"【处理逻辑】\n{to_text(logic).strip()}")
    if inputs:
        parts.append("【入参】\n" + "\n".join(f"◆ {t}\n{c}" for t, c in inputs))
    states = "、".join(f"\"{s}\"" for s in STATES)
    example = json.dumps({"结果": sample, "状态": STATES[0], "原因": ""}, ensure_ascii=False)
    parts.append(
        "【回复格式】只输出一个 JSON 对象，不要代码围栏，不要任何解释。顶层字段：\n"
        f"- 结果：{result_desc}\n"
        f"- 状态：只能是 {states} 之一（成功＝按要求做完；失败＝做不到或出错；"
        f"超出预期＝实际情况和任务的前提不符，要上层重新决定）\n"
        f"- 原因：文本；状态不是成功时必须写清楚原因，成功时留空\n"
        f"示例：{example}")
    return "\n\n".join(parts)


def check_reply(data, spec: list):
    """返回 (规范化后的 {结果, 状态, 原因}, 问题列表)。"""
    from .dsl_model import _check_format
    if not isinstance(data, dict):
        return None, ["回复应该是一个 JSON 对象" if data is not None else "回复不是合法 JSON"]
    problems = []
    state = to_text(data.get("状态")).strip()
    if state not in STATES:
        problems.append(f"状态 只能是 {' / '.join(STATES)}，你回了「{state[:30]}」")
    reason = data.get("原因")
    reason = "" if reason is None else to_text(reason).strip()
    if state in STATES and state != STATES[0] and not reason:
        problems.append(f"状态是 {state} 时 原因 不能空")
    result = data.get("结果")
    if spec:
        if not isinstance(result, dict):
            problems.append("结果 应该是一个对象")
        else:
            result, more = _check_format(result, spec)
            problems += [f"结果.{p}" if not p.startswith("缺少") else p.replace("缺少字段 ", "缺少字段 结果.")
                         for p in more]
    elif result is None or (isinstance(result, str) and not result.strip()):
        problems.append("缺少 结果")
    if problems:
        return None, problems
    return {"结果": result, "状态": state, "原因": reason}, []


def _fake(task, spec: list) -> dict:
    from .dsl_model import _KIND_SAMPLE
    head = to_text(task).strip()[:20]
    if spec:
        result = {}
        for name, _, kind, options in spec:
            result[name] = options[0] if options else (
                f"（空跑）{head}" if kind == "文本" else
                0 if kind == "数字" else False if kind == "是否" else [] if kind == "列表"
                else _KIND_SAMPLE.get(kind))
    else:
        result = f"（空跑）{head}"
    return {"结果": result, "状态": STATES[0], "原因": "", "空跑": True}


def _failed(reason: str, **extra) -> dict:
    return {"结果": "", "状态": "失败", "原因": reason, **extra}


def dispatch(engine, task, inputs="", logic="", fmt="") -> dict:
    """派一个子任务，返回 {结果, 状态, 原因}（失败时可能多 问题 / 回复）。不抛错。"""
    from .zhipu import strip_json
    if not to_text(task).strip():
        return _failed("没写任务描述")
    try:
        spec = parse_format(fmt)
    except Exception as e:
        return _failed(f"回复格式写错了：{e}")
    if engine is None:
        return _failed("拿不到引擎（派任务只能在脚本里调）")
    if getattr(engine, "dry_run", False):
        return _fake(task, spec)
    prompt = build_prompt(task, collect_inputs(inputs, engine.workdir), logic, spec)
    msgs = ([{"role": "system", "content": engine.system}] if engine.system else []) + \
        [{"role": "user", "content": prompt}]
    problems, last = [], ""
    for attempt in range(2):
        try:
            reply = engine.client.chat_messages(msgs, temperature=engine.temperature,
                                                model=engine.model)
        except Exception as e:
            first = (str(e).strip().splitlines() or [type(e).__name__])[0]
            return _failed(f"模型没有回应：{first}"[:200])
        if isinstance(reply, (dict, list)):        # 假客户端可以直接回结构
            data, last = reply, to_text(reply)
        else:
            last = str(reply)
            try:
                data = json.loads(strip_json(last))
            except json.JSONDecodeError:
                data = None
        value, problems = check_reply(data, spec)
        if not problems:
            return value
        if attempt == 0:
            msgs = msgs + [{"role": "assistant", "content": last},
                           {"role": "user", "content": _REASK.format("；".join(problems))}]
    return _failed(FORMAT_BAD, 问题="；".join(problems), 回复=last[:500])


def _item_of(x) -> tuple:
    """列表里的一项 → (任务, 入参, 逻辑, 格式)。对象认中英文键，文本当任务描述。"""
    if isinstance(x, dict):
        def get(*keys):
            return next((x[k] for k in keys if k in x), "")
        return (get("任务", "task"), get("入参", "inputs"), get("逻辑", "处理逻辑", "logic"),
                get("格式", "回复格式", "format"))
    return to_text(x), "", "", ""


def dispatch_many(engine, items, limit=DEFAULT_PARALLEL) -> list:
    """并行派一组互不依赖的子任务，最多 limit 个同时跑；结果顺序同输入。"""
    if isinstance(items, str):
        text = items.strip()
        try:
            items = json.loads(text) if text else []
        except json.JSONDecodeError:
            raise ValueError(f"要一个子任务列表（JSON 数组），给的是：{text[:60]}") from None
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise ValueError("要一个子任务列表（JSON 数组）")
    try:
        n = int(to_text(limit).strip() or DEFAULT_PARALLEL)
    except ValueError:
        raise ValueError(f"并发数要是整数，给的是「{limit}」") from None
    n = max(1, min(n, MAX_PARALLEL))
    if not items:
        return []

    def one(x):
        try:
            return dispatch(engine, *_item_of(x))
        except Exception as e:     # dispatch 自己不抛；这里兜住意外，不让一项拖垮整组
            return _failed(f"{type(e).__name__}: {e}"[:200])

    with ThreadPoolExecutor(max_workers=min(n, len(items)), thread_name_prefix="zs-task") as pool:
        return list(pool.map(one, items))
