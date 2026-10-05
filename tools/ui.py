# -*- coding: utf-8 -*-
"""UI engine: parse .ui text, bind field metadata, emit code via pluggable backends.

Pipeline
--------
    .ui text --parse--> widget tree --bind--> typed tree --backend--> files

parse() only does syntax. Binding and validating are separate steps so the
same tree can be checked against different field tables, and so callers that
only want the tree (see the ir backend) never pay for the rest.

Backends live in BACKENDS; add one with register_backend(). Only the vue and
standalone backends touch Jinja, and they import tools.render lazily inside
the function — a module-level import would force every caller, including ir
and text, to drag in the whole template system. That is not hypothetical:
when templates/frontend/ was missing, text and ir kept working and only vue
raised TemplateNotFound, which is how the missing directory got diagnosed in
one step.

Scope: compute per screen, and per container where a screen is not enough
-------------------------------------------------------------------------
This file has produced the same class of bug three times: compute one value
at too wide a scope, use it everywhere below, and it silently targets the
wrong thing. Once globally (drill screen's Enter fired the chat screen's
send), once again globally (drill's placeholder went into the chat stream
and never cleared, leaving the drill screen blank), and once per screen when
per container was needed (inside the drill overlay, Enter fired the top
bar's "start drill" — throwing away the question being answered).

Every one of them was invisible: no error, just the wrong thing happening.
_tag_submit_action now walks containers and inherits downward;
_screen_streams keys by screen name. When adding another "which one does
this node use" value, pick the narrowest scope that can answer it.

Vocabulary
----------
Modifiers carry layout intent AND size. The earlier rule was "intent only,
no parameters" — on the grounds that 200px means nothing to a character
terminal. That reasoning does not hold: Qt's setFixedWidth and Flutter's
SizedBox are pixels too, so pixels are near-universal across real GUI
toolkits; the one exception was a hypothetical target that was never going
to be built. Meanwhile the parameters did not disappear when kept out —
they just moved into style.css.j2, where changing a width means editing a
Jinja file instead of the .ui everyone can read.

Field types are not written in .ui. The data model declares them once (see
tools/entity.py); repeating them here would let the two drift. Pass a field
table to bind().

Naming: identifiers are English because this is ordinary Python. The *values*
of Node.kind and the keywords below stay Chinese — those are DSL vocabulary,
not identifiers, and translating them would just add a lookup step.
"""

from dataclasses import dataclass, field
from typing import Optional


# --- diagnostics ----------------------------------------------------------

class Issue:
    """A non-fatal problem found while binding or validating.

    Syntax errors raise; everything else accumulates as Issues so one bad
    field does not hide the other twenty. The `code` is what lets a caller
    grade them — build.py blocks on some and only prints the rest. Treating
    every Issue as fatal once made a harmless note stop the whole build.
    """

    __slots__ = ("line", "code", "message")

    def __init__(self, message: str, line: int = 0, code: str = "error"):
        self.line = line
        self.code = code
        self.message = message

    def __str__(self):
        if self.line:
            return f"第 {self.line} 行：{self.message}"
        return self.message

    def to_dict(self):
        return {"line": self.line, "code": self.code, "message": self.message}


class UiSyntaxError(Exception):
    """The .ui text is malformed.

    Named UiSyntaxError rather than SyntaxError so it cannot be confused
    with, or accidentally renamed into, the builtin.
    """

    def __init__(self, message: str, line: int = 0, code: str = "syntax"):
        super().__init__(message)
        self.issue = Issue(message, line=line, code=code)

    def __str__(self):
        return str(self.issue)


# --- tree -----------------------------------------------------------------

@dataclass
class Node:
    """One node of the widget tree.

    kind:      界面 布局 区域 分组 列表 浮层 字段 列 动作 文案 消息流 显示
    label:     human-facing text, may contain spaces
    type:      fields and columns only, attached by bind()
    widget:    overrides the widget the type would imply (控件 <name>)
    bind:      data path this node reads/writes (绑 <path>); defaults to name
    when:      visibility condition, passed to the target verbatim (当 <expr>)
    hint:      placeholder text (提示 <text>), NOT the label above the box
    goto:      actions only (切到 <screen>): switch screens locally, no request
    opens:     actions only (打开 <overlay>): pop an overlay, local
    accept:    file fields only (接受 image/*): the picker's filter
    maxsize:   file fields only (最大 5MB): checked on pick
    role:      screens only: 表单 / 列表 / 自定义
    ratio:     「比 n」share among siblings; 0 means not participating
    cols:      「列数 n」grid column count
    size:      宽/高/间距/对齐/内边距, values handed to the target as written
    clears:    filled by the engine for 「清空」/「回显」 actions: which paths
    modifiers: layout intent, kept verbatim for backends to interpret
    """

    kind: str
    name: str = ""
    label: str = ""
    type: Optional[str] = None
    widget: Optional[str] = None
    bind: Optional[str] = None
    when: Optional[str] = None
    hint: str = ""
    goto: str = ""
    opens: str = ""
    accept: str = ""             # 「接受 image/*」：文件选择器的过滤。注意它
                                 # 只是选择器的筛选，不是校验——用户能在选择
                                 # 框里切成「所有文件」照选，把关必须在后端做。
    maxsize: str = ""            # 「最大 5MB」：选完就查，省得传上去才被拒
    carry: str = ""              # 列表行上的动作「带 id」：跳过去时把这一行的
                                 # id 放进地址（#笔记列表?浮层=笔记&id=5）。
                                 # 刷新、把地址发给别人，都还知道是哪一条。
    load: str = ""               # 界面或浮层上的「载入 note_open」：带着地址
                                 # 参数进来、表单里又不是那一条时，调这个接口
                                 # 把记录拉回来
    selects: str = ""            # 「选中 sel」：点中的图节点写进这个共享路径
    to: str = ""                 # 「选项」的「交给 quiz_answer」：点了哪个选项就
                                 # 把它写进同名表单字段，然后提交这个动作
    flip: str = ""               # 卡片的「翻页 card.code」：这个共享值一变，卡片
                                 # 重建、播一次翻入动画（不用「带」：那个词是给
                                 # 跳转带参数的，用在这里会被当成写漏了「切到」）
    direction: str = ""          # 「方向 纵向/横向」：图的 dagre rankdir
    popup: str = ""              # 「点开 节点详情」：点中节点时弹出的浮层
    around: str = ""             # 节点图「围绕 sel」
    title_f: str = ""            # 节点图「标题 kanji,kana」
    sub_f: str = ""              # 节点图「说明 kana,meaning」
    required: Optional[bool] = None
    role: Optional[str] = None
    ratio: int = 0
    cols: int = 0
    size: dict = field(default_factory=dict)
    clears: list = field(default_factory=list)
    submit_action: str = ""      # 在这里按 Enter 触发的动作，渲染前由引擎填
    modifiers: list = field(default_factory=list)
    children: list = field(default_factory=list)
    line: int = 0

    def has(self, word: str) -> bool:
        """For templates: {% if node.has('横排') %}"""
        return word in self.modifiers

    def of_kind(self, kind: str) -> list:
        return [n for n in self.children if n.kind == kind]

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def fields(self) -> list:
        """Every 字段 / 列 below this node, at any depth.

        Depth matters: 分组 may sit inside 区域 or directly under 界面, so
        scanning direct children is not enough. Overlay fields are included —
        they share the screen's form state.
        """
        return [n for n in self.walk() if n.kind in ("字段", "列")]

    def actions(self) -> list:
        return [n for n in self.walk() if n.kind == "动作"]

    def streams(self) -> list:
        return [n for n in self.walk() if n.kind == "消息流"]

    def overlays(self) -> list:
        """本界面的浮层。浮层不参与正常布局，模板单独渲染在最后。"""
        return [n for n in self.children if n.kind == "浮层"]

    def body(self) -> list:
        """除浮层之外的直接子节点——也就是界面本体。"""
        return [n for n in self.children if n.kind != "浮层"]

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "name": self.name, "label": self.label,
            "type": self.type, "widget": self.widget, "bind": self.bind,
            "when": self.when, "hint": self.hint, "goto": self.goto,
            "opens": self.opens, "accept": self.accept, "maxsize": self.maxsize,
            "required": self.required, "role": self.role,
            "ratio": self.ratio, "cols": self.cols, "size": dict(self.size),
            "clears": list(self.clears),
            "modifiers": list(self.modifiers), "line": self.line,
            "children": [c.to_dict() for c in self.children],
        }


