"""约定规划 contracts/<模块>.md 的检查：dslproj 的约定检查（格式、跨模块调用必须是依赖且上游有该公开函数、接口指向公开函数、
每个公开函数有用例……）+ v3 另加：约定里的 模块 / 依赖 与 plan/top.zs 一致、表名以「模块名」或「模块名_」开头（各模块的表不重名）。
确定性，不调模型。
"""
from pathlib import Path

from ..packs.dslproj import contract as C


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


def check(text, name, top, project):
    """→ 问题列表（空 = 通过）。top：top.load 的结果；project：读上游约定的项目目录。"""
    mods = {m["名"]: m["依赖"] for m in top["模块"]}
    if name not in mods:
        return [f"模块「{name}」不在 plan/top.zs 里"]
    c, probs = C.parse(text)
    ups, up_probs = upstream_of(project, name, c["依赖"] or mods[name])
    probs += up_probs
    probs += C.check(c, name, ups, list(mods))
    if sorted(c["依赖"]) != sorted(mods[name]):
        probs.append(f"约定的「依赖」是 {sorted(c['依赖']) or '无'}，plan/top.zs 里 {name} 的依赖是 {sorted(mods[name]) or '无'}，两边要一致")
    for t in c["表"]:
        if t["名"] != name and not t["名"].startswith(name + "_"):
            probs.append(f"第 {t['行']} 行：表名「{t['名']}」要以「{name}_」开头（各模块的表不重名）")
    seen = set()
    return [p for p in probs if not (p in seen or seen.add(p))]


def load(project, name):
    """通过检查后的约定 → (contract, 原文)；读不到抛 FileNotFoundError。"""
    text = path_of(project, name).read_text(encoding="utf-8")
    return C.parse(text)[0], text


def digest(c):
    """给记录用的摘要：函数 / 公开函数 / 接口 / 用例 / 表数。"""
    return {"表": len(c["表"]), "函数": len(c["函数"]), "公开函数": sum(1 for f in c["函数"] if f["公开"]),
            "接口": len(c["接口"]), "用例": len(c["用例"])}
