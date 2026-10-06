# -*- coding: utf-8 -*-
"""Parser for entity definitions — the data model half of the DSL.

    实体 article 文章
      字段 title 文本 必填 唯一 标题
      字段 body 长文本 正文
      字段 status 枚举 draft,published,archived 必填 发布状态
    结束

    实体 answer 作答
      字段 learner 文本 必填 索引 关联 learner 学习者
      字段 correct 布尔 必填 默认 否 对错
      字段 at 文本 必填 默认 now 时间
    结束

    实体 wrong 错题本
      字段 learner 文本 必填 关联 learner
      字段 question 文本 必填
      字段 times 整数 必填 默认 1 错次
      主键 learner question
    结束

    实体 mastery 掌握
      字段 learner 文本 必填 学习者
      字段 point 文本 必填 知识点
      唯一 learner point
    结束

One entity per block. The name is the table name; the class name is derived
(article -> Article, see tools.render.to_class_name). Entities get an
implicit autoincrement `id` unless 主键 names one explicitly.

This is the single source the three template sets read from: db templates
turn entities into DDL and models, backend templates into routes, and the
UI engine takes its field table and options map from the same entities
(field_table / options_map below). Rename a field here and all three follow
— that is the whole point of the split, and the .ui file then carries no
types, no required flags and no enum options of its own.

Relations
---------
`关联 <entity>` marks a column as a foreign key to that entity's primary
key. Only the many-to-one direction is written, because that is where the
column actually lives; the reverse (one-to-many) is derivable and each
target renders it differently, so it is left to the templates.

Many-to-many is still out of scope: it needs a join table, and inventing
one implicitly would hide a table the user never wrote.

Cross-store references stay out
-------------------------------
A column pointing at something that is not a table here — a question id in
a jsonl bank, a node id in another database — must not get 关联. There is
no table to reference, and pretending otherwise turns a working schema into
one that will not build. Validate such columns in application code instead.

Naming: identifiers are English because this is ordinary Python. The block
keywords and type names stay Chinese — DSL vocabulary, same as in ui.py.
"""

from dataclasses import dataclass, field as dc_field
from typing import Optional

BLOCK = "实体"
LINE = "字段"
PK = "主键"
# 行首的「唯一 a b」是多列唯一（一组列合起来不能重复），渲染成一个唯一索引。
# 跟字段行里的旗标「唯一」同一个词，位置不同：旗标管一列，这一行管一组。
UNIQUE = "唯一"
END = "结束"

# Bare words that may follow the type
FLAGS = {"必填", "唯一", "索引"}

# Modifiers that take one value. Same shape as .ui's keyed modifiers, and
# the same limitation: the value cannot contain a space.
KEYED = {"关联", "默认"}

# Defaults that mean "let the database fill this in" rather than a literal.
# Spelled as words because a script should not have to know SQLite's
# function names — and because the same word renders differently per target.
DEFAULT_WORDS = {"now", "今天", "现在"}


class EntitySyntaxError(Exception):
    """The entity text is malformed. The message carries a line number."""

    def __init__(self, message: str, line: int = 0):
        super().__init__(message)
        self.line = line
        self.message = message

    def __str__(self):
        return f"第 {self.line} 行：{self.message}" if self.line else self.message


@dataclass
class Field:
    """One column.

    The attribute names match what tools/render.py's filters expect:
    .name .type .required .options — do not rename without changing those.
    """

    name: str
    type: str
    required: bool = False
    unique: bool = False
    indexed: bool = False
    options: list = dc_field(default_factory=list)
    # Target entity name when this column is a foreign key, else "".
    ref: str = ""
    # Literal default, or one of DEFAULT_WORDS. Empty means no default.
    default: str = ""
    label: str = ""
    line: int = 0

    @property
    def default_is_word(self) -> bool:
        """True when the default is a symbolic word, not a literal value.

        Templates need the distinction: `now` becomes a function call,
        `0` becomes the number zero, `draft` becomes a quoted string.
        """
        return self.default in DEFAULT_WORDS

    def to_dict(self) -> dict:
        return {
            "name": self.name, "type": self.type, "required": self.required,
            "unique": self.unique, "indexed": self.indexed,
            "options": list(self.options), "ref": self.ref,
            "default": self.default, "label": self.label,
        }