# --- grammar --------------------------------------------------------------

# block keyword -> what may appear directly inside it.
# 分组 is allowed both inside 区域 and directly under 界面: a screen with no
# region-level layout should not have to wrap everything in an empty region.
# 浮层 takes the same children as 区域 — a modal may hold anything a panel
# can, from one line of text to a full form.
BLOCK_RULES = {
    "界面": {"布局", "分组", "列表", "文案", "动作", "浮层"},
    "布局": {"区域"},
    "区域": {"分组", "列表", "布局", "文案", "动作"},
    "分组": {"字段", "动作", "文案", "布局"},
    "列表": {"列", "动作", "文案"},
    "浮层": {"布局", "分组", "列表", "文案", "动作"},
}

LINE_KEYWORDS = {"字段", "列", "动作", "文案", "消息流", "显示", "全部字段", "图"}

# line keyword -> the blocks it may appear in
LINE_PARENT = {
    "字段": {"分组", "浮层"},
    "全部字段": {"分组", "浮层"},
    "列": {"列表"},
    "动作": {"界面", "区域", "分组", "列表", "浮层"},
    "文案": {"界面", "区域", "分组", "列表", "浮层"},
    "消息流": {"界面", "区域", "分组", "浮层"},
    "显示": {"界面", "区域", "分组", "浮层"},
    "图": {"界面", "区域", "分组", "浮层"},
}

# Bare words that toggle something on the node they follow.
# 「节点图」：有向无环图（Vue Flow + dagre）。不叫「图」——「图」是静态图片。
LINE_KEYWORDS = LINE_KEYWORDS | {"节点图"}
LINE_PARENT["节点图"] = {"界面", "区域", "分组", "浮层"}

# 「选项」：一组大按钮，内容从共享状态里来（绑 card.options，每项 {key, text,
# state}），点一个就把它的 key 写进同名表单字段、提交「交给」的那个动作。
#   选项 choice 绑 card.options 交给 quiz_answer
# 跟「控件 单选」的区别：单选的选项是编译时从实体枚举里取的、只有值没有说明，
# 还得另点一个提交按钮；做题这种「选项每道题都不一样、点了就交」的场合用这个。
# state 由后端给（right / wrong / pick / dim），有值的按钮不能再点——判完了。
LINE_KEYWORDS = LINE_KEYWORDS | {"选项"}
LINE_PARENT["选项"] = {"界面", "区域", "分组", "浮层"}

FLAG_MODIFIERS = {
    "竖排", "横排", "网格", "占满",   # layout intent
    "必填",                          # field
    "提交", "次要", "危险",           # action styling
    "顶栏", "底栏",                   # pinned to top/bottom; the middle scrolls
    "单行高",                        # textarea starts one row tall, grow() extends it
    "共享",                          # field lives in cross-screen state
    "回显",                          # action: echo the input into the stream
                                     # BEFORE the request goes out
    "关闭",                          # action: close the overlay it sits in;
                                     # combines with 远程 (request, then close)
    "清空",                          # action: reset its own container's fields
    "重置",                          # 打开 action: reset the whole screen form
                                     # before popping the overlay. The "new"
                                     # button needs it: after editing a row in
                                     # the same overlay, that row's values are
                                     # still in the form.
    "进入时",                        # action: fire once each time its screen is
                                     # entered (first load, 切到, back/forward).
                                     # 列表页靠它打开就有数据，不用先点刷新。
    "远程",                          # action fires a request; the address is
                                     # the caller's business, not the .ui's
}

# Size values are handed to the target verbatim; the engine neither
# interprets nor validates units. 200px / 50% / 12rem / auto — whether a
# unit is understood is the target's business, and screening here would
# only tie .ui to one target's unit table.
#
# Every key here MUST also be in KEYED_MODIFIERS below, or _eat_modifiers
# never recognises it and the word silently ends up inside a block name.
# Adding 内边距 to only one of the two cost a debugging round, which is why
# KEYED_MODIFIERS is built as a union rather than written out twice.
SIZE_KEYS = {"宽": "width", "高": "height", "间距": "gap",
             "对齐": "align", "内边距": "padding"}

# Words that take an argument.
# 「比」hangs on the child, not the container (not 「布局 横排 比例 1:3」):
# the share travels with the node, so adding, removing or reordering
# children never shifts it, and the container need not know its child count.
#
# A keyed modifier eats the next word, so the label has to come after it:
#   动作 del 危险 打开 确认删除 删除
#   动作 next 提交 远程 当 shared.verdict 下一题
#   字段 avatar 接受 image/* 最大 2MB 头像
# writing the label first leaves the whole 「当 ...」 inside the label: the
# button reads 「下一题 当 shared.verdict」 and no v-if is emitted at all.
KEYED_MODIFIERS = ({"绑", "控件", "当", "比", "列数", "提示", "切到", "打开",
                    "接受", "最大", "选中", "方向", "带", "载入"}
                   | set(SIZE_KEYS))

