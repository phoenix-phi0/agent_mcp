"""dslagent 训练数据：每次运行（v2）留一条完整样本，另有补标签、补录旧实验的命令。

存放（仓库外，不提交）：DSLAGENT_DATASET（缺省 ~/dslagent_data）下 index.jsonl（每次运行一行摘要）+ runs/<run_id>.json.gz（完整样本）。
样本由「运行目录」拼出（result.json / calls.json / calls/*.prompt.txt|reply.txt / plan_tools.json / toollogs/ / plan_v*.zs / outline.md …），
实时记录（v2.run 收尾调 record）和补录旧运行（backfill）走同一个 build_sample；缺的字段留空并列进 missing。
写入失败只在 stderr 记一行警告，不影响运行结果。

    python -m tools.dslagent.dataset label <run_id> key=value …     往样本追加标签（同步更新 index）
    python -m tools.dslagent.dataset backfill [--exp DIR] [--jobs DIR] [--limit N]
    python -m tools.dslagent.dataset stats
"""
import fcntl
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = "DSLAGENT_DATASET"
DEFAULT_DIR = "~/dslagent_data"
SCHEMA = 1
PLAN_TAGS = ("plan", "plan_fix", "plan_wrapup")
ENV_KEYS = ("DSLAGENT_PLANNER", "DSLAGENT_MODELS", "DSLAGENT_PLAN_MODEL", "DSLAGENT_SUBTASK", "DSLAGENT_PACK", "DSLAGENT_VERIFY")

_SECRET_RX = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_\-]{16,}", r"Bearer\s+[A-Za-z0-9._\-]{20,}", r"gh[pousr]_[A-Za-z0-9]{20,}", r"xox[abprs]-[A-Za-z0-9\-]{10,}",
    r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_\-]{30,}")]
_KV_RX = re.compile(r"""(?i)((?:api[_-]?key|secret|token|passwd|password|authorization)["']?\s*[:=]\s*["'])([^"'\s]{8,})(["'])""")


def root():
    return Path(os.environ.get(ENV) or DEFAULT_DIR).expanduser()


def scrub(x, stat=None):
    """递归把字符串里像密钥的片段换成 [REDACTED]；stat（dict）累计次数。"""
    if isinstance(x, str):
        n = 0
        for rx in _SECRET_RX:
            x, k = rx.subn("[REDACTED]", x)
            n += k
        x, k = _KV_RX.subn(lambda m: m.group(1) + "[REDACTED]" + m.group(3), x)
        n += k
        if stat is not None and n:
            stat["n"] = stat.get("n", 0) + n
        return x
    if isinstance(x, list):
        return [scrub(i, stat) for i in x]
    if isinstance(x, dict):
        return {k: scrub(v, stat) for k, v in x.items()}
    return x


# ------------------------------------------------------------------ 读运行目录


