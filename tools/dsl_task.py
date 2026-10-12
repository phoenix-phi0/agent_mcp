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
（带「  12| 」行号前缀，每段最多 MAX_LINES 行）附上；项里别处出现「文件:起-止」（多段 a-b,c-d、
夹在句子中间）也一样，原文附在该项后面；文件不存在、行号越界附一行说明，不静默丢弃；别的原样附上。

预算（「预算 调用 N 秒 M」）用完时客户端抛 ScriptHalt：不当成子任务失败，原样往外抛，
由引擎按「终止 超出预期」结束；并行派任务里一项撞上，整组跟着结束。

空跑（引擎的 dry_run，dslagent 规划检查时开着）：不调模型，给一个结构合法的假结果
（状态=成功，结果按格式字段填占位值），带 空跑=是。
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import json_repair as JR
from .dsl_core import HALT_STATES, ScriptReturn, to_text

STATES = HALT_STATES
DEFAULT_PARALLEL = 3
MAX_PARALLEL = 8
MAX_LINES = 400
FORMAT_BAD = "格式不合格"
# 文件:起-止 / 文件:行 / 文件（带扩展名）
FILE_REF_RE = re.compile(r"^([^\s:,，]+\.[A-Za-z0-9_]+)(?::(\d+)(?:-(\d+))?)?$")
# 文本里任意位置的 文件:区间[,区间…]，区间 起-止 或 单行；逗号后允许空格
INLINE_REF_RE = re.compile(r"([^\s:,，;；\"'“”()（）\[\]{}<>|=]+\.[A-Za-z][A-Za-z0-9_]*):"
                           r"(\d+(?:-\d+)?(?:[,，]\s*\d+(?:-\d+)?)*)")
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
    """整个入参就是一个「文件:起-止」（或带扩展名的文件名）→ 带行号的那几行；不是文件引用返回 None。"""
    m = FILE_REF_RE.match(ref.strip())
    if not m:
        return None
    if m.group(2) is None:
        p = (Path(workdir).resolve() / m.group(1))
        if not p.is_file():
            return None
    return _read_range(workdir, m.group(1), m.group(2), m.group(3))


def _read_range(workdir: Path, name: str, start, end) -> str:
    """name 的第 start-end 行（都可空＝整份）。读不到、越界时返回一行说明，不返回 None。"""
    ref = name if start is None else f"{name}:{start}" + (f"-{end}" if end else "")
    root = Path(workdir).resolve()
    p = (root / name).resolve()
    if p != root and root not in p.parents:
        return f"[读不到 {ref}：越出工作目录]"
    if not p.is_file():
        return f"[读不到 {ref}：文件不存在]"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    a = int(start or 1)
    b = int(end or (start or len(lines)))
    if a < 1 or a > len(lines) or b < a:
        why = "起止写反了" if 1 <= a <= len(lines) else "行号越界"
        return f"[读不到 {ref}：{why}，文件共 {len(lines)} 行]"
    note = f"（要求到第 {b} 行，文件只有 {len(lines)} 行，读到末尾）\n" if b > len(lines) else ""
    b = min(b, len(lines))
    if b - a + 1 > MAX_LINES:
        b = a + MAX_LINES - 1
    body = "\n".join(f"{i:4d}| {lines[i - 1]}" for i in range(a, b + 1))
    return f"{note}（{name} 第 {a}-{b} 行，共 {len(lines)} 行）\n{body}"


def _inline_refs(workdir: Path, text: str) -> list:
    """文本里出现的所有「文件:起-止」（含 a-b,c-d 多段、逗号后带空格、出现在句子中间）→ 原文块列表，同一段只读一次。"""
    out, seen = [], set()
    for m in INLINE_REF_RE.finditer(text):
        name = m.group(1)
        if name.startswith("//"):  # 网址的 host:port
            continue
        for seg in re.split(r"[,，]\s*", m.group(2)):
            a, _, b = seg.partition("-")
            key = (name, a, b)
            if key not in seen:
                seen.add(key)
                out.append(_read_range(workdir, name, a, b or None))
    return out


