# -*- coding: utf-8 -*-
"""cbatch engine=dsl/auto 的真模型集成测试（手动跑，要花钱，不在 run_all.sh 里）。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/dslagent_live.py paths     # 三条路径 + auto 分到 claude
    cd /home/ysc/mcp && .venv/bin/python tests/tools/dslagent_live.py regress   # N1–N10 各 1 次 dsl 回归

场景是 /tmp/dslagent 实验里的 shopkit（N1–N6 来自 route/scen，N7–N10 来自 plan7/scen），先拷到
SCEN（默认 /home/ysc/dslagent_tmp/scen，含 tasks.json）。每次运行把场景再拷一份到 WORK/<run>/repo 里改。
走的是 cbatch.submit → 独立的执行器进程（新代码），不碰 MCP 服务；CBATCH_HOME 也指到 WORK/jobs，
不混进平时的任务列表。验收：完整测试全过 + tests/ 没改（哈希）+ 已知场景的根因检查。
"""

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SCEN = Path(os.environ.get("DSLAGENT_SCEN", "/home/ysc/dslagent_tmp/scen"))
WORK = Path(os.environ.get("DSLAGENT_WORK", "/home/ysc/dslagent_tmp/live"))
os.environ["CBATCH_HOME"] = str(WORK / "jobs")
os.environ.setdefault("DSLAGENT_TMP", str(WORK / "tmp"))

from tools import cbatch    # noqa: E402

TASKS = json.loads((SCEN / "tasks.json").read_text(encoding="utf-8")) if (SCEN / "tasks.json").is_file() else {}


