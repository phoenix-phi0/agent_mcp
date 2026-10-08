"""python -m tools.dslagent run|auto …：见 __init__ 的说明。最后一行打印结果 JSON。"""
import argparse
import json
import signal
import sys
from pathlib import Path


def _task(a):
    if a.task_file:
        return Path(a.task_file).read_text(encoding="utf-8")
    return a.task or ""


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools.dslagent")
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run", help="模板 → 规划，在 project 里直接改文件")
    r.add_argument("--project", required=True)
    r.add_argument("--task")
    r.add_argument("--task-file")
    r.add_argument("--out", required=True)
    r.add_argument("--test-cmd")
    r.add_argument("--max-plan", type=int, default=2)
    r.add_argument("--no-template", action="store_true")
    r.add_argument("--no-infer", action="store_true", help="模板预读不并入推理候选（同 DSLAGENT_INFER=0）")
    r.add_argument("--wall", type=int, default=500)
    r.add_argument("--inject", default="{}", help="测试用 JSON，如 {\"template\": \"fail\"}")
    u = sp.add_parser("auto", help="只做 engine=auto 的判定")
    u.add_argument("--project")
    u.add_argument("--task")
    u.add_argument("--task-file")
    u.add_argument("--test-cmd")
    a = ap.parse_args(argv)

    from . import runner
    if a.cmd == "auto":
        d = runner.decide_auto(_task(a), a.project, a.test_cmd)
        print(json.dumps(d, ensure_ascii=False))
        return 0

    # 被 cbatch 超时 / 取消杀掉时走 finally：关掉常驻 claude 进程，写下已有的记录
    def on_term(*_):
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, on_term)
    res = runner.run(a.project, _task(a), a.out, test_cmd=a.test_cmd, max_plan=a.max_plan,
                     template=not a.no_template, wall=a.wall, inject=json.loads(a.inject or "{}"),
                     infer=False if a.no_infer else None)
    print(json.dumps({k: res[k] for k in ("fixed", "engine_used", "versions", "calls", "cost", "seconds", "stop")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
