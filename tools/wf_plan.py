"""编排清单的成本计算。"""
from tools.dsl_core import to_text


def cost_summary(items, budget, allowed, cost_of) -> dict:
    rows, cache = [], {}
    for i, item in enumerate(items, 1):
        role = item.get("agent")
        if role not in cache:
            cache[role] = cost_of(role)
        rows.append({"index": i, "agent": role, "cost": cache[role],
                     "content": to_text(item.get("content", ""))})
    total = round(sum(r["cost"] for r in rows), 3)
    outside = sorted({r["agent"] for r in rows} - set(allowed)) if allowed else []
    summary = {"total": total, "budget": budget, "tasks": rows,
               "status": "超出" if (budget is not None and total > budget) or outside else "未超出"}
    if outside:
        summary["not_in_roster"] = outside
    return summary
