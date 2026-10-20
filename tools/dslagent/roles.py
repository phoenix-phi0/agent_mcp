"""角色登记表解析 / 校验 + 派代理 调度（dslagent 子 agent 管理，见 data/reports/agent_mgmt.md）。

tools/dslagent/roles.zs 的格式见该文件开头注释：「角色 <名>」…「结束」为一块，块内 `字段: 值`。
load_roles() 解析（格式错报 ValueError）；check_roles() 校验内容（模型串、工具/回复格式取值、超时/预算、提示词文件存在）。

派代理 dispatch_agent()：按角色取默认模型（DSLAGENT_MODELS 可按角色名覆盖，同 v2 的环境变量，见 env_role_model）、
按角色「可读范围」把入参里范围外的键挡掉（codex 角色尤其要靠这个把关——codex 本身已经在空 cwd 里跑且关了
shell_tool，见 engines.call_codex；这里再保证连 system/user 提示词文本里都不会带出范围外的材料，双重保险）、
回复不合格时按「回退模型」重试一次、记一条账到调度层账本（ledger.Ledger），按角色预算把关（超了不调模型，记
status=over）。backend 测试注入：`backend(spec, system, user, timeout) -> dict(text, cost, sec, reason, rc, …)`，
缺省走 `engines.call`。
"""
import concurrent.futures as CF
import json
import os
import re
import time
from pathlib import Path

from . import engines as EG
from . import ledger as LG

HERE = Path(__file__).resolve().parent
DEFAULT_PATH = HERE / "roles.zs"

REQUIRED = ("默认模型", "工具", "单次超时", "回复格式", "提示词文件")
TOOLS_OK = ("无", "只读", "读写")
FORMAT_OK = ("json", "zs", "text", "code")
ROLE_MODELS_ENV = "DSLAGENT_MODELS"      # 复用 v2 的环境变量；JSON 的键除了步骤名还认角色名

_BLOCK_RE = re.compile(r"^角色\s+(\S+)\s*$")
_ROLES_CACHE = None


# ------------------------------------------------------------------ 解析 / 校验


def parse_roles(text):
    """roles.zs 正文 → {名: {字段: 值}}（值都是原始字符串）。格式不对报 ValueError。"""
    roles_ = {}
    name, cur = None, None
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = _BLOCK_RE.match(s)
        if m:
            if name is not None:
                raise ValueError(f"角色「{name}」没有写「结束」就开始了新角色「{m.group(1)}」")
            name, cur = m.group(1), {}
            continue
        if s == "结束":
            if name is None:
                raise ValueError("「结束」前面没有对应的「角色」")
            if name in roles_:
                raise ValueError(f"角色「{name}」重复登记")
            roles_[name] = cur
            name, cur = None, None
            continue
        if name is None:
            raise ValueError(f"这一行不在任何「角色」块里：{s!r}")
        k, sep, v = s.partition(":")
        if not sep:
            raise ValueError(f"角色「{name}」里这一行缺「:」：{s!r}")
        cur[k.strip()] = v.strip()
    if name is not None:
        raise ValueError(f"角色「{name}」缺「结束」")
    return roles_


def load_roles(path=None):
    return parse_roles(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))


def roles():
    """缺省登记表的缓存单例（测试要用别的登记表就直接传 roles_map= 给 dispatch_agent，不要动这个缓存）。"""
    global _ROLES_CACHE
    if _ROLES_CACHE is None:
        _ROLES_CACHE = load_roles()
    return _ROLES_CACHE


def _list_field(f, key):
    return [x.strip() for x in (f.get(key) or "").split(",") if x.strip()]


