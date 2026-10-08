"""执行器：模板 → 规划（最多 MAX_PLAN 版）→ 交回调用方决定要不要 Claude 兜底。

    from tools.dslagent import runner
    r = runner.run(project, task, out_dir)          # 在 project 里直接改文件
    r["fixed"], r["engine_used"], r["handoff"]       # handoff：没修好时给兜底 claude 的交接说明

两条路径（开局跑测试定，result.json 的 kind 记 bugfix / task）：
  - 修 bug（开局有失败测试）：下面 1–5，plan6/plan7 验证过的 P6 生产路径。
  - 任务（开局测试全过）：不套模板，模型规划最多 MAX_PLAN 版（系统提示同修 bug 的规划，用户提示换成「完成任务」的说法，
    文件清单含 .json/.csv/.md 等），一版算完成＝测试全过、测试文件没动、脚本没报错、结论「修好」，再过完成前核对；
    写/删/改模块名动词（verbs/code）都过安全约束；退回规划前回归已坏先回滚到开局快照。engine_used=plan_task。
流程（修 bug）：
  1. 开局跑测试（test_cmd 缺省按项目探测 pytest / unittest）。测试命令没跑到测试 → 不动手，交回。
  2. 第 1 版套固定模板（template.py，不调模型规划）：定位.zs（预读 + 搜索 + 可直接给改法）→ 读改测.zs。
  3. 没修好 → 模型写 .zs 计划（prompts.py；系统提示缓存），白名单 + 假模型空跑检查，错了带行号回去重写（≤2 次），
     执行；最多 MAX_PLAN 版。每版之间项目里的修改保留。
  4. 每次模型调用走常驻 claude 进程（pool.py；首 token 超过 DSLAGENT_HEDGE_SEC 秒、或出首 token 后流停住
     DSLAGENT_STALL_SEC 秒，就换个会话对冲重发），
     记进 calls.json（用途、耗时、费用、token、是否对冲）。
  5. 执行中的小分支交给逻辑规则（reason.py + rules/*.dl，动词 推理；DSLAGENT_RULES=0 关）：读改测里每次改完看测试变化
     （变多撤回 / 同错两次升级）、改文件前查安全约束、退回规划前回归已坏先回滚、宣布修好前核对任务点名的产物
     （不满足再做一轮，仍不满足问模型确认一次）。
预算：总模型调用 ≤ MAX_CALLS（含规划、重写、计划内的问）；墙钟超过 wall 不再开新一版。

**要在独立进程里跑**（python -m tools.dslagent run …，cbatch 就是这么调的）：它把 llm_router 的
ClaudeCLIClient._run_local 换成常驻进程池、设 DSLAGENT_STATE 等环境变量，都是进程级的。
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parents[1]
LIB = PKG / "lib"
VERBS = PKG / "verbs"
DEFS = VERBS / "code" / "defs"
MODEL = "cli:claude/sonnet"
MAX_PLAN, MAX_CALLS, MAX_FIX = 2, 15, 2
WALL = 500
INJECT_FAIL = "用包 common text code\n打印 结论：没修好 （测试注入：模板这一版不做任何事）"

# auto 判定：提示词里像「有失败的测试 / 报错栈」的说法
FAIL_SIGNAL = re.compile(r"Traceback \(most recent call last\)|失败的测试|测试[^。\n]{0,12}(失败|没过|不通过|报错)|"
                         r"failing tests?|tests? (?:fail|failed|failing)\b|^FAILED\b|^FAIL:|^ERROR: test|AssertionError",
                         re.I | re.M)


def _defs():
    if str(DEFS) not in sys.path:
        sys.path.insert(0, str(DEFS))


def _verb_module(name):
    """直接加载 code 包里的一个动词文件（runner 自己也要跑测试、列文件）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"_dslagent_{name}", DEFS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------ 目录、测试命令

