"""workflow 的文件夹式 agent：SOUL.md + agent.json。"""
import json
import re
from pathlib import Path

from tools import config
from tools.dsl_core import DSLError, ScriptReturn

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_EFFORTS = set(config.EFFORTS)
# platform:<模型 ID>[@effort]：走 Claude Platform 托管 agent，工具在阿里云自托管 worker 的沙箱里执行（见 tools/platform_agent.py）
_PLATFORM = re.compile(r"platform:claude-[a-z0-9][a-z0-9.-]*(@(low|medium|high|xhigh|max))?")
_KEYS = {"model", "effort", "tools", "skills", "packages", "max_tool_rounds", "agentic", "cost", "description",
         "timeout", "via", "category"}
# category：卡的分类，只用来分组显示（agents 工具、查看器的换卡下拉）；目录见 workflow_demo/agents/CATALOG.md
CATEGORIES = ("架构", "分析", "会议", "实现", "测试", "验收", "记录", "人")
# 机械步骤：节点里写「指令 命令名 键=值 …」，由内置的 ROBOT 直接跑命令表（tools/cmd_table.json）里的命令，
# 不调模型，不建卡。调用方是 workflow（只放行只读命令和几条跑测试的命令，提交、推送、重启服务不在里面）。
# 参数值里可以写 {变量}；整个值就是一个 {变量} 时保留结构（列表还是列表）。
CMD = "cmd"         # ROBOT 内部用的 model 标记，不能写在卡上
_CMD_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
CMD_CALLER = "workflow"
ROBOT = "ROBOT"     # 内置的「机器人」：节点写了「指令」时由它执行，不用建卡
CMD_OUTPUT_MAX = 20000


HUMAN = "human"     # 卡的 model 写 "human"：这个角色是人，不调模型，只等人在查看器上交结果
# 卡的 model 写 "muse"：这一步交给 Muse 自己做。受控运行停在这一步、往 musebatch 队列投一条任务，
# Muse 认领、在项目目录里干活、set_task 写回结果（当场按格式校验）。见 tools/musebatch.py
MUSE = "muse"
EXTERNAL = (HUMAN, MUSE)     # 不调模型、停下等外部交结果的执行者


def card_executor(workdir, name):
    """不走 load_agent 的快速判断（受控运行决定停不停时用）：卡在、而且 model 是 human / muse 就返回它，否则 None。"""
    roots = [Path(workdir) / "agents", Path(__file__).resolve().parents[2] / "tools/dslagent/agent_profiles"]
    for root in roots:
        f = root / str(name) / "agent.json"
        if f.is_file():
            try:
                model = json.loads(f.read_text(encoding="utf-8")).get("model")
            except (OSError, ValueError):
                return None
            return model if model in EXTERNAL else None
    return None


def is_human_card(workdir, name):
    return card_executor(workdir, name) == HUMAN


