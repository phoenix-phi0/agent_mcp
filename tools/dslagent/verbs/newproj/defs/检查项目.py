"""检查项目能不能加载（不起服务）：实体校验 → 接口重复 → gen build（编译界面，写 web/）→ make_app（加载路由）。
参数 JSON：{项目目录: 默认 "."}。返回 {ok, msg}；不过时 msg 是汇总的报错文本，可直接嵌进下一轮提示词。
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 检查项目(参数: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    arg = 参数 if isinstance(参数, dict) else str(参数 or "").strip()
    if isinstance(arg, str) and arg and not arg.startswith("{"):
        arg = {"项目目录": arg}
    o, err = G.parse_obj(arg)
    if err:
        return {"ok": "否", "msg": err}
    root, err = G.project_root(WORKSPACE, o.get("项目目录"))
    if err:
        return {"ok": "否", "msg": err}
    if G.is_dry():
        return {"ok": "是", "msg": "（空跑）未真的检查"}
    if not (root / "entities").is_dir():
        return {"ok": "否", "msg": f"{o.get('项目目录') or '.'} 不像项目目录（没有 entities/）"}
    return G.run_op("check_project", {"root": str(root)})
