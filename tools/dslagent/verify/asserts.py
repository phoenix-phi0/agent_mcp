"""性质断言：纯函数，无 I/O。check(assertions, actual, before=None, exc=None) -> (ok, [失败说明])
actual: 调用返回值（字符串或已解析的 JSON 值）；before: 改前代码同输入的返回值（只有 同改前 用）；exc: 抛出的异常文本或 None。"""
import json
import re

VOCAB = ("条数", "都不含", "都含", "有含", "都匹配", "字段都在", "有序", "行号连续", "不抛异常", "同改前", "类型")


def to_items(v):
    """字符串 → 按行切（去空行）；列表照用；字典 → 单元素列表；其他标量 → 单元素列表"""
    if isinstance(v, str):
        return [x for x in v.split("\n") if x.strip() != ""]
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v]
    return [v]


def text_of(item, field=None):
    if field is not None:
        if not isinstance(item, dict) or field not in item:
            return None
        item = item[field]
    return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)


def _arg(spec):
    """都含/都不含/有含/都匹配 的参数：可为值本身，或 {"字段": f, "值": v}"""
    if isinstance(spec, dict) and "值" in spec:
        return spec.get("字段"), spec["值"]
    return None, spec


def _as_list(x):
    return x if isinstance(x, list) else [x]


def _one(kind, spec, items, actual, before, exc):
    if kind == "条数":
        if not isinstance(spec, dict) or len(spec) != 1:
            return False, "条数参数格式错"
        (op, n), = spec.items()
        if op not in ("≤", "=", "≥") or not isinstance(n, int):
            return False, "条数参数格式错"
        c = len(items)
        ok = c <= n if op == "≤" else c == n if op == "=" else c >= n
        return ok, f"条数 {c} 不满足 {op}{n}"
    if kind in ("都不含", "都含", "有含", "都匹配"):
        field, val = _arg(spec)
        texts = [text_of(i, field) for i in items]
        if any(t is None for t in texts):
            return False, f"有项缺字段 {field}"
        if kind == "都不含":
            bad = [t for t in texts if any(str(s) in t for s in _as_list(val))]
            return not bad, f"含禁用子串的项: {bad[:3]}"
        if kind == "都含":
            bad = [t for t in texts if not all(str(s) in t for s in _as_list(val))]
            return not bad, f"不含 {val!r} 的项: {bad[:3]}"
        if kind == "有含":
            miss = [s for s in _as_list(val) if not any(str(s) in t for t in texts)]
            return not miss, f"没有任何项含: {miss}"
        try:
            rx = re.compile(str(val))
        except re.error:
            return False, "正则非法"
        bad = [t for t in texts if not rx.fullmatch(t)]
        return not bad, f"不匹配 {val!r} 的项: {bad[:3]}"
    if kind == "字段都在":
        if not isinstance(spec, dict) or "字段" not in spec or not isinstance(spec.get("取值"), list):
            return False, "字段都在参数格式错"
        vals = [i.get(spec["字段"], _MISSING) if isinstance(i, dict) else _MISSING for i in items]
        bad = [v for v in vals if v is _MISSING or v not in spec["取值"]]
        return not bad, f"字段 {spec['字段']} 取值越界: {[str(b) for b in bad[:3]]}"
    if kind == "有序":
        if not isinstance(spec, dict) or spec.get("方向") not in ("升", "降") or "字段" not in spec:
            return False, "有序参数格式错"
        f = spec["字段"]
        if f == "行":
            keys = [i if isinstance(i, str) else json.dumps(i, ensure_ascii=False) for i in items]
        else:
            if any(not isinstance(i, dict) or f not in i for i in items):
                return False, f"有项缺字段 {f}"
            keys = [i[f] for i in items]
        try:
            ok = all((a <= b) if spec["方向"] == "升" else (a >= b) for a, b in zip(keys, keys[1:]))
        except TypeError:
            return False, "字段值不可比较"
        return ok, f"不是{spec['方向']}序: {keys[:6]}"
    if kind == "行号连续":
        if not isinstance(spec, dict) or not isinstance(spec.get("从"), int):
            return False, "行号连续参数格式错"
        k = spec["从"]
        for n, it in enumerate(items):
            m = re.match(r"\s*(\d+)\|", it) if isinstance(it, str) else None
            if not m or int(m.group(1)) != k + n:
                return False, f"第{n + 1}行应以 {k + n}| 开头: {str(it)[:40]!r}"
        return True, ""
    if kind == "不抛异常":
        return (exc is None) == bool(spec), f"异常: {exc}"
    if kind == "同改前":
        if before is _MISSING:
            return False, "无改前结果"
        return actual == before, f"与改前不同: 现 {str(actual)[:120]!r} 前 {str(before)[:120]!r}"
    if kind == "类型":
        t = {"str": str, "list": list, "dict": dict, "int": int}.get(spec)
        if t is None:
            return False, "类型参数非法"
        ok = isinstance(actual, t) and not (t is int and isinstance(actual, bool))
        return ok, f"类型是 {type(actual).__name__}"
    return False, f"未知断言 {kind}"


_MISSING = object()


def check(assertions, actual, before=_MISSING, exc=None):
    """assertions: 列表，每元素是 {类型名: 参数}（可含多个键）。全部满足才 ok。→ (ok, [失败说明])"""
    if isinstance(assertions, dict):
        assertions = [assertions]
    if not isinstance(assertions, list) or not assertions:
        return False, ["断言不是非空列表"]
    items = to_items(actual) if exc is None else []
    fails = []
    for a in assertions:
        if not isinstance(a, dict) or not a:
            fails.append(f"断言项格式错: {a!r}")
            continue
        for kind, spec in a.items():
            if kind not in VOCAB:
                fails.append(f"未知断言 {kind}")
                continue
            if exc is not None and kind not in ("不抛异常", "同改前"):
                fails.append(f"{kind}: 调用抛了异常 {exc}")
                continue
            ok, why = _one(kind, spec, items, actual, before, exc)
            if not ok:
                fails.append(f"{kind}{json.dumps(spec, ensure_ascii=False)}: {why}")
    return not fails, fails