@dataclass
class Entity:
    """One table. `name` is the table name; the class name is derived."""

    name: str
    fields: list = dc_field(default_factory=list)
    # Explicit primary key columns. Empty means the implicit autoincrement id.
    pk: list = dc_field(default_factory=list)
    # Multi-column unique groups from 「唯一 a b」 lines, each a list of columns.
    uniques: list = dc_field(default_factory=list)
    label: str = ""
    line: int = 0

    @property
    def has_implicit_id(self) -> bool:
        return not self.pk

    @property
    def key_name(self) -> str:
        """What a foreign key should point at. Composite keys give the first
        column, which is wrong for a real composite reference — validate()
        rejects that case, so this only ever runs on single-column keys."""
        return self.pk[0] if self.pk else "id"

    def field(self, name: str) -> Optional[Field]:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def refs(self) -> list:
        """Fields that point at another entity."""
        return [f for f in self.fields if f.ref]

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "pk": list(self.pk),
            "uniques": [list(u) for u in self.uniques],
            "has_implicit_id": self.has_implicit_id,
            "fields": [f.to_dict() for f in self.fields],
        }


def _eat_modifiers(words, lineno: int):
    """Eat flags and keyed modifiers, then treat the rest as the label.

    Same shape as the .ui line format, on purpose: one parsing habit for
    both languages. A label therefore cannot start with a modifier word.
    """
    flags, keyed, i = [], {}, 0
    while i < len(words):
        w = words[i]
        if w in FLAGS:
            flags.append(w)
            i += 1
        elif w in KEYED:
            if i + 1 >= len(words):
                raise EntitySyntaxError(f"「{w}」后面要跟一个值", lineno)
            keyed[w] = words[i + 1]
            i += 2
        else:
            break
    return flags, keyed, " ".join(words[i:])


def parse(text: str) -> list:
    """Parse entity definitions. Returns a list of Entity.

    Field line:  字段 <名> <类型> [选项,逗号分隔] [旗标/键值...] [标签]
    Key line:    主键 <字段> [<字段>...]
    Unique line: 唯一 <字段> <字段> [...]    多列合起来唯一，可以写多行

    The enum options sit right after the type because they are part of it —
    an enum without options is not a usable type, and validate() says so.
    """
    from .render import TYPES          # lazy: render pulls in Jinja

    entities, current = [], None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        keyword, _, rest = line.partition(" ")
        rest = rest.strip()

        if keyword == END:
            if current is None:
                raise EntitySyntaxError("多余的「结束」", lineno)
            entities.append(current)
            current = None
            continue

        if keyword == BLOCK:
            if current is not None:
                raise EntitySyntaxError(
                    f"「实体」不能嵌套（「{current.name}」还没「结束」）", lineno)
            words = rest.split()
            if not words:
                raise EntitySyntaxError("「实体」要有名字", lineno)
            current = Entity(name=words[0], label=" ".join(words[1:]), line=lineno)
            continue

        if keyword == PK:
            if current is None:
                raise EntitySyntaxError("「主键」要写在「实体」里", lineno)
            cols = rest.split()
            if not cols:
                raise EntitySyntaxError("「主键」后面要跟字段名", lineno)
            if current.pk:
                raise EntitySyntaxError(
                    f"实体「{current.name}」已经声明过主键", lineno)
            current.pk = cols
            continue

        if keyword == UNIQUE:
            if current is None:
                raise EntitySyntaxError("「唯一」行要写在「实体」里", lineno)
            cols = rest.split()
            if len(cols) < 2:
                raise EntitySyntaxError(
                    "「唯一」行管的是一组列，至少两个字段；一列唯一写在字段行里"
                    "（字段 code 文本 必填 唯一）", lineno)
            current.uniques.append(cols)
            continue

        if keyword == LINE:
            if current is None:
                raise EntitySyntaxError("「字段」要写在「实体」里", lineno)
            words = rest.split()
            if len(words) < 2:
                raise EntitySyntaxError(
                    "「字段」要有名字和类型，比如：字段 title 文本 必填 标题", lineno)
            name, type_name = words[0], words[1]
            i = 2
            options = []
            # Options only follow an enum, and only as a comma list. Checking
            # for the comma avoids swallowing a one-word label by mistake.
            if type_name == "枚举" and i < len(words) and "," in words[i]:
                options = [o.strip() for o in words[i].replace("，", ",").split(",")
                           if o.strip()]
                i += 1
            flags, keyed, label = _eat_modifiers(words[i:], lineno)
            if type_name not in TYPES:
                raise EntitySyntaxError(
                    f"未知类型「{type_name}」，可用：{'、'.join(TYPES)}", lineno)
            current.fields.append(Field(
                name=name, type=type_name, options=options,
                required="必填" in flags, unique="唯一" in flags,
                indexed="索引" in flags,
                ref=keyed.get("关联", ""), default=keyed.get("默认", ""),
                label=label or name, line=lineno))
            continue

        raise EntitySyntaxError(
            f"不认识「{keyword}」。可用：{BLOCK}、{LINE}、{PK}、{UNIQUE}、{END}", lineno)

    if current is not None:
        raise EntitySyntaxError(f"实体「{current.name}」没有「结束」", current.line)
    return entities


