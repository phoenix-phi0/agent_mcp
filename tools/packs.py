# -*- coding: utf-8 -*-
"""动词包的统一入口。

在此之前，「加载哪些包」这件事散在五个地方各写一遍：

    agents/flows.py     _verbs()      写死 ["common","quiz","japanese"]
    agents/serve.py     _verbs()      同上，代码几乎一样
    app2/serve.py       _verbs()      同上
    fs.py               _make_verbs() 同上
    dsl/run.py          扫描全部包

加个新包要改四处，漏一处那边就少动词，而且不报错——只在调用到的时候
说「没有这个动词」，看着像动词写错了。web 包当初就是这么被漏掉的。

## 现在谁说了算

**脚本自己**。`.zs` 开头写 `用包 common quiz`，引擎按名字去 verbs_root()
下加载。调用方只提供包目录，不决定加载什么：

    eng = engine_for(client, workspace)      # 不预加载
    eng.run(script)                          # 脚本里的「用包」说了算

这样脚本是自描述的——换个地方跑不会莫名其妙少个动词，而且能拿到严格
模式：写错的动词名会报错，不会被当成普通文本静默带过。

没写「用包」的脚本仍然能跑，只是一个动词都没有。`讲解.zs` 和
`词汇扩展.zs` 就是这种——它们只有读取、打印、问，本来就不调动词。

## 例外：不经过脚本的调用

练习模式那条路直接调 Python 动词，没有脚本可写「用包」，所以要显式
给包名：

    call_verb("挑题号", 题库, "1", 课程, packs=["common", "quiz"])

调用方自己定义一个常量列出要用的包，比藏在这里的默认值清楚——
哪段代码依赖哪些包，在那段代码旁边就看得见。
"""

import os
from pathlib import Path

from .dsl import DSLEngine, RESERVED, to_text
from .verbs import VerbRegistry

# 项目根：tools/ 的上一级
CODE_ROOT = Path(__file__).resolve().parent.parent

# 打包成 exe 后代码在临时目录、数据在 exe 旁边，所以数据目录要单独算
DATA_ROOT = Path(os.environ.get("JP_DATA_DIR") or CODE_ROOT)

_cache: dict[tuple, VerbRegistry] = {}


def verbs_root() -> Path:
    """动词包目录。

    跟着数据目录走而不是代码目录：打包之后用户仍然要能编辑动词包，
    塞进 exe 里就改不了了，那跟「改流程不碰代码」的初衷相反。
    """
    return DATA_ROOT / "verbs"


def available() -> list[str]:
    """列出有哪些包可用。

    判据跟 load_pack 一致：有 _verbs.py 或者顶层有 .zs 就算一个包。
    只有 defs/ 而没有 _verbs.py 的目录不算——那样没人去扫 defs/。
    """
    root = verbs_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and (any(p.glob("*.zs"))
                                     or (p / "_verbs.py").is_file()))


def registry(packs: list[str], workspace: Path | str | None = None,
             cache: bool = True) -> VerbRegistry:
    """建一个动词表并加载指定的包。

    packs 是必填的——没有默认值。默认值会让「这段代码依赖哪些包」变成
    一个要翻源码才知道的事，而且加新包时容易忘了某处没跟上。

    结果按 (包组合, workspace) 缓存：同一组合反复建表会重复执行每个包的
    _verbs.py，白费事。改了动词包调 clear_cache()，或者传 cache=False。
    """
    names = list(packs)
    ws = Path(workspace).resolve() if workspace else DATA_ROOT
    key = (tuple(names), str(ws))

    if cache and key in _cache:
        return _cache[key]

    reg = VerbRegistry(reserved=RESERVED)
    root = verbs_root()
    for name in names:
        pack = root / name
        if pack.is_dir():
            reg.load_pack(pack, workspace=ws)
        else:
            # 不抛异常：点名的包里有一个不存在，不该让整个环境起不来。
            # 记警告，describe() 和 list_verbs 里看得到。
            reg.warnings.append(f"动词包不存在：{pack}")

    if cache:
        _cache[key] = reg
    return reg


def engine_for(client=None, workspace: Path | str | None = None,
               packs: list[str] | None = None, verbose: bool = False,
               **kwargs) -> DSLEngine:
    """造一个配好动词包目录的引擎。

    默认不预加载任何包，由脚本里的「用包」决定。传 packs 是给那些
    确实没法在脚本里声明的场合留的口子，正常不该用到。
    """
    ws = Path(workspace).resolve() if workspace else DATA_ROOT
    return DSLEngine(
        client,
        workdir=ws,
        verbose=verbose,
        verbs=registry(packs, ws) if packs else None,
        verbs_root=verbs_root(),
        **kwargs,
    )


def call_verb(name: str, *args, packs: list[str],
              workspace: Path | str | None = None):
    """不经过 DSL，直接调一个 Python 动词。

    练习模式那种「就三个固定的函数调用」的场景用这个——走 DSL 只是多一层。
    动词表在这里起的是函数注册表的作用，同一套动词两边都能用。

    packs 是关键字参数且必填：调用方自己列出依赖，看得见。

    返回值保留原始类型：动词返回列表就给列表，调用方是 Python 代码，
    能直接用。要文本的话用 call_verb_text——DSL 那边才必须转，因为
    output 是字符串列表。
    """
    reg = registry(packs, workspace)
    if not reg.has(name):
        return f"[没有动词] {name}"
    params = reg.bind(name, [to_text(a) for a in args])
    kind, impl = reg.resolve(name)
    if kind != "python":
        return f"[{name} 不是 Python 动词]"
    result = impl(**params)
    return "" if result is None else result


def call_verb_text(name: str, *args, **kwargs) -> str:
    """call_verb 的文本版。期望字符串的老调用方用这个，判断逻辑不用改。"""
    return to_text(call_verb(name, *args, **kwargs))


def clear_cache() -> None:
    """清掉动词表缓存。改了 verbs/ 下的代码之后调用。"""
    _cache.clear()


def describe(packs: list[str] | None = None,
             workspace: Path | str | None = None) -> str:
    """人类可读的动词清单，带加载警告。

    不给 packs 就把目录里所有包都加载一遍——这个函数是给人看的，
    列全比列准更有用。
    """
    names = list(packs) if packs else available()
    reg = registry(names, workspace, cache=False)
    out = [
        f"包目录　　{verbs_root()}",
        f"目录里有　{', '.join(available()) or '无'}",
        f"本次加载　{', '.join(reg.packs) or '无'}",
        "",
        reg.describe(),
    ]
    if reg.warnings:
        out += ["", "[警告]"] + ["  " + w for w in reg.warnings]
    return "\n".join(out)


if __name__ == "__main__":
    print(describe())
