"""旧路径的逻辑规则（规则 1 测试变化、规则 2 完成前核对的检查部分、退回规划前的回滚判断）。

规则求值、规则 3 安全约束、done_items（从任务文字抽点名产物）在 ../reason.py（v2 也用）；
规则文件 rules/测试变化.dl、rules/完成核对.dl 在 legacy/rules/（../reason.py 的 rules() 会去那里找）。
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from ..common import _verb_module
from ..reason import STATE, _src_files, infer


# ============================================================ 规则 1 测试变化

def fail_set(summary):
    s = summary or ""
    if "全部通过" in s:
        return set()
    names = {re.sub(r"\s+", " ", l.split(":", 1)[1]).strip() for l in s.splitlines() if l.startswith(("FAIL:", "ERROR:"))}
    return names or {"<测试整体没跑通>"}


def err_sig(summary):
    lines = sorted({l.strip() for l in (summary or "").splitlines()
                    if l.startswith(("FAIL:", "ERROR:")) or re.match(r"^\s*\w*(Error|Exception)\b", l)})
    return hashlib.sha1("\n".join(lines).encode()).hexdigest()[:10]


def _summary(x):
    if isinstance(x, dict):
        return x.get("summary") or ("全部通过" if x.get("passed") == "是" else "")
    return str(x or "")


def test_facts(before, after, hist="", can_undo=True):
    """before/after：跑测试 的结果（结构或摘要文本）；hist：之前各次改动后的错误签名（逗号隔开）。"""
    b, a = fail_set(_summary(before)), fail_set(_summary(after))
    passed = (after.get("passed") == "是") if isinstance(after, dict) else not a
    delta = "more" if len(a) > len(b) else "less" if len(a) < len(b) else "changed" if a != b else "same"
    sig = err_sig(_summary(after))
    prev = [x for x in str(hist or "").split(",") if x and x != "无"]
    facts = {"after_pass": passed, "delta": delta, "same_err2": bool(prev) and prev[-1] == sig and not passed,
             "can_undo": bool(can_undo)}
    extra = {"sigs": ",".join(prev + [sig]), "new_fail": sorted(a - b), "n_before": len(b), "n_after": len(a),
             "delta": delta}
    return facts, extra


# ============================================================ 规则 2 完成前核对（检查部分）

def done_unmet(root, items, snap=None):
    """逐条核对 → 未满足项（文字）列表。snap：开局 {相对路径: bytes}（unchanged 用）。"""
    root = Path(root)
    srcs = None
    out = []
    for it in items:
        k = it["kind"]
        if k == "exists" and not (root / it["path"]).is_file():
            out.append(f"文件 {it['path']} 还不存在（任务要求新建）")
        elif k == "absent" and (root / it["path"]).exists():
            out.append(f"文件 {it['path']} 还在（任务要求删除）")
        elif k == "unchanged" and snap is not None and it["path"] in snap:
            p = root / it["path"]
            if not p.is_file() or p.read_bytes() != snap[it["path"]]:
                out.append(f"文件 {it['path']} 被改动了（任务要求不许改）")
        elif k in ("def", "forbid"):
            if srcs is None:
                srcs = {r: f.read_text(encoding="utf-8", errors="ignore") for r, f in _src_files(root)}
            if k == "def":
                pat = re.compile(rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(it['name'])}\b|^\s*{re.escape(it['name'])}\s*[:=]", re.M)
                if not any(pat.search(s) for s in srcs.values()):
                    out.append(f"代码里找不到 {it['name']} 的定义（任务点名要有）")
            else:
                bad = [r for r, s in srcs.items() if r.startswith(it["dir"]) and re.search(rf"\b{re.escape(it['name'])}\b", s)]
                if bad:
                    out.append(f"{it['dir']} 下仍出现 {it['name']}（{'、'.join(bad[:3])}），任务要求不能再出现")
        elif k == "keys":
            p = root / it["path"]
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
                miss = [x for x in it["keys"] if not isinstance(j, dict) or x not in j]
            except (OSError, ValueError):
                miss = None
            if miss is None:
                out.append(f"{it['path']} 读不出 JSON 对象")
            elif miss:
                out.append(f"{it['path']} 缺键：{'、'.join(miss)}")
        elif k == "lines":
            p = root / it["path"]
            n = len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) if p.is_file() else 0
            if n > it["max"]:
                out.append(f"{it['path']} 有 {n} 行，任务要求 {it['max']} 行以内")
        elif k == "import":
            try:
                p = subprocess.run([sys.executable, "-c", f"from {it['mod']} import {it['name']}"], cwd=root,
                                   capture_output=True, text=True, timeout=30,
                                   env=_pycache_env())
                if p.returncode != 0:
                    out.append(f"from {it['mod']} import {it['name']} 失败：{(p.stderr.strip().splitlines() or [''])[-1][:120]}")
            except subprocess.TimeoutExpired:
                out.append(f"from {it['mod']} import {it['name']} 超时")
    return out


def _pycache_env():
    """子进程环境：不写 .pyc。不用 PYTHONPYCACHEPREFIX 缓存——.pyc 只按 mtime（秒）+ 大小判新旧，
    同一秒内的等长改动会读到旧字节码。"""
    return _verb_module("跑测试").clean_env(PYTHONDONTWRITEBYTECODE="1")


def done_facts(tests_pass, unmet, redo_left, confirm_left):
    return {"tests_pass": bool(tests_pass), "unmet_any": bool(unmet), "redo_left": bool(redo_left),
            "confirm_left": bool(confirm_left)}


# ============================================================ 退回规划前的回滚判断（规则 3 安全.dl 的 replan 条）

def replan_check(fail0, summary_now, dirty):
    """退回规划前：fail0 开局失败集合；summary_now 当前测试摘要；dirty 有改动。→ 推理结果（action=rollback 要先回滚）。"""
    now = fail_set(summary_now)
    reg = sorted(now - set(fail0)) if "全部通过" not in (summary_now or "") else []
    d = infer("安全", {"op": "replan", "regress": bool(reg), "dirty": bool(dirty)})
    d["regress"] = reg
    if d["action"] == "rollback":
        STATE["log"].append({"op": "退回规划", "file": "", "why": f"回归 {reg[:3]}，先回滚", "code": d["code"]})
    return d
