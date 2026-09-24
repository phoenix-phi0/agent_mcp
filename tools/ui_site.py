# -*- coding: utf-8 -*-
"""把几个 `.ui` 文件合成一个应用。

    from tools import ui_site
    screens, issues = ui_site.merge({"learner.ui": 文本, "answer.ui": 文本})
    compile_ui(screens, ...)

## 为什么能直接拼

界面切换是 hash 路由：`route` 这个 ref 存当前界面名，`current` 是它的
computed，每个界面的 form 上挂 `v-if="current.name === '界面名'"`。

所以**几个文件的界面进同一个 screens 数组，「切到」就能跨文件跳**，
路由那层一行都不用改。`compile_ui` 的第一个参数本来就接受 screens 列表。

## 要处理的只有重名和入口

**重名**：`current` 是 `screens.find(s => s.name === route.value)`，重名
的话永远命中第一个，另一个界面**永远打不开**——而且不报错。所以合并时
必须查，还要说清楚是哪两个文件撞了。

**入口**：`screens[0]` 是 hash 为空时的默认界面。单文件时那是「第一个
界面」，多文件时变成「合并顺序的第一个」——那取决于字典序，不该由它
决定。所以 `entry` 参数显式指定，指定的那个排到最前。

## 跨文件的「切到」检查

`validate` 现在按单份文本检查，跳到别的文件里的界面会报 unknown_screen。
合并之后一起检查就没这问题——这也是必须先合并再校验的原因。
"""

from tools.ui import parse


class SiteError(Exception):
    """界面重名，或者指定的入口不存在。"""


def merge(files: dict, entry: str = "") -> tuple:
    """合并几个 .ui。files 是 {文件名: 文本}，返回 (screens, 问题列表)。

    entry 指定哪个界面是入口（hash 为空时显示的那个），不给就用第一个
    文件的第一个界面。

    重名直接抛——那是必须修的错，不是可以将就的问题：重名的界面里有
    一个永远打不开，而运行时什么都不会报。
    """
    screens = []
    来自 = {}          # 界面名 -> 哪个文件，报重名时要说清楚
    问题 = []

    for name in sorted(files):
        text = files[name]
        try:
            parsed = parse(text)
        except Exception as e:
            问题.append(f"{name}：解析失败 {type(e).__name__}: {e}")
            continue

        for s in parsed:
            if s.name in 来自:
                raise SiteError(
                    f"界面「{s.name}」重名：{来自[s.name]} 和 {name} 里都有。"
                    f"合并之后后面那个永远打不开——路由按名字找，只会命中"
                    f"第一个。改掉其中一个的名字。")
            来自[s.name] = name
            screens.append(s)

    if not screens:
        问题.append("一个界面都没有")
        return screens, 问题

    if entry:
        idx = next((i for i, s in enumerate(screens) if s.name == entry), -1)
        if idx < 0:
            有 = "、".join(s.name for s in screens)
            raise SiteError(f"入口界面「{entry}」不存在。有这些：{有}")
        # 挪到最前：hash 为空时前端取 screens[0]
        screens.insert(0, screens.pop(idx))

    return screens, 问题


def describe(files: dict, entry: str = "") -> str:
    """合并之后有哪些界面、跨文件跳转接不接得上。排查用。"""
    try:
        screens, 问题 = merge(files, entry)
    except SiteError as e:
        return f"[出错] {e}"

    名字 = {s.name for s in screens}
    lines = [f"{len(files)} 个文件，{len(screens)} 个界面"]
    if entry:
        lines[0] += f"，入口「{entry}」"

    for s in screens:
        跳转 = [n.goto for n in _walk(s) if getattr(n, "goto", "")]
        坏的 = [g for g in 跳转 if g not in 名字]
        标 = f"  {s.name}（{s.role or '自定义'}）"
        if 跳转:
            标 += f"　→ {'、'.join(跳转)}"
        if 坏的:
            标 += f"　[目标不存在：{'、'.join(坏的)}]"
        lines.append(标)

    lines.extend("  " + x for x in 问题)
    return "\n".join(lines)


def _walk(node):
    yield node
    for c in getattr(node, "children", ()) or ():
        yield from _walk(c)


def merge_files(paths, entry: str = "", root=None) -> str:
    """文本进文本出的排查入口。paths 是逗号分隔的文件名。

    给 MCP 的 _CALLABLE 用——JSON 传不了字典，所以收路径自己读。
    路径相对 root（默认 data/）。
    """
    from pathlib import Path

    base = Path(root) if root else \
        Path(__file__).resolve().parent.parent / "data"

    files = {}
    for rel in [x.strip() for x in paths.split(",") if x.strip()]:
        p = (base / rel).resolve()
        if base.resolve() not in p.parents and p.parent != base.resolve():
            return f"[路径越界] {rel}"
        if not p.is_file():
            return f"[文件不存在] {rel}"
        files[p.name] = p.read_text(encoding="utf-8")

    return describe(files, entry)
