"""规划路径 v2（DSLAGENT_PLANNER=v2 时 runner.run 转到这里；缺省仍走 runner 的模板 / 规划路径）。

把 plan35/proto 的 proto_dsl（含 proto2 的先要数据）搬成生产路径。流程：
  1 数据包：v2pack.build 确定性收集候选模块、引用行、登记处行、import 了候选模块的测试断言（约 4 万字符）。
  2 补查：一次短调用（PRE_SYS）列出要补查的项（≤8：查引用 / 查文本 / 读文件），程序执行后并入数据包（补查命中的模块
    再收一轮测试断言）；回「够了」就跳过。
  3 规划：一次调用（PLAN_SYS）输出 .zs（#改法、#清单、预算、派任务 / 并行派任务 / 终止）；strip_prose → autoclose →
    白名单 + 有 #清单 / 预算 → 假模型空跑；有错带着错误重写 1 次，仍错判失败（不执行）。
  4 执行：仓库 DSL 引擎（V2Engine = AgentEngine + 测试闸门）跑计划。计划里的 跑测试 只在结果会改变走向时真跑
    （test_gate：结果变量被 打印 / 终止 以外的语句用到，或所在 如果 的分支不全是 打印 / 终止），否则给「通过」
    的占位结果，验收时统一跑。终止 成功 才往下验收，否则回滚到开局、判失败。
  5 验收：一次全量测试（代码自上次真跑以来没变就复用）；#清单 核对；查残留（只搜计划开头「# 旧写法: 正则」声明的，
    范围限清单 / 改动文件所在的顶层目录，不含测试和本次新建的文件）；有缺口派 1 次补改（FIX_SYS，入参给缺口所在
    函数全文），补改后重核、重跑测试。
  6 边界复核：一次短调用（BOUND_SYS）按任务原文 + diff 写 3–5 个 unittest 边界用例（写在任务目录 boundary/，不进项目），
    跑；失败带失败信息派 1 次补改（BFIX_SYS），再跑用例和全量测试；仍失败 → 状态 超出预期（不报成功），原因写明用例；
    补改弄坏现有测试 → 撤回补改，同样 超出预期。用例文件跑不起来（语法错、导入错）记下来，不算代码的问题。
  7 回复：reply = {结果, 状态, 原因}；v2 记各步耗时、调用次数、费用（calls.json 逐次）。
子任务回复格式：缺省 json；DSLAGENT_SUBTASK=tool 时子任务挂 dslmcp 的 dsl 工具读 / 搜 / 改文件（toolsub.py），每个子任务的结果记在 v2.子任务。
模型调用：claude CLI，--system-prompt 替换默认提示，--tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands
（同 plan35 proto），单轮流式；run(model=…) 可换成假模型（测试用）。
"""
import ast
import difflib
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import dslcheck as DC
from . import v2pack as K

PKG = Path(__file__).resolve().parent
LIB = PKG / "lib"
VERBS = PKG / "verbs"
MODEL = "sonnet"
MAX_CALLS = 20           # 补查 1 + 规划 1（+重写 1）+ 计划内 ≤12 + 补改 1 + 边界 1 + 边界补改 1，留余量
WALL = 900
IDLE_SEC = 60            # 首 token 之后这么久没有新流事件就杀掉该次调用
MAX_OUT = 20000          # 单次调用累计输出超过这么多字符就杀掉（reason=输出超长）
TOOL_MARKS = ("<invoke", "<function_calls")   # 流里出现这些 = 模型在写工具调用格式（reason=输出工具调用格式）
GUARD_REASONS = ("空闲超时", "输出工具调用格式", "输出超长")
TEST_TIMEOUT = 600
BOUND_TIMEOUT = 120
FN_CAP = 250             # 补改入参：单个函数最多给多少行
FIX_CAP = 40000          # 补改入参总字符
DIFF_CAP = 12000
OLD_RX_LINE = re.compile(r"^\s*#\s*旧写法\s*[:：]\s*(.+?)\s*$", re.M)
SKIP_NOTE = "未跑（这次测试的结果不改变计划走向，验收时统一跑一次全量测试）"


class Stop(Exception):
    pass


def enabled():
    return (os.environ.get("DSLAGENT_PLANNER") or "").strip().lower() == "v2"


# ------------------------------------------------------------------ 提示词

PRE_SYS = r"""你是「分支式规划者」的第一步：先判断数据包够不够写计划。用户消息给你一个改代码任务和一份从仓库确定性抽出的数据包
（不一定全）。你看不到别的文件，不能运行任何东西。现在**不要写计划**，只说还要补查什么，程序会替你查、把结果附到数据包后面。

可以要的三类查询（合计最多 8 项）：
- "查引用"：名字或写法（原样字符串，如函数名、import 写法、某段固定代码片段），程序在全仓逐行找出现处；
- "查文本"：Python 正则，程序在全仓逐行搜；
- "读文件"："相对路径:起-止"，程序给带行号原文（每项最多 200 行）。
全仓 = 项目里的 .py 和文本文件，排除隐藏目录、虚拟环境、__pycache__；结果是「文件:行号: 内容」。
任务是「收敛 / 统一 / 替换所有 / 改用 / 去重」类时，一定要用查文本把**所有**旧写法的位置找全（旧写法可能有几种变体，各写一个正则），
并读出数据包里没有原文的位置所在的函数。

只输出一个 JSON 对象（不要 markdown 围栏、不要别的文字）：
{"查引用": ["..."], "查文本": ["..."], "读文件": ["文件:起-止"], "够了": false}
数据包已经足够写出覆盖全部位置的计划时输出 {"查引用": [], "查文本": [], "读文件": [], "够了": true}。
"""

SUB_SYS = ("你是子任务执行者，被一个自动化流程调用。只根据用户消息里给你的数据完成任务，不能读别的文件，也不能运行任何东西。"
           "按用户消息末尾的输出格式只输出一个 JSON 对象（不要代码围栏、不要别的文字）。"
           "修改内容 edits 每项字段名固定为 file（相对项目根路径）、old（从给你的原文一字不差抄，含缩进，不带「  12| 」行号前缀，"
           "在文件里只出现一次）、new（替换后的文本）。不要改测试文件（tests/ 下、test_*.py）。")

RULES = r"""【规划规则（这次要写的脚本）】
- 第一行 用包 common text code；第二行写 预算 调用 N 秒 M（N ≤ 12，含 问JSON / 派任务 / 并行派任务 里的每次调用和重问；M ≤ 600）。
- 改法：数据包 / 补查结果里能看到原文的改动，原文一字不差抄进脚本末尾的 #改法 段（不带「  12| 」行号前缀，含缩进，在文件里唯一），
  脚本里 设 res = 改文件 {e1}；如果 {res.ok} 不等于 是，把 {res.msg} 带进一次 派任务（入参给那段「文件:起-止」）让它重给 edits，
  再 改文件 {r.结果}，还不行就 终止 失败。新建文件用 @@ 新建。改法尽量合成一段一次套（原子），互相独立的大块可分 e1、e2。
- 子任务：数据包里没有原文、或要看运行结果才能决定怎么改的，用 派任务（入参「文件:起-止」由动词读出当前文件那几行附上；
  格式 edits:列表,说明:文本；逻辑里写明 edits 字段名 file/old/new、old 一字不差不带行号前缀、新模块的函数签名和 import 写法）；
  拿回后 设 res = 改文件 {r.结果}（结果里就有 edits）。互不依赖的用 并行派任务，结果是列表，遍历 逐个 改文件。
- 任务含「收敛 / 统一 / 替换所有 / 改用 / 去重」之类要求时：脚本必须覆盖数据包和补查结果里查到的**每一个**位置（每个都要有改法或
  子任务负责，清单逐文件列出）；不确定是否属于任务范围的位置按任务原文的范围判断。要改的位置分布在 ≥3 个文件时：新模块先用 #改法 建好，
  再按文件 并行派任务（每项负责 1–2 个文件，总数 ≤ 8），任务描述里写明新模块的函数签名、行为和 import 写法，入参给它负责的那几处所在函数。
- 旧写法：在脚本开头（用包、预算 之后）用注释逐行写 # 旧写法: <Python 正则>，匹配「改完后仓库里不应再出现」的旧实现写法
  （如被替换掉的手写判断、被删掉的旧函数定义）。执行器验收时用它在任务涉及的目录里（不含测试和本次新建的文件）搜残留，有残留就派补改，
  补改后仍有残留判失败。正则要专一：只匹配旧实现，不能匹配改完后合法存在的代码（包括新写的调用）、注释或无关代码；没有可核对的旧写法就不写。
- 必须写 #清单 段（写在最后）：逐行 改 路径:函数名 / 新建 路径 / 删 路径，列出这次要动的全部文件。
- 结尾不写 跑测试：脚本结束后执行器统一跑一次全量测试验收。脚本中间的 跑测试 只有结果会改变后续走向（失败要补救、要把失败摘要带进
  派任务）时才真跑，否则执行器跳过（按通过处理）。
- 全部改完 终止 成功 一句话；做不到 终止 失败 原因；前提不符或范围远超描述 终止 超出预期 原因。不要打印「结论：」行。
- 不要改测试文件（tests/ 下）；改动覆盖任务原文的每一条要求。不用 定位.zs / 读改测.zs（数据包已给原文）。
- 只输出 .zs 脚本本身（含 #改法 / #清单 段），不要代码围栏，不要任何解释文字。"""