def validate(entities) -> list:
    """Check the parsed entities. Returns a list of plain-language problems."""
    from .render import IDENTIFIER, TYPES

    by_name = {e.name: e for e in entities}
    problems, seen = [], set()

    for e in entities:
        if not IDENTIFIER.match(e.name or ""):
            problems.append(
                f"第 {e.line} 行：实体名「{e.name}」要是字母开头的 ASCII 标识符"
                f"（中文名请写成英文，比如「文章」写成 article）")
        if e.name in seen:
            problems.append(f"第 {e.line} 行：重复的实体名「{e.name}」")
        seen.add(e.name)
        if not e.fields:
            problems.append(f"第 {e.line} 行：实体「{e.name}」一个字段都没有")

        names = set()
        for f in e.fields:
            if not IDENTIFIER.match(f.name or ""):
                problems.append(
                    f"第 {f.line} 行：字段名「{f.name}」要是字母开头的 ASCII 标识符")
            if f.name == "id" and not e.pk:
                problems.append(
                    f"第 {f.line} 行：不用写 id，每个实体都隐式带一个自增主键"
                    f"（要自己定主键就写「主键」行）")
            if f.name in names:
                problems.append(f"第 {f.line} 行：「{e.name}」里重复的字段名「{f.name}」")
            names.add(f.name)
            if f.type == "枚举" and not f.options:
                problems.append(
                    f"第 {f.line} 行：枚举字段「{f.name}」要给选项，"
                    f"比如：字段 {f.name} 枚举 draft,published")
            if f.type != "枚举" and f.options:
                problems.append(f"第 {f.line} 行：只有枚举字段能带选项")
            if f.type not in TYPES:
                problems.append(f"第 {f.line} 行：未知类型「{f.type}」")

            if f.ref:
                target = by_name.get(f.ref)
                # A dangling reference builds a schema that will not create.
                # Say which entities exist — the usual cause is a typo or a
                # column pointing outside this file, and those need different
                # fixes.
                if target is None:
                    problems.append(
                        f"第 {f.line} 行：「{f.name} 关联 {f.ref}」指向不存在的实体。"
                        f"这里有：{'、'.join(sorted(by_name)) or '无'}。"
                        f"指向库外的东西（jsonl 题库、别的库）不要写「关联」，"
                        f"那种校验放在应用代码里")
                elif len(target.pk) > 1:
                    problems.append(
                        f"第 {f.line} 行：「{f.name}」指向的「{f.ref}」是复合主键，"
                        f"单列外键接不上。给「{f.ref}」加一个单列的唯一标识，"
                        f"或者这一列不写「关联」")
                elif f.ref == e.name and not e.pk:
                    # Self-reference is fine, but only against an explicit
                    # key — the implicit id is never written by hand.
                    problems.append(
                        f"第 {f.line} 行：「{f.name}」指向自己所在的实体，"
                        f"这需要显式主键")

            if f.default and f.type == "枚举" and f.options \
                    and f.default not in f.options:
                problems.append(
                    f"第 {f.line} 行：默认值「{f.default}」不在枚举选项里"
                    f"（{'、'.join(f.options)}）")

        for col in e.pk:
            f = e.field(col)
            if f is None:
                problems.append(
                    f"第 {e.line} 行：主键里的「{col}」不是这个实体的字段")
            elif not f.required:
                # Optional columns in a primary key are a contradiction
                # SQLite silently tolerates; say it here instead of letting
                # NULLs pile up.
                problems.append(
                    f"第 {f.line} 行：主键字段「{col}」要标「必填」")

        for cols in e.uniques:
            for col in cols:
                if e.field(col) is None and not (col == "id" and not e.pk):
                    problems.append(
                        f"第 {e.line} 行：「唯一 {' '.join(cols)}」里的「{col}」"
                        f"不是这个实体的字段")
            if len(set(cols)) != len(cols):
                problems.append(
                    f"第 {e.line} 行：「唯一 {' '.join(cols)}」里有重复的字段")

    return problems


