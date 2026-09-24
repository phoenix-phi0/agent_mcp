# -*- coding: utf-8 -*-
"""精确替换：改 data/ 下文件里的一小段，不重写整个文件。

## 为什么需要它

`write_file` 只能整个覆盖。改一个上千行的文件里的两行，要把上千行原样
搬一遍——那些内容在传输途中毫无意义，而且**实际压垮过 MCP 服务器两次**。
交给 zcode 做同样的事也超时了：它读进来、改完、再写回去，中间那些行
还是要经过一次 MCP。

所以缺的是一个「只发改动」的写入方式。

## 界线跟 write_file 一样：只能改 data/

第一版把根设成了项目根，理由是「它存在的意义就是改 tools/ 这些 data
之外的代码」。那个理由站不住——那只是想要的便利，不是安全上的论证。

这套目录的安全性建立在一条界线上：**可写的地方不被执行，会执行的地方
不可写**。`verbs/` 下的 `_verbs.py` 会被 `load_pack` 直接执行，能改那里
等于任意代码执行；`tools/`、`agents/` 同理。开这个口子省下的是几次手动
复制，赔进去的是整套假设。

所以 data/ 之外的文件仍然要人手动改。那是这条界线本来就该有的代价。

## 用法

    file.show(path, around="某段文字")    先看一眼，确认 old 怎么写
    file.edit(path, old, new)             替换唯一一处
    file.edit(path, old, new, count=3)    替换 3 处（个数必须对上）
    file.restore(path)                    撤回上一次改动

## 为什么要求 old 唯一

不唯一就报错，并说出找到几处。

替换多处时必须显式给 count，而且个数对不上也报错——「我以为只有一处，
其实有三处」是这类工具最常见的事故，静默替换全部会改坏两处看不见的
地方。
"""

import difflib
from pathlib import Path

# 跟 fs.py 的 DATA 同一个目录：唯一对外可写的地方
ROOT = Path(__file__).resolve().parent.parent / "data"

# 改之前先备份到这里。备份是一次性的（同名覆盖），够用来救「上一次
# 改错了」——真要历史版本该用 git。
BACKUP_DIR = ROOT / ".edit_backup"


class EditError(Exception):
    """路径不合法、找不到、或者匹配不唯一。"""


def _resolve(path: str) -> Path:
    p = (ROOT / path).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise EditError(
            f"路径越界：{path}。只能改 data/ 下的文件——"
            f"tools/ verbs/ 这些会被执行的目录不开放写入，"
            f"那条界线是这套目录安全性的基础。")
    if not p.is_file():
        raise EditError(f"文件不存在：{path}")
    return p


def _backup(p: Path, text: str) -> None:
    """改之前存一份。失败不影响主流程——备份是好意，不是前提。"""
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        rel = p.relative_to(ROOT).as_posix().replace("/", "__")
        (BACKUP_DIR / rel).write_text(text, encoding="utf-8")
    except (OSError, ValueError):
        pass


def edit(path: str, old: str, new: str, count: int = 1) -> str:
    """把 path 里的 old 换成 new。

    old 必须正好出现 count 次，多了少了都报错并说出实际几次——
    「我以为只有一处」是这类操作最常见的事故。

    返回改动前后的 diff 片段，好让调用方确认改对了地方。
    """
    p = _resolve(path)
    text = p.read_text(encoding="utf-8")

    found = text.count(old)
    if found == 0:
        raise EditError(f"{path} 里找不到那段内容。" + _hint(text, old))
    if found != count:
        raise EditError(
            f"{path} 里那段出现了 {found} 次，但 count={count}。"
            f"要全改就传 count={found}，只改一处就把 old 写长一点让它唯一。")

    updated = text.replace(old, new)
    _backup(p, text)
    p.write_text(updated, encoding="utf-8")
    return f"已改 {path}（{found} 处）\n" + _diff(text, updated, path)


def append(path: str, text: str) -> str:
    """在文件末尾追加。适合往列表、字典末尾加东西。"""
    p = _resolve(path)
    old = p.read_text(encoding="utf-8")
    _backup(p, old)
    p.write_text(old.rstrip("\n") + "\n" + text.rstrip("\n") + "\n",
                 encoding="utf-8")
    return f"已在 {path} 末尾追加 {len(text.splitlines())} 行"


def show(path: str, around: str = "", lines: int = 12) -> str:
    """看一段内容，确认 old 该怎么写。

    around 给一段文字，返回它周围的若干行（带行号）。不给就返回开头。

    这个函数存在是因为 edit 的 old 必须一字不差——空格、引号、换行都算。
    凭记忆写十有八九对不上，先看一眼比试三次快。
    """
    p = _resolve(path)
    rows = p.read_text(encoding="utf-8").splitlines()

    if not around:
        return "\n".join(f"{i:5} | {r}" for i, r in enumerate(rows[:lines], 1))

    hits = [i for i, r in enumerate(rows) if around in r]
    if not hits:
        return f"{path} 里没有含「{around}」的行"

    out = [f"{path}：{len(hits)} 处含「{around}」"]
    for hit in hits[:5]:
        lo = max(0, hit - lines // 2)
        hi = min(len(rows), hit + lines // 2 + 1)
        out.append("")
        for i in range(lo, hi):
            mark = ">" if i == hit else " "
            out.append(f"{mark}{i + 1:5} | {rows[i]}")
    if len(hits) > 5:
        out.append(f"\n（还有 {len(hits) - 5} 处没显示）")
    return "\n".join(out)


def _hint(text: str, old: str) -> str:
    """找不到时给点线索：有没有长得像的行。

    多数情况是空格数量或者引号种类不一样，肉眼看 diff 比重猜快。
    """
    first = old.strip().splitlines()[0] if old.strip() else ""
    if not first:
        return ""
    probe = first[:20]
    hits = [r for r in text.splitlines() if probe in r]
    if not hits:
        return "连近似的行都没有，确认路径和内容对不对。"
    return ("有这么几行看着像，注意空格和引号：\n"
            + "\n".join("  " + h for h in hits[:3]))


def _diff(before: str, after: str, path: str) -> str:
    """只显示变化的那几行，不显示整个文件。"""
    rows = list(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=path, tofile=path, lineterm="", n=2))
    if len(rows) > 40:
        rows = rows[:40] + [f"…（还有 {len(rows) - 40} 行 diff）"]
    return "\n".join(rows)


def restore(path: str) -> str:
    """把上一次改动撤回。只保留最近一次，救不了更早的。"""
    p = _resolve(path)
    rel = p.relative_to(ROOT).as_posix().replace("/", "__")
    b = BACKUP_DIR / rel
    if not b.is_file():
        return f"{path} 没有备份"
    p.write_text(b.read_text(encoding="utf-8"), encoding="utf-8")
    return f"已把 {path} 恢复到上一次改动之前"
