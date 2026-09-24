# -*- coding: utf-8 -*-
"""把 .ui 里的实体引用展开成具体字段。

两种写法：

    字段 article.title 标题          单写一个，带实体名
    全部字段 article 除 id created    整表展开，去掉几个

## 为什么是独立的一步，不在 parse 里

`parse()` 不知道实体长什么样——那是 `.entity` 的事。要在解析时展开，
`ui.py` 就得 import `entity.py`，两个本来独立的语言绑死在一起。

而 `compile_ui` 的第一个参数可以是文本也可以是已解析的 screens，所以
展开插在中间正好：

    screens = parse(text)
    expand(screens, entities)        # ← 这里
    compile_ui(screens, fields=..., ...)

`ui.py` 那边只要认得「全部字段」这个行关键字就行（两行常量），别的
一概不知道。

## 名字和绑定是两回事

展开出来的节点 `name` 是带实体名的（`article.title`），`bind` 是裸名
（`title`）。

    name  用来查字段表——带实体名才能区分两个实体里的同名字段
    bind  是前端表单里的键——裸名，不然生成的 JS 里会出现
          form["article.title"] 这种，模板里但凡用点号访问就炸

手写的 `字段 article.title` 也照这个规则补上 bind，不然两种写法出来的
产物不一样。

## 展开带不了样式

实体里只有类型和必填，「提示文字」「宽度」「占几列」这些纯界面的东西
它不知道。所以 `全部字段` 适合快速出一个能用的表单，要调样式还得把那
几个字段单独写出来。

这条限制没法绕过，除非把界面属性也塞进 .entity——那就让数据模型开始
关心显示，不划算。
"""

from .ui import Issue, Node

KEYWORD = "全部字段"
EXCLUDE_WORD = "除"


def _entity_of(entities, name: str):
    for e in entities:
        if e.name == name:
            return e
    return None


def _split_excludes(label: str):
    """从「除 id created」里取出要排除的字段名。

    「除」后面的都算排除项。写在 label 里是因为 ui.py 的行解析把认不出
    的词都归进 label——这样新语法不用改解析器。
    """
    parts = (label or "").split()
    if not parts or parts[0] != EXCLUDE_WORD:
        return set()
    return set(parts[1:])


def _walk(node):
    """深度优先遍历所有有 children 的节点。"""
    yield node
    for child in getattr(node, "children", ()) or ():
        yield from _walk(child)


def expand(screens, entities) -> list:
    """把 screens 里的「全部字段」展开成具体字段，就地修改。

    返回 Issue 列表——指向不存在的实体、排除了不存在的字段这些。
    不抛异常：一个写错的实体名不该让整个界面生成不出来，报出来让人
    自己看。
    """
    issues = []
    known = ", ".join(sorted(e.name for e in entities)) or "无"

    for screen in screens:
        for parent in _walk(screen):
            kids = getattr(parent, "children", None)
            if not kids:
                continue

            out = []
            for node in kids:
                if node.kind != KEYWORD:
                    out.append(node)
                    continue

                entity = _entity_of(entities, node.name or "")
                if entity is None:
                    issues.append(Issue(
                        f"「全部字段 {node.name}」指向不存在的实体。"
                        f"这里有：{known}",
                        line=node.line, code="unknown_entity"))
                    continue

                excludes = _split_excludes(node.label)
                有的 = {f.name for f in entity.fields}
                for miss in sorted(excludes - 有的):
                    # 排除一个不存在的字段多半是拼写错，或者实体改过名。
                    # 不挡住生成，但要说一声——静默忽略的话，人会以为
                    # 那个字段被排掉了，实际它压根没在表里。
                    issues.append(Issue(
                        f"「除 {miss}」：实体「{entity.name}」里没有这个字段",
                        line=node.line, code="unknown_exclude"))

                for f in entity.fields:
                    if f.name in excludes:
                        continue
                    out.append(Node(
                        kind="字段",
                        name=f"{entity.name}.{f.name}",
                        label=f.label or f.name,
                        type=f.type,
                        required=True if f.required else None,
                        # 展开出来的节点没有修饰词——实体里没有界面属性。
                        # 要提示文字、宽度这些，把那个字段单独写出来。
                        modifiers=[],
                        line=node.line,
                    ))

            parent.children = out

    _fill_bind(screens)
    return issues


def _fill_bind(screens) -> None:
    """给带实体名的字段补上 bind（裸字段名）。

    name 带实体名是为了查字段表，bind 是前端表单里的键——那里要裸名，
    不然生成的 JS 里会出现 form["article.title"]，模板但凡用点号访问
    就炸。

    手写的「字段 article.title」也走这里，两种写法的产物才一样。

    bind 已经有值就不动：.ui 里显式写了「绑 xxx」是有意的覆盖。
    """
    for screen in screens:
        for node in _walk(screen):
            if node.kind != "字段" or node.bind:
                continue
            if "." in (node.name or ""):
                node.bind = node.name.split(".", 1)[1]


def describe(screens) -> str:
    """列出展开后的字段，排查用。"""
    lines = []
    for screen in screens:
        names = [f"{n.name}→{n.bind}" for n in _walk(screen)
                 if n.kind == "字段"]
        lines.append(f"{screen.name}：{len(names)} 个字段")
        lines.extend("  " + x for x in names)
    return "\n".join(lines)


def check(ui_text: str, entity_text: str = "") -> str:
    """文本进、文本出的排查入口。给 MCP 的 _CALLABLE 用。

    两个参数都是文本：.ui 的内容和 .entity 的内容。JSON 传不了 screens
    和 entities 那种对象，所以要这么一层——跟 entity.render_sql 同样的
    理由。

    不给 entity_text 就只解析不展开，那时「全部字段」会原样留着，
    用来确认 ui.py 认不认得这个关键字。
    """
    from .entity import parse as parse_entity
    from .ui import parse as parse_ui

    try:
        screens = parse_ui(ui_text)
    except Exception as e:
        return f"解析 .ui 失败：{type(e).__name__}: {e}"

    if not entity_text.strip():
        待展开 = [n.name for s in screens for n in _walk(s)
                 if n.kind == KEYWORD]
        return (f"解析出 {len(screens)} 个界面。"
                f"待展开的「全部字段」：{'、'.join(待展开) or '无'}\n"
                f"（没给实体定义，没有展开）")

    try:
        entities = parse_entity(entity_text)
    except Exception as e:
        return f"解析 .entity 失败：{type(e).__name__}: {e}"

    issues = expand(screens, entities)
    out = [describe(screens)]
    if issues:
        out.append("")
        out.append("问题：")
        out.extend(f"  - {i}" for i in issues)
    return "\n".join(out)


def check_files(ui_path: str, entity_path: str = "") -> str:
    """同 check，但收两个路径，自己去 data/ 下读。

    比 check 顺手：不用把 .entity 的全文塞进 JSON 参数里转义一遍。
    tool_call_file 一次只能塞一个文件，而这件事要两个。

    路径相对 data/，越界会被挡——跟 write_file 同一条线。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "data"

    def read(rel: str) -> str:
        p = (root / rel).resolve()
        if p != root and root not in p.parents:
            raise ValueError(f"路径越界：{rel}")
        if not p.is_file():
            raise ValueError(f"文件不存在：{rel}")
        return p.read_text(encoding="utf-8")

    try:
        ui_text = read(ui_path)
        entity_text = read(entity_path) if entity_path else ""
    except ValueError as e:
        return f"[出错] {e}"

    return check(ui_text, entity_text)