# Screen roles. Written before or after the screen name:
#   界面 表单 文章编辑      /      界面 文章编辑 表单
# Kept out of FLAG_MODIFIERS on purpose: 表单 and 列表 would otherwise be
# both a role and a modifier, and 列表 is a block keyword on top of that.
# 节点图「点开 <浮层>」：点中节点就直接弹出这个浮层，一步看详情。
KEYED_MODIFIERS = KEYED_MODIFIERS | {"点开"}

# 节点图「图例」：图下面那行「实心带勾=已掌握　亮边=可学……」。浮层里的小图用不着。
FLAG_MODIFIERS = FLAG_MODIFIERS | {"图例"}

# 节点图：「围绕 sel」只画选中点和它的直接前置、直接后续（详情里的邻域图）；
# 「标题 字段」「说明 字段」指定卡片拿哪个字段当名字和说明行，可写几个、逗号隔开，
# 取第一个有值的——条目、词这些数据没有 label/sub 字段也能画成卡片。
KEYED_MODIFIERS = KEYED_MODIFIERS | {"围绕", "标题", "说明"}

# 动作「隐藏」：不画按钮，别的照旧——配「进入时」就是进页面自动拉数据、
# 却不在界面上摆一个没人点的「刷新」。
FLAG_MODIFIERS = FLAG_MODIFIERS | {"隐藏"}

# 「卡片」：分组画成居中的一张卡（做题的题卡）。配「翻页 <共享路径>」时那个
# 值一变卡片就整个重建、播一次翻入动画——换题时看得出是新的一张。
# 「正文」：「显示」按正文排（大字、保留换行），不是顶栏那种小号灰字。
FLAG_MODIFIERS = FLAG_MODIFIERS | {"卡片", "正文"}
KEYED_MODIFIERS = KEYED_MODIFIERS | {"交给", "翻页"}

SCREEN_ROLES = {"表单", "列表", "自定义"}
DEFAULT_ROLE = "自定义"

UNNAMED_BLOCKS = {"布局"}     # take modifiers, no name
NAMELESS_LINES = {"文案"}     # take a label, no name


def _eat_modifiers(words, start: int):
    """Consume flags and keyed modifiers from words[start:].

    Returns (flags, keyed, index_of_first_leftover_word). Stops at the first
    word that is neither — everything from there on is name or label text.
    A keyed value is a single word, so it cannot contain spaces.
    """
    flags, keyed, i = [], {}, start
    while i < len(words):
        w = words[i]
        if w in KEYED_MODIFIERS:
            if i + 1 >= len(words):
                break
            keyed[w] = words[i + 1]
            i += 2
            continue
        if w in FLAG_MODIFIERS:
            flags.append(w)
            i += 1
            continue
        break
    return flags, keyed, i


def _parse_tail(rest: str, roles: bool = False):
    """Split '<name> <modifiers...> <text>' into its parts.

    Modifiers are eaten between the name and the text, so a label may contain
    spaces without quoting — the whitespace-splitting trap from .zs need not
    repeat here. The cost is that a label cannot begin with a modifier word:
    「动作 submit 提交 远程 提交」 eats the trailing 提交 as a flag and the
    label ends up empty, falling back to the name.

    roles=True additionally accepts a screen role, before or after the name.
    """
    words = rest.split()
    if not words:
        return "", [], {}, "", None

    i = 0
    role = None
    # Check the LEADING position first. Taking words[0] as the name
    # unconditionally makes a leading role word become the name, and
    # _join_name then appends the real name to it: 「界面 表单 文章编辑」
    # parsed as name="表单 文章编辑" with role=自定义, so every downstream
    # role lookup silently missed — and dump() output looked perfectly fine.
    if roles and words[i] in SCREEN_ROLES:
        role = words[i]
        i += 1

    if i >= len(words):
        return "", [], {}, "", role

    name = words[i]
    i += 1

    if roles and role is None and i < len(words) and words[i] in SCREEN_ROLES:
        role = words[i]
        i += 1

    flags, keyed, i = _eat_modifiers(words, i)

    if roles and role is None and i < len(words) and words[i] in SCREEN_ROLES:
        role = words[i]
        i += 1
        more_flags, more_keyed, i = _eat_modifiers(words, i)
        flags += more_flags
        keyed.update(more_keyed)

    return name, flags, keyed, " ".join(words[i:]), role


def _parse_unnamed(rest: str):
    """Split '<modifiers...> <text>' for blocks and lines that take no name."""
    words = rest.split()
    flags, keyed, i = _eat_modifiers(words, 0)
    return flags, keyed, " ".join(words[i:])


def _apply_keyed(node: Node, keyed: dict):
    if "围绕" in keyed:
        node.around = keyed["围绕"]
    if "标题" in keyed:
        node.title_f = keyed["标题"]
    if "说明" in keyed:
        node.sub_f = keyed["说明"]
    if "交给" in keyed:
        node.to = keyed["交给"]
    if "翻页" in keyed:
        node.flip = keyed["翻页"]
    if "点开" in keyed:
        node.popup = keyed["点开"]
    if "绑" in keyed:
        node.bind = keyed["绑"]
    if "控件" in keyed:
        node.widget = keyed["控件"]
    if "当" in keyed:
        node.when = keyed["当"]
    if "提示" in keyed:
        node.hint = keyed["提示"]
    if "切到" in keyed:
        node.goto = keyed["切到"]
    if "打开" in keyed:
        node.opens = keyed["打开"]
    if "接受" in keyed:
        node.accept = keyed["接受"]
    if "最大" in keyed:
        node.maxsize = keyed["最大"]
    if "带" in keyed:
        node.carry = keyed["带"]
    if "载入" in keyed:
        node.load = keyed["载入"]
    if "选中" in keyed:
        node.selects = keyed["选中"]
    if "方向" in keyed:
        node.direction = keyed["方向"]
    for key, css in SIZE_KEYS.items():
        if key in keyed:
            # 修饰值不能含空格（整行按空格切分），而 padding 这类 CSS 简写
            # 偏偏要空格分隔。约定用逗号写，这里换回空格：
            #   内边距 14px,20px  →  padding:14px 20px
            node.size[css] = keyed[key].replace(",", " ")
    for key, attr in (("比", "ratio"), ("列数", "cols")):
        if key in keyed:
            try:
                n = int(keyed[key])
            except ValueError:
                n = 0            # 写了非数字就当没写，不值得为此中断解析
            setattr(node, attr, max(n, 0))


def _join_name(name: str, leftover: str, keyword: str, lineno: int) -> str:
    """Block and screen names may contain spaces, so trailing words join the name.

    This is why a misspelled modifier is dangerous here: 「分组 发布设置 網格」
    silently yields the name 「发布设置 網格」 rather than an error. Modifier
    words are checked against the known sets, so only *misspellings* slip
    through — the same class of trap as .zs silently passing through unknown
    verbs. Eyeball dump() output for stray words.
    """
    if not leftover:
        return name
    return (name + " " + leftover).strip()


