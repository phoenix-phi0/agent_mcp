"""做一个模块：起子进程跑 `python -m tools.dslagent run --pack dslproj …`（范围激活、DSLAGENT_MODELS 等环境变量是进程级的，同进程并行会串）。

每一轮在项目的一份拷贝里做（out/modules/<模块>/r<轮>/proj）：v2 的范围闸会把「范围外的改动」恢复成改前内容，
同层几个模块在同一个目录里并行就会互相恢复；做完只把本模块范围内的文件（entities / services / routes / queries / tests 里属于它的）拷回项目。
返回 {状态, 原因, 花费, 调用, 轮, 模型, 记录目录, 秒}。
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .. import common as C
from ..packs.dslproj import project as P

COPY_IGNORE = shutil.ignore_patterns(".*", "__pycache__", "node_modules", "*.pyc", "*.db", "*.db-*", "sessions")
MAX_FAIL = 4000        # 上一轮失败原因带进任务的最大字数
MODEL_STEPS = ("plan", "plan_fix", "sub", "fix", "bound")


def base_cmd(ctx):
    if ctx.module_cmd:
        return list(ctx.module_cmd)
    env = os.environ.get("DSLAGENT_V3_MODULE_CMD")
    return json.loads(env) if env else [sys.executable, "-m", "tools.dslagent"]


def scope_files(root, module):
    root = Path(root)
    return sorted({str(f.relative_to(root)) for g in P.scope_globs(module) for f in root.glob(g) if f.is_file()})


def sync_back(work, project, module):
    """本模块范围内的文件：work 里有的拷回 project，project 里有而 work 里没有的删掉。→ (写入, 删除)。"""
    have, now = set(scope_files(work, module)), set(scope_files(project, module))
    for rel in sorted(have):
        dst = Path(project) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(work) / rel, dst)
    gone = sorted(now - have)
    for rel in gone:
        (Path(project) / rel).unlink()
    return sorted(have), gone


def task_text(module, last_fail):
    t = f"模块 {module}\n"
    if (last_fail or "").strip():
        t += f"\n上一轮没有做成（做模块的结果 + 验收），问题如下，针对这些问题改；约定不能改：\n{last_fail.strip()[:MAX_FAIL]}\n"
    return t


def last_json(stdout):
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def run_module(ctx, module, last_fail="", model="sonnet", task_text_override=None):
    ctx.guard()
    with ctx.lock:
        if module not in ctx.rounds:          # 续跑：轮号接着上一次的，不覆盖已有的记录目录
            done = [int(d.name[1:]) for d in (ctx.out / "modules" / module).glob("r[0-9]*") if d.name[1:].isdigit()]
            ctx.rounds[module] = max(done, default=0)
        ctx.rounds[module] = n = ctx.rounds[module] + 1
    rec = ctx.out / "modules" / module / f"r{n}"
    work = rec / "proj"
    shutil.rmtree(rec, ignore_errors=True)
    rec.mkdir(parents=True)
    shutil.copytree(ctx.project, work, ignore=COPY_IGNORE)
    task = rec / "task.txt"
    task.write_text(task_text(module, last_fail) if task_text_override is None else task_text_override, encoding="utf-8")
    cmd = base_cmd(ctx) + ["run", "--pack", "dslproj", "--project", str(work), "--task-file", str(task), "--out", str(rec / "v2"),
                           "--wall", str(ctx.module_wall)]
    env = dict(os.environ)
    env["DSLAGENT_MODELS"] = json.dumps({s: model for s in MODEL_STEPS})
    t0 = time.time()
    out = {"模块": module, "轮": n, "模型": model, "记录目录": str(rec)}
    try:
        p = subprocess.run(cmd, cwd=str(C.ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=ctx.module_wall + 300)
        stdout, stderr, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        stdout, stderr, rc = (e.stdout or ""), (e.stderr or ""), -9
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
    (rec / "stdout.txt").write_text(stdout or "", encoding="utf-8")
    (rec / "stderr.txt").write_text(stderr or "", encoding="utf-8")
    j = last_json(stdout)
    sec = round(time.time() - t0, 1)
    if j is None:
        why = "子进程超时被杀" if rc == -9 else f"子进程没有给出结果（退出码 {rc}）：{(stderr or '').strip()[-300:]}"
        out.update(状态="失败", 原因=why, 花费=0.0, 调用=0, 秒=sec)
    else:
        out.update(状态="成功" if j.get("fixed") else "失败", 原因=str(j.get("stop") or ""), 花费=float(j.get("cost") or 0.0),
                   调用=int(j.get("calls") or 0), 秒=sec)
    written, gone = sync_back(work, ctx.project, module)
    out.update(写入=written, 删除=gone)
    with ctx.lock:
        ctx.module_cost += out["花费"]
    ctx.log("模块", **{k: v for k, v in out.items() if k not in ("写入", "删除")}, 写入文件数=len(written))
    ctx.take_call(out["调用"])
    ctx.guard()
    return {k: out[k] for k in ("状态", "原因", "花费", "调用", "轮", "模型", "记录目录", "秒")}
