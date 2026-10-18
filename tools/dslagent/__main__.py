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
    r = sp.add_parser("run", help="开局有失败：模板 → 规划（修 bug）；全过：模型规划（任务路径）。在 project 里直接改文件")
    r.add_argument("--project", required=True)
    r.add_argument("--task")
    r.add_argument("--task-file")
    r.add_argument("--out", required=True)
    r.add_argument("--test-cmd")
    r.add_argument("--max-plan", type=int, default=2)
    r.add_argument("--no-template", action="store_true")
    r.add_argument("--no-infer", action="store_true", help="模板预读不并入推理候选（同 DSLAGENT_INFER=0）")
    r.add_argument("--wall", type=int, default=500)
    r.add_argument("--scope", help="允许改动的目录前缀，逗号分隔（如 kg/,tests/kg/）；只对 v2 规划路径有效，范围外的改动恢复并要求补改")
    r.add_argument("--inject", default="{}", help="测试用 JSON，如 {\"template\": \"fail\"}")
    u = sp.add_parser("auto", help="只做 engine=auto 的判定")
    u.add_argument("--project")
    u.add_argument("--task")
    u.add_argument("--task-file")
    u.add_argument("--test-cmd")
    n = sp.add_parser("newproj", help="新建项目：跳过规划，直接执行固定模板 packs/newproj/newproj.zs")
    n.add_argument("req_file", help="需求文件")
    n.add_argument("project", help="项目目录（不存在就建）")
    n.add_argument("--out", required=True)
    n.add_argument("--wall", type=int, default=None, help="墙钟秒数；缺省：旧模板 900，--split 2400，--layered 3600，--modular 5400")
    n.add_argument("--split", action="store_true", help="按功能分次生成（packs/newproj/newproj_split.zs）：功能清单 → 实体 → 逐个功能 sql / zs / ui；缺省仍是旧模板")
    n.add_argument("--layered", action="store_true", help="分层逐实体生成（layered.py）：分层清单 → 实体 → 查询 → 接口 → 界面，每个文件单独检查，失败的文件让依赖它的上层跳过；缺省仍是旧模板")
    n.add_argument("--cost-cap", type=float, default=None, help="Claude 侧累计花费上限（美元），达到就不再调模型、以「部分成功：花费达上限」结束；缺省读环境变量 NEWPROJ_COST_CAP，都没有 = 不限（只对 --layered 有效）")
    n.add_argument("--modular", action="store_true", help="顶层规划 → 层次×模块 → 按层逐层构建（modbuild.py）：能力清单 → 顶层规划(PLAN.md) → 层次×模块(LAYERS.md) → 数据/查询/流程/接口/界面，层内按构建顺序逐模块；--cost-cap 同样有效，缺省墙钟 5400 秒")
    a = ap.parse_args(argv)
    if a.cmd == "newproj":
        from . import v2
        res = v2.run_newproj(Path(a.req_file).read_text(encoding="utf-8"), a.project, a.out, wall=a.wall, split=a.split,
                             **({"modular": True, "cost_cap": a.cost_cap} if a.modular else {"layered": True, "cost_cap": a.cost_cap} if a.layered else {}))
        print(json.dumps({k: res[k] for k in ("fixed", "calls", "cost", "seconds", "stop", "changed_files")}, ensure_ascii=False))
        return 0

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
                     infer=False if a.no_infer else None, scope=a.scope)
    print(json.dumps({k: res[k] for k in ("kind", "fixed", "engine_used", "versions", "calls", "cost", "seconds", "stop")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
