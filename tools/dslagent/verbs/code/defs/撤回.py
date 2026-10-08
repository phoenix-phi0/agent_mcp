"""把项目非测试文件恢复到 留底 时的样子（留底后新建的删掉）。返回 {ok: 是/否, msg}。
例如 设 u = 撤回 {bk.id}
"""
import json
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 撤回(编号: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import state_dir
    import 推理 as T
    R = T._R()
    p = state_dir(WORKSPACE) / "backup" / f"{str(编号).strip()}.json"
    if not p.is_file():
        return {"ok": "否", "msg": f"没有留底 {编号}"}
    snap = {k: v.encode("latin-1") for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    R.restore(Path(WORKSPACE).resolve(), snap)
    return {"ok": "是", "msg": f"已撤回到留底 {编号}"}