def field_table(entities, entity_name: Optional[str] = None) -> dict:
    """Build the field table the UI engine's bind() takes.

    This is the join between the two languages: .ui names a field, this says
    what it is. Without an entity_name the tables are merged; a name defined
    differently in two entities is a conflict the caller resolves by passing
    entity_name.
    """
    table = {}
    for e in entities:
        if entity_name and e.name != entity_name:
            continue
        for f in e.fields:
            spec = {"type": f.type, "required": f.required}
            table[f.name] = spec
            # 带实体名的键给 `字段 article.title` 这种写法用。裸名会撞——
            # 两个实体都有 name 而含义不同时，合并只剩一个；写上实体名
            # 就说清楚了要哪个。两个键各用一份字典，不共享可变状态。
            table[f"{e.name}.{f.name}"] = dict(spec)
    return table


def options_map(entities, entity_name: Optional[str] = None) -> dict:
    """Enum options keyed by field name, for the UI engine's options_map."""
    out = {}
    for e in entities:
        if entity_name and e.name != entity_name:
            continue
        for f in e.fields:
            if f.type == "枚举" and f.options:
                out[f.name] = list(f.options)
                # 跟 field_table 一样给两种键：`字段 article.status` 的
                # 选项也要能按带实体名的键找到
                out[f"{e.name}.{f.name}"] = list(f.options)
    return out


def order(entities) -> list:
    """Entities sorted so that a table comes after everything it references.

    Foreign keys make creation order matter. A cycle is left in declaration
    order rather than raising: SQLite tolerates circular references when the
    tables are created in one transaction, and refusing to build would be a
    harsher rule than the database itself applies.
    """
    by_name = {e.name: e for e in entities}
    out, placed = [], set()

    def visit(e, seen):
        if e.name in placed or e.name in seen:
            return
        seen.add(e.name)
        for f in e.refs():
            target = by_name.get(f.ref)
            if target is not None and target.name != e.name:
                visit(target, seen)
        if e.name not in placed:
            placed.add(e.name)
            out.append(e)

    for e in entities:
        visit(e, set())
    return out


def dump(entities) -> str:
    """Indented text, for eyeballing what the parser produced."""
    out = []
    for e in entities:
        head = f"实体 {e.name}"
        if e.label and e.label != e.name:
            head += f" — {e.label}"
        out.append(head)
        for f in e.fields:
            bits = [f.type]
            if f.options:
                bits.append("/".join(f.options))
            for flag, on in (("必填", f.required), ("唯一", f.unique),
                             ("索引", f.indexed)):
                if on:
                    bits.append(flag)
            if f.ref:
                bits.append(f"→{f.ref}")
            if f.default:
                bits.append(f"默认={f.default}")
            tail = f" — {f.label}" if f.label and f.label != f.name else ""
            out.append(f"  {f.name}: {' '.join(bits)}{tail}")
        if e.pk:
            out.append(f"  主键: {' '.join(e.pk)}")
        for cols in e.uniques:
            out.append(f"  唯一: {' '.join(cols)}")
    return "\n".join(out)


