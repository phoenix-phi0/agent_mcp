"""派任务的「工具」模式（DSLAGENT_SUBTASK=tool）：子任务是一次多轮 claude 调用，挂一个 MCP 工具 `dsl`（dslmcp.py），
模型用工具读 / 搜 / 改，最后回 {结果, 状态, 原因} JSON。这里是真工具调用（claude CLI 挂 MCP）。

- 工具：dsl(code)。白名单（dslcheck.check_call；读片段 搜索代码 查引用 改文件 写文件 + 用包 设 如果 打印），执行前语法 + 白名单 + 空跑，
  不过就把错误作为工具结果回给模型；返回本次输出（≤ 6000 字）。同一子任务里变量共享（一个 MCP 进程 = 一个子任务）。
  每次调用追加一行日志到 任务目录/toollogs/*.jsonl（ts、code_len、edited、files、sec、status）。
- claude 参数：-p --output-format stream-json --verbose --include-partial-messages --max-turns 6 --tools "" --strict-mcp-config
  --mcp-config <json> --allowedTools mcp__dsl__dsl --setting-sources "" --disable-slash-commands（见 v2.call_claude）。
- 快照：子任务开始前记项目快照（V2.snapshot）；重试 / 兜底前、失败时把这个子任务的工具改过的文件（MCP 日志里记的，并行子任务各管各的）恢复到快照。
  成功时结果里 edits 为空（工具已改）→ 计划里的 改文件 {r.结果} 是空操作（V2Engine._no_edits）；结果里写明改了哪些文件。
  工具没改任何文件、最终回复却带了 edits（照 json 模式回的）→ 保留，由计划里的 改文件 套用。
- 保险（v2.call_claude）：空闲超时、输出超长、「输出工具调用格式」（只查当前一轮的文字；真实工具调用是 tool_use 块，不算）。
  触发一次 → 恢复快照后同输入重试 1 次；累计触发 2 次 → 兜底。
- 兜底：同一子任务出现 保险触发 2 次 / 轮数用尽（error_max_turns）或没回最终文字 / 最终回复不是合法 JSON（或字段不合格）
  任一情况 → 恢复快照，用 json 模式（dsl_task.dispatch_json，直接给改法）重发该子任务一次，结果记 fallback=1 和 fallback_reason。
- 结果附：工具调用（次数）、轮数、保险触发（次数及原因）、工具改文件、子任务秒、缓存读 token、fallback。
"""
import json
import time

from tools.dsl_core import ScriptHalt, ScriptReturn, to_text

from . import promptfile as PF

MAX_TURNS = 6
GUARD = ("空闲超时", "输出工具调用格式", "输出超长")
TOOL_MARKS = ("<invoke", "<function_calls")

SYSTEM = PF.text("toolsub_system.txt")


def _snap(workdir):
    from . import v2 as V2
    return V2.snapshot(workdir)


def _restore(workdir, base, files):
    """把这个子任务的工具改过的文件（MCP 日志里记的）恢复成快照；并行派任务里别的子任务改的文件不动。"""
    from . import v2 as V2
    V2.restore(workdir, base, sorted(files))


def _fail(reason, **extra):
    return {"结果": "", "状态": "失败", "原因": reason, **extra}


def _parse(text):
    from tools.zhipu import strip_json
    try:
        return json.loads(strip_json(text))
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _edits(result):
    return result.get("edits") if isinstance(result, dict) else None