def parse(text: str, types=None) -> list:
    """Parse .ui text into a list of top-level 界面 nodes.

    types is a convenience shortcut for bind(): a plain {name: type} map.
    Prefer calling bind() explicitly with a full field table.
    """
    types = types or {}
    roots, stack = [], []

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        keyword, _, rest = line.partition(" ")
        rest = rest.strip()

        if keyword == "结束":
            if not stack:
                raise UiSyntaxError("多余的「结束」", line=lineno)
            stack.pop()
            continue

        # --- blocks ---
        if keyword in BLOCK_RULES:
            if keyword == "界面":
                if stack:
                    raise UiSyntaxError("「界面」不能嵌套在别的块里", line=lineno)
                name, flags, keyed, leftover, role = _parse_tail(rest, roles=True)
                name = _join_name(name, leftover, keyword, lineno)
                if not name:
                    raise UiSyntaxError("「界面」要有名字", line=lineno)
                node = Node(kind="界面", name=name, modifiers=flags,
                            role=role or DEFAULT_ROLE, line=lineno)
                _apply_keyed(node, keyed)
                roots.append(node)
                stack.append(node)
                continue

            if not stack:
                raise UiSyntaxError(f"「{keyword}」要写在「界面」里", line=lineno)
            parent = stack[-1]
            allowed = BLOCK_RULES.get(parent.kind, set())
            if keyword not in allowed:
                raise UiSyntaxError(
                    f"「{keyword}」不能直接放在「{parent.kind}」里，"
                    f"这里只能放：{'、'.join(sorted(allowed)) or '(无)'}", line=lineno)

            if keyword in UNNAMED_BLOCKS:
                flags, keyed, leftover = _parse_unnamed(rest)
                if leftover:
                    raise UiSyntaxError(
                        f"「{keyword}」只收修饰词，不收名字（多出「{leftover}」）",
                        line=lineno)
                node = Node(kind=keyword, modifiers=flags, line=lineno)
            else:
                name, flags, keyed, leftover, _ = _parse_tail(rest)
                name = _join_name(name, leftover, keyword, lineno)
                if not name:
                    raise UiSyntaxError(f"「{keyword}」要有名字", line=lineno)
                node = Node(kind=keyword, name=name, modifiers=flags, line=lineno)
            _apply_keyed(node, keyed)
            parent.children.append(node)
            stack.append(node)
            continue

        # --- lines ---
        if keyword in LINE_KEYWORDS:
            if not stack:
                raise UiSyntaxError(f"「{keyword}」要写在块里", line=lineno)
            parent = stack[-1]
            expected = LINE_PARENT[keyword]
            if parent.kind not in expected:
                raise UiSyntaxError(
                    f"「{keyword}」只能写在{' / '.join(sorted(expected))}里，"
                    f"当前在「{parent.kind}」里", line=lineno)

            if keyword in NAMELESS_LINES:
                flags, keyed, label = _parse_unnamed(rest)
                node = Node(kind=keyword, label=label, modifiers=flags, line=lineno)
            else:
                name, flags, keyed, label, _ = _parse_tail(rest)
                if not name:
                    raise UiSyntaxError(f"「{keyword}」要有名字", line=lineno)
                node = Node(kind=keyword, name=name, label=label or name,
                            type=types.get(name), modifiers=flags,
                            required=("必填" in flags) or None, line=lineno)
            _apply_keyed(node, keyed)
            parent.children.append(node)
            continue

        known = "、".join(sorted(set(BLOCK_RULES) | {"结束"} | LINE_KEYWORDS))
        raise UiSyntaxError(f"不认识「{keyword}」。可用：{known}", line=lineno)

    if stack:
        unclosed = "、".join(f"{n.kind}(第 {n.line} 行)" for n in stack)
        raise UiSyntaxError(f"有块没有「结束」：{unclosed}", line=stack[0].line)

    return roots


def dump(nodes, indent: int = 0) -> str:
    """Draw the tree as indented text. Also the text backend's whole output.

    Worth eyeballing after edits: a misspelled modifier lands in the label
    or the name instead of the [] brackets, which is the one failure mode
    the parser cannot catch. A label reading 「回显 清空 发送」 means those
    two flags are not in FLAG_MODIFIERS on this build.
    """
    out = []
    for n in nodes:
        extras = []
        if n.role:
            extras.append(f"角色={n.role}")
        if n.bind:
            extras.append(f"绑={n.bind}")
        if n.widget:
            extras.append(f"控件={n.widget}")
        if n.when:
            extras.append(f"当={n.when}")
        if n.hint:
            extras.append(f"提示={n.hint}")
        if n.goto:
            extras.append(f"切到={n.goto}")
        if n.opens:
            extras.append(f"打开={n.opens}")
        if n.accept:
            extras.append(f"接受={n.accept}")
        if n.maxsize:
            extras.append(f"最大={n.maxsize}")
        if n.type:
            extras.append(f"类型={n.type}")
        if n.ratio:
            extras.append(f"比={n.ratio}")
        if n.cols:
            extras.append(f"列数={n.cols}")
        for k, v in n.size.items():
            extras.append(f"{k}={v}")
        if n.required is True:
            extras.append("必填")
        mods = f" [{' '.join(n.modifiers)}]" if n.modifiers else ""
        extra = f" {{{' '.join(extras)}}}" if extras else ""
        label = f" — {n.label}" if n.label and n.label != n.name else ""
        out.append("  " * indent + f"{n.kind} {n.name}{mods}{extra}{label}")
        if n.children:
            out.append(dump(n.children, indent + 1))
    return "\n".join(out)


# --- binding and validation -----------------------------------------------

def bind(screens, fields: dict) -> list:
    """Attach field metadata from a field table. Returns a list of Issues.

    fields maps a field name to either a bare type string ("文本") or a dict
    ({"type": "文本", "required": True, "widget": "多行", "bind": "a.b"}).
    Values already set on the node win — an explicit 控件 in the .ui text is
    a deliberate override and should not be clobbered by the table.
    """
    issues = []
    for screen in screens:
        for node in screen.fields():
            spec = fields.get(node.name)
            if spec is None:
                issues.append(Issue(f"字段「{node.name}」不在字段表里",
                                    line=node.line, code="unknown_field"))
                continue
            if isinstance(spec, str):
                spec = {"type": spec}
            node.type = spec.get("type", node.type)
            if "widget" in spec and not node.widget:
                node.widget = spec.get("widget")
            if "bind" in spec and not node.bind:
                node.bind = spec.get("bind")
            if "required" in spec:
                mapped = bool(spec["required"])
                if node.required is True and mapped is False:
                    issues.append(Issue(
                        f"字段「{node.name}」在界面上标了必填，字段表里不是",
                        line=node.line, code="required_conflict"))
                node.required = mapped
            elif node.has("必填"):
                node.required = True
            if not node.bind:
                node.bind = node.name
    return issues