def tmp_dir():
    """临时目录（claude 子进程的 TMPDIR、进程池的空工作目录）。DSLAGENT_TMP > ~/.cache/dslagent/tmp。
    默认不用 /tmp：WSL 上 /tmp 是 1.9G 的内存盘，满过两次，claude 写不了临时文件就 ENOSPC 秒退。"""
    d = Path(os.environ.get("DSLAGENT_TMP") or Path.home() / ".cache" / "dslagent" / "tmp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _python():
    """PATH 上有 python3 就写 python3（不写绝对路径：兜底 claude 的 Bash(python3 …*) 放行规则才对得上）。"""
    return "python3" if shutil.which("python3") else sys.executable


def detect_test_cmd(project):
    """按项目探测测试命令：有 pytest 配置（pytest.ini / conftest.py / pyproject 的 [tool.pytest] / setup.cfg、tox.ini 的
    [pytest] 段）且 python3 装了 pytest → pytest（--tb=native 让摘要能认出调用位置）；否则有 tests/ → unittest discover -s tests；
    顶层有 test_*.py → unittest discover；都没有 → None。"""
    import subprocess
    p = Path(project)
    py = _python()
    cfg = (p / "pytest.ini").is_file() or (p / "conftest.py").is_file() or (p / "tests" / "conftest.py").is_file()
    for name, marks in (("pyproject.toml", ("[tool.pytest",)), ("setup.cfg", ("[tool:pytest]",)), ("tox.ini", ("[pytest]",))):
        f = p / name
        if f.is_file():
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                txt = ""
            cfg = cfg or any(m in txt for m in marks)
    if cfg:
        try:
            ok = subprocess.run([py, "-c", "import pytest"], capture_output=True, timeout=30).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if ok:
            return f"{py} -m pytest -q --tb=native -p no:cacheprovider"
    if (p / "tests").is_dir():
        return f"{py} -m unittest discover -s tests"
    if any(p.glob("test_*.py")):
        return f"{py} -m unittest discover"
    return None


def test_state(project, test_cmd, timeout=120):
    """跑一次测试：{runnable, failing, rc, summary}。runnable＝确实跑到了测试（unittest「Ran N tests」N>0，
    或 pytest 的 N passed/failed/error、收集出错）；failing＝能跑且没全过。"""
    _defs()
    m = _verb_module("跑测试")
    rc, text = m.run_raw(Path(project).resolve(), test_cmd, timeout)
    ran = re.search(r"^Ran (\d+) tests?", text, re.M)
    runnable = bool(ran and int(ran.group(1)) > 0) or \
        bool(re.search(r"\b\d+ (passed|failed|errors?)\b|errors? during collection", text))
    return {"runnable": runnable, "failing": runnable and rc not in (0, None), "rc": rc,
            "summary": m.summarize(Path(project).resolve(), rc, text)["summary"]}


def decide_auto(prompt, project, test_cmd=None, timeout=120):
    """engine=auto 的判定，返回 {engine: dsl|claude, kind?: bugfix|task, reason, test_cmd, initial?, items?}。规则：
    1. 没给 project → claude（dsl 会直接改 project 里的文件，不替调用方猜目录）；
    2. 测试命令（给的或探测的）没有、跑不起来、或没跑到任何测试 → claude（dsl 两条路径都靠测试验收）；
    3. 初始有失败：给了 test_cmd 或提示词里有失败测试 / Traceback 的说法 → dsl 修 bug；没有 → claude（不像修 bug 的任务）；
    4. 初始全过：提示词里有失败测试 / Traceback 的说法 → claude（说有 bug 但测试没覆盖到，不是 dsl 能验收的）；
       否则用完成前核对的抽取器（reason.done_items）从任务文本里抽明确产物（新建/删除的路径、函数/类名、JSON 键、
       行数约束、import 等），抽到 ≥1 个 → dsl 任务路径；一个都抽不到 → claude（开放式任务）。"""
    if not project:
        return {"engine": "claude", "reason": "没给 project", "test_cmd": test_cmd}
    hit = FAIL_SIGNAL.search(prompt or "")
    cmd = test_cmd or detect_test_cmd(project)
    if not cmd:
        return {"engine": "claude", "reason": "项目里探测不到测试（没有 tests/、test_*.py 或 pytest 配置），dsl 没法验收",
                "test_cmd": None}
    st = test_state(project, cmd, timeout)
    if not st["runnable"]:
        return {"engine": "claude", "reason": f"测试命令没跑到任何测试（{cmd}）：{st['summary'][:200]}",
                "test_cmd": cmd, "initial": st}
    if st["failing"]:
        if test_cmd or hit:
            why = "给了 test_cmd" if test_cmd else f"提示词里有「{hit.group(0)[:30]}」"
            return {"engine": "dsl", "kind": "bugfix", "reason": f"{why}，测试能跑且初始有失败 → 修 bug 路径",
                    "test_cmd": cmd, "initial": st}
        return {"engine": "claude", "reason": "初始有失败测试，但没给 test_cmd、提示词里也没有失败测试/Traceback，不像修 bug 任务",
                "test_cmd": cmd, "initial": st}
    if hit:
        return {"engine": "claude", "reason": f"提示词里有「{hit.group(0)[:30]}」，但初始测试全过（测试没覆盖到这个问题）",
                "test_cmd": cmd, "initial": st}
    from . import reason as R
    items = R.done_items(prompt, R.all_files(project))
    if not items:
        return {"engine": "claude", "reason": "初始测试全过，任务文本里抽不出明确产物（路径/标识符/JSON 键/行数约束等），按开放式任务交 claude",
                "test_cmd": cmd, "initial": st, "items": []}
    desc = "；".join(_item_text(it) for it in items[:4]) + (f" 等 {len(items)} 项" if len(items) > 4 else "")
    return {"engine": "dsl", "kind": "task", "reason": f"初始测试全过，任务文本里抽到明确产物：{desc} → 任务路径",
            "test_cmd": cmd, "initial": st, "items": items}


def _item_text(it):
    k = it["kind"]
    return {"exists": lambda: f"新建 {it['path']}", "absent": lambda: f"删除 {it['path']}",
            "unchanged": lambda: f"不改 {it['path']}", "def": lambda: f"定义 {it['name']}",
            "forbid": lambda: f"{it['dir']} 下不出现 {it['name']}", "keys": lambda: f"{it['path']} 键 {','.join(it['keys'][:4])}",
            "lines": lambda: f"{it['path']} ≤{it['max']} 行", "import": lambda: f"from {it['mod']} import {it['name']}"}.get(
        k, lambda: k)()


# ------------------------------------------------------------ 快照、验收

def snapshot(project):
    """项目里 .py 源码（跳过隐藏目录、虚拟环境等）的原文，验收和 diff 用。"""
    _defs()
    import _sandbox
    out = {}
    for rel in _sandbox.py_files(project):
        try:
            out[rel] = (Path(project) / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    return out


def text_snapshot(files, max_bytes=200000):
    """reason.all_files 的字节快照 → 能按 utf-8 解码、不太大的文本文件（任务路径的 diff 用，含 .json/.csv/.md）。"""
    out = {}
    for rel, b in files.items():
        if len(b) <= max_bytes:
            try:
                out[rel] = b.decode("utf-8")
            except UnicodeDecodeError:
                pass
    return out


def _tests_hash(files):
    _defs()
    import _sandbox
    h = hashlib.sha256()
    for k in sorted(x for x in files if _sandbox.is_test_rel(x)):
        h.update(k.encode())
        h.update(files[k].encode())
    return h.hexdigest()


def diff_since(project, snap, limit=4000, every=False):
    """相对 snap 的源码改动：(diff 文本, 改了的文件, 改动行数)。every：snap 是 text_snapshot（所有文本文件）。"""
    if every:
        from . import reason as R
        now = text_snapshot(R.all_files(project))
    else:
        now = snapshot(project)
    lines, files, n = [], [], 0
    for rel in sorted(set(snap) | set(now)):
        a = snap.get(rel, "").splitlines()
        b = now.get(rel, "").splitlines()
        if a == b:
            continue
        d = list(difflib.unified_diff(a, b, rel, rel, lineterm="", n=1))
        files.append(rel)
        n += sum(1 for l in d if l[:1] in "+-" and not l.startswith(("+++", "---")))
        lines += d
    return "\n".join(lines)[:limit], files, n


def verify(project, snap, test_cmd):
    st = test_state(project, test_cmd)
    untouched = _tests_hash(snapshot(project)) == _tests_hash(snap)
    return {"passed": st["rc"] == 0, "tests_untouched": untouched, "fixed": st["rc"] == 0 and untouched,
            "summary": st["summary"]}


# ------------------------------------------------------------ 调用记录

def _opt(cmd, name):
    return cmd[cmd.index(name) + 1] if name in cmd and cmd.index(name) + 1 < len(cmd) else None


def call_meta(p):
    """从 claude 的 JSON 结果里取：费用、出错、回复前 400 字、duration_ms、duration_api_ms、usage；常驻进程另有 ttft/spawn，
    对冲的 hedged / winner / hedge_at_ms / hedge_reason / hedges / extra_cost（费用 cost 已含 extra_cost），
    以及 first_out_ms / no_output_ms / stall_ms / last_out_ms / legs（超时的调用也有，判断是没出首 token 还是出了以后卡住）。"""
    try:
        r = json.loads(p.stdout)
    except Exception:
        return {"cost": None, "raw": (p.stdout or p.stderr or "")[:300]}
    u = r.get("usage") or {}
    pm = r.get("_pool") or {}
    return {"cost": r.get("total_cost_usd"), "is_error": r.get("is_error"), "reply": str(r.get("result"))[:400],
            "duration_ms": r.get("duration_ms"), "duration_api_ms": r.get("duration_api_ms"),
            "ttft_ms": pm.get("ttft_ms"), "spawn": pm.get("spawn"), "retried": pm.get("retried"),
            "hedged": pm.get("hedged"), "winner": pm.get("winner"), "hedge_at_ms": pm.get("hedge_at_ms"),
            "hedge_reason": pm.get("hedge_reason"), "hedges": pm.get("hedges"),
            "extra_cost": pm.get("extra_cost"), "extra_cost_est": pm.get("extra_cost_est"),
            "first_out_ms": pm.get("first_out_ms"), "no_output_ms": pm.get("no_output_ms"),
            "stall_ms": pm.get("stall_ms"), "last_out_ms": pm.get("last_out_ms"), "legs": pm.get("legs"),
            "usage": {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
                      "cache_read": u.get("cache_read_input_tokens"), "cache_creation": u.get("cache_creation_input_tokens")}}


# ------------------------------------------------------------ 主流程

def run(project, task, out_dir, test_cmd=None, max_plan=MAX_PLAN, template=True, wall=WALL, inject=None,
        max_calls=MAX_CALLS, infer=None):
    """跑一次。project 里直接改文件；记录写进 out_dir（calls.json、result.json、plan_v*.zs/out.txt、state/）。
    inject：测试用，{"template": "fail"} 让模板这一版什么都不做（触发转规划 / 兜底的路径）。
    infer：模板预读并入推理候选（infer.py）；None＝看 DSLAGENT_INFER（默认开）。返回结果字典（同 result.json）。"""
    from tools import llm_router
    from tools.mock import MockClient

    from . import plan as P
    from . import prompts as PR
    from . import infer as I
    from . import template as T
    from . import reason as R
    from .engine import AgentEngine
    from .pool import Pool, child_env

    project = Path(project).resolve()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    state = out / "state"
    state.mkdir(exist_ok=True)
    inject = inject or {}
    test_cmd = test_cmd or detect_test_cmd(project)
    t_start = time.time()
    res = {"project": str(project), "test_cmd": test_cmd, "kind": None, "fixed": False, "engine_used": None, "versions": 0,
           "calls": 0, "cost": 0.0, "seconds": 0, "stop": "", "dir": str(out), "calls_log": str(out / "calls.json"),
           "version_log": [], "subcalls": [], "changed_files": [], "handoff": "", "report": ""}

    def finish():
        res["seconds"] = round(time.time() - t_start, 1)
        if not res["fixed"]:
            res["handoff"] = handoff_note(res)
        res["report"] = report(res)
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        return res

    if not test_cmd:
        res["stop"] = "项目里探测不到测试（没有 tests/、test_*.py 或 pytest 配置），dsl 要靠测试验收；可以传 test_cmd"
        return finish()
    os.environ["DSLAGENT_STATE"] = str(state)
    os.environ["DSLAGENT_TEST_CMD"] = test_cmd
    os.environ.setdefault("DSL_CLAUDE_TIMEOUT", "150")

    tmp = tmp_dir()
    pool_cwd = tmp / "pool_cwd"
    pool_cwd.mkdir(exist_ok=True)
    from tools.cbatch import CLAUDE_BIN
    pool = Pool(pool_cwd, os.environ.get("CBATCH_CLAUDE") or CLAUDE_BIN, child_env(tmp), log=out / "claude_stderr.log")
    kinds = (["template"] if template else []) + ["plan"] * max(0, int(max_plan))
    # 先起常驻进程（不调 API），进程启动（≈2 秒）和开局跑测试重叠。规划用的那个等到真要规划时才起：
    # 模板多半一版就修好（实验 28/28），一开始就起等于白占几百兆内存——并发 5 个任务时机器被拖慢过
    bal = MODEL.split("/")[-1]

    def prewarm(system):
        try:
            pool.prewarm(system, bal)
        except OSError:
            pass        # 起不来就算了，第一次调用时会再起一次并把错误记进 calls.json
    if kinds:
        prewarm(PR.LIB_SYSTEM if kinds[0] == "template" else PR.SYSTEM)   # 模板只调 定位/读改测（系统提示 LIB_SYSTEM）

    # 推理候选的事实抽取只读源码、和测试结果无关：后台线程先做，和开局跑测试重叠
    ijob = I.start(project) if template and I.enabled(infer) else None
    res["infer"] = {"on": ijob is not None}
    snap = snapshot(project)
    snap_all = R.all_files(project)
    R.setup(project, snap_all, task)
    st0 = test_state(project, test_cmd)
    test0 = st0["summary"]
    fail0 = R.fail_set(test0)
    res["rollbacks"] = 0
    res["done_check"] = {"items": R.done_items(task, snap_all), "log": []}
    chk = {"redo": False, "confirm": False}
    res["initial"] = {"runnable": st0["runnable"], "failing": st0["failing"], "summary": test0[:2000]}
    if not st0["runnable"]:
        pool.kill()
        res["stop"] = f"测试命令没跑到任何测试：{test0[:300]}"
        return finish()
    task_mode = not st0["failing"]
    res["kind"] = "task" if task_mode else "bugfix"
    snap_txt = text_snapshot(snap_all) if task_mode else None
    if task_mode:
        # 任务路径：不套模板、不用推理候选，直接模型规划；常驻进程换成规划的系统提示
        kinds = ["plan"] * max(0, int(max_plan))
        if template:
            pool.kill()
            if kinds:
                prewarm(PR.SYSTEM)
        if not kinds:
            res["stop"] = "规划版数上限 0，什么都没做"
            return finish()
    calls, subcalls = [], res["subcalls"]
    phase = {"v": "plan", "ver": 0}
    cap = {"plan_limit": 99}
    orig = llm_router.ClaudeCLIClient._run_local

    def counted(cmd, timeout):
        if len(calls) >= max_calls:
            raise llm_router.BackendError(f"总模型调用已满 {max_calls} 次，强制停")
        if phase["v"] == "exec" and sum(1 for c in calls if c["phase"] == "exec" and c["ver"] == phase["ver"]) >= cap["plan_limit"]:
            raise llm_router.BackendError(f"这一版计划内模型调用已满 {cap['plan_limit']} 次（预算），强制停")
        prompt = cmd[2] if len(cmd) > 2 else ""
        t0 = time.time()
        p = pool.run_local(cmd, timeout)
        t1 = time.time()
        kind = "定位" if P.LOC_MARK in prompt else ("读改测" if P.RCT_MARK in prompt else "")
        rec = {"phase": phase["v"], "ver": phase["ver"], "model": _opt(cmd, "--model"), "sec": round(t1 - t0, 2),
               "prompt_chars": len(prompt), "purpose": {"plan": "规划", "fix": "重写"}.get(phase["v"]) or kind or "问JSON",
               "t_start": round(t0, 3), "t_end": round(t1, 3)}
        rec.update(call_meta(p))
        calls.append(rec)
        return p

    def no_fallback(prompt, system=None):
        raise RuntimeError("claude 这次没跑成，档位要退到别的模型——dslagent 不允许")

    client = llm_router.wrap(MockClient(handler=no_fallback, offline=False))
    lister = _verb_module("列文件")
    lister.WORKSPACE = project
    files = lister.列文件("全部" if task_mode else "")

    def scripts_for(plan_dir, subs):
        m = {n: LIB / n for n in P.LIBS}
        m.update({f"_plan/{k}": Path(plan_dir) / k for k in subs})
        return m

    prev = None
    last_test = test0
    try:
        llm_router.ClaudeCLIClient._run_local = staticmethod(counted)
        for ver, kind in enumerate(kinds, 1):
            if time.time() - t_start > wall:
                res["stop"] = f"墙钟超过 {wall} 秒，不再开第 {ver} 版"
                break
            left = max_calls - len(calls)
            if left < 2:
                res["stop"] = f"总调用只剩 {left} 次，不够再规划+执行"
                break
            versions_left = len(kinds) - ver
            plan_cap = max(1, left - 1 - (1 if versions_left else 0))
            vrec = {"ver": ver, "kind": kind, "fix_rounds": 0, "fix_problems": []}
            phase.update(v="plan", ver=ver)
            t0 = time.time()
            try:
                if kind == "template":
                    aug = (lambda p: I.augment(ijob, p, task, test0, project)) if ijob else None
                    txt, tparams = T.build(task, test0, project, augment=aug)
                    if "infer" in tparams:
                        res["infer"] = tparams["infer"]
                    if inject.get("template") == "fail":
                        txt = INJECT_FAIL
                        tparams = dict(tparams, injected="fail")
                    vrec["template"] = tparams
                else:
                    if prev is None:
                        pr = (PR.task_first_prompt if task_mode else PR.first_prompt)(
                            task, files, test0, left, plan_cap, versions_left, test_cmd)
                    else:
                        rb = ""
                        if R.enabled():
                            d = R.replan_check(fail0, test_state(project, test_cmd)["summary"],
                                               R.all_files(project) != snap_all)
                            if d["action"] == "rollback":
                                R.restore(project, snap_all)
                                res["rollbacks"] += 1
                                rb = (f"\n【安全约束】上一版改坏了原本通过的测试（{'；'.join(d['regress'][:3])}），"
                                      f"已把项目回滚到开局状态，下面的 diff/测试是回滚后的；别重复那条改法。")
                        if task_mode:
                            diff, _, _ = diff_since(project, snap_txt, 3000, every=True)
                            pr = PR.task_replan_prompt(task, files, test0, left, plan_cap, versions_left, ver - 1,
                                                       prev["script"], prev["out"][-5000:], prev["error"],
                                                       test_state(project, test_cmd)["summary"], diff, test_cmd, rb.strip())
                        else:
                            diff, _, _ = diff_since(project, snap, 3000)
                            pr = PR.replan_prompt(task, files, test0, left, plan_cap, versions_left, ver - 1, prev["script"],
                                                  prev["out"][-5000:], prev["error"], test_state(project, test_cmd)["summary"],
                                                  diff, test_cmd, (PR.TEMPLATE_NOTE if prev["kind"] == "template" else "") + rb)
                    txt = client.chat(pr, system=PR.SYSTEM, model=MODEL)
            except Exception as e:
                res["stop"] = f"第 {ver} 版规划失败：{type(e).__name__}: {str(e)[:300]}"
                break
            vrec["sec_plan"] = round(time.time() - t0, 2)
            (out / f"plan_v{ver}_raw.txt").write_text(txt, encoding="utf-8")
            script, _ = P.strip_prose(txt)
            script = _autoclose(P, script, vrec)
            ok_check = False
            while True:
                main, subs = P.split_subs(script)
                probs = P.whitelist_check(main, subs)
                if probs:
                    problem = "白名单检查没过：\n" + "\n".join(probs[:10])
                elif kind == "template":
                    problem = ""     # 固定骨架，自测里各场景都空跑过；不再空跑
                else:
                    err, _, _ = P.dry_run(project, state.parent / "dry", main, subs, task, scripts_for, MODEL)
                    problem = f"用假模型空跑报错：{err}" if err else ""
                if not problem:
                    ok_check = True
                    break
                vrec["fix_problems"].append(problem[:400])
                if kind == "template" or vrec["fix_rounds"] >= MAX_FIX or max_calls - len(calls) < 2:
                    break
                vrec["fix_rounds"] += 1
                phase.update(v="fix", ver=ver)
                try:
                    txt = client.chat(PR.fix_prompt(script, problem), system=PR.SYSTEM, model=MODEL)
                except Exception as e:
                    vrec["fix_problems"].append(f"重写调用失败：{e}")
                    break
                (out / f"plan_v{ver}_fix{vrec['fix_rounds']}_raw.txt").write_text(txt, encoding="utf-8")
                script, _ = P.strip_prose(txt)
                script = _autoclose(P, script, vrec)
            (out / f"plan_v{ver}.zs").write_text(script, encoding="utf-8")
            main, subs = P.split_subs(script)
            text, error = "", ""
            if ok_check:
                left = max_calls - len(calls)
                cap["plan_limit"] = max(1, left - (1 if versions_left else 0))
                phase.update(v="exec", ver=ver)
                plan_dir = out / f"plan_v{ver}_subs"
                if subs:
                    P.write_subs(plan_dir, subs)
                n_sub = len(subcalls)
                eng = AgentEngine(client=client, workdir=project, verbose=False, verbs_root=VERBS,
                                  scripts=scripts_for(plan_dir, subs), on_call=subcalls.append)
                eng.model = MODEL
                eng.vars["task"] = task
                t0 = time.time()
                try:
                    eng.run(main)
                except Exception as e:
                    error = f"{type(e).__name__}: {str(e)[:600]}"
                vrec["sec_exec"] = round(time.time() - t0, 1)
                for sc in subcalls[n_sub:]:
                    sc["ver"] = ver
                text = "\n".join(eng.output)
                if eng.returned and not text.strip():
                    text = f"（脚本返回：{str(eng.returned[0])[:2000]}）"
            else:
                error = "检查没通过，这一版没有执行：" + (vrec["fix_problems"][-1] if vrec["fix_problems"] else "")
            (out / f"plan_v{ver}_out.txt").write_text(text + (f"\n\n[报错] {error}" if error else ""), encoding="utf-8")
            if ver < len(kinds) and kinds[ver] == "plan" and not re.search(r"结论[:：]\s*修好", text):
                prewarm(PR.SYSTEM)      # 这版自己都说没修好、下一版要规划：先起进程，和下面的验收测试重叠
            v = verify(project, snap, test_cmd)
            last_test = v["summary"]
            concl = re.findall(r"结论[:：]\s*(.+)", text)
            if task_mode:
                # 任务路径没有失败测试可对：完成＝测试全过且没动测试文件、脚本没报错、结论「修好」
                v["fixed"] = v["fixed"] and not error and bool(concl) and concl[-1].strip().startswith("修好")
            vrec.update(calls=sum(1 for c in calls if c["ver"] == ver), error=error[:400],
                        conclusion=concl[-1][:200] if concl else "", fixed_after=v["fixed"], out_tail=text[-800:])
            res["version_log"].append(vrec)
            prev = {"kind": kind, "script": script, "out": text, "error": error}
            if v["fixed"] and R.enabled():
                # 完成前核对（rules/完成核对.dl）：任务点名的产物逐条查；不满足 → 再做一轮 → 仍不满足问模型确认一次
                unmet = R.done_unmet(project, res["done_check"]["items"], snap_all)
                d = R.infer("完成核对", R.done_facts(True, unmet, not chk["redo"] and max_calls - len(calls) >= 2,
                                                     not chk["confirm"] and max_calls - len(calls) >= 1))
                res["done_check"]["log"].append({"ver": ver, "unmet": unmet, "action": d["action"]})
                if d["action"] == "redo":
                    chk["redo"] = True
                    prev["error"] = ("【完成核对】测试全过，但任务点名的这些要求还没满足，这一版只补这些（已完成的保留）：\n- "
                                     + "\n- ".join(unmet))
                    if ver == len(kinds):
                        kinds.append("plan")
                    continue
                if d["action"] == "confirm":
                    chk["confirm"] = True
                    still = _confirm(client, task, unmet, phase)
                    res["done_check"]["log"].append({"confirm": "仍未满足" if still else "模型确认不是要求"})
                    if still:
                        res["stop"] = "完成核对：" + "；".join(unmet)[:300]
                        break
                elif d["action"] != "done":
                    res["stop"] = "完成核对：" + "；".join(unmet)[:300]
                    break
            if v["fixed"]:
                res["fixed"] = True
                res["engine_used"] = "plan_task" if task_mode else kind
                break
            if not v["tests_untouched"]:
                res["stop"] = "测试文件被改了，停（需要人看）"
                break
        else:
            if not res["fixed"]:
                res["stop"] = res["stop"] or ((f"{len(kinds)} 版都没完成（按测试/报错/结论判断）" if task_mode
                                               else f"{len(kinds)} 版都没修好") if kinds
                                              else "模板关了、规划版数上限 0，什么都没做")
    finally:
        llm_router.ClaudeCLIClient._run_local = orig
        pool.close()
        (out / "calls.json").write_text(json.dumps(calls, ensure_ascii=False, indent=1), encoding="utf-8")
        res["versions"] = len(res["version_log"])
        res["engine_used"] = res["engine_used"] or (("plan_task" if task_mode else res["version_log"][-1]["kind"])
                                                    if res["version_log"] else None)
        res["calls"] = len(calls)
        res["cost"] = round(sum(c.get("cost") or 0 for c in calls), 4)
        res["calls_by_purpose"] = {k: sum(1 for c in calls if c["purpose"] == k) for k in {c["purpose"] for c in calls}}
        res["rule_fires"] = list(R.STATE["fires"])
        res["blocks"] = list(R.STATE["log"])
        dsnap = snap_txt if task_mode else snap
        _, res["changed_files"], res["changed_lines"] = diff_since(project, dsnap, every=task_mode)
        res["diff"] = diff_since(project, dsnap, 3000, every=task_mode)[0]
        res["final_test"] = last_test[:2000]
    return finish()


def _confirm(client, task, unmet, phase):
    """完成核对补做后仍不满足：交模型对照任务确认一次。返回 True＝仍算未完成（调用失败也按未完成）。"""
    items = "\n".join(f"{i}. {u}" for i, u in enumerate(unmet, 1))
    pr = (f"一个自动执行的代理宣布完成了下面的任务，但机械核对（从任务文字里抽取点名的文件/名字/键）发现有几项未满足。"
          f"抽取可能有误（比如把任务里举例或已有的名字当成必须新建的）。请只对照任务原文判断：每一项是不是任务确实要求、"
          f"且按核对结果确实没做到。\n\n【任务】\n{task}\n\n【未满足项】\n{items}\n\n"
          f"只输出一行 JSON：{{\"still_required\": [确实是要求且没做到的序号], \"reason\": \"一句话\"}}")
    phase.update(v="confirm")
    try:
        txt = client.chat(pr, model=MODEL)
        m = re.search(r"\{.*\}", txt, re.S)
        return bool((json.loads(m.group(0)) if m else {}).get("still_required", [1]))
    except Exception:
        return True


def _autoclose(P, script, vrec):
    new, n, why = P.autoclose(script)
    if n:
        vrec.setdefault("autoclose", []).append({"added": n, "blocks": why})
    return new


def report(res):
    """给 cbatch 任务 output 的几行人话。"""
    how = {"template": "模板第 1 版", "plan": f"规划第 {res['versions']} 版",
           "plan_task": f"任务路径规划第 {res['versions']} 版"}.get(res["engine_used"], "")
    ok, ng = ("完成", "没完成") if res.get("kind") == "task" else ("修好", "没修好")
    head = (f"DSL {ok}（{how}）" if res["fixed"] else f"DSL {ng}：{res['stop'] or '见记录'}") + \
        f"；{res['versions']} 版，{res['calls']} 次模型调用，${res['cost']:.4f}，{res['seconds']}s"
    lines = [head]
    if res.get("changed_files"):
        lines.append(f"改动：{'、'.join(res['changed_files'])}（{res.get('changed_lines', 0)} 行）")
    for v in res["version_log"]:
        lines.append(f"第 {v['ver']} 版（{'模板' if v['kind'] == 'template' else '规划'}）：{v.get('conclusion') or v.get('error') or '没有结论'}")
    lines.append(f"测试命令：{res['test_cmd']}")
    lines.append(f"记录：{res['dir']}")
    return "\n".join(lines)


def handoff_note(res):
    """dsl 没修好时给兜底 claude 的交接说明：每版做了什么、定位/读改测的轨迹、已做的修改、当前测试。"""
    parts = [f"【停下原因】{res['stop'] or ('没完成' if res.get('kind') == 'task' else '没修好')}"]
    for v in res["version_log"]:
        parts.append(f"【第 {v['ver']} 版（{'固定模板' if v['kind'] == 'template' else '模型规划'}）】结论：{v.get('conclusion') or '无'}"
                     + (f"；报错：{v['error']}" if v.get("error") else ""))
    for sc in res["subcalls"][-6:]:
        parts.append(f"- {sc['name']}（第 {sc.get('ver')} 版）outcome={sc.get('outcome')} segs={sc.get('segs', '')[:200]}\n"
                     f"  {str(sc.get('log', ''))[:500]}")
    parts.append("【它已经做的修改（相对开始时的 diff）】\n" + (res.get("diff") or "（没有改动源码）"))
    parts.append("【当前测试】\n" + (res.get("final_test") or res.get("initial", {}).get("summary", "")))
    return "\n".join(parts)[:7000]