FIX_SYS = ("你是补改子任务执行者。一个改代码任务已经按计划改完，但验收发现了下面列出的缺口（旧写法残留、清单里该改没改的位置、"
           "没过的测试）。只根据用户消息给你的数据补改，不能读别的文件，也不能运行任何东西。每处缺口给了它所在函数的完整当前代码；"
           "对外行为（返回值、异常类型和文字）按任务原文保持；需要的 import 一并加上。\n"
           "【回复格式】只输出一个 JSON 对象（不要 markdown 围栏、不要别的文字）：\n"
           '{"结果": {"edits": [{"file": "相对项目根路径", "old": "要替换的原文，从给你的当前代码一字不差抄（不带行号前缀，含缩进，'
           '在文件里唯一）", "new": "替换后的文本"}], "说明": "逐条说明每处缺口怎么处理"}, '
           '"状态": "成功|失败|超出预期", "原因": "失败或超出预期时写原因，成功留空"}\n'
           "不要改测试文件（tests/ 下、test_*.py）。")

BOUND_SYS = r"""你是代码改动的边界复核员。用户消息给你一个改代码任务的原文和改动后的 diff（含新建文件全文）。
写 3–5 个 unittest 边界用例，检查改动是否满足任务原文里**明确写出**的要求：边界输入（空、0、负数、非整数、不存在、越界、
符号链接等任务里提到的情形）、原文点名的返回文字 / 异常文字、对外行为不变的承诺。只测任务原文写明的行为，不要臆测原文没说的细节；
期望值必须能从任务原文或 diff 里确定地推出来，拿不准的不写。

运行环境：用例文件放在项目外的临时目录，以项目根为当前目录运行（python -m unittest -v），项目根已在 sys.path 里，
os.environ["PROJ"] 是项目根的绝对路径。不能写项目里的文件（需要文件就用 tempfile 建在临时目录）；不联网、不起子进程、
每个用例 1 秒内跑完。项目里的模块按 diff 里的路径 import（如 tools/safepath.py → from tools.safepath import is_inside）；
目录里没有 __init__.py、靠 sys.path.insert 加载的模块，用 importlib.util.spec_from_file_location 按文件路径加载。

要测的函数在每个用例里直接调用（模块.函数(...)）；不要把函数存成类属性再用 self.f(...) 调（会被绑定成方法、多传一个 self）。

只输出一个完整的 Python 文件（不要 markdown 围栏、不要别的文字）：import unittest，一个 TestCase 类，每个 test_ 方法第一行写
一句中文 docstring 说明它检查任务原文的哪条要求。"""

BFIX_SYS = ("你是补改子任务执行者。一个改代码任务改完后现有测试全过，但按任务原文写的边界用例没过。只根据用户消息给你的数据补改，"
            "不能读别的文件，也不能运行任何东西。先对照任务原文和失败输出判断：用例的期望确实是任务原文写明的要求 → 改代码让它通过"
            "（不要为迎合用例违反任务原文）；用例代码自身有编程错误（调用方式、导入、夹具写错，跟期望值无关）→ 在 用例代码 里给改好的"
            "完整用例文件（期望值不许改），代码有问题的同时给 edits；用例的期望和任务原文不符 → 不改，状态写 超出预期，原因写明哪个用例、"
            "哪里不符。\n"
            "【回复格式】只输出一个 JSON 对象（不要 markdown 围栏、不要别的文字）：\n"
            '{"结果": {"edits": [{"file": "相对项目根路径", "old": "要替换的原文，从给你的当前代码一字不差抄（不带行号前缀，含缩进，'
            '在文件里唯一）", "new": "替换后的文本"}], "用例代码": "可选：改好的完整用例文件（只修用例自身的编程错误时给）", '
            '"说明": "逐条说明"}, '
            '"状态": "成功|失败|超出预期", "原因": "失败或超出预期时写原因，成功留空"}\n'
            "不要改测试文件（tests/ 下、test_*.py）。")

_PLAN_SYS = None


def plan_system():
    global _PLAN_SYS
    if _PLAN_SYS is None:
        from . import prompts as DPR
        keep = ("赋值右边不要以", "一条语句只能写在一行", "修改内容的字段名固定为", "你看不到代码")
        tips = "【写法要点（节选）】\n" + "\n".join(
            "- " + b.strip() for b in DPR.TIPS.split("\n- ") if b.strip().startswith(keep))
        _PLAN_SYS = ("你是「分支式规划者」。用户消息会给你一个改代码任务、一份从仓库里确定性抽出的「数据包」（相关代码片段带行号、"
                     "登记处、引用行、相关测试断言、文件大纲），后面可能有「补查结果」，同等对待。你看不到别的文件，也不能运行任何东西。"
                     "你要写一段中文 DSL 脚本（.zs），交给 DSL 引擎直接执行（不再改写）；脚本里的 派任务 / 问JSON 会调另一个模型，"
                     "它只看得到你写进提示词、入参里的数据。\n\n"
                     f"{DPR.CHEAT}\n\n{DPR.VERBS}\n\n{tips}\n\n{RULES}\n\n"
                     "【示例（分支式规划的写法示例，只示意写法，不是答案）】\n"
                     + (LIB / "示例_分支规划.zs").read_text(encoding="utf-8"))
    return _PLAN_SYS


def plan_user(task, pack):
    return f"【任务原文】\n{task}\n\n【数据包】\n{pack}"


def parse_json(text):
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < i:
        raise ValueError("回复里没有 JSON 对象")
    return json.loads(s[i:j + 1])


# ------------------------------------------------------------------ 模型调用


