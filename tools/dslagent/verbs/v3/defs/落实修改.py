"""落实修改：修改计划固定的收尾动词（没有参数）。按依赖分层，对 ctx.pending_contracts 里登记过的模块（新增模块
登记的空串＝走 规划一份 的正常写约定全流程含复核；改约定 登记的条目＝走强制问题通道，带「上一版+条目」只跑程序
检查不复核）并行写/重写约定，消费完清空登记表 → 同步顶层依赖（含刷新目录）。
没有登记过任何模块（计划里只有 改需求/删除模块）也要跑，只做 同步顶层依赖。
返回 {"written": [模块名…]}
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
    return {"written": written}
