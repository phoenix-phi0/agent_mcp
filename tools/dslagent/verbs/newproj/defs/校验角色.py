"""检查功能的 zs 里，清单标了「角色」的接口是否写了对应的「角色 <代号>」。参数：功能清单项（含 名、接口:[{路径, 动作, 角色}]）。
在 routes/<功能>.zs 和 routes/<功能>_*.zs 里按路径找「接口 POST /路径 …」行，行里要有「角色 <代号>」（或「只许 <中文名>」，中文名按教师/学生/管理员对回代号）。
返回 {ok, msg}：msg 点名接口和应加的写法，可直接嵌进重写提示词。清单里没有标角色的接口不查。
"""
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
HEAD = re.compile(r"^接口\s+\S+\s+(\S+)(.*)$", re.M)
ROLE = re.compile(r"(?:^|\s)(?:角色|只许)\s+(\S+)")
CN = {"教师": "teacher", "老师": "teacher", "学生": "student", "管理员": "admin"}


def 校验角色(功能=None) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    if G.is_dry():
        return {"ok": "是", "msg": ""}
    f = 功能 if isinstance(功能, dict) else (G.parse_obj(功能)[0] or {})
    need = [(a.get("路径"), str(a.get("角色")).strip()) for a in (f.get("接口") or [])
            if isinstance(a, dict) and str(a.get("角色") or "").strip()]
    if not need:
        return {"ok": "是", "msg": ""}
    root = Path(WORKSPACE).resolve()
    name = str(f.get("名") or "")
    files = [p for p in [root / "routes" / f"{name}.zs"] + sorted((root / "routes").glob(f"{name}_*.zs")) if p.is_file()]
    have = {}
    for p in files:
        for m in HEAD.finditer(p.read_text(encoding="utf-8", errors="replace")):
            r = ROLE.search(m.group(2))
            have[m.group(1)] = CN.get(r.group(1), r.group(1)) if r else ""
    errs = []
    for path, role in need:
        if path not in have:
            errs.append(f"清单里的接口 {path}（角色 {role}）在 routes/{name}*.zs 里没找到")
        elif have[path] != role:
            errs.append(f"接口 {path} 清单标了角色 {role}，但接口行没写「角色 {role}」（写法：接口 POST {path} 动作 xxx 角色 {role}）")
    return {"ok": "否" if errs else "是", "msg": "；".join(errs)}