def validate(screens, require_bind: bool = False, endpoints=None) -> list:
    """Check the bound tree. Returns a list of Issues; never raises."""
    issues, seen = [], set()
    for screen in screens:
        if screen.kind != "界面":
            issues.append(Issue(f"顶层不是界面：{screen.kind}", code="not_screen"))
            continue
        if screen.name in seen:
            issues.append(Issue(f"重复的界面名「{screen.name}」",
                                line=screen.line, code="dup_screen"))
        seen.add(screen.name)
        for node in screen.fields():
            if require_bind and node.type is None:
                issues.append(Issue(f"字段「{node.name}」没有类型",
                                    line=node.line, code="untyped"))
        for node in screen.walk():
            if node.when is not None and not str(node.when).strip():
                issues.append(Issue("「当」后面是空的",
                                    line=node.line, code="empty_when"))

    # 「切到」指向的界面要存在。写错了不会报错，只是点下去没反应——
    # 跟未知动词静默透传同一类，所以在这里拦一道。
    names = {s.name for s in screens if s.kind == "界面"}
    for screen in screens:
        for a in screen.actions():
            if a.goto and a.goto not in names:
                issues.append(Issue(
                    f"动作「{a.name}」要切到「{a.goto}」，但没有这个界面",
                    line=a.line, code="unknown_screen"))

    # 「打开」指向的浮层要在同一个界面里。浮层是界面的一部分，跨界面弹
    # 别人的浮层没有意义——真要那样，该把它做成一个界面。
    for screen in screens:
        names_here = {o.name for o in screen.overlays()}
        for a in screen.actions():
            if a.opens and a.opens not in names_here:
                issues.append(Issue(
                    f"动作「{a.name}」要打开浮层「{a.opens}」，"
                    f"但界面「{screen.name}」里没有这个浮层",
                    line=a.line, code="unknown_overlay"))

    # 节点图「点开」指向的浮层要在同一界面里。写错了不报错、点节点也不弹，
    # 跟「打开」「切到」写错是同一类静默失败，所以一样拦一道。
    for screen in screens:
        here = {o.name for o in screen.overlays()}
        for n in screen.walk():
            if n.kind == "节点图" and getattr(n, "popup", "") and n.popup not in here:
                issues.append(Issue(
                    f"节点图「{n.name}」要点开浮层「{n.popup}」，"
                    f"但界面「{screen.name}」里没有这个浮层",
                    line=n.line, code="unknown_popup"))

    issues.extend(_check_state_paths(screens))
    if endpoints is not None:
        issues.extend(_check_endpoints(screens, endpoints))
    return issues


def _check_endpoints(screens, endpoints) -> list:
    """「远程」actions must have a matching entry in endpoints.

    .ui only says "this action fires a request"; the address comes from the
    caller. An address is a deployment detail — writing it into .ui would
    weld the interface description to one backend. The cost is that two
    places must agree, so check it. 「切到」/「打开」/「关闭」 are local and exempt.
    """
    issues = []
    for screen in screens:
        for a in screen.actions():
            if a.has("远程") and a.name not in (endpoints or {}):
                issues.append(Issue(
                    f"动作「{a.name}」标了远程，但 endpoints 里没有它",
                    line=a.line, code="missing_endpoint"))
    return issues


def _check_state_paths(screens) -> list:
    """Path clashes in cross-screen state, and ambiguous stream routing.

    Shared state is one object for every screen, so a path collision is
    invisible within a single screen — the whole forest has to be checked at
    once. bind() cannot catch these either: 消息流 and 显示 are not fields,
    so fields() never returns them.
    """
    issues, owner, streams = [], {}, []
    for screen in screens:
        for node in screen.walk():
            if node.kind == "消息流":
                streams.append(node)
            shared_node = (node.kind in ("消息流", "显示")
                           or (node.kind == "字段" and node.has("共享")))
            if not shared_node:
                continue
            path = node.bind or node.name
            prev = owner.get(path)
            if prev is not None and prev.kind != node.kind:
                issues.append(Issue(
                    f"共享路径「{path}」被「{prev.kind}」和「{node.kind}」同时占用"
                    f"（另一处在第 {prev.line} 行）",
                    line=node.line, code="path_conflict"))
            owner.setdefault(path, node)

    # 后端返回不带 stream 字段时，消息落到「当前界面那条流」上（见
    # _screen_streams）。多条流时这仍是靠约定的路由，值得说一声——不过
    # 只是提示，后端很可能每次都带着 stream。
    if len(streams) > 1 and any(a.has("远程") for s in screens for a in s.actions()):
        names = "、".join(n.bind or n.name for n in streams)
        issues.append(Issue(
            f"有 {len(streams)} 个消息流（{names}），后端返回的 messages 不带 "
            f"stream 字段时会落到当前界面那条流上",
            line=streams[1].line, code="ambiguous_stream"))
    return issues


# --- backends -------------------------------------------------------------
# Each backend takes (screens, options) and returns
#   {"files": {name: text}, "screens": [...], "warnings": [...], "meta": {...}}

def _envelope(screens, files, backend, warnings=None):
    return {
        "files": files,
        "screens": [s.to_dict() for s in screens],
        "warnings": warnings or [],
        "meta": {"backend": backend},
    }


def ir_backend(screens, options=None):
    """Serialize the widget tree itself, for callers that render elsewhere.

    This is the backend that justifies keeping Jinja out of module scope:
    using it must not require the template system to be installed.

    Note it does NOT run render_vue, so submit_action / clears stay empty —
    those are filled during rendering. Use the vue backend to inspect them.
    """
    import json
    tree = [s.to_dict() for s in screens]
    return _envelope(screens,
                     {"ui.json": json.dumps(tree, ensure_ascii=False, indent=2)},
                     "ir")


def text_backend(screens, options=None):
    """Indented text, for eyeballing what the parser produced."""
    return _envelope(screens, {"tree.txt": dump(screens)}, "text")


def vue_backend(screens, options=None):
    """Vue 3, no build step.

    options["inline"] picks the packaging: three files plus a CDN tag by
    default, or one self-contained HTML when true (needs vue_source or
    vue_path). Same components either way — see render_vue.
    """
    options = options or {}
    files = render_vue(screens,
                       title=options.get("title", "UI"),
                       options_map=options.get("options_map") or {},
                       rows=options.get("rows") or [],
                       endpoints=options.get("endpoints") or {},
                       inline=options.get("inline", False),
                       vue_source=options.get("vue_source"),
                       vue_path=options.get("vue_path"),
                       nav=options.get("nav"))
    return _envelope(screens, files, "vue")