def check(text: str) -> str:
    """Parse and validate; returns a plain-language summary."""
    try:
        entities = parse(text)
    except EntitySyntaxError as e:
        return f"语法错误：{e}"
    if not entities:
        return "没有解析到任何实体"

    problems = validate(entities)
    lines = []
    for e in entities:
        bits = [f"{len(e.fields)} 个字段"]
        if e.pk:
            bits.append(f"主键 {'+'.join(e.pk)}")
        if e.refs():
            bits.append("关联 " + "、".join(f.ref for f in e.refs()))
        lines.append(f"实体「{e.name}」：{'，'.join(bits)}")
    if problems:
        lines.append("问题：")
        lines.extend("  - " + p for p in problems)
    return "\n".join(lines)


def render_db(entities, db_name: str = "app") -> dict:
    """Render the database layer. Jinja is imported here, not at module scope.

    Entities are reordered so referenced tables are created first — the
    templates should not have to think about it.
    """
    from .render import db_renderer

    r = db_renderer()
    ordered = order(entities)
    return {
        "schema.sql": r.render("schema.sql.j2", entities=ordered),
        "models.py": r.render("models.py.j2", entities=ordered, db_name=db_name),
    }


# ----------------------------------------------------------------------
# Text-in, text-out wrappers
#
# fs.py's _CALLABLE passes arguments as JSON, so it can only hand over
# strings. render_db takes a list of Entity objects, which JSON cannot
# express — hence these. tool_call_file feeds a .entity file straight in.
#
# Errors come back as readable text rather than exceptions: this entry
# point exists for a person to look at the result, and a traceback is
# noise there.
# ----------------------------------------------------------------------


def render_sql(text: str, strict: bool = False) -> str:
    """A .entity text -> the CREATE TABLE script.

    strict=True 时语法错和校验不过都抛异常，而不是把错误文字当成 SQL
    返回。程序调用一律该用它：返回错误文字的话，调用方会把那段中文交给
    SQLite，报的是「near "语法错误：第": syntax error」——指向的位置跟
    真正的原因毫无关系，查起来绕一大圈。实际踩过。

    默认仍然返回错误文字，因为 MCP 工具那条路要把错误显示给人看。
    """
    try:
        entities = parse(text)
    except EntitySyntaxError as e:
        if strict:
            raise
        return f"语法错误：{e}"
    if not entities:
        if strict:
            raise EntitySyntaxError("没有解析到任何实体")
        return "没有解析到任何实体"

    problems = validate(entities)
    if problems:
        if strict:
            raise EntitySyntaxError("校验没过：" + "；".join(problems))
        return "校验没过，先修这些：\n" + "\n".join("  - " + p for p in problems)

    try:
        return render_db(entities)["schema.sql"]
    except Exception as e:
        # Missing Jinja filters land here. Name the file to change —
        # "UndefinedError: 转默认值" on its own points nowhere useful.
        return (f"渲染失败：{type(e).__name__}: {e}\n"
                f"如果提示某个过滤器不存在，看 _render_patch.md——"
                f"转默认值 / 主键名 这两个要加进 tools/render.py")


def render_models(text: str, db_name: str = "app") -> str:
    """A .entity text -> the SQLAlchemy models."""
    try:
        entities = parse(text)
    except EntitySyntaxError as e:
        return f"语法错误：{e}"
    problems = validate(entities)
    if problems:
        return "校验没过，先修这些：\n" + "\n".join("  - " + p for p in problems)
    try:
        return render_db(entities, db_name)["models.py"]
    except Exception as e:
        return f"渲染失败：{type(e).__name__}: {e}"
