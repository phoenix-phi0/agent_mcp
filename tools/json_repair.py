# -*- coding: utf-8 -*-
"""模型 JSON 回复的确定性修复，问JSON 和 派任务 共用。只修这些，不猜内容：

  括号    解析不了、括号不配平且只差末尾若干个 } / ]：扫描（忽略字符串里的括号）后补齐再解析
  旧键    子任务的顶层字段是英文 result/status/reason/thought；模型回了旧中文键
          （结果/状态/原因/思路，含嵌套在「结果」对象里面的）一律换成英文键，不覆盖已有的英文键
  上提    子任务回复里「status」「reason」被写进了「result」对象里面（顶层没有 status）：提到顶层；「thought」同理

修不了的原样交回，由调用方走原有的校验和重问。
"""
import json

_CLOSE = {"{": "}", "[": "]"}


def close_tail(text: str):
    """text 只差末尾若干个 } / ] 时返回要补的那串，别的情况（已平衡、不在末尾、括号错配）返回 None。"""
    stack, in_str, esc = [], False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in _CLOSE:
            stack.append(_CLOSE[ch])
        elif ch in "}]":
            if not stack or stack.pop() != ch:
                return None
    if in_str or not stack:
        return None
    return "".join(reversed(stack))


def parse(text: str):
    """text（已抠出 JSON 部分）→ (data, repaired, err)。
    data 为 None 表示解析不了，err 是 json 的报错原文；repaired 是 "" 或 "补括号"。"""
    try:
        return json.loads(text), "", ""
    except json.JSONDecodeError as e:
        err = str(e)
    tail = close_tail(text.rstrip())
    if tail:
        try:
            return json.loads(text.rstrip() + tail), "补括号", err
        except json.JSONDecodeError:
            pass
    return None, "", err


_KEY_MAP = {"结果": "result", "状态": "status", "原因": "reason", "思路": "thought"}


def _norm_dict(d):
    """一层字典的键：旧中文键（结果/状态/原因/思路）换成新英文键，有英文键的不覆盖、中文键照样去掉。
    返回 (换名后的字典, 是否换过)。"""
    if not isinstance(d, dict):
        return d, False
    changed = False
    out = dict(d)
    for cn, en in _KEY_MAP.items():
        if cn in out:
            if en not in out:
                out[en] = out.pop(cn)
            else:
                del out[cn]
            changed = True
    return out, changed


def normalize_keys(data):
    """模型回复兼容旧键：顶层的 结果/状态/原因/思路 换成 result/status/reason/thought；
    「结果」/「result」对象内部混进的 状态/原因/思路（模型嵌套错位）同样换名，供 lift_status/lift_thought 识别。
    返回 (data, 是否换过)。"""
    if not isinstance(data, dict):
        return data, False
    data, changed = _norm_dict(data)
    if isinstance(data.get("result"), dict):
        inner, inner_changed = _norm_dict(data["result"])
        if inner_changed:
            data = {**data, "result": inner}
            changed = True
    return data, changed


def lift_status(data):
    """{result:{…,status,reason}} 顶层没有 status → 把 status/reason 提到顶层。返回 (data, 是否提了)。"""
    if not isinstance(data, dict) or "status" in data or not isinstance(data.get("result"), dict) \
            or "status" not in data["result"]:
        return data, False
    inner = dict(data["result"])
    out = dict(data)
    out["status"] = inner.pop("status")
    if "reason" in inner and "reason" not in out:
        out["reason"] = inner.pop("reason")
    out["result"] = inner
    return out, True


def lift_thought(data):
    """{result:{…,thought}} 顶层没有 thought → 把 thought 提到顶层（放最前面）。返回 (data, 是否提了)。"""
    if not isinstance(data, dict) or "thought" in data or not isinstance(data.get("result"), dict) \
            or "thought" not in data["result"]:
        return data, False
    inner = dict(data["result"])
    return {"thought": inner.pop("thought"), **data, "result": inner}, True


def fill_shell(data):
    """顶层直接是 {edits:[…]}（没有 result / status）→ 补成 {result:{edits,…}, status:成功, reason:""}；thought 留在顶层。
    只补外壳，不动、不放宽 edits 本身（edits 的校验仍在后面）。返回 (data, 是否补了)。"""
    if not isinstance(data, dict) or "result" in data or "status" in data or not isinstance(data.get("edits"), list):
        return data, False
    inner = {k: v for k, v in data.items() if k not in ("thought", "reason")}
    out = {"thought": data["thought"]} if "thought" in data else {}
    return {**out, "result": inner, "status": "成功", "reason": ""}, True


def parse_reply(text: str, lift: bool = True):
    """模型回复原文 → (data, repaired, err)：抠出 JSON 部分（去围栏 / 取最外层括号）→ parse（补括号）→
    normalize_keys（旧中文键转英文）→ lift_status（lift=True 才做）。
    子任务（json / tool）、补改（fix / bfix）、问JSON 都走这一个；repaired 是 ""、"补括号"、"旧键转换"、
    "状态上提" 或它们按出现顺序拼起来（"补括号+旧键转换+状态上提" 这种）。
    问JSON 的回复格式是用户自己声明的，不做旧键转换 / 状态上提（lift=False）。"""
    from .zhipu import strip_json
    data, repaired, err = parse(strip_json(text or ""))
    if lift:
        data, normalized = normalize_keys(data)
        if normalized:
            repaired = (repaired + "+" if repaired else "") + "旧键转换"
        data, lifted = lift_status(data)
        if lifted:
            repaired = (repaired + "+" if repaired else "") + "状态上提"
        data, lifted_t = lift_thought(data)
        if lifted_t:
            repaired = (repaired + "+" if repaired else "") + "思路上提"
    return data, repaired, err
