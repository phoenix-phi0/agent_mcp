"""调度层账本：每次 派代理 / 派任务（带角色）调用一条 jsonl 账（run_id、call_id、parent_id、role、model、effort、
tokens in/out、cost、secs、status、reason 摘要）。子进程 / 子任务并入父账本：同一个 run_id 下按 parent_id 串起来。

落盘位置：某次运行的记录目录（v3 的 out、v2 的 out）下 agents.jsonl，一行一条、只追加。
`python -m tools.dslagent agents stats --out <目录…>` 读一个或多个目录（或文件）汇总统计，见 stats()。
"""
import json
import threading
import time
import uuid
from pathlib import Path

LEDGER_NAME = "agents.jsonl"

_counter_lock = threading.Lock()
_counters = {}


class BudgetExceeded(Exception):
    """角色预算或总预算超了（调度层按「终止 超出预期」处理）。"""


def new_run_id():
    return uuid.uuid4().hex[:12]


def new_call_id(run_id):
    """同一 run_id 下自增的调用序号，形如 <run_id>-<n>（线程安全）。"""
    with _counter_lock:
        n = _counters.get(run_id, 0) + 1
        _counters[run_id] = n
    return f"{run_id}-{n}"


class Ledger:
    """一份 jsonl 账本；可多进程 / 多线程并发追加（锁 + 只追加写）。"""

    def __init__(self, path, run_id=None):
        self.path = Path(path)
        self.run_id = run_id or new_run_id()
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, *, role, model=None, effort=None, call_id=None, parent_id=None, tokens_in=None, tokens_out=None,
               cost=0.0, secs=0.0, status="ok", reason="", **extra):
        row = {
            "run_id": self.run_id, "call_id": call_id or new_call_id(self.run_id), "parent_id": parent_id,
            "role": role, "model": model, "effort": effort, "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost": round(cost or 0.0, 6), "secs": round(secs or 0.0, 2), "status": status,
            "reason": (reason or "")[:300], "t": round(time.time(), 3),
        }
        row.update(extra)
        with self.lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def spent(self, role=None):
        """本账本（这一份文件）里已花费的美元；role 给了只算该角色的。"""
        total = 0.0
        for row in read_rows(self.path):
            if role is None or row.get("role") == role:
                total += row.get("cost") or 0.0
        return total

    def check_budget(self, role, role_budget, total_budget):
        """超预算抛 BudgetExceeded（不记账——调用方决定要不要记一条 status=over 的账）。"""
        if role_budget is not None and self.spent(role) >= role_budget:
            raise BudgetExceeded(f"角色「{role}」花费已达单角色预算 ${role_budget:.2f}")
        if total_budget is not None and self.spent() >= total_budget:
            raise BudgetExceeded(f"账本总花费已达上限 ${total_budget:.2f}")


def read_rows(path):
    """一个 jsonl 文件 / 一个目录（扫目录下所有 agents.jsonl，含子目录——子进程 / 子任务各自的账本也在这里并起来）
    → 行列表；文件不存在给 []。只认账本文件名，不扫目录下别的 jsonl（如 v3 的 v3_log.jsonl，字段结构不一样）。"""
    p = Path(path)
    files = []
    if p.is_dir():
        files = sorted(p.rglob(LEDGER_NAME))
    elif p.is_file():
        files = [p]
    rows = []
    for f in files:
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        except OSError:
            continue
    return rows


def read_all(paths):
    rows = []
    for p in paths:
        rows.extend(read_rows(p))
    return rows


def stats(rows):
    """按角色、按模型汇总：调用数、成功率、平均轮数（没有轮数字段就按 1 算）、花费、用时。"""
    def _agg(rows, key):
        out = {}
        for r in rows:
            k = r.get(key) or "（空）"
            a = out.setdefault(k, {"调用数": 0, "成功数": 0, "花费": 0.0, "用时": 0.0, "轮数合计": 0})
            a["调用数"] += 1
            if r.get("status") in ("ok", "成功"):
                a["成功数"] += 1
            a["花费"] += r.get("cost") or 0.0
            a["用时"] += r.get("secs") or 0.0
            a["轮数合计"] += r.get("num_turns") or 1
        for a in out.values():
            n = a["调用数"]
            a["成功率"] = round(a.pop("成功数") / n, 3) if n else 0.0
            a["平均轮数"] = round(a.pop("轮数合计") / n, 2) if n else 0.0
            a["花费"] = round(a["花费"], 6)
            a["用时"] = round(a["用时"], 2)
        return out
    return {"按角色": _agg(rows, "role"), "按模型": _agg(rows, "model"), "总调用数": len(rows)}
