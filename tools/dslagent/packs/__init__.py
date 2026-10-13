"""资料包（pack）：v2 规划核心按任务类型插拔的「收集资料」那一半。选择：环境变量 DSLAGENT_PACK（缺省 code）。

核心（v2.py）只认下面这套接口，不知道资料是什么。一个资料包 = 本目录下的一个模块（或带这些名字的任何对象），
在 REGISTRY 里登记名字即可；目前只有 code（改代码任务：文件大纲）。

接口（模块级名字）：
  NAME                  str，取值名（= DSLAGENT_PACK 的值）。
  plan_outline(task, project) -> dict      （可选；不实现就只给任务原文）
      只产「文件大纲」，规划的 user = 任务原文 + 大纲：{"text": 大纲文本, "refs": [候选文件], "记录": {…并进 v2.*}}；
      不收代码片段 / 引用行 / 测试断言（规划自己用只读 dsl 工具读）。确定性，不调模型。
  files(project)        迭代 (相对路径, 绝对路径)：这类任务里「会被改动 / 要做快照」的文件（snap.snapshot 用它）。
  TASK_DESC, PACK_DESC  str，说明性文字（规划提示 agents/plan.md 开头已按 code 包写死，现在不再拼进提示）。
  PLAN_RULES            str，规划提示里这类任务专属的规则行（每行以「- 」开头），插在通用规则中间；文本在 agents/shared/plan_rules_<RULES_KEY>.md，由 agents/plan.md 插入。
  RULES_KEY             str（可选，缺省取 NAME），上面两个规则文件名里的「包名」。
  PLAN_RULES_END        str，同上，插在「终止」规则之后、「只输出 .zs」之前。
  plan_problems(main, body, cl, generic) -> list[str]
      计划静态检查里这类任务专属的问题；generic 是核心已查出的通用问题（如缺 预算），按包希望的顺序合并后整体返回。

以后加「文档」「数据」类资料包要实现的：上面全部名字。plan_outline 给文档段落 / 表结构的大纲、
files 给要快照的文档 / 数据文件、PLAN_RULES 写这类任务的计划写法；配套的验收见 tools/dslagent/verify/。
"""
import importlib
import os

REGISTRY = {"code": "tools.dslagent.packs.code"}
DEFAULT = "code"


def available():
    return sorted(REGISTRY)


def pick(name):
    """按取值拿资料包模块；不认识的名字报 ValueError（列出可用的）。"""
    n = (name or DEFAULT).strip().lower() or DEFAULT
    if n not in REGISTRY:
        raise ValueError(f"DSLAGENT_PACK 取值不对：{name!r}，可用：{'、'.join(available())}")
    return importlib.import_module(REGISTRY[n])


def current():
    """环境变量 DSLAGENT_PACK 选的资料包（缺省 code）。"""
    return pick(os.environ.get("DSLAGENT_PACK"))
