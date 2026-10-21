"""落实修改：修改计划固定的收尾动词（没有参数）。按依赖分层，对 ctx.pending_contracts 里登记过的模块（新增模块
登记的空串＝走 规划一份 的正常写约定全流程含复核；改约定 登记的条目＝走强制问题通道，带「上一版+条目」只跑程序
检查不复核）并行写/重写约定，消费完清空登记表 → 同步顶层依赖（含刷新目录）。
没有登记过任何模块（计划里只有 改需求/删除模块）也要跑，只做 同步顶层依赖。
最前面先验收：计划里 改文件 改过文件的模块（约定没登记要重写的），逐个跑 加载检查 + 比对约定 + 跑用例，任一不过 →
把这份计划改过的文件全部恢复成改之前的原文，终止 失败（原因带验收原文）；全过 → 模块保持「已完成」（约定没变，hash 不变），
不触发任何重做。约定要重写的模块（改约定/新增模块）不在这里验收，由后面的重做负责。
返回 {"written": [模块名…], "edited": [改过文件的模块名…]}
例如 落实修改
"""
import importlib.util
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")

ROOT = Path(__file__).resolve().parents[5]


def _load(path):
    spec = importlib.util.spec_from_file_location(f"_v3_load_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def 落实修改() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL, top as VT
    c = X.ctx()
    edited = _accept_edits(X, c)
    targets = dict(c.pending_contracts or {})
    c.pending_contracts = {}
    written = []
    if targets:
        if not c.top_path().is_file():
            X.fail("有要写/重写的约定，但还没有 plan/top.zs")
        try:
            top = PL.current_top(c)
        except ValueError as e:
            X.fail(e)
        pe = _load(ROOT / "verbs" / "common" / "defs" / "并行执行.py")
        for layer in VT.layers(top):
            names = [m for m in layer if m in targets]
            if not names:
                continue
            jobs = []
            for m in names:
                entry = targets.get(m) or ""
                args = {"种类": "约定", "模块": m, "需求": c.req, "最多": "3", "模型": "sonnet"}
                if entry:
                    args["强制问题"] = entry
                jobs.append({"脚本": "规划一份", "参数": args})
            rs = pe.并行执行(jobs, "3")
            bad = [r for r in rs if r.get("status") != "成功"]
            if bad:
                who = (bad[0].get("params") or {}).get("模块") or "?"
                X.fail(f"落实修改没通过（{','.join(names)}）：{who}：{bad[0].get('reason')}")
            written.extend(names)
    sync = _load(Path(__file__).parent / "同步顶层依赖.py")
    sync.同步顶层依赖()
    return {"written": written, "edited": edited}


def _accept_edits(X, c):
    """改过文件的模块（约定不重写的）立刻验收；不过就恢复这份计划改的全部文件并 终止 失败。→ 验收通过的模块名。"""
    from tools.dslagent.packs import dslproj as DP
    from tools.dslagent.v3 import change_plan as CP, top as VT
    pending = set(c.pending_contracts or {})
    todo = [m for m in sorted(c.file_edits) if m not in pending]
    for m in sorted(set(c.file_edits) & pending):      # 约定要重写的模块：文件改动留给重做，不单独验收
        c.file_edits.pop(m, None)
    top_text = c.top_path().read_text(encoding="utf-8") if c.top_path().is_file() else ""
    live = {m["名"] for m in VT.parse(top_text)[0]["模块"]} if top_text else set()
    bad, ok = {}, []
    for m in todo:
        if m not in live:
            continue
        r = DP.accept(c.project, {"task": f"模块 {m}"})
        c.log("验收", 模块=m, 通过=r["通过"], 说明=("改文件后验收：" + r["摘要"])[:1500])
        if r["通过"]:
            ok.append(m)
        else:
            bad[m] = r["摘要"]
    if bad:
        n = CP.restore_edits(c)
        first = sorted(bad)[0]
        X.fail(f"改文件后模块 {'、'.join(sorted(bad))} 验收没通过，已把这份计划改的 {n} 个文件全部恢复。{first}：{bad[first]}")
    for m in ok:
        c.file_edits.pop(m, None)
    return ok
