"""workflow 的文件夹式 agent：SOUL.md + agent.json。"""
import json
import re
from pathlib import Path

from tools import config
from tools.dsl_core import DSLError, ScriptReturn

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_EFFORTS = set(config.EFFORTS)
_KEYS = {"model", "effort", "tools", "skills", "packages", "max_tool_rounds", "agentic", "cost", "description",
         "timeout", "via"}


def load_agent(engine, name, model_override=None):
    """读角色卡。model_override：外部控制换模型时整串替换卡里的 model（effort 写在 @ 后面）。"""
    if not _NAME.fullmatch(name):
        raise DSLError(f"agent 名称无效：{name}")
    # 项目内 agent 优先；公共角色目录可复用，但只有含 agent.json 的目录才算可调用 agent。
    roots = [engine.workdir / "agents", Path(__file__).resolve().parents[2] / "tools/dslagent/agent_profiles"]
    folder = next((root / name for root in roots if (root / name / "agent.json").is_file()), None)
    if folder is None:
        raise DSLError(f"没有 agent「{name}」：需要 agents/{name}/agent.json 和 SOUL.md")
    soul = folder / "SOUL.md"
    if not soul.is_file():
        raise DSLError(f"agent「{name}」缺少 SOUL.md")
    try:
        data = json.loads((folder / "agent.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise DSLError(f"agent「{name}」配置无法读取：{e}") from e
    if not isinstance(data, dict) or set(data) - _KEYS:
        raise DSLError(f"agent「{name}」配置字段无效：{set(data) - _KEYS if isinstance(data, dict) else '需要对象'}")
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise DSLError(f"agent「{name}」必须配置 model")
    model = model.strip()
    effort = data.get("effort")
    if effort is not None:
        if not isinstance(effort, str) or effort not in _EFFORTS:
            raise DSLError(f"agent「{name}」effort 无效：{effort}")
        if not model.startswith(("cli:claude/", "cli:codex/")) or "@" in model:
            raise DSLError(f"agent「{name}」只有 cli:claude 和 cli:codex 模型支持独立 effort 配置")
        model += "@" + effort
    if model_override:
        if not isinstance(model_override, str) or not model_override.strip():
            raise DSLError(f"agent「{name}」覆盖的模型无效：{model_override}")
        model = model_override.strip()
    try:
        config.parse_model(model)
    except (ValueError, config.ModelNameError) as e:
        raise DSLError(f"agent「{name}」模型配置无效：{e}") from e
    for key in ("tools", "skills", "packages"):
        if not isinstance(data.get(key, []), list) or any(not isinstance(x, str) or not x.strip() for x in data.get(key, [])):
            raise DSLError(f"agent「{name}」的 {key} 必须是非空字符串列表")
    # cost：这张卡跑一次的相对成本（只是一个数，流程用它分配任务、记账）；description：给派活的节点看的一句话
    cost = data.get("cost")
    if cost is not None and (not isinstance(cost, (int, float)) or isinstance(cost, bool) or not 0 < cost <= 1000):
        raise DSLError(f"agent「{name}」cost 必须是 0–1000 之间的正数")
    description = data.get("description", "")
    if not isinstance(description, str) or len(description) > 300:
        raise DSLError(f"agent「{name}」description 必须是不超过 300 字的字符串")
    rounds = data.get("max_tool_rounds", 3)
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= 10:
        raise DSLError(f"agent「{name}」max_tool_rounds 必须在 1–10")
    # timeout：纯问答（按格式提交）一次的超时秒数。慢模型（fable@high 写约定要两分钟以上）要调大；
    # agentic 的卡写在 agentic.timeout 里，这里不收
    call_timeout = data.get("timeout")
    if call_timeout is not None:
        if not isinstance(call_timeout, int) or isinstance(call_timeout, bool) or not 30 <= call_timeout <= 3600:
            raise DSLError(f"agent「{name}」timeout 必须是 30–3600 的整数")
        if data.get("agentic") is not None:
            raise DSLError(f"agent「{name}」agentic 的超时写在 agentic.timeout 里，不写顶层 timeout")
    # via：只给 cli:goose 用，"batchmgr" = 一律经 batchmgr 调 GLM（本机 goose 在 MCP 里审长约定交不上）
    via = data.get("via")
    if via is not None and (via != "batchmgr" or not model.startswith("cli:goose/")):
        raise DSLError(f"agent「{name}」via 只能是 \"batchmgr\"，且只给 cli:goose 模型用")
    agentic = data.get("agentic")
    if agentic is not None:
        # agentic：claude -p 自带工具在 cwd 里干活。只认 cli:claude；不能和 DSL 的 tools 混用
        if not isinstance(agentic, dict) or set(agentic) - {"cwd", "allowed_tools", "timeout", "max_turns", "venv",
                                                             "mcp_tools", "sandbox"}:
            raise DSLError(f"agent「{name}」agentic 只能写 cwd、allowed_tools、timeout、max_turns、venv、mcp_tools、"
                           f"sandbox")
        is_codex = model.startswith("cli:codex")
        if not (model.startswith("cli:claude") or is_codex):
            raise DSLError(f"agent「{name}」agentic 目前只支持 cli:claude 和 cli:codex 模型（现在是 {model}）")
        from tools.llm_router import CODEX_SANDBOXES
        if is_codex:
            # codex 的权限由它的系统级沙箱管：写 sandbox，不写 allowed_tools；探针 / 审查还没接
            if agentic.get("allowed_tools") or agentic.get("mcp_tools"):
                raise DSLError(f"agent「{name}」codex 的 agentic 用 sandbox 管权限，不写 allowed_tools、mcp_tools")
            if agentic.get("sandbox", "workspace-write") not in CODEX_SANDBOXES:
                raise DSLError(f"agent「{name}」agentic.sandbox 只能是 {' / '.join(CODEX_SANDBOXES)}")
        elif "sandbox" in agentic:
            raise DSLError(f"agent「{name}」sandbox 只给 cli:codex 用；claude 用 allowed_tools")
        if data.get("tools"):
            raise DSLError(f"agent「{name}」agentic 和 tools 不能同时写")
        root = engine.workdir.resolve()
        # cwd 可以写变量，如 work/{project}：按引擎变量展开，每个项目一个目录
        raw_cwd = engine.expand(str(agentic.get("cwd") or "."))
        if "{" in raw_cwd or "}" in raw_cwd or not raw_cwd.strip():
            raise DSLError(f"agent「{name}」agentic.cwd 里的变量没有值：{agentic.get('cwd')}（在 run.zs 里先设好）")
        cwd = (root / raw_cwd.strip()).resolve()
        if cwd != root and root not in cwd.parents:
            raise DSLError(f"agent「{name}」agentic.cwd 越出工作目录")
        allowed = [] if is_codex else agentic.get("allowed_tools")
        if not is_codex and (not isinstance(allowed, list) or not allowed
                             or any(not isinstance(x, str) or not x.strip() for x in allowed)):
            raise DSLError(f"agent「{name}」agentic.allowed_tools 必须是非空字符串列表")
        if any(x.replace(" ", "") in ("Bash", "Bash(*)", "Bash(:*)") for x in allowed):
            raise DSLError(f"agent「{name}」agentic 不允许不受限的 Bash，写成 Bash(python3 -m pytest:*) 这样")
        timeout = agentic.get("timeout", 600)
        turns = agentic.get("max_turns", 40)
        for key, val, lo, hi in (("timeout", timeout, 30, 3600), ("max_turns", turns, 1, 200)):
            if not isinstance(val, int) or isinstance(val, bool) or not lo <= val <= hi:
                raise DSLError(f"agent「{name}」agentic.{key} 必须是 {lo}–{hi} 的整数")
        cwd.mkdir(parents=True, exist_ok=True)
        venv = agentic.get("venv", False)
        if not isinstance(venv, bool):
            raise DSLError(f"agent「{name}」agentic.venv 只能是 true 或 false")
        # mcp_tools：再挂几个 gsb_tools 的工具（探针、独立审查），见 llm_router.GSB_AGENT_TOOLS
        from tools.llm_router import GSB_AGENT_TOOLS
        mcp_tools = agentic.get("mcp_tools", [])
        if (not isinstance(mcp_tools, list) or any(not isinstance(x, str) for x in mcp_tools)
                or set(mcp_tools) - set(GSB_AGENT_TOOLS)):
            raise DSLError(f"agent「{name}」agentic.mcp_tools 只能从 {list(GSB_AGENT_TOOLS)} 里选")
        agentic = {"cwd": cwd, "allowed_tools": [x.strip() for x in allowed],
                   "timeout": timeout, "max_turns": turns, "venv": venv, "mcp_tools": list(mcp_tools)}
        if is_codex:
            agentic["sandbox"] = (data["agentic"].get("sandbox") or "workspace-write")
    parts = [soul.read_text(encoding="utf-8").strip()]
    for rel in data.get("skills", []):
        path = (folder / rel).resolve()
        if folder.resolve() not in path.parents or not path.is_file():
            raise DSLError(f"agent「{name}」技能文件不存在或越出目录：{rel}")
        if path.stat().st_size > 64 * 1024:
            raise DSLError(f"agent「{name}」技能文件超过 64 KB：{rel}")
        parts.append(f"【技能 {rel}】\n{path.read_text(encoding='utf-8')}")
    return {"name": name, "model": model, "tools": data.get("tools", []),
            "packages": data.get("packages", []), "rounds": rounds,
            "system": "\n\n".join(parts), "agentic": agentic,
            "cost": cost, "description": description.strip(), "timeout": call_timeout, "via": via}


def card_info(engine, name):
    """给编排的「角色清单」「成本合计」用：卡的名字、成本、一句话说明、模型。"""
    profile = load_agent(engine, name)
    return {"name": name, "cost": profile["cost"], "description": profile["description"],
            "model": profile["model"]}


def load_format(engine, name):
    """节点的「格式 名字」→ (名字, JSON Schema)。格式文件在工作目录 formats/ 下。"""
    from tools import wf_submit
    try:
        return name, wf_submit.load_format(engine.workdir, name)
    except wf_submit.FormatError as e:
        raise DSLError(str(e)) from e


def check_format(fmt, result):
    """结果不符合格式就返回错误列表（空 = 符合）。"""
    from tools import wf_submit
    return wf_submit.validate(fmt[1], result) if fmt else []


def _prompt(task, context, node=None, fmt=None, submit=False, notes=None, previous=None):
    prompt = f"本次调用：{node}（提交格式 {fmt[0]}）\n" if fmt else ""
    prompt += f"任务：{task}\n"
    if context is not None:
        prompt += f"参考文本：{json.dumps(context, ensure_ascii=False) if isinstance(context, (dict, list)) else context}\n"
    if notes:
        prompt += "补充说明（人工追加，和任务同等效力）：\n"
        prompt += "".join(f"{i}. {note['text']}\n" for i, note in enumerate(notes, 1))
    if previous is not None:
        prompt += "上一次交的结果被打回，要按意见重做：\n"
        reject = next((note for note in reversed(notes or []) if note.get("kind") == "reject"), None)
        if reject is not None:
            prompt += f"打回意见：{reject['text']}\n"
        result = json.dumps(previous, ensure_ascii=False)
        if len(result) > 20000:
            result = result[:20000] + "…（已截断）"
        prompt += f"上一次的结果：{result}\n"
    if fmt and submit:
        return prompt          # 用 submit 工具交：工具的参数格式就是这一步的格式，提示由 submit_call 加
    if fmt:
        return (prompt + "按下面的 JSON Schema 只返回一个 JSON 对象，不要代码围栏或解释：\n"
                + json.dumps(fmt[1], ensure_ascii=False))
    return prompt + "只返回一个 JSON 对象，不要代码围栏或解释。"


def _uses_submit(engine, profile, fmt):
    """有格式、模型是 cli:claude / cli:goose、不是离线假客户端 → 用 submit 工具交。"""
    if not fmt or getattr(engine.client, "offline", False) is True:
        return False
    spec = config.parse_model(profile["model"])
    return spec.channel == "cli" and spec.provider in ("claude", "goose", "codex")


def describe(engine, name, task, context=None, model=None, node=None, fmt=None, notes=None, previous=None):
    """不调用，只给出这一步会怎么调：外部自己执行时照这个拼请求（prompt 里带格式）。"""
    profile = load_agent(engine, name, model)
    out = {"card": name, "model": profile["model"], "agentic": bool(profile.get("agentic")),
           "system": profile["system"],
           "prompt": _prompt(task, context, node, fmt, notes=notes, previous=previous),
           "cost": profile.get("cost")}
    if fmt:
        out.update(format=fmt[0], schema=fmt[1])
    return out


def call_agent(engine, name, task, context=None, model=None, node=None, fmt=None, notes=None, previous=None):
    profile = load_agent(engine, name, model)
    for pack in profile["packages"]:
        if not _NAME.fullmatch(pack):
            raise DSLError(f"agent「{name}」动词包名无效：{pack}")
        engine._do_use(pack, engine._at)
    tools = profile["tools"]
    if tools:
        # schema 检查保证每个可用工具都已加载。模型仅看到这份白名单。
        engine._tools_schema(tools)
    # 给编排过程记录用：这次实际用的模型和方式
    submit = _uses_submit(engine, profile, fmt)
    engine._wf_last_call = {"model": profile["model"], "agentic": bool(profile.get("agentic"))}
    if profile.get("cost") is not None:
        engine._wf_last_call["cost"] = profile["cost"]
    if fmt:
        engine._wf_last_call.update(format=fmt[0], via="submit" if submit else "json")
    on_call = getattr(engine, "_wf_on_call", None)
    if on_call:
        on_call(engine._wf_last_call)   # 调用前就把模型写进进行中的那条事件
    prompt = _prompt(task, context, node, fmt, submit, notes=notes, previous=previous)
    messages = [{"role": "system", "content": profile["system"]},
                {"role": "user", "content": prompt}]
    if engine.dry_run:
        return {}
    from tools import llm_router as _router
    _router.LAST_USAGE["value"] = None
    try:
        # 离线的假客户端（测试、mock）照旧走 client，不真去起 claude，同 RouterClient 的约定
        if submit:
            from tools import llm_router
            reply = llm_router.submit_call(prompt, profile["system"], profile["model"], fmt[1],
                                           agentic=profile.get("agentic"), timeout=profile.get("timeout"),
                                           via=profile.get("via"))
        elif profile.get("agentic") and getattr(engine.client, "offline", False) is not True:
            from tools import llm_router
            reply = llm_router.claude_agentic(prompt, profile["system"], profile["model"],
                                              **profile["agentic"])
        else:
            reply = (engine._chat_tools(messages, tools, profile["rounds"], profile["model"])
                 if tools else engine.client.chat_messages(messages, temperature=engine.temperature,
                                                           model=profile["model"]))
    except ScriptReturn:
        raise
    except Exception as e:
        raise DSLError(f"agent「{name}」调用失败：{e}") from e
    finally:
        # 实际用量（claude 自己报的费用、token、轮数，加上工具内部的花费）：成功失败都记
        if _router.LAST_USAGE["value"]:
            engine._wf_last_call["usage"] = _router.LAST_USAGE["value"]
    if isinstance(reply, dict):
        result = reply
    else:
        text = str(reply).strip()
        try:
            result = json.loads(text)
        except (ValueError, TypeError):
            # 模型常把 JSON 包在 ```json 围栏里或前后带一句话：先剥一次再判失败
            try:
                from tools.llm_router import strip_json
                result = json.loads(strip_json(text))
            except Exception as e:
                # 原始回复记进过程记录，外部控制才能看清是重试、换模型还是手修后 submit
                engine._wf_last_call["raw"] = text[:20000]
                raise DSLError(f"agent「{name}」没有返回 JSON 对象（回复 {len(text)} 字，"
                               f"开头：{text[:80]!r}）") from e
    if not isinstance(result, dict):
        engine._wf_last_call["raw"] = str(reply)[:20000]
        raise DSLError(f"agent「{name}」必须返回 JSON 对象")
    errors = check_format(fmt, result)
    if errors:
        engine._wf_last_call["raw"] = json.dumps(result, ensure_ascii=False)[:20000]
        raise DSLError(f"agent「{name}」的结果不符合格式 {fmt[0]}：" + "；".join(errors[:5]))
    return result
