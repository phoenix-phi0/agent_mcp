# -*- coding: utf-8 -*-
"""Template rendering for the output layers: db, backend, frontend, standalone.

Design notes
------------
1. The type table (TYPES) exists once and all template sets read it. Field
   types are the contract between the layers; a second copy is a second
   thing to keep in sync.
2. Frontend templates use different delimiters. Frontend output is full of
   {{ }} — Vue interpolation, JS template literals — which collides with
   Jinja's defaults, so the frontend renderer switches to <% %> / <%= %>.
   This has a real cost: writing a frontend template and reaching for
   {% %} out of habit yields "unknown tag" rather than anything obvious.
   The standalone set keeps the default delimiters — it emits no framework
   markup, so there is nothing to collide with.
3. autoescape is always False. These templates emit source code, not web
   pages; escaping would turn < & " into entities and the output would be
   broken on arrival.
4. The renderers are lazy. Importing this module must not fail just because
   a template directory does not exist yet.

The UI type column carries a *semantic* widget name (单行, 多行, 单选...),
not an HTML tag. Each target maps those to its own controls: HTML turns
单行 into <input type="text">, Qt would turn it into QLineEdit. Putting
HTML in the shared table would weld one target into the contract.

Naming: identifiers are English because this is ordinary Python. The Jinja
filter names stay Chinese — those appear in template text, which is the
same human-facing surface as .ui and .zs.

Entity and field objects are duck-typed. An entity needs .name and .fields
(and, for keys and relations, .pk); a field needs .name, .type, .required
and .options, plus .ref and .default once it takes part in a relation.
tools/entity.py produces exactly that shape.
"""

import re
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

# --- the type contract ----------------------------------------------------
# DSL type -> (SQL column type, Python annotation, semantic widget)
# Changing a row here changes every template set at once.

TYPES = {
    "文本":   ("VARCHAR(255)", "str",      "单行"),
    "长文本": ("TEXT",         "str",      "多行"),
    "整数":   ("INTEGER",      "int",      "数字"),
    "小数":   ("REAL",         "float",    "数字"),
    "日期":   ("DATETIME",     "datetime", "日期"),
    "布尔":   ("INTEGER",      "bool",     "开关"),
    "枚举":   ("VARCHAR(32)",  "str",      "单选"),
    # 文件存的是路径不是内容——落盘由后端决定，库里只记去哪找。存 BLOB
    # 会让数据库很快变得难以备份。
    # 多文件先按逗号分隔的路径串存；真需要按文件查询时再独立成表。
    #
    # 前端这一侧文件不进 form，单独放 files（见 templates/frontend/
    # app.js.j2）：form 要能 JSON 深拷贝，而 File 对象走一遍 JSON 会变成
    # {}，静默丢失。
    "文件":   ("VARCHAR(255)", "str",      "选文件"),
    "多文件": ("TEXT",         "str",      "选多文件"),
}

# An entity gets this implicit primary key unless it declares 主键 itself.
PRIMARY_KEY = "id INTEGER PRIMARY KEY AUTOINCREMENT"

# Symbolic defaults — "let the database fill this in" rather than a literal.
# Spelled as words in the DSL because a script should not have to know what
# SQLite calls the current time, and because the same word has to render
# differently per target (SQLite here, Postgres or an ORM elsewhere).
DEFAULT_SQL = {
    "now":  "(datetime('now','localtime'))",
    "现在": "(datetime('now','localtime'))",
    "今天": "(date('now','localtime'))",
}

# Names have to work as both SQL identifiers and Python attributes, so the
# allowed set is the intersection of the two.
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class UnknownType(Exception):
    """A field declares a type that is not in TYPES."""


class InvalidName(Exception):
    """A name cannot serve as both a SQL identifier and a Python attribute."""


def _lookup(type_name: str):
    if type_name not in TYPES:
        available = "、".join(TYPES)
        raise UnknownType(f"未知字段类型「{type_name}」，可用：{available}")
    return TYPES[type_name]


def validate_name(name: str, what: str = "名字") -> str:
    """Entity and field names must be plain ASCII identifiers.

    Chinese names, hyphens and leading digits all produce Python and SQL
    that fails to parse. Better to stop at generation time than to ship a
    file that breaks when it runs.
    """
    if not IDENTIFIER.match(name or ""):
        raise InvalidName(
            f"{what}「{name}」不合法：只能用字母开头的 ASCII 字母、数字、下划线。"
            f"中文名请写成英文，比如「文章」写成 article。"
        )
    return name


# --- filters --------------------------------------------------------------
# The type filters take the whole field object rather than just its type
# string: NOT NULL, CHECK and required all depend on .required and .options,
# and passing only the type would push those conditionals into every
# template set separately.

def to_class_name(name: str) -> str:
    """Table name -> Python class name. article -> Article, blog_post -> BlogPost."""
    validate_name(name, "实体名")
    return "".join(p[:1].upper() + p[1:] for p in name.split("_") if p)


def to_sql(field) -> str:
    """Field -> one SQL column definition, without the trailing comma.

    Only type, enum check and NOT NULL. UNIQUE, DEFAULT and REFERENCES are
    appended by the template — they are per-target decisions (an ORM spells
    all three differently), and folding them in here would mean every target
    inherits SQLite's syntax.
    """
    validate_name(field.name, "字段名")
    column_type, _, _ = _lookup(field.type)
    parts = [field.name, column_type]
    if field.type == "枚举":
        if not field.options:
            raise UnknownType(f"枚举字段「{field.name}」没有给选项")
        values = ", ".join(
            "'" + str(o).replace("'", "''") + "'" for o in field.options
        )
        parts.append(f"CHECK ({field.name} IN ({values}))")
    if field.required:
        parts.append("NOT NULL")
    return " ".join(parts)