def call_claude(system, user, timeout=300, model=None, reply_path=None, idle=None, mcp_config=None, max_turns=1, allow_tool=None):
    """claude -p（model 缺省 MODEL），自定系统提示，无工具 / MCP / 技能，单轮，流式（记首 token）。返回 text / sec / ttft / cost / usage / rc / stderr / reason。
    首 token 之后 idle 秒没有任何新流事件 → killpg（reason=空闲超时）；首 token 前只受总超时管。
    流式累计文本出现 <invoke / <function_calls → killpg（reason=输出工具调用格式）；累计超过 MAX_OUT 字符 → killpg（reason=输出超长）。
    reply_path：边收流边把文本增量追加进该文件，被杀时已收到的内容也在；返回的 partial 是已收到的流文本。
    mcp_config（DSLAGENT_SUBTASK=tool）：多挂一个 MCP（--mcp-config + --strict-mcp-config，内置工具仍 --tools ""，只许 allow_tool 那一个），
    --max-turns 用 max_turns；text 是最后一轮的最终回复（中途轮次里的文字、真实工具调用不算），「输出工具调用格式」只查当前这一轮的文字，
    返回里多 num_turns / tool_calls / subtype。"""
    from tools.cbatch import CLAUDE_BIN
    from .pool import child_env
    from .runner import tmp_dir
    tmp = tmp_dir()
    cwd = tmp / "v2_empty"
    cwd.mkdir(parents=True, exist_ok=True)
    cmd = [os.environ.get("CBATCH_CLAUDE") or CLAUDE_BIN, "-p", "--model", model or MODEL, "--output-format", "stream-json",
           "--verbose", "--include-partial-messages", "--max-turns", str(max_turns), "--tools", "", "--setting-sources", "",
           "--strict-mcp-config", "--disable-slash-commands", "--system-prompt", system]
    if mcp_config:
        cmd += ["--mcp-config", str(mcp_config), "--allowedTools", allow_tool or "mcp__dsl__dsl"]
    idle = idle or IDLE_SEC
    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         cwd=cwd, env=child_env(tmp), start_new_session=True)
    err_buf, killed = [], []
    last = [time.time()]
    fh = None
    if reply_path:
        try:
            fh = open(reply_path, "w", encoding="utf-8")
        except OSError:
            fh = None

    def feed():
        try:
            p.stdin.write(user)
            p.stdin.close()
        except OSError:
            pass

    def drain():
        err_buf.append(p.stderr.read())

    def kill(why="总超时"):
        killed.append(why)
        try:
            os.killpg(p.pid, 9)
        except OSError:
            pass
    th = [threading.Thread(target=feed, daemon=True), threading.Thread(target=drain, daemon=True)]
    for t in th:
        t.start()
    timer = threading.Timer(timeout, kill)
    timer.start()
    text, result, ttft, streamed = "", None, None, ""
    turn_text, total_chars = "", 0          # mcp 模式：当前这一轮的流文本 / 全部轮的累计字数
    msgs, tool_calls, tool_ids = {}, 0, set()                # mcp 模式：消息 id → {text, tool}（按出现顺序），真实工具调用块数
    done = threading.Event()

    def watch():
        while not done.wait(min(1.0, max(0.05, idle / 4))):
            if ttft is not None and time.time() - last[0] > idle:
                kill("空闲超时")
                return
    wd = threading.Thread(target=watch, daemon=True)
    wd.start()
    try:
        for line in p.stdout:
            last[0] = time.time()
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            ty = ev.get("type")
            if ty == "stream_event":
                se = ev.get("event") or {}
                if se.get("type") == "message_start":
                    turn_text = ""
                if se.get("type") == "content_block_delta":
                    if ttft is None:
                        ttft = round(time.time() - t0, 2)
                    d = se.get("delta") or {}
                    if d.get("type") == "text_delta" and d.get("text"):
                        streamed += d["text"]
                        turn_text += d["text"]
                        total_chars += len(d["text"])
                        if not killed:
                            if any(m in (turn_text if mcp_config else streamed) for m in TOOL_MARKS):
                                kill("输出工具调用格式")
                            elif (total_chars if mcp_config else len(streamed)) > MAX_OUT:
                                kill("输出超长")
                        if fh:
                            try:
                                fh.write(d["text"])
                                fh.flush()
                            except OSError:
                                pass
            elif ty == "assistant":
                if mcp_config:
                    m = msgs.setdefault(ev["message"].get("id") or f"m{len(msgs)}", {"text": "", "tool": False})
                    for b in ev["message"].get("content", []):
                        if b.get("type") == "text":
                            m["text"] += b["text"]
                        elif b.get("type") == "tool_use":
                            m["tool"] = True
                            tool_ids.add(b.get("id") or len(tool_ids))
                            tool_calls = len(tool_ids)
                    continue
                for b in ev["message"].get("content", []):
                    if b.get("type") == "text":
                        text += b["text"]
            elif ty == "result":
                result = ev
        p.wait()
    finally:
        timer.cancel()
        done.set()
        for t in th:
            t.join(timeout=5)
        if fh:
            fh.close()
    reason = killed[0] if killed else None
    if mcp_config:
        last_msg = list(msgs.values())[-1] if msgs else None
        text = (last_msg["text"] if last_msg and not last_msg["tool"] else "") if result is None or result.get("is_error") \
            else (result.get("result") or "")
    err = "".join(x or "" for x in err_buf) + (f"\n[{reason}被杀]" if killed else "")
    res = result or {}
    u = res.get("usage", {}) or {}
    usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
             "cache_read": u.get("cache_read_input_tokens"), "cache_creation": u.get("cache_creation_input_tokens")}
    return {"text": text, "sec": round(time.time() - t0, 1), "rc": p.returncode, "ttft": ttft,
            "cost": res.get("total_cost_usd") or 0.0, "usage": usage, "stderr": err[-500:], "reason": reason,
            "partial": streamed, "num_turns": res.get("num_turns"), "tool_calls": tool_calls,
            "subtype": res.get("subtype")}


class Model:
    """全部模型调用的入口：计数、墙钟、费用、逐次记录（calls/NN_tag.*.txt、self.log）。
    backend(system, user, tag, timeout) → dict（text, cost, …）或 str；只有指定了非 MODEL 的模型（规划那次）才多传 model=。"""

    def __init__(self, out, backend=None, max_calls=MAX_CALLS, deadline=None):
        self.out = Path(out)
        self.real = backend is None
        self.backend = backend or (lambda s, u, tag, timeout, model=None, **kw: call_claude(s, u, timeout, model, **kw))
        self.max_calls, self.deadline = max_calls, deadline
        self.n, self.cost, self.log = 0, 0.0, []
        self.lock = threading.Lock()
        (self.out / "calls").mkdir(parents=True, exist_ok=True)

    def __call__(self, system, user, tag, model=None):
        """一次调用；因空闲超时 / rc≠0 / 空回复失败时同输入重试 1 次（计入调用数和费用，记录 retry=1 和首次失败原因）。"""
        try:
            return self._once(system, user, tag, model)
        except RuntimeError as e:
            reason = getattr(e, "reason", None) or str(e)
            return self._once(system, user, tag, model, retry=reason)

    def _once(self, system, user, tag, model=None, retry=None):
        with self.lock:
            if self.n >= self.max_calls:
                raise Stop(f"总模型调用已满 {self.max_calls} 次（{tag}）")
            if self.deadline and time.time() > self.deadline:
                raise Stop(f"墙钟用完（{tag} 前）")
            self.n += 1
            n = self.n
        left = (self.deadline - time.time()) if self.deadline else 300
        t0 = time.time()
        kw = {"model": model} if model and model != MODEL else {}
        rp = self.out / "calls" / f"{n:02d}_{tag}.reply.txt"
        if self.real:
            kw["reply_path"] = rp
        r = self.backend(system, user, tag, max(30, min(300, left + 5)), **kw)
        if isinstance(r, str):
            r = {"text": r}
        rec = {"n": n, "tag": tag, "sec": r.get("sec", round(time.time() - t0, 2)), "ttft": r.get("ttft"),
               "cost": r.get("cost") or 0.0, "usage": r.get("usage"), "rc": r.get("rc"),
               "model": model or MODEL, "sys_chars": len(system), "user_chars": len(user), "t_start": round(t0, 3)}
        if retry:
            rec["retry"] = 1
            rec["first_fail"] = retry
        with self.lock:
            self.cost += rec["cost"]
            self.log.append(rec)
        try:
            (self.out / "calls" / f"{n:02d}_{tag}.prompt.txt").write_text(f"[system]\n{system}\n\n[user]\n{user}",
                                                                          encoding="utf-8")
            rp.write_text(
                (r.get("text") or r.get("partial") or "") + ("\n\n[stderr]\n" + r["stderr"] if r.get("stderr") else ""), encoding="utf-8")
        except OSError:
            pass
        bad = r.get("reason") in GUARD_REASONS or (r.get("rc") not in (None, 0)) or not (r.get("text") or "").strip()
        if bad:
            why = r.get("reason") or (f"rc={r.get('rc')}" if r.get("rc") not in (None, 0) else "空回复")
            rec["failed"] = why
            e = RuntimeError(f"模型没有回应（{why}，rc={r.get('rc')}）：{(r.get('stderr') or '')[-200:]}")
            e.reason = why
            if retry:
                e.args = (f"{e.args[0]}；首次失败：{retry}",)
            raise e
        return r["text"]


def _tool_call(self, system, user, tag, mcp_config, max_turns=6):
    """DSLAGENT_SUBTASK=tool：一次带 MCP 的多轮调用（计 1 次调用数，费用、逐次记录同 _once）。不重试、不抛模型失败——
    失败原因（保险触发 / rc≠0 / 空回复）放在返回的 failed 里，由 toolsub 决定重试还是兜底。返回 backend 的 dict。"""
    with self.lock:
        if self.n >= self.max_calls:
            raise Stop(f"总模型调用已满 {self.max_calls} 次（{tag}）")
        if self.deadline and time.time() > self.deadline:
            raise Stop(f"墙钟用完（{tag} 前）")
        self.n += 1
        n = self.n
    left = (self.deadline - time.time()) if self.deadline else 300
    t0 = time.time()
    rp = self.out / "calls" / f"{n:02d}_{tag}.reply.txt"
    kw = {"reply_path": rp} if self.real else {}
    r = self.backend(system, user, tag, max(30, min(300, left + 5)), mcp_config=str(mcp_config), max_turns=max_turns, **kw)
    if isinstance(r, str):
        r = {"text": r}
    rec = {"n": n, "tag": tag, "sec": r.get("sec", round(time.time() - t0, 2)), "ttft": r.get("ttft"),
           "cost": r.get("cost") or 0.0, "usage": r.get("usage"), "rc": r.get("rc"), "tool": 1,
           "num_turns": r.get("num_turns"), "tool_calls": r.get("tool_calls"), "subtype": r.get("subtype"),
           "sys_chars": len(system), "user_chars": len(user), "t_start": round(t0, 3)}
    with self.lock:
        self.cost += rec["cost"]
        self.log.append(rec)
    try:
        (self.out / "calls" / f"{n:02d}_{tag}.prompt.txt").write_text(f"[system]\n{system}\n\n[user]\n{user}", encoding="utf-8")
        rp.write_text((r.get("text") or r.get("partial") or "") + ("\n\n[stderr]\n" + r["stderr"] if r.get("stderr") else ""),
                      encoding="utf-8")
    except OSError:
        pass
    if r.get("reason") in GUARD_REASONS:
        rec["failed"] = r["failed"] = r["reason"]
    elif r.get("subtype") == "error_max_turns":
        rec["failed"] = r["failed"] = "轮数用尽"
    elif r.get("rc") not in (None, 0):
        rec["failed"] = r["failed"] = f"rc={r.get('rc')}"
    elif not (r.get("text") or "").strip():
        rec["failed"] = r["failed"] = "空回复"
    r["call_n"] = n
    return r


