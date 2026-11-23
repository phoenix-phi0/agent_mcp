"""项目的接口约定文件 work/<项目>/CONTRACT.json：读、写、按改动方案合并。

文件内容：
  {"version": 1, "source": 谁写的, "updated": 时间, "run": 哪次运行,
   "architecture": architecture 格式（模块、provides/uses、数据模型、集成场景、全项目约定）,
   "contract_notes": 架构师的裁决（[{module, decisions}]）,
   "history": [每次写入一条：时间、来源、改了什么],
   "warnings": 最近一次合并时查出来要人看的（uses 对不上、模块顺序、没交代的模块）}

整项目流程、重构流程跑完写一份（存约定）；改项目流程读它、按改动方案合并后写回（合并约定）。
合并只做确定的事：按 order 排模块，改动的模块整份替换、新模块加进来、写了删除的去掉；
别的（数据模型、集成场景、目录、全项目约定）方案里给了就用方案的。合并后查一遍 uses 和对方 provides 对不对得上。
"""
import copy
import json
import time
from pathlib import Path

from tools.dsl_core import DSLError

VERSION = 1
PLAN_ONLY = ("status", "change")          # 改动方案里模块多出来的字段，写进约定时去掉
REPLACEABLE = ("layout", "data_model", "integration", "conventions", "risks", "open_questions")


def safe_path(workdir, rel):
    root = Path(workdir).resolve()
    path = (root / str(rel).strip()).resolve()
    if root not in path.parents or path.suffix != ".json":
        raise DSLError(f"约定文件要在工作目录里、以 .json 结尾：{rel}")
    return path


def read(path):
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise DSLError(f"约定文件不是合法的 JSON：{path.name}（{e}）") from e
    if not isinstance(data, dict) or not isinstance(data.get("architecture"), dict):
        raise DSLError(f"约定文件里没有 architecture：{path.name}")
    return data


def _modules(arch, what):
    mods = arch.get("modules") if isinstance(arch, dict) else None
    if not isinstance(mods, list) or not mods or not all(isinstance(m, dict) and m.get("name") for m in mods):
        raise DSLError(f"{what}：architecture.modules 要是非空的模块列表，每个模块有 name")
    return mods


def check_uses(mods):
    """uses 里引用的接口要在前面某个模块的 provides 里，签名一字不差。返回问题清单。"""
    out = []
    seen = {}
    for m in mods:
        for u in m.get("uses") or []:
            if not isinstance(u, dict):
                # 早期的架构格式 uses 只写名字：没有签名可对，提醒改项目前补全
                out.append(f"{m['name']} 的 uses 只写了名字（{str(u)[:40]}），没写签名：旧格式，改这个模块前要补全")
                continue
            ref = str(u.get("ref", ""))
            owner, _, iface = ref.partition(".")
            if owner not in seen:
                out.append(f"{m['name']} 用到 {ref}：模块 {owner} 不存在或排在后面")
                continue
            prov = {p.get("name"): p for p in seen[owner].get("provides") or []}
            if iface not in prov:
                out.append(f"{m['name']} 用到 {ref}：{owner} 的 provides 里没有 {iface}")
            elif str(prov[iface].get("signature", "")).strip() != str(u.get("signature", "")).strip():
                out.append(f"{m['name']} 用到 {ref}：签名和 {owner} 的 provides 不一致")
        seen[m["name"]] = m
    return out


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def save(path, arch, notes, source, run=None):
    """整份写入（整项目流程、重构流程）：以前的 history 留着，再记一条。"""
    _modules(arch, "存约定")
    arch = copy.deepcopy(arch)
    arch.pop("changes", None)
    old = read(path)
    entry = {"at": _now(), "source": source, "summary": "整份写入", "run": run or None}
    data = {"version": VERSION, "source": source, "updated": entry["at"], "run": run or None,
            "architecture": arch, "contract_notes": copy.deepcopy(notes or []),
            "history": (old.get("history") or []) + [entry], "warnings": check_uses(arch["modules"])}
    _write(path, data)
    return data


def merge(path, plan, notes, source, run=None):
    """按改动方案（change_plan 格式）改约定再写回。方案和约定对不上的硬伤直接报错，不写文件。"""
    old = read(path)
    if not old:
        raise DSLError(f"没有可合并的约定：{path.name} 不存在（先用整项目流程或重构流程生成一份）")
    if not isinstance(plan, dict):
        raise DSLError("合并约定：改动方案要是对象")
    base = old["architecture"]
    old_mods = {m["name"]: m for m in _modules(base, "原约定")}
    plan_mods = {}
    for m in plan.get("modules") or []:
        if not isinstance(m, dict) or not m.get("name"):
            raise DSLError("合并约定：改动方案的 modules 里每项要有 name")
        if m["name"] in plan_mods:
            raise DSLError(f"合并约定：改动方案里模块 {m['name']} 写了两次")
        plan_mods[m["name"]] = m
    removed = {str(r.get("name")): r for r in plan.get("removed") or [] if isinstance(r, dict)}
    order = [str(x) for x in plan.get("order") or []]
    errors = []
    if len(set(order)) != len(order):
        errors.append("order 里有重复的模块名")
    for name, m in plan_mods.items():
        if name not in order:
            errors.append(f"改动的模块 {name} 不在 order 里")
        if m.get("status") == "新增" and name in old_mods:
            errors.append(f"{name} 标成新增，但原约定里已经有这个模块")
        if m.get("status") == "修改" and name not in old_mods:
            errors.append(f"{name} 标成修改，但原约定里没有这个模块")
    for name in order:
        if name not in old_mods and name not in plan_mods:
            errors.append(f"order 里的 {name} 既不在原约定里，也不在改动的模块里")
        if name in removed:
            errors.append(f"{name} 写了删除，又在 order 里")
    for name in removed:
        if name not in old_mods:
            errors.append(f"要删除的 {name} 原约定里没有")
    if errors:
        raise DSLError("合并约定：改动方案和原约定对不上，没有写文件：" + "；".join(errors))

    warnings = []
    mods = []
    for name in order:
        if name in plan_mods:
            m = {k: v for k, v in copy.deepcopy(plan_mods[name]).items() if k not in PLAN_ONLY}
        else:
            m = copy.deepcopy(old_mods[name])
        mods.append(m)
    for name in old_mods:
        if name not in order and name not in removed:
            warnings.append(f"原约定的模块 {name} 不在 order 里也没写删除：放在最后保留")
            mods.append(copy.deepcopy(old_mods[name]))
    warnings += check_uses(mods)

    arch = copy.deepcopy(base)
    arch.pop("changes", None)
    arch["modules"] = mods
    if plan.get("project_summary"):
        arch["summary"] = plan["project_summary"]
    for key in REPLACEABLE:
        if key in plan:
            arch[key] = copy.deepcopy(plan[key])
    entry = {"at": _now(), "source": source, "summary": str(plan.get("summary", "")),
             "changed": [n for n in order if n in plan_mods and plan_mods[n].get("status") != "新增"],
             "added": [n for n in order if plan_mods.get(n, {}).get("status") == "新增"],
             "removed": sorted(removed), "run": run or None}
    data = {"version": VERSION, "source": source, "updated": entry["at"], "run": run or None,
            "architecture": arch,
            "contract_notes": copy.deepcopy(notes if notes is not None else old.get("contract_notes") or []),
            "history": (old.get("history") or []) + [entry], "warnings": warnings}
    _write(path, data)
    return data
