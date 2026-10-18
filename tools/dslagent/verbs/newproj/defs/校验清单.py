"""校验「功能清单」（split 模板第一步模型的输出）。参数：清单文本（可带围栏）或已解析的对象；返回
{ok, errors, 模板, 功能, 数量, 调用上限}。errors 用「；」连接，可直接嵌进重写提示词。
规则：功能名唯一且为英文 snake；sql 名以「<功能名>_」为前缀（或就等于功能名）且全局唯一；接口路径以 / 开头、全局唯一；
动作名全局唯一（英文 snake）；模板只能 default / full / private；功能数 ≤ NEWPROJ_SPLIT_MAX_FEATURES（默认 12）。
每个功能的「规则」（需求里必须实现的业务规则）要是文本列表（缺省补 []，可为空）。
顶层可选「角色」（英文 snake 文本列表）、接口项可带「角色」（必须在顶层「角色」里）；有角色模板必须是 private；
第 2 个参数（需求原文，可选）里出现登录 / 账号 / 角色 / 权限 / 老师才能… 这类说法时，清单必须给「角色」。
功能可以为空（纯增删改查）。调用上限 = 4 + 功能数×10（sql 2 + zs 2+规则重写 2 + 核对 2 + ui 2），给模板 预算 用。
"""
import json
import os
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
FENCE = re.compile(r"^```[^\n]*\n(.*?)\n?```[ \t]*$", re.S)
MAX_FEATURES_ENV = "NEWPROJ_SPLIT_MAX_FEATURES"
DEFAULT_MAX = 12
TEMPLATES = ("default", "full", "private")


def max_features():
    try:
        return max(1, int(os.environ.get(MAX_FEATURES_ENV) or DEFAULT_MAX))
    except ValueError:
        return DEFAULT_MAX


CALLS_PER_FEATURE = 10
# 需求里提到登录 / 账号 / 角色 / 权限、或「只有老师能…」这类按身份限制的说法 → 清单必须给角色
ROLE_HINT = re.compile(r"登录|登陆|账号|帐号|账户|角色|权限|(?:仅|只|只有|只许|只能|仅限)(?:由)?(?:老师|教师|学生|管理员)|(?:老师|教师|管理员)(?:才能|才可以|专属)|(?:老师|教师|学生|管理员)(?:端|账号)")


def calls_cap(n):
    return 4 + CALLS_PER_FEATURE * n


def _parse(x):
    if isinstance(x, dict):
        return x, ""
    t = str(x or "").strip()
    m = FENCE.match(t)
    if m:
        t = m.group(1).strip()
    if not t:
        return None, "清单为空"
    try:
        v = json.loads(t)
    except ValueError as e:
        return None, f"清单不是合法 JSON：{e}"
    return (v, "") if isinstance(v, dict) else (None, "清单要是一个 JSON 对象 {模板, 功能}")


def _strs(v, what, errs):
    if v in (None, ""):
        return []
    if not isinstance(v, list) or not all(isinstance(i, str) for i in v):
        errs.append(f"{what} 要是文本列表")
        return []
    return v


