"""v3 动词共用：取运行上下文、把致命错误变成「终止」。"""
from tools.dsl_core import ScriptHalt


def ctx():
    from tools.dslagent.v3.core import ctx_of
    return ctx_of()


def fail(reason):
    raise ScriptHalt("失败", str(reason), "")


def numbered(problems):
    return "\n".join(f"{i}. {p}" for i, p in enumerate(problems, 1))