def standalone_backend(screens, options=None):
    """One self-contained HTML file with no runtime at all.

    For hosts that hand a page to a webview as a string — pywebview's
    create_window(html=...) and friends — where interactivity is not needed.
    A startup self-check window is the case in point: it appears exactly when
    no server is running, and it only lists what is missing.

    No runtime means values are baked in at generation time from
    options["state"], 「当」 is evaluated then too (a falsy condition drops
    the block rather than emitting a v-if nobody will run), and fields render
    read-only. Overlays and file pickers are not supported here — with no
    runtime there is nothing to open them or to hold a File. About 2 KB,
    against ~170 KB for the inline vue packaging — that is the whole trade.
    """
    options = options or {}
    files = render_standalone(screens,
                              title=options.get("title", "UI"),
                              state=options.get("state") or {})
    return _envelope(screens, files, "standalone")


BACKENDS = {"ir": ir_backend, "text": text_backend, "vue": vue_backend,
            "standalone": standalone_backend}


def register_backend(name, fn):
    """Add a target. fn(screens, options) -> envelope dict.

    This is the seam that makes the engine reusable: a Qt or terminal target
    can live entirely outside this file.
    """
    BACKENDS[name] = fn


# --- vue rendering --------------------------------------------------------

def _default_widgets():
    """Semantic widget per type, from the shared type contract.

    Imported lazily: tools.render pulls in Jinja, and the ir and text
    backends must stay usable without it.
    """
    from .render import TYPES
    return {name: row[2] for name, row in TYPES.items()}


def _blank_for(node, widgets):
    """The empty value a widget starts at."""
    w = node.widget or widgets.get(node.type or "", "单行")
    if w == "开关":
        return False
    if w == "数字":
        return 0
    return ""


def _put_path(root: dict, path: str, value):
    """Set a dotted path, creating intermediate dicts along the way.

    「绑 article.body」 renders as v-model="form.article.body", so the default
    state must actually contain an `article` object. Keying defaults by field
    name instead left form.article undefined and Vue wrote into nothing at
    the first keystroke.
    """
    parts = path.split(".")
    node = root
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node.setdefault(parts[-1], value)


def _form_defaults(screens):
    """Initial form state, one object per screen.

    Screens get separate state: two screens may use the same field name for
    unrelated purposes, and a shared object would let one screen read the
    other's leftovers. Keyed by screen name — validate() flags duplicates.
    「共享」 fields are excluded; they live in the shared object instead, and
    storing them twice would mean writes landing in the wrong copy.

    Overlay fields are included: an overlay belongs to its screen, so its
    fields share that screen's form.
    """
    widgets = _default_widgets()
    out = {}
    for s in screens:
        state = {}
        for f in s.fields():
            if f.kind != "字段" or f.has("共享"):
                continue
            # 文件字段不进 form：form 要能 JSON 深拷贝（payload、snapshot
            # 都靠它），而 File 对象走一遍 JSON 会变成 {}，静默丢失。
            # 它们单独存在 files 里，见 templates/frontend/app.js.j2。
            if f.type in ("文件", "多文件"):
                continue
            _put_path(state, f.bind or f.name, _blank_for(f, widgets))
        out[s.name] = state
    return out


def _shared_defaults(screens):
    """Cross-screen state: 共享 fields, message streams and 显示 nodes."""
    widgets = _default_widgets()
    shared = {}
    for s in screens:
        for n in s.walk():
            if n.kind == "字段" and n.has("共享"):
                _put_path(shared, n.bind or n.name, _blank_for(n, widgets))
            elif n.kind == "消息流":
                _put_path(shared, n.bind or n.name, [])
            elif n.kind == "显示":
                _put_path(shared, n.bind or n.name, "")
            elif n.kind == "选项":
                _put_path(shared, n.bind or n.name, [])
    # 节点图数据整块放共享状态，后端用 state 换掉整个对象即可。
    for s in screens:
        for n in s.walk():
            if n.kind == "节点图":
                _put_path(shared, n.bind or n.name, {"nodes": [], "edges": []})
                if getattr(n, "selects", ""):
                    _box = shared
                    for _k in n.selects.split(".")[:-1]:
                        _box = _box.setdefault(_k, {})
                    _box[n.selects.split(".")[-1]] = None
    # 最后再把所有「选中」路径压回 None：浮层里的节点图常常绑在选中节点身上
    # （绑 sel.points），上面开槽时会把 sel 建成对象，「当 shared.sel」就恒真了。
    for s in screens:
        for n in s.walk():
            if n.kind == "节点图" and getattr(n, "selects", ""):
                _box = shared
                for _k in n.selects.split(".")[:-1]:
                    _box = _box.setdefault(_k, {})
                _box[n.selects.split(".")[-1]] = None
    return shared


def _first_stream(screens) -> str:
    """Global fallback, used only when a screen has no stream of its own."""
    for s in screens:
        streams = s.streams()
        if streams:
            return streams[0].bind or streams[0].name
    return ""


def _file_fields(screens) -> dict:
    """界面名 -> 这个界面的文件字段名列表。

    文件不进 form，单独放 files；提交时也要换成 FormData。两件事都要
    知道「这个界面有没有文件」，算一次给模板用。
    """
    out = {}
    for s in screens:
        names = [f.bind or f.name for f in s.fields()
                 if f.kind == "字段" and f.type in ("文件", "多文件")]
        if names:
            out[s.name] = names
    return out


def _screen_streams(screens) -> dict:
    """界面名 -> 这个界面第一条消息流。

    必须按界面分。早先回显、乐观占位、后端返回三处都用全局第一条流，于是
    在练习界面提交时，占位「…」被塞进对话界面的 chat，而后端返回
    stream:"drill" 把真消息放进 drill——占位永远留在 chat 里清不掉，练习页
    什么也看不见。
    """
    out = {}
    for s in screens:
        st = s.streams()
        if st:
            out[s.name] = st[0].bind or st[0].name
    return out


def _lookup(state, path, default=""):
    """Read a dotted path out of baked-in state (standalone backend)."""
    node = state
    for part in str(path).split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return "" if node is None else node


def _listing(state, path):
    """Same, but always hands back a list so templates can just iterate."""
    v = _lookup(state, path, [])
    return v if isinstance(v, list) else [v]


