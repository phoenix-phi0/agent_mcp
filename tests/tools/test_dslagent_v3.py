# -*- coding: utf-8 -*-
"""dslagent v3：顶层解析 / 检查 / 依赖分层、约定检查（与 top 不一致…）、提示词示例、生成骨架（加载检查过）、生成分配、
state 续跑（约定改了要重做）、并行执行、脚本动词里的终止往外传、做模块组（重试 / 末次换模型 / 失败终止 / 组内并行）、
v3.zs 用假模型空跑整条流程（四步都走到，续跑时跳过已完成）、--stop-after、花费上限。不调真模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_v3.py

做模块的子进程用 fixtures/v3_stub_module.py 替身（把参考实现 fixtures/v3_solution 里属于该模块的文件拷进去）；
参考实现有三个模块：graph、vocab（依赖 graph）、progress（依赖 graph）。
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_v3_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
for k in ("DSLAGENT_PLANNER", "DSLAGENT_PACK", "DSLAGENT_VERIFY", "DSLAGENT_PLAN_MODE", "DSL_NOW", "DSLAGENT_V3_MODULE_CMD"):
    os.environ.pop(k, None)

from tools import DSLEngine                                       # noqa: E402
from tools.mock import MockClient                                 # noqa: E402
from tools.dslagent import common as CM                           # noqa: E402
from tools.dslagent.packs.dslproj import contract as DC           # noqa: E402
from tools.dslagent.v3 import contracts as VC, core, planning as PL, scaffold as SF, top as VT   # noqa: E402

SOL = ROOT / "tests" / "tools" / "fixtures" / "v3_solution"
STUB = ROOT / "tests" / "tools" / "fixtures" / "v3_stub_module.py"
CMD = [sys.executable, str(STUB)]
PASS = FAIL = 0
N = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def fresh(name):
    global N
    N += 1
    p = TMP / f"{name}{N}"
    shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True)
    return p


def contract_text(m):
    return (SOL / "contracts" / f"{m}.md").read_text(encoding="utf-8")


TOP3 = "项目 demo\n模块 graph        # 知识图谱\n模块 vocab 依赖 graph\n模块 progress 依赖 graph\n"


class Fake:
    """假模型：按 tag 回答；scripts：{tag: [第 1 次回复, 第 2 次回复, …]}（用完用最后一个）；缺省顶层 = TOP3，约定 = 参考实现。"""

    def __init__(self, top=TOP3, scripts=None):
        self.top, self.scripts, self.calls = top, scripts or {}, []

    def __call__(self, system, user, tag, timeout, **kw):
        self.calls.append({"tag": tag, "user": user, "system": system, "model": kw.get("model")})
        seq = self.scripts.get(tag)
        if seq:
            n = sum(1 for c in self.calls if c["tag"] == tag)
            return {"text": seq[min(n, len(seq)) - 1], "cost": 0.01}
        if tag == "v3_top":
            return {"text": self.top, "cost": 0.01}
        return {"text": contract_text(tag.replace("v3_contract_", "")), "cost": 0.01}

    def n(self, prefix=""):
        return sum(1 for c in self.calls if c["tag"].startswith(prefix))


def stub_env(state, plan=None, sleep=0.0):
    os.environ["V3_STUB_SOL"] = str(SOL)
    os.environ["V3_STUB_STATE"] = str(state)
    os.environ["V3_STUB_SLEEP"] = str(sleep)
    if plan is not None:
        pf = state.parent / "stub_plan.json"
        pf.write_text(json.dumps(plan), encoding="utf-8")
        os.environ["V3_STUB_PLAN"] = str(pf)
    else:
        os.environ.pop("V3_STUB_PLAN", None)


def stub_calls(state):
    f = Path(state) / "calls.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.is_file() else []


def run_v3(proj, out, backend, **kw):
    return core.run("需求：做一个学习系统（测试）", proj, out, backend=backend, module_cmd=CMD, **kw)


# ------------------------------------------------------------------ 顶层解析 / 检查 / 分层

def test_top():
    print("顶层解析 / 检查")
    ok = VT.check(TOP3)
    check(ok == [], "三模块的 top 通过检查", ok)
    top = VT.parse(TOP3)[0]
    check(top["项目"] == "demo" and [m["名"] for m in top["模块"]] == ["graph", "vocab", "progress"], "解析出项目和模块", top)
    check(top["模块"][1]["依赖"] == ["graph"], "依赖解析（注释被去掉）", top)
    p = VT.check("项目 demo\n模块 a 依赖 nothere\n")
    check(any("nothere" in x and "没有写成模块" in x for x in p), "缺依赖被查出", p)
    p = VT.check("项目 demo\n模块 a 依赖 b\n模块 b 依赖 c\n模块 c 依赖 a\n")
    check(any("成环" in x for x in p), "成环被查出", p)
    p = VT.check("项目 demo\n模块 a 依赖 a\n")
    check(any("依赖了自己" in x for x in p), "自依赖被查出", p)
    p = VT.check("项目 demo\n模块 Graph\n模块 知识图谱\n模块 my-mod\n")
    check(sum("snake" in x for x in p) == 3, "非 snake 的模块名都被查出", p)
    p = VT.check("项目 Demo\n模块 a\n")
    check(any("项目名" in x for x in p), "项目名非 snake 被查出", p)
    p = VT.check("项目 demo\n模块 a\n职责 管数据\n")
    check(any("只能写" in x for x in p), "多余的语句被查出", p)
    p = VT.check("模块 a\n模块 a\n")
    check(any("缺「项目" in x for x in p) and any("重复" in x for x in p), "缺项目 / 模块重复", p)
    p = VT.check("项目 demo\n")
    check(any("一个模块都没写" in x for x in p), "没有模块被查出", p)
    check(VT.check("```\n项目 demo\n模块 a  # 说明\n```\n") == [], "代码围栏被忽略")
    check(VT.layers(top) == [["graph"], ["vocab", "progress"]], "依赖分层", VT.layers(top))
    t2 = VT.parse("项目 d\n模块 tutor 依赖 progress vocab\n模块 progress 依赖 graph\n模块 vocab 依赖 graph\n模块 graph\n")[0]
    check(VT.layers(t2) == [["graph"], ["progress", "vocab"], ["tutor"]], "多层分层", VT.layers(t2))
    try:
        VT.load("项目 d\n模块 a 依赖 b\n")
        check(False, "load 不通过要抛 ValueError")
    except ValueError:
        check(True, "load 不通过抛 ValueError")


# ------------------------------------------------------------------ 约定检查

def project_with_contracts(mods=("graph",)):
    p = fresh("proj")
    (p / "contracts").mkdir()
    for m in mods:
        shutil.copy(SOL / "contracts" / f"{m}.md", p / "contracts" / f"{m}.md")
    return p


def test_contract_check():
    print("约定检查")
    top = VT.load(TOP3)
    p = project_with_contracts()
    check(VC.check(contract_text("graph"), "graph", top, p) == [], "graph 约定通过")
    check(VC.check(contract_text("progress"), "progress", top, p) == [], "progress 约定（上游 graph 已通过）通过")
    probs = VC.check(contract_text("progress"), "progress", top, fresh("empty"))
    check(any("还没有约定文件" in x for x in probs), "上游约定还没通过时不放行", probs)
    # 与 top 不一致：多依赖 / 少依赖
    t2 = VT.load("项目 demo\n模块 graph\n模块 progress 依赖 graph vocab\n模块 vocab 依赖 graph\n")
    probs = VC.check(contract_text("progress"), "progress", t2, p)
    check(any("两边要一致" in x for x in probs), "约定的依赖与 top 不一致被查出", probs)
    t3 = VT.load("项目 demo\n模块 graph\n模块 progress\n")
    probs = VC.check(contract_text("progress"), "progress", t3, p)
    check(any("两边要一致" in x for x in probs), "top 里没有依赖而约定写了依赖被查出", probs)
    probs = VC.check(contract_text("graph"), "other", top, p)
    check(any("不在 plan/top.zs" in x for x in probs), "模块不在 top 里", probs)
    # 表名前缀
    bad = contract_text("graph").replace("graph_point", "points")
    probs = VC.check(bad, "graph", top, p)
    check(any("要以「graph_」开头" in x for x in probs), "表名不带模块前缀被查出", probs)
    # 跨模块调用必须是依赖且上游有该公开函数
    bad = contract_text("progress").replace("调用 graph.取知识点 code", "调用 graph.不存在 code", 1)
    probs = VC.check(bad, "progress", top, p)
    check(any("没有公开函数" in x for x in probs), "调用上游没有的函数被查出", probs)
    bad = contract_text("vocab").replace("依赖 graph", "依赖 无", 1)
    probs = VC.check(bad, "vocab", top, p)
    check(any("不在本模块的「依赖」里" in x for x in probs), "调用了不在依赖里的模块被查出", probs)
    # 公开函数没有用例 / 接口指向私有
    bad = contract_text("graph")
    bad = bad[:bad.index("用例 加边_成功")] + "\n"
    cut = bad.split("## 用例")[0] + "## 用例\n用例 取知识点_取到\n  先 数据 graph_point code=P1 title=一\n  调用 取知识点 code=P1\n  得 code=P1\n"
    probs = VC.check(cut, "graph", top, p)
    check(any("一条验收用例都没有" in x for x in probs), "公开函数没用例被查出", probs)
    probs = VC.check(contract_text("graph").replace("-> 加边", "-> 没有这个"), "graph", top, p)
    check(any("不是本模块的公开函数" in x for x in probs), "接口指向非公开函数被查出", probs)
    bad = contract_text("graph").replace("公开 函数 取知识点 code", "公开 函数 取知识点 code extra?", 1).replace(
        "调用 取知识点 code=P1\n  得 code=P1 title=一次函数", "调用 取知识点 code=P1 extra=空\n  得 code=P1 title=一次函数", 1)
    probs = VC.check(bad, "graph", top, p)
    check(any("可选入参 extra 传了「空」" in x for x in probs), "给可选入参传「空」的用例被查出", probs)
    check(VC.check(bad.replace(" extra=空", ""), "graph", top, p) == [], "不传可选入参的用例通过")
    probs = VC.check("这不是约定", "graph", top, p)
    check(probs != [], "格式不对被查出", probs)
    # 模型把 ``` 围栏带进来：写规划时 clean 掉
    check(PL.check(type("C", (), {"top_path": lambda s: p / "plan" / "top.zs", "project": p})(), "顶层", "```\n项目 d\n模块 a\n```") == [], "顶层检查忽略围栏")


def test_prompt_example():
    print("提示词")
    for name in ("top.md", "contract.md"):
        t = core.prompt_text(name)
        check(all(h in t for h in ("# 任务描述", "# 入参", "# 出参", "# 处理逻辑")), f"{name} 是 任务描述 + 入参 + 出参 + 处理逻辑", t[:80])
    t = core.prompt_text("contract.md")
    block = t.split("# 完整示例")[1].split("```")[1]
    top = VT.load("项目 demo\n模块 graph\n模块 progress 依赖 graph\n")
    p = project_with_contracts()
    probs = VC.check(block.strip() + "\n", "progress", top, p)
    check(probs == [], "contract.md 里的完整示例自己能通过约定检查", probs)
    ex = core.prompt_text("top.md").split("输出：")[1]
    lines = "\n".join(l.strip() for l in ex.splitlines() if l.strip())
    check(VT.check(lines) == [], "top.md 里的小例子能通过顶层检查", VT.check(lines))
    check("职责" in core.prompt_text("top.md") and "注释" in core.prompt_text("top.md"), "top.md 说明不写职责等、说明写注释")
    check("需求是唯一来源" in t and "不得编造" in t, "contract.md 要求不得编造需求以外的功能")


# ------------------------------------------------------------------ 骨架 / 分配 / state

def test_skeleton_build_state():
    print("生成骨架 / 生成分配 / state")
    p = project_with_contracts(("graph", "vocab", "progress"))
    top = VT.load(TOP3)
    r = SF.gen_skeleton(p, top)
    check(len(r["新建"]) == 9 and r["问题"] == [], "三个模块各生成实体 / 业务 / 接口，加载检查过", r)
    svc = (p / "services" / "progress.zs").read_text(encoding="utf-8")
    check("业务 progress" in svc and "依赖 graph" in svc and "公开 函数 记作答 learner point_code correct" in svc
          and "报错 未实现" in svc and "# 伪代码" not in svc and "# 调用 graph.取知识点" in svc, "业务骨架：函数头 + 伪代码注释 + 未实现", svc)
    ent = (p / "entities" / "progress.entity").read_text(encoding="utf-8")
    check("实体 progress_answer" in ent and "字段 learner 文本 必填" in ent and "字段 id" not in ent, "实体骨架：表和字段（id 隐含）", ent)
    rt = (p / "routes" / "progress.zs").read_text(encoding="utf-8")
    check("接口 POST /progress/answer" in rt and "调用 progress.记作答 learner={learner} point_code={point_code} correct={correct}" in rt, "接口骨架：头 + 调用", rt)
    g = (p / "routes" / "graph.zs").read_text(encoding="utf-8")
    check("接口 GET /graph/point" in g and "接口 POST /graph/edge" in g, "一个模块多个接口", g)
    # 已存在的不覆盖
    (p / "services" / "graph.zs").write_text("业务 graph\n  用包 db\n  公开 函数 取知识点 code\n    返回 {\"x\": 1}\n  结束\n结束\n", encoding="utf-8")
    r2 = SF.gen_skeleton(p, top)
    check(r2["新建"] == [] and len(r2["已有"]) == 9, "已存在的文件不覆盖", r2)
    check("返回" in (p / "services" / "graph.zs").read_text(encoding="utf-8"), "改过的 services/graph.zs 原样保留")
    # 可选入参用 {x 或}
    c, _ = VC.load(p, "progress")
    c["函数"][0]["入参"].append("pass_line?")
    c["接口"].append({"方法": "GET", "路径": "/progress/x", "函数": "记作答", "行": 1})
    check("pass_line={pass_line 或}" in SF.route_text("progress", c), "可选入参用 {x 或}")
    # 缺约定
    try:
        SF.gen_skeleton(fresh("noc"), top)
        check(False, "缺约定要抛 ValueError")
    except ValueError as e:
        check("缺约定" in str(e), "缺约定抛 ValueError", e)
    # 分配
    text = SF.build_text(top)
    check(text.splitlines()[1:] == ["用包 v3", "做模块组 graph", "做模块组 vocab,progress", "终止 成功 全部模块完成"], "build.zs 按依赖分层", text)
    check((p / SF.gen_build(p, top)).read_text(encoding="utf-8") == text, "生成分配写 plan/build.zs")
    # state：约定 hash 变了视为未完成
    ctx = core.Ctx(p, fresh("out"), "x", None)
    check(ctx.is_done("graph") is False, "没记过 = 未完成")
    ctx.mark_done("graph")
    check(ctx.is_done("graph") is True and ctx.is_done("vocab") is False, "标记完成后已完成，别的模块不受影响")
    st = json.loads((p / "plan" / "state.json").read_text(encoding="utf-8"))
    check(st["模块"]["graph"]["通过"] and len(st["模块"]["graph"]["约定hash"]) == 64, "state.json 记通过 + 约定 hash", st)
    f = p / "contracts" / "graph.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n# 改了\n", encoding="utf-8")
    check(ctx.is_done("graph") is False, "约定改了视为未完成")
    f.write_text(f.read_text(encoding="utf-8").replace("\n# 改了\n", "\n"), encoding="utf-8")
    check(ctx.is_done("graph") is True, "约定改回去又算已完成（hash 一致）")
    f.write_text(f.read_text(encoding="utf-8").replace("\n", "\r\n"), encoding="utf-8", newline="")
    check(ctx.is_done("graph") is True, "只换行符不同 hash 不变")


# ------------------------------------------------------------------ 引擎：脚本动词里的终止、并行执行

def engine(workdir):
    return DSLEngine(MockClient(handler=lambda p, s=None: "嗯", offline=True), workdir=workdir, verbose=False,
                     verbs_root=CM.VERBS)


def test_engine_bits():
    print("脚本动词的终止往外传 / 并行执行")
    w = fresh("eng")
    vroot = fresh("verbs")
    (vroot / "tv").mkdir()
    (vroot / "tv" / "停一下.zs").write_text("# 停一下：终止\n# 参数：x\n终止 失败 停了{x}\n", encoding="utf-8")
    (vroot / "tv" / "_verbs.py").write_text("from pathlib import Path\nfrom tools.verbs import scan_verbs\nWORKSPACE=Path('.')\nPACK_DIR=Path('.')\n"
                                            "def register(reg, ws):\n    scan_verbs(reg, PACK_DIR, ws, pack_dir=PACK_DIR)\n", encoding="utf-8")
    e = DSLEngine(MockClient(handler=lambda p, s=None: "嗯", offline=True), workdir=w, verbose=False, verbs_root=vroot)
    e.run("用包 tv\n停一下 7\n打印 不该到这里\n")
    check(e.halted and e.halted["状态"] == "失败" and e.halted["原因"] == "停了7" and "不该到这里" not in "\n".join(e.output),
          "没接结果：脚本动词里的终止结束调用方", (e.halted, e.output))
    e = DSLEngine(MockClient(handler=lambda p, s=None: "嗯", offline=True), workdir=w, verbose=False, verbs_root=vroot)
    e.run("用包 tv\n设 r = 停一下 7\n打印 接着走 {r.状态} {r.原因}\n")
    check(e.halted is None and "接着走 失败 停了7" in "\n".join(e.output), "接了结果：拿到 {状态, 原因, 停在}，接着走", (e.halted, e.output))
    # 并行执行
    (w / "ok.zs").write_text("返回 {\"v\": \"{x}\"}\n", encoding="utf-8")
    (w / "bad.zs").write_text("终止 失败 boom\n", encoding="utf-8")
    (w / "err.zs").write_text("读取 t = 不存在的文件.txt\n", encoding="utf-8")
    (w / "slow.zs").write_text("设 n = 1\n", encoding="utf-8")
    e = engine(w)
    e.vars["jobs"] = ["ok.zs x=1", "bad.zs", "err.zs", "ok x=4", "nothere.zs"]
    e.run("用包 common\n设 rs = 并行执行 {jobs} 并发=2\n返回 {rs}\n")
    rs = e.returned[0] if e.returned else None
    check(isinstance(rs, list) and len(rs) == 5, "返回结果列表，长度同输入", rs)
    if isinstance(rs, list) and len(rs) == 5:
        check([r["状态"] for r in rs] == ["成功", "失败", "失败", "成功", "失败"], "单个失败 / 出错不影响别的项，顺序同输入", [r["状态"] for r in rs])
        check(rs[0]["返回"] == {"v": "1"} and rs[3]["返回"] == {"v": "4"}, "子脚本的返回值带回来", rs)
        check(rs[1]["原因"] == "boom", "终止的原因带回来", rs[1])
        check("不存在" in rs[2]["原因"] or "找不到" in rs[2]["原因"], "脚本出错：状态失败 + 原因", rs[2])
        check("找不到子脚本" in rs[4]["原因"], "找不到子脚本：状态失败", rs[4])
    # 对象形式：值可以带空格 / 换行；每项独立作用域；脚本动词按声明绑默认值
    (w / "echo.zs").write_text("返回 {a}\n", encoding="utf-8")
    e = engine(w)
    e.vars["jobs"] = [{"脚本": "echo", "参数": {"a": "有 空格\n和换行"}}, {"脚本": "echo", "参数": {}}]
    e.run("用包 common\n设 rs = 并行执行 {jobs}\n返回 {rs}\n")
    rs = e.returned[0]
    check(rs[0]["返回"] == "有 空格\n和换行", "对象形式的参数可以带空格和换行", rs)
    check(rs[1]["返回"] == "{a}", "每项独立作用域（上一项的变量不串过来）", rs)
    # 并发：同时在跑的数目 = 并发（用 sleep 脚本动词量）
    pk = fresh("vp") / "pp"
    pk.mkdir()
    os.symlink(ROOT / "verbs" / "common", pk.parent / "common")
    (pk / "_verbs.py").write_text(
        "import threading, time\nfrom pathlib import Path\nLOCK = threading.Lock()\nSTATE = {'now': 0, 'max': 0}\n"
        "WORKSPACE = Path('.')\nPACK_DIR = Path('.')\n"
        "def register(reg, ws):\n    @reg.verb('睡')\n    def 睡(秒: str = '0.3') -> str:\n"
        "        with LOCK:\n            STATE['now'] += 1\n            STATE['max'] = max(STATE['max'], STATE['now'])\n"
        "        time.sleep(float(秒))\n        with LOCK:\n            STATE['now'] -= 1\n        return str(STATE['max'])\n", encoding="utf-8")
    (pk / "睡一下.zs").write_text("# 睡一下\n# 参数：秒=0.3\n用包 pp\n设 m = 睡 {秒}\n返回 {m}\n", encoding="utf-8")
    for conc, want in (("1", 1), ("3", 3)):
        e = DSLEngine(MockClient(handler=lambda p, s=None: "嗯", offline=True), workdir=w, verbose=False, verbs_root=pk.parent)
        t0 = time.time()
        e.vars["jobs"] = ["睡一下", "睡一下", "睡一下"]
        e.run(f"用包 common pp\n设 rs = 并行执行 {{jobs}} 并发={conc}\n返回 {{rs}}\n")
        el = time.time() - t0
        rs = e.returned[0]
        check(all(r["状态"] == "成功" for r in rs), f"脚本动词当子脚本，并发={conc} 全部成功", rs)
        check((el >= 0.85) if conc == "1" else (el < 0.85), f"并发={conc}：耗时 {el:.2f}s", el)


# ------------------------------------------------------------------ 整条流程（假模型 + 替身子进程）

def test_full_flow_clean():
    print("v3.zs 整条流程：重写 / 续跑 / 跳过")
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    fk = Fake(scripts={
        "v3_top": ["项目 Demo\n模块 Graph\n", TOP3],
        "v3_contract_progress": [contract_text("progress").replace("依赖 graph", "依赖 无", 1), contract_text("progress")],
    })
    res = run_v3(proj, out, fk)
    check(res["状态"] == "成功" and res["原因"] == "全部模块完成", "整条流程成功", {k: res[k] for k in ("状态", "原因", "输出")})
    rec = res["记录"]
    top_ev = [r for r in rec["规划"] if r["种类"] == "顶层" and r["事件"] == "检查"]
    check([r["通过"] for r in top_ev] == [False, True], "顶层：第 1 次不过、重写后通过", top_ev)
    check("【检查发现的问题" in fk.calls[1]["user"] and "snake" in fk.calls[1]["user"] and "项目 Demo" in fk.calls[1]["user"],
          "重写时带上次的内容和问题", fk.calls[1]["user"][-400:])
    check(fk.calls[0]["system"].startswith("# 任务描述") and "【需求】" in fk.calls[0]["user"], "顶层提示词 = prompts/top.md，入参有需求")
    pg = [r for r in rec["规划"] if r["模块"] == "progress" and r["事件"] == "检查"]
    check([r["通过"] for r in pg] == [False, True] and "两边要一致" in json.dumps(pg[0]["问题"], ensure_ascii=False), "约定：progress 第 1 次依赖对不上 top，重写后通过", pg)
    cu = [c for c in fk.calls if c["tag"] == "v3_contract_progress"][0]["user"]
    check("【顶层规划 plan/top.zs】" in cu and "项目 demo" in cu and "### 上游模块 graph（直接依赖，可以调用）" in cu and "用例 加边_成功" not in cu and "公开 函数 取知识点" in cu,
          "约定输入 = 需求 + top.zs + 上游已通过的约定（去掉用例）", cu[-600:])
    check(fk.n("v3_contract_") == 4 and fk.n("v3_top") == 2, "模型调用：顶层 2 次、约定 4 次（progress 重写 1 次）", [c["tag"] for c in fk.calls])
    for m in ("graph", "vocab", "progress"):
        check((proj / "contracts" / f"{m}.md").is_file() and (proj / "services" / f"{m}.zs").is_file(), f"{m}：约定和实现都在")
    check((proj / "plan" / "build.zs").read_text(encoding="utf-8").count("做模块组") == 2, "plan/build.zs 生成了（两层）")
    check(sorted(json.loads((proj / "plan" / "state.json").read_text(encoding="utf-8"))["模块"]) == ["graph", "progress", "vocab"], "state.json 三个模块都标了通过")
    check({r["模块"] for r in rec["模块"]} == {"graph", "vocab", "progress"} and len(rec["模块"]) == 3, "每个模块做了 1 轮", rec["模块"])
    check(abs(res["花费"] - (0.01 * 6 + 0.25 * 3)) < 1e-6, "总花费 = 规划 + 模块", res["花费"])
    check(all((Path(r["记录目录"]) / "task.txt").is_file() for r in rec["模块"]), "每个模块的记录目录有任务文件")
    check((out / "result.json").is_file() and (out / "v3_log.jsonl").is_file() and (out / "steps" / "top_w2.txt").is_file(), "out 里有 result.json / v3_log.jsonl / steps/")
    # 同层并行：vocab 与 progress 在一层，各自都收到任务
    calls = stub_calls(state)
    check(sorted(c["模块"] for c in calls) == ["graph", "progress", "vocab"], "做模块各调 1 次", calls)
    check(all(json.loads(c["models"])["plan"] == "sonnet" for c in calls), "非末次用 sonnet", [c["models"] for c in calls])
    # 续跑：同一命令再跑 → 规划不重写、模块不重做
    fk2, n_stub = Fake(), len(calls)
    res2 = run_v3(proj, out, fk2)
    check(res2["状态"] == "成功" and fk2.calls == [], "续跑：已通过的规划一个模型调用都没有", [c["tag"] for c in fk2.calls])
    check(len(stub_calls(state)) == n_stub and res2["模块花费"] == 0, "续跑：已完成且约定未变的模块不重做", stub_calls(state)[n_stub:])
    check((out / "result_run1.json").is_file() and (out / "result.json").is_file(), "续跑：上一次的 result.json 留成 result_run1.json")
    names = sorted(f.name for f in (out / "calls").glob("*.prompt.txt"))
    check(len(names) == len(set(n.split("_", 1)[0] for n in names)) == 6, "calls/ 里每次调用一个文件，没有被覆盖", names)
    # 约定改了 → 只重做那个模块
    f = proj / "contracts" / "vocab.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n# 改了一行注释\n", encoding="utf-8")
    fk3 = Fake()
    res3 = run_v3(proj, out, fk3)
    again = stub_calls(state)[n_stub:]
    check(res3["状态"] == "成功" and fk3.calls == [] and [c["模块"] for c in again] == ["vocab"], "续跑：约定改了的模块重做，别的不动", again)
    check(sorted(d.name for d in (out / "modules" / "vocab").iterdir()) == ["r1", "r2"], "续跑：模块轮号接着走，上一次的记录目录还在", sorted(d.name for d in (out / "modules" / "vocab").iterdir()))
    # 约定被改坏（与 top 不一致）→ 续跑时只重写它，且重写的输入带盘上那份和问题
    f.write_text(f.read_text(encoding="utf-8").replace("依赖 graph", "依赖 无", 1), encoding="utf-8")
    fk4 = Fake()
    res4 = run_v3(proj, out, fk4)
    check(res4["状态"] == "成功" and [c["tag"] for c in fk4.calls] == ["v3_contract_vocab"], "续跑：不过检查的约定重写，别的跳过", [c["tag"] for c in fk4.calls])
    u = fk4.calls[0]["user"]
    check("【你上次写的内容】" in u and "两边要一致" in u and "依赖 无" in u, "续跑重写时输入带盘上那份约定和检查问题", u[-500:])


def test_stop_after():
    print("--stop-after")
    for stop, has_contracts, has_skel, has_build, mods in (("top", False, False, False, 0), ("contract", True, False, False, 0), ("build", True, True, True, 0)):
        proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
        stub_env(state)
        fk = Fake()
        res = run_v3(proj, out, fk, stop_after=stop)
        check(res["状态"] == "成功" and "停在" in res["原因"], f"stop-after={stop}：成功并说明停在哪", (res["状态"], res["原因"]))
        check((proj / "plan" / "top.zs").is_file(), f"stop-after={stop}：top.zs 写了")
        check((proj / "contracts" / "graph.md").is_file() == has_contracts, f"stop-after={stop}：约定 {'写了' if has_contracts else '没写'}")
        check((proj / "services" / "graph.zs").is_file() == has_skel, f"stop-after={stop}：骨架 {'生成了' if has_skel else '没生成'}")
        check((proj / "plan" / "build.zs").is_file() == has_build, f"stop-after={stop}：build.zs {'生成了' if has_build else '没生成'}")
        check(stub_calls(state) == [], f"stop-after={stop}：没有做任何模块")
    try:
        core.run("x", fresh("p"), fresh("o"), stop_after="nonsense", backend=Fake())
        check(False, "stop-after 不认识要报错")
    except ValueError:
        check(True, "stop-after 不认识报错")


def test_top_fails():
    print("三次不过终止失败")
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    fk = Fake(scripts={"v3_top": ["项目 demo\n模块 A\n"]})
    res = run_v3(proj, out, fk)
    check(res["状态"] == "失败" and "写了 3 次都没通过检查" in res["原因"] and fk.n("v3_top") == 3, "顶层 3 次不过：终止 失败，写了 3 次", (res["状态"], res["原因"]))
    check(not (proj / "plan" / "top.zs").exists() and not (proj / "contracts").exists(), "没通过的不存，后面的步骤不走")
    # 约定 3 次不过：只有这个模块失败，同层别的模块写完
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    fk = Fake(scripts={"v3_contract_vocab": ["这不是约定"]})
    res = run_v3(proj, out, fk)
    check(res["状态"] == "失败" and "vocab：" in res["原因"] and "progress：" not in res["原因"], "约定：vocab 3 次不过，终止 失败，原因点名 vocab", res["原因"])
    check(fk.n("v3_contract_vocab") == 3 and fk.n("v3_contract_progress") == 1 and (proj / "contracts" / "progress.md").is_file(),
          "同层别的模块照常写完（progress 1 次通过），失败的模块只重写自己", [c["tag"] for c in fk.calls])
    check(not (proj / "services").exists() and stub_calls(state) == [], "约定没全过：不生成骨架、不做模块")
    # 续跑：已通过的约定不重写
    fk2 = Fake()
    res2 = run_v3(proj, out, fk2)
    check(res2["状态"] == "成功" and sorted(c["tag"] for c in fk2.calls) == ["v3_contract_vocab"], "续跑：只补写没通过的 vocab", [c["tag"] for c in fk2.calls])


def test_group_retry():
    print("做模块组：重试 / 末次换模型 / 失败终止 / 组内并行")
    # graph 前两轮没做成（验收不过），第 3 轮（末次，opus）做成
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state, plan={"graph": 2})
    res = run_v3(proj, out, Fake())
    calls = [c for c in stub_calls(state) if c["模块"] == "graph"]
    check(res["状态"] == "成功" and len(calls) == 3, "graph 做了 3 轮后通过", (res["状态"], res["原因"], len(calls)))
    ms = [json.loads(c["models"])["plan"] for c in calls]
    check(ms == ["sonnet", "sonnet", "opus"], "末次换模型（前两轮 sonnet，第 3 轮 opus）", ms)
    check(set(json.loads(calls[2]["models"]).values()) == {"opus"}, "末次所有步骤都用 opus", calls[2]["models"])
    check("上一轮没有做成" not in calls[0]["task"] and "上一轮没有做成" in calls[1]["task"] and "上一轮没有做成" in calls[2]["task"], "第 2、3 轮的任务带上一轮的失败原因", calls[1]["task"])
    check("加载检查" in calls[1]["task"] and "比对约定" in calls[1]["task"] and "跑用例" in calls[1]["task"], "失败原因含三项验收的结果", calls[1]["task"])
    acc = [r for r in res["记录"]["验收"] if r["模块"] == "graph"]
    check([r["通过"] for r in acc] == [False, False, True], "验收记录：否 否 是", acc)
    rounds = [r for r in res["记录"]["模块"] if r["模块"] == "graph"]
    check([r["轮"] for r in rounds] == [1, 2, 3] and [r["模型"] for r in rounds] == ["sonnet", "sonnet", "opus"], "每个模块的轮数 / 模型有记录", rounds)
    # progress 三轮都不行：vocab 仍然做完，整体 终止 失败
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state, plan={"progress": 99}, sleep=0.5)
    t0 = time.time()
    res = run_v3(proj, out, Fake())
    calls = stub_calls(state)
    check(res["状态"] == "失败" and "progress" in res["原因"] and "3 次" in res["原因"] and "vocab" not in res["原因"], "有模块 3 次没过：终止 失败，原因写模块名和失败原因", res["原因"][:300])
    check(sum(c["模块"] == "progress" for c in calls) == 3 and sum(c["模块"] == "vocab" for c in calls) == 1, "progress 做 3 轮，vocab 做 1 轮就过", [(c["模块"], c["轮"]) for c in calls])
    st = json.loads((proj / "plan" / "state.json").read_text(encoding="utf-8"))["模块"]
    check("vocab" in st and "graph" in st and "progress" not in st, "等组内其他模块做完：vocab 已标记完成，progress 没有", st)
    v1 = next(c for c in calls if c["模块"] == "vocab")
    p1 = next(c for c in calls if c["模块"] == "progress" and c["轮"] == 1)
    check(abs(v1["t"] - p1["t"]) < 0.4, "同层两个模块并行开工", (v1["t"], p1["t"]))
    check(time.time() - t0 < 0.5 * 5 + 6, "并行：没有把同层模块串起来", time.time() - t0)
    # 续跑：vocab、graph 不重做；progress 再做 3 轮（此时仍失败）
    n0 = len(calls)
    stub_env(state, plan={"progress": 99})
    res2 = run_v3(proj, out, Fake())
    again = stub_calls(state)[n0:]
    check(res2["状态"] == "失败" and sorted({c["模块"] for c in again}) == ["progress"], "续跑只重试没完成的模块", [(c["模块"], c["轮"]) for c in again])
    # 参数：最多=2 / 并发（直接改 build.zs 不是正路；这里验证 做模块组 的默认值来自声明）
    check("最多=3" in (ROOT / "tools/dslagent/verbs/v3/defs/做模块组.zs").read_text(encoding="utf-8").splitlines()[1], "做模块组 声明 最多=3 末次模型=opus 并发=3")


def test_cost_cap():
    print("花费上限")
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    res = run_v3(proj, out, Fake(), cost_cap=0.3)
    check(res["状态"] == "超出预期" and "上限" in res["原因"], "花费到上限：超出预期并说明", (res["状态"], res["原因"]))
    check(len(stub_calls(state)) < 3 or res["花费"] >= 0.3, "到上限后不再做新的模块", len(stub_calls(state)))


def test_verb_decls():
    print("动词包")
    from tools.verbs import VerbRegistry
    from tools.dsl_core import RESERVED
    reg = VerbRegistry(reserved=RESERVED)
    reg.load_pack(CM.VERBS / "v3", ROOT)
    want = {"规划到通过": "zs", "规划一份": "zs", "做模块组": "zs", "做一个模块": "zs"}
    for n, k in want.items():
        check(reg.has(n) and reg.kind_of(n) == "script", f"{n} 是 .zs 动词")
    for n in ("写规划", "检查规划", "存规划", "已有规划", "依赖分层", "生成骨架", "生成分配", "做模块", "已完成", "标记完成"):
        check(reg.has(n) and reg.kind_of(n) == "python", f"{n} 是 Python 动词")
    check(not reg.warnings, "加载没有警告", reg.warnings)
    sig = lambda n: " ".join(p.show() for p in reg.specs_of(n))        # noqa: E731
    check(sig("规划到通过") == "<种类> <需求?> <停在?> <最多=3> <模型=sonnet>", "规划到通过 签名", sig("规划到通过"))
    check(sig("做模块组") == "<模块> <最多=3> <末次模型=opus> <并发=3>", "做模块组 签名", sig("做模块组"))
    check(sig("做模块") == "<模块> <上次失败?> <模型=sonnet>" or sig("做模块").startswith("<模块> <上次失败"), "做模块 签名", sig("做模块"))
    check(sig("写规划").startswith("<种类> <需求?> <模块?> <上次问题?>"), "写规划 签名", sig("写规划"))
    flow = (core.HERE / "v3.zs").read_text(encoding="utf-8")
    check(all(s in flow for s in ("规划到通过 顶层", "规划到通过 约定", "生成骨架", "生成分配", "执行 plan/build.zs", "预算 调用 120 秒 36000")), "v3.zs 是流程脚本", flow)


if __name__ == "__main__":
    try:
        test_top()
        test_contract_check()
        test_prompt_example()
        test_skeleton_build_state()
        test_engine_bits()
        test_full_flow_clean()
        test_stop_after()
        test_top_fails()
        test_group_retry()
        test_cost_cap()
        test_verb_decls()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
