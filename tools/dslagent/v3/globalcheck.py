"""全局程序检查：全部约定都通过各自的检查之后跑一次，不调模型。查两类跨模块重复：
同一「方法 + 路径」在两个模块的「## 接口」里都定义、同一张表名在两个模块的「## 表」里都定义
（约定检查已经要求表名以「模块名_」开头，正常不该撞，这里兜底防拼错 / 抄错）。

check(project, top) -> {"条数": n, "按模块": {模块: [问题…]}, "摘要": 摘要文本}；没问题 条数=0。
"""
from collections import defaultdict

from ..packs.dslproj import contract as C
from . import contracts as VC


def check(project, top):
    by_route, by_table = defaultdict(set), defaultdict(set)
    for m in top["模块"]:
        name = m["名"]
        f = VC.path_of(project, name)
        if not f.is_file():
            continue
        c, probs = C.parse(f.read_text(encoding="utf-8"))
        if probs:
            continue
        for i in c["接口"]:
            by_route[(i["方法"], i["路径"])].add(name)
        for t in c["表"]:
            by_table[t["名"]].add(name)
    per_module = defaultdict(list)
    for (method, path), mods in sorted(by_route.items()):
        if len(mods) > 1:
            msg = f"接口「{method} {path}」在模块 {'、'.join(sorted(mods))} 里都定义了，一个方法+路径只能属于一个模块"
            for m in mods:
                per_module[m].append(msg)
    for table, mods in sorted(by_table.items()):
        if len(mods) > 1:
            msg = f"表「{table}」在模块 {'、'.join(sorted(mods))} 里都定义了，一张表只能属于一个模块"
            for m in mods:
                per_module[m].append(msg)
    total = sum(len(v) for v in per_module.values())
    brief = "；".join(f"{m}：{'; '.join(v)}" for m, v in sorted(per_module.items()))
    return {"条数": total, "按模块": dict(per_module), "摘要": brief}
