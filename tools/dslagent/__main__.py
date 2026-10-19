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
    r.add_argument("--wall", type=int, default=None, help="墙钟秒数；缺省：旧命令 500，--pack 的 v2 路径 900")
    r.add_argument("--scope", help="允许改动的路径，逗号分隔（目录前缀如 kg/,tests/kg/，精确文件，或带 * 的通配如 routes/graph*.zs）；只对 v2 规划路径有效，范围外的改动恢复并要求补改；缺省取资料包的 scope_for")
    r.add_argument("--pack", help="资料包名（code / dslproj，见 packs/）：写了就走 v2 规划路径（与 DSLAGENT_PLANNER 无关），场景差异全由包声明；不写 = 旧命令（code 行为不变）")
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
    n.add_argument("--resume", action="store_true", help="继续上次的 --modular 构建（project / --out 用上次的）：不重做顶层规划和层次×模块，沿用上次通过且仍过检查的文件，失败 / 跳过 / 未做的按原顺序重做；--cost-cap 只算本次新花的，result.json 保留上次记录并追加，calls.json 追加")
    n.add_argument("--codex-cap", type=int, default=None, help="codex 调用次数上限（只对 --modular 有效）：codex 调用不计费、不进 --cost-cap（熔断只看 Claude 侧花费），用这个限次数；达到就停、以「部分成功」结束；缺省不限。规划 / 生成可分别指定模型：DSLAGENT_MODELS 里 mplan（规划类）/ mgen（生成类），没写走 sub")
    n.add_argument("--no-contract", action="store_true", help="（只对 --modular）不先约定接口：回到逐文件规划、按下层真实文件对接的老做法；缺省先约定接口（CONTRACTS.md）再按约定实现，实现后试调一轮")
    n.add_argument("--from-plan", default=None, metavar="旧输出目录", help="（只对 --modular）读回旧运行的顶层规划与层次×模块（plan/top.zs、plan/layers.zs；旧版 JSON 目录也读，转成 DSL 规划文件；再不行从 result.json 与 calls/ 还原），跳过这两步，在新的 project / --out 里从数据层做起")
    v = sp.add_parser("v3", help="v3 流程（v3/v3.zs）：顶层规划 → 约定 → 骨架 → 分配 → 按层做模块；断了重跑同一命令即续跑")
    v.add_argument("--req", required=True, help="需求文件")
    v.add_argument("--project", required=True, help="项目目录（不存在就建）")
    v.add_argument("--out", required=True, help="记录目录：每步产物、检查结果、重写次数、每个模块的 v2 记录目录、花费")
    v.add_argument("--stop-after", choices=("top", "contract", "build"), default=None, help="跑到这一步的产物写出并通过检查就停")
    v.add_argument("--cost-cap", type=float, default=None, help="花费上限（美元），达到就以「超出预期」结束")
    v.add_argument("--wall", type=int, default=None, help="整个流程的墙钟秒数（缺省 36000）")
    v.add_argument("--module-wall", type=int, default=1500, help="做一个模块时 v2 子进程的墙钟秒数")
    a = ap.parse_args(argv)
    if a.cmd == "v3":
        from .v3 import core as V3
        def on_term(*_):
            raise SystemExit(143)
        signal.signal(signal.SIGTERM, on_term)
        res = V3.run(Path(a.req).read_text(encoding="utf-8"), a.project, a.out, stop_after=a.stop_after, cost_cap=a.cost_cap,
                     **({"wall": a.wall} if a.wall else {}), module_wall=a.module_wall)
        print(json.dumps({k: res.get(k) for k in ("状态", "原因", "停在", "花费", "用时", "模型调用")}, ensure_ascii=False))
        return 0 if res["状态"] == "成功" else 1
    if a.cmd == "newproj":
        from . import v2
        if a.resume and not a.modular:
            ap.error("--resume 要和 --modular 一起用")
        if (a.from_plan or a.no_contract) and not a.modular:
            ap.error("--from-plan / --no-contract 要和 --modular 一起用")
        if a.from_plan and a.resume:
            ap.error("--from-plan 和 --resume 不能一起用（from-plan 是在新目录重新开始，resume 是接着上次的目录）")
        res = v2.run_newproj(Path(a.req_file).read_text(encoding="utf-8"), a.project, a.out, wall=a.wall, split=a.split,
                             **({"modular": True, "cost_cap": a.cost_cap, "codex_cap": a.codex_cap, **({"resume": True} if a.resume else {}), **({"contract": False} if a.no_contract else {}), **({"from_plan": a.from_plan} if a.from_plan else {})} if a.modular else {"layered": True, "cost_cap": a.cost_cap} if a.layered else {}))
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
    if a.pack:
        from . import entry
        res = entry.run_pack(a.project, _task(a), a.pack, a.out, scope=a.scope, test_cmd=a.test_cmd, wall=a.wall)
        print(json.dumps({k: res.get(k) for k in ("kind", "fixed", "engine_used", "versions", "calls", "cost", "seconds", "stop")},
                         ensure_ascii=False))
        return 0
    res = runner.run(a.project, _task(a), a.out, test_cmd=a.test_cmd, max_plan=a.max_plan,
                     template=not a.no_template, wall=500 if a.wall is None else a.wall, inject=json.loads(a.inject or "{}"),
                     infer=False if a.no_infer else None, scope=a.scope)
    print(json.dumps({k: res[k] for k in ("kind", "fixed", "engine_used", "versions", "calls", "cost", "seconds", "stop")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
