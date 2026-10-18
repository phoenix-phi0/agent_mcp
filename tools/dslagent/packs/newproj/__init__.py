"""资料包 newproj（新建项目）：固定模板 newproj.zs，不走规划，也不强制 #清单。接口见 packs/__init__.py。

- EXTRA_VERBS：本包额外放开的动词 = newproj 动词包（verbs/newproj）+ 撤回 / 留底（其它包仍不放开）。
- EXTRA_PACKS：脚本里 用包 可以写的额外包名。
- TEMPLATE：固定模板路径；SPLIT_TEMPLATE：按功能分次生成的模板 newproj_split.zs（v2.run_newproj(split=True) 用，旧模板不动）；提示词正文在本目录 prompts/*.md，由 读原文 pack:xxx.md 读取。
- model_system()：模板里模型调用的专用系统提示；模型步骤键 = sub（DSLAGENT_MODELS 的 sub 管 newproj 的全部模型调用），默认 sonnet。
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
SPLIT_TEMPLATE = Path(__file__).with_name("newproj_split.zs")
EXTRA_PACKS = ("newproj",)
EXTRA_VERBS = frozenset({"读原文", "校验实体", "拆分隔块", "生成增删改查", "预编译sql", "项目摘要", "检查项目", "撤回", "留底", "校验清单", "核对规则", "校验角色"})


def model_system():
    """模板里 问 / 问JSON 的系统提示（prompts/sys_model.md）。不设的话引擎落到子任务 JSON edits 提示，与分隔块格式冲突。"""
    return (Path(__file__).with_name("prompts") / "sys_model.md").read_text(encoding="utf-8").strip()


def files(project):
    return text_files(project)


def plan_problems(main, body, cl, generic):
    """不要求 #清单；通用问题（缺 预算）照旧。"""
    return list(generic)
