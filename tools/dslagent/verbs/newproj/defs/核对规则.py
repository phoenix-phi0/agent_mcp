"""解析「核对规则」那一步模型的回复。参数：回复文本（可带围栏）、功能清单项（含「规则」列表）。
回复格式：JSON 列表（或 {结果:[…]}），每条 {序号, 规则, 实现: 是|否, 依据}。按序号对回规则（序号缺失时按规则原文对）；
清单里的规则没出现在回复里也算「否」。返回 {ok, parsed, unimplemented, unimplemented_list, count}：ok=是 表示没有未实现的规则；
回复不是合法 JSON 时 parsed=否、ok=是（核对不了不拿它当理由重写，由模板记一笔）；unimplemented 是可直接嵌进重写提示词的文本，unimplemented_list 是原规则文本的列表。
规则列表为空直接 ok=是（count 0）。
"""
import json
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
FENCE = re.compile(r"^```[^\n]*\n(.*?)\n?```[ \t]*$", re.S)


def _items(text):
    t = str(text or "").strip()
    m = FENCE.match(t)
    if m:
        t = m.group(1).strip()
    try:
        v = json.loads(t)
    except ValueError:
        i, j = t.find("["), t.rfind("]")
        if i < 0 or j <= i:
            return None
        try:
            v = json.loads(t[i:j + 1])
        except ValueError:
            return None
    if isinstance(v, dict):
        v = next((v[k] for k in ("结果", "核对", "规则", "items") if isinstance(v.get(k), list)), None)
    return v if isinstance(v, list) and all(isinstance(x, dict) for x in v) else None


def 核对规则(回复: str = "", 功能=None) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    if G.is_dry():
        return {"ok": "是", "parsed": "是", "unimplemented": "", "unimplemented_list": [], "count": 0}
    f = 功能 if isinstance(功能, dict) else (G.parse_obj(功能)[0] or {})
    rules = [r for r in (f.get("规则") or []) if isinstance(r, str) and r.strip()]
    if not rules:
        return {"ok": "是", "parsed": "是", "unimplemented": "", "unimplemented_list": [], "count": 0}
    items = _items(回复)
    if items is None:
        return {"ok": "是", "parsed": "否", "unimplemented": "", "unimplemented_list": [], "count": len(rules)}
    got = {}
    for it in items:
        idx = it.get("序号")
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = next((i + 1 for i, r in enumerate(rules) if str(it.get("规则") or "").strip() == r.strip()), None)
        if idx is not None and 1 <= idx <= len(rules):
            got[idx] = it
    bad, bad_rules = [], []
    for i, r in enumerate(rules, 1):
        it = got.get(i)
        if it is None:
            bad.append(f"「{r}」（核对回复里没有这一条）")
            bad_rules.append(r)
        elif str(it.get("实现") or "").strip() != "是":
            why = str(it.get("依据") or "").strip()
            bad.append(f"「{r}」" + (f"（{why}）" if why else ""))
            bad_rules.append(r)
    return {"ok": "否" if bad else "是", "parsed": "是", "unimplemented": "；".join(bad), "unimplemented_list": bad_rules, "count": len(rules)}