def load_agent(engine, name, model_override=None, command=None):
    """读角色卡。model_override：外部控制换模型时整串替换卡里的 model（effort 写在 @ 后面）。
    name 是 ROBOT 时不读卡，按节点上的指令（command）跑命令。"""
    if name == ROBOT:
        if model_override:
            raise DSLError(f"{ROBOT} 是跑命令的机器人，不能换模型；要让 AI 或人来做，换成别的卡")
        return robot_profile(command)
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
    if "category" in data and data["category"] not in CATEGORIES:
        raise DSLError(f"agent「{name}」category 只能是 {'、'.join(CATEGORIES)}（现在是 {data['category']!r}）")
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise DSLError(f"agent「{name}」必须配置 model")
    model = model.strip()
    effort = data.get("effort")
    if effort is not None and model != HUMAN:
        if not isinstance(effort, str) or effort not in _EFFORTS:
            raise DSLError(f"agent「{name}」effort 无效：{effort}")
        if not model.startswith(("cli:claude/", "cli:codex/", "platform:")) or "@" in model:
            raise DSLError(f"agent「{name}」只有 cli:claude、cli:codex 和 platform 模型支持独立 effort 配置")
        model += "@" + effort
    if model_override:
        if not isinstance(model_override, str) or not model_override.strip():
            raise DSLError(f"agent「{name}」覆盖的模型无效：{model_override}")
        model = model_override.strip()
    if model == HUMAN:
        # 人：没有模型、工具、effort；卡上只留说明（SOUL.md 当作给人看的发言须知）
        if effort is not None or data.get("agentic") is not None or data.get("tools") or data.get("packages"):
            raise DSLError(f"agent「{name}」是人（model=human），不写 effort、agentic、tools、packages")
        cost = data.get("cost")
        if cost is not None and (not isinstance(cost, (int, float)) or isinstance(cost, bool) or not 0 < cost <= 1000):
            raise DSLError(f"agent「{name}」cost 必须是 0–1000 之间的正数")
        return {"name": name, "model": HUMAN, "tools": [], "packages": [], "rounds": 1,
                "system": soul.read_text(encoding="utf-8").strip(), "agentic": None, "cost": cost,
                "description": str(data.get("description", "")).strip(), "timeout": None, "via": None}
    if model == CMD:
        raise DSLError(f"agent「{name}」model 不能写 cmd：机械步骤在节点里写「指令 命令名 键=值 …」，不建卡")
    is_platform = model.startswith("platform:")
    if is_platform:
        if not _PLATFORM.fullmatch(model):
            raise DSLError(f"agent「{name}」模型配置无效：{model}（写成 platform:claude-sonnet-5-5 或带 @effort）")
        if data.get("agentic") is None:
            raise DSLError(f"agent「{name}」platform 模型要写 agentic.cwd（工具在哪个项目目录里执行）")
    elif model == MUSE:
        # Muse 自己做：工具、权限、模型都在它那边，卡上只有说明、技能和在哪个目录干活
        bad = [k for k in ("tools", "packages", "via", "timeout", "max_tool_rounds") if data.get(k)]
        if bad:
            raise DSLError(f"agent「{name}」是 Muse（model=muse），不写 {'、'.join(bad)}")
    else:
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
                                                             "mcp_tools", "sandbox", "min_reads"}:
            raise DSLError(f"agent「{name}」agentic 只能写 cwd、allowed_tools、timeout、max_turns、venv、mcp_tools、"
                           f"sandbox、min_reads")
        is_codex = model.startswith("cli:codex")
        is_muse = model in ("cli:muse", MUSE)
        if not (model.startswith("cli:claude") or is_codex or is_platform or is_muse):
            raise DSLError(f"agent「{name}」agentic 目前只支持 cli:claude、cli:codex、cli:muse 和 platform 模型（现在是 {model}）")
        if is_muse and (agentic.get("allowed_tools") or agentic.get("mcp_tools") or "sandbox" in agentic
                        or "min_reads" in agentic):
            # Muse 是轮询 mbatch 的执行端，工具和权限在它自己那边，编排管不到
            raise DSLError(f"agent「{name}」{model} 的 agentic 只写 cwd、timeout、max_turns、venv，"
                           f"不写 allowed_tools、mcp_tools、sandbox、min_reads")
        if is_platform and (agentic.get("allowed_tools") or agentic.get("mcp_tools") or "sandbox" in agentic):
            raise DSLError(f"agent「{name}」platform 的权限由自托管 worker 的沙箱管，不写 allowed_tools、mcp_tools、sandbox")
        from tools.llm_router import CODEX_SANDBOXES
        if is_codex:
            # codex 的权限由它的系统级沙箱管：写 sandbox，不写 allowed_tools；探针 / 审查还没接
            if agentic.get("allowed_tools") or agentic.get("mcp_tools"):
                raise DSLError(f"agent「{name}」codex 的 agentic 用 sandbox 管权限，不写 allowed_tools、mcp_tools")
            if agentic.get("sandbox", "workspace-write") not in CODEX_SANDBOXES:
                raise DSLError(f"agent「{name}」agentic.sandbox 只能是 {' / '.join(CODEX_SANDBOXES)}")
        elif "sandbox" in agentic and not is_platform:
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
        if is_platform and cwd.parent != root / "work":
            raise DSLError(f"agent「{name}」platform 的 agentic.cwd 必须是 work/<项目>（worker 只开放这一层）")
        allowed = [] if (is_codex or is_platform or is_muse) else agentic.get("allowed_tools")
        if not (is_codex or is_platform or is_muse) and (not isinstance(allowed, list) or not allowed
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
        allowed = [x.strip() for x in allowed]
        if venv:
            # 用项目虚拟环境时，测试命令常写成 .venv/bin/python -m pytest：卡上放行的 python / pip / pytest
            # 命令自动加上 .venv/bin/ 的写法（实测整项目流程里 TEST_ENGINEER、QA 因此被拦，测试一次没跑成）
            extra_venv = []
            for x in allowed:
                m = re.fullmatch(r"Bash\((python3?|pip3?|pytest)((?: [^)]*)?(?::\*)?)\)", x)
                if m:
                    v = f"Bash(.venv/bin/{m[1]}{m[2]})"
                    if v not in allowed and v not in extra_venv:
                        extra_venv.append(v)
            allowed += extra_venv
        agentic = {"cwd": cwd, "allowed_tools": allowed,
                   "timeout": timeout, "max_turns": turns, "venv": venv, "mcp_tools": list(mcp_tools)}
        if is_codex:
            agentic["sandbox"] = (data["agentic"].get("sandbox") or "workspace-write")
        min_reads = data["agentic"].get("min_reads", 0)
        if "min_reads" in data["agentic"] and not is_platform:
            raise DSLError(f"agent「{name}」min_reads 只给 platform 模型用（按会话里的工具调用计数）")
        if not isinstance(min_reads, int) or isinstance(min_reads, bool) or not 0 <= min_reads <= 50:
            raise DSLError(f"agent「{name}」agentic.min_reads 必须是 0–50 的整数")
        if is_platform:
            agentic["project"] = cwd.name
            agentic["min_reads"] = min_reads
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


def _check_command(name, command, args):
    if not isinstance(command, str) or not _CMD_NAME.fullmatch(command):
        raise DSLError(f"「{name}」要写命令表里的命令名（现在是 {command!r}）")
    from tools import cmd as _cmd
    if command not in {c["name"] for c in _cmd.list_as(CMD_CALLER)}:
        raise DSLError(f"「{name}」命令 {command} 不在命令表里，或流程（{CMD_CALLER}）没有权限跑它")
    if not isinstance(args, dict) or any(not isinstance(k, str) for k in args):
        raise DSLError(f"「{name}」命令参数必须是对象")
    return command, args


def robot_profile(command):
    """节点上直接写「指令 命令名 键=值 …」：不用卡，由内置的 ROBOT 执行。"""
    if not isinstance(command, dict):
        raise DSLError(f"{ROBOT} 只用在写了「指令」的节点上")
    cmd_name, args = _check_command(ROBOT, command.get("name"), command.get("args", {}))
    return {"name": ROBOT, "model": CMD, "tools": [], "packages": [], "rounds": 1,
            "system": f"机器人：照节点上的指令跑命令表里的 {cmd_name}，不调模型。", "agentic": None, "cost": None,
            "description": "按指令跑命令表里的命令", "timeout": None, "via": None,
            "command": cmd_name, "args": args}


_WHOLE_VAR = re.compile(r"^\{([^{}]+)\}$")


def _cmd_value(engine, value):
    if isinstance(value, str):
        m = _WHOLE_VAR.fullmatch(value.strip())
        if m and "或" not in m[1]:
            got = engine.lookup(m[1].strip())
            if got is None:
                raise DSLError(f"命令参数 {value} 没有值")
            if isinstance(got, str) and got.lstrip()[:1] in ("[", "{"):
                # 设 x = [...] 存的是 JSON 字面量文本：按结构传
                try:
                    return json.loads(got)
                except ValueError:
                    pass
            return got
        for ref in re.findall(r"(?<!\{)\{([^{}]+)\}(?!\})", value):
            if "或" not in ref and engine.lookup(ref.strip()) is None:
                raise DSLError(f"命令参数 {value} 里的变量 {ref} 没有值")
        return str(engine.expand(value))
    if isinstance(value, list):
        return [_cmd_value(engine, v) for v in value]
    if isinstance(value, dict):
        return {k: _cmd_value(engine, v) for k, v in value.items()}
    return value


def run_cmd(engine, profile):
    """机械步骤：按卡上的 command 和 args 跑一条命令表里的命令，返回固定结构的结果。
    命令被拒（参数不合法、没权限）算这一步出错；命令跑了但退出码不是 0 算「失败」，由流程自己分支。"""
    from tools import cmd as _cmd
    args = {k: _cmd_value(engine, v) for k, v in profile["args"].items()}
    # DSL 的变量都是字符串：命令表里写着 int / bool 的参数照类型转一下（转不了就原样交给命令表去拒）
    spec = next((c["params"] for c in _cmd.list_as(CMD_CALLER) if c["name"] == profile["command"]), {})
    for k, v in list(args.items()):
        kind = (spec.get(k) or {}).get("type")
        if kind == "int" and isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
            args[k] = int(v.strip())
        elif kind == "bool" and isinstance(v, str) and v.strip() in ("true", "false", "是", "否"):
            args[k] = v.strip() in ("true", "是")
        elif kind == "text" and isinstance(v, (dict, list)):
            # 整条记录交给命令（如抽查依据）：按 JSON 文本传
            args[k] = json.dumps(v, ensure_ascii=False)
    res = _cmd.run_as(CMD_CALLER, profile["command"], args)
    if res.get("status") == "rejected":
        raise DSLError(f"命令 {profile['command']} 被拒：{res.get('reason') or res.get('output')}")
    output = str(res.get("output") or "")
    if len(output) > CMD_OUTPUT_MAX:
        output = "…（前面已截断）" + output[-CMD_OUTPUT_MAX:]
    data = None
    last = output.strip().splitlines()[-1] if output.strip() else ""
    if last.startswith("{") and last.endswith("}"):
        try:
            data = json.loads(last)
        except ValueError:
            data = None
    ok = res.get("status") == "ok" and res.get("exit_code") == 0
    return {"状态": "成功" if ok else "失败", "结果": output, "command": profile["command"], "args": args,
            "exit_code": res.get("exit_code"), "data": data}


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
    if (not fmt or getattr(engine.client, "offline", False) is True or profile["model"].startswith("platform:")
            or profile["model"] in EXTERNAL or profile["model"] == CMD):
        return False
    spec = config.parse_model(profile["model"])
    return spec.channel == "cli" and spec.provider in ("claude", "goose", "codex", "muse")


def describe(engine, name, task, context=None, model=None, node=None, fmt=None, notes=None, previous=None,
             command=None):
    """不调用，只给出这一步会怎么调：外部自己执行时照这个拼请求（prompt 里带格式）。"""
    profile = load_agent(engine, name, model, command=command)
    out = {"card": name, "model": profile["model"], "agentic": bool(profile.get("agentic")),
           "system": profile["system"],
           "prompt": _prompt(task, context, node, fmt, notes=notes, previous=previous),
           "cost": profile.get("cost")}
    if fmt:
        out.update(format=fmt[0], schema=fmt[1])
    if profile["model"] == CMD:
        out.update(command=profile["command"], args=profile["args"])
    agentic = profile.get("agentic")
    if agentic:
        # 人工交代码用（workflow_ctl.submit_files）：这一步在哪个目录干活、用不用项目 venv、测试命令
        root = engine.workdir.resolve()
        out["cwd"] = Path(agentic["cwd"]).relative_to(root).as_posix() or "."
        out["venv"] = bool(agentic.get("venv"))
        test_cmd = engine.expand("{test_cmd 或 }")
        if isinstance(test_cmd, str) and test_cmd.strip():
            out["test_cmd"] = test_cmd.strip()
    return out


def call_agent(engine, name, task, context=None, model=None, node=None, fmt=None, notes=None, previous=None,
               command=None):
    # command：节点写了「指令」。换成别的卡（人、AI）来做这一步时用不到它
    profile = load_agent(engine, name, model, command=command)
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
    if profile["model"] == CMD:
        # 机械步骤：不调模型（假客户端也不消耗回复），结果有格式就照样校验
        engine._wf_last_call["executor"] = f"cmd:{profile['command']}"
        result = run_cmd(engine, profile)
        errors = check_format(fmt, result)
        if errors:
            engine._wf_last_call["raw"] = json.dumps(result, ensure_ascii=False)[:20000]
            raise DSLError(f"命令步骤「{name}」的结果不符合格式 {fmt[0]}：" + "；".join(errors[:5]))
        return result
    if profile["model"] == HUMAN:
        raise DSLError(f"「{name}」是人：这一步要人在查看器上交结果（受控运行会在这里停下等），不会调模型")
    if profile["model"] == MUSE:
        raise DSLError(f"「{name}」交给 Muse 自己做：受控运行会在这里停下、往 musebatch 队列投任务，"
                       f"Muse 认领后 set_task 交结果，不会调模型")
    from tools import llm_router as _router
    _router.LAST_USAGE["value"] = None
    try:
        # 离线的假客户端（测试、mock）照旧走 client，不真去起 claude，同 RouterClient 的约定
        if submit:
            from tools import llm_router
            reply = llm_router.submit_call(prompt, profile["system"], profile["model"], fmt[1],
                                           agentic=profile.get("agentic"), timeout=profile.get("timeout"),
                                           via=profile.get("via"))
        elif profile["model"].startswith("platform:") and getattr(engine.client, "offline", False) is not True:
            from tools import platform_agent
            reply = platform_agent.call(prompt, profile["system"], profile["model"], profile["agentic"], card=name)
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
