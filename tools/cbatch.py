# -*- coding: utf-8 -*-
"""CBatch：把一批提示词交给 Claude Code 的无头模式（claude -p）逐条跑。

接口跟 tools/zbatch.py 一样（describe / submit / status / wait / jobs /
cancel），换的是执行端：zbatch 交给 Windows 上的 ZBatch 服务去调 zcode，
这里直接在本机起 claude -p。

## 没有服务，只有一个后台进程

submit 起一个脱离当前进程的执行器（python -m tools.cbatch _run <job_id>），
它逐条跑任务，进度和输出写进 JOBS/<job_id>/job.json。查状态就是读这个
文件，取消就是杀执行器的进程组。

所以不用像 zbatch 那样先启动服务、找端口；调用方进程退出了，批量照样
跑完。代价是没有仪表盘——要看就 describe() 或直接看 job.json。

## 两道限制，跟 zbatch 同样的理由

**单次最多 MAX_TASKS 条。** 批量失控的代价比单次调用大得多。

**默认不放开权限。** claude -p 没人点「允许」，需要批准的工具调用会被
直接拒掉，于是默认只能读、不能写、不能随便跑命令。要写文件就显式传
permission_mode="acceptEdits" 或 allowed_tools=[...]——放不放开该是调用方
看着任务内容决定的，不该是默认值。唯一的例外是 gsb_tools：调用方已经放行了不受限的
Bash 时自动再放行它（它不增加任何权限），见 _with_gsb；submit(gsb_tools=False) 关掉。

## 每条都是新进程

claude -p 跑完就退出，下一条重新起。share 模式靠 --resume 接上一条的
会话（上下文还在），isolated 模式各条互不相干。都不会碰到 MCP 进程里
缓存旧模块的问题。

## 环境变量要洗掉一层

在 Claude Code 会话里调这个模块时，环境里带着 CLAUDECODE、
CLAUDE_CODE_SESSION_ID 这些。原样传给子进程，claude -p 会以为自己是
当前会话的子会话。所以起子进程前把它们去掉，让每条任务是独立的会话。

## 用法

    from tools import cbatch

    cbatch.describe()                         # 最近跑了什么
    j = cbatch.submit(["任务一", "任务二"])    # 提交，立刻返回
    cbatch.status(j["job_id"])                # 查进度
    cbatch.wait(j["job_id"])                  # 等跑完
    cbatch.cancel(j["job_id"])

## 执行方式 engine

默认 engine="claude"，就是上面说的 claude -p，行为不变。另外两种：

- engine="dsl"：交给 tools/dslagent，在任务的 project 目录里**直接改文件**，要求项目测试能跑。按开局测试分两条路：
  有失败 → 修 bug 路径（固定模板 → 模型规划最多 2 版）；全过 → 任务路径（模型规划最多 2 版，
  可写/删文件、改模块名，完成＝测试全过 + 结论修好 + 完成前核对）。
  没成且 fallback（默认 true）就交给 claude -p 兜底：cwd=project，提示词带上 dsl 的记录摘要和改动 diff；
  兜底的权限沿用这批的 permission_mode / allowed_tools（给了任一个就照用户的）；都没给就是 acceptEdits +
  PROJECT_TOOLS（Read/Edit/Write/Grep/Glob、python/pytest/unittest、ls/cat/head/tail/wc/diff、git diff/status）
  + 测试命令，不放开任意 Bash / 装包 / 联网 / rm / git commit、push。
- engine="auto"：执行时判定（decide()）。先做能力检查（auto.capability_gaps：装依赖/联网/任意 shell/改仓库外
  文件/浏览器/交互式调试）→ 命中就 claude。再走规则（auto.decide_auto）：没 project / 测试跑不起来 → claude；
  初始有失败且（给了 test_cmd 或提示词里有失败测试 / Traceback）→ dsl 修 bug；初始全过、没有报错说法、任务文本里
  抽得出明确产物 → dsl 任务路径。规则拿不准的两种（全过但抽不出产物；有失败但没报错说法）再做**一次**短分类
  （ROUTE_JUDGE，问 JSON {route, needs, reason}，见 ROUTE_PROMPT）：needs 非空或 route=claude → claude；超时、
  格式不对 → claude。判定理由、来源（能力检查/规则/短分类）和分类耗时记在 engine_reason、route。
  判给 claude 且给了 project 的，claude -p 在 project 里跑（权限同下面的兜底）；没给 project 的照旧在 cwd 里跑。
- engine="dsl" 也做能力检查，但只在 engine_warning 里记警告，不改道（尊重调用方的显式选择）。
- 早退回：dsl 任务路径第 1 版计划卡在「缺能力 / 白名单外动词」上时 dslagent 不写第 2 版，直接交 claude 兜底
  （dsl_early_exit 记原因）。

规划路径：提交时环境变量 DSLAGENT_PLANNER（如 v2）记进这批的 options.dsl_planner，起 dsl 进程时原样设给它
（dsl_options 的 planner 逐条覆盖）；不设就是 dslagent 的缺省路径。
资料包：dsl_options 的 pack（如 code）设成 dsl 进程的 DSLAGENT_PACK（验收 DSLAGENT_VERIFY 缺省跟随它）；不设用环境里的 / 缺省 code。
非 code 的包（如 dslproj）另加命令行 --pack，走统一入口 entry.run_pack（v2 规划路径，与 DSLAGENT_PLANNER 无关）；dsl_options.scope（字符串或列表，路径 / glob）传 --scope。
取值不认识在提交时就报错，列出可用的（见 tools/dslagent/packs/）。
规划方式：只有一种——任务原文 + 文件大纲 + 只读 dsl 工具按需读代码。老的 plan_mode=full（资料包全文 + 补查）已移除：dsl_options.plan_mode 传 full
（或别的值）提交时报错，传 read 等于没传；DSLAGENT_PLAN_MODE 环境变量同。
子任务方式：dsl_options 的 subtask（json 缺省 / tool）设成 dsl 进程的 DSLAGENT_SUBTASK（计划里的 派任务 / 并行派任务）：json = 子任务只回 JSON，改法由计划里的
改文件 套用；tool = 子任务自己挂可写的 dsl 工具（读片段 / 搜索代码 / 查引用 / 改文件 / 写文件）读和改，最后回 JSON（只支持 claude 做 sub；出问题退回 json）。
取值不对在提交时报错；不给就看提交时环境里的 DSLAGENT_SUBTASK，再缺省 json。
按步骤指定模型：dsl_options.models = {plan, sub, fix, bound}（或一个字符串 = 四步都用它），没写的步骤 sonnet。
plan = 规划 / 规划重写，sub = 计划里的 问 / 问JSON / 派任务 / 并行派任务，fix = 验收补改，bound = 边界复核及其补改。
模型串：sonnet / opus / haiku（或完整 claude 模型名）；codex:<模型>[:<强度>]（强度缺省 medium）；grok[:<强度>]（low|medium|high|xhigh，缺省 low）；
opencode:<provider/model>；goose[:<模型>[:<强度>]]（goose run，provider / 登录用 goose 自己的配置，如 goose:gpt-6-luna；模型缺省取 goose 配置）。
提交时校验，不合格直接报错：规划只支持 claude / codex / grok / goose（grok 用自带只读工具读代码，codex / goose 挂只读 dsl 工具；opencode 不能做规划），
subtask=tool（DSLAGENT_SUBTASK=tool）时 sub 只支持 claude。顶层 model 仍是执行任务那个 claude 的模型，也仍透传成规划模型，但 models.plan 写了以它为准。

dsl 在独立进程里跑（python -m tools.dslagent run），记录在任务目录 task_<n>/ 下；每条任务的
engine_used（template / plan / plan_task / claude_fallback / claude）、versions、calls、cost_usd、seconds、calls_log
都写在 job.json 里。

## 并发

isolated 模式下 claude 任务和 dsl 任务分两条道：claude 道并发 concurrency（默认 1，按提交顺序），dsl 道
（engine=dsl/auto）并发 dsl_concurrency（默认 DSL_CONCURRENCY=3：机器 3.8G，每条 dsl 常驻 1–2 个 claude 进程）。
auto 判给 claude 的那条在 dsl 道里判完后排到 claude 道的名额上跑。同一个 project 的 dsl/auto 任务按提交顺序
一条接一条（直接改同一批文件）。
share 模式照旧逐条跑。

## 分流日志

每条任务结束追加一行到 ROUTING_LOG（~/.claude-batch/routing.jsonl）：提示词哈希、请求的 engine、auto 判定
（路线、来源、理由、分类耗时）、engine_used、成功与否、耗时、费用。routing_stats() 按路线汇总成功率/耗时/费用。
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from .zcode_tool import UnsafeWorkdirError, check_workdir

ROOT = Path(__file__).resolve().parents[1]

# 任务目录。环境变量可以改，测试用临时目录。
JOBS = Path(os.environ.get("CBATCH_HOME")
            or Path.home() / ".claude-batch" / "jobs")

# 执行端。测试换成假的 claude，不花钱也不联网。
#
# PATH 里找不到就退到默认安装位置：MCP 服务（zmcp.service）是 systemd
# 起的，PATH 里没有 ~/.local/bin，只写 "claude" 在那边一定找不到。
CLAUDE_BIN = (os.environ.get("CBATCH_CLAUDE") or shutil.which("claude")
              or str(Path.home() / ".local" / "bin" / "claude"))

MAX_TASKS = 10

# 并发，见模块文档「并发」
DSL_CONCURRENCY = 3
MAX_CONCURRENCY = 5

# 分流日志，见模块文档「分流日志」
ROUTING_LOG = Path(os.environ.get("CBATCH_ROUTING") or JOBS.parent / "routing.jsonl")

# 执行方式，见模块文档「执行方式 engine」
ENGINES = ("claude", "dsl", "auto")
# dsl 执行器的命令。测试换成假的，不调模型。
DSL_CMD = os.environ.get("CBATCH_DSL", "").split() or [sys.executable, "-m", "tools.dslagent"]

# 默认模型。不设的话用 Claude Code 自己的默认（Opus），批量任务多是跑命令、
# 贴结果这类活，用不着，一条贵五倍。要别的就在 submit 里传 model。
DEFAULT_MODEL = "sonnet"

# model="auto"：先让一个便宜的评估调用把整批任务看一遍，每条分一档。
#
# 一次评估整批，不是每条评一次：多花的是一次调用（约两分钱、几秒），
# 跟任务条数无关。评估在执行器里做，submit 照样立刻返回。
#
# 评估失败（超时、输出不是要的格式、给了不认识的档）就整批退回
# AUTO_FALLBACK，不让任务卡住——选错档的代价是贵一点或差一点，任务
# 跑不了的代价更大。失败原因记在 job.json 的 auto 里。
#
# 评估只给难度档，档到 (模型, effort) 的对应在这里定：换模型只改这张表，
# 不用改提示词。最低一档原来是 haiku，Haiku 4.5 是上一代（知识截止
# 2025-02），退役日期「不早于 2026-10-15」；Sonnet 5.5 低 effort 在官方
# 测评上远强于它、按任务算花费也差不多，所以换成 sonnet + low。
# effort 为 None 就不带 --effort，用 claude 自己的默认。
AUTO_TIERS = {"easy": ("sonnet", "low"),
              "normal": ("sonnet", None),
              "hard": ("opus", None)}
AUTO_JUDGE = ("sonnet", "low")
AUTO_FALLBACK = (DEFAULT_MODEL, None)
AUTO_TIMEOUT = 90
# 每条提示词给评估看的长度上限。难度看开头基本就够了，整段塞进去是白花钱。
AUTO_PEEK = 2000

AUTO_PROMPT = """下面是一批要交给编程助手（Claude Code，能读写文件、跑命令）执行的任务。
给每条任务定一个难度档，在够用的前提下选低的：

