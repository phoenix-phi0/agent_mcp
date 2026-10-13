"""模型调用的保险：常量只在这一处（四个引擎、Model、toolsub 共用；测试要改阈值就改这里的值）。

保险触发 = 进程被杀，原因是下面 GUARD_REASONS 之一（R_*）；失败原因也用这些常量比较，不写字面量。
"""
IDLE_SEC = 60            # 首 token 之后这么久没有新流事件就杀掉该次调用（claude / codex / grok）
IDLE_OC = 120            # opencode 整段才发事件，空闲超时比逐字流宽
IDLE_MCP = 180           # codex 挂 MCP（工具调用慢）时的空闲超时
FIRST_CAP = 120          # 首个事件之前最多静默这么久（四个引擎；codex / grok / opencode 可用 DSLAGENT_*_FIRST_CAP 覆盖）
MAX_OUT = 20000          # 单次调用累计输出超过这么多字符就杀掉
TOOL_MARKS = ("<invoke", "<function_calls")   # 流里出现这些 = 模型在写工具调用格式
CALL_MAX = 300           # 单次调用总超时上限
CALL_MIN = 30            # 剩余墙钟再少也给这么多

R_TOTAL = "总超时"
R_FIRST = "首字前静默超时"
R_IDLE = "空闲超时"
R_MARK = "输出工具调用格式"
R_LONG = "输出超长"
R_TRY_TOOL = "尝试调用工具"
R_BAD_TOOL = "调用被禁工具"
R_READ_CAP = "读超限"
GUARD_REASONS = (R_FIRST, R_IDLE, R_MARK, R_LONG, R_TRY_TOOL, R_BAD_TOOL, R_READ_CAP)

# 失败原因（非保险）
F_TURNS = "轮数用尽"
F_EMPTY = "空回复"


def call_timeout(left):
    """单次调用的总超时：剩余墙钟 + 5 秒，夹在 CALL_MIN..CALL_MAX 之间（left=None 用 CALL_MAX）。"""
    if left is None:
        return CALL_MAX
    return max(CALL_MIN, min(CALL_MAX, left + 5))


def has_mark(text):
    return any(m in (text or "") for m in TOOL_MARKS)