Model.tool_call = _tool_call


class Client:
    """DSL 引擎的模型客户端：问 / 问JSON / 派任务 / 并行派任务 都走 Model（同一套计数和记录）。"""
    offline = True       # llm_router 见 offline=True 不分派
    model = MODEL

    def __init__(self, M):
        self.M, self.k = M, 0
        self.lock = threading.Lock()

    def chat_messages(self, messages, temperature=None, model=None, **kw):
        from tools.llm_router import _render
        prompt, system = _render(messages)
        with self.lock:
            self.k += 1
            k = self.k
        try:
            return self.M(system or SUB_SYS, prompt, f"dsl{k:02d}")
        except Stop as e:
            raise RuntimeError(str(e)) from None

    def run_tool(self, system, user, workdir, label, max_turns=6):
        """DSLAGENT_SUBTASK=tool：起一个只挂 dsl 工具的 MCP（stdio，进程由 claude CLI 拉起，随这次调用结束），调一次多轮 claude。
        返回 Model.tool_call 的 dict，外加 tool_log（MCP 追加的每次工具调用日志行，文件在任务目录 toollogs/）。"""
        with self.lock:
            self.k += 1
            k = self.k
        d = self.M.out / "toollogs"
        d.mkdir(parents=True, exist_ok=True)
        tag = f"dsl{k:02d}_{label}"
        log = d / f"{tag}.jsonl"
        cfg = d / f"{tag}.mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"dsl": {"command": sys.executable, "args": [
            str(PKG / "dslmcp.py"), "--workdir", str(workdir), "--log", str(log), "--verbs-root", str(VERBS),
            "--state", str(d / f"{tag}_state")]}}},
            ensure_ascii=False), encoding="utf-8")
        try:
            r = self.M.tool_call(system, user, tag, cfg, max_turns)
        except Stop as e:
            raise RuntimeError(str(e)) from None
        rows = []
        try:
            for line in log.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        except OSError:
            pass
        r["tool_log"] = rows
        return r

    def chat(self, prompt, system=None, temperature=None, model=None, **kw):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        return self.chat_messages(msgs)

    def chat_json(self, prompt, system=None, temperature=None, model=None, **kw):
        from tools.zhipu import strip_json
        return json.loads(strip_json(self.chat(prompt, system=system)))


# ------------------------------------------------------------------ 项目快照 / 改法 / 测试


def snapshot(project):
    out = {}
    for rel, f in K.text_files(project):
        try:
            out[rel] = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    return out


def changed(before, after):
    return sorted(r for r in set(before) | set(after) if before.get(r) != after.get(r))


def code_hash(snap):
    h = hashlib.sha256()
    for k in sorted(snap):
        h.update(k.encode() + b"\0" + snap[k].encode("utf-8", "replace") + b"\1")
    return h.hexdigest()


def diff_text(before, after, limit=DIFF_CAP):
    parts = []
    for rel in changed(before, after):
        a, b = before.get(rel), after.get(rel)
        if a is None:
            parts.append(f"--- 新建 {rel}\n" + b)
            continue
        if b is None:
            parts.append(f"--- 删除 {rel}")
            continue
        parts.append("\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), rel, rel, lineterm="", n=2)))
    return "\n".join(parts)[:limit]


def restore(project, base, files):
    """把 files 恢复成 base 里的样子（base 里没有的删掉）。"""
    for rel in files:
        p = Path(project) / rel
        t = base.get(rel)
        if t is None:
            if p.is_file():
                p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(t, encoding="utf-8")


def apply_edits(project, edits):
    """全部能套才套（原子）。不改测试文件、不出项目。返回 (ok, 说明)。"""
    root = Path(project).resolve()
    new_txt = {}
    if not isinstance(edits, list) or not edits:
        return False, "没有 edits"
    for e in edits:
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) for k in ("file", "old", "new")):
            return False, f"edits 项格式不对：{str(e)[:120]}"
        rel = e["file"][2:] if e["file"].startswith("./") else e["file"]
        p = (root / rel).resolve()
        if p == root or root not in p.parents:
            return False, f"不允许改项目外的 {rel}"
        if K.is_test(rel):
            return False, f"不允许改测试文件 {rel}"
        cur = new_txt.get(rel, p.read_text(encoding="utf-8") if p.is_file() else None)
        if e["old"] == "":
            if cur is not None and cur.strip():
                return False, f"{rel} 已存在且非空，新建文件 old 不能为空"
            new_txt[rel] = e["new"]
            continue
        if cur is None:
            return False, f"{rel} 不存在"
        n = cur.count(e["old"])
        if n != 1:
            return False, f"{rel}: old 出现 {n} 次（应为 1）：{e['old'][:120]!r}"
        new_txt[rel] = cur.replace(e["old"], e["new"], 1)
    for rel, t in new_txt.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
    return True, f"已套 {len(edits)} 处，涉及 {sorted(new_txt)}"


def _test_verb():
    from .runner import _verb_module
    return _verb_module("跑测试")