def run(engine, task, inputs: list, logic, spec: list) -> dict:
    """一个子任务：tool 调用（保险触发重试 1 次）→ 合格的最终 JSON 就返回；否则按规则兜底 json 模式。"""
    from tools import dsl_task as T
    raw = getattr(engine.client, "_inner", engine.client)
    runner = getattr(raw, "run_tool", None)
    if runner is None:
        return _fail("这个引擎的模型客户端不支持 tool 模式（只有 dslagent v2 的客户端支持）")
    engine.usage.take()                    # 计一次调用（后面的重试 / 兜底不再计，费用照样进总账）
    prompt = T.build_prompt(task, inputs, logic, spec)
    base = _snap(engine.workdir)
    t_all = time.time()
    st = {"保险触发": [], "工具调用": 0, "轮数": 0, "缓存读": 0, "尝试": [], "改过": set()}
    fb = ""

    def tally(r):
        rows = r.get("tool_log") or []
        st["工具调用"] += len(rows)
        st["改过"].update(f for x in rows for f in x.get("files", []))
        st["轮数"] += r.get("num_turns") or 0
        st["缓存读"] += ((r.get("usage") or {}).get("cache_read") or 0)
        st["尝试"].append({"工具调用": len(rows), "轮数": r.get("num_turns"), "failed": r.get("failed"), "秒": r.get("sec"),
                         "改文件": sorted({f for x in rows for f in x.get("files", [])})})

    def spent():
        why = engine.usage.over() if engine.usage.limited else engine.usage.spent
        if why:
            raise ScriptHalt("超出预期", f"预算用完：{why}", "")

    value = None
    for attempt in range(2):
        try:
            r = runner(SYSTEM, prompt, engine.workdir, f"tool{attempt + 1}", MAX_TURNS)
        except ScriptReturn:
            raise
        except Exception as e:  # noqa: BLE001
            first = (str(e).strip().splitlines() or [type(e).__name__])[0]
            _restore(engine.workdir, base, st["改过"])
            return _fail(f"模型没有回应：{first}"[:200], **_extra(st, t_all, [], 0))
        tally(r)
        spent()
        text = (r.get("text") or "").strip()
        why = r.get("failed")
        if not why and any(m in text for m in TOOL_MARKS):
            why = "输出工具调用格式"
        if why in GUARD:
            st["保险触发"].append(why)
            _restore(engine.workdir, base, st["改过"])
            if len(st["保险触发"]) >= 2:
                fb = "保险触发 2 次：" + "、".join(st["保险触发"])
                break
            continue
        if why == "轮数用尽" or (why == "空回复" and (r.get("tool_calls") or 0) > 0):
            fb = "轮数用尽未回 JSON" if why == "轮数用尽" else "工具调用后没有最终回复"
            _restore(engine.workdir, base, st["改过"])
            break
        if why:                               # rc≠0 / 空回复（没调工具）：当模型没有回应，重试 1 次
            st.setdefault("失败", []).append(why)
            _restore(engine.workdir, base, st["改过"])
            if attempt == 1:
                return _fail(f"模型没有回应：{why}", **_extra(st, t_all, [], 0))
            continue
        data = _parse(text)
        res, problems = T.check_reply(data, spec)
        if problems:
            fb = "最终回复不是合法 JSON：" + "；".join(problems)[:200]
            _restore(engine.workdir, base, st["改过"])
            break
        value = (res, r)
        break
    else:
        fb = fb or "保险触发"
    if value is None:
        if not fb:
            return _fail("模型没有回应", **_extra(st, t_all, [], 0))
        res = T.dispatch_json(engine, task, inputs, logic, spec, client=raw)
        spent()
        return dict(res, **_extra(st, t_all, [], 1), fallback_reason=fb)
    res, r = value
    files = sorted(st["改过"])
    result = res.get("结果")
    ed = _edits(result)
    if files and ed:
        result["edits"] = []                  # 工具已经改了，不再交主流程套（套会因为原文对不上而失败）
        st["丢弃edits"] = len(ed)
    if files and res.get("状态") == "成功":
        note = "（工具里改了：" + "、".join(files) + "）"
        if isinstance(result, str):
            res["结果"] = result + note
        elif isinstance(result, dict):
            for k in ("说明", "note"):
                if isinstance(result.get(k), str):
                    result[k] += note
                    break
    return dict(res, **_extra(st, t_all, files, 0))


def _extra(st, t_all, files, fallback):
    return {"工具调用": st["工具调用"], "轮数": st["轮数"], "保险触发": list(st["保险触发"]), "工具改文件": files,
            "子任务秒": round(time.time() - t_all, 1), "缓存读": st["缓存读"], "fallback": fallback,
            "尝试": st["尝试"], **({"丢弃edits": st["丢弃edits"]} if "丢弃edits" in st else {}),
            **({"模型失败": st["失败"]} if "失败" in st else {})}
