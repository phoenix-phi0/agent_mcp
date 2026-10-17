"""校验实体文本（tools.entity.parse + validate）。返回 {ok, errors, 实体数}，errors 用「；」连接。
可选第 2、3 个参数：模板、需求原文——模板是 private 而需求里没出现登录 / 账号 / 只看自己这类说法就不过。
例如 设 v = 校验实体 {ent.实体文本} {ent.模板} {req}
"""
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
PRIVATE_HINT = re.compile(r"登录|登陆|账号|帐号|账户|注册|只看自己|只能看到自己|自己的(?:数据|记录)|仅自己|私人|私有")


def 校验实体(文本: str = "", 模板: str = "", 需求: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    if G.is_dry():
        return {"ok": "是", "errors": "", "实体数": 1}
    text = str(文本 or "")
    if not text.strip():
        return {"ok": "否", "errors": "实体文本为空", "实体数": 0}
    if str(模板 or "").strip() and str(模板).strip() not in ("default", "full", "private"):
        return {"ok": "否", "errors": f"模板「{模板}」不对，只能是 default / full / private", "实体数": 0}
    try:
        from tools.entity import parse, validate
        ents = parse(text)
        errs = list(validate(ents))
    except Exception as e:  # noqa: BLE001  解析错误转成 errors
        return {"ok": "否", "errors": str(e) or type(e).__name__, "实体数": 0}
    if not ents:
        errs.append("没有解析出任何实体")
    if str(模板).strip() == "private" and str(需求 or "").strip() and not PRIVATE_HINT.search(需求):
        errs.append("需求里没有出现登录、账号、只看自己的数据这类说法，不许选 private 模板，改选 full 或 default")
    return {"ok": "否" if errs else "是", "errors": "；".join(errs), "实体数": len(ents)}
