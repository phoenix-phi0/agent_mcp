"""用逻辑规则（dslagent/rules/<名>.dl，infer.Datalog 求值）决定执行中的小分支。返回 {action, reason, code, …}。
规则名可写成 规则=测试变化.dl 或 测试变化。
  测试变化 前 后 史      前/后是 跑测试 的结果，史是之前的错误签名（逗号隔开，首次传 无）→ action: done|undo_reask|escalate|keep|reask，
                         另给 sigs（更新后的错误史）、new_fail（新出现的失败）、delta
  完成核对               按任务原文（笔记里的 task）核对点名产物 → action: done|redo|confirm|not_done，unmet（未满足项）
例如 设 d = 推理 规则=测试变化.dl {t0} {t} {sigs}
"""
import importlib.util
import json
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def _R():
    m = sys.modules.get("dslagent_reason")
    if m is None:
        p = Path(__file__).resolve().parents[3] / "reason.py"
        spec = importlib.util.spec_from_file_location("dslagent_reason", p)
        m = importlib.util.module_from_spec(spec)
        sys.modules["dslagent_reason"] = m
        spec.loader.exec_module(m)
    return m


def _val(x):
    if isinstance(x, (dict, list)):
        return x
    try:
        return json.loads(x)
    except (TypeError, ValueError):
        return x


def 推理(规则: str = "", 甲: str = "", 乙: str = "", 丙: str = "") -> dict:
    R = _R()
    name = str(规则).split("=", 1)[-1].strip()
    name = name[:-3] if name.endswith(".dl") else name
    if name == "测试变化":
        facts, extra = R.test_facts(_val(甲), _val(乙), str(丙 or ""))
        d = R.infer(name, facts)
        d.update(sigs=extra["sigs"], new_fail="；".join(extra["new_fail"]) or "无", delta=extra["delta"],
                 n_before=extra["n_before"], n_after=extra["n_after"])
        return d
    if name == "完成核对":
        root = Path(WORKSPACE).resolve()
        snap = R.STATE.get("snap") or R.all_files(root)
        items = R.done_items(R.STATE.get("task") or str(甲 or ""), snap)
        unmet = R.done_unmet(root, items, snap)
        d = R.infer(name, R.done_facts(str(乙 or "是") == "是", unmet, str(丙 or "否") == "是", False))
        d.update(unmet="；".join(unmet) or "无", n_items=len(items))
        return d
    return {"action": "", "reason": f"没有规则 {name}（可用：测试变化、完成核对；安全约束由写删动词自动调用）"}