def check_roles(roles_map):
    """校验内容，不合格的地方逐条返回（不抛错，调用方决定怎么处理）。"""
    problems = []
    for name, f in sorted(roles_map.items()):
        for req in REQUIRED:
            if not f.get(req):
                problems.append(f"角色「{name}」缺「{req}」")
        for field in ("默认模型", "回退模型"):
            v = f.get(field)
            if v:
                try:
                    EG.parse(v)
                except ValueError as e:
                    problems.append(f"角色「{name}」{field}不合法：{e}")
        tool = f.get("工具")
        if tool and tool not in TOOLS_OK:
            problems.append(f"角色「{name}」工具要是 {'|'.join(TOOLS_OK)}，收到 {tool!r}")
        fmt = f.get("回复格式")
        if fmt and fmt not in FORMAT_OK:
            problems.append(f"角色「{name}」回复格式要是 {'|'.join(FORMAT_OK)}，收到 {fmt!r}")
        timeout = f.get("单次超时")
        if timeout:
            try:
                ok = float(timeout) > 0
            except ValueError:
                ok = False
            if not ok:
                problems.append(f"角色「{name}」单次超时要是正数，收到 {timeout!r}")
        budget = f.get("预算")
        if budget and budget != "无":
            try:
                ok = float(budget) > 0
            except ValueError:
                ok = False
            if not ok:
                problems.append(f"角色「{name}」预算要是正数或「无」，收到 {budget!r}")
        pf = f.get("提示词文件") or ""
        if pf.endswith(".md") and ":" not in pf and not (HERE / pf).is_file():
            problems.append(f"角色「{name}」提示词文件不存在：{pf}")
    return problems


# ------------------------------------------------------------------ 模型解析（含按角色覆盖）


