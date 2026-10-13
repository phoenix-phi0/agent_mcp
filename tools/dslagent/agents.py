"""v2 里各个 agent（模型调用角色）的定义，集中在这一处：调用处从这里取步骤、提示、工具、轮数、回复格式、重试策略。

每个 Agent：
  step      models 里的键（plan / sub / fix / bound），决定用哪个引擎和模型（engines.step_of）
  system    system 提示：prompts/ 下的文件名（PF.text 逐字读）；规划的 system 要按资料包 / 引擎拼，写成 system_fn（"模块:函数"）
  user_fn   user 的拼装函数（"模块:函数"，延迟导入）
  tools     TOOLS_* 之一：无 / 只读 dsl / grok 自带只读 / 可写 dsl（tools_grok：grok 引擎换成这个）
  turns     多轮调用的 --max-turns（没有工具的 agent 是 1）；turns_grok：grok 引擎的轮数
  reply     回复格式：zs（.zs 计划文本）/ json（{结果,状态,原因}）/ code（一段 python 代码）
  parser    解析器（"模块:函数"；json 回复统一走 dsl_task.parse_check：补括号 / 状态上提 + {结果,状态,原因} 校验）
  retry     Retry(次数, 方式, 用尽后)：方式 = 原样重试 / 带问题重问 / 重写；用尽后 = 退回 json 或空
tag（calls.json 里的调用标记）→ agent 见 of_tag。
"""
import importlib
import re
from dataclasses import dataclass

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
    system: str = ""
    system_fn: str = ""
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

    def system_text(self, *a, **k):
        if self.system_fn:
            return self.load(self.system_fn)(*a, **k)
        from . import promptfile as PF
        return PF.text(self.system) if self.system else ""


PLAN = Agent("plan", "plan", system_fn="v2:plan_system", user_fn="v2:plan_user_read",
             tools=TOOLS_RO, tools_grok=TOOLS_GROK, turns=12, turns_grok=20, reply="zs", parser="plan:strip_prose",
             retry=Retry(2, RETRY_SAME), rewrites=1)
PLAN_FIX = Agent("plan_fix", "plan", system_fn="v2:plan_system", user_fn="prompts:fix_prompt",
                 tools=TOOLS_RO, tools_grok=TOOLS_GROK, turns=12, turns_grok=20, reply="zs", parser="plan:strip_prose",
                 retry=Retry(2, RETRY_SAME))
SUB_JSON = Agent("sub_json", "sub", system="sub_sys.txt", user_fn="tools.dsl_task:build_prompt",
                 reply="json", parser="tools.dsl_task:parse_check", retry=Retry(2, RETRY_ASK))
SUB_TOOL = Agent("sub_tool", "sub", system="toolsub_system.txt", user_fn="tools.dsl_task:build_prompt",
                 tools=TOOLS_RW, turns=6, reply="json", parser="tools.dsl_task:parse_check", retry=Retry(2, RETRY_SAME, FALLBACK_JSON))
FIX = Agent("fix", "fix", system="verify/code/fix_sys.txt", user_fn="verify.code:_fix_user",
            reply="json", parser="tools.dsl_task:parse_check", retry=Retry(2, RETRY_ASK))
BOUND = Agent("bound", "bound", system="verify/code/bound_sys.md", reply="code", parser="verify.code:strip_code")
BFIX = Agent("bfix", "bound", system="verify/code/bfix_sys.txt", reply="json", parser="tools.dsl_task:parse_check",
             retry=Retry(2, RETRY_ASK))

AGENTS = {a.name: a for a in (PLAN, PLAN_FIX, SUB_JSON, SUB_TOOL, FIX, BOUND, BFIX)}


def of_tag(tag):
    """调用 tag → Agent（plan / plan_fix / dslNN / dslNN_toolK / fix / bound / bfix，后缀 _reask 归同一个）；不认识返回 None。"""
    t = re.sub(r"_reask$", "", tag or "")
    if re.match(r"^dsl\d+_tool", t):
        return SUB_TOOL
    if re.match(r"^dsl\d+", t):
        return SUB_JSON
    return AGENTS.get(t)
