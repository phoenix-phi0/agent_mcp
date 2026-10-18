"""v2 里各个 agent（模型调用角色）的定义，集中在这一处：调用处从这里取步骤、提示、工具、轮数、回复格式、重试策略。

人读的内容都在 agents/<名>.md（frontmatter：名称 / 步骤 / 工具 / 最多轮数 / 回复格式 / 失败时怎么办 / 输入；正文 = 完整 system 提示词），
公用大块在 agents/shared/；解析、展开插入、选变体在 promptfile.py（见 agents/README.md）。这里只留 Python 才能表达的东西：

每个 Agent：
  step      models 里的键（plan / plan_fix / sub / fix / bound），决定用哪个引擎和模型（engines.step_of）        ← md「步骤」
  tools     TOOLS_* 之一：无 / 只读 dsl / grok 自带只读 / 可写 dsl（tools_grok：grok 引擎换成这个）      ← md「工具」
  turns     多轮调用的 --max-turns（没有工具的 agent 是 1）；turns_grok：grok 引擎的轮数                ← md「最多轮数」
  reply     回复格式：zs（.zs 计划文本）/ json（{结果,状态,原因}）/ code（一段 python 代码）            ← md「回复格式」
  user_fn   user 的拼装函数（"模块:函数"，延迟导入）                                                   （代码里）
  parser    解析器（"模块:函数"；json 回复统一走 dsl_task.parse_check：补括号 / 状态上提 + {结果,状态,原因} 校验）（代码里）
  retry     Retry(次数, 方式, 用尽后)：方式 = 原样重试 / 带问题重问 / 重写；用尽后 = 退回 json 或空         （代码里；次数要与 md「失败时怎么办」里的「最多 N 次」一致，加载时核对）
tag（calls.json 里的调用标记）→ agent 见 of_tag。
"""
import importlib
import re
from dataclasses import dataclass

from . import promptfile as PF

TOOLS_NONE = "无"
TOOLS_RO = "只读dsl"
TOOLS_GROK = "grok自带只读"
TOOLS_RW = "可写dsl"

RETRY_SAME = "原样重试"        # 同输入再来一次（保险触发 / rc≠0 / 空回复）
RETRY_ASK = "带问题重问"       # 把上次回复和问题发回去
RETRY_REWRITE = "重写"         # 计划检查没过：带问题重写
FALLBACK_JSON = "退回json"     # tool 模式用尽后退回 json 模式
NONE = ""


@dataclass(frozen=True)
class Retry:
    times: int = 1             # 最多尝试几次（含第一次）
    how: str = NONE
    then: str = NONE           # 用尽后怎么办


@dataclass(frozen=True)
class Agent:
    name: str
    step: str
    file: str = ""             # agents/ 下的文件名
    user_fn: str = ""
    tools: str = TOOLS_NONE
    tools_grok: str = ""
    turns: int = 1
    turns_grok: int = 0
    reply: str = "json"
    parser: str = ""
    retry: Retry = Retry()
    rewrites: int = 0          # 计划检查没过时带问题重写几次（plan_fix）

    def tools_for(self, engine):
        return self.tools_grok if engine == "grok" and self.tools_grok else self.tools

    def turns_for(self, engine):
        return self.turns_grok if engine == "grok" and self.turns_grok else self.turns

    def load(self, ref):
        """"模块:函数" → 对象（模块相对 tools.dslagent）。"""
        mod, _, attr = ref.partition(":")
        return getattr(importlib.import_module(mod if mod.startswith("tools.") else f"tools.dslagent.{mod}"), attr)

    def system_text(self, engine=None, pack=None):
        """完整 system 提示词：展开 agents/<file> 的插入，再按引擎选变体；pack 是资料包名（缺省 code）。"""
        return PF.render(self.file, engine, 包=pack or "code")