- easy：机械的活。跑一条命令贴输出、读文件摘一段、按明确说明改一两处、简单问答。
- normal：常规开发。写一个函数或一个小模块、改 bug、写测试、读几个文件后总结。
- hard：难的活。跨多个文件的设计或重构、原因不明的排查、要权衡取舍的方案、
  需求含糊要自己判断的。

只输出一个 JSON 数组，不要别的文字、不要代码块标记。每条任务一个对象，
按编号顺序：[{"i": 1, "tier": "easy", "reason": "一句话理由"}, ...]

"""

# engine=auto 规则拿不准时的短分类（每条至多一次）。跟 model=auto 的评估同一套做法：不开工具、不连 MCP、
# 只看提示词；超时或输出不对就回落 claude——判给 claude 只是贵一点，判错给 dsl 要白跑一趟再兜底。
ROUTE_JUDGE = ("sonnet", "low")
ROUTE_TIMEOUT = int(os.environ.get("CBATCH_ROUTE_TIMEOUT") or 60)
ROUTE_PEEK = 3000
ROUTES = ("dsl_task", "dsl_bugfix", "claude")

# 给分类看的 dsl 能力清单（动词细节见 tools/dslagent/prompts.py 的 VERBS）
DSL_ABILITY = """dsl 执行端只能用这些动词，在项目目录里自动完成任务，靠项目测试验收：
- 列文件 / 搜索代码（正则）/ 读片段：读项目里的任何文本文件
- 改文件：按原文精确替换（可一次改多个文件多处）
- 写文件：新建或整份覆盖项目内的非测试文件（.py/.json/.csv/.md 等）
- 删文件：删项目内非测试文件
- 改模块名：挪模块并更新所有 import / 调用，可留兼容层
- 运行代码：跑 ≤30 行只读 Python 看中间值（10 秒、不联网、不许写文件、不许子进程）
- 跑测试：只能跑项目的测试命令
- 问模型：每步可以让模型读代码后给出修改（模型本身会写代码、会分析）
做不到：装依赖、联网、跑测试以外的命令或 shell 脚本、改项目外的文件、改测试文件、浏览器/GUI、交互式调试。
验收方式：测试全过、测试文件没动，再逐条核对任务点名的产物（文件/函数名/JSON 键等）；
所以任务目标要能落到具体文件和代码改动上。没有具体目标的开放式要求（「看看哪里能优化」「整理一下代码」）验收不了。"""

ROUTE_PROMPT = """你负责给一条编程任务分流，二选一的执行端：
A. dsl：下面这个受限的自动执行端，便宜快，但只会用列出的动词；
B. claude：通用编程助手（能跑任意命令、装依赖、联网、自己判断开放式需求），贵一些。

{ability}

【项目开局测试】{state}
【项目文件概况】
{files}

【任务】
{task}

判断：
- route=dsl_task：测试全过、任务是加功能/改代码/改数据文件/重构等，目标能落到具体文件或函数上，dsl 动词够用；
- route=dsl_bugfix：测试有失败，任务就是让这些失败的测试通过（修 bug、按测试补实现），dsl 动词够用；
- route=claude：需要动词做不到的事，或目标开放、验收不了，或拿不准。
needs 列出任务里超出 dsl 能力的需求（没有就空列表）。
只输出一行 JSON，不要别的文字、不要代码块：{{"route": "dsl_task|dsl_bugfix|claude", "needs": ["…"], "reason": "一句话"}}"""

# 单条任务的时间上限（秒）。超时就杀掉这一条，接着跑下一条。
TASK_TIMEOUT = 600

# 拼进系统提示的交代。理由见 zbatch.PREAMBLE：执行端不会认输，没人告诉它
# 什么时候该停，它会一直重试到被超时杀掉，什么都留不下。
#
# 走 --append-system-prompt 而不是拼在提示词前面：每条都带上，share 模式
# 续接会话时也不会被当成用户说的话重复一遍。
PREAMBLE = """这是批量任务里的一条，没有人在旁边看着，也没法回答你的问题。