def tree_hash(d):
    h = hashlib.sha256()
    for f in sorted(Path(d).rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        h.update(str(f.relative_to(d)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def verify(repo, scen):
    """同实验的 verify_route / verify7：测试全过 + tests/ 没改 + 改了哪些文件 + 根因。"""
    repo, base = Path(repo), SCEN / scen
    p = subprocess.run(["python3", "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=repo,
                       capture_output=True, text=True, timeout=120)
    files = []
    for f in sorted(base.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(base)
        g = repo / rel
        if list(difflib.unified_diff(f.read_text().splitlines(), g.read_text().splitlines() if g.exists() else [])):
            files.append(str(rel))
    ok = p.returncode == 0 and tree_hash(repo / "tests") == tree_hash(base / "tests")
    src = lambda n: (repo / "shopkit" / n).read_text()  # noqa: E731
    root = {
        "N3": lambda: "shopkit/catalog.py" in files and not {"shopkit/shipping.py", "shopkit/invoice.py"} & set(files),
        "N4": lambda: "return int(Decimal" not in src("pricing.py") + src("tax.py"),
        "N5": lambda: files == ["shopkit/fulfillment.py"],
        "N6": lambda: "SYMBOLS[" not in src("invoice.py") + src("receipt.py") + src("cart.py"),
        "N7": lambda: "shopkit/utils.py" in files,
        "N8": lambda: {"shopkit/tax.py", "shopkit/shipping.py"} <= set(files),
        "N9": lambda: "shopkit/settings.py" in files,
        "N10": lambda: "(10, 2200)" in src("shipping.py"),
    }.get(scen)
    return {"fixed": ok, "files": files, "root_cause": root() if root else None}


def fresh(run, scen, drop_tests=False):
    d = WORK / run
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(SCEN / scen, d / "repo", ignore=shutil.ignore_patterns("__pycache__", "tests" if drop_tests else "_none_"))
    return str(d / "repo")


def run_jobs(specs):
    """specs：[(名字, submit 参数)]，并发提交，全部跑完返回 {名字: job}。前台等。"""
    out = {}

    def one(name, kw):
        j = cbatch.submit(**kw)
        out[name] = cbatch.wait(j["job_id"], timeout=1500, every=3)
    th = [threading.Thread(target=one, args=s) for s in specs]
    for t in th:
        t.start()
    for t in th:
        t.join()
    return out


def row(t, v):
    return (f"engine_used={t.get('engine_used')} status={t['status']} versions={t.get('versions')} calls={t.get('calls')} "
            f"cost=${t.get('cost_usd') or 0:.4f} sec={t.get('seconds')} fixed={v['fixed']} root={v['root_cause']} "
            f"files={v['files']} reason={t.get('engine_reason', '')[:80]}")


def paths():
    r1, r2, r3 = fresh("p1_template_N1", "N1"), fresh("p2_plan_N9", "N9"), fresh("p3_fallback_N4", "N4")
    r4 = fresh("p4_auto_claude", "N1", drop_tests=True)
    jobs = run_jobs([
        ("dsl", dict(name="live-paths", cwd=str(WORK), engine="dsl", tasks=[
            {"prompt": TASKS["N1"]["desc"], "project": r1},
            {"prompt": TASKS["N9"]["desc"], "project": r2, "dsl_options": {"inject": {"template": "fail"}}},
            {"prompt": TASKS["N4"]["desc"], "project": r3, "dsl_options": {"inject": {"template": "fail"}, "max_plan": 0}},
        ])),
        ("auto", dict(name="live-auto", cwd=r4, engine="auto", permission_mode="acceptEdits", tasks=[
            {"prompt": "在 shopkit/money.py 文件第一行加一行注释「# 金额格式化工具」，别的不要动。", "project": r4},
        ])),
    ])
    res = []
    for (label, repo, scen), t in zip([("(i) 模板命中", r1, "N1"), ("(ii) 模板失败→规划", r2, "N9"),
                                       ("(iii) 规划上限0→claude 兜底", r3, "N4")], jobs["dsl"]["tasks"]):
        v = verify(repo, scen)
        print(label, row(t, v))
        res.append({"label": label, "task": {k: t.get(k) for k in ("engine_used", "status", "versions", "calls", "cost_usd",
                                                                    "seconds", "calls_log", "engine_reason", "error")}, "verify": v})
    t = jobs["auto"]["tasks"][0]
    head = (Path(r4) / "shopkit/money.py").read_text(encoding="utf-8").splitlines()[0]
    print("(iv) auto 无测试任务", f"engine_used={t.get('engine_used')} status={t['status']} cost=${t.get('cost_usd') or 0:.4f} "
          f"sec={t.get('seconds')} reason={t.get('engine_reason')} 首行={head!r}")
    res.append({"label": "(iv) auto 无测试", "task": {k: t.get(k) for k in ("engine_used", "status", "cost_usd", "seconds",
                                                                         "engine_reason")}, "first_line": head})
    (WORK / "paths_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def regress():
    scens = [f"N{i}" for i in range(1, 11)]
    repos = {n: fresh(f"reg_{n}", n) for n in scens}
    specs = [(f"g{k}", dict(name=f"live-regress-{k}", cwd=str(WORK), engine="dsl", fallback=False,
                            tasks=[{"prompt": TASKS[n]["desc"], "project": repos[n]} for n in scens[2 * k:2 * k + 2]]))
             for k in range(5)]
    t0 = time.time()
    jobs = run_jobs(specs)
    res = []
    for k in range(5):
        for n, t in zip(scens[2 * k:2 * k + 2], jobs[f"g{k}"]["tasks"]):
            v = verify(repos[n], n)
            print(n, row(t, v))
            res.append({"scen": n, "engine_used": t.get("engine_used"), "status": t["status"], "versions": t.get("versions"),
                        "calls": t.get("calls"), "cost": t.get("cost_usd"), "seconds": t.get("seconds"),
                        "calls_log": t.get("calls_log"), **v})
    res.sort(key=lambda x: int(x["scen"][1:]))
    ok = sum(1 for x in res if x["fixed"])
    print(f"成功 {ok}/{len(res)}，平均 {sum(x['seconds'] or 0 for x in res) / len(res):.1f}s，"
          f"平均 ${sum(x['cost'] or 0 for x in res) / len(res):.4f}，总 ${sum(x['cost'] or 0 for x in res):.3f}，"
          f"墙钟 {time.time() - t0:.0f}s")
    (WORK / "regress_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    {"paths": paths, "regress": regress}[sys.argv[1] if len(sys.argv) > 1 else "paths"]()