def _tag_submit_action(screens) -> None:
    """给每个节点记上「在这里按 Enter 该触发哪个动作」。

    按容器就近取，不是按界面。练习页顶栏有「开始练习」、浮层里有「作答」，
    两个都是「提交 远程」；按界面取第一个的话，浮层里的输入框按 Enter 会
    打到顶栏那个开始练习上——重新出一道题，把正在答的冲掉，而且不报错。

    找法是自上而下带着继承：每进一层容器，如果这层有「提交 远程」动作就
    改用它，没有就沿用外层的。所以浮层里的回车属于浮层，底栏里的属于底栏，
    都符合直觉。

    挂在节点上而不是当渲染参数传：layout.j2 是递归的，参数要穿过每一层
    宏调用才能到 widgets.j2，多加一个上下文变量就要改三个模板。
    """
    def first_submit(box):
        for a in box.children:
            if a.kind == "动作" and a.has("提交") and a.has("远程"):
                return a.name
        return ""

    def walk(box, inherited):
        here = first_submit(box) or inherited
        for n in box.children:
            n.submit_action = here
            if n.children:
                walk(n, here)

    for screen in screens:
        screen.submit_action = first_submit(screen)
        walk(screen, screen.submit_action)


def _tag_clears(screens) -> None:
    """Record which field paths a 「清空」/「回显」 action works on.

    The scope is the action's own container — in a bottom bar that is the one
    input box. Not the whole screen's form: on the drill screen the course and
    topic selects live in the same screen as the answer box, and clearing the
    form would wipe the user's choices too. The old page cleared exactly one
    textarea; this rule is that behaviour generalised.

    Only this screen's form fields are collected. 「共享」 fields live in the
    shared object — they are cross-screen state and one submit should not
    reset them.
    """
    def containers(screen):
        yield screen
        for n in screen.walk():
            if n.kind in ("布局", "区域", "分组", "列表", "浮层"):
                yield n

    for screen in screens:
        for box in containers(screen):
            acts = [a for a in box.children if a.kind == "动作"
                    and (a.has("清空") or a.has("回显"))]
            if not acts:
                continue
            paths = [f.bind or f.name for f in box.children
                     if f.kind == "字段" and not f.has("共享")]
            for a in acts:
                a.clears = paths


def _walk_nodes(node):
    """深度遍历一棵节点树，含它自己。"""
    yield node
    for c in getattr(node, "children", ()) or ():
        yield from _walk_nodes(c)


def render_vue(screens, title="UI", options_map=None, rows=None,
               endpoints=None, inline=False, vue_source=None, vue_path=None,
               template_dir=None, nav=None):
    """Render the frontend. Jinja is imported here, not at module scope.

    inline=False  index.html + style.css + app.js, Vue from a CDN tag.
                  For hosts that already run a server — a separate Vue file
                  also gets browser-cached.
    inline=True   one self-contained index.html with everything inlined
                  (~170 KB). For webview hosts with no server. Vue itself
                  comes from vue_source or vue_path; downloading at
                  generation time would make builds depend on the network.
                  Without it index.html.j2 falls back to the CDN and is no
                  longer self-contained.

    Both paths render the same shell template — a second template for the
    inline case would duplicate the shell, and duplicates diverge.
    """
    import json
    from .render import frontend_renderer

    options_map = options_map or {}
    rows = rows or []
    endpoints = endpoints or {}
    _tag_submit_action(screens)
    _tag_clears(screens)
    shared = _shared_defaults(screens)
    has_remote = any(a.has("远程") for s in screens for a in s.actions())
    ctx = {
        "screens": screens,
        "title": title,
        "options_map": options_map,
        "default_widgets": _default_widgets(),
        "screens_json": json.dumps(
            [{"name": s.name, "role": s.role or DEFAULT_ROLE} for s in screens],
            ensure_ascii=False),
        "form_defaults_json": json.dumps(_form_defaults(screens), ensure_ascii=False),
        # 表格数据的初值，按数据键分开：预览时每张表都塞同一份示例数据。
        # 数据键默认是表名，「绑」能另指一个。
        #
        # 早先是一份全局的 rows_json（一个界面只能有一张表），跟前端那个
        # 全局 rows 一起去掉了。
        "lists_init_json": json.dumps(
            {(n.bind or n.name): rows
             for s in screens for n in _walk_nodes(s) if n.kind == "列表"},
            ensure_ascii=False),
        # 界面名 -> 「载入」用的动作。带着地址参数进来时用它把记录拉回来。
        "loaders_json": json.dumps({s.name: s.load for s in screens if s.load},
                                   ensure_ascii=False),
        # 界面名 -> 标了「进入时」的动作，每次进入那个界面自动跑一次。
        # 列表页靠它打开就有数据，不用先点一下刷新。
        "enter_json": json.dumps(
            {s.name: [a.name for a in s.actions() if a.has("进入时")]
             for s in screens
             if any(a.has("进入时") for a in s.actions())},
            ensure_ascii=False),
        # 浮层名 -> 浮层上的「载入」。地址里带着「浮层=X&id=5」时用它拉记录
        "overlay_loaders_json": json.dumps(
            {o.name: o.load for s in screens for o in s.overlays() if o.load},
            ensure_ascii=False),
        # 顶部导航，由项目编译时算好传进来（见 gen/project.py 的 build）。
        # 传了就用它，不管有没有「切到」；没传照旧按 has_goto 决定。
        "nav": bool(nav),
        "nav_json": json.dumps(nav or [], ensure_ascii=False),
        # 导航里的「退出登录」：只有真有这个接口时才放，不然点了没反应
        "nav_logout": bool(nav) and "auth_logout" in (endpoints or {}),
        "has_shared_state": bool(shared),
        "shared_json": json.dumps(shared, ensure_ascii=False),
        "has_endpoints": bool(endpoints),
        "endpoints_json": json.dumps(endpoints, ensure_ascii=False),
        "has_to_actions": has_remote,
        # .ui 里用了「切到」就说明界面切换已经自己安排好了（比如放进顶栏），
        # 引擎那条 nav 是多余的。没用「切到」时 nav 是唯一的切换入口，
        # 藏了就再也切不过去——这不该由样式表写死，引擎知道答案。
        "has_goto": any(a.goto for s in screens for a in s.actions()),
        # 没有浮层的 .ui 一行浮层代码都不生成
        "has_overlays": any(s.overlays() for s in screens),
        # 有图才插 Vue Flow 和 dagre 的 CDN，没有的页面一个外部依赖都不多
        "has_graphs": any(n.kind == "节点图" for s in screens for n in s.walk()),
        "first_stream_json": json.dumps(_first_stream(screens), ensure_ascii=False),
        # 界面名 -> 该界面的消息流。回显、占位、后端返回三处都按当前界面
        # 取，不能用全局第一条——见 _screen_streams 的说明。
        "screen_streams_json": json.dumps(_screen_streams(screens),
                                          ensure_ascii=False),
        # 界面名 -> 该界面的文件字段。有文件的界面提交走 FormData，没有的
        # 照旧发 JSON——两条路差别不小，引擎先算好省得运行时判断。
        "file_fields_json": json.dumps(_file_fields(screens), ensure_ascii=False),
        # 动作名 -> 发请求前要本地回显的字段路径。旧版发消息时先
        # add('你', text) 再发请求，自己说的话立刻出现；等后端回传的话，
        # 接真模型要等好几秒，中间只有一个「…」。
        "echoes_json": json.dumps(
            {a.name: a.clears for s in screens for a in s.actions()
             if a.has("回显") and a.clears},
            ensure_ascii=False),
        # 动作名 -> 提交成功后要清空的数据路径。按钮和 Enter 都查这张表，
        # 免得两条路各传各的、哪天漏一处。
        "clears_json": json.dumps(
            {a.name: a.clears for s in screens for a in s.actions()
             if a.has("清空") and a.clears},
            ensure_ascii=False),
    }
    fr = frontend_renderer()
    css = fr.render("style.css.j2", **ctx)
    app = fr.render("app.js.j2", **ctx)

    if not inline:
        return {"index.html": fr.render("index.html.j2", **ctx),
                "style.css": css, "app.js": app}

    if vue_source is None and vue_path:
        from pathlib import Path
        vue_source = Path(vue_path).read_text(encoding="utf-8")
    return {"index.html": fr.render("index.html.j2", inline_css=css,
                                    inline_js=app, vue_source=vue_source, **ctx)}