def to_default(field) -> str:
    """Field -> what goes after DEFAULT (the keyword itself is the template's).

    Order matters. Symbolic words first, then numbers, strings last. The
    other way round turns `默认 0` into '0' — stored as text, so a later
    `WHERE correct = 0` quietly matches nothing. SQLite will not complain;
    the column just behaves wrong.

    Booleans accept 是/否 so the .entity file can use the same words the
    DSL uses everywhere else for true and false.
    """
    value = str(getattr(field, "default", "") or "")
    if value in DEFAULT_SQL:
        return DEFAULT_SQL[value]
    if field.type == "布尔":
        if value in ("是", "true", "True", "1"):
            return "1"
        if value in ("否", "false", "False", "0"):
            return "0"
    try:
        float(value)
        return value
    except ValueError:
        return "'" + value.replace("'", "''") + "'"


def pk_name(entity_name: str, entities) -> str:
    """The column a foreign key should point at.

    An explicit 主键 names it; otherwise it is the implicit id. A composite
    key would need a composite foreign key, which this does not emit —
    entity.validate() rejects that case before rendering, so only the first
    column is ever taken here.

    Unknown names fall back to "id" rather than raising: the target is
    already checked upstream, and a template blowing up on a name the
    validator let through would point at the wrong file.
    """
    for entity in entities:
        if entity.name == entity_name:
            pk = getattr(entity, "pk", None) or []
            return pk[0] if pk else "id"
    return "id"


def to_python(field) -> str:
    """Field -> a SQLAlchemy 2.x Mapped annotation."""
    validate_name(field.name, "字段名")
    _, annotation, _ = _lookup(field.type)
    if not field.required:
        annotation = f"Optional[{annotation}]"
    return f"Mapped[{annotation}]"


def to_widget(field) -> str:
    """Field -> a semantic widget name (单行, 多行, 单选...).

    Deliberately not an HTML tag: each target's templates map these to their
    own controls, which keeps the shared table free of one target's markup.
    """
    validate_name(field.name, "字段名")
    _, _, widget = _lookup(field.type)
    return widget


def _imports_for(entity) -> set:
    needed = set()
    for f in entity.fields:
        _, annotation, _ = _lookup(f.type)
        if annotation == "datetime":
            needed.add("from datetime import datetime")
        if not f.required:
            needed.add("from typing import Optional")
    return needed


def to_imports(entity) -> str:
    """Imports needed by one entity's Python types."""
    return "\n".join(sorted(_imports_for(entity)))


def collect_imports(entities) -> str:
    """Imports needed by a group of entities, deduplicated and sorted.

    Deduplicating in Python rather than in the template: accumulating a list
    in Jinja needs the jinja2.ext.do extension, which is not worth enabling
    for one call site.
    """
    needed = set()
    for entity in entities:
        needed |= _imports_for(entity)
    return "\n".join(sorted(needed))


# --- renderers ------------------------------------------------------------

class Renderer:
    """One template directory plus one set of delimiters.

    Delimiters are (block_start, block_end, variable_start, variable_end).
    Frontend templates must move off the default {{ }} or they and Vue's own
    interpolation eat each other.
    """

    def __init__(self, template_dir, delimiters=("{%", "%}", "{{", "}}")):
        block_start, block_end, var_start, var_end = delimiters
        self.template_dir = Path(template_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            block_start_string=block_start,
            block_end_string=block_end,
            variable_start_string=var_start,
            variable_end_string=var_end,
            autoescape=False,           # emitting source code, never escape
            undefined=StrictUndefined,  # a typo'd name should fail loudly
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        # Filter names stay Chinese: they appear in template text.
        self.env.filters["转类名"] = to_class_name
        self.env.filters["转SQL"] = to_sql
        self.env.filters["转默认值"] = to_default
        self.env.filters["主键名"] = pk_name
        self.env.filters["转Python"] = to_python
        self.env.filters["转控件"] = to_widget
        self.env.filters["转导入"] = to_imports
        self.env.filters["汇总导入"] = collect_imports
        self.env.globals["主键列"] = PRIMARY_KEY

    def render(self, template_name: str, **context) -> str:
        return self.env.get_template(template_name).render(**context)

    def templates(self) -> list:
        return sorted(self.env.list_templates())


TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "templates"


@lru_cache(maxsize=1)
def db_renderer() -> Renderer:
    return Renderer(TEMPLATE_ROOT / "db")


@lru_cache(maxsize=1)
def backend_renderer() -> Renderer:
    return Renderer(TEMPLATE_ROOT / "backend")


@lru_cache(maxsize=1)
def frontend_renderer() -> Renderer:
    return Renderer(TEMPLATE_ROOT / "frontend", delimiters=("<%", "%>", "<%=", "%>"))


@lru_cache(maxsize=1)
def standalone_renderer() -> Renderer:
    """Self-contained HTML with no runtime: inlined CSS, no CDN, no server.

    Keeps the default {{ }} delimiters — this target emits no framework
    markup, so there is nothing to collide with. (Getting this wrong once
    cost an hour: the macros silently exported nothing because the file was
    written with <% %> while the environment expected {% %}.)
    """
    return Renderer(TEMPLATE_ROOT / "standalone")
