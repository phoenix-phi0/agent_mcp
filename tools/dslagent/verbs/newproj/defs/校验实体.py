"""校验实体文本（tools.entity.parse + validate）。返回 {ok, errors, 实体数}，errors 用「；」连接。
可选第 4 个参数：功能清单已定的模板，是 private 而实体步选了别的就不过（清单有角色，登录注册靠 private）。
可选第 2、3 个参数：模板、需求原文——模板是 private 而需求里没出现登录 / 账号 / 只看自己这类说法就不过。
例如 设 v = 校验实体 {ent.实体文本} {ent.模板} {req}
"""
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
PRIVATE_HINT = re.compile(r"登录|登陆|账号|帐号|账户|注册|只看自己|只能看到自己|自己的(?:数据|记录)|仅自己|私人|私有")


def 校验实体(文本: str = "", 模板: str = "", 需求: str = "", 清单模板: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _tplset
    import _gen as G
    if G.is_dry():
        return {"ok": "是", "errors": "", "entity_count": 1}
    text = str(文本 or "")
    if not text.strip():
        return {"ok": "否", "errors": "实体文本为空", "entity_count": 0}
    if str(模板 or "").strip() and str(模板).strip() not in _tplset.names():
        return {"ok": "否", "errors": f"模板「{模板}」不对，只能是 {_tplset.menu()}", "entity_count": 0}
    try:
        from tools.entity import parse, validate
        ents = parse(text)
        errs = list(validate(ents))
    except Exception as e:  # noqa: BLE001  解析错误转成 errors
        return {"ok": "否", "errors": str(e) or type(e).__name__, "entity_count": 0}
    if not ents:
        errs.append("没有解析出任何实体")
    if str(模板).strip() == "private" and str(需求 or "").strip() and not PRIVATE_HINT.search(需求):
        errs.append("需求里没有出现登录、账号、只看自己的数据这类说法，不许选 private 模板，改选 full 或 default")
    if str(清单模板 or "").strip() == "private" and str(模板).strip() != "private":
        errs.append("功能清单定了 private 模板（有登录 / 角色），模板这一行要写 private，且要登录隔离的实体带 owner 字段")
    return {"ok": "否" if errs else "是", "errors": "；".join(errs), "entity_count": len(ents)}