def 校验清单(清单: str = "", 需求: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    if G.is_dry():       # 空跑：给一个占位功能，让循环体整个走一遍
        feats = [{"名": "demo", "说明": "占位", "实体": [], "sql": [{"名": "demo_list", "参数": [], "说明": ""}],
                  "接口": [{"路径": "/demo/list2", "动作": "demo_list2", "说明": ""}], "界面": ["demo页"], "规则": []}]
        return {"ok": "是", "errors": "", "模板": "full", "功能": feats, "数量": 1, "调用上限": calls_cap(1), "角色": []}
    obj, err = _parse(清单)
    if err:
        return {"ok": "否", "errors": err, "模板": "", "功能": [], "数量": 0, "调用上限": calls_cap(0), "角色": []}
    errs = []
    tpl = str(obj.get("模板") or "").strip()
    if tpl not in TEMPLATES:
        errs.append(f"模板「{tpl}」不对，只能是 default / full / private")
    feats = obj.get("功能")
    if feats is None:
        feats = []
    if not isinstance(feats, list) or not all(isinstance(f, dict) for f in feats):
        return {"ok": "否", "errors": "「功能」要是对象列表", "模板": tpl, "功能": [], "数量": 0, "调用上限": calls_cap(0), "角色": []}
    roles = _strs(obj.get("角色"), "顶层「角色」", errs)
    for r in roles:
        if not SNAKE.match(r):
            errs.append(f"角色「{r}」要是英文小写 snake（如 teacher）")
    if len(set(roles)) != len(roles):
        errs.append("「角色」里有重复项")
    if roles and tpl != "private":
        errs.append("清单给了「角色」，模板必须是 private（登录注册靠 private 生成）")
    if not roles and str(需求 or "").strip() and ROLE_HINT.search(str(需求)):
        errs.append("需求里提到了登录 / 账号 / 角色 / 权限，清单顶层必须给「角色」（如 [\"teacher\",\"student\"]，注册默认角色放最后）并选 private 模板；只有一种登录用户就写一个角色")
    if len(feats) > max_features():
        errs.append(f"功能太多（{len(feats)} 个，上限 {max_features()}），请合并相近的功能")
    names, sqls, paths, acts = set(), set(), set(), set()
    for f in feats:       # 缺的列表补 []，模板里「等于 []」就能跳过空步骤
        for k in ("实体", "sql", "接口", "界面", "规则"):
            if f.get(k) in (None, ""):
                f[k] = []
    for i, f in enumerate(feats, 1):
        n = f.get("名")
        if not isinstance(n, str) or not SNAKE.match(n):
            errs.append(f"第 {i} 个功能名「{n}」要是英文小写 snake（如 book_stats）")
            n = None
        elif n in names:
            errs.append(f"功能名「{n}」重复")
        else:
            names.add(n)
        tag = n or f"第{i}个功能"
        _strs(f.get("实体"), f"{tag} 的实体", errs)
        _strs(f.get("界面"), f"{tag} 的界面", errs)
        for r in _strs(f.get("规则"), f"{tag} 的规则", errs):
            if not r.strip():
                errs.append(f"{tag} 的规则里有空字符串")
        for q in f.get("sql") or []:
            qn = q.get("名") if isinstance(q, dict) else None
            if not isinstance(qn, str) or not SNAKE.match(qn):
                errs.append(f"{tag} 的 sql 名「{qn}」要是英文小写 snake")
                continue
            if n and qn != n and not qn.startswith(n + "_"):
                errs.append(f"sql 名「{qn}」要以功能名「{n}_」开头")
            if qn in sqls:
                errs.append(f"sql 名「{qn}」重复")
            sqls.add(qn)
            _strs(q.get("参数"), f"sql「{qn}」的参数", errs)
        for a in f.get("接口") or []:
            p = a.get("路径") if isinstance(a, dict) else None
            an = a.get("动作") if isinstance(a, dict) else None
            if not isinstance(p, str) or not p.startswith("/"):
                errs.append(f"{tag} 的接口路径「{p}」要以 / 开头")
            elif p in paths:
                errs.append(f"接口路径「{p}」重复")
            else:
                paths.add(p)
            ar = a.get("角色") if isinstance(a, dict) else None
            if ar not in (None, "") and (not isinstance(ar, str) or ar not in roles):
                errs.append(f"接口「{p}」的角色「{ar}」不在顶层「角色」{roles or '（没给）'} 里")
            if not isinstance(an, str) or not SNAKE.match(an):
                errs.append(f"{tag} 的动作名「{an}」要是英文小写 snake")
            elif an in acts:
                errs.append(f"动作名「{an}」重复")
            else:
                acts.add(an)
    return {"ok": "否" if errs else "是", "errors": "；".join(errs), "模板": tpl, "功能": feats if not errs else [],
            "数量": len(feats), "调用上限": calls_cap(len(feats)), "角色": roles if not errs else [],
            "角色模板": "private" if roles and not errs else ""}
