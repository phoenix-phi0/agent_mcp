# -*- coding: utf-8 -*-
"""模板渲染器 —— 前端 / 后端 / 数据库三套模板的共同底座。

放置位置：tools/render.py（本文件写在 data/ 下仅供复制，data/ 不会被执行）

设计要点
--------
1. 类型映射表只有一份（TYPES），三套模板共用。字段类型是三边的契约，
   多一份副本就多一处不同步的机会。
2. 前端模板另用一套定界符。前端产物里 {{ }} 是 Vue / 模板字符串的语法，
   跟 Jinja 默认定界符冲突，所以前端渲染器用 <% %> 和 <%= %>。
3. autoescape 恒为 False。渲染的是源代码不是网页，转义会把 < & " 变成
   实体，产出的文件直接是坏的。

用法
----
    from tools.render import 后端渲染器, 前端渲染器, 数据库渲染器

    代码 = 后端渲染器.渲染("crud.py.j2", 实体=实体)
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

# --- 类型契约 -------------------------------------------------------------
# DSL 类型 -> (SQL 列类型, Python 注解, HTML 输入控件)
# 改这里等于同时改三套模板的行为，务必同步更新 tools/test_render.py。

TYPES = {
    "文本":   ("VARCHAR(255)", "str",      'input type="text"'),
    "长文本": ("TEXT",         "str",      "textarea"),
    "整数":   ("INTEGER",      "int",      'input type="number"'),
    "小数":   ("REAL",         "float",    'input type="number" step="any"'),
    "日期":   ("DATETIME",     "datetime", 'input type="date"'),
    "布尔":   ("INTEGER",      "bool",     'input type="checkbox"'),
    "枚举":   ("VARCHAR(32)",  "str",      "select"),
}

# 每个实体隐式带一个自增主键，不在 DSL 里书写。
主键列 = "id INTEGER PRIMARY KEY AUTOINCREMENT"


class 未知类型(Exception):
    """DSL 里写了 TYPES 之外的字段类型。"""


def _查(类型: str):
    if 类型 not in TYPES:
        可用 = "、".join(TYPES)
        raise 未知类型(f"未知字段类型「{类型}」，可用：{可用}")
    return TYPES[类型]


# --- filter ---------------------------------------------------------------

def 转SQL(字段) -> str:
    """字段 -> 一行 SQL 列定义（不含末尾逗号）。"""
    列类型, _, _ = _查(字段.类型)
    片段 = [字段.名, 列类型]
    if 字段.类型 == "枚举" and 字段.选项:
        值 = ", ".join(f"'{o}'" for o in 字段.选项)
        片段.append(f"CHECK ({字段.名} IN ({值}))")
    if 字段.必填:
        片段.append("NOT NULL")
    return " ".join(片段)


def 转Python(字段) -> str:
    """字段 -> SQLAlchemy 2.x 的 Mapped 注解。"""
    _, 注解, _ = _查(字段.类型)
    if not 字段.必填:
        注解 = f"Optional[{注解}]"
    return f"Mapped[{注解}]"


def 转输入框(字段) -> str:
    """字段 -> 一个 HTML 表单控件。"""
    _, _, 控件 = _查(字段.类型)
    必填 = " required" if 字段.必填 else ""
    if 控件 == "textarea":
        return f'<textarea name="{字段.名}"{必填}></textarea>'
    if 控件 == "select":
        选项 = "".join(f'<option value="{o}">{o}</option>' for o in (字段.选项 or []))
        return f'<select name="{字段.名}"{必填}>{选项}</select>'
    return f'<{控件} name="{字段.名}"{必填}>'


def 转导入(实体) -> str:
    """实体用到的 Python 类型需要哪些 import。"""
    需要 = set()
    for 字段 in 实体.字段:
        _, 注解, _ = _查(字段.类型)
        if 注解 == "datetime":
            需要.add("from datetime import datetime")
        if not 字段.必填:
            需要.add("from typing import Optional")
    return "\n".join(sorted(需要))


# --- 渲染器 ---------------------------------------------------------------

class 渲染器:
    """一套模板目录 + 一套定界符。

    定界符按 (块开, 块闭, 变量开, 变量闭) 传入。前端模板必须换掉默认的
    {{ }}，否则跟前端框架自己的插值语法互相吃掉。
    """

    def __init__(self, 模板目录, 定界符=("{%", "%}", "{{", "}}")):
        块开, 块闭, 变量开, 变量闭 = 定界符
        self.模板目录 = Path(模板目录)
        self.env = Environment(
            loader=FileSystemLoader(str(self.模板目录)),
            block_start_string=块开,
            block_end_string=块闭,
            variable_start_string=变量开,
            variable_end_string=变量闭,
            autoescape=False,        # 生成源码，绝不转义
            undefined=StrictUndefined,  # 模板里拼错变量名要立刻报错
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        self.env.filters["转SQL"] = 转SQL
        self.env.filters["转Python"] = 转Python
        self.env.filters["转输入框"] = 转输入框
        self.env.filters["转导入"] = 转导入
        self.env.globals["主键列"] = 主键列

    def 渲染(self, 模板名: str, **上下文) -> str:
        return self.env.get_template(模板名).render(**上下文)

    def 模板清单(self):
        return sorted(self.env.list_templates())


_根 = Path(__file__).resolve().parent.parent / "templates"

数据库渲染器 = 渲染器(_根 / "db")
后端渲染器 = 渲染器(_根 / "backend")
前端渲染器 = 渲染器(_根 / "frontend", 定界符=("<%", "%>", "<%=", "%>"))
