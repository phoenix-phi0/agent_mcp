"""核查.zs 用的 Python 部分（动词的壳在 verbs/v3/defs）：

  merge(...)  存问题清单：把各路结果（程序 / 回归 / 冒烟 / 规划）并成一份、去重、丢掉不合格项

模型子任务（派任务）的回复固定是 {result, status, reason}（见 tools/dsl_task.py），核查类的 result 是 {found: 是否, items: 列表}。
"""

KEYS = ("issue", "modules", "basis")


# ------------------------------------------------------------------ 存问题清单

def _clean_one(it):
    """一条结果项 → (规整后的条目, 问题文本)；合格问题文本为空。"""
    if not isinstance(it, dict):
        return None, "不是对象"
    miss = [k for k in KEYS if k not in it or it[k] is None]
    if miss:
        return None, "缺字段 " + "、".join(miss)
    mods = it["modules"]
    if isinstance(mods, list):
        mods = "、".join(str(x) for x in mods)
    out = {"issue": str(it["issue"]).strip(), "modules": str(mods).strip(),
           "basis": str(it["basis"]).strip()}
    if not out["issue"] or not out["basis"] or not out["modules"]:
        return None, "issue / modules / basis 不能为空"
    return out, ""


def _as_list(v):
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def _program_items(v, label, kept, dropped):
    """程序类结果（{count, items, …} 或条目列表）：逐项规整。"""
    if v in (None, ""):
        return
    items = v.get("items") if isinstance(v, dict) else v
    for it in _as_list(items):
        out, why = _clean_one(it)
        if out:
            kept.append(out)
        else:
            dropped.append({"source": label, "reason": why, "raw": it})


def _model_items(r, label, module, kept, dropped, unchecked):
    """子任务的返回 {result, status, reason}：status 非成功 → unchecked；否则 found / items 一致才收。"""
    if not isinstance(r, dict) or r.get("status") != "成功":
        r = r if isinstance(r, dict) else {}
        reason = str(r.get("reason") or r.get("status") or "没有返回")
        if r.get("问题"):                       # 回复格式不合格时 派任务 把具体哪儿不对放在「问题」里
            reason += f"（{r['问题']}）"
        unchecked.append({"module": module, "reason": reason[:500]})
        return
    res = r.get("result")
    if not isinstance(res, dict) or "found" not in res or not isinstance(res.get("items"), list):
        dropped.append({"source": label, "reason": "result 缺 found / items", "raw": res})
        return
    found = res["found"] in (True, "是", "true", "True")
    if found != bool(res["items"]):
        dropped.append({"source": label, "reason": f"found={'是' if found else '否'} 但 items {'非空' if res['items'] else '为空'}，前后矛盾",
                        "raw": res})
        return
    for it in res["items"]:
        out, why = _clean_one(it)
        if out:
            kept.append(out)
        else:
            dropped.append({"source": label, "reason": why, "raw": it})


def merge(程序=None, 回归=None, 冒烟=None, 规划=None):
    """→ (items, unchecked, dropped)。按（issue, modules）去重，顺序：程序、回归、冒烟、规划。"""
    kept, dropped, unchecked = [], [], []
    for v, label in ((程序, "程序"), (回归, "回归"), (冒烟, "冒烟")):
        _program_items(v, label, kept, dropped)
    if 规划 not in (None, ""):
        _model_items(规划, "规划", "规划层", kept, dropped, unchecked)
    seen, items = set(), []
    for it in kept:
        key = (it["issue"], it["modules"])
        if key not in seen:
            seen.add(key)
            items.append(it)
    return items, unchecked, dropped
