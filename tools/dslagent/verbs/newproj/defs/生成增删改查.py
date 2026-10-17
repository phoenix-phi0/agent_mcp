"""用 gen 为项目生成增删改查（queries / routes / ui）并建库。
参数 JSON：{项目目录: 默认 ".", 模板: default|full|private, 实体: [名…]（可选，缺省全部）, 覆盖: 是|否}。
先 init（不放示例）；private 先加登录注册，没有 owner 字段的实体改用 full。实体要事先写在 entities/*.entity。
返回 {ok, msg}。gen 需要 jinja2/flask，当前解释器没有就转 .venv python 子进程。
例如 设 g = 生成增删改查 {gp}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 生成增删改查(参数: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    o, err = G.parse_obj(参数)
    if err:
        return {"ok": "否", "msg": err}
    root, err = G.project_root(WORKSPACE, o.get("项目目录"))
    if err:
        return {"ok": "否", "msg": err}
    if G.is_dry():
        return {"ok": "是", "msg": "（空跑）未真的生成"}
    tpl = str(o.get("模板") or "full").strip()
    only = o.get("实体") or []
    if isinstance(only, str):
        only = [x for x in only.replace("，", ",").split(",") if x.strip()]
    only = [str(x).strip() for x in only]
    force = str(o.get("覆盖") or "否").strip() in ("是", "true", "True", "1")
    return G.run_op("generate", {"root": str(root), "tpl": tpl, "only": only, "force": force})
