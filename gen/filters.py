# -*- coding: utf-8 -*-
"""Jinja 过滤器：模板从实体里挑东西时用。

## 为什么是过滤器不是预先算好的上下文

预先算好的话，Python 那边就替模板定死了一半形状——`写的列` 已经过滤掉
符号默认值了，某套模板想让客户端传 `created_at` 就拿不到。

而模板集存在的意义正是「不同形状」。所以这边只提供能力，挑什么由模板
自己决定：

    {% for f in e.fields | 可写 %}       排除数据库自己填的
    {% for f in e.fields | 上列表 %}     去长文本、截六个
    {% for f in e.fields %}              全都要

跟 `templates/db/` 那套一致（那边是 `转SQL`、`转默认值`、`主键名`），
两处用同一种风格。

## 名字用中文

过滤器出现在模板正文里，而模板正文是中文 DSL（`.zs` 和 `.ui`）。
`{{ f | 转参数 }}` 混在中文里比 `{{ f | to_param }}` 顺眼，也跟
`render.py` 的做法一致。
"""


# ----------------------------------------------------------------------
# 实体级
# ----------------------------------------------------------------------


def 主键(entity) -> str:
    """主键列名。没写「主键」行就是隐式的自增 id。"""
    pk = getattr(entity, "pk", None) or []
    return pk[0] if pk else "id"


def 主键自增(entity) -> bool:
    """主键是不是隐式的自增 id。

    这个区别决定了一串行为：自增主键不在 `.entity` 里、不进 INSERT、
    表单里没有它，所以更新和删除要从别处（state）取。
    """
    return not (getattr(entity, "pk", None) or [])


def 标签(entity) -> str:
    return entity.label or entity.name


# ----------------------------------------------------------------------
# 字段筛选
# ----------------------------------------------------------------------


def 数据库填(f) -> bool:
    """这一列该不该交给数据库自己填。

    判据是「默认值是符号词」——`默认 now` 在 schema 里渲染成
    `DEFAULT (datetime(...))`，值是写入那一刻才定的。表单里没有这一列，
    硬传个空串反而把默认值覆盖掉。

    字面量默认（`默认 0`）不算：那种字段表单里通常是有的，用户改了就该
    按用户的来。
    """
    return bool(getattr(f, "default_is_word", False))


def 可写(fields) -> list:
    """INSERT / UPDATE 要写的列。

    隐式自增主键本来就不在 fields 里，不用管。

    **显式主键不排除**——它是普通字段，新建时必须给值，排掉的话插进去
    主键是 NULL。第一版这里的逻辑正好写反了，是实测才发现的。
    """
    return [f for f in fields if not 数据库填(f)]


def 系统字段(fields) -> list:
    """带「系统」旗标的列：值由系统定，客户端不写、表单里不出现。"""
    return [f for f in fields if getattr(f, "system", False)]


def 客户端写(fields) -> list:
    """INSERT / UPDATE 里客户端能写的列：可写，再去掉「系统」字段。

    新建时系统字段不进 INSERT，由表里的 DEFAULT 填；修改时不进 SET。
    查询单条（one）仍用「可写」，系统字段要照常返回。
    """
    return [f for f in 可写(fields) if not getattr(f, "system", False)]


def 上列表(fields) -> list:
    """列表显示哪几列。

    去掉长文本（一行正文顶十行高），最多六列（再多横向就爆了）。
    列表本来就该只给摘要，要看全的点进详情。
    """
    return [f for f in fields if f.type != "长文本"][:6]


def 上表格(fields) -> list:
    """界面的列表里显示哪几列。比 SQL 少两列。

    SQL 多取两列不费什么，界面上多两列就挤了。
    """
    return [f for f in fields if f.type != "长文本"][:4]


def 除去(fields, 名字) -> list:
    """去掉某个名字的列。给「SET 里不能有主键」这类用。

        {% for f in e.fields | 可写 | 除去(主键) %}
    """
    return [f for f in fields if f.name != 名字]


# ----------------------------------------------------------------------
# 字段渲染
# ----------------------------------------------------------------------


def 转占位符(f) -> str:
    """字段在 SQL 里的参数写法。

    整数、布尔、小数要 CAST——db 包的参数一律是字符串，而 SQLite 在
    表达式两侧比较时不自动转，文本永远大于数字，结果恒假**而且不报错**。

    在每条查询里写清楚，而不是在动词里搞一条影响所有查询的隐式规则：
    「什么算数字」永远有边界（`007` 转成 `7` 就匹配不上文本编号列）。

    非必填的列还要把空串转成 NULL：表单里没填的字段发过来是空串，而空串
    不是 NULL——外键会拿它去找 `code = ''` 的记录，找不到就报「关联的记录
    不存在」，于是「知识点先留空」这种再正常不过的事做不了。实测撞上过。
    必填的列不转：那种列本来就不该收到空串，转成 NULL 只会把「漏填了」
    变成一句更难懂的报错。
    """
    if f.type in ("整数", "布尔"):
        return f"CAST(NULLIF(:{f.name}, '') AS INTEGER)" if not f.required \
            else f"CAST(:{f.name} AS INTEGER)"
    if f.type == "小数":
        return f"CAST(NULLIF(:{f.name}, '') AS REAL)" if not f.required \
            else f"CAST(:{f.name} AS REAL)"
    return f":{f.name}" if f.required else f"NULLIF(:{f.name}, '')"


def 转赋值(f) -> str:
    """UPDATE 的 SET 里一行：`title = :title`。"""
    return f"{f.name} = {转占位符(f)}"


def 转动词参数(f) -> str:
    """动词调用里的一个参数：`title={title}`。"""
    return f"{f.name}={{{f.name}}}"


def 列名(fields) -> str:
    """逗号分隔的列名，SELECT 和 INSERT 的列清单用。"""
    return ", ".join(f.name for f in fields)


def 标题(f) -> str:
    """字段的显示名。没写标签就用字段名。"""
    return f.label or f.name


FILTERS = {
    "主键": 主键,
    "主键自增": 主键自增,
    "标签": 标签,
    "可写": 可写,
    "系统字段": 系统字段,
    "客户端写": 客户端写,
    "上列表": 上列表,
    "上表格": 上表格,
    "除去": 除去,
    "转占位符": 转占位符,
    "转赋值": 转赋值,
    "转动词参数": 转动词参数,
    "列名": 列名,
    "标题": 标题,
    "数据库填": 数据库填,
}