1. 同一件事失败两次就停下来报告：失败在哪一步、报的什么错、本来想做什么。
2. 单条任务有时间上限，超时会被直接杀掉。输出很长时先停下来说明。
3. 没让你改文件的任务就别改，只报告。
4. 最后一段回复就是这条任务的结果，写清楚结论。
5. 运行程序、跑测试必须在前台跑完、看到结果再汇报，不得放到后台后就结束这条任务；需要等待就在前台轮询（sleep 后再查），直到拿到结果。"""

# allowed_tools 放行了 gsb_tools 时追加在 PREAMBLE 后面，没放行就不写，免得提示不存在的工具。
# 为什么要写：这些工具在子进程里是延迟加载的（只有名字没有 schema），任务书又全是写死的
# shell 命令，不提醒的话执行端一次都不会调，全靠 Bash（K69：71 次 Bash，gsb 工具 0 次）。
# 第 5 条的「sleep 后再查」和 run_wait / wait_pid 冲突，这时换成下面第 8 条。
GSB_TOOLS_PREFIX = "mcp__gsb_tools"
PREAMBLE_TOOLS = """工具用法（gsb_tools）：
6. 这些工具一开始只有名字，先 ToolSearch 查询 "select:mcp__gsb_tools__read_files,mcp__gsb_tools__run_wait,mcp__gsb_tools__multi_edit,mcp__gsb_tools__probe,mcp__gsb_tools__probe_wait,mcp__gsb_tools__review,mcp__gsb_tools__review_wait,mcp__gsb_tools__verify,mcp__gsb_tools__verify_wait,mcp__gsb_tools__wait_pid" 加载，再调用。
7. 读文件用 read_files（可一次多个、带行号范围、glob），不要用 shell 的 cat/head/tail/sed -n 读；grep/rg 搜索照用，看搜到的内容再回 read_files。同一文件改 2 处以上、或一次改多个文件，用 multi_edit。
8. 测试、构建等长命令用 run_wait 阻塞等结果，后台进程用 wait_pid；不要 sleep 轮询，sleep 超过 10 秒一律改用 wait_pid。（取代第 5 条括号里的 sleep 做法，其余照第 5 条：必须拿到结果再汇报。）
9. 要读很多文件再对照 / 总结时，派给 probe（只读）只收结论，互不相干的几块 wait=false 并行派再 probe_wait；探针不改文件，改代码自己做，关键结论自己抽查。
10. 改了代码的任务，等代码改完、报告草稿写好后，在 commit/push 前调 review 做初步审查（给 task_file，有草稿就给 report_file）；不要做到一半就调，它审的是当时的状态，会把还没做的步骤报成问题。意见只是线索不是定论，核实后再改，报告里附上审查结论。
11. 全量回归、起服务实测交给 verify（wait=false + verify_wait 可并行），不要自己现写一次性验证脚本；跑完核对结论和证据再采信。verify 的沙箱里被验项目只读（.git 也是），需要 git worktree 的基线对比它做不了，会返回「无法验证」，这种基线对比自己在 shell 里做，并在报告里写明。"""


def _system_prompt(o: dict) -> str:
    if not any(str(t).startswith(GSB_TOOLS_PREFIX) for t in o["allowed_tools"]):
        return PREAMBLE
    return PREAMBLE + "\n" + PREAMBLE_TOOLS


def _with_gsb(allowed_tools, on: bool = True) -> list:
    """调用方放行了不受限的 Bash 时，默认再放行 gsb_tools。

    只在这种情况追加：不受限的 Bash 已经能跑任意命令、改任意文件，gsb_tools（run_wait 就是 shell，
    multi_edit 就是改文件）不增加任何权限。默认只读的调用、只给 acceptEdits 的调用、只放行
    Bash(ls:*) 这类受限命令的调用都不追加——给它们加等于悄悄升级权限，跟「默认不放开权限」冲突。
    调用方已经写了 gsb_tools 就不重复加；on=False（submit 的 gsb_tools=False）整个关掉。
    """
    tools = list(allowed_tools or [])
    if on and "Bash" in tools and not any(str(t).startswith(GSB_TOOLS_PREFIX) for t in tools):
        tools.append(GSB_TOOLS_PREFIX)
    return tools

# 要从子进程环境里去掉的变量，见模块文档「环境变量要洗掉一层」
_ENV_DROP_PREFIX = ("CLAUDE_CODE_",)
_ENV_DROP = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"}


class CBatchError(Exception):
    """参数不对，或者任务不存在。"""


# ----------------------------------------------------------------------
# job.json 读写


def _job_dir(job_id: str) -> Path:
    return JOBS / job_id


def _load(job_id: str) -> dict:
    f = _job_dir(job_id) / "job.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CBatchError(f"没有这个任务：{job_id}") from None


def _save(d: dict) -> None:
    """先写临时文件再改名：查状态的人随时在读，不能读到写了一半的。"""
    f = _job_dir(d["id"]) / "job.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, f)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _settle(d: dict) -> dict:
    """job.json 说在跑、执行器却已经没了（被 kill -9、机器重启），改成 died。

    不改的话 wait 会一直等一个永远不会结束的任务。
    """
    if d.get("status") == "queued" and not d.get("pid"):
        # 执行器还没起来写 pid。刚提交时正常，一分钟还没动静就是起不来了
        # （看 runner.log）
        age = (datetime.now() - datetime.fromisoformat(d["created"])).total_seconds()
        if age < 60:
            return d
    if d.get("status") in ("queued", "running") and not _pid_alive(d.get("pid")):
        d["status"] = "died"
        d["note"] = "执行器进程已经不在了，job.json 停在中途"
        for t in d["tasks"]:
            if t["status"] == "running":
                t["status"] = "died"
    return d


# ----------------------------------------------------------------------
# 对外接口


def _engine_fields(it: dict, i: int, engine, project, test_cmd, fallback,
                   dsl_options) -> None:
    """定下一条任务的 engine 和 dsl 字段（任务里的优先于这批的默认值），不对就报错。

    claude 任务只多一个 engine 键，别的字段一律不带——它的执行跟原来一字不差。
    """
    eng = it.pop("_engine", engine) or "claude"
    own = {k: it.pop("_" + k) for k in ("project", "test_cmd", "fallback", "dsl_options")
           if "_" + k in it}
    if eng not in ENGINES:
        raise CBatchError(f"第 {i} 条：engine 只能是 {' / '.join(ENGINES)}，收到：{eng!r}")
    it["engine"] = eng
    if eng == "claude":
        return
    proj = own.get("project", project)
    if eng == "dsl" and not proj:
        raise CBatchError(f"第 {i} 条：engine=dsl 要给 project（要修的项目目录，dsl 会直接改里面的文件）")
    if proj:
        # 规则同 cwd：家目录、/、含凭证的目录不行
        try:
            proj = check_workdir(proj)
        except UnsafeWorkdirError as e:
            raise CBatchError(f"第 {i} 条：project 不能用：{e}") from None
    fb = own.get("fallback", fallback)
    if isinstance(fb, str):
        fb = fb.strip().lower() not in ("0", "false", "no", "否", "")
    opts = own.get("dsl_options", dsl_options) or {}
    if not isinstance(opts, dict):
        raise CBatchError(f"第 {i} 条：dsl_options 要是字典，收到：{opts!r}")
    if opts.get("pack"):
        from tools.dslagent import packs as _packs
        try:
            _packs.pick(str(opts["pack"]))
        except ValueError as e:
            raise CBatchError(f"第 {i} 条：dsl_options.pack 不对：{e}") from None
    if opts.get("plan_mode"):
        from tools.dslagent import v2 as _v2
        try:
            _v2.check_plan_mode(str(opts["plan_mode"]))
        except ValueError as e:
            raise CBatchError(f"第 {i} 条：dsl_options.plan_mode 不对：{e}") from None
    if opts.get("subtask"):
        from tools.dslagent import dslcheck as _dc
        try:
            _dc.check_mode(str(opts["subtask"]))
        except ValueError as e:
            raise CBatchError(f"第 {i} 条：dsl_options.subtask 不对：{e}") from None
    if opts.get("models"):
        from tools.dslagent import engines as _eng
        try:
            _eng.validate(opts["models"], (str(opts.get("subtask") or os.environ.get("DSLAGENT_SUBTASK") or "json")).strip().lower())
        except ValueError as e:
            raise CBatchError(f"第 {i} 条：dsl_options.models 不对：{e}") from None
    it.update(project=proj or None, test_cmd=own.get("test_cmd", test_cmd) or None,
              fallback=bool(fb), dsl_options=opts, engine_reason="")


def submit(tasks, name: str = "", mode: str = "isolated", cwd: str = None,
           model: str = DEFAULT_MODEL, permission_mode: str = None,
           allowed_tools=None, timeout: int = TASK_TIMEOUT,
           preamble: bool = True, engine: str = "claude", project: str = None,
           test_cmd: str = None, fallback: bool = True,
           dsl_options: dict = None, concurrency: int = 1,
           dsl_concurrency: int = DSL_CONCURRENCY, gsb_tools: bool = True) -> dict:
    """提交一批任务，立刻返回，不等跑完。

    tasks：提示词列表，或 {prompt, outfile} 字典列表。outfile 给了的话，
        那条的最终回复另存一份到这个文件（相对 cwd）。
    mode="isolated"：每条独立。默认这个：一条跑偏不会带歪后面的。
    mode="share"：后一条用 --resume 接前一条的会话，适合「先读、再改」。
        前一条失败了，后一条就从头开新会话，不接一个坏掉的上下文。
    cwd：claude 在哪个目录跑，决定它能看到哪些文件和项目设置。默认当前目录。
        不收 ~、/、家目录和含 .ssh 等凭证的父目录（当前目录是这些也不行）。
    model：默认 sonnet（DEFAULT_MODEL）。传 None 或空串就不带 --model，
        用 Claude Code 自己的默认。传 "auto" 就先评估难度，每条分到
        AUTO_TIERS 里的一档（模型加 effort），见 AUTO_PROMPT；分到的结果和
        理由记在每条任务的 model、effort、model_reason 里。
    permission_mode / allowed_tools：原样传给 claude，见模块文档「默认不
        放开权限」。
    gsb_tools：默认 True。allowed_tools 里有不受限的 Bash 时自动再放行 mcp__gsb_tools
        （并在系统提示里追加工具用法，见 PREAMBLE_TOOLS）；其它情况不追加，见 _with_gsb。
        传 False 关掉，任务只会拿到调用方写的那些工具。
    timeout：单条任务的秒数上限。dsl 任务的 dsl 部分和兜底的 claude 各算一次。
    engine：claude（默认）/ dsl / auto，见模块文档「执行方式 engine」。
        project、test_cmd、fallback、dsl_options 是这批的默认值，tasks 里的字典可以逐条覆盖
        （{"prompt": …, "engine": "dsl", "project": "/path", "test_cmd": "…", "fallback": false}）。
        engine=dsl 必须有 project（任务里或这里）；test_cmd 缺省按项目探测 pytest / unittest。
        dsl_options 是调试用的：{"max_plan": 2, "template": true, "inject": {...}, "planner": "v2", "pack": "code", "subtask": "json",
        "models": {"plan": "opus", "sub": "codex:gpt-5.1:low", "fix": "sonnet", "bound": "grok"}}（models 见模块文档）。
    concurrency / dsl_concurrency：isolated 模式下 claude 道、dsl 道（engine=dsl/auto）各自的并发上限，
        默认 1 / DSL_CONCURRENCY（3），最多 MAX_CONCURRENCY；见模块文档「并发」。share 模式逐条跑，不看这两个。

    返回 {"job_id", "status", "tasks", "dir"}。
    """
    items = []
    for t in tasks:
        if isinstance(t, str) and t.strip():
            items.append({"prompt": t, "outfile": ""})
        elif isinstance(t, dict) and t.get("prompt"):
            items.append({"prompt": t["prompt"],
                          "outfile": t.get("outfile", "")})
            for k in ("engine", "project", "test_cmd", "fallback", "dsl_options"):
                if k in t:
                    items[-1]["_" + k] = t[k]
        else:
            raise CBatchError(f"任务要是非空字符串或含 prompt 的字典，收到：{t!r}")

    if not items:
        raise CBatchError("一条任务都没有")
    if len(items) > MAX_TASKS:
        raise CBatchError(f"一次最多 {MAX_TASKS} 条，这次给了 {len(items)} 条。")
    if mode not in ("share", "isolated"):
        raise CBatchError(f"mode 只能是 share 或 isolated，收到：{mode}")
    # bypassPermissions 等于什么都不拦，还没人看着。真要放开到那一步，该是
    # 人在终端里自己跑 claude，不是一次工具调用的参数。MCP 那边谁都能传
    # 这个参数，所以在这里挡，不指望调用方自觉。
    if permission_mode == "bypassPermissions":
        raise CBatchError("不收 bypassPermissions：批量任务没人看着，"
                          "要放开就用 acceptEdits 或 allowed_tools 指定到具体工具")
    for k, v in (("concurrency", concurrency), ("dsl_concurrency", dsl_concurrency)):
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= MAX_CONCURRENCY:
            raise CBatchError(f"{k} 要是 1–{MAX_CONCURRENCY} 的整数，收到：{v!r}")
    if shutil.which(CLAUDE_BIN) is None:
        raise CBatchError(f"找不到 {CLAUDE_BIN}，Claude Code 装了吗？")
    for i, it in enumerate(items, 1):
        _engine_fields(it, i, engine, project, test_cmd, fallback, dsl_options)

    # 家目录、/ 不行：claude 能读工作目录下的一切，那里有 .ssh、
    # .git-credentials 和各 CLI 的登录凭证。规则同 zcode_tool.check_workdir
    try:
        cwd = check_workdir(cwd or os.getcwd())
    except UnsafeWorkdirError as e:
        raise CBatchError(f"cwd 不能用：{e}") from None

    # 编号带毫秒：jobs() 按编号排新旧，只到秒的话同一秒提交的几批顺序是
    # 随机的（后面那段是随机串）。测试连着提交时撞上的。
    now = datetime.now()
    job_id = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}" \
        + uuid.uuid4().hex[:4]
    jd = _job_dir(job_id)
    jd.mkdir(parents=True)

    d = {
        "id": job_id, "name": name, "mode": mode, "cwd": cwd,
        "status": "queued", "created": _now(), "started": None,
        "finished": None, "pid": None,
        "options": {"model": model, "permission_mode": permission_mode,
                    "allowed_tools": _with_gsb(allowed_tools, gsb_tools),
                    "timeout": int(timeout), "preamble": bool(preamble),
                    "engine": engine, "concurrency": concurrency,
                    "dsl_concurrency": dsl_concurrency,
                    "dsl_planner": os.environ.get("DSLAGENT_PLANNER") or None},
        "auto": None,
        "tasks": [dict(it, status="pending", output="", error="",
                       model=None if model == "auto" else (model or None),
                       effort=None, model_reason="",
                       session_id=None, cost_usd=None, turns=None,
                       seconds=None, engine_used=None, versions=None,
                       calls=None, calls_log=None) for it in items],
    }
    _save(d)

    # 经一个中间进程起执行器（_detach），中间进程马上退出、在这里收掉。
    # 执行器于是成了孤儿、归 init 管，跑完由 init 回收。
    #
    # 直接 Popen 的话执行器是调用方的子进程：调用方（MCP 服务、测试）
    # 活着又不 wait 它，它跑完就成了僵尸，kill(pid, 0) 照样成功——
    # 「执行器死了」永远判不出来，wait 会空等到超时。测试撞上的。
    subprocess.run([sys.executable, "-m", "tools.cbatch", "_detach", job_id],
                   cwd=str(ROOT), stdin=subprocess.DEVNULL, check=True,
                   env=dict(os.environ, CBATCH_HOME=str(JOBS)))

    # pid 由执行器自己写进 job.json，这里不再写：执行器可能已经开跑、把
    # status 改成 running 了，这时候再存一次 d 会把它改回 queued。
    return {"job_id": job_id, "status": "queued", "tasks": len(items),
            "dir": str(jd)}


def status(job_id: str, full: bool = False) -> dict:
    """查一个任务的进度和输出。

    full=False 时每条输出截断到 500 字，理由同 zbatch.status：批量输出
    加起来很容易几万字，全塞进对话里挤掉上下文。
    """
    d = _settle(_load(job_id))
    done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
    d["progress"] = f"{done}/{len(d['tasks'])}"
    if not full:
        for t in d["tasks"]:
            out = t.get("output") or ""
            if len(out) > 500:
                t["output"] = out[:500] + f"…（还有 {len(out) - 500} 字）"
    return d


def wait(job_id: str, timeout: int = 300, every: int = 5) -> dict:
    """等一个任务跑完，返回最终状态。超时返回当前状态，不报错——
    「还在跑」本身就是有用的信息。"""
    deadline = time.time() + timeout
    while True:
        d = status(job_id)
        if d["status"] not in ("queued", "running"):
            return d
        if time.time() >= deadline:
            d["_note"] = f"等了 {timeout} 秒还在跑，这是中途状态"
            return d
        time.sleep(every)


def jobs(limit: int = 10) -> list:
    """最近的任务（新的在前），每个只给概要。"""
    if not JOBS.is_dir():
        return []
    out = []
    for jd in sorted(JOBS.iterdir(), reverse=True):
        if not (jd / "job.json").is_file():
            continue
        d = _settle(_load(jd.name))
        done = sum(t["status"] not in ("pending", "running") for t in d["tasks"])
        out.append({"id": d["id"], "name": d["name"], "status": d["status"],
                    "progress": f"{done}/{len(d['tasks'])}",
                    "created": d["created"]})
        if len(out) >= limit:
            break
    return out


def cancel(job_id: str) -> dict:
    """取消：整组杀掉执行器和它正在跑的那条 claude，没跑的标成 cancelled。"""
    d = _load(job_id)
    if d["status"] not in ("queued", "running"):
        return {"job_id": job_id, "status": d["status"], "note": "已经结束了"}
    if not d.get("pid"):
        raise CBatchError("执行器还没起来，过几秒再取消")
    # 先落标记再杀：执行器被杀前要是刚好写了一次 job.json，标记不会被盖掉
    # ——它每次写之前都会重读这个标记（见 _run）。
    (_job_dir(job_id) / "cancel").touch()
    try:
        os.killpg(d["pid"], signal.SIGTERM)
    except (ProcessLookupError, TypeError):
        pass
    for _ in range(20):
        if not _pid_alive(d["pid"]):
            break
        time.sleep(0.1)
    d = _load(job_id)
    d["status"] = "cancelled"
    d["finished"] = _now()
    for t in d["tasks"]:
        if t["status"] in ("pending", "running"):
            t["status"] = "cancelled"
    _save(d)
    return {"job_id": job_id, "status": "cancelled"}


def describe() -> str:
    """人话版的概况：执行端在不在、最近跑了什么。排查时先跑这个。"""
    exe = shutil.which(CLAUDE_BIN)
    lines = [f"执行端：{exe or f'找不到 {CLAUDE_BIN}'}",
             f"任务目录：{JOBS}"]
    js = jobs(5)
    lines.append(f"最近 {len(js)} 个任务" if js else "还没有任务")
    for j in js:
        lines.append(f"  {j['id']}  {j['status']:10} {j['progress']:6} "
                     f"{j['name'][:30]}")
    return "\n".join(lines)


def decide(prompt: str, project: str = None, test_cmd: str = None, classify: bool = True,
           cwd: str = None) -> dict:
    """engine=auto 的判定（只判不跑，可单独调用）：能力检查 → 规则 → 规则拿不准时一次短分类。

    返回 {engine: dsl|claude, kind, reason, source: 能力检查|规则|短分类|出错, test_cmd, needs,
    classify: {route, needs, reason, seconds, ok, error, cost_usd} 或 None}。classify=False 时拿不准就照规则给 claude。
    """
    from .dslagent import auto as runner
    try:
        r = runner.decide_auto(prompt, project, test_cmd)
    except Exception as e:   # 判定本身坏了不该让任务卡住，退回默认
        return {"engine": "claude", "kind": None, "source": "出错", "test_cmd": None, "needs": [], "classify": None,
                "reason": f"判定出错（{type(e).__name__}: {e}），用 claude"}
    out = {"engine": r["engine"], "kind": r.get("kind"), "reason": r["reason"], "test_cmd": r.get("test_cmd"),
           "needs": list(r.get("needs") or []), "classify": None,
           "source": "能力检查" if r.get("needs") else "规则"}
    unsure = r.get("uncertain")
    if not unsure or not classify:
        return out
    failing = bool((r.get("initial") or {}).get("failing"))
    c = _route_classify(prompt, project, r.get("initial") or {}, cwd)
    out.update(classify=c, source="短分类", needs=c["needs"])
    head = f"规则拿不准（{r['reason']}）→ 短分类 {c['seconds']}s："
    if not c["ok"]:
        out.update(engine="claude", kind=None, reason=head + f"失败（{c['error']}），回落 claude")
    elif c["needs"]:
        out.update(engine="claude", kind=None,
                   reason=head + f"{c['route']}，但需要 dsl 做不到的：{'、'.join(c['needs'])} → claude；{c['reason']}")
    elif c["route"] == "dsl_task" and not failing:
        out.update(engine="dsl", kind="task", reason=head + f"dsl_task → 任务路径；{c['reason']}")
    elif c["route"] == "dsl_bugfix" and failing:
        out.update(engine="dsl", kind="bugfix", reason=head + f"dsl_bugfix → 修 bug 路径；{c['reason']}")
    elif c["route"] == "claude":
        out.update(engine="claude", kind=None, reason=head + f"claude；{c['reason']}")
    else:
        why = "测试有失败，dsl 会走修 bug 路径、不是这个任务" if failing else "测试全过，没有失败测试可按修 bug 验收"
        out.update(engine="claude", kind=None, reason=head + f"{c['route']}，但{why} → claude；{c['reason']}")
    return out


def _project_overview(project, limit: int = 60) -> str:
    """给分类看的项目文件清单：相对路径 + 行数，跳过隐藏目录、虚拟环境、缓存。"""
    skip = {"__pycache__", "node_modules", "venv", ".venv", "env", "site-packages", "build", "dist"}
    rows = []
    for dp, dns, fns in os.walk(project):
        dns[:] = sorted(x for x in dns if not x.startswith(".") and x not in skip)
        for fn in sorted(fns):
            if fn.startswith(".") or fn.endswith((".pyc", ".pyo")):
                continue
            f = Path(dp) / fn
            try:
                n = f.read_bytes().count(b"\n") if f.stat().st_size < 2_000_000 else -1
            except OSError:
                continue
            rows.append(f"{f.relative_to(project)}（{n} 行）" if n >= 0 else f"{f.relative_to(project)}（大文件）")
    more = f"\n…还有 {len(rows) - limit} 个文件" if len(rows) > limit else ""
    return "\n".join(rows[:limit]) + more if rows else "（空）"


def _route_classify(prompt: str, project, initial: dict, cwd: str = None) -> dict:
    """规则拿不准时的一次短分类，见 ROUTE_PROMPT。不抛异常：超时、格式不对都记在 error 里，ok=False。"""
    st = ("有失败：" if initial.get("failing") else "全部通过：") + (initial.get("summary") or "")[:600]
    body = ROUTE_PROMPT.format(ability=DSL_ABILITY, state=st, files=_project_overview(project) if project else "（没给项目）",
                               task=(prompt or "")[:ROUTE_PEEK])
    jm, je = ROUTE_JUDGE
    cmd = [CLAUDE_BIN, "-p", body, "--output-format", "json", "--model", jm] + (["--effort", je] if je else []) + \
        ["--tools", "", "--strict-mcp-config", "--system-prompt", "你负责给编程任务分流。只输出 JSON。"]
    c = {"route": "claude", "needs": [], "reason": "", "seconds": 0.0, "ok": False, "error": "", "cost_usd": None,
         "judge": "/".join(x for x in ROUTE_JUDGE if x)}
    if not cwd:
        from .dslagent.common import tmp_dir
        cwd = str(tmp_dir())
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=_child_env(), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=ROUTE_TIMEOUT)
        r = json.loads(p.stdout)
        c["cost_usd"] = r.get("total_cost_usd")
        text = (r.get("result") or "").strip()
        m = re.search(r"\{.*\}", text, re.S)
        x = json.loads(m.group(0) if m else text)
        if x.get("route") not in ROUTES:
            raise ValueError(f"route 不认识：{x.get('route')!r}")
        needs = x.get("needs") or []
        if not isinstance(needs, list):
            raise ValueError(f"needs 不是列表：{needs!r}")
        c.update(route=x["route"], needs=[str(n)[:80] for n in needs if str(n).strip()][:6],
                 reason=str(x.get("reason") or "")[:200], ok=True)
    except subprocess.TimeoutExpired:
        c["error"] = f"超过 {ROUTE_TIMEOUT} 秒"
    except (json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError) as e:
        c["error"] = f"输出解析不了（{type(e).__name__}: {str(e)[:100]}）"
    except OSError as e:
        c["error"] = f"起不来（{e}）"
    c["seconds"] = round(time.time() - t0, 1)
    return c


def routing_stats(since: str = None, path: str = None) -> dict:
    """分流日志汇总：按路线（auto 判定 → 实际执行端）给条数、成功率、平均耗时、平均/总费用，另给短分类的次数和平均耗时。

    since：只算这个时间之后的（ISO 格式前缀比较，如 "2026-10-08"）。path：日志文件，默认 ROUTING_LOG。
    """
    f = Path(path) if path else ROUTING_LOG
    rows = []
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                x = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not since or (x.get("ts") or "") >= since:
                rows.append(x)

    def agg(xs):
        n = len(xs)
        secs = [x["seconds"] for x in xs if isinstance(x.get("seconds"), (int, float))]
        costs = [x["cost_usd"] for x in xs if isinstance(x.get("cost_usd"), (int, float))]
        ok = sum(1 for x in xs if x.get("ok"))
        return {"n": n, "ok": ok, "rate": round(ok / n, 3) if n else None,
                "avg_sec": round(sum(secs) / len(secs), 1) if secs else None,
                "avg_cost": round(sum(costs) / len(costs), 4) if costs else None,
                "total_cost": round(sum(costs), 4)}

    def group(key):
        g = {}
        for x in rows:
            g.setdefault(key(x), []).append(x)
        return {k: agg(v) for k, v in sorted(g.items())}

    cl = [x for x in rows if x.get("classify_sec") is not None]
    return {"log": str(f), "total": agg(rows),
            "by_route": group(lambda x: f"{x.get('engine')}:{x.get('decision') or x.get('engine')}→{x.get('engine_used')}"),
            "by_decision": group(lambda x: f"{x.get('decision') or x.get('engine')}（{x.get('source') or '-'}）"),
            "by_engine_used": group(lambda x: x.get("engine_used") or "?"),
            "classify": {"n": len(cl), "failed": sum(1 for x in cl if not x.get("classify_ok")),
                         "avg_sec": round(sum(x["classify_sec"] for x in cl) / len(cl), 1) if cl else None},
            "early_exit": sum(1 for x in rows if x.get("early_exit")),
            "warnings": sum(1 for x in rows if x.get("warning"))}


# ----------------------------------------------------------------------
# 执行器（在后台进程里跑）


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items()
            if k not in _ENV_DROP and not k.startswith(_ENV_DROP_PREFIX)}


def _classify(d: dict) -> None:
    """model="auto" 时给每条任务定档，结果写进 t["model"]、t["effort"] 和 d["auto"]。

    评估调用不开工具（--tools ""）、不连 MCP、换掉默认系统提示，在任务目录
    里跑而不是 cwd——它只需要看提示词，不该去读项目文件，也不该把项目的
    CLAUDE.md 读进来白占 token。
    """
    body = AUTO_PROMPT + "\n\n".join(
        f"### 任务 {i}\n{t['prompt'][:AUTO_PEEK]}"
        for i, t in enumerate(d["tasks"], 1))
    judge_model, judge_effort = AUTO_JUDGE
    cmd = [CLAUDE_BIN, "-p", body, "--output-format", "json",
           "--model", judge_model, "--effort", judge_effort,
           "--tools", "", "--strict-mcp-config",
           "--system-prompt", "你负责给任务评估难度。只输出 JSON。"]
    info = {"judge": f"{judge_model}/{judge_effort}", "ok": False, "error": "",
            "cost_usd": None}
    fallback = "/".join(x for x in AUTO_FALLBACK if x)
    picks = {}
    try:
        p = subprocess.run(cmd, cwd=str(_job_dir(d["id"])), env=_child_env(),
                           stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=AUTO_TIMEOUT)
        r = json.loads(p.stdout)
        info["cost_usd"] = r.get("total_cost_usd")
        text = (r.get("result") or "").strip()
        # 叮嘱了不要代码块，还是会有，剥掉
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        for x in json.loads(text):
            if x.get("tier") in AUTO_TIERS:
                picks[int(x["i"])] = (*AUTO_TIERS[x["tier"]],
                                      f"{x['tier']}：{x.get('reason', '')}")
        missing = [i for i in range(1, len(d["tasks"]) + 1) if i not in picks]
        if missing:
            info["error"] = f"第 {missing} 条没给出可用的档，用 {fallback}"
        else:
            info["ok"] = True
    except subprocess.TimeoutExpired:
        info["error"] = f"评估超过 {AUTO_TIMEOUT} 秒，整批用 {fallback}"
    except (json.JSONDecodeError, ValueError, TypeError, KeyError,
            AttributeError) as e:
        info["error"] = f"评估结果解析不了（{e}），没分到的用 {fallback}"

    for i, t in enumerate(d["tasks"], 1):
        t["model"], t["effort"], t["model_reason"] = picks.get(
            i, (*AUTO_FALLBACK, "评估没给出，用默认"))
    d["auto"] = info


def _command(d: dict, t: dict, resume: str = None) -> list:
    o = d["options"]
    cmd = [CLAUDE_BIN, "-p", t["prompt"], "--output-format", "json"]
    if resume:
        cmd += ["--resume", resume]
    if t.get("model"):
        cmd += ["--model", t["model"]]
    if t.get("effort"):
        cmd += ["--effort", t["effort"]]
    if o["permission_mode"]:
        cmd += ["--permission-mode", o["permission_mode"]]
    if o["allowed_tools"]:
        cmd += ["--allowed-tools", *o["allowed_tools"]]
    if o["preamble"]:
        cmd += ["--append-system-prompt", _system_prompt(o)]
    return cmd


def _run_one(d: dict, t: dict, resume: str = None) -> None:
    """跑一条，结果写回 t。不抛异常：一条坏了记下来，接着跑下一条。"""
    t0 = time.time()
    try:
        # 提示词走参数不走标准输入：-p 后面跟提示词是 claude 的常规用法，
        # 而且以 - 开头的提示词也不会被当成选项（它是 -p 的值）。
        p = subprocess.run(_command(d, t, resume), cwd=d["cwd"],
                           env=_child_env(), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True,
                           timeout=d["options"]["timeout"])
    except subprocess.TimeoutExpired:
        t.update(status="timeout", seconds=round(time.time() - t0, 1),
                 error=f"超过 {d['options']['timeout']} 秒，已杀掉")
        return
    t["seconds"] = round(time.time() - t0, 1)

    try:
        r = json.loads(p.stdout)
    except json.JSONDecodeError:
        # 不是 JSON 多半是 claude 自己没起来（参数错、没登录），原样留着
        t.update(status="error", output=p.stdout,
                 error=(p.stderr or f"退出码 {p.returncode}，输出不是 JSON").strip())
        return

    t.update(output=r.get("result") or "", session_id=r.get("session_id"),
             cost_usd=r.get("total_cost_usd"), turns=r.get("num_turns"))
    # 被拒的工具调用单独记：默认不放开权限，任务「成功」了但该写的文件
    # 没写，原因只在这里看得到。只留工具名，参数可能很长。
    denied = [x.get("tool_name", "?") for x in r.get("permission_denials") or []]
    if denied:
        t["denied"] = denied
    if r.get("is_error") or p.returncode != 0:
        t.update(status="error",
                 error=(r.get("subtype") or "") + (" " + p.stderr.strip()
                                                    if p.stderr.strip() else ""))
    else:
        t["status"] = "done"

    if t["outfile"] and t["output"]:
        f = Path(d["cwd"]) / t["outfile"]
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t["output"], encoding="utf-8")
        except OSError as e:
            t["error"] = (t["error"] + f" 写 outfile 失败：{e}").strip()


# ---- engine=dsl / auto


def _decide(d: dict, t: dict) -> str:
    """engine=auto：decide() 判一次，理由记进 t["engine_reason"]、判定细节记进 t["route"]。返回 dsl 或 claude。"""
    r = decide(t["prompt"], t.get("project"), t.get("test_cmd"), cwd=str(_job_dir(d["id"])))
    t["engine_reason"] = f"auto → {r['engine']}" + (f"（{r['kind']}）" if r.get("kind") else "") + \
        f"［{r['source']}］：{r['reason']}"
    c = r.get("classify")
    t["route"] = {"decision": r["engine"] + (f"/{r['kind']}" if r.get("kind") else ""), "source": r["source"],
                  "needs": r["needs"], "classify": c}
    if c and c.get("cost_usd"):
        t["route_cost_usd"] = c["cost_usd"]
    if r["engine"] == "dsl" and r.get("test_cmd"):
        t["test_cmd"] = r["test_cmd"]
    return r["engine"]


def _run_dsl(d: dict, t: dict, i: int) -> dict:
    """在独立进程里跑 dslagent（它换掉 llm_router 的后端、设环境变量，都是进程级的），读回 result.json。

    跟执行器同一个进程组：cancel 整组杀时它和它起的 claude 一起走。超时先 TERM（它会关掉常驻
    claude、写下已有记录），10 秒还在就 KILL。
    """
    tdir = _job_dir(d["id"]) / f"task_{i}"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "task.txt").write_text(t["prompt"], encoding="utf-8")
    o = t.get("dsl_options") or {}
    timeout = d["options"]["timeout"]
    cmd = [*DSL_CMD, "run", "--project", t["project"], "--task-file", str(tdir / "task.txt"),
           "--out", str(tdir), "--wall", str(max(60, timeout - 60)),
           "--max-plan", str(int(o.get("max_plan", 2)))]
    if t.get("test_cmd"):
        cmd += ["--test-cmd", t["test_cmd"]]
    if o.get("template") is False:
        cmd.append("--no-template")
    if o.get("pack") and str(o["pack"]).strip().lower() != "code":
        cmd += ["--pack", str(o["pack"]).strip().lower()]       # 非 code 的资料包走统一入口（v2 规划路径），与 DSLAGENT_PLANNER 无关；code 仍是旧命令
    if o.get("scope"):
        cmd += ["--scope", str(o["scope"]) if not isinstance(o["scope"], (list, tuple)) else ",".join(map(str, o["scope"]))]
    if o.get("inject"):
        cmd += ["--inject", json.dumps(o["inject"], ensure_ascii=False)]
    t["calls_log"] = str(tdir / "calls.json")
    env = _child_env()
    planner = o.get("planner") or d["options"].get("dsl_planner")
    if planner:
        env["DSLAGENT_PLANNER"] = str(planner)
        t["dsl_planner"] = str(planner)
    if o.get("pack"):
        env["DSLAGENT_PACK"] = str(o["pack"])
        t["dsl_pack"] = str(o["pack"])
    if o.get("subtask"):
        env["DSLAGENT_SUBTASK"] = str(o["subtask"]).strip().lower()
        t["dsl_subtask"] = env["DSLAGENT_SUBTASK"]
    if t.get("model"):
        env["DSLAGENT_PLAN_MODEL"] = str(t["model"])
    if o.get("models"):
        from tools.dslagent import engines as _eng
        t["dsl_models"] = _eng.normalize(o["models"])
        env["DSLAGENT_MODELS"] = json.dumps(t["dsl_models"], ensure_ascii=False)
    with open(tdir / "runner.log", "ab") as log:
        p = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
    try:
        return json.loads((tdir / "result.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        tail = (tdir / "runner.log").read_text(encoding="utf-8", errors="replace")[-600:]
        why = f"超过 {timeout} 秒被杀" if p.returncode in (-15, -9, 143) else f"退出码 {p.returncode}"
        return {"fixed": False, "engine_used": None, "versions": 0, "calls": 0, "cost": 0,
                "stop": f"dsl 执行器没写出结果（{why}）：{tail}", "handoff": "", "report": "",
                "calls_log": str(tdir / "calls.json"), "dir": str(tdir), "test_cmd": t.get("test_cmd")}


def _fallback_prompt(t: dict, r: dict) -> str:
    note = r.get("handoff") or r.get("stop") or "（没有记录）"
    cmd = r.get("test_cmd") or t.get("test_cmd")
    what = "自动执行流程（中文 DSL agent）已经先试过，没能完成" if r.get("kind") == "task" else \
        "自动修复流程（中文 DSL agent）已经先试过，没能修好"
    return (f"{t['prompt']}\n\n【交接说明】另一个{what}。"
            f"它对项目做的修改还在（见下面的 diff），对的留着、不对的改回去；它的判断不一定对，请自己核实。"
            f"测试文件不要改。可以运行项目里的 Python 脚本/代码来验证，工作目录限于本项目，不要改项目以外的文件。"
            f"\n\n{note}"
            + (f"\n\n跑测试用：{cmd}" if cmd else ""))


def _run_engine(d: dict, t: dict, i: int, resume: str = None, gate=None) -> None:
    """engine=dsl / auto 的一条：auto 先判定；dsl 没修好且 fallback 就交 claude 兜底。结果写回 t。

    gate(道) 返回占并发名额的上下文（"dsl" / "claude"），见 _run_lanes；逐条跑时不占。
    """
    from contextlib import nullcontext
    gate = gate or (lambda lane: nullcontext())
    with gate("dsl"):
        t0 = time.time()      # 从拿到名额算起，排队不算进 seconds
        if t["engine"] == "auto":
            eng = _decide(d, t)
        else:
            from .dslagent.auto import capability_gaps
            gaps = capability_gaps(t["prompt"])
            if gaps:   # 调用方显式选了 dsl：只记警告，不改道
                t["engine_warning"] = "能力检查：任务像是需要 dsl 做不到的事——" + "、".join(gaps) + "；按 engine=dsl 照跑"
            eng = "dsl"
        if eng == "dsl":
            _run_dsl_and_fallback(d, t, i, t0)
    if eng == "claude":
        with gate("claude"):
            t1 = time.time()
            # 给了 project 就在 project 里跑，权限同兜底（这批没给权限时 acceptEdits + PROJECT_TOOLS + 测试命令）
            _run_one(_in_project(d, t, t.get("test_cmd")) if t.get("project") else d, t, resume)
            t["engine_used"] = "claude"
            # 耗时含判定（跑开局测试、短分类）
            t["seconds"] = round((t.get("seconds") or 0) + (t1 - t0), 1)
            if t.get("route_cost_usd"):
                t["cost_usd"] = round((t.get("cost_usd") or 0) + t["route_cost_usd"], 4)


def _run_dsl_and_fallback(d: dict, t: dict, i: int, t0: float) -> None:
    r = _run_dsl(d, t, i)
    if r.get("kind"):
        t["dsl_kind"] = r["kind"]
    if r.get("early_exit"):
        t["dsl_early_exit"] = r["early_exit"]
    t.update(versions=r.get("versions"), calls=r.get("calls"), cost_usd=r.get("cost"),
             calls_log=r.get("calls_log") or t.get("calls_log"), dsl_dir=r.get("dir"),
             dsl_fixed=bool(r.get("fixed")), dsl_stop=r.get("stop", ""),
             engine_used=r.get("engine_used") or "dsl", output=r.get("report") or r.get("stop", ""))
    route_cost = t.get("route_cost_usd") or 0
    if r.get("fixed"):
        t.update(status="done", seconds=round(time.time() - t0, 1))
        if route_cost:
            t["cost_usd"] = round((t["cost_usd"] or 0) + route_cost, 4)
    elif t.get("fallback", True) and t.get("project"):
        d2 = _in_project(d, t, r.get("test_cmd") or t.get("test_cmd"))
        t2 = dict(t, prompt=_fallback_prompt(t, r), outfile="")
        _run_one(d2, t2)
        dsl_out = t["output"]
        for k in ("status", "output", "error", "session_id", "turns", "denied"):
            if k in t2:
                t[k] = t2[k]
        t["output"] = (t["output"] or "") + f"\n\n——（先跑的 DSL）{dsl_out}"
        t["cost_usd"] = round((r.get("cost") or 0) + (t2.get("cost_usd") or 0) + route_cost, 4)
        t["engine_used"] = "claude_fallback"
        t["seconds"] = round(time.time() - t0, 1)
    else:
        t.update(status="error", error=r.get("stop") or "dsl 没修好", seconds=round(time.time() - t0, 1))
        if route_cost:
            t["cost_usd"] = round((t["cost_usd"] or 0) + route_cost, 4)
    if t["outfile"] and t["output"]:
        f = Path(d["cwd"]) / t["outfile"]
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t["output"], encoding="utf-8")
        except OSError as e:
            t["error"] = (t["error"] + f" 写 outfile 失败：{e}").strip()


# 兜底 / auto→claude 在 project 里跑、这批又没给权限时的默认放行：能读写、能跑 Python 和测试验证、
# 几个只读命令；不放开任意 Bash、装包、联网、删除、git 提交推送、systemctl。
PROJECT_TOOLS = ["Read", "Edit", "Write", "Grep", "Glob",
                 "Bash(python3:*)", "Bash(python:*)",
                 "Bash(python3 -m pytest:*)", "Bash(python -m pytest:*)", "Bash(pytest:*)",
                 "Bash(python3 -m unittest:*)", "Bash(python -m unittest:*)",
                 "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(diff:*)",
                 "Bash(git diff:*)", "Bash(git status:*)"]


def _in_project(d: dict, t: dict, test_cmd) -> dict:
    """在 t 的 project 里跑 claude 用的 d：cwd=project；这批没给权限就 acceptEdits + PROJECT_TOOLS + 测试命令。

    permission_mode / allowed_tools 给了任一个就照调用方的（只给 allowed_tools 时模式补 acceptEdits，同以前）。
    """
    o = d["options"]
    tools = list(o["allowed_tools"])
    if not o["permission_mode"] and not tools:
        tools = PROJECT_TOOLS + ([f"Bash({test_cmd}*)"] if test_cmd else [])
    return dict(d, cwd=t["project"],
                options=dict(o, permission_mode=o["permission_mode"] or "acceptEdits", allowed_tools=tools))


def _log_route(d: dict, t: dict, i: int) -> None:
    """分流日志一行，见模块文档「分流日志」。写不了就算了，不影响任务。"""
    import hashlib
    rt = t.get("route") or {}
    c = rt.get("classify") or {}
    row = {"ts": _now(), "job": d["id"], "i": i,
           "hash": hashlib.sha256(t["prompt"].encode("utf-8")).hexdigest()[:12],
           "engine": t.get("engine", "claude"), "decision": rt.get("decision"), "source": rt.get("source"),
           "reason": (t.get("engine_reason") or "")[:300], "needs": rt.get("needs") or [],
           "classify_route": c.get("route"), "classify_ok": c.get("ok") if c else None,
           "classify_sec": c.get("seconds") if c else None,
           "engine_used": t.get("engine_used"), "dsl_kind": t.get("dsl_kind"),
           "early_exit": t.get("dsl_early_exit"), "warning": t.get("engine_warning"),
           "ok": t.get("status") == "done", "status": t.get("status"),
           "seconds": t.get("seconds"), "cost_usd": t.get("cost_usd")}
    try:
        ROUTING_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_LOCK, open(ROUTING_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


_LOG_LOCK = threading.Lock()


def _detach(job_id: str) -> None:
    """起执行器然后自己退出，见 submit 里的说明。

    执行器开新会话（自己一个进程组，cancel 好整组杀），标准输入输出全接到
    文件上——调用方退出、终端关掉，它都不受影响。
    """
    with open(_job_dir(job_id) / "runner.log", "ab") as log:
        subprocess.Popen([sys.executable, "-m", "tools.cbatch", "_run", job_id],
                         cwd=str(ROOT), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)


def _run(job_id: str) -> None:
    jd = _job_dir(job_id)
    cancelled = lambda: (jd / "cancel").exists()   # noqa: E731

    d = _load(job_id)
    d.update(status="running", started=_now(), pid=os.getpid())
    _save(d)

    if d["options"]["model"] == "auto":
        _classify(d)
        if cancelled():
            return
        _save(d)

    if d["mode"] == "share":
        prev_session = None
        for i, t in enumerate(d["tasks"], 1):
            if cancelled():
                break
            t["status"] = "running"
            _save(d)
            _exec(d, t, i, prev_session)
            prev_session = t["session_id"] if t["status"] == "done" else None
            if cancelled():
                return          # cancel() 负责收尾，这里再写会盖掉它
            _save(d)
    else:
        _run_lanes(d, cancelled)

    if cancelled():
        return
    d["finished"] = _now()
    st = {t["status"] for t in d["tasks"]}
    d["status"] = "done" if st == {"done"} else "partial" if "done" in st else "failed"
    _save(d)


def _exec(d: dict, t: dict, i: int, resume: str = None, gate=None) -> None:
    """跑一条（按 engine 分），跑完记分流日志。"""
    if t.get("engine", "claude") == "claude":
        if gate:
            with gate("claude"):
                _run_one(d, t, resume)
        else:
            _run_one(d, t, resume)
        t["engine_used"] = "claude"
    else:
        _run_engine(d, t, i, resume, gate)
    _log_route(d, t, i)


def _run_lanes(d: dict, cancelled) -> None:
    """isolated 模式：claude 道和 dsl 道各自限并发（见模块文档「并发」）。

    每条在自己的线程里改一份拷贝，跑完在锁里写回 d 再存盘——json.dumps(d) 时不会碰上别的线程正在改的字典。
    claude 道按提交顺序发名额（并发 1 时跟原来逐条跑一样的顺序）。
    """
    o = d["options"]
    lock = threading.Lock()
    lanes = {"claude": max(1, int(o.get("concurrency") or 1)),
             "dsl": max(1, int(o.get("dsl_concurrency") or DSL_CONCURRENCY))}
    sems = {k: threading.Semaphore(v) for k, v in lanes.items()}
    from contextlib import contextmanager

    @contextmanager
    def gate(lane):
        sems[lane].acquire()
        try:
            yield
        finally:
            sems[lane].release()

    def save():
        with lock:
            if not cancelled():
                _save(d)

    def work(i, t):
        if cancelled():
            return
        w = dict(t, status="running")
        with lock:
            t["status"] = "running"
        save()
        try:
            _exec(d, w, i, None, gate)
        except Exception as e:   # 一条坏了不拖垮整批
            w.update(status="error", error=f"执行器出错：{type(e).__name__}: {e}")
        with lock:
            t.clear()
            t.update(w)
        save()

    # claude 道：按顺序一条接一条地占名额（Semaphore 不保证先来先得，所以 claude 任务由几个工作线程按序取）
    claude_q = [(i, t) for i, t in enumerate(d["tasks"], 1) if t.get("engine", "claude") == "claude"]
    other = [(i, t) for i, t in enumerate(d["tasks"], 1) if t.get("engine", "claude") != "claude"]
    q_lock = threading.Lock()

    def claude_worker():
        while True:
            with q_lock:
                if not claude_q:
                    return
                i, t = claude_q.pop(0)
            work(i, t)

    # dsl 道：同一个 project 的按提交顺序一条接一条（直接改同一批文件，互斥且顺序有意义），不同 project 的各一个线程，
    # 同时在跑的条数由 gate("dsl") 卡（auto 判给 claude 的那条还要到 claude 道排队）
    groups = {}
    for i, t in other:
        groups.setdefault(t.get("project") or f"_{i}", []).append((i, t))

    def group_worker(items):
        for i, t in items:
            work(i, t)

    threads = [threading.Thread(target=claude_worker, daemon=True) for _ in range(lanes["claude"])]
    threads += [threading.Thread(target=group_worker, args=(g,), daemon=True) for g in groups.values()]
    for th in threads:
        th.start()
    for th in threads:
        th.join()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "_run":
        _run(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "_detach":
        _detach(sys.argv[2])
    else:
        print(describe())
