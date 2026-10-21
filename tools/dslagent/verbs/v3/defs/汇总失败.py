"""汇总失败：看 并行执行 返回的结果列表，把没成功的汇总。返回 {status: 失败|超出预期, reason: 一行一个「模块：原因」, count}，全成功 count 为 0。
有任何一项是 超出预期（预算 / 花费用完）状态就是 超出预期，否则 失败。
例如 设 s = 汇总失败 {rs}
"""
from tools.verbs import as_list

WORKSPACE = None
PACK_DIR = None


def 汇总失败(结果列表: str = "") -> dict:
    bad = [r for r in as_list(结果列表) if isinstance(r, dict) and r.get("status") != "成功"]
    lines = []
    for r in bad:
        who = (r.get("params") or {}).get("模块") or r.get("script") or "?"
        lines.append(f"{who}：{str(r.get('reason') or r.get('status')).strip()}")
    state = "超出预期" if any(r.get("status") == "超出预期" for r in bad) else "失败"
    return {"status": state, "reason": "\n".join(lines), "count": len(bad)}
