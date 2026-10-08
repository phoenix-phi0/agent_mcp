"""删掉项目里的一个文件（限项目内、不许删测试文件、不许删目录；安全约束 reason.check 先查：仍被引用/没等价迁移的数据文件会被拦）。返回 {ok: 是/否, msg}。
例如 设 d = 删文件 studykit/data/vocab.csv
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 删文件(文件: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import is_test_rel, resolve
    root = Path(WORKSPACE).resolve()
    p, err = resolve(root, 文件)
    if err:
        return {"ok": "否", "msg": err}
    rel = str(p.relative_to(root))
    if p == root or is_test_rel(rel):
        return {"ok": "否", "msg": f"不许删：{rel}（测试文件或项目根）"}
    if not p.exists():
        return {"ok": "是", "msg": f"{rel} 本来就不存在"}
    import 推理 as T
    why = T._R().check("删除", root, rel)
    if why:
        return {"ok": "否", "msg": why, "blocked": "是"}
    if not p.is_file():
        return {"ok": "否", "msg": f"{rel} 不是普通文件，不删"}
    p.unlink()
    return {"ok": "是", "msg": f"已删除 {rel}"}
