"""修改式重做的材料（M2）：约定变了的模块不按新建重做，而是带着「这次改了什么」改现有代码。

- plan/changes/<序号>.json：改约定 执行前登记 {"modules": {模块: {old_contract, plan_entries, issues, task, baseline, notes}}}；
  序号 = 当前最新一份修改计划的序号（跟 .zs 同号）。baseline = 修改前各用例的通过状态（含指纹，用例本身改了就不比）。
- contract_diff：旧新约定按 函数 / 接口 / 表 / 用例 分组，各列 新增 / 修改 / 删除（程序算，不调模型）。
- mod_task：改模块 给子进程的任务文本（模块名 + 「这次是修改，不是新建」+ 修改需求 + 本模块计划条目与问题 + 新旧约定差异 + 范围规则）。
- unaffected_check：没出现在差异里的函数、修改前通过的用例，修改后必须仍通过。
"""
import json
import re
from pathlib import Path

from ..packs.dslproj import contract as C
from ..packs.dslproj import project as P
from . import change_plan as CP
from . import contracts as VC

MAX_FAIL = 4000
PLAN_ENTRY_VERBS = ("改约定", "新增模块")


def plan_no(project):
    p = CP.latest_plan_path(project)
    return p.stem if p else "0"


def record_path(project, no=None):
    return CP.changes_dir(project) / f"{no or plan_no(project)}.json"


def _load(path):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("modules"), dict) else None
    except (OSError, ValueError):
        return None


def latest_record(project, module):
    """最新一份 plan/changes/*.json 里该模块的记录；没有返回 None。"""
    d = CP.changes_dir(project)
    files = sorted((f for f in (d.glob("*.json") if d.is_dir() else []) if f.stem.isdigit()), key=lambda f: int(f.stem), reverse=True)
    for f in files:
        data = _load(f)
        if data and module in data["modules"]:
            return data["modules"][module]
    return None


def _strip(o):
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k != "行"}
    if isinstance(o, list):
        return [_strip(x) for x in o]
    return o


def fp(o):
    return json.dumps(_strip(o), ensure_ascii=False, sort_keys=True)


def _decode(s):
    return (s or "").replace("\\_", " ").replace("\\n", "\n").replace("\\t", "\t")


def case_func(module, u):
    tgt = (u.get("调用") or {}).get("目标") or ""
    mod, _, fn = tgt.rpartition(".")
    return fn if (not mod or mod == module) else ""


def case_baseline(project, module):
    """修改前各用例的通过状态 {用例名: {通过, 函数, 指纹}}；约定读不到 / 建表跑不起来返回 {}。"""
    from ..packs.dslproj import cases as K
    try:
        c, _ = P.load_contract(project, module)
        r = K.run(project, module)
    except Exception:  # noqa: BLE001  基线拿不到就不做「未受影响」比较
        return {}
    if any(f["名"] == "建表" for f in r["失败"]) or (r["原因"] and not r["失败"]):
        return {}
    failed = {f["名"] for f in r["失败"]}
    return {u["名"]: {"通过": u["名"] not in failed, "函数": case_func(module, u), "指纹": fp(u)} for u in c["用例"]}


def plan_entries(ctx, module):
    """→ (本次涉及该模块的计划条目原文, 对应问题原文)；条目取最新一份修改计划里 改约定 / 新增模块 <模块> 的行。"""
    from . import issues as IS
    p = CP.latest_plan_path(ctx.project)
    if not p:
        return [], []
    items, _ = CP.parse_plan(p.read_text(encoding="utf-8"))
    entries, nums = [], []
    for it in items:
        if it["动词"] in PLAN_ENTRY_VERBS and (it["内容"].split() or [""])[0] == module:
            entries.append(_decode(f"{it['动词']} {it['内容']}"))
            nums += [n for n in it["对应问题"] if n not in nums]
    src = getattr(ctx, "issues_items", None) or []
    issues = [IS.format_issue(n, src[n - 1]) for n in nums if 1 <= n <= len(src)]
    return entries, issues


def record(ctx, module, note=None):
    """登记 / 更新该模块在本次修改计划里的记录：第一次登记时存旧约定全文和修改前的用例状态（此时约定还没重写）。"""
    path = record_path(ctx.project)
    data = _load(path) or {"plan": plan_no(ctx.project), "modules": {}}
    rec = data["modules"].get(module)
    if rec is None:
        f = VC.path_of(ctx.project, module)
        old = f.read_text(encoding="utf-8") if f.is_file() else ""
        rec = {"module": module, "old_contract": old, "task": getattr(ctx, "task", "") or "",
               "baseline": case_baseline(ctx.project, module) if old else {}, "notes": []}
        data["modules"][module] = rec
    if note:
        rec["notes"].append(_decode(note))
    rec["plan_entries"], rec["issues"] = plan_entries(ctx, module)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


