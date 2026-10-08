"""改动前给项目非测试文件留底（存进状态目录），配合 撤回 用。返回 {id}。
例如 设 bk = 留底
"""
import json
import sys
import time
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 留底() -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import state_dir
    import 推理 as T
    R = T._R()
    root = Path(WORKSPACE).resolve()
    snap = {k: v.decode("latin-1") for k, v in R.all_files(root).items() if not R._is_test(k)}
    bid = f"bk{int(time.time() * 1000) % 10**9}"
    d = state_dir(WORKSPACE) / "backup"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{bid}.json").write_text(json.dumps(snap), encoding="utf-8")
    return {"id": bid}