def _split_items(text: str) -> list:
    """按逗号拆项；但 a.py:1-5,9-12 里跟在区间后面的纯区间（9-12）属于上一项，不拆。"""
    items = []
    for x in (x.strip() for x in re.split(r"[,，]", text)):
        if not x:
            continue
        if items and re.fullmatch(r"\d+(-\d+)?", x) and re.search(r":\d+(-\d+)?(,\d+(-\d+)?)*$", items[-1]):
            items[-1] += "," + x
        else:
            items.append(x)
    return items


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
            data = _split_items(text)
    pairs = list(data.items()) if isinstance(data, dict) else \
        [(str(i), v) for i, v in enumerate(data if isinstance(data, list) else [data], 1)]
    out = []
    for name, value in pairs:
        got = _read_ref(workdir, value) if isinstance(value, str) else None
        if got is None and isinstance(value, str):
            blocks = _inline_refs(workdir, value)
            if blocks:
                got = value.strip() + "\n" + "\n".join(blocks)
                title = name if isinstance(data, dict) else f"第 {name} 项"
                out.append((title, got))
                continue
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
    value = _dispatch(engine, task, inputs, logic, fmt)
    log = getattr(engine, "sublog", None)
    if isinstance(log, list) and not value.get("空跑"):
        log.append({"模式": "工具" if getattr(engine, "subtask_mode", "json") == "tool" else "json",
                    "任务": to_text(task).strip()[:200], **{k: v for k, v in value.items() if k != "结果"},
                    "结果": to_text(value.get("结果"))[:500]})
    return value


def _dispatch(engine, task, inputs, logic, fmt) -> dict:
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
    if getattr(engine, "subtask_mode", "json") == "tool" and getattr(engine, "run_subtask_tool", None):
        return engine.run_subtask_tool(task, collect_inputs(inputs, engine.workdir), logic, spec)
    return dispatch_json(engine, task, collect_inputs(inputs, engine.workdir), logic, spec)


def dispatch_json(engine, task, inputs: list, logic, spec: list, client=None) -> dict:
    """json 模式的一次子任务（子任务回 JSON，edits 交主流程套用）。inputs 已经是 collect_inputs 的结果。client 缺省用引擎的。"""
    from .zhipu import strip_json
    client = client or engine.client
    prompt = build_prompt(task, inputs, logic, spec)
    msgs = ([{"role": "system", "content": engine.system}] if engine.system else []) + \
        [{"role": "user", "content": prompt}]
    problems, last = [], ""
    for attempt in range(2):
        try:
            reply = client.chat_messages(msgs, temperature=engine.temperature,
                                        model=engine.model)
        except ScriptReturn:       # 预算用完：交给引擎终止
            raise
        except Exception as e:
            first = (str(e).strip().splitlines() or [type(e).__name__])[0]
            return _failed(f"模型没有回应：{first}"[:200])
        repaired, err = "", ""
        if isinstance(reply, (dict, list)):        # 假客户端可以直接回结构
            data, last = reply, to_text(reply)
        else:
            last = str(reply)
            data, repaired, err = JR.parse(strip_json(last))
        data, lifted = JR.lift_status(data)
        if lifted:
            repaired = (repaired + "+" if repaired else "") + "状态上提"
        value, problems = check_reply(data, spec)
        if not problems:
            return dict(value, repaired=repaired, 原文=last[:500]) if repaired else value
        feedback = [p + f"（{err}）" if err and data is None and p == "回复不是合法 JSON" else p for p in problems]
        if attempt == 0:
            msgs = msgs + [{"role": "assistant", "content": last},
                           {"role": "user", "content": _REASK.format("；".join(feedback))}]
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
        except ScriptReturn:
            raise
        except Exception as e:     # dispatch 自己不抛；这里兜住意外，不让一项拖垮整组
            return _failed(f"{type(e).__name__}: {e}"[:200])

    with ThreadPoolExecutor(max_workers=min(n, len(items)), thread_name_prefix="zs-task") as pool:
        return list(pool.map(one, items))