def full_test(project, test_cmd):
    """跑一次全量测试：{passed, summary, sec}。"""
    m = _test_verb()
    t0 = time.time()
    rc, text = m.run_raw(Path(project).resolve(), test_cmd, int(os.environ.get("DSLAGENT_TEST_TIMEOUT") or TEST_TIMEOUT))
    s = m.summarize(Path(project).resolve(), rc, text)
    return {"passed": s["passed"] == "是", "summary": s["summary"], "sec": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ 计划里的 跑测试：要不要真跑


def test_gate(script):
    """主脚本里每个 跑测试 语句的行号（0 起，同引擎的 _at）→ 要不要真跑。
    真跑 ⇔ 结果变量被 打印 / 终止 以外的语句用到；如果 / 否则如果 的条件用到它时，整条 如果 链的各分支都只有 打印 / 终止、
    且（有 否则，或分支里没有 终止，或链后面到块尾也只有 打印 / 终止）才算不影响走向。不赋值的 跑测试 不真跑。"""
    from tools.dsl_core import BLOCK_OPENERS, normalize, split_head
    from tools.dsl_sections import split_sections
    body = split_sections(script)[0]
    lines = [normalize(l).strip() for l in body.split("\n")]
    heads = [split_head(l) if l and not l.startswith("#") else ("", "") for l in lines]
    trivial = {"print", "halt", ""}

    def block_end(i):
        """lines[i] 是块开头 → 与它配对的 结束 的行号（找不到给 len）。"""
        d = 0
        for j in range(i, len(lines)):
            h = heads[j][0]
            if h in BLOCK_OPENERS:
                d += 1
            elif h == "end":
                d -= 1
                if d == 0:
                    return j
        return len(lines)

    def chain_of(j):
        """j 是 if / elif → (if 行, [(分支起, 分支止)], 有否则, 结束行)。"""
        i = j
        if heads[j][0] == "elif":       # 往回找配对的 如果
            d = 0
            for k in range(j - 1, -1, -1):
                h = heads[k][0]
                if h == "end":
                    d += 1
                elif h in BLOCK_OPENERS:
                    if d == 0:
                        i = k
                        break
                    d -= 1
        end = block_end(i)
        parts, has_else, start, d = [], False, i + 1, 0
        for k in range(i + 1, end):
            h = heads[k][0]
            if h in BLOCK_OPENERS:
                d += 1
            elif h == "end":
                d -= 1
            elif d == 0 and h in ("elif", "else"):
                parts.append((start, k))
                start = k + 1
                has_else = has_else or h == "else"
        parts.append((start, end))
        return i, parts, has_else, end

    def only_trivial(a, b):
        return all(heads[k][0] in trivial for k in range(a, b))

    def after_trivial(end):
        d = 0
        for k in range(end + 1, len(lines)):
            h = heads[k][0]
            if h in BLOCK_OPENERS:
                return False
            if h in ("end", "elif", "else"):
                return True
            if h not in trivial:
                return False
        return True

    def needed(var, i):
        ref = re.compile(r"\{\s*" + re.escape(var) + r"(?:[.}\s])")
        for j, l in enumerate(lines):
            if j == i or not ref.search(l):
                continue
            h = heads[j][0]
            if h in ("print", "halt", "#", ""):
                continue
            if h in ("if", "elif"):
                _, parts, has_else, end = chain_of(j)
                if not all(only_trivial(a, b) for a, b in parts):
                    return True
                halts = any(heads[k][0] == "halt" for a, b in parts for k in range(a, b))
                if has_else or not halts or after_trivial(end):
                    continue
            return True
        return False

    gate = {}
    for i, (h, rest) in enumerate(heads):
        if h == "跑测试":
            gate[i] = False
        elif h == "set":
            name, _, val = rest.partition("=")
            if split_head(val.strip())[0] == "跑测试":
                gate[i] = needed(name.strip(), i)
    return gate


def _engine_cls():
    from .engine import AgentEngine

    class V2Engine(AgentEngine):
        """AgentEngine + 测试闸门：主脚本里 test_gate 判为不影响走向的 跑测试 不真跑，给通过的占位结果；
        真跑的记下当时的代码哈希和结果（验收时代码没变就复用）。空跑时 跑测试 一律给占位结果。"""
        gate = None
        project = None
        tests = None

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.subtask_mode = DC.env_mode()

        def _no_edits(self, rest):
            """tool 模式：子任务在工具里改完了文件，结果里没有 edits——计划里的 改文件 {r.结果} 当空操作。"""
            args = [self.expand(a) for a in rest.split()]
            if len(args) != 1:
                return False
            try:
                e = args[0] if isinstance(args[0], dict) else json.loads(args[0])
            except (TypeError, json.JSONDecodeError):
                return False
            return (isinstance(e, dict) and isinstance(e.get("edits"), list) and not e["edits"]
                    and e.get("old") is None and not e.get("files"))

        def _do_verb(self, name, rest, lineno, assign_to=None):
            if name == "改文件" and self.subtask_mode == "tool" and not self.dry_run and self._no_edits(rest):
                return self._deliver({"ok": "是", "msg": "（结果里没有 edits：子任务在工具里已改好，空操作）", "n": 0}, assign_to)
            if name != "跑测试":
                return super()._do_verb(name, rest, lineno, assign_to)
            if self.dry_run:
                return self._deliver({"passed": "是", "summary": "（空跑）" + SKIP_NOTE}, assign_to)
            log = self.tests if self.tests is not None else []
            if self._depth == 0 and self.gate is not None and not self.gate.get(self._at, True):
                log.append({"line": self._at + 1, "mode": "skipped"})
                return self._deliver({"passed": "是", "summary": SKIP_NOTE}, assign_to)
            t0 = time.time()
            super()._do_verb(name, rest, lineno, assign_to)
            res = self.vars.get(assign_to) if assign_to else None
            if self.project is not None:
                v = res if isinstance(res, dict) else {}
                log.append({"line": self._at + 1, "mode": "real", "sec": round(time.time() - t0, 1),
                            "passed": v.get("passed") == "是", "summary": str(v.get("summary", ""))[:4000],
                            "hash": code_hash(snapshot(self.project)), "known": isinstance(res, dict)})
    return V2Engine


# ------------------------------------------------------------------ 3 规划检查


def scripts_for(plan_dir, subs):
    from . import plan as DP
    m = {n: LIB / n for n in DP.LIBS}
    m.update({f"_plan/{k}": Path(plan_dir) / k for k in subs})
    return m


def check(project, work, script, task):
    """plan.py 的检查 + 有 #清单、有 预算 + 空跑。返回 (问题文本或空, 主脚本, 子脚本, 记录)。"""
    from tools.dsl_sections import split_sections

    from . import plan as DP
    rec = {}
    main, subs = DP.split_subs(script)
    probs = DP.whitelist_check(main, subs)
    body, _, cl, _ = split_sections(main)
    if cl is None or not cl.get("items"):
        probs.append("缺 #清单 段（脚本最后写 #清单，逐行 改 路径:函数名 / 新建 路径 / 删 路径）")
    if not re.search(r"^\s*预算\s", body, re.M):
        probs.append("开头缺 预算 语句（第二行写 预算 调用 N 秒 M）")
    for rx in OLD_RX_LINE.findall(main):
        try:
            re.compile(rx)
        except re.error as e:
            probs.append(f"# 旧写法 的正则不合法 {rx!r}：{e}")
    if probs:
        rec["阶段"] = "静态"
        return "白名单 / 格式检查没过：\n" + "\n".join(probs[:12]), main, subs, rec
    t0 = time.time()
    err, n, out = DP.dry_run(project, work, main, subs, task, scripts_for, MODEL, engine_cls=_engine_cls())
    rec.update(阶段="空跑", 空跑秒=round(time.time() - t0, 1), 空跑假调用=n)
    return (f"用假模型空跑报错：{err}" if err else ""), main, subs, rec


# ------------------------------------------------------------------ 5 验收


def enclosing(text, ln):
    """包含第 ln 行的最内层函数 (起, 止)；不在函数里返回 None。"""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    best = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.lineno - len(n.decorator_list)
            if a <= ln <= n.end_lineno and (best is None or n.end_lineno - a < best[1] - best[0]):
                best = (a, n.end_lineno)
    return best


def func_span(text, name):
    """名为 name（可带类名 A.f）的函数 / 类 (起, 止)。"""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    last = name.split(".")[-1]
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == last:
            return n.lineno - len(getattr(n, "decorator_list", [])), n.end_lineno
    return None


def scope_dirs(files):
    """查残留的范围：清单 / 改动文件所在的顶层目录（根目录下的文件就是它自己）。"""
    out = set()
    for f in files:
        parts = Path(f).parts
        out.add(parts[0] if len(parts) > 1 else f)
    return sorted(out)


def residuals(project, patterns, dirs, new_files):
    hits = []
    for s in patterns:
        try:
            rx = re.compile(s)
        except re.error:
            continue
        _, _, allh = K.grep(project, rx, limit=0, py_only=True, skip_tests=True, dirs=dirs)
        for rel, i, l in allh:
            if rel in new_files:
                continue
            hits.append({"文件": rel, "行": i, "该行": l.strip()[:200], "模式": s})
    return hits


def checklist_gaps(project, cl, changed_files):
    out = []
    for op, path, loc in (cl or {}).get("items") or []:
        exists = (Path(project) / path).is_file()
        if op in ("删", "删除"):
            ok = not exists
        elif op == "新建":
            ok = exists
        else:
            ok = exists and path in changed_files      # 位置（函数名）可能被正当删掉（改成 import），不核对
        if not ok:
            out.append({"文件": path, "操作": op, "位置": loc,
                        "说明": {"删": "该删没删", "删除": "该删没删", "新建": "该新建的文件不存在"}.get(op, "清单里要改，但文件没改动"
                                                                             if exists else "文件不存在")})
    return out


TB_LOC = re.compile(r"^\s+([\w./-]+\.py):(\d+)\s")


TRACE_REF = re.compile(r"(?:File \"([^\"\n]+)\", line (\d+)|([\w./-]+\.(?:py|zs|ui|entity)):(\d+))")


def _trace_refs(project, summary):
    """失败摘要里出现的 (项目内相对路径, 行号)，按出现顺序去重。"""
    root = str(Path(project).resolve()) + os.sep
    out = []
    for m in TRACE_REF.finditer(summary or ""):
        rel, ln = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if rel.startswith(root):
            rel = rel[len(root):]
        if (rel, int(ln)) not in out:
            out.append((rel, int(ln)))
    return out


def _fix_fallback(project, before, after, summary):
    """定位不到被改的源码函数时的退路：失败栈涉及的、本次改过的文件里行号前后各 30 行 → 本次改动所在函数 → diff。"""
    ch = set(changed(before, after))
    blks, total = [], 0
    for rel, ln in _trace_refs(project, summary):
        t = after.get(rel) if rel in ch else None
        if t is None:
            continue
        n = len(t.splitlines())
        s = K.snippet(project, rel, max(1, ln - 30), min(n, ln + 30), text=t)
        if total + len(s) > FIX_CAP:
            break
        total += len(s)
        blks.append(s)
    if blks:
        return "（没定位到函数；失败栈涉及的、本次改过的文件里相关片段，按行号前后各 30 行）\n\n" + "\n\n".join(blks)
    fn = _changed_funcs(project, before, after)
    if fn:
        return "（没定位到函数；本次改动所在函数的完整当前代码）\n\n" + fn
    diff = diff_text(before, after)
    return "未能定位，附 diff：\n" + (diff or "（本次没有任何文件改动）")


def _fix_user(project, task, gaps, before, after, test_summary=""):
    """补改入参：任务原文、新模块接口、缺口列表、每处缺口所在函数全文（当前代码）、文件开头。"""
    parts = [f"【任务原文】\n{task}"]
    news = [r for r in changed(before, after) if before.get(r) is None and r.endswith(".py") and after.get(r)]
    if news:
        parts.append("【本次新建的模块】\n" + "\n\n".join(
            f"（import 写法：from {K.modname(r)} import …）\n" + K.snippet(project, r, 1, 120) for r in news))
    parts.append("【缺口列表】\n" + "\n".join(f"{k}. {g['说明']}" for k, g in enumerate(gaps, 1)))
    if test_summary:
        parts.append("【全量测试失败摘要】\n" + test_summary[:4000])
    locs = []
    for g in gaps:
        if g.get("文件") and g.get("行"):
            locs.append((g["文件"], g["行"], None))
        elif g.get("文件") and g.get("位置"):
            locs.append((g["文件"], None, g["位置"]))
        elif g.get("文件"):
            locs.append((g["文件"], None, None))
    for l in (test_summary or "").splitlines():
        m = TB_LOC.match(l)
        if m and not K.is_test(m.group(1)):
            locs.append((m.group(1), int(m.group(2)), None))
    parts.append("【缺口所在函数的完整当前代码】")
    seen, total, got = set(), 0, False
    for rel in dict.fromkeys(x[0] for x in locs):
        t = K.read(project, rel)
        if t is None:
            continue
        n = len(t.splitlines())
        blk = [K.snippet(project, rel, 1, min(n, 25), text=t) + "\n（文件开头，供加 import）"]
        for r2, ln, name in locs:
            if r2 != rel:
                continue
            sp = (enclosing(t, ln) or (max(1, ln - 15), min(n, ln + 15))) if ln else \
                (func_span(t, name) if name else None) or (1, min(n, FN_CAP))
            a, b = sp[0], min(sp[1], sp[0] + FN_CAP - 1)
            if (rel, a) in seen:
                continue
            seen.add((rel, a))
            blk.append(K.snippet(project, rel, a, b, text=t))
        s2 = "\n\n".join(blk)
        if total + len(s2) > FIX_CAP:
            parts.append(f"（{rel} 等后面的代码超出长度上限，略）")
            break
        total += len(s2)
        got = got or len(blk) > 1
        parts.append(s2)
    if not got:
        parts.append(_fix_fallback(project, before, after, test_summary))
    return "\n\n".join(parts)


def _check_reply(rep):
    if not isinstance(rep, dict) or rep.get("状态") not in ("成功", "失败", "超出预期"):
        return "缺 状态，或 状态 不是 成功/失败/超出预期"
    if rep["状态"] == "成功":
        res = rep.get("结果")
        ed = res.get("edits") if isinstance(res, dict) else None
        if not isinstance(ed, list) or not all(isinstance(e, dict) and all(isinstance(e.get(k), str)
                                                                            for k in ("file", "old", "new")) for e in ed):
            return "结果.edits 必须是 [{file, old, new}] 列表（都是字符串）"
    return None


def dispatch_fix(M, project, system, user, tag):
    """派 1 次补改（回复不合格重答 1 次），能套就套。返回记录 {状态, 原因, 说明, edits, 套用, 套用说明, files}。"""
    rec = {"发生": True}
    try:
        txt = M(system, user, tag)
        try:
            rep = parse_json(txt)
            bad = _check_reply(rep)
        except ValueError as e:
            rep, bad = None, f"JSON 解析失败：{e}"
        if bad:
            txt = M(system, user + f"\n\n【你上一次的回复不合格：{bad}。请严格按回复格式只输出 JSON。】", tag + "_reask")
            try:
                rep = parse_json(txt)
                bad = _check_reply(rep)
            except ValueError as e:
                bad = f"JSON 解析失败：{e}"
    except (Stop, RuntimeError) as e:
        return {"发生": False, "原因": f"没派成：{e}"}
    if bad:
        rec.update(状态="回复不合格", 原因=bad)
        return rec
    res = rep.get("结果") if isinstance(rep.get("结果"), dict) else {}
    rec.update(状态=rep["状态"], 原因=str(rep.get("原因") or ""), 说明=str(res.get("说明") or "")[:1000])
    if isinstance(res.get("用例代码"), str) and res["用例代码"].strip():
        rec["用例代码"] = res["用例代码"]
    ed = res.get("edits") or []
    rec["edits"] = len(ed)
    if rep["状态"] == "成功" and ed:
        ok, msg = apply_edits(project, ed)
        if not ok:          # 整体套不上时逐条套，能套的先套上
            n_ok = sum(1 for e in ed if apply_edits(project, [e])[0])
            msg += f"；逐条套上 {n_ok}/{len(ed)}"
            ok = n_ok > 0
        rec.update(套用=ok, 套用说明=msg)
    return rec


# ------------------------------------------------------------------ 6 边界复核


def test_python(test_cmd):
    try:
        first = shlex.split(test_cmd or "")[0]
    except (IndexError, ValueError):
        return sys.executable
    return first if re.search(r"python[\d.]*$", Path(first).name) else sys.executable


def strip_code(text):
    t = (text or "").strip()
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", t, re.S)
    if m:
        return m.group(1).strip() + "\n"
    i = t.find("import ")
    return (t[i:] if i > 0 and not t.startswith(("import", "from", "#", '"""')) else t) + "\n"


FAIL_LINE = re.compile(r"^(FAIL|ERROR): (\w+) \(([^)]*)\)", re.M)


def run_boundary(project, test_cmd, bdir):
    """跑用例文件 bdir/test_boundary_v2.py。返回 {ok, ran, failed: [名], broken, tail, sec}。
    broken：用例文件本身跑不起来（语法错 / 导入错 / 一个用例都没跑到）。"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PROJ=str(Path(project).resolve()),
               PYTHONPATH=os.pathsep.join([str(bdir), str(Path(project).resolve())]))
    env.pop("PYTHONPYCACHEPREFIX", None)
    t0 = time.time()
    try:
        p = subprocess.run([test_python(test_cmd), "-m", "unittest", "-v", "test_boundary_v2"], cwd=project,
                           capture_output=True, text=True, timeout=BOUND_TIMEOUT, env=env, stdin=subprocess.DEVNULL)
        out, rc = (p.stderr or "") + (p.stdout or ""), p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"边界用例超过 {BOUND_TIMEOUT} 秒没跑完", None
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    ran = int(m.group(1)) if m else 0
    failed = [(n, c) for _, n, c in FAIL_LINE.findall(out)]
    broken = rc is None or ran == 0 or any("_FailedTest" in c or n == "test_boundary_v2" for n, c in failed)
    docs = _docs(bdir / "test_boundary_v2.py")
    return {"ok": rc == 0 and ran > 0, "ran": ran, "failed": [n for n, _ in failed],
            "failed_desc": [f"{n}（{docs.get(n, '')}）" if docs.get(n) else n for n, _ in failed],
            "broken": broken, "tail": out[-6000:], "sec": round(time.time() - t0, 1)}


def _docs(f):
    try:
        tree = ast.parse(Path(f).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return {}
    return {n.name: (ast.get_docstring(n) or "").strip().splitlines()[0] if ast.get_docstring(n) else ""
            for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test")}


def _changed_funcs(project, before, after, cap=FIX_CAP):
    """改动过的 .py 里，改动行所在函数的完整当前代码（新建文件给全文前 200 行）。"""
    parts, total = [], 0
    for rel in changed(before, after):
        a, b = before.get(rel), after.get(rel)
        if b is None or not rel.endswith(".py"):
            continue
        if a is None:
            s = K.snippet(project, rel, 1, 200, text=b)
        else:
            lines = set()
            sm = difflib.SequenceMatcher(None, a.splitlines(), b.splitlines(), autojunk=False)
            for tag, _, _, j1, j2 in sm.get_opcodes():
                if tag != "equal":
                    lines.update(range(j1 + 1, max(j1 + 1, j2) + 1))
            spans = sorted({enclosing(b, ln) or (max(1, ln - 10), ln + 10) for ln in lines})
            n = len(b.splitlines())
            s = "\n\n".join([K.snippet(project, rel, 1, min(n, 25), text=b) + "\n（文件开头）"] +
                            [K.snippet(project, rel, x, min(y, x + FN_CAP - 1), text=b) for x, y in spans])
        if total + len(s) > cap:
            break
        total += len(s)
        parts.append(s)
    return "\n\n".join(parts)


# ------------------------------------------------------------------ 主流程


def run(project, task, out_dir, test_cmd=None, wall=WALL, model=None, max_calls=MAX_CALLS, boundary=True):
    """跑一次 v2。project 里直接改文件；记录写进 out_dir（calls/、calls.json、plan*.zs、pack*.md、boundary/、result.json）。
    model：假模型 backend(system, user, tag, timeout) → str|dict（测试用），缺省走 claude CLI。
    返回结果字典（runner.run 同款字段 + reply / v2）。"""
    from . import plan as DP
    from . import prompts as DPR
    from .runner import detect_test_cmd

    project = Path(project).resolve()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    test_cmd = test_cmd or detect_test_cmd(project)
    M = Model(out, backend=model, max_calls=max_calls, deadline=t_start + wall)
    steps, info = {}, {"补查": None, "够了": None, "补查项": 0, "数据包字符": 0, "检查": [], "重写": False,
                       "子任务模式": DC.env_mode(), "子任务": []}
    res = {"project": str(project), "test_cmd": test_cmd, "kind": "task", "planner": "v2", "fixed": False,
           "engine_used": "v2", "versions": 0, "calls": 0, "cost": 0.0, "seconds": 0, "stop": "", "dir": str(out),
           "calls_log": str(out / "calls.json"), "version_log": [], "subcalls": [], "changed_files": [], "handoff": "",
           "report": "", "v2": info}
    state = {"状态": "失败", "原因": ""}
    accept, bound = {}, {"跑了": False}

    def step(name, t0):
        steps[name] = round(time.time() - t0, 1)

    if not test_cmd:
        state["原因"] = "项目里探测不到测试（没有 tests/、test_*.py 或 pytest 配置），v2 要靠测试验收；可以传 test_cmd"
        return _finish(res, out, M, steps, state, accept, bound, {}, {}, t_start)
    os.environ["DSLAGENT_STATE"] = str(out / "state")
    os.environ["DSLAGENT_TEST_CMD"] = test_cmd
    os.environ.setdefault("DSLAGENT_TEST_TIMEOUT", str(TEST_TIMEOUT))
    base = snapshot(project)
    cur = base
    main, subs, script = "", {}, ""
    try:
        # ---- 1 数据包
        t0 = time.time()
        pack, pinfo = K.build(project, task)
        info.update(候选=pinfo["cands"], 测试断言文件=list(pinfo["test_files"]))
        step("1数据包", t0)
        # ---- 2 补查
        t0 = time.time()
        txt = M(PRE_SYS, plan_user(task, pack), "preq")
        try:
            q = parse_json(txt)
        except ValueError as e:
            q = {"够了": True, "_err": str(e)}
        info["补查"] = q
        info["够了"] = bool(q.get("够了")) if isinstance(q, dict) else True
        extra = ""
        if not info["够了"]:
            extra, info["补查记录"], qfiles = K.run_queries(project, q)
            info["补查项"] = len(info["补查记录"])
            ta, tf = K.test_asserts(project, qfiles - set(pinfo["cands"]), skip=set(pinfo["test_files"]))
            if ta:
                extra += "\n\n" + ta
                info["测试断言文件"] += tf
        full_pack = pack + ("\n\n" + extra if extra else "")
        info["数据包字符"] = len(full_pack)
        (out / "pack.md").write_text(full_pack, encoding="utf-8")
        step("2补查", t0)
        # ---- 3 规划
        t0 = time.time()
        problem = ""
        plan_model = os.environ.get("DSLAGENT_PLAN_MODEL") or MODEL
        info["规划模型"] = res["plan_model"] = plan_model
        for k in range(2):
            raw = M(plan_system(), plan_user(task, full_pack) if k == 0 else DPR.fix_prompt(script, problem),
                    "plan" if k == 0 else "plan_fix", model=plan_model)
            (out / f"plan_v{k + 1}.raw.txt").write_text(raw, encoding="utf-8")
            script, _ = DP.strip_prose(raw)
            script, n_close, _ = DP.autoclose(script)
            (out / f"plan_v{k + 1}.zs").write_text(script, encoding="utf-8")
            problem, main, subs, crec = check(project, out / "dry", script, task)
            info["检查"].append(dict(crec, 补结束=n_close, 问题=problem[:1500]))
            if not problem:
                break
            info["重写"] = True
        step("3规划", t0)
        if problem:
            raise Stop("计划 .zs 重写 1 次仍没过检查：" + problem[:400])
        (out / "plan.zs").write_text(script, encoding="utf-8")
        # ---- 4 执行
        t0 = time.time()
        gate = test_gate(main)
        info["测试闸门"] = {str(k + 1): v for k, v in gate.items()}
        plan_dir = out / "plan_subs"
        DP.write_subs(plan_dir, subs)
        Eng = _engine_cls()
        eng = Eng(client=Client(M), workdir=project, verbose=False, verbs_root=VERBS,
                  scripts=scripts_for(plan_dir, subs), on_call=res["subcalls"].append)
        eng.gate, eng.project, eng.tests = gate, project, []
        eng.model = MODEL
        eng.sublog = info["子任务"]
        eng.vars["task"] = task
        err = ""
        try:
            eng.run(main)
        except Exception as e:  # noqa: BLE001  脚本报错按失败处理
            err = f"{type(e).__name__}: {str(e)[:800]}"
        halted = eng.halted
        (out / "plan_out.txt").write_text("\n".join(eng.output) + (f"\n\n[报错] {err}" if err else "")
                                          + f"\n\n[终止] {json.dumps(halted, ensure_ascii=False)}", encoding="utf-8")
        info.update(终止=halted, 报错=err, 清单=eng.checklist, 计划内测试=eng.tests,
                    预算={"calls": eng.usage.calls, "max_calls": eng.usage.max_calls, "max_secs": eng.usage.max_secs})
        step("4执行", t0)
        res["versions"] = 1
        if err:
            raise Stop(f"脚本报错：{err}")
        if not halted:
            raise Stop("脚本跑完没有 终止（没自报成功）")
        if halted.get("状态") != "成功":
            state["状态"] = "超出预期" if halted.get("状态") == "超出预期" else "失败"
            raise Stop(f"脚本终止 {halted.get('状态')}：{str(halted.get('原因'))[:300]}")
        # ---- 5 验收
        t0 = time.time()
        cur = snapshot(project)
        old_rx = OLD_RX_LINE.findall(main)
        ch = changed(base, cur)
        new_files = {r for r in ch if base.get(r) is None}
        cl_files = [p for _, p, _ in (eng.checklist or {}).get("items") or []]
        dirs = scope_dirs(ch + cl_files)
        accept.update(旧写法=old_rx, 范围=dirs)

        def audit(snap_now):
            chn = changed(base, snap_now)
            hits = residuals(project, old_rx, dirs, {r for r in chn if base.get(r) is None}) if old_rx else []
            gaps = checklist_gaps(project, eng.checklist, set(chn))
            return hits, gaps

        def test_now(snap_now, tag):
            h = code_hash(snap_now)
            last = next((x for x in reversed(eng.tests) if x["mode"] == "real" and x.get("known")), None)
            if last and last["hash"] == h:
                r = {"passed": last["passed"], "summary": last["summary"], "sec": 0.0, "mode": "复用"}
            else:
                r = dict(full_test(project, test_cmd), mode="真跑")
                eng.tests.append({"line": tag, "mode": "real", "sec": r["sec"], "passed": r["passed"],
                                  "summary": r["summary"][:4000], "hash": h, "known": True})
            accept.setdefault("测试", []).append({"步": tag, "通过": r["passed"], "秒": r["sec"], "方式": r["mode"]})
            return r
        hits, gaps = audit(cur)
        t = test_now(cur, "验收")
        accept.update(残留=len(hits), 残留列表=hits[:40], 清单缺口=gaps)
        if hits or gaps or not t["passed"]:
            glist = [dict(h, 说明=f"{h['文件']}:{h['行']} 还有旧写法（匹配 {h['模式']}）：{h['该行']}") for h in hits[:30]]
            glist += [dict(g, 说明=f"清单 {g['操作']} {g['文件']}{':' + g['位置'] if g.get('位置') else ''}：{g['说明']}")
                      for g in gaps]
            if not t["passed"]:
                glist.append({"说明": "全量测试没过（失败摘要见下）"})
            accept["补改"] = dispatch_fix(M, project, FIX_SYS, _fix_user(project, task, glist, base, cur,
                                                                       "" if t["passed"] else t["summary"]), "fix")
            cur = snapshot(project)
            hits, gaps = audit(cur)
            t = test_now(cur, "补改后")
            accept.update(补改后残留=len(hits), 补改后残留列表=hits[:40], 补改后清单缺口=gaps)
        accept["通过"] = t["passed"] and not hits and not gaps
        accept["测试摘要"] = t["summary"][:2000]
        step("5验收", t0)
        if not accept["通过"]:
            why = [] if t["passed"] else ["全量测试没过：" + t["summary"][:300]]
            why += [f"仍有 {len(hits)} 处旧写法残留（{hits[0]['文件']}:{hits[0]['行']}）"] if hits else []
            why += ["清单没做到：" + "；".join(f"{g['操作']} {g['文件']}" for g in gaps[:4])] if gaps else []
            state.update(状态="失败", 原因="验收没过（已派 1 次补改）：" + "；".join(why))
            raise _Done()
        # ---- 6 边界复核
        if boundary:
            t0 = time.time()
            state.update(_boundary(M, project, task, test_cmd, base, out, bound, test_now))
            step("6边界复核", t0)
        else:
            state.update(状态="成功", 原因="")
    except _Done:
        pass
    except Stop as e:
        state["原因"] = str(e)
        if state["状态"] == "成功":
            state["状态"] = "失败"
    except Exception as e:  # noqa: BLE001  流程自身出错不能让 cbatch 拿不到结果
        state.update(状态="失败", 原因=f"v2 流程出错：{type(e).__name__}: {str(e)[:400]}")
    if state["状态"] != "成功" and not accept:
        # 计划没跑成（检查没过 / 报错 / 没自报成功）：回滚到开局，项目保持原样
        now = snapshot(project)
        restore(project, base, changed(base, now))
        info["回滚"] = changed(base, now)
    return _finish(res, out, M, steps, state, accept, bound, base, snapshot(project), t_start)


class _Done(Exception):
    pass


def _boundary(M, project, task, test_cmd, base, out, bound, test_now):
    """边界复核。返回 {状态, 原因}。"""
    cur = snapshot(project)
    diff = diff_text(base, cur)
    bdir = out / "boundary"
    bdir.mkdir(parents=True, exist_ok=True)
    bound["跑了"] = True
    try:
        code = strip_code(M(BOUND_SYS, f"【任务原文】\n{task}\n\n【改动（diff，新建文件给全文）】\n{diff}", "bound"))
    except (Stop, RuntimeError) as e:
        bound["结论"] = f"没生成用例（{e}），未复核"
        return {"状态": "成功", "原因": ""}
    (bdir / "test_boundary_v2.py").write_text(code, encoding="utf-8")
    r = run_boundary(project, test_cmd, bdir)
    bound["第1次"] = {k: r[k] for k in ("ok", "ran", "failed_desc", "broken", "sec")}
    (bdir / "run1.txt").write_text(r["tail"], encoding="utf-8")
    if r["ok"]:
        bound["结论"] = f"{r['ran']} 个用例全过"
        return {"状态": "成功", "原因": ""}
    if r["broken"]:
        bound["结论"] = f"用例文件跑不起来，未复核：{r['tail'][-300:]}"
        return {"状态": "成功", "原因": ""}
    names = "、".join(r["failed_desc"])
    user = (f"【任务原文】\n{task}\n\n【改动（diff）】\n{diff}\n\n【边界用例】\n```python\n{code}```\n\n"
            f"【没过的用例和输出】\n{r['tail'][-5000:]}\n\n【改动所在函数的完整当前代码】\n{_changed_funcs(project, base, cur)}")
    fx = dispatch_fix(M, project, BFIX_SYS, user, "bfix")
    new_case = strip_code(fx.pop("用例代码", "")) if fx.get("用例代码") and fx.get("状态") == "成功" else ""
    bound["补改"] = dict(fx, 改了用例=bool(new_case))
    if new_case:            # 用例自身的编程错误：换成改好的用例文件（原文件留作 test_boundary_v2.run1.py）
        (bdir / "test_boundary_v2.run1.py").write_text(code, encoding="utf-8")
        (bdir / "test_boundary_v2.py").write_text(new_case, encoding="utf-8")
    after = snapshot(project)
    if not changed(cur, after) and not new_case:
        bound["结论"] = f"用例没过：{names}；补改没改代码（{fx.get('状态', '')}：{fx.get('原因', '')[:200]}）"
        return {"状态": "超出预期", "原因": f"边界复核：用例 {names} 没过；补改没有改代码"
                + (f"（补改说：{fx.get('原因', '')[:200]}）" if fx.get("原因") else "")}
    r2 = run_boundary(project, test_cmd, bdir)
    bound["第2次"] = {k: r2[k] for k in ("ok", "ran", "failed_desc", "broken", "sec")}
    (bdir / "run2.txt").write_text(r2["tail"], encoding="utf-8")
    t = test_now(after, "边界补改后")
    if not t["passed"]:
        restore(project, cur, changed(cur, after))
        bound["结论"] = f"用例 {names} 没过；补改弄坏了现有测试，已撤回"
        return {"状态": "超出预期", "原因": f"边界复核：用例 {names} 没过；补改会让现有测试失败，已撤回补改"}
    if r2["ok"]:
        what = "、".join(x for x, y in (("改了代码", changed(cur, after)), ("修了用例自身的错", new_case)) if y)
        bound["结论"] = f"用例 {names} 第 1 次没过，补改（{what}）后全过"
        return {"状态": "成功", "原因": ""}
    if r2["broken"]:
        bound["结论"] = f"用例 {names} 没过；补改后用例文件跑不起来：{r2['tail'][-300:]}"
        return {"状态": "超出预期", "原因": f"边界复核：用例 {names} 没过；补改后用例文件跑不起来"}
    left = "、".join(r2["failed_desc"]) or names
    bound["结论"] = f"补改后用例 {left} 仍没过"
    return {"状态": "超出预期", "原因": f"边界复核：补改后用例 {left} 仍没过"}


def _finish(res, out, M, steps, state, accept, bound, base, now, t_start):
    ch = changed(base, now) if base else []
    res.update(fixed=state["状态"] == "成功", stop="" if state["状态"] == "成功" else state["原因"],
               calls=M.n, cost=round(M.cost, 4), seconds=round(time.time() - t_start, 1), changed_files=ch,
               diff=diff_text(base, now, 3000) if base else "", status=state["状态"])
    res["calls_by_purpose"] = {}
    for c in M.log:
        k = re.sub(r"\d+$|_reask$", "", c["tag"])
        res["calls_by_purpose"][k] = res["calls_by_purpose"].get(k, 0) + 1
    res["v2"].update(步骤秒=steps, 验收=accept, 边界复核=bound)
    tests = res["v2"].get("计划内测试") or []
    res["final_test"] = (accept.get("测试摘要") or "")[:2000]
    res["reply"] = {"结果": {"改动文件": ch, "测试": accept.get("测试摘要", "")[:300],
                           "边界复核": bound.get("结论", "未跑"), "步骤秒": steps, "调用": M.n,
                           "费用": round(M.cost, 4), "测试次数": {
                               "真跑": sum(1 for x in tests if x["mode"] == "real"),
                               "跳过": sum(1 for x in tests if x["mode"] == "skipped"),
                               "复用": sum(1 for x in accept.get("测试", []) if x["方式"] == "复用")}},
                    "状态": state["状态"], "原因": state["原因"]}
    res["report"] = report(res)
    if not res["fixed"]:
        res["handoff"] = (f"【停下原因】（v2 规划路径，状态 {state['状态']}）{state['原因']}\n"
                          f"【它已经做的修改（相对开始时的 diff）】\n{res['diff'] or '（没有改动）'}\n"
                          f"【当前测试】\n{res['final_test'] or '（没跑到验收）'}")[:7000]
    try:
        (out / "calls.json").write_text(json.dumps(M.log, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass
    return res


def report(res):
    r = res["reply"]
    head = (f"DSL v2 {r['状态']}" + (f"：{r['原因']}" if r["原因"] else "")
            + f"；{res['calls']} 次模型调用，${res['cost']:.4f}，{res['seconds']}s")
    lines = [head, "各步秒：" + "，".join(f"{k} {v}" for k, v in r["结果"]["步骤秒"].items()),
             f"边界复核：{r['结果']['边界复核']}"]
    if res.get("changed_files"):
        lines.append("改动：" + "、".join(res["changed_files"]))
    lines.append(f"测试命令：{res['test_cmd']}")
    lines.append(f"记录：{res['dir']}")
    return "\n".join(lines)
