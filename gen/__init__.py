# -*- coding: utf-8 -*-
"""从 `.entity` 生成前后端文件。

    py -m gen                      列出有哪些实体
    py -m gen article              看会生成什么
    py -m gen article --write      写盘
    py -m gen --all --write        所有实体
    py -m gen article --check      只跑自检
    py -m gen --web                网页界面：左边写实体，右边实时看产物

一个实体出七个文件：

    queries/article_list.sql     列表
    queries/article_one.sql      按主键查一条
    queries/article_insert.sql   新建
    queries/article_update.sql   更新
    queries/article_delete.sql   删除
    routes/article.zs            五个接口，对应上面五条
    ui/article.ui                列表 + 表单 + 详情

## 生成什么在模板里，不在代码里

    gen/templates/default/*.j2

换套模板就换个形状——带搜索分页的、只读的、带审核流的，各做一套，
不用改 Python。代码只管把实体喂进去、把产物拿出来。

模板从实体里挑东西用过滤器（`gen/filters.py`）：

    {% for f in e.fields | 可写 %}       排除数据库自己填的列
    {% for f in e.fields | 上列表 %}     去长文本、截六个
    {{ f | 转占位符 }}                   整数布尔小数加 CAST

过滤器而不是预先算好的上下文：预算好等于替模板定死一半形状，而模板集
存在的意义正是「不同形状」。

## 生成是一次性的

产物写 `gen/out/`，不直接进项目——往 `routes/` 里扔文件是会立刻生效的
（`dsl_http` 下次扫描就注册了）。看过之后自己复制过去。

复制过去那一刻它就不再是生成物，是普通的手写文本。实体改了字段，已经
复制出去的东西不会跟着变。

代码生成器的老问题是「改了之后重新生成就冲掉」，解法要么生成器作废，
要么发明一套保留自定义部分的机制。两条都不好走，所以不做双向。

要跟着实体变的那部分由 `.ui` 的 `全部字段 article` 承担——那是编译时
展开的，实体加个字段界面自动多一个。

## 后端完整，前端是起点

后端五个接口生成出来就能用——它们的形状是确定的。

前端只生成最简单的那种。列表内直接编辑、可增删行的子表格、状态按钮
这些生成出来也要重写，不如只给个能跑的起点。
"""

import sys as _sys
from pathlib import Path as _Path

# 项目根加进 path，好让子模块 import 得到 tools.*。
#
# 放这儿而不是各个子模块里：包的 __init__ 在任何子模块之前跑，所以
# 不管谁先被 import 都管用。先前是 core.py 里加的，结果 web.py 直接
# import preview.py 时走不到那段，报 No module named 'tools'。
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from .core import (DEFAULT_DB, ENTITY_DIR, OUT_DIR, PARTS,  # noqa: F401,E402
                   PART_LABELS, check, generate, load, write)
from .filters import FILTERS                                # noqa: F401
from .templates_ import (DEFAULT_SET, TemplateError,        # noqa: F401
                         render, sets)

__all__ = [
    "generate", "write", "check", "load",
    "render", "sets", "TemplateError",
    "PARTS", "DEFAULT_SET", "DEFAULT_DB", "ENTITY_DIR", "OUT_DIR",
    "FILTERS",
]