def _jread(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _tread(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _jsonl(p):
    rows = []
    t = _tread(p)
    for line in (t or "").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def _split_prompt(text):
    """calls/NN_tag.prompt.txt（"[system]\\n…\\n\\n[user]\\n…"）→ (system, user)；格式不对 → (None, None)。"""
    if not text or not text.startswith("[system]\n"):
        return None, None
    s, sep, u = text[len("[system]\n"):].partition("\n\n[user]\n")
    return (s, u) if sep else (None, None)


def _sha(s):
    return hashlib.sha256((s or "").encode("utf-8", "replace")).hexdigest()[:16] if s is not None else None


def project_name(project, hint=""):
    """项目名：目录名；实验里统一叫 repo / p 的，按内容认（verbs+tools → agent_mcp；否则第一个带 __init__.py 的包目录名），认不出用 hint。"""
    p = Path(project) if project else None
    if p is None:
        return hint or ""
    if p.name not in ("repo", "p", "proj", "project", "work"):
        return p.name
    if p.is_dir():
        if (p / "verbs").is_dir() and (p / "tools").is_dir():
            return "agent_mcp"
        for c in sorted(p.iterdir()):
            if c.is_dir() and c.name not in ("tests", "test") and (c / "__init__.py").exists():
                return c.name
    return hint or p.name


def _git_head(before=None):
    cmd = ["git", "-C", str(ROOT), "rev-list", "-1"] + ([f"--before={int(before)}"] if before else []) + ["HEAD"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _agent_name(tag):
    try:
        from . import agents as AG
        a = AG.of_tag(tag)
        return a.name if a else None
    except Exception:  # noqa: BLE001
        return None


def _parse_reply(text):
    """子任务 / 补改 / 复核回复：能解析成 JSON 对象 → (True, 状态)，否则 (False, None)。"""
    try:
        from tools.zhipu import strip_json
        d = json.loads(strip_json(text or ""))
    except Exception:  # noqa: BLE001
        return False, None
    return (True, d.get("状态")) if isinstance(d, dict) else (False, None)


# ------------------------------------------------------------------ 规划时读码返回内容（grok 在开局快照上重取）


def capture_reads(project, plan_tools):
    """grok 自带只读工具的返回内容日志里没有：按 plan_tools 的参数在（还没改过的）项目上重取，{序号: 全文}。
    序号 = plan_tools 里的下标（字符串）。只在规划刚结束、执行还没开始时调（此时项目 = 开局快照）。取不到的不记。"""
    out = {}
    try:
        from . import wrapup as WU
        for i, c in enumerate(plan_tools or []):
            fn = WU._FN.get(c.get("工具"))
            if fn and isinstance(c.get("参数"), dict):
                s = fn(Path(project).resolve(), c["参数"])
                if s:
                    out[str(i)] = s
    except Exception as e:  # noqa: BLE001
        print(f"[dataset] 重取读码内容失败：{type(e).__name__}: {e}", file=sys.stderr)
    return out


# ------------------------------------------------------------------ 拼样本


def _trajectory(out, tag, attempt, plan_tools, reads):
    """第 attempt 次 tag 调用的读码轨迹 → ([{工具, 参数, 返回字数, 状态, 返回内容}], 缺内容的条数)。"""
    rows = _jsonl(out / "toollogs" / f"{tag}_a{attempt}.jsonl")
    traj, miss = [], 0
    for i, c in enumerate(plan_tools):
        if c.get("调用") != tag or c.get("尝试") != attempt:
            continue
        content = reads.get(str(i))
        if content is None and c.get("工具") == "dsl":
            r = rows[c["序"] - 1] if 0 < c.get("序", 0) <= len(rows) else {}
            content = r.get("reply")
        if content is None:
            miss += 1
        traj.append({"工具": c.get("工具"), "参数": c.get("参数"), "返回字数": c.get("返回字数"), "状态": c.get("状态"),
                     "返回内容": content})
    return traj, miss


def _sub_tool_log(out, tag):
    rows = _jsonl(out / "toollogs" / f"{tag}.jsonl")
    return [{"参数": r.get("code"), "状态": r.get("status"), "改了": r.get("files"), "返回字数": r.get("out_chars"),
             "返回内容": r.get("reply")} for r in rows] or None


def _model_name(c):
    return c.get("model")


def build_v2(out, task=None, project=None, reads=None, meta=None):
    """v2 运行目录 → 样本 dict（还没有 run_id / 时间 / git，由调用方补）。拼不出来的字段留 None，名字进 missing。"""
    out = Path(out)
    res = _jread(out / "result.json", {}) or {}
    calls = _jread(out / "calls.json", []) or []
    plan_tools = _jread(out / "plan_tools.json", []) or []
    reads = reads or {}
    v2 = res.get("v2") or {}
    missing = []
    sys_hash = {}
    prompts = {}
    for c in calls:
        n, tag = c.get("n"), c.get("tag")
        pt = _tread(out / "calls" / f"{n:02d}_{tag}.prompt.txt")
        rp = _tread(out / "calls" / f"{n:02d}_{tag}.reply.txt")
        s, u = _split_prompt(pt)
        prompts[n] = (s, u, rp)
    plan_user = next((prompts[c["n"]][1] for c in calls if c.get("tag") == "plan" and prompts.get(c["n"], (0, 0))[1] is not None), None)
    if task is None and plan_user:
        m = re.match(r"【任务原文】\n(.*?)(?:\n\n## |\Z)", plan_user, re.S)
        task = (m.group(1) if m else plan_user)
    if plan_user is None:
        missing.append("规划user提示词")
    # ---- 规划尝试
    attempts, rnd, seen = [], 0, {}
    checks = v2.get("检查") or []
    plan_calls = [c for c in calls if c.get("tag") in PLAN_TAGS]
    for idx, c in enumerate(plan_calls):
        tag, n = c["tag"], c["n"]
        if tag == "plan_fix":
            rnd = max(rnd, 1)
        seen[tag] = seen.get(tag, 0) + 1
        s, u, rp = prompts.get(n, (None, None, None))
        nxt = plan_calls[idx + 1]["tag"] if idx + 1 < len(plan_calls) else None
        final = nxt in (None, "plan_fix") and not (tag == "plan" and nxt == "plan_wrapup")   # 这一轮（重写序号 rnd）的最后一次调用
        traj, nmiss = ([], 0) if tag == "plan_wrapup" else _trajectory(out, tag, seen[tag], plan_tools, reads)
        zs = _tread(out / f"plan_v{rnd + 1}.zs") if final else None
        chk = checks[rnd] if final and rnd < len(checks) else None
        attempts.append({
            "调用序": n, "tag": tag, "重写轮": rnd, "agent": _agent_name(tag), "引擎": c.get("engine"), "模型": _model_name(c),
            "effort": c.get("effort"), "system哈希": _sha(s), "user": u, "回复原文": rp,
            "失败原因": c.get("failed"), "读码轨迹": traj, "读码缺内容条数": nmiss,
            "输出zs": zs, "输出zs_清洗前": _tread(out / f"plan_v{rnd + 1}.raw.txt") if final else None,
            "计划检查": ({"通过": not chk.get("问题"), "问题": chk.get("问题"), "阶段": chk.get("阶段")} if chk else None),
            "秒": c.get("sec"), "费用": c.get("cost"), "usage": c.get("usage")})
        sys_hash[tag] = _sha(s)
    if attempts and any(a["读码缺内容条数"] for a in attempts):
        missing.append("读码返回内容")
    if not attempts:
        missing.append("规划尝试")
    # ---- 子任务调用
    subs = []
    acc = v2.get("验收") or {}
    bound = v2.get("边界复核") or {}
    for c in calls:
        tag = c["tag"]
        if tag in PLAN_TAGS:
            continue
        s, u, rp = prompts.get(c["n"], (None, None, None))
        ok, st = _parse_reply(rp)
        rec = {"调用序": c["n"], "tag": tag, "agent": _agent_name(tag), "引擎": c.get("engine"), "模型": _model_name(c),
               "effort": c.get("effort"), "system哈希": _sha(s), "user": u, "回复原文": rp, "失败原因": c.get("failed"),
               "解析通过": ok, "回复状态": st, "改法套上": None, "秒": c.get("sec"), "费用": c.get("cost")}
        if tag.startswith("fix"):
            rec["改法套上"] = (acc.get("补改") or {}).get("套用")
        elif tag.startswith("bfix"):
            rec["改法套上"] = (bound.get("补改") or {}).get("套用")
        elif "_tool" in tag or c.get("tool"):
            rec["工具调用"] = _sub_tool_log(out, tag)
        subs.append(rec)
    # ---- 执行
    halted = v2.get("终止")
    ver = None
    zs_final = _tread(out / "plan.zs")
    if zs_final is not None:
        for k in range(1, 4):
            if _tread(out / f"plan_v{k}.zs") == zs_final:
                ver = k
    execution = None
    if zs_final is not None or halted is not None or v2.get("报错"):
        execution = {"执行的计划版本": ver, "脚本正常结束": bool(halted) and not v2.get("报错"), "终止": halted, "报错": v2.get("报错") or "",
                     "预算": v2.get("预算"), "清单": v2.get("清单"), "计划内测试": v2.get("计划内测试"),
                     "输出": _tread(out / "plan_out.txt"), "子任务结果": v2.get("子任务")}
    sample = {
        "模型": v2.get("models"), "规划模型": res.get("plan_model") or v2.get("规划模型"),
        "输入": {"任务": task, "规划user": plan_user, "大纲": _tread(out / "outline.md"),
                 "system": {"agent": "plan", "哈希": sys_hash.get("plan"), "说明": "全文由 git HEAD + tools/dslagent/agents/ 复原"}},
        "规划尝试": attempts, "执行": execution, "子任务调用": subs,
        "结果": {"状态": res.get("status"), "fixed": res.get("fixed"), "原因": res.get("stop"), "验收": acc or None,
                 "边界复核": bound or None, "改动文件": res.get("changed_files"), "diff": res.get("diff"),
                 "花费": res.get("cost"), "秒": res.get("seconds"), "调用数": res.get("calls"), "步骤秒": v2.get("步骤秒"),
                 "最终测试": res.get("final_test")},
        "missing": missing, "labels": {}}
    sample["_project_dir"] = res.get("project")
    if meta:
        sample.update(meta)
    return sample


def _finish_sample(s, run_id, ts, head, project, source, backfill, hint="", head_approx=False):
    proj_dir = s.pop("_project_dir", None) or project
    s0 = {"schema": SCHEMA, "run_id": run_id, "时间": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)), "ts": ts,
          "git_head": head, "git_head_近似": head_approx, "项目": project_name(proj_dir, hint), "项目目录": str(proj_dir) if proj_dir else None,
          "来源": source, "backfill": "是" if backfill else "否"}
    s0.update(s)
    st = {}
    s0 = scrub(s0, st)
    s0["脱敏处数"] = st.get("n", 0)
    return s0


def index_row(s, path):
    plans = s.get("规划尝试") or []
    rounds = {}
    for a in plans:
        if a.get("计划检查"):
            rounds[a["重写轮"]] = a["计划检查"]["通过"]
    res = s.get("结果") or {}
    inp = s.get("输入") or {}
    return {"run_id": s["run_id"], "时间": s["时间"], "项目": s.get("项目"), "任务": (inp.get("任务") or "")[:80],
            "规划模型": s.get("规划模型"), "计划尝试数": len(plans), "首轮计划过检查": rounds.get(0),
            "最终状态": res.get("状态"), "fixed": res.get("fixed"),
            "隐藏测试标签": "hidden_pass" in (s.get("labels") or {}), "backfill": s.get("backfill"), "来源": s.get("来源"),
            "文件": str(path)}


# ------------------------------------------------------------------ 读写


def _lock(d):
    d.mkdir(parents=True, exist_ok=True)
    f = open(d / ".lock", "a")
    fcntl.flock(f, fcntl.LOCK_EX)
    return f


def write(sample, base=None):
    """样本写成 runs/<run_id>.json.gz，往 index.jsonl 追加一行（已有同 run_id 的行则替换）。返回样本路径。"""
    base = Path(base) if base else root()
    p = base / "runs" / f"{sample['run_id']}.json.gz"
    lk = _lock(base)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False)
        os.replace(tmp, p)
        _index_put(base, index_row(sample, p))
    finally:
        lk.close()
    return p