# ---------------------------------------------------------------- 新旧约定差异

def _head(f):
    return C.head_text(f)


def _fn_view(f):
    return {"公开": f["公开"], "入参": f["入参"], "返回": f["返回"], "报错": [(e["码"], e["文字"]) for e in f["报错"]],
            "伪代码": [x["文字"] for x in f["伪代码"]]}


def _grp():
    return {"新增": [], "修改": [], "删除": []}


def _cmp(old, new, key, view, show, detail):
    """old/new：条目列表；key 取键，view 取比较用的内容，show 取显示文字，detail(旧,新)→改了哪些部分的文字。"""
    o, n = {key(x): x for x in old}, {key(x): x for x in new}
    g = _grp()
    for k in n:
        if k not in o:
            g["新增"].append(show(n[k]))
        elif fp(view(o[k])) != fp(view(n[k])):
            g["修改"].append(f"{show(n[k])}（{detail(o[k], n[k])}；旧：{show(o[k])}）")
    for k in o:
        if k not in n:
            g["删除"].append(show(o[k]))
    return g


def _changed_keys(a, b):
    return "、".join(k for k in a if fp(a[k]) != fp(b.get(k))) or "内容"


def _table_view(t):
    return {"学习记录": t["学习记录"], "字段": [(f["名"], f["类型"], f["说明"]) for f in t["字段"]]}


def _table_detail(a, b):
    fo, fn = {f["名"]: f for f in a["字段"]}, {f["名"]: f for f in b["字段"]}
    parts = [f"新增字段 {k}" for k in fn if k not in fo] + [f"删除字段 {k}" for k in fo if k not in fn] \
        + [f"字段 {k} 变了" for k in fn if k in fo and fp(fo[k]) != fp(fn[k])]
    if a["学习记录"] != b["学习记录"]:
        parts.append("学习记录标注变了")
    return "、".join(parts) or "内容"


def _iface_show(i):
    tag = " 公开" if i["公开"] else (f" 角色 {i['角色']}" if i["角色"] else "")
    up = f" 上传 {i['上传']['字段']}" if i.get("上传") else ""
    return f"{i['方法']} {i['路径']} -> {i['函数']}{up}{tag}"


def contract_diff(old_text, new_text):
    """→ {"函数": {新增, 修改, 删除}, "接口": …, "表": …, "用例": …, "其他": [文字]}；旧约定为空串＝全部新增。"""
    o, _ = C.parse(old_text or "")
    n, _ = C.parse(new_text or "")
    d = {
        "函数": _cmp(o["函数"], n["函数"], lambda f: f["名"], _fn_view, _head,
                    lambda a, b: _changed_keys(_fn_view(a), _fn_view(b)) + " 变了"),
        "接口": _cmp(o["接口"], n["接口"], lambda i: (i["方法"], i["路径"]), lambda i: i, _iface_show, lambda a, b: "指向的函数 / 角色 / 上传变了"),
        "表": _cmp(o["表"], n["表"], lambda t: t["名"], _table_view, lambda t: f"表 {t['名']}", _table_detail),
        "用例": _cmp(o["用例"], n["用例"], lambda u: u["名"], lambda u: u, lambda u: f"用例 {u['名']}", lambda a, b: "内容变了"),
        "其他": [],
    }
    if sorted(o["依赖"]) != sorted(n["依赖"]):
        d["其他"].append(f"依赖：{' '.join(o['依赖']) or '无'} → {' '.join(n['依赖']) or '无'}")
    if fp(o["认证"]) != fp(n["认证"]):
        d["其他"].append("认证声明变了")
    return d


def render_diff(d):
    out = []
    for name in ("函数", "接口", "表", "用例"):
        sub = [(k, d[name][k]) for k in ("新增", "修改", "删除") if d[name][k]]
        if not sub:
            continue
        out.append(f"### {name}")
        for k, rows in sub:
            out.append(f"{k}：")
            out += [f"- {r}" for r in rows]
    if d["其他"]:
        out.append("### 其他")
        out += [f"- {r}" for r in d["其他"]]
    return "\n".join(out) or "（约定文本有变，但解析后的函数 / 接口 / 表没有差异）"