def render_standalone(screens, title="UI", state=None):
    """Render one runtime-free HTML file. Jinja imported here, not at module scope."""
    from .render import standalone_renderer

    state = state or {}

    def visible(node):
        # 「当」 names a condition the host knows at generation time. An
        # unknown key means "no reason to hide it" — dropping content over a
        # typo'd condition would be worse than showing it.
        if not node.when:
            return True
        return bool(_lookup(state, node.when, True))

    r = standalone_renderer()
    # These go on the Environment, and close over `state` rather than taking
    # it as an argument: nodes.j2 is imported as a module, so its macros run
    # outside the calling template's context — anything passed per-render,
    # `state` included, is undefined in there.
    r.env.globals.update(
        lookup=lambda path, default="": _lookup(state, path, default),
        listing=lambda path: _listing(state, path),
        visible=visible)
    # Macro names are Chinese. TemplateModule only exposes a macro as a Python
    # attribute when its name is a valid identifier, so .节点 does not resolve —
    # go through the module's export dict.
    render_node = r.env.get_template("nodes.j2").module.__dict__["节点"]
    html = r.render("page.html.j2", screens=screens, title=title,
                    state=state, 节点=render_node)
    return {"page.html": html}


# --- entry points ---------------------------------------------------------

def parse_ui(text):
    return parse(text)


# 前端模板认得的控件名（templates/frontend/widgets.j2 的「控件」宏）。
# 两边要一起改：模板里加了一种控件，这里也要加上。
KNOWN_WIDGETS = {"单行", "多行", "数字", "日期", "开关", "下拉", "单选",
                 "密码", "选文件", "选多文件"}


def check_widgets(screens) -> list:
    """「控件 X」里的 X 前端认不认得。

    不认得的名字在模板里落到最后的 else，变成普通文本框，而且什么都不报。
    「控件 密码」就是这么把密码明文显示在屏幕上的——所以编译时查出来。
    """
    issues = []
    for screen in screens:
        for node in _walk_nodes(screen):
            w = getattr(node, "widget", None)
            if w and w not in KNOWN_WIDGETS:
                issues.append(Issue(
                    f"「控件 {w}」前端不认得，会显示成普通文本框。"
                    f"可用：{'、'.join(sorted(KNOWN_WIDGETS))}",
                    line=node.line, code="unknown_widget"))
    return issues


def check_loaders(screens, endpoints) -> list:
    """「载入 X」的 X 得是个有接口的动作；「带 id」得配「切到」或「打开」。

    载入的接口不存在的话，刷新编辑界面时表单静默地一直是空的；带了 id
    却没说去哪儿，参数无处可去。两种都是写了等于没写、而且不报错。
    """
    issues = []
    for screen in screens:
        # 界面和它的浮层都可以写「载入」
        for holder in [screen, *screen.overlays()]:
            if holder.load and endpoints is not None and holder.load not in endpoints:
                what = "界面" if holder is screen else "浮层"
                issues.append(Issue(
                    f"{what}「{holder.name}」要「载入 {holder.load}」，但没有这个接口",
                    line=holder.line, code="missing_endpoint"))
        for node in _walk_nodes(screen):
            if (getattr(node, "carry", "") and not getattr(node, "goto", "") and not getattr(node, "popup", "")
                    and not getattr(node, "opens", "")):
                issues.append(Issue(
                    f"动作「{node.name}」写了「带 {node.carry}」但没有「切到」"
                    f"或「打开」，参数无处可去",
                    line=node.line, code="carry_without_goto"))
    return issues


def compile_ui(text_or_screens, backend="vue", fields=None,
               require_bind=False, options=None):
    """Parse, bind, validate and emit in one call.

    Issues are returned, not raised — a missing field type should not stop
    you from seeing the rest of the output. Callers grade them by `code`;
    see build.py's BLOCKING set.
    """
    screens = (parse(text_or_screens) if isinstance(text_or_screens, str)
               else text_or_screens)
    issues = []
    if fields is not None:
        issues.extend(bind(screens, fields))
    issues.extend(validate(screens, require_bind=require_bind,
                           endpoints=(options or {}).get("endpoints")))
    issues.extend(check_widgets(screens))
    issues.extend(check_loaders(screens, (options or {}).get("endpoints")))
    if backend not in BACKENDS:
        raise ValueError(f"未知后端「{backend}」，可用：{'、'.join(sorted(BACKENDS))}")
    result = BACKENDS[backend](screens, options or {})
    result["issues"] = [i.to_dict() for i in issues]
    return {"screens": screens, "issues": issues, "result": result}


def check(text, fields=None):
    """Parse and validate only; returns a plain-language summary.

    fields accepts either shape bind() takes: {name: "文本"} or
    {name: {"type": "文本", ...}}.
    """
    try:
        screens = parse(text)
    except UiSyntaxError as e:
        return f"语法错误：{e}"
    if not screens:
        return "没有解析到任何界面"

    issues = []
    if fields is not None:
        issues.extend(bind(screens, fields))
        issues.extend(validate(screens, require_bind=True))
    else:
        issues.extend(validate(screens, require_bind=False))

    lines = []
    for screen in screens:
        n, a = len(screen.fields()), len(screen.actions())
        ov = len(screen.overlays())
        unknown = [x.name for x in screen.fields() if x.type is None]
        extra = f"，类型未知：{'、'.join(unknown)}" if unknown else ""
        more = f"，{ov} 个浮层" if ov else ""
        lines.append(f"界面「{screen.name}」角色={screen.role}："
                     f"{n} 个字段，{a} 个动作{more}{extra}")
    if issues:
        lines.append("问题：")
        lines.extend(f"  - {i}" for i in issues)
    return "\n".join(lines)
