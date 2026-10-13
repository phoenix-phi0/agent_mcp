# -*- coding: utf-8 -*-
"""模型 JSON 回复的确定性修复，问JSON 和 派任务 共用。只修两种，不猜内容：

  括号    解析不了、括号不配平且只差末尾若干个 } / ]：扫描（忽略字符串里的括号）后补齐再解析
  上提    子任务回复里「状态」「原因」被写进了「结果」对象里面（顶层没有 状态）：提到顶层

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


def lift_status(data):
    """{结果:{…,状态,原因}} 顶层没有 状态 → 把 状态/原因 提到顶层。返回 (data, 是否提了)。"""
    if not isinstance(data, dict) or "状态" in data or not isinstance(data.get("结果"), dict) \
            or "状态" not in data["结果"]:
        return data, False
    inner = dict(data["结果"])
    out = dict(data)
    out["状态"] = inner.pop("状态")
    if "原因" in inner and "原因" not in out:
        out["原因"] = inner.pop("原因")
    out["结果"] = inner
    return out, True


def parse_reply(text: str, lift: bool = True):
    """模型回复原文 → (data, repaired, err)：抠出 JSON 部分（去围栏 / 取最外层括号）→ parse（补括号）→ lift_status（lift=True 才做）。
    子任务（json / tool）、补改（fix / bfix）、问JSON 都走这一个；repaired 是 ""、"补括号"、"状态上提" 或 "补括号+状态上提"。
    问JSON 的回复格式是用户自己声明的，不做状态上提（lift=False）。"""
    from .zhipu import strip_json
    data, repaired, err = parse(strip_json(text or ""))
    if lift:
        data, lifted = lift_status(data)
        if lifted:
            repaired = (repaired + "+" if repaired else "") + "状态上提"
    return data, repaired, err