def affected_funcs(old_text, new_text):
    """差异里出现的函数名：函数的新增 / 修改 / 删除 + 新增 / 修改 / 删除的接口所指的函数。"""
    o, _ = C.parse(old_text or "")
    n, _ = C.parse(new_text or "")
    of, nf = {f["名"]: f for f in o["函数"]}, {f["名"]: f for f in n["函数"]}
    out = {k for k in set(of) | set(nf) if fp(_fn_view(of[k]) if k in of else None) != fp(_fn_view(nf[k]) if k in nf else None)}
    oi, ni = {(i["方法"], i["路径"]): i for i in o["接口"]}, {(i["方法"], i["路径"]): i for i in n["接口"]}
    for k in set(oi) | set(ni):
        if fp(oi.get(k)) != fp(ni.get(k)):
            out |= {x["函数"] for x in (oi.get(k), ni.get(k)) if x}
    return out


# ---------------------------------------------------------------- 任务文本 / 验收

def explanation(project, module, rec=None):
    """取修改说明：修改需求 / 计划条目与问题 / 新旧约定差异 / 范围规则四段（不含模块行）；没有记录返回空串。"""
    rec = rec or latest_record(project, module)
    if not rec:
        return ""
    f = VC.path_of(project, module)
    new_text = f.read_text(encoding="utf-8") if f.is_file() else ""
    old = rec.get("old_contract") or ""
    task = (rec.get("task") or "").strip() or "（没有单独的修改需求文字，按下面的计划条目和问题）"
    entries = rec.get("plan_entries") or rec.get("notes") or []
    issues = rec.get("issues") or []
    plan_part = "本模块的计划条目：\n" + ("\n".join(f"- {e}" for e in entries) or "（无）") + "\n\n对应的问题：\n" + ("\n".join(issues) or "（无）")
    new_note = "" if old else "（这是新增模块：现有文件只有骨架，下面的差异就是整份约定）\n"
    return (f"## 修改需求\n{task}\n\n## 本模块的计划条目与问题\n{plan_part}\n\n## 新旧约定差异\n{new_note}{render_diff(contract_diff(old, new_text))}\n\n"
            "## 范围规则\n"
            "- 约定已经按上面的差异改好并冻结，不能改；现有文件是上一版约定下通过验收的代码。\n"
            "- 只改上面差异和计划条目涉及的部分（含相应的表结构、接口块、用例要的数据），其余代码一字不动。\n"
            "- 没出现在差异里的函数，代码和它们的用例结果都不能变：修改前通过的用例，修改后必须仍通过（验收会逐个核对）。")


def mod_task(project, module, last_fail=""):
    rec = latest_record(project, module)
    t = f"模块 {module}\n\n## 这次是修改，不是新建\n本模块已经有代码，不要重写整个模块；按下面的说明在现有代码上改。\n\n"
    t += explanation(project, module, rec) if rec else "（没有这次修改的记录，按约定核对现有代码。）"
    t += "\n"
    if (last_fail or "").strip():
        t += f"\n## 上一轮没有做成\n上一轮的结果 + 验收如下，针对这些问题改（约定不能改，范围规则照旧）：\n{last_fail.strip()[:MAX_FAIL]}\n"
    return t


def unaffected_check(project, module):
    """→ {"ok": bool, "problems": [文字], "checked": n}：差异外函数的、修改前通过的用例，修改后必须仍通过。没有记录 / 基线 → ok。"""
    rec = latest_record(project, module)
    if not rec or not rec.get("baseline"):
        return {"ok": True, "problems": [], "checked": 0}
    from ..packs.dslproj import cases as K
    try:
        c, text = P.load_contract(project, module)
    except P.ProjError as e:
        return {"ok": False, "problems": [str(e)], "checked": 0}
    affected = affected_funcs(rec.get("old_contract") or "", text)
    r = K.run(project, module)
    failed = {f["名"]: f["原因"] for f in r["失败"]}
    probs, n = [], 0
    for u in c["用例"]:
        b = rec["baseline"].get(u["名"])
        if not b or not b["通过"] or b["指纹"] != fp(u) or not b["函数"] or b["函数"] in affected:
            continue
        n += 1
        if u["名"] in failed:
            probs.append(f"未受影响的用例 {u['名']}（函数 {b['函数']} 不在差异里，修改前通过）现在不过：{failed[u['名']]}")
    return {"ok": not probs, "problems": probs, "checked": n}
