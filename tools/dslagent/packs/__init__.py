"""资料包（pack）：v2 规划核心按任务类型插拔的「收集资料」那一半。选择：环境变量 DSLAGENT_PACK（缺省 code）。

核心（v2.py）只认下面这套接口，不知道资料是什么。一个资料包 = 本目录下的一个模块（或带这些名字的任何对象），
在 REGISTRY 里登记名字即可；目前只有 code（改代码任务：候选模块 / 引用行 / 登记处 / 测试断言 / 文件大纲）。

接口（模块级名字）：
  NAME                  str，取值名（= DSLAGENT_PACK 的值）。
  collect(task, project, limits=None) -> dict
      确定性收集（不调模型），在规划前跑一次。入参：task 任务原文；project 项目目录；limits 可选 {"budget": 总字符上限}。
      出参：{"text": 资料包文本（索引 + 正文，拼进规划提示的【数据包】）,
             "refs": [引用列表：这份资料包选中的文件 / 条目，补查后做增补用],
             "info": 包自己的内部信息（交回给 extra）,
             "记录": 要并进结果记录 v2.* 的字段（如 {"候选": [...], "测试断言文件": [...]}）}
  plan_outline(task, project) -> dict      （可选；规划 plan_mode=read 用，不实现就只给任务原文）
      只产「文件大纲」：{"text": 大纲文本, "refs": [候选文件], "记录": {…并进 v2.*}}；不收代码片段 / 引用行 / 测试断言（规划自己用 dsl 工具读）。
  extra(project, query, collected) -> dict
      执行「补查」：query 是补查那次调用回的 JSON（字段由 QUERY_SYS 规定），collected 是 collect 的出参。
      出参：{"text": 附到资料包后面的补查结果文本（可含增补的资料）, "log": [每项补查的记录，条数记进 v2.补查项],
             "记录": 要并进 v2.* 的字段（可空）}
  QUERY_SYS             str，补查那次调用的 system 提示；约定回复是 JSON，含 "够了": bool，其余字段由包自定、由 extra 读。
  files(project)        迭代 (相对路径, 绝对路径)：这类任务里「会被改动 / 要做快照」的文件（snap.snapshot 用它）。
  TASK_DESC, PACK_DESC  str，规划提示开头那句里的「任务」「资料包」是什么（如「改代码任务」「…数据包（…）」）。
  PLAN_RULES            str，规划提示里这类任务专属的规则行（每行以「- 」开头），插在通用规则中间。
  PLAN_RULES_END        str，同上，插在「终止」规则之后、「只输出 .zs」之前。
  plan_problems(main, body, cl, generic) -> list[str]
      计划静态检查里这类任务专属的问题；generic 是核心已查出的通用问题（如缺 预算），按包希望的顺序合并后整体返回。

以后加「文档」「数据」类资料包要实现的：上面全部名字。collect 收集文档段落 / 表结构摘要、extra 按补查要求取更多片段、
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
