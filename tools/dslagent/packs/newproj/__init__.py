"""资料包 newproj（新建项目）：固定模板 newproj.zs，不走规划，也不强制 #清单。接口见 packs/__init__.py。

- EXTRA_VERBS：本包额外放开的动词 = newproj 动词包（verbs/newproj）+ 撤回 / 留底（其它包仍不放开）。
- EXTRA_PACKS：脚本里 用包 可以写的额外包名。
- TEMPLATE：固定模板路径；提示词正文在本目录 prompts/*.md，由 读原文 pack:xxx.md 读取。
- files(project)：要做快照的文件 = 项目里的文本文件（同 code 包的遍历规则）。
"""
from pathlib import Path

from ..code import text_files

NAME = "newproj"
RULES_KEY = "code"           # 本包不规划；若被当规划包用，借 code 的规则文本
TASK_DESC = "新建项目：按需求文件生成一个 gen 项目（实体 → 增删改查 → 定制 sql / 接口 / 界面）"
PACK_DESC = "固定模板 newproj.zs"
PLAN_RULES = ""
PLAN_RULES_END = ""
TEMPLATE = Path(__file__).with_name("newproj.zs")
EXTRA_PACKS = ("newproj",)
EXTRA_VERBS = frozenset({"读原文", "校验实体", "拆分隔块", "生成增删改查", "预编译sql", "项目摘要", "检查项目", "撤回", "留底"})


def files(project):
    return text_files(project)


def plan_problems(main, body, cl, generic):
    """不要求 #清单；通用问题（缺 预算）照旧。"""
    return list(generic)