def _index_put(base, row):
    ix = base / "index.jsonl"
    rows = [json.loads(x) for x in ix.read_text(encoding="utf-8").splitlines() if x.strip()] if ix.exists() else []
    hit = [i for i, r in enumerate(rows) if r.get("run_id") == row["run_id"]]
    if not hit:
        with open(ix, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return
    rows[hit[0]] = row
    tmp = ix.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, ix)


def load(run_id, base=None):
    base = Path(base) if base else root()
    p = base / "runs" / f"{run_id}.json.gz"
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def iter_samples(base=None):
    base = Path(base) if base else root()
    for line in (base / "index.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            try:
                yield row, load(row["run_id"], base)
            except (OSError, ValueError):
                continue


def record(out, project=None, task=None, reads=None, base=None):
    """v2.run 收尾调：运行目录 → 样本 → 写盘。任何失败只在 stderr 记一行警告，返回 None；绝不抛。"""
    try:
        out = Path(out)
        ts = time.time()
        run_id = time.strftime("%Y%m%d-%H%M%S", time.localtime(ts)) + "-" + hashlib.sha1(f"{out.resolve()}{ts}".encode()).hexdigest()[:6]
        s = build_v2(out, task=task, project=project, reads=reads)
        env = {k: os.environ[k] for k in ENV_KEYS if os.environ.get(k)}
        s = _finish_sample(s, run_id, ts, _git_head(), project, "live", False)
        s["dsl_options"] = env
        s["运行目录"] = str(out)
        return write(s, base)
    except Exception as e:  # noqa: BLE001
        print(f"[dataset] 写样本失败（不影响运行）：{type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return None


# ------------------------------------------------------------------ 补标签


def _val(v):
    if v in ("是", "否"):
        return v
    if v.lower() in ("true", "false"):
        return "是" if v.lower() == "true" else "否"
    return v


def label(run_id, kv, base=None):
    """往样本追加标签（key=value 列表或 dict），同步更新 index。run_id 可写唯一前缀。返回样本的 labels。"""
    base = Path(base) if base else root()
    if not (base / "runs" / f"{run_id}.json.gz").exists():
        hit = sorted(p.name[:-8] for p in (base / "runs").glob(f"{run_id}*.json.gz"))
        if len(hit) != 1:
            raise ValueError(f"找不到样本 {run_id}" if not hit else f"{run_id} 匹配多个样本：{hit[:5]}")
        run_id = hit[0]
    items = dict(kv) if isinstance(kv, dict) else {}
    if not isinstance(kv, dict):
        for x in kv:
            k, sep, v = x.partition("=")
            if not sep or not k:
                raise ValueError(f"标签要写成 key=value：{x!r}")
            items[k] = _val(v)
    lk = _lock(base)
    try:
        s = load(run_id, base)
        s.setdefault("labels", {}).update(scrub(items))
        p = base / "runs" / f"{run_id}.json.gz"
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False)
        os.replace(tmp, p)
        _index_put(base, index_row(s, p))
    finally:
        lk.close()
    return s["labels"]


# ------------------------------------------------------------------ 补录


def _legacy_task(d):
    for p in (d, d.parent, d.parent.parent):
        t = _tread(p / "task.txt")
        if t and t.strip():
            return t.strip()
    pt = _tread(d / "calls" / "01_plan.prompt.txt")
    _, u = _split_prompt(pt)
    if u:
        m = re.search(r"【任务原文】\n(.*?)(?:\n\n## |\n\n【|\Z)", u, re.S)
        if m:
            return m.group(1).strip()
    return None


def _hidden_labels(d):
    """运行目录旁的 row.json（或 ../rows.json 里同名行）里的隐藏测试结果 → 标签。"""
    for p in (d, d.parent):
        row = _jread(p / "row.json")
        if isinstance(row, dict) and "hidden" in row:
            return _row_labels(row)
    for p in (d.parent, d.parent.parent, d.parent.parent.parent):
        rows = _jread(p / "rows.json")
        if isinstance(rows, list):
            for name in (d.parent.name, d.name):
                for r in rows:
                    if isinstance(r, dict) and r.get("name") == name and "hidden" in r:
                        return _row_labels(r)
    return {}


def _row_labels(r):
    lab = {"hidden_pass": "是" if r.get("hidden") else "否", "hidden_source": "实验 row.json"}
    if r.get("hidden_tail"):
        lab["hidden_detail"] = str(r["hidden_tail"])[-600:]
    if "existing" in r:
        lab["existing_pass"] = "是" if r.get("existing") else "否"
    return lab


def build_legacy(d, task):
    """非 v2 的旧运行（plan_vN.zs 多版 / proto）→ 样本。只有任务、各版 .zs、结果；其余留空。"""
    res = _jread(d / "result.json", {}) or {}
    vers = sorted({int(m.group(1)) for f in d.iterdir() if (m := re.match(r"plan_v(\d+)\.zs$", f.name))})
    plans = []
    for k in vers or [0]:
        zs = _tread(d / (f"plan_v{k}.zs" if k else "plan.zs"))
        if zs is None:
            continue
        raw = next((t for t in (_tread(d / n) for n in (f"plan_v{k}_raw.txt", f"plan_v{k}.raw.txt", "plan.raw.txt")) if t), None)
        plans.append({"重写轮": max(k - 1, 0), "tag": "plan", "回复原文": raw, "输出zs": zs, "输出": _tread(d / f"plan_v{k}_out.txt"),
                      "读码轨迹": [], "计划检查": None})
    calls = _jread(d / "calls.json", [])
    subs = [{"tag": c.get("purpose") or c.get("tag"), "模型": c.get("model_used") or c.get("model"), "回复原文": c.get("reply"),
             "秒": c.get("sec"), "费用": c.get("cost")} for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []
    fixed = res.get("fixed")
    s = {"模型": None, "规划模型": (calls[0].get("model") if isinstance(calls, list) and calls and isinstance(calls[0], dict) else None),
         "输入": {"任务": task, "规划user": None, "大纲": None, "system": None},
         "规划尝试": plans, "执行": {"版本数": res.get("versions"), "引擎": res.get("engine_used")}, "子任务调用": subs,
         "结果": {"状态": "成功" if fixed else "失败", "fixed": fixed, "原因": res.get("stop"), "验收": None, "边界复核": None,
                  "改动文件": res.get("changed_files"), "diff": res.get("diff"), "花费": res.get("cost"), "秒": res.get("seconds"),
                  "调用数": res.get("calls"), "最终测试": res.get("final_test")},
         "missing": ["规划user提示词", "system哈希", "读码轨迹", "计划检查结果", "子任务提示词", "验收明细"], "labels": {}, "_project_dir": res.get("project")}
    return s


def _mtime(p):
    try:
        return p.stat().st_mtime
    except OSError:
        return time.time()


def backfill_dir(d, base=None, source="exp", meta=None, hint=""):
    """一个运行目录 → 补录成样本；已补录过（同目录 run_id 固定）返回 "exists"，拼不出返回 "skip:原因"，成功返回 run_id。"""
    d = Path(d)
    res = _jread(d / "result.json")
    if not isinstance(res, dict):
        return "skip:没有 result.json"
    run_id = "bf-" + hashlib.sha1(str(d.resolve()).encode()).hexdigest()[:12]
    base = Path(base) if base else root()
    if (base / "runs" / f"{run_id}.json.gz").exists():
        return "exists"
    is_v2 = res.get("planner") == "v2" and (d / "calls.json").exists()
    task = _legacy_task(d)
    if is_v2:
        s = build_v2(d, task=task)
        task = (s.get("输入") or {}).get("任务")
        if not (s["规划尝试"] and any(a.get("输出zs") is not None or a.get("回复原文") for a in s["规划尝试"])):
            return "skip:没有任何一版 .zs"
        kind = "v2"
    else:
        if not task:
            return "skip:找不到任务原文"
        s = build_legacy(d, task)
        if not s["规划尝试"]:
            return "skip:没有任何一版 .zs"
        kind = "proto" if (d / "log.jsonl").exists() else "legacy"
    if not task:
        return "skip:找不到任务原文"
    s["输入"]["任务"] = task
    if not (s.get("结果") or {}).get("状态"):
        return "skip:没有结果"
    s["labels"] = _hidden_labels(d)
    ts = _mtime(d / "result.json")
    s["missing"] = sorted(set(s["missing"]))
    s["backfill_来源目录"] = str(d)
    if meta:
        s.update(meta)
    s = _finish_sample(s, run_id, ts, _git_head(ts), res.get("project"), f"{source}:{kind}", True, hint, head_approx=True)
    write(s, base)
    return run_id


def find_exp_dirs(exp):
    """实验目录下所有「像 v2 / 旧规划运行」的运行目录（有 result.json 且旁边有 plan*.zs / plan*.raw.txt；跳过项目副本 repo 和 v2 的外层包装）。"""
    exp = Path(exp)
    found = []
    for dp, dn, fn in os.walk(exp):
        for skip in ("repo", ".venv", "node_modules", ".git", "state", "tmp", "dry", "plan_subs", "boundary"):
            if skip in dn:
                dn.remove(skip)
        if "result.json" in fn and any(re.match(r"plan.*\.(zs|raw\.txt)$", f) for f in fn):
            found.append(Path(dp))
    return sorted(found)


def find_job_dirs(jobs):
    """~/.claude-batch/jobs/*/job.json 里 engine=dsl 且 dsl_dir 有运行记录的任务 → [(运行目录, 任务原文, dsl_options, 任务项)]。"""
    out = []
    for jf in sorted(Path(jobs).glob("*/job.json")):
        job = _jread(jf, {}) or {}
        for t in job.get("tasks") or []:
            if isinstance(t, dict) and t.get("engine") == "dsl" and t.get("dsl_dir") and Path(t["dsl_dir"]).is_dir():
                out.append((Path(t["dsl_dir"]), t.get("prompt"), t.get("dsl_options"), t))
    return out


def backfill(exp=None, jobs=None, base=None, limit=None):
    exp = Path(exp or "~/dslagent_exp").expanduser()
    jobs = Path(jobs or "~/.claude-batch/jobs").expanduser()
    stat = {"新增": 0, "已有": 0, "跳过": {}, "按来源": {}}

    def note(r, kind):
        if r == "exists":
            stat["已有"] += 1
        elif r.startswith("skip:"):
            stat["跳过"][r[5:]] = stat["跳过"].get(r[5:], 0) + 1
        else:
            stat["新增"] += 1
            stat["按来源"][kind] = stat["按来源"].get(kind, 0) + 1

    done = set()
    for d, prompt, opts, t in find_job_dirs(jobs):
        if limit and stat["新增"] >= limit:
            break
        done.add(d.resolve())
        meta = {"dsl_options": opts or {}, "批量任务": str(d.parent.name)}
        res = _jread(d / "result.json")
        if isinstance(res, dict) and res.get("planner") == "v2":
            note(backfill_dir(d, base, "cbatch", meta), "cbatch")
        else:
            note("skip:cbatch 任务不是 v2 运行（模板 / 旧规划）", "cbatch")
    for d in find_exp_dirs(exp):
        if limit and stat["新增"] >= limit:
            break
        if d.resolve() in done:
            continue
        note(backfill_dir(d, base, "exp", None, hint=d.relative_to(exp).parts[0]), "exp")
    return stat


def stats(base=None):
    from collections import Counter
    base = Path(base) if base else root()
    rows = [json.loads(x) for x in (base / "index.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    out = {"总数": len(rows)}
    for k in ("来源", "项目", "规划模型", "首轮计划过检查", "最终状态", "隐藏测试标签", "backfill"):
        out[k] = dict(Counter(str(r.get(k)) for r in rows).most_common(12))
    return out


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] not in ("label", "backfill", "stats"):
        print(__doc__)
        return 2
    cmd, rest = a[0], a[1:]
    if cmd == "label":
        if len(rest) < 2:
            print("用法：label <run_id> key=value …")
            return 2
        try:
            print(json.dumps(label(rest[0], rest[1:]), ensure_ascii=False, indent=1))
        except (ValueError, OSError) as e:
            print(f"失败：{e}", file=sys.stderr)
            return 1
        return 0
    if cmd == "stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=1))
        return 0
    opt = {}
    i = 0
    while i < len(rest):
        if rest[i] in ("--exp", "--jobs", "--limit") and i + 1 < len(rest):
            opt[rest[i][2:]] = rest[i + 1]
            i += 2
        else:
            i += 1
    if "limit" in opt:
        opt["limit"] = int(opt["limit"])
    print(json.dumps(backfill(**opt), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
