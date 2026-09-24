# render.py 要加的两个过滤器

新模板 `templates/db/schema.sql.j2` 用了 `转默认值` 和 `主键名`，
这两个现在不存在，得加进 `tools/render.py`。

## 一、转默认值

放在 `to_sql` 旁边：

```python
# 「默认 now」这类符号词，各目标各自翻译。写成词而不是 SQL 函数名，
# 是因为脚本不该知道 SQLite 管当前时间叫什么——换 Postgres 时那个名字
# 就不一样了。
DEFAULT_SQL = {
    "now": "(datetime('now','localtime'))",
    "现在": "(datetime('now','localtime'))",
    "今天": "(date('now','localtime'))",
}


def to_default(field) -> str:
    """Field -> DEFAULT 后面那一段（不含 DEFAULT 这个词本身）。

    符号词查表，数字原样，别的都当字符串加引号。

    判断顺序要紧：先查符号词表，再试数字，最后才是字符串。反过来的话
    「默认 0」会变成 '0' —— 存进去是文本，之后 `WHERE correct = 0`
    就匹配不上了，而且不报错。
    """
    v = str(field.default)
    if v in DEFAULT_SQL:
        return DEFAULT_SQL[v]
    # 布尔字段的「是/否」也认，跟 to_text 的约定一致
    if field.type == "布尔" and v in ("是", "true", "True"):
        return "1"
    if field.type == "布尔" and v in ("否", "false", "False"):
        return "0"
    try:
        float(v)
        return v
    except ValueError:
        return "'" + v.replace("'", "''") + "'"
```

## 二、主键名

外键要指向目标表的主键列名，而那取决于目标有没有写「主键」行：

```python
def pk_name(entity_name: str, entities) -> str:
    """目标实体的主键列名。隐式主键是 id，显式的取第一列。

    复合主键的目标只取第一列，这对不上——真正的外键该是复合的。
    但复合外键的语法和单列差很多，而且指向复合主键的引用本身就少见，
    所以这里只处理单列，validate 里应该拦住复合的情况。
    """
    for e in entities:
        if e.name == entity_name:
            return e.pk[0] if e.pk else "id"
    return "id"
```

注册的时候要用 `pass_context` 或者直接传 entities——Jinja 过滤器拿不到
模板的其它变量。模板里我写成 `{{ field.ref | 主键名(entities) }}`，
所以按普通过滤器注册即可，entities 是显式传进去的参数。

## 三、注册

`db_renderer()` 里加两行：

```python
    env.filters["转默认值"] = to_default
    env.filters["主键名"] = pk_name
```

## 四、validate 要补一条

`entity.py` 的 `validate()` 里，外键指向复合主键的情况现在没拦：

```python
            if f.ref and f.ref in known:
                target = next(e2 for e2 in entities if e2.name == f.ref)
                if len(target.pk) > 1:
                    problems.append(
                        f"第 {f.line} 行：「{f.name}」指向的「{f.ref}」是复合主键，"
                        f"单列外键接不上。给「{f.ref}」加一个单列的唯一标识，"
                        f"或者这一列不写「关联」")
```

## 五、models.py.j2 也要跟

那个模板现在不知道外键、默认值、复合主键。SQLAlchemy 侧对应的是
`ForeignKey(...)`、`default=`、`primary_key=True`。

先不动它——`.entity` 眼下只用来生成建表 SQL，ORM 模型那条路还没人走。
真要用的时候再改，免得改了没人验证。
