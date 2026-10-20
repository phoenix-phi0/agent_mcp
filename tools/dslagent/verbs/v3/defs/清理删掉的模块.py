"""清理删掉的模块：contracts/ 或 plan/state.json 里有、plan/top.zs 里没有的模块 → 删它的
contracts/entities/services/routes/queries/tests 文件（routes/queries/tests 按「最长模块名前缀」归属，
归属时把 top.zs 里还在的模块也算进去，不会误删还活着的模块的文件）与 state.json 里的记录。
别的模块的约定要是还依赖着被删的模块，约定检查（contracts.check 的「还没有约定文件」）会报错，不在这里管。
顶层存盘后、约定阶段开头调（规划到通过.zs）。
返回 {"删了": [模块名…]}。
例如 清理删掉的模块
"""
import json
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def _owner(stem, names, sep=""):
    prefix = [m for m in names if stem.startswith(m + sep)]
    return max(prefix, key=len, default=None)


def 清理删掉的模块() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import top as VT
    c = X.ctx()
    project = c.project
    if not c.top_path().is_file():
        return {"删了": []}          # 没有 plan/top.zs（不该发生：顶层阶段先于这里跑）不动，不拿空模块表当「全删」
    top, probs = VT.parse(c.top_path().read_text(encoding="utf-8"))
    if probs:
        return {"删了": []}          # top.zs 还没通过检查，不动（规划到通过 的 顶层 阶段会先拦）
    live = {m["名"] for m in top["模块"]}
    cdir = project / "contracts"
    contract_mods = {f.stem for f in cdir.glob("*.md")} if cdir.is_dir() else set()
    state = c.load_state()
    state_mods = set(state.get("模块", {}).keys())
    candidates = sorted((contract_mods | state_mods) - live)
    if not candidates:
        return {"删了": []}
    all_names = live | contract_mods | state_mods
    removed, deleted = [], []
    for name in candidates:
        files = []
        for rel in (f"contracts/{name}.md", f"entities/{name}.entity", f"services/{name}.zs"):
            f = project / rel
            if f.is_file():
                f.unlink()
                files.append(rel)
        rd = project / "routes"
        for rf in sorted(rd.glob("*.zs")) if rd.is_dir() else []:
            if _owner(rf.stem, all_names) == name:
                rf.unlink()
                files.append(str(rf.relative_to(project)))
        qd = project / "queries"
        for qf in sorted(qd.glob("*_*.sql")) if qd.is_dir() else []:
            if _owner(qf.stem, all_names, sep="_") == name:
                qf.unlink()
                files.append(str(qf.relative_to(project)))
        td = project / "tests"
        for tf in sorted(td.glob("*_*")) if td.is_dir() else []:
            if tf.is_file() and _owner(tf.name, all_names, sep="_") == name:
                tf.unlink()
                files.append(str(tf.relative_to(project)))
        if name in state.get("模块", {}):
            del state["模块"][name]
            files.append("plan/state.json#" + name)
        if files:
            deleted.append(name)
            removed.append({"模块": name, "文件": files})
    if deleted:
        c.state_path().parent.mkdir(parents=True, exist_ok=True)
        c.state_path().write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        c.log("规划", 种类="约定", 事件="清理删掉的模块", 删了=removed)
    return {"删了": deleted}
