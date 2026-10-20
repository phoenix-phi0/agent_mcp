"""约定规划 contracts/<模块>.md 的检查：dslproj 的约定检查（格式、跨模块调用必须是依赖且上游有该公开函数、接口指向公开函数、
每个公开函数有用例、多余依赖……）+ v3 另加：约定的「依赖」必须是 plan/top.zs 里的模块且不成环（不要求与 top.zs 逐字一致，
全部约定过后用「同步顶层依赖」动词同步）、表名以「模块名」或「模块名_」开头（各模块的表不重名）。
确定性，不调模型。
"""
from pathlib import Path

from ..packs.dslproj import contract as C
from . import top as T


def path_of(project, module):
    return Path(project) / "contracts" / f"{module}.md"


def upstream_of(project, name, deps):
    """→ ({上游: 约定}, 问题)：deps 里每个模块读 contracts/<m>.md 并解析；读不到 / 解析不过记问题。"""
    ups, probs = {}, []
    for d in deps:
        f = path_of(project, d)
        if not f.is_file():
            probs.append(f"依赖的模块「{d}」还没有约定文件（contracts/{d}.md）")
            continue
        uc, p = C.parse(f.read_text(encoding="utf-8"))
        if p:
            probs.append(f"上游 contracts/{d}.md 解析不通过：{p[0]}")
        else:
            ups[d] = uc
    return ups, probs


def cycle_with(project, name, deps, mods):
    """用已通过的约定（没通过的模块退回 top 里缺省的依赖）搭一张依赖图，把 name 的依赖换成 deps → 有环返回环上的名字列表，没有返回 None。"""
    graph = {}
    for m, d in mods.items():
        if m == name:
            graph[m] = list(deps)
            continue
        try:
            uc, _ = load(project, m)
            graph[m] = uc["依赖"]
        except FileNotFoundError:
            graph[m] = d
    return T.find_cycle(graph)


def check(text, name, top, project):
    """→ 问题列表（空 = 通过）。top：top.load 的结果；project：读上游约定的项目目录。"""
    mods = {m["名"]: m["依赖"] for m in top["模块"]}
    if name not in mods:
        return [f"模块「{name}」不在 plan/top.zs 里"]
    c, probs = C.parse(text)
    ups, up_probs = upstream_of(project, name, c["依赖"] or mods[name])
    probs += up_probs
    probs += C.check(c, name, ups, list(mods))
    # 依赖与 top.zs 不要求逐字一致：只要依赖的是 top.zs 里的模块（上面已查）且不成环就放行；
    # 全部约定过后由「同步顶层依赖」把 top.zs 改成与约定一致。
    cyc = cycle_with(project, name, c["依赖"], mods)
    if cyc:
        probs.append("约定的「依赖」会和已有约定一起成环：" + " → ".join(cyc))
    for t in c["表"]:
        if t["名"] != name and not t["名"].startswith(name + "_"):
            probs.append(f"第 {t['行']} 行：表名「{t['名']}」要以「{name}_」开头（各模块的表不重名）")
    probs += optional_empty(c)
    seen = set()
    return [p for p in probs if not (p in seen or seen.add(p))]


def optional_empty(c):
    """用例里给「可选入参」传「空」：可选入参不传和传空串都是空串，函数里分不出来，这样的用例没法由实现满足
    （常见错法：'传空表示清空、不传表示不改'）。→ 问题列表。"""
    fns = {f["名"]: f for f in c["函数"]}
    probs = []
    for u in c["用例"]:
        call = u["调用"]
        f = fns.get(call["目标"]) if call else None
        if f is None:
            continue
        opt = set(C.params(f)[1])
        for k, v in call["参数"].items():
            if k in opt and v in ("空", ""):
                probs.append(f"第 {call['行']} 行：用例 {u['名']} 给可选入参 {k} 传了「空」，可选入参不传和传空串都是空串，函数分不出来，"
                             f"这样的用例实现没法满足（想表达清空 / 置空，请把它改成必填入参或另做一个函数）")
    return probs


def load(project, name):
    """通过检查后的约定 → (contract, 原文)；读不到抛 FileNotFoundError。"""
    text = path_of(project, name).read_text(encoding="utf-8")
    return C.parse(text)[0], text


def digest(c):
    """给记录用的摘要：函数 / 公开函数 / 接口 / 用例 / 表数。"""
    return {"表": len(c["表"]), "函数": len(c["函数"]), "公开函数": sum(1 for f in c["函数"] if f["公开"]),
            "接口": len(c["接口"]), "用例": len(c["用例"])}