def env_role_model(role_name):
    """DSLAGENT_MODELS（JSON 对象，或 「角色=模型串,角色=模型串」简写）里按角色名查，没写返回 None。"""
    raw = (os.environ.get(ROLE_MODELS_ENV) or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("{"):
            val = json.loads(raw)
        elif "=" in raw.split(":", 1)[0]:
            val = dict(x.partition("=")[0::2] for x in raw.split(",") if "=" in x)
        else:
            return None
    except ValueError:
        return None
    if not isinstance(val, dict):
        return None
    v = val.get(role_name)
    return v.strip() if isinstance(v, str) and v.strip() else None


def resolve_model(role_name, field="默认模型", roles_map=None):
    """角色名 + 字段（默认模型 / 回退模型）→ engines.parse() 的结果；角色不存在报 KeyError。"""
    rm = roles_map if roles_map is not None else roles()
    if role_name not in rm:
        raise KeyError(f"角色「{role_name}」没有登记（见 {DEFAULT_PATH}）")
    spec_s = (field == "默认模型" and env_role_model(role_name)) or rm[role_name].get(field) or rm[role_name].get("默认模型")
    return EG.parse(spec_s)


# ------------------------------------------------------------------ 派代理


def _check_scope(role_name, role, inputs):
    allowed = _list_field(role, "可读范围")
    if not allowed or not inputs:
        return
    extra = [k for k in inputs if k not in allowed]
    if extra:
        raise ValueError(f"角色「{role_name}」的可读范围是 {allowed}，入参里有范围外的键：{extra}")


def _prompt_text(pf):
    """提示词文件字段 → system 提示词文本；「(…)」式的文档性说明（如 build_module 的 v2 子进程）给空字符串。"""
    pf = (pf or "").strip()
    if not pf or pf.startswith(("(", "（")) or ":" in pf:
        return ""
    p = HERE / pf
    return p.read_text(encoding="utf-8").strip() if p.is_file() else ""


def _user_text(task, inputs):
    parts = [f"【任务】\n{task.strip()}"] if (task or "").strip() else []
    for k, v in (inputs or {}).items():
        parts.append(f"【{k}】\n{v}")
    return "\n\n".join(parts)


def _reply_ok(fmt, text):
    t = (text or "").strip()
    if not t:
        return False
    if fmt != "json":
        return True
    for a_ch, b_ch in (("{", "}"), ("[", "]")):
        a, b = t.find(a_ch), t.rfind(b_ch)
        if a >= 0 and b > a:
            try:
                json.loads(t[a:b + 1])
                return True
            except ValueError:
                continue
    return False


def dispatch_agent(role_name, task="", inputs=None, fmt=None, *, out_dir, backend=None, parent_id=None,
                    ledger=None, roles_map=None, budget=None):
    """`派代理 角色 任务 入参? 格式?` 的 Python 实现。返回 {result, status, reason, role, model, cost, calls, secs}。
    status：ok（成功）/ fail（角色不存在、入参越范围、两次都没拿到合格回复）/ over（预算超了，没调模型）。"""
    rm = roles_map if roles_map is not None else roles()
    led = ledger or LG.Ledger(Path(out_dir) / LG.LEDGER_NAME)
    if role_name not in rm:
        reason = f"角色「{role_name}」没有登记"
        led.record(role=role_name, status="fail", reason=reason, parent_id=parent_id)
        return {"result": "", "status": "fail", "reason": reason, "role": role_name, "model": None,
                "cost": 0.0, "calls": 0, "secs": 0.0}
    role = rm[role_name]
    try:
        _check_scope(role_name, role, inputs)
    except ValueError as e:
        led.record(role=role_name, status="fail", reason=str(e), parent_id=parent_id)
        return {"result": "", "status": "fail", "reason": str(e), "role": role_name, "model": None,
                "cost": 0.0, "calls": 0, "secs": 0.0}

    role_budget = budget if budget is not None else (None if (role.get("预算") in (None, "", "无")) else float(role["预算"]))
    try:
        led.check_budget(role_name, role_budget, None)
    except LG.BudgetExceeded as e:
        led.record(role=role_name, status="over", reason=str(e), parent_id=parent_id)
        return {"result": "", "status": "over", "reason": str(e), "role": role_name, "model": None,
                "cost": 0.0, "calls": 0, "secs": 0.0}

    system = _prompt_text(role.get("提示词文件"))
    user = _user_text(task, inputs)
    timeout = float(role.get("单次超时") or 300)
    call = backend or (lambda spec, s, u, tmo: EG.call(spec, s, u, tmo))

    def _attempt(field):
        spec = resolve_model(role_name, field, rm)
        t0 = time.time()
        r = call(spec, system, user, timeout)
        if not isinstance(r, dict):
            r = {"text": str(r)}
        r.setdefault("sec", round(time.time() - t0, 2))
        return spec, r

    spec, r = _attempt("默认模型")
    fmt = fmt or role.get("回复格式")

    def _ok(r):
        return not r.get("reason") and r.get("rc") in (None, 0) and _reply_ok(fmt, r.get("text"))
    ok, used_fallback = _ok(r), False
    if not ok and role.get("回退模型"):
        used_fallback = True
        spec, r = _attempt("回退模型")
        ok = _ok(r)

    status, reason = ("ok", "") if ok else ("fail", r.get("reason") or "回复不合格")
    row = led.record(role=role_name, model=spec["spec"], effort=spec.get("effort"), parent_id=parent_id,
                      cost=r.get("cost") or 0.0, secs=r.get("sec") or 0.0, status=status, reason=reason,
                      num_turns=r.get("num_turns"), fallback=used_fallback)
    return {"result": r.get("text") or "", "status": status, "reason": reason, "role": role_name,
            "model": spec["spec"], "cost": r.get("cost") or 0.0, "calls": 1, "secs": r.get("sec") or 0.0,
            "call_id": row["call_id"]}


def parallel_dispatch_agents(items, *, out_dir, backend=None, parent_id=None, roles_map=None, max_workers=None):
    """`并行派代理` 的 Python 实现：items 是 [{角色, 任务?, 入参?, 格式?, parent_id?}, …]，共用一份账本；
    并发数缺省 DSLAGENT_AGENT_CONCURRENCY（没设 = 4），超了排队（线程池天然排队）。按入参原序返回结果列表。"""
    led = LG.Ledger(Path(out_dir) / LG.LEDGER_NAME)
    mw = max_workers or int(os.environ.get("DSLAGENT_AGENT_CONCURRENCY") or 4)
    with CF.ThreadPoolExecutor(max_workers=max(1, mw)) as ex:
        futs = [ex.submit(dispatch_agent, it["角色"], it.get("任务", ""), it.get("入参"), it.get("格式"),
                           out_dir=out_dir, backend=backend, parent_id=it.get("parent_id", parent_id),
                           ledger=led, roles_map=roles_map) for it in items]
        return [f.result() for f in futs]
