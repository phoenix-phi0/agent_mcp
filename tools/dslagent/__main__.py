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
    r.add_argument("--wall", type=int, default=None, help="墙钟秒数；缺省：旧命令 500，--pack 的 v2 路径 900（包声明了 WALL 就用包的，如 dslproj 1800）")
    r.add_argument("--scope", help="允许改动的路径，逗号分隔（目录前缀如 kg/,tests/kg/，精确文件，或带 * 的通配如 routes/graph*.zs）；只对 v2 规划路径有效，范围外的改动恢复并要求补改；缺省取资料包的 scope_for")
    r.add_argument("--pack", help="资料包名（code / dslproj，见 packs/）：写了就走 v2 规划路径（与 DSLAGENT_PLANNER 无关），场景差异全由包声明；不写 = 旧命令（code 行为不变）")
    r.add_argument("--budget-calls", type=int, default=None, help="（--pack 时）把规划写的「预算 调用 N」至少提到这个数（只放宽不收紧），v2 的总调用上限跟着放宽；v3 change2 --max-turns 就是用它透传给修改代理的")
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
    v = sp.add_parser("v3", help="v3 流程（v3/v3.zs）：顶层规划 → 约定 → 骨架 → 分配 → 按层做模块；断了重跑同一命令即续跑；"
                       "action=build2 是最小主干新建流程（build2.zs，刻意不含接口冒烟）；action=audit/change 改走 核查.zs / 修改.zs（核查出问题清单 / 按问题清单改代码），缺省 build 是原来的新建流程")
    v.add_argument("action", nargs="?", choices=("build", "build2", "audit", "change", "audit2", "change2", "fix2", "brief"), default="build")
    v.add_argument("--req", help="需求文件（brief 以外都要）")
    v.add_argument("--project", required=True, help="项目目录（不存在就建）")
    v.add_argument("--out", help="记录目录：每步产物、检查结果、重写次数、每个模块的 v2 记录目录、花费（brief 以外都要；brief 给了就写 brief.json / brief.md，不给打印 md）")
    v.add_argument("--stop-after", choices=("top", "contract", "build"), default=None, help="跑到这一步的产物写出并通过检查就停（只对 build 有效）")
    v.add_argument("--cost-cap", type=float, default=None, help="花费上限（美元）：每次调模型之前先查，已花费达到上限就不再调、以「超出预期」结束（原因里写已花费）；最后一次调用可能略超")
    v.add_argument("--wall", type=int, default=None, help="整个流程的墙钟秒数（缺省 36000）")
    v.add_argument("--module-wall", type=int, default=1800, help="做一个模块时 v2 子进程的墙钟秒数")
    v.add_argument("--skip", default=None, help="（build2）逗号隔开的模块名：直接跳过不做，依赖它们的模块也跳过（续跑时先跳过已知会失败的模块）")
    v.add_argument("--task", default=None, help="（audit / change）这一轮要完成的具体任务，不写就是纯核查 / 按问题清单改")
    v.add_argument("--issues", default="latest", help="（change）读哪份问题清单：路径或 latest（默认最新一份）")
    v.add_argument("--llm", default="sonnet", help="（audit / change / audit2 / fix2）调模型用的模型名")
    v.add_argument("--modules", default=None, help="（audit2 / fix2）只审这些模块，逗号隔开（如 lesson,quiz；必须是有 contracts/<名>.md 的模块）：plan/audit2.json 只含它们的问题，范围外模块的全量回归不过、以及核查员指出「问题出在范围外模块」的 contract_issue / module_issue 不终止，记进 skipped_issues 后继续审；范围内模块自己的 contract_issue 照旧；缺省 = 审全部模块")
    v.add_argument("--contract-check", choices=("拦截", "提醒", "关"), default=None,
                   help="（audit2 / fix2）核查开头的约定闸（逐模块 v3/contracts.check，不调模型）：拦截（缺省）= 范围内有违约就报 contract_issue、"
                        "不跑回归不派核查员；提醒 = 照常核查，违约放进 audit2.json 的 contract_warnings；关 = 不查（同 K174 之前）。"
                        "约定里的豁免标注见 v3/contracts.py")
    v.add_argument("--rounds", type=int, default=5, help="（fix2）核查→修改最多几轮")
    v.add_argument("--impl-model", default=None, help="（change2 / fix2）modify_module（改代码的 v2 子进程）用的模型串，如 haiku；顶替 roles.zs 里它的默认模型（回退模型照旧）。"
                                                          "核查员（audit2）的模型仍是 --llm；不传 = 同旧")
    v.add_argument("--brief", action="store_true", help="（change2 / fix2）给 modify_module 附「本模块实现简报（自动推出，只是提醒）」一节"
                                                       "（v3/brief.py：骨架、依赖接口、实现要点 R1/R2/R6，只列本轮要改的函数），不给 audit2 核查员；"
                                                       "开始前把影响面建议（--modules 建议、可能漏改契约）写进日志和记录目录 brief_impact.*，不自动改 --modules")
    v.add_argument("--declare", default=None, help="（brief；change2 / fix2 要和 --brief 一起）设计声明文件：每行「旧值<Tab>新来源函数」（旧值如 enum:N5..N1、persona:老师、"
                                                       "lit:日语学习系统、re:正则；K168 domain.tsv 的 5 列格式也认）或「值域<Tab>字段<Tab>来源」。"
                                                       "给了就在约定 / services / .ui 里盘点还写死旧值的位置，并把声明的字段加进用例值域检查；只提示，不改 --modules")
    v.add_argument("--max-turns", type=int, default=8, help="（change2）每个 modify_module 代理（v2 子进程）里计划「预算 调用 N」的下限：规划写的 N 小于它就被提到它，只放宽不收紧；缺省 8，传 0 = 不干预（规划自己定）。背景：K29b 两轮 modify_module 都只用了 2 次模型调用（1 规划 + 1 派任务）就收尾，quiz 要新增 9 个函数装不下；agents.jsonl 每条记 v2_calls（上限）和 num_turns（实际）。只对 change2 生效，audit2 / fix2 / build2 / 修改 不受影响")
    ag = sp.add_parser("agents", help="子 agent 管理：角色登记表、调度层账本")
    agsp = ag.add_subparsers(dest="agents_cmd", required=True)
    st = agsp.add_parser("stats", help="按角色 / 按模型统计调用数、成功率、平均轮数、花费、用时")
    st.add_argument("--out", nargs="+", required=True, help="一个或多个账本目录（扫目录下全部 *.jsonl）或 jsonl 文件")
    a = ap.parse_args(argv)
    if a.cmd == "agents":
        from . import ledger as L
        if a.agents_cmd == "stats":
            print(json.dumps(L.stats(L.read_all(a.out)), ensure_ascii=False))
        return 0
    if a.cmd == "v3":
        from .v3 import core as V3
        from . import engines as EG
        if (a.impl_model or a.brief) and a.action not in ("change2", "fix2"):
            ap.error("--impl-model / --brief 只对 change2 / fix2 有效")
        if a.contract_check and a.action not in ("audit2", "fix2"):
            ap.error("--contract-check 只对 audit2 / fix2 有效")
        declare = None
        if a.declare:
            if a.action not in ("brief", "change2", "fix2") or (a.action != "brief" and not a.brief):
                ap.error("--declare 只对 brief，以及带 --brief 的 change2 / fix2 有效")
            if not Path(a.declare).is_file():
                ap.error(f"--declare 文件不存在：{a.declare}")
            from .v3 import brief as BR
            declare = BR.load_declare(a.declare)
            for p in declare["问题"]:
                print(f"[设计声明] {p}", file=sys.stderr)
        if a.impl_model:
            try:
                EG.parse(a.impl_model)
            except ValueError as e:
                ap.error(f"--impl-model：{e}")
        if a.action == "brief":
            from .v3 import brief as BR
            names = [m.strip() for m in (a.modules or "").split(",") if m.strip()] or None
            b = BR.main(a.project, modules=names, out=a.out, declare=a.declare)
            imp = b["影响面"] or {}
            print(json.dumps({"模块": [m["模块"] for m in b["模块"]], "要点数": sum(len(f["要点"]) for m in b["模块"] for f in m["函数"]),
                              "建议模块": imp.get("建议模块"), "可能漏改契约": imp.get("可能漏改契约"), "out": a.out}, ensure_ascii=False))
            return 0
        if not a.req or not a.out:
            ap.error("v3 除 brief 外都要 --req 和 --out")
        def on_term(*_):
            EG.kill_all()
            raise SystemExit(143)
        signal.signal(signal.SIGTERM, on_term)
        req_text = Path(a.req).read_text(encoding="utf-8")
        if a.action in ("audit2", "change2", "fix2"):   # 最小主干：audit2.zs / change2.zs / fix2.zs（循环：核查→改）
            if a.modules and a.action == "change2":
                ap.error("--modules 只对 audit2 / fix2 有效")
            names = [m.strip() for m in (a.modules or "").split(",") if m.strip()]
            if a.modules is not None and not names:
                ap.error("--modules 不能是空的")
            miss = [m for m in names if not (Path(a.project) / "contracts" / f"{m}.md").is_file()]
            if miss:
                ap.error(f"--modules 里的模块没有 contracts/<名>.md：{','.join(miss)}")
            scope = {"scope": "|" + "|".join(names) + "|", "modules": ",".join(names)} if names else {}
            if a.contract_check:
                scope["contract_check"] = a.contract_check
            extra = ({"issues": a.issues} if a.action == "change2"
                     else {"llm": a.llm, "rounds": a.rounds, **scope} if a.action == "fix2" else {"llm": a.llm, **scope})
            res = V3.run_entry(a.action, a.project, a.out, req_text, extra_vars=extra,
                               cost_cap=a.cost_cap, **({"wall": a.wall} if a.wall else {}), module_wall=a.module_wall,
                               **({"module_calls": a.max_turns} if a.action == "change2" else {}),
                               **({"impl_model": a.impl_model} if a.impl_model else {}), **({"brief": True} if a.brief else {}),
                               **({"declare": declare} if declare else {}))
            print(json.dumps({k: res.get(k) for k in ("status", "reason", "at", "花费", "用时", "模型调用", "returned")}, ensure_ascii=False))
            return 0 if res["status"] == "成功" else 1
        if a.action == "audit":
            res = V3.run_entry("核查", a.project, a.out, req_text,
                               extra_vars={"task": a.task or "", "llm": a.llm},
                               cost_cap=a.cost_cap, **({"wall": a.wall} if a.wall else {}))
            print(json.dumps({k: res.get(k) for k in ("status", "reason", "at", "花费", "用时", "模型调用", "returned")}, ensure_ascii=False))
            return 0 if res["status"] == "成功" else 1
        if a.action == "change":
            res = V3.run_entry("修改", a.project, a.out, req_text,
                               extra_vars={"issues": a.issues, "task": a.task or "", "llm": a.llm},
                               cost_cap=a.cost_cap, **({"wall": a.wall} if a.wall else {}), module_wall=a.module_wall)
            print(json.dumps({k: res.get(k) for k in ("status", "reason", "at", "花费", "用时", "模型调用", "returned")}, ensure_ascii=False))
            return 0 if res["status"] == "成功" else 1
        res = V3.run(req_text, a.project, a.out, stop_after=a.stop_after, cost_cap=a.cost_cap,
                     **({"wall": a.wall} if a.wall else {}), module_wall=a.module_wall,
                     **({"script": "build2"} if a.action == "build2" else {}), **({"skip": a.skip} if a.skip else {}))
        print(json.dumps({k: res.get(k) for k in ("status", "reason", "at", "花费", "用时", "模型调用")}, ensure_ascii=False))
        return 0 if res["status"] == "成功" else 1
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
        from . import engines as EG
        EG.kill_all()
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, on_term)
    if a.pack:
        from . import entry
        res = entry.run_pack(a.project, _task(a), a.pack, a.out, scope=a.scope, test_cmd=a.test_cmd, wall=a.wall,
                             **({"budget_calls": a.budget_calls} if a.budget_calls else {}))
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