def for_engine(system, tag, engine):
    """system 恰好是该 tag 的 agent 默认（Claude）渲染时，按引擎换成它的变体渲染；其余（规划已按引擎渲染、调用方自带的 system）原样。
    目前只有 codex 在 sub / sub_tool / fix / bfix 的「变体：codex」里有不同写法（带「思路」字段）。"""
    a = of_tag(tag)
    if engine != "codex" or a is None or a is PLAN or system != a.system_text():
        return system
    return a.system_text(engine)


def _split(v, what):
    """「默认值；引擎：值」→ (默认值, {引擎: 值})。"""
    head, *rest = [x.strip() for x in v.split("；") if x.strip()]
    over = {}
    for r in rest:
        k, sep, x = r.partition("：")
        if not sep:
            raise ValueError(f"agent 文件里「{what}」的写法不对：{v!r}（应为「默认值；引擎：值」）")
        over[k.strip()] = x.strip()
    return head, over


def _agent(file, user_fn="", parser="", retry=Retry(), rewrites=0):
    d = PF.agent_doc(file)
    m = d.meta
    for k in ("名称", "步骤", "工具", "最多轮数", "回复格式", "失败时怎么办", "输入"):
        if k not in m:
            raise ValueError(f"{d.path} 的 frontmatter 缺「{k}」")
    tools, tg = _split(m["工具"], "工具")
    turns, ug = _split(m["最多轮数"], "最多轮数")
    n = re.search(r"最多\s*(\d+)\s*次", m["失败时怎么办"])
    if retry.times > 1 and not (n and int(n.group(1)) == retry.times):
        raise ValueError(f"{d.path} 的「失败时怎么办」要写「最多 {retry.times} 次」，与 agents.py 里的 Retry 对上")
    return Agent(m["名称"], m["步骤"], file, user_fn, tools, tg.get("grok", ""), int(turns), int(ug.get("grok", 0)),
                 re.split(r"[（(]", m["回复格式"])[0].strip(), parser, retry, rewrites)


PLAN = _agent("plan.md", "v2:plan_user_read", "plan:strip_prose", Retry(2, RETRY_SAME), rewrites=1)
PLAN_FIX = _agent("plan_fix.md", "prompts:fix_prompt", "plan:strip_prose", Retry(2, RETRY_SAME))
SUB_JSON = _agent("sub.md", "tools.dsl_task:build_prompt", "tools.dsl_task:parse_check", Retry(2, RETRY_ASK))
SUB_TOOL = _agent("sub_tool.md", "tools.dsl_task:build_prompt", "tools.dsl_task:parse_check", Retry(2, RETRY_SAME, FALLBACK_JSON))
FIX = _agent("fix.md", "verify.code:_fix_user", "tools.dsl_task:parse_check", Retry(2, RETRY_ASK))
BOUND = _agent("bound.md", parser="verify.code:strip_code")
BFIX = _agent("bfix.md", parser="tools.dsl_task:parse_check", retry=Retry(2, RETRY_ASK))
BOUND_JUDGE = _agent("bound_judge.md", parser="verify.bound_table:parse_judge", retry=Retry(2, RETRY_ASK))
TABLE_FILL = _agent("bound_table_fill.md", user_fn="verify.bound_table:fill_user", parser="verify.bound_table:parse_rows")

AGENTS = {a.name: a for a in (PLAN, PLAN_FIX, SUB_JSON, SUB_TOOL, FIX, BOUND, BFIX, BOUND_JUDGE, TABLE_FILL)}


def of_tag(tag):
    """调用 tag → Agent（plan / plan_fix / plan_wrapup（grok 读超限后的收尾，归 plan）/ dslNN / dslNN_toolK / fix / bound / bfix /
    bound_judge / table_fill（补表，归 plan 步骤），后缀 _reask 归同一个）；不认识返回 None。"""
    t = re.sub(r"_reask$", "", tag or "")
    if t == "plan_wrapup":
        return PLAN
    if re.match(r"^dsl\d+_tool", t):
        return SUB_TOOL
    if re.match(r"^dsl\d+", t):
        return SUB_JSON
    return AGENTS.get(t)
