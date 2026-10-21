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
from tools.dslagent.packs.dslproj import project as PJ            # noqa: E402
from tools.dslagent.v3 import contracts as VC, core, planning as PL, scaffold as SF, top as VT   # noqa: E402
from tools.dslagent import v2 as V2                                # noqa: E402
from tools.dslagent import guard as G                               # noqa: E402

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

# B2：接口「上传」——字段叫 doc，函数要收 doc_path，顺带要 file_name/file_size/file_ext（骨架会取「上传信息」）
UP_CONTRACT = (
    "模块 up\n\n"
    "## 函数\n"
    "公开 函数 新建 doc_path file_name? file_size? file_ext?\n"
    "  返回 {path, name, size, ext}\n"
    "  伪代码 返回 {\"path\": doc_path, \"name\": file_name, \"size\": file_size, \"ext\": file_ext}\n\n"
    "## 接口\n"
    "POST /up/new -> 新建 上传 doc 类型 md,txt 上限 1MB\n\n"
    "## 用例\n"
    "用例 新建_基本\n"
    "  先 文件 uploads/seed.md 内容=占位\n"
    "  调用 新建 doc_path=uploads/seed.md\n"
    "  得 有返回\n")


class Fake:
    """假模型：按 tag 回答；scripts：{tag: [第 1 次回复, 第 2 次回复, …]}（用完用最后一个）；缺省顶层 = TOP3，约定 = 参考实现。"""

    def __init__(self, top=TOP3, scripts=None):
        self.top, self.scripts, self.calls = top, scripts or {}, []

    def __call__(self, system, user, tag, timeout, **kw):
        self.calls.append({"tag": tag, "user": user, "system": system, "model": kw.get("model"), "idle": kw.get("idle")})
        seq = self.scripts.get(tag)
        if seq:
            n = sum(1 for c in self.calls if c["tag"] == tag)
            return {"text": seq[min(n, len(seq)) - 1], "cost": 0.01}
        if tag == "v3_top":
            return {"text": self.top, "cost": 0.01}
        if tag.startswith("v3_review_"):
            return {"text": '{"通过": "是", "问题列表": []}', "cost": 0.01}
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
    # 约定的依赖不要求和 top 逐字一致：只要是 top 里的模块、不成环就放行
    t2 = VT.load("项目 demo\n模块 graph\n模块 progress 依赖 graph vocab\n模块 vocab 依赖 graph\n")
    check(VC.check(contract_text("progress"), "progress", t2, p) == [], "top 比约定多写一个依赖（vocab）也放行")
    t3 = VT.load("项目 demo\n模块 graph\n模块 progress\n")
    check(VC.check(contract_text("progress"), "progress", t3, p) == [], "top 没写依赖、约定自己声明了依赖也放行（靠不成环把关）")
    # 但放行不包括会成环的依赖
    p2 = project_with_contracts(("graph", "progress"))
    top2 = VT.load("项目 demo\n模块 graph\n模块 progress 依赖 graph\n")
    bad_graph = contract_text("graph").replace("依赖 无", "依赖 progress", 1).replace(
        "伪代码 按 code 查 graph_point 表的一行，原样返回（查不到就返回空）",
        "伪代码 按 code 查 graph_point 表的一行，原样返回（查不到就返回空）\n  伪代码 调用 progress.记作答 learner=x point_code=code correct=1", 1)
    probs = VC.check(bad_graph, "graph", top2, p2)
    check(any("成环" in x for x in probs), "约定的依赖会和已有约定一起成环被查出", probs)
    # 多余依赖：声明了但伪代码 / 用例里都没调用过
    unused = contract_text("vocab").replace("依赖 graph", "依赖 graph progress", 1)
    probs = VC.check(unused, "vocab", VT.load("项目 demo\n模块 graph\n模块 progress\n模块 vocab 依赖 graph progress\n"), p2)
    check(any("多余依赖" in x and "progress" in x for x in probs), "声明了依赖但没调用过被查出是多余依赖", probs)
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


def test_auth_contract():
    print("约定里的「认证」/ 角色 / 公开：解析、检查、生成骨架、比对约定")
    SOL = ROOT / "tests" / "tools" / "fixtures" / "v3_auth_solution"
    text = (SOL / "contracts" / "account.md").read_text(encoding="utf-8")
    c, probs = DC.parse(text)
    check(probs == [], "参考实现 account 约定解析没有问题", probs)
    check(c["认证"] == {"必须": False, "可选": True, "核对": ("app.db", "account_by_name"), "身份": ("who", "me"),
                        "角色": {"teacher": "教师", "student": "学生"}, "拒绝": {}}, "头部认证声明解析成结构化字典", c["认证"])
    ifaces = {i["路径"]: i for i in c["接口"]}
    check(ifaces["/account/login"]["公开"] is True and ifaces["/account/login"]["角色"] == "", "登录接口：公开", ifaces["/account/login"])
    check(ifaces["/account/whoami"]["公开"] is False and ifaces["/account/whoami"]["角色"] == "teacher", "whoami 接口：角色 teacher", ifaces["/account/whoami"])
    top = {"模块": [{"名": "account", "依赖": []}]}
    check(DC.check(c, "account", {}, ["account"]) == [], "account 约定整体检查通过", DC.check(c, "account", {}, ["account"]))

    # 接口角色没有被「认证 角色」声明 → 拒
    bad = text.replace("GET /account/whoami -> 我的角色 角色 teacher", "GET /account/whoami -> 我的角色 角色 principal", 1)
    bc, _ = DC.parse(bad)
    probs = DC.check(bc, "account", {}, ["account"])
    check(any("没有在头部用「认证 角色 principal" in x for x in probs), "接口的角色没有被「认证 角色」声明 → 拒", probs)
    # 公开和角色同时写 → 拒（解析阶段就报）
    _, pprobs = DC.parse(text.replace("GET /account/whoami -> 我的角色 角色 teacher", "GET /account/whoami -> 我的角色 公开 角色 teacher", 1))
    check(any("不能同时写「公开」和「角色」" in x for x in pprobs), "接口同时写 公开 和 角色 → 解析报问题", pprobs)
    # 写了角色 / 公开但头部没有「认证」→ 提示不会生效
    no_auth = "\n".join(l for l in text.splitlines() if not l.startswith("认证")) + "\n"
    nc, _ = DC.parse(no_auth)
    nprobs = DC.check(nc, "account", {}, ["account"])
    check(any("没有「认证 必须」或「认证 可选」，这行不会生效" in x for x in nprobs), "去掉头部认证声明，接口的 角色/公开 不会生效 → 提示", nprobs)
    # 「认证 身份」声明的变量没有被任何公开函数收为入参 → 拒
    bad2 = text.replace("公开 函数 我的角色 who", "公开 函数 我的角色 somebody", 1).replace("who=1", "x=1")
    bad2 = bad2.replace("按 username=who 查", "按 username=somebody 查", 1)
    b2c, b2probs = DC.parse(bad2)
    check(not b2probs, "改参数名之后格式仍然合法（先确认这步没引入别的解析问题）", b2probs)
    check(any("没有一个公开函数把「who」写成入参" in x for x in DC.check(b2c, "account", {}, ["account"])),
          "「认证 身份 who …」声明了，但没有公开函数收 who 这个入参 → 拒")
    # 「认证 必须」和「认证 可选」不能同时写
    _, both_probs = DC.parse("模块 x\n认证 必须\n认证 可选\n## 函数\n公开 函数 f a\n")
    check(any("不能同时写" in x for x in both_probs), "认证 必须 和 认证 可选 同时写 → 拒", both_probs)

    # 生成骨架：routes 文件顶层带认证声明，每条接口带 公开 / 角色
    p = fresh("auth_skel")
    (p / "contracts").mkdir()
    shutil.copy(SOL / "contracts" / "account.md", p / "contracts" / "account.md")
    top_auth = VT.load("项目 demo\n模块 account\n")
    r = SF.gen_skeleton(p, top_auth)
    check(r["问题"] == [], "account 骨架生成加载检查过", r)
    routes_text = (p / "routes" / "account.zs").read_text(encoding="utf-8")
    check(routes_text.splitlines()[:5] == ["认证 可选", "认证 核对 app.db account_by_name", "认证 身份 who 默认 me",
                                           "认证 角色 teacher 教师", "认证 角色 student 学生"], "routes 文件顶层按约定写出认证声明", routes_text)
    check("接口 POST /account/login 公开" in routes_text and "接口 GET /account/whoami 角色 teacher" in routes_text, "接口行带 公开 / 角色", routes_text)
    check(SF.auth_header(DC.parse("模块 x\n## 函数\n公开 函数 f a\n")[0]) == "", "没有「认证」声明的约定：auth_header 是空串")

    # 比对约定：实际 routes 文件和约定头部的认证声明不一致 → 差异
    for m, content in (("services", (SOL / "services" / "account.zs").read_text(encoding="utf-8")),
                       ("entities", (SOL / "entities" / "account.entity").read_text(encoding="utf-8"))):
        (p / m / "account.zs" if m == "services" else p / m / "account.entity").write_text(content, encoding="utf-8")
    (p / "queries").mkdir(exist_ok=True)
    for f in (SOL / "queries").glob("*.sql"):
        shutil.copy(f, p / "queries" / f.name)
    c2, _ = PJ.load_contract(p, "account")
    cmp = PJ.compare(p, "account", c2, ["account"])
    check(cmp["一致"] and not cmp["差异"], "骨架 + 参考实现的 services/entities/queries：比对约定一致", cmp)
    bad_routes = routes_text.replace("认证 可选", "认证 必须", 1)
    (p / "routes" / "account.zs").write_text(bad_routes, encoding="utf-8")
    cmp2 = PJ.compare(p, "account", c2, ["account"])
    check(any("「认证 必须」是 False" in x and "实际是 True" in x for x in cmp2["差异"]), "routes 实际写的认证声明和约定不一致 → 比对约定报差异", cmp2["差异"])
    (p / "routes" / "account.zs").write_text(routes_text.replace("接口 GET /account/whoami 角色 teacher", "接口 GET /account/whoami 公开", 1), encoding="utf-8")
    cmp3 = PJ.compare(p, "account", c2, ["account"])
    check(any("约定「公开」是 False，实际是 True" in x for x in cmp3["差异"]), "接口的 公开/角色 和约定不一致 → 比对约定报差异", cmp3["差异"])


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
    check("用包 common db text" in svc, "业务骨架点名 用包 common db text", svc)
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
    # 从没通过过的模块（never_built）：约定重写后骨架跟着重写，改过的文件也被刷成新骨架；通过过的不动
    r3 = SF.gen_skeleton(p, top, never_built=lambda n: n == "graph")
    check(r3["新建"] == ["services/graph.zs"] and "报错 未实现" in (p / "services" / "graph.zs").read_text(encoding="utf-8"), "never_built 的模块：内容和约定骨架不同的已有文件重写，别的模块不动", r3)
    r3b = SF.gen_skeleton(p, top, never_built=lambda n: True)
    check(r3b["新建"] == [], "never_built 的模块：内容已是最新骨架 → 不重写", r3b)
    (p / "services" / "graph.zs").write_text("业务 graph\n  用包 db\n  公开 函数 取知识点 code\n    返回 {\"x\": 1}\n  结束\n结束\n", encoding="utf-8")
    # 可选入参用 {x 或}
    c, _ = VC.load(p, "progress")
    c["函数"][0]["入参"].append("pass_line?")
    c["接口"].append({"方法": "GET", "路径": "/progress/x", "函数": "记作答", "公开": False, "角色": "", "上传": None, "行": 1})
    check("pass_line={pass_line 或}" in SF.route_text("progress", c), "可选入参用 {x 或}")
    # 缺约定
    try:
        SF.gen_skeleton(fresh("noc"), top)
        check(False, "缺约定要抛 ValueError")
    except ValueError as e:
        check("缺约定" in str(e), "缺约定抛 ValueError", e)
    # 分配
    text = SF.build_text(top)
    check(text.splitlines()[1:] == ["用包 v3", "做模块组 graph", "做模块组 vocab,progress", "全量回归", "接口冒烟", "终止 成功 全部模块完成"], "build.zs 按依赖分层 + 全量回归 + 接口冒烟", text)
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


def test_learner_record_scaffold():
    print("B1：表带「学习记录」标注 → 骨架额外生成 routes/_project.zs（迁移 只加）；比对约定认它")
    p = project_with_contracts(("graph", "vocab", "progress"))
    top = VT.load(TOP3)
    f = p / "contracts" / "progress.md"
    text = f.read_text(encoding="utf-8")
    assert "表 progress_answer\n" in text
    f.write_text(text.replace("表 progress_answer\n", "表 progress_answer 学习记录\n", 1), encoding="utf-8")
    r = SF.gen_skeleton(p, top)
    check("routes/_project.zs" in r["新建"] and r["问题"] == [], "表带「学习记录」→ 额外生成 routes/_project.zs", r)
    check((p / "routes" / "_project.zs").read_text(encoding="utf-8") == "迁移 只加\n", "routes/_project.zs 内容只有「迁移 只加」")
    c, _ = VC.load(p, "progress")
    check(c["表"][0]["学习记录"] is True, "约定解析出「学习记录」标注")
    check(PJ.compare(p, "progress", c, ["graph", "vocab", "progress"])["一致"], "比对约定：有 routes/_project.zs 后一致")
    (p / "routes" / "_project.zs").unlink()
    d = PJ.compare(p, "progress", c, ["graph", "vocab", "progress"])["差异"]
    check(any("学习记录" in x and "迁移 只加" in x for x in d), "去掉 routes/_project.zs → 比对约定报差异", d)
    r2 = SF.gen_skeleton(p, top)
    check("routes/_project.zs" in r2["新建"], "再生成骨架：发现文件被删了 → 补回来", r2)
    # 已有的不重写
    (p / "routes" / "_project.zs").write_text("迁移 只加\n# 手改过\n", encoding="utf-8")
    r3 = SF.gen_skeleton(p, top)
    check("routes/_project.zs" in r3["已有"] and "手改过" in (p / "routes" / "_project.zs").read_text(encoding="utf-8"), "已存在的 routes/_project.zs 不覆盖", r3)


def test_upload_scaffold():
    print("B2：接口「上传」→ 骨架先存文件（失败回 400）、按入参决定要不要取上传信息；业务骨架加 用包 doc；比对约定核对")
    p = fresh("proj")
    (p / "contracts").mkdir()
    (p / "contracts" / "up.md").write_text(UP_CONTRACT, encoding="utf-8")
    top = VT.load("项目 demo\n模块 up\n")
    r = SF.gen_skeleton(p, top)
    check(r["问题"] == [], "骨架生成无加载检查问题", r)
    rt = (p / "routes" / "up.zs").read_text(encoding="utf-8")
    check("设 doc_path = 存文件 doc 类型=md,txt 上限=1MB" in rt, "骨架先存文件，类型 / 上限原样带下来", rt)
    check("如果 {doc_path} 开头是 [" in rt and '返回 {"error":"{doc_path}"} 400' in rt and "结束" in rt, "存文件失败回 400", rt)
    check("设 doc_info = 上传信息 doc" in rt, "函数要 file_name/file_size/file_ext → 额外取 上传信息", rt)
    check("设 file_name = {doc_info.name}" in rt and "设 file_size = {doc_info.size}" in rt and "设 file_ext = {doc_info.ext}" in rt,
          "上传信息的三个字段分别取出", rt)
    check("调用 up.新建 doc_path={doc_path} file_name={file_name 或} file_size={file_size 或} file_ext={file_ext 或}" in rt,
          "调用业务函数时把存盘路径和上传信息都传进去", rt)
    svc = (p / "services" / "up.zs").read_text(encoding="utf-8")
    check("用包 common db text doc" in svc, "业务骨架：有上传接口的模块点名 用包 doc", svc)
    c, _ = VC.load(p, "up")
    check(PJ.compare(p, "up", c, ["up"])["一致"], "比对约定：骨架生成的和约定一致")
    # 没有 file_name/file_size/file_ext 入参的函数：不该多取「上传信息」
    c2, _ = DC.parse(UP_CONTRACT.replace(" file_name? file_size? file_ext?", ""))
    rt2 = SF.route_text("up", c2)
    check("上传信息" not in rt2 and "设 doc_path = 存文件 doc 类型=md,txt 上限=1MB" in rt2, "函数没有那几个入参 → 不取 上传信息", rt2)
    # routes 脚本的「类型」被改掉 → 比对约定报差异
    broken = rt.replace("类型=md,txt", "类型=md")
    (p / "routes" / "up.zs").write_text(broken, encoding="utf-8")
    d = PJ.compare(p, "up", c, ["up"])["差异"]
    check(any("类型 md,txt" in x for x in d), "routes 脚本的「类型」和约定对不上 → 比对约定报差异", d)
    (p / "routes" / "up.zs").write_text(rt.replace("doc 类型=md,txt 上限=1MB", "doc"), encoding="utf-8")
    d2 = PJ.compare(p, "up", c, ["up"])["差异"]
    check(any("声明了「上传" in x for x in d2) is False and any("类型 md,txt" in x for x in d2) and any("上限 1MB" in x for x in d2),
          "routes 脚本干脆不写「类型」「上限」→ 两条都报差异", d2)


def test_upload_multipart():
    print("B2：单测用真实 multipart 验证骨架——存文件 / 上传信息 的产出真被业务函数收到、合格的存盘、不合格的 400 且不存盘")
    import io
    from tools.dsl_http import Router
    p = fresh("proj")
    c, probs = DC.parse(UP_CONTRACT)
    check(not probs, "UP_CONTRACT 解析无问题", probs)
    (p / "routes").mkdir()
    (p / "routes" / "up.zs").write_text(SF.route_text("up", c), encoding="utf-8")
    (p / "services").mkdir()
    (p / "services" / "up.zs").write_text(
        "业务 up\n  用包 common db text doc\n  公开 函数 新建 doc_path file_name? file_size? file_ext?\n"
        "    设 out.path = {doc_path}\n    设 out.name = {file_name 或}\n"
        "    设 out.size = {file_size 或}\n    设 out.ext = {file_ext 或}\n    返回 {out}\n  结束\n结束\n",
        encoding="utf-8")
    router = Router(p / "routes", p, p / "sessions", real=False, login=False)
    client = router.app().test_client()
    resp = client.post("/up/new", data={"doc": (io.BytesIO(b"hello world"), "a.md")}, content_type="multipart/form-data")
    body = resp.get_json()
    check(resp.status_code == 200 and body == {"path": body.get("path"), "name": "a.md", "size": 11, "ext": "md"}
          and str(body.get("path", "")).startswith("uploads/"),
          "真实 multipart：存文件 + 上传信息 的结果被业务函数原样收到、经路由原样返回", (resp.status_code, body))
    saved = (p / body["path"])
    check(saved.is_file() and saved.read_bytes() == b"hello world", "文件真的存到了磁盘，内容一致", saved)
    before = {f.name for f in (p / "uploads").iterdir()}
    resp2 = client.post("/up/new", data={"doc": (io.BytesIO(b"nope"), "a.exe")}, content_type="multipart/form-data")
    body2 = resp2.get_json()
    check(resp2.status_code == 400 and "文件类型不支持" in (body2 or {}).get("error", ""), "类型不在白名单 → 400", body2)
    after = {f.name for f in (p / "uploads").iterdir()}
    check(before == after, "不合格的文件没有被存下来", (before, after))


def test_module_cleanup():
    print("B1：清理删掉的模块——contracts / state 里有、top.zs 里没有的模块 → 删它的文件与 state 记录")
    p = project_with_contracts(("graph", "vocab", "progress"))
    top = VT.load(TOP3)
    SF.gen_skeleton(p, top)
    out = fresh("out")
    ctx = core.Ctx(p, out, "x", None)
    ctx.mark_done("vocab")
    check(ctx.is_done("vocab"), "vocab 先标记完成（后面验证 state 记录也会被清掉）")
    new_top = "项目 demo\n模块 graph        # 知识图谱\n模块 progress 依赖 graph\n"
    (p / "plan" / "top.zs").write_text(new_top, encoding="utf-8")
    e = engine(p)
    e.v3 = ctx
    e.run("用包 v3\n设 r = 清理删掉的模块\n返回 {r}\n")
    r = e.returned[0] if e.returned else None
    check(r == {"removed": ["vocab"]}, "top.zs 里没有 vocab 了 → 报告删了它", r)
    check(not any((p / sub / f"vocab.{ext}").exists() for sub, ext in
                  (("contracts", "md"), ("entities", "entity"), ("services", "zs"), ("routes", "zs"))), "vocab 的 contracts/entities/services/routes 文件都删了")
    check("vocab" not in ctx.load_state().get("模块", {}), "state.json 里 vocab 的记录也删了")
    check((p / "contracts" / "graph.md").is_file() and (p / "contracts" / "progress.md").is_file()
          and (p / "services" / "progress.zs").is_file(), "别的模块的文件没受影响（没有因为前缀相近被误删）")
    # 再跑一次：没有可清理的模块 → 空操作
    e2 = engine(p)
    e2.v3 = ctx
    e2.run("用包 v3\n设 r = 清理删掉的模块\n返回 {r}\n")
    check(e2.returned[0] == {"removed": []}, "没有可清理的模块 → 空操作")
    # 别的约定仍依赖被删的模块：约定检查报「还没有约定文件」
    probs = VC.upstream_of(p, "x", ["vocab"])[1]
    check(any("还没有约定文件" in x for x in probs), "删掉的模块被别的约定依赖 → 约定检查报错（contracts/vocab.md 已经没有了）", probs)


def test_sync_deps():
    print("同步顶层依赖")
    check(VT.sync_deps("项目 demo\n模块 graph        # 知识图谱\n模块 vocab 依赖 graph\n模块 progress 依赖 graph\n",
                        {"progress": ["graph", "vocab"]})
          == "项目 demo\n模块 graph        # 知识图谱\n模块 vocab 依赖 graph\n模块 progress 依赖 graph vocab\n",
          "按 want 改依赖子句，保留注释、不碰没列出的模块")
    check(VT.sync_deps("模块 a 依赖 b   # 说明\n", {"a": []}) == "模块 a  # 说明\n", "依赖清空时去掉「依赖」子句，注释保留")
    check(VT.sync_deps("模块 a\n", {"a": ["b", "c"]}) == "模块 a 依赖 b c\n", "原来没依赖、want 要加依赖")
    check(VT.sync_deps("模块 a 依赖 b\n", {}) == "模块 a 依赖 b\n", "want 里没有的模块原样不动")

    p = project_with_contracts(("graph", "vocab", "progress"))
    (p / "contracts" / "progress.md").write_text(
        contract_text("progress").replace("依赖 graph", "依赖 graph vocab", 1), encoding="utf-8")
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(TOP3, encoding="utf-8")
    ctx = core.Ctx(p, fresh("out"), "x", None)
    eng = core.V3Engine(MockClient(handler=lambda prompt, s=None: "嗯", offline=True), workdir=p, verbose=False, verbs_root=CM.VERBS)
    eng.v3 = ctx
    eng.run("用包 v3\n设 r = 同步顶层依赖\n返回 {r}\n")
    r = eng.returned[0]
    check(r["changed"] == ["progress"] and r["unchanged"] is False, "检测到 progress 的约定比 top.zs 多依赖一个 vocab", r)
    new_top = (p / "plan" / "top.zs").read_text(encoding="utf-8")
    check("模块 progress 依赖 graph vocab" in new_top and "模块 graph        # 知识图谱" in new_top, "top.zs 的 progress 依赖同步成约定的样子，别的行（含注释）不动", new_top)
    eng2 = core.V3Engine(MockClient(handler=lambda prompt, s=None: "嗯", offline=True), workdir=p, verbose=False, verbs_root=CM.VERBS)
    eng2.v3 = ctx
    eng2.run("用包 v3\n设 r = 同步顶层依赖\n返回 {r}\n")
    check(eng2.returned[0] == {"changed": [], "unchanged": True}, "再跑一次：已经同步过，没有变化", eng2.returned[0])


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
    check(e.halted and e.halted["status"] == "失败" and e.halted["reason"] == "停了7" and "不该到这里" not in "\n".join(e.output),
          "没接结果：脚本动词里的终止结束调用方", (e.halted, e.output))
    e = DSLEngine(MockClient(handler=lambda p, s=None: "嗯", offline=True), workdir=w, verbose=False, verbs_root=vroot)
    e.run("用包 tv\n设 r = 停一下 7\n打印 接着走 {r.status} {r.reason}\n")
    check(e.halted is None and "接着走 失败 停了7" in "\n".join(e.output), "接了结果：拿到 {status, reason, at}，接着走", (e.halted, e.output))
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
        check([r["status"] for r in rs] == ["成功", "失败", "失败", "成功", "失败"], "单个失败 / 出错不影响别的项，顺序同输入", [r["status"] for r in rs])
        check(rs[0]["returned"] == {"v": "1"} and rs[3]["returned"] == {"v": "4"}, "子脚本的返回值带回来", rs)
        check(rs[1]["reason"] == "boom", "终止的原因带回来", rs[1])
        check("不存在" in rs[2]["reason"] or "找不到" in rs[2]["reason"], "脚本出错：状态失败 + 原因", rs[2])
        check("找不到子脚本" in rs[4]["reason"], "找不到子脚本：状态失败", rs[4])
    # 对象形式：值可以带空格 / 换行；每项独立作用域；脚本动词按声明绑默认值
    (w / "echo.zs").write_text("返回 {a}\n", encoding="utf-8")
    e = engine(w)
    e.vars["jobs"] = [{"脚本": "echo", "参数": {"a": "有 空格\n和换行"}}, {"脚本": "echo", "参数": {}}]
    e.run("用包 common\n设 rs = 并行执行 {jobs}\n返回 {rs}\n")
    rs = e.returned[0]
    check(rs[0]["returned"] == "有 空格\n和换行", "对象形式的参数可以带空格和换行", rs)
    check(rs[1]["returned"] == "{a}", "每项独立作用域（上一项的变量不串过来）", rs)
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
        check(all(r["status"] == "成功" for r in rs), f"脚本动词当子脚本，并发={conc} 全部成功", rs)
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
    check(res["status"] == "成功" and res["reason"] == "全部模块完成", "整条流程成功", {k: res[k] for k in ("status", "reason", "输出")})
    rec = res["记录"]
    top_ev = [r for r in rec["规划"] if r["种类"] == "顶层" and r["事件"] == "检查"]
    check([r["通过"] for r in top_ev] == [False, True], "顶层：第 1 次不过、重写后通过", top_ev)
    check("【检查发现的问题" in fk.calls[1]["user"] and "snake" in fk.calls[1]["user"] and "项目 Demo" in fk.calls[1]["user"],
          "重写时带上次的内容和问题", fk.calls[1]["user"][-400:])
    check(fk.calls[0]["system"].startswith("# 任务描述") and "【需求】" in fk.calls[0]["user"], "顶层提示词 = prompts/top.md，入参有需求")
    pg = [r for r in rec["规划"] if r["模块"] == "progress" and r["事件"] == "检查"]
    check([r["通过"] for r in pg] == [False, True] and "不在本模块的「依赖」里" in json.dumps(pg[0]["问题"], ensure_ascii=False), "约定：progress 第 1 次把依赖去掉了但伪代码还调 graph，重写后通过", pg)
    cu = [c for c in fk.calls if c["tag"] == "v3_contract_progress"][0]["user"]
    check("【顶层规划 plan/top.zs】" in cu and "项目 demo" in cu and "### 上游模块 graph（直接依赖，可以调用）" in cu and "用例 加边_成功" not in cu and "公开 函数 取知识点" in cu,
          "约定输入 = 需求 + top.zs + 上游已通过的约定（去掉用例）", cu[-600:])
    check(fk.n("v3_contract_") == 4 and fk.n("v3_top") == 2, "模型调用：顶层 2 次、约定 4 次（progress 重写 1 次）", [c["tag"] for c in fk.calls])
    check(all(c["idle"] == G.CONTRACT_IDLE for c in fk.calls if c["tag"].startswith("v3_contract_")), "写约定的调用放宽了空闲超时（约定步骤 vs 普通调用）", [c["idle"] for c in fk.calls if c["tag"].startswith("v3_contract_")])
    check(all(c["idle"] is None for c in fk.calls if c["tag"] == "v3_top"), "顶层规划的调用不放宽超时", [c["idle"] for c in fk.calls if c["tag"] == "v3_top"])
    for m in ("graph", "vocab", "progress"):
        check((proj / "contracts" / f"{m}.md").is_file() and (proj / "services" / f"{m}.zs").is_file(), f"{m}：约定和实现都在")
    check((proj / "plan" / "build.zs").read_text(encoding="utf-8").count("做模块组") == 2, "plan/build.zs 生成了（两层）")
    check(sorted(json.loads((proj / "plan" / "state.json").read_text(encoding="utf-8"))["模块"]) == ["graph", "progress", "vocab"], "state.json 三个模块都标了通过")
    check({r["模块"] for r in rec["模块"]} == {"graph", "vocab", "progress"} and len(rec["模块"]) == 3, "每个模块做了 1 轮", rec["模块"])
    check(abs(res["花费"] - (0.01 * 9 + 0.25 * 3)) < 1e-6, "总花费 = 规划 + 模块", res["花费"])
    check(all((Path(r["记录目录"]) / "task.txt").is_file() for r in rec["模块"]), "每个模块的记录目录有任务文件")
    check((out / "result.json").is_file() and (out / "v3_log.jsonl").is_file() and (out / "steps" / "top_w2.txt").is_file(), "out 里有 result.json / v3_log.jsonl / steps/")
    # 同层并行：vocab 与 progress 在一层，各自都收到任务
    calls = stub_calls(state)
    check(sorted(c["模块"] for c in calls) == ["graph", "progress", "vocab"], "做模块各调 1 次", calls)
    check(all(json.loads(c["models"])["plan"] == "sonnet" for c in calls), "非末次用 sonnet", [c["models"] for c in calls])
    # 续跑：同一命令再跑 → 规划不重写、模块不重做
    fk2, n_stub = Fake(), len(calls)
    res2 = run_v3(proj, out, fk2)
    check(res2["status"] == "成功" and fk2.calls == [], "续跑：已通过的规划一个模型调用都没有", [c["tag"] for c in fk2.calls])
    check(len(stub_calls(state)) == n_stub and res2["模块花费"] == 0, "续跑：已完成且约定未变的模块不重做", stub_calls(state)[n_stub:])
    check((out / "result_run1.json").is_file() and (out / "result.json").is_file(), "续跑：上一次的 result.json 留成 result_run1.json")
    names = sorted(f.name for f in (out / "calls").glob("*.prompt.txt"))
    check(len(names) == len(set(n.split("_", 1)[0] for n in names)) == 9, "calls/ 里每次调用一个文件，没有被覆盖", names)
    # 约定改了 → 只重做那个模块
    f = proj / "contracts" / "vocab.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n# 改了一行注释\n", encoding="utf-8")
    fk3 = Fake()
    res3 = run_v3(proj, out, fk3)
    again = stub_calls(state)[n_stub:]
    check(res3["status"] == "成功" and fk3.calls == [] and [c["模块"] for c in again] == ["vocab"], "续跑：约定改了的模块重做，别的不动", again)
    check(sorted(d.name for d in (out / "modules" / "vocab").iterdir()) == ["r1", "r2"], "续跑：模块轮号接着走，上一次的记录目录还在", sorted(d.name for d in (out / "modules" / "vocab").iterdir()))
    # 约定被改坏（与 top 不一致）→ 续跑时只重写它，且重写的输入带盘上那份和问题
    f.write_text(f.read_text(encoding="utf-8").replace("依赖 graph", "依赖 无", 1), encoding="utf-8")
    fk4 = Fake()
    res4 = run_v3(proj, out, fk4)
    check(res4["status"] == "成功" and [c["tag"] for c in fk4.calls] == ["v3_contract_vocab", "v3_review_vocab"], "续跑：不过检查的约定重写，别的跳过", [c["tag"] for c in fk4.calls])
    u = fk4.calls[0]["user"]
    check("【你上次写的内容】" in u and "不在本模块的「依赖」里" in u and "依赖 无" in u, "续跑重写时输入带盘上那份约定和检查问题", u[-500:])


def test_review():
    print("约定对照需求复核")
    bad = '{"passed": false, "issues": ["需求第九节要求讲解调模型回答，约定改成了模板"]}'
    ok = '{"passed": true, "issues": []}'
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    fk = Fake(scripts={"v3_review_graph": [bad, "```json\n" + ok + "\n```"]})
    res = run_v3(proj, out, fk, stop_after="contract")
    check(res["status"] == "成功", "复核打回一次后通过，流程成功", {k: res[k] for k in ("status", "reason")})
    rv = [r for r in res["记录"]["规划"] if r["模块"] == "graph" and r["事件"] == "复核"]
    check([r["通过"] for r in rv] == [False, True] and "模板" in rv[0]["问题"][0] and rv[0]["状态"] == "已复核", "记录里有复核结果：打回、通过", rv)
    check(fk.n("v3_review_graph") == 2 and fk.n("v3_contract_graph") == 2, "打回后重写一次再复核（各 2 次）", [c["tag"] for c in fk.calls])
    rw = [c for c in fk.calls if c["tag"] == "v3_contract_graph"][1]["user"]
    check("【检查发现的问题" in rw and "复核（对照需求）：需求第九节要求讲解调模型回答" in rw, "复核问题当上次问题带回重写", rw[-300:])
    rq = [c for c in fk.calls if c["tag"] == "v3_review_graph"][0]
    check("【本轮需求全文】" in rq["user"] and "做一个学习系统" in rq["user"] and "【模块 graph 的约定】" in rq["user"] and "## 函数" in rq["user"]
          and "【顶层规划 plan/top.zs】" in rq["user"] and "项目 demo" in rq["user"] and "【项目接口目录" not in rq["user"],
          "复核入参 = 需求全文 + top.zs + 该模块约定（graph 是第一个模块，还没有别的约定，没有目录）", rq["user"][:200])
    check(rq["model"] in (None, "sonnet") or "sonnet" in str(rq["model"]), "复核默认 sonnet", rq["model"])
    check(fk.n("v3_review_") == 4 and fk.n("v3_contract_") == 4, "三个模块各复核一次（graph 两次）", [c["tag"] for c in fk.calls])
    # 一直打回：计入最多次数，三次后失败
    proj2, out2 = fresh("p"), fresh("o")
    fk2 = Fake(scripts={"v3_review_graph": [bad]})
    res2 = run_v3(proj2, out2, fk2, stop_after="contract")
    check(res2["status"] == "失败" and "模板" in res2["reason"] and fk2.n("v3_contract_graph") == 3 and fk2.n("v3_review_graph") == 3,
          "复核一直不过：写 3 次后终止失败", {k: res2[k] for k in ("status", "reason")})
    check(not (proj2 / "contracts" / "graph.md").exists(), "没通过的约定不存盘")
    # 程序检查不过时不调复核
    proj3, out3 = fresh("p"), fresh("o")
    broken = contract_text("graph").replace("模块 graph", "模块 nope", 1)
    fk3 = Fake(scripts={"v3_contract_graph": [broken, contract_text("graph")]})
    run_v3(proj3, out3, fk3, stop_after="contract")
    check(fk3.n("v3_review_graph") == 1 and fk3.n("v3_contract_graph") == 2, "程序检查不过的稿子不进复核", [c["tag"] for c in fk3.calls])
    # 回复不是 JSON：再问一次；仍不行记「未复核」放行
    proj4, out4 = fresh("p"), fresh("o")
    fk4 = Fake(scripts={"v3_review_graph": ["我觉得挺好"]})
    res4 = run_v3(proj4, out4, fk4, stop_after="contract")
    rv4 = [r for r in res4["记录"]["规划"] if r["模块"] == "graph" and r["事件"] == "复核"]
    check(res4["status"] == "成功" and fk4.n("v3_review_graph") == 2 and rv4 and rv4[-1]["状态"] == "未复核", "复核回复坏掉：问两次后记未复核并放行", rv4)
    check(PL.parse_review('{"通过": "否", "问题列表": []}') is None and PL.parse_review('x {"通过":"是"} y') == {"passed": True, "issues": []},
          "parse_review：否且没问题视为无效；容忍前后文字；兼容旧键 通过/问题列表")
    check(PL.parse_review('{"passed": false, "issues": []}') is None and PL.parse_review('x {"passed":true} y') == {"passed": True, "issues": []},
          "parse_review：新键 passed/issues")


def test_catalog():
    print("接口目录 plan/catalog.md：生成 / 刷新 / 一行概要")
    from tools.dslagent.v3 import catalog as CAT
    p = fresh("cat")
    (p / "plan").mkdir(parents=True)
    (p / "plan" / "top.zs").write_text(TOP3, encoding="utf-8")
    (p / "contracts").mkdir()
    for m in ("graph", "vocab", "progress"):
        (p / "contracts" / f"{m}.md").write_text(contract_text(m), encoding="utf-8")
    text = CAT.refresh(p)
    check((p / "plan" / "catalog.md").is_file() and (p / "plan" / "catalog.md").read_text(encoding="utf-8") == text,
          "refresh 存盘的内容和返回一致")
    check("## 模块 graph" in text and "## 模块 progress" in text and "## 模块 vocab" in text, "三个模块各一节（按名排序）", text[:50])
    check("说明：知识图谱" in text, "top.zs 里模块行的注释进了说明", text)
    check("公开 函数 取知识点 code" in text and "返回 {id, code, title}" in text and "伪代码" not in text,
          "公开函数：函数头 + 返回，没有伪代码", text)
    check("GET /graph/point -> 取知识点" in text and "POST /progress/answer -> 记作答" in text, "接口行进了目录", text)
    check("表 progress_answer" in text and "用例" not in text, "表名进了目录，用例没有", text)
    text2 = CAT.refresh(p)
    check(text2 == text, "内容没变：refresh 两次结果一致（不重写）")
    top_text = (p / "plan" / "top.zs").read_text(encoding="utf-8")
    brief = CAT.brief_index(p, top_text, exclude={"progress", "graph"})
    check("模块 vocab" in brief and "记作答" in brief and "模块 graph" not in brief and "模块 progress" not in brief,
          "brief_index 排除给定模块，只给剩下模块一行", brief)
    check("伪代码" not in brief and "用例" not in brief and "\n\n" not in brief.strip(), "一行概要不含伪代码 / 用例，一个模块一行", brief)
    check(CAT.refresh(fresh("cat_empty")) is None, "没有 plan/top.zs 时 refresh 不生成")


DUP_A = ("模块 a\n\n## 函数\n公开 函数 f x\n  返回 {ok}\n  伪代码 返回 {\"ok\": 1}\n\n"
         "## 接口\nGET /dup/x -> f\n\n## 用例\n用例 f_ok\n  调用 f x=1\n  得 有返回\n")
DUP_A_FIXED = DUP_A.replace("/dup/x", "/a/x")
DUP_B = ("模块 b\n\n## 函数\n公开 函数 g y\n  返回 {ok}\n  伪代码 返回 {\"ok\": 1}\n\n"
         "## 接口\nGET /dup/x -> g\n\n## 用例\n用例 g_ok\n  调用 g y=1\n  得 有返回\n")


def test_global_check():
    print("全局检查：跨模块方法+路径 / 表名重复")
    from tools.dslagent.v3 import globalcheck as G
    p = fresh("gchk")
    (p / "contracts").mkdir(parents=True)
    (p / "contracts" / "a.md").write_text(DUP_A, encoding="utf-8")
    (p / "contracts" / "b.md").write_text(DUP_B, encoding="utf-8")
    top = {"项目": "demo", "模块": [{"名": "a", "依赖": [], "行": 1}, {"名": "b", "依赖": [], "行": 2}]}
    g = G.check(p, top)
    check(g["条数"] == 2 and set(g["按模块"]) == {"a", "b"}, "冲突的两个模块各记一条问题", g)
    check("GET /dup/x" in g["按模块"]["a"][0] and "a" in g["按模块"]["a"][0] and "b" in g["按模块"]["a"][0],
          "问题指出冲突的方法+路径和涉及的两个模块", g["按模块"]["a"])
    (p / "contracts" / "a.md").write_text(DUP_A_FIXED, encoding="utf-8")
    g2 = G.check(p, top)
    check(g2["条数"] == 0, "路径改掉之后没有冲突了", g2)


def test_global_check_flow():
    print("全局检查接入 v3 流程：同一路径两个模块都用，逼重写；解决后过，一直冲突就终止失败")
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    fk = Fake(top="项目 demo\n模块 a\n模块 b\n", scripts={"v3_contract_a": [DUP_A, DUP_A_FIXED], "v3_contract_b": [DUP_B]})
    res = run_v3(proj, out, fk, stop_after="contract")
    check(res["status"] == "成功", "冲突被发现、强制重写后解决，流程成功", {k: res[k] for k in ("status", "reason")})
    check("/a/x" in (proj / "contracts" / "a.md").read_text(encoding="utf-8"), "冲突的模块 a 被强制重写成了不冲突的路径")
    check(fk.n("v3_contract_a") == 2, "模块 a 因全局检查冲突多写了一次（原来 1 次 + 逼写 1 次）", [c["tag"] for c in fk.calls])
    gev = [r for r in res["记录"]["规划"] if r["事件"] == "全局检查"]
    check(len(gev) >= 2 and gev[0]["条数"] == 2 and gev[-1]["条数"] == 0, "记录里看得到全局检查：先有冲突，重写后没有了", gev)

    proj2, out2 = fresh("p"), fresh("o")
    fk2 = Fake(top="项目 demo\n模块 a\n模块 b\n", scripts={"v3_contract_a": [DUP_A], "v3_contract_b": [DUP_B]})
    res2 = run_v3(proj2, out2, fk2, stop_after="contract")
    check(res2["status"] == "失败" and "全局检查" in res2["reason"] and "/dup/x" in res2["reason"],
          "两边都不改：全局检查两轮后仍冲突，终止失败", res2["reason"])


def test_stop_after():
    print("--stop-after")
    for stop, has_contracts, has_skel, has_build, mods in (("top", False, False, False, 0), ("contract", True, False, False, 0), ("build", True, True, True, 0)):
        proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
        stub_env(state)
        fk = Fake()
        res = run_v3(proj, out, fk, stop_after=stop)
        check(res["status"] == "成功" and "停在" in res["reason"], f"stop-after={stop}：成功并说明停在哪", (res["status"], res["reason"]))
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
    check(res["status"] == "失败" and "写了 3 次都没通过检查" in res["reason"] and fk.n("v3_top") == 3, "顶层 3 次不过：终止 失败，写了 3 次", (res["status"], res["reason"]))
    check(not (proj / "plan" / "top.zs").exists() and not (proj / "contracts").exists(), "没通过的不存，后面的步骤不走")
    # 约定 3 次不过：只有这个模块失败，同层别的模块写完
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    fk = Fake(scripts={"v3_contract_vocab": ["这不是约定"]})
    res = run_v3(proj, out, fk)
    check(res["status"] == "失败" and "vocab：" in res["reason"] and "progress：" not in res["reason"], "约定：vocab 3 次不过，终止 失败，原因点名 vocab", res["reason"])
    check(fk.n("v3_contract_vocab") == 3 and fk.n("v3_contract_progress") == 1 and (proj / "contracts" / "progress.md").is_file(),
          "同层别的模块照常写完（progress 1 次通过），失败的模块只重写自己", [c["tag"] for c in fk.calls])
    check(not (proj / "services").exists() and stub_calls(state) == [], "约定没全过：不生成骨架、不做模块")
    # 续跑：已通过的约定不重写
    fk2 = Fake()
    res2 = run_v3(proj, out, fk2)
    check(res2["status"] == "成功" and sorted(c["tag"] for c in fk2.calls) == ["v3_contract_vocab", "v3_review_vocab"], "续跑：只补写没通过的 vocab", [c["tag"] for c in fk2.calls])


def test_group_retry():
    print("做模块组：重试 / 末次换模型 / 失败终止 / 组内并行")
    # graph 前两轮没做成（验收不过），第 3 轮（末次，opus）做成
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state, plan={"graph": 2})
    res = run_v3(proj, out, Fake())
    calls = [c for c in stub_calls(state) if c["模块"] == "graph"]
    check(res["status"] == "成功" and len(calls) == 3, "graph 做了 3 轮后通过", (res["status"], res["reason"], len(calls)))
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
    check(res["status"] == "失败" and "progress" in res["reason"] and "3 次" in res["reason"] and "vocab" not in res["reason"], "有模块 3 次没过：终止 失败，原因写模块名和失败原因", res["reason"][:300])
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
    check(res2["status"] == "失败" and sorted({c["模块"] for c in again}) == ["progress"], "续跑只重试没完成的模块", [(c["模块"], c["轮"]) for c in again])
    # 参数：最多=2 / 并发（直接改 build.zs 不是正路；这里验证 做模块组 的默认值来自声明）
    check("最多=3" in (ROOT / "tools/dslagent/verbs/v3/defs/做模块组.zs").read_text(encoding="utf-8").splitlines()[1], "做模块组 声明 最多=3 末次模型=opus 并发=3")


def test_cost_cap():
    print("花费上限")
    proj, out, state = fresh("p"), fresh("o"), fresh("st") / "state"
    stub_env(state)
    res = run_v3(proj, out, Fake(), cost_cap=0.3)
    check(res["status"] == "超出预期" and "上限" in res["reason"], "花费到上限：超出预期并说明", (res["status"], res["reason"]))
    check(len(stub_calls(state)) < 3 or res["花费"] >= 0.3, "到上限后不再做新的模块", len(stub_calls(state)))


def full_project(mods=("graph", "vocab", "progress")):
    """v3_solution 的几个模块，按真实项目布局摆好（contracts / entities / services / routes / queries）。"""
    p = fresh("regp")
    for sub in ("contracts", "entities", "services", "routes", "queries"):
        d = SOL / sub
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and any(f.stem.startswith(m) for m in mods):
                dst = p / sub / f.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst)
    return p


def stub_cmd(out, fixes=None):
    """假「做模块」子进程：fixes = {模块: 要写回的 services/<模块>.zs 内容}（没列的模块什么也不改，直接报「没做」）。"""
    srcs = {}
    for m, text in (fixes or {}).items():
        f = out / f"fix_{m}.zs"
        f.write_text(text, encoding="utf-8")
        srcs[m] = str(f)
    script = out / "stub_cmd.py"
    script.write_text(
        "import json, re, sys\nfrom pathlib import Path\n"
        "argv = sys.argv[1:]\n"
        "a = dict(zip(argv[1::2], argv[2::2])) if argv and argv[0] == 'run' else {}\n"
        "task = Path(a['--task-file']).read_text(encoding='utf-8')\n"
        "m = re.search(r'^模块\\s+(\\S+)', task, re.M).group(1)\n"
        f"srcs = {srcs!r}\n"
        "proj = Path(a['--project'])\n"
        "fixed = m in srcs\n"
        "if fixed:\n"
        "    (proj / 'services' / f'{m}.zs').write_text(Path(srcs[m]).read_text(encoding='utf-8'), encoding='utf-8')\n"
        "print(json.dumps({'kind': 'task', 'fixed': fixed, 'calls': 1, 'cost': 0.01, 'seconds': 0, 'stop': ''}))\n",
        encoding="utf-8")
    return [sys.executable, str(script)]


def test_full_regression():
    print("全量回归：所有模块重新验收；不过的标未完成，按依赖分层交 做一个模块 重做；2 轮仍不过 终止 失败")
    from tools.dsl_core import ScriptHalt
    from tools.dslagent.v3 import regress as RG
    top = VT.load(TOP3)
    p = full_project()
    ctx = core.Ctx(p, fresh("o"), "x", None)
    for m in ("graph", "vocab", "progress"):
        ctx.mark_done(m)
    eng = core.V3Engine(MockClient(handler=lambda s, u=None: "嗯", offline=True), workdir=p, verbose=False, verbs_root=CM.VERBS)
    eng.v3 = ctx
    r = RG.full_regression(ctx, eng, top)
    check(r["状态"] == "通过" and r["轮数"] == 1, "参考实现全部通过：第 1 轮就过，不碰任何模块", r)
    check(all(ctx.is_done(m) for m in ("graph", "vocab", "progress")), "全部仍标记完成")

    # 破坏 graph 的业务实现（报错码改错 → 跑用例不过），假装它之前标记完成（约定 hash 没变）
    broken = (p / "services" / "graph.zs").read_text(encoding="utf-8").replace("报错 404 没有这个知识点", "报错 400 没有这个知识点", 1)
    (p / "services" / "graph.zs").write_text(broken, encoding="utf-8")
    ctx.mark_done("graph")

    out2 = fresh("o")
    fixed_graph = (SOL / "services" / "graph.zs").read_text(encoding="utf-8")
    ctx2 = core.Ctx(p, out2, "x", None, module_cmd=stub_cmd(out2, {"graph": fixed_graph}))
    for m in ("graph", "vocab", "progress"):
        ctx2.mark_done(m)
    eng2 = core.V3Engine(MockClient(handler=lambda s, u=None: "嗯", offline=True), workdir=p, verbose=False, verbs_root=CM.VERBS)
    eng2.v3 = ctx2
    r2 = RG.full_regression(ctx2, eng2, top)
    check(r2["状态"] == "通过" and r2["轮数"] == 2, "第 1 轮查出 graph 不过、重做；第 2 轮全部重新验收通过", r2)
    check(ctx2.is_done("graph") and ctx2.is_done("vocab") and ctx2.is_done("progress"), "重做后 graph 重新标记完成，别的模块没被碰")
    acc = [row for row in ctx2.records["验收"] if row.get("模块") == "graph"]
    check(any(not row["通过"] and "全量回归" in row["说明"] and "跑用例" in row["说明"] for row in acc), "验收记录里有全量回归查出的失败原因", acc)

    # 一直修不好：做一个模块 3 次都没过 → 立刻 终止 失败（不等第 2 轮）
    (p / "services" / "graph.zs").write_text(broken, encoding="utf-8")
    out3 = fresh("o")
    ctx3 = core.Ctx(p, out3, "x", None, module_cmd=stub_cmd(out3))        # 不给 fixes：谁都修不好
    ctx3.mark_done("graph")
    ctx3.mark_done("vocab")
    ctx3.mark_done("progress")
    eng3 = core.V3Engine(MockClient(handler=lambda s, u=None: "嗯", offline=True), workdir=p, verbose=False, verbs_root=CM.VERBS)
    eng3.v3 = ctx3
    try:
        RG.full_regression(ctx3, eng3, top)
        check(False, "修不好要抛 ScriptHalt 失败")
    except ScriptHalt as e:
        check(e.value["status"] == "失败" and "graph" in e.value["reason"], "重做还是不过：终止 失败，原因点名 graph", e.value)
    check(not ctx3.is_done("graph"), "修不好：graph 不再标记完成")


def test_interface_smoke_migrate():
    print("B1：接口冒烟认「学习记录」表——老库缺表自动补齐，第二次是空操作；没开「迁移 只加」则报给拥有表的模块")
    from tools.dslagent.v3 import regress as RG
    p = full_project()
    f = p / "contracts" / "progress.md"
    text = f.read_text(encoding="utf-8")
    f.write_text(text.replace("表 progress_answer\n", "表 progress_answer 学习记录\n", 1), encoding="utf-8")
    (p / "routes" / "_project.zs").write_text("迁移 只加\n", encoding="utf-8")
    mods = ["graph", "vocab", "progress"]
    results, notes = RG.run_smoke(p, mods)
    check(all(ok for ok, _ in results.values()), "有「迁移 只加」声明：老库自动补表、第二次空操作，接口冒烟仍然全过", results)
    (p / "routes" / "_project.zs").unlink()
    results2, _ = RG.run_smoke(p, mods)
    ok, why = results2["progress"]
    check(not ok and "迁移 只加" in why, "没有「迁移 只加」声明 → 归到拥有这张表的 progress 模块", results2)


def test_interface_smoke():
    print("接口冒烟：真起 Router（Flask 测试客户端），同一份种子数据上核对「直接调用」与「走 HTTP」一致")
    from tools.dslagent.v3 import regress as RG
    p = full_project()
    mods = ["graph", "vocab", "progress"]
    results, notes = RG.run_smoke(p, mods)
    check(set(results) == set(mods) and all(ok for ok, _ in results.values()), "参考实现：三个模块的接口冒烟都过", results)
    check(notes == [], "参考实现没有需要备注的差异（at 字段用固定 DSL_NOW，直接调用和 HTTP 应该完全一致）", notes)
    check(not (p / "app.db").exists() and not (p / "sessions").exists(), "接口冒烟不改动传入的项目（在临时拷贝里跑）")

    # 路由和约定对不上（接口声明的方法和 routes 实际注册的方法不一致）→ HTTP 侧 404，状态码不一致，判失败
    bad = (p / "routes" / "graph.zs").read_text(encoding="utf-8").replace("接口 GET /graph/point", "接口 POST /graph/point", 1)
    (p / "routes" / "graph.zs").write_text(bad, encoding="utf-8")
    results2, _ = RG.run_smoke(p, mods)
    ok, why = results2["graph"]
    check(not ok and "状态码不一致" in why, "路由方法改错：直接调用 200，HTTP 404 → 冒烟不过，原因说状态码不一致", why)
    check(results2["vocab"][0] and results2["progress"][0], "别的模块不受影响", results2)


AUTH_SOL = ROOT / "tests" / "tools" / "fixtures" / "v3_auth_solution"


def auth_project(name):
    """v3_auth_solution（account 模块：认证 可选 + 认证 核对 + 角色 teacher/student，一个公开登录接口 + 一个
    角色 teacher 的接口）拷一份到临时目录，可以改了再跑。"""
    p = fresh(name)
    for sub in ("contracts", "entities", "services", "routes", "queries"):
        for f in (AUTH_SOL / sub).glob("*"):
            dst = p / sub / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst)
    return p


def test_interface_smoke_auth():
    print("接口冒烟：多人模式（认证 可选/必须）——非公开接口先核对 401，再补调用人账号登录、带登录态核对一致")
    from tools.dslagent.v3 import regress as RG
    p = auth_project("smoke_auth")
    results, notes = RG.run_smoke(p, ["account"])
    check(results == {"account": (True, "")} and notes == [], "参考实现：公开的登录接口 + 角色 teacher 的接口都过，没有备注", (results, notes))
    check(not (p / "app.db").exists() and not (p / "sessions").exists(), "接口冒烟不改动传入的项目")

    # 把角色接口错改成公开：不登录也该被拦（401），实际会直接命中业务逻辑 → 404，状态码不一致，冒烟查出来
    p2 = auth_project("smoke_auth_pub")
    bad = (p2 / "routes" / "account.zs").read_text(encoding="utf-8").replace("接口 GET /account/whoami 角色 teacher", "接口 GET /account/whoami 公开", 1)
    (p2 / "routes" / "account.zs").write_text(bad, encoding="utf-8")
    results2, _ = RG.run_smoke(p2, ["account"])
    ok2, why2 = results2["account"]
    check(not ok2 and "不登录应该 401" in why2, "角色接口被错改成公开：不登录也该 401，冒烟查出来", why2)

    # 角色接口改错成要求 student（约定和路由一起改，保持一致）：造的调用人账号角色随接口要求换，业务结果仍然一致
    # （业务函数只看 who 这个参数，不看调用人是谁的角色——调用人账号只用来过登录这一关）
    p3 = auth_project("smoke_auth_role")
    bad_route = (p3 / "routes" / "account.zs").read_text(encoding="utf-8").replace(
        "接口 GET /account/whoami 角色 teacher", "接口 GET /account/whoami 角色 student", 1)
    (p3 / "routes" / "account.zs").write_text(bad_route, encoding="utf-8")
    bad_contract = (p3 / "contracts" / "account.md").read_text(encoding="utf-8").replace(
        "GET /account/whoami -> 我的角色 角色 teacher", "GET /account/whoami -> 我的角色 角色 student", 1)
    (p3 / "contracts" / "account.md").write_text(bad_contract, encoding="utf-8")
    results3, _ = RG.run_smoke(p3, ["account"])
    check(results3["account"][0], "角色接口换成 student：造 student 调用人账号登录，一样核对通过", results3)

    # 没有登录公开接口时退回直接签发 cookie：删掉 登录 相关的函数 / 接口 / 用例，whoami 一样能核对
    p4 = auth_project("smoke_auth_nologin")
    (p4 / "routes" / "account.zs").write_text(
        "认证 可选\n认证 核对 app.db account_by_name\n认证 身份 who 默认 me\n认证 角色 teacher 教师\n认证 角色 student 学生\n\n"
        "接口 GET /account/whoami 角色 teacher\n  设 r = 调用 account.我的角色 who={who}\n  返回 {r}\n结束\n", encoding="utf-8")
    (p4 / "contracts" / "account.md").write_text(
        "模块 account\n依赖 无\n认证 可选\n认证 核对 app.db account_by_name\n认证 身份 who 默认 me\n"
        "认证 角色 teacher 教师\n认证 角色 student 学生\n\n## 表\n表 account_user\n  id 整数 主键\n  username 文本 唯一 用户名\n"
        "  password_hash 文本 密码哈希\n  role 文本 角色\n\n## 函数\n公开 函数 我的角色 who\n  返回 {role}\n  报错 404 没有这个用户\n"
        "  伪代码 按 username=who 查 account_user，查不到 报错 404；查到返回 {\"role\": role}\n\n## 接口\n"
        "GET /account/whoami -> 我的角色 角色 teacher\n\n## 用例\n用例 我的角色_有\n  先 数据 account_user username=t1 role=teacher password_hash=x\n"
        "  调用 我的角色 who=t1\n  得 role=teacher\n用例 我的角色_没有\n  调用 我的角色 who=nope\n  报错 404\n", encoding="utf-8")
    (p4 / "services" / "account.zs").write_text(
        "业务 account\n  用包 db auth\n\n  公开 函数 我的角色 who\n    设 row = 查一行 app.db account_user_by_username username={who}\n"
        "    如果 {row} 为空\n      报错 404 没有这个用户\n    结束\n    返回 {\"role\": \"{row.role}\"}\n  结束\n结束\n", encoding="utf-8")
    results4, _ = RG.run_smoke(p4, ["account"])
    check(results4["account"][0], "没有公开登录接口：直接签发 cookie 的退路一样核对通过", results4)


def test_smoke_actor_failures():
    print("G1：冒烟造不出调用人账号 → 判失败（不再静默跳过）；库路径取认证声明第一参数；NOT NULL 列补占位值")
    import sqlite3
    from tools.dslagent.v3 import regress as RG
    # 认证核对指的查询文件不存在：判失败，归到拥有「认证 核对」的模块
    p = auth_project("smoke_noq")
    (p / "queries" / "account_by_name.sql").unlink()
    results, _ = RG.run_smoke(p, ["account"])
    ok, why = results["account"]
    check(not ok and "认证核对指的查询 account_by_name.sql 不存在，真实路由必 500" in why, "查询文件不存在 → 失败，原因写清楚", why)
    check(why.count("不存在，真实路由必 500") == 1, "同一原因只记一次，不按接口重复", why)
    # 表里没有 role 列、接口要角色：判失败而不是跳过
    p2 = auth_project("smoke_norole")
    ent = (p2 / "entities" / "account.entity").read_text(encoding="utf-8").replace("  字段 role 文本 必填 角色\n", "")
    (p2 / "entities" / "account.entity").write_text(ent, encoding="utf-8")
    (p2 / "queries" / "account_by_name.sql").write_text("SELECT username FROM account_user WHERE username = :username", encoding="utf-8")
    results2, notes2 = RG.run_smoke(p2, ["account"])
    ok2, why2 = results2["account"]
    check(not ok2 and ("造不出调用人账号" in why2 or "建库失败" in why2 or "role" in why2), "缺 role 列 → 失败而不是跳过", why2)
    check(not any("造不出调用人账号" in n for n in notes2), "不再写进备注静默跳过", notes2)
    # _make_actor：库用认证声明第一参数；其他 NOT NULL 无默认值的列补占位
    w = fresh("actor_ws")
    (w / "queries").mkdir()
    (w / "queries" / "q.sql").write_text("SELECT username, role FROM acct WHERE username = :username", encoding="utf-8")
    con = sqlite3.connect(w / "other.db")
    con.execute("CREATE TABLE acct(id INTEGER PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT, role TEXT NOT NULL, "
                "display_name TEXT NOT NULL, disabled INTEGER NOT NULL, score REAL NOT NULL, note TEXT NOT NULL DEFAULT 'd', tag TEXT)")
    con.commit()
    con.close()
    u, pw = RG._make_actor(w, w / "app.db", {"check": ("other.db", "q")}, "teacher")
    row = sqlite3.connect(w / "other.db").execute("SELECT username, role, display_name, disabled, score, note, tag FROM acct").fetchall()
    check(row == [(u, "teacher", "x", 0, 0, "d", None)], "按认证声明的库建账号，NOT NULL 文本给 'x'、数字 / disabled 给 0，有默认值的不动", row)
    try:
        RG._make_actor(w, w / "app.db", {"check": ("nope.db", "q")}, "teacher")
        check(False, "库文件不存在应抛 ActorError")
    except RG.ActorError as e:
        check("nope.db" in e.why and not e.missing_query, "库文件不存在 → ActorError 写明库名", e.why)
    try:
        RG._make_actor(w, w / "app.db", {"check": ("other.db", "zzz")}, "")
        check(False, "查询文件不存在应抛 ActorError")
    except RG.ActorError as e:
        check(e.missing_query and "zzz.sql 不存在" in e.why, "查询文件不存在 → missing_query", e.why)


def test_verb_decls():
    print("动词包")
    from tools.verbs import VerbRegistry
    from tools.dsl_core import RESERVED
    reg = VerbRegistry(reserved=RESERVED)
    reg.load_pack(CM.VERBS / "v3", ROOT)
    want = {"规划到通过": "zs", "规划一份": "zs", "做模块组": "zs", "做一个模块": "zs"}
    for n, k in want.items():
        check(reg.has(n) and reg.kind_of(n) == "script", f"{n} 是 .zs 动词")
    check(reg.has("复核约定") and reg.kind_of("复核约定") == "python", "复核约定 是 Python 动词")
    for n in ("写规划", "检查规划", "存规划", "已有规划", "依赖分层", "生成骨架", "生成分配", "做模块", "已完成", "标记完成", "同步顶层依赖",
              "全局检查", "全局重写任务表"):
        check(reg.has(n) and reg.kind_of(n) == "python", f"{n} 是 Python 动词")
    check(not reg.warnings, "加载没有警告", reg.warnings)
    sig = lambda n: " ".join(p.show() for p in reg.specs_of(n))        # noqa: E731
    check(sig("规划到通过") == "<种类> <需求?> <停在?> <最多=3> <模型=sonnet>", "规划到通过 签名", sig("规划到通过"))
    check(sig("做模块组") == "<模块> <最多=3> <末次模型=opus> <并发=3>", "做模块组 签名", sig("做模块组"))
    check(sig("做模块") == "<模块> <上次失败?> <模型=sonnet>" or sig("做模块").startswith("<模块> <上次失败"), "做模块 签名", sig("做模块"))
    check(sig("写规划").startswith("<种类> <需求?> <模块?> <上次问题?>"), "写规划 签名", sig("写规划"))
    check(sig("复核约定") == "<模块> <文本> <需求?> <模型=sonnet>", "复核约定 签名", sig("复核约定"))
    check("强制问题" in sig("规划一份"), "规划一份 带了 强制问题 可选参数", sig("规划一份"))
    flow = (core.HERE / "v3.zs").read_text(encoding="utf-8")
    check(all(s in flow for s in ("规划到通过 顶层", "规划到通过 约定", "同步顶层依赖", "生成骨架", "生成分配", "执行 plan/build.zs", "预算 调用 120 秒 36000")), "v3.zs 是流程脚本", flow)
    plan_flow = (core.HERE.parent / "verbs" / "v3" / "defs" / "规划到通过.zs").read_text(encoding="utf-8")
    check("全局检查" in plan_flow and "全局重写任务表" in plan_flow, "规划到通过.zs 接入了全局检查", plan_flow)


TUTOR_NEW = ("模块 tutor\n\n## 函数\n公开 函数 ping\n  返回 {ok}\n  伪代码 返回 {\"ok\": 1}\n\n"
             "## 接口\nGET /tutor/ping -> ping\n\n## 用例\n用例 ping_ok\n  调用 ping\n  得 有返回\n")


def test_plan_verbs():
    print("D3：修改计划四个动词是真动词——改需求 / 新增模块 / 删除模块 / 改约定（各自登记 ctx.pending_contracts）")
    p = project_with_contracts(("graph", "vocab", "progress"))
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(TOP3, encoding="utf-8")
    SF.gen_skeleton(p, VT.load(TOP3))
    req_dir = fresh("req")
    req_file = req_dir / "req.md"
    req_file.write_text("## 1 概述\nxxx\n\n## 2 词库\nyyy\n\n## 3 进度\nzzz\n", encoding="utf-8")
    out = fresh("out")
    ctx = core.Ctx(p, out, "需求全文", None, req_path=req_file)
    ctx.mark_done("vocab")
    check(ctx.is_done("vocab"), "vocab 先标记完成（后面验证删除模块会把这条 state 记录也清掉）")
    e = engine(p)
    e.v3 = ctx
    e.run("用包 v3\n设 r = 改需求 2 词库支持按知识点练习\n返回 {r}\n")
    check(e.halted is None and e.returned[0] == {"section": "2"}, "改需求返回改的节号", (e.halted, e.returned))
    req_now = req_file.read_text(encoding="utf-8")
    check("## 1 概述\nxxx" in req_now and "## 3 进度\nzzz" in req_now, "别的节不受影响", req_now)
    check("## 2 词库\n词库支持按知识点练习" in req_now, "改需求真的改了节的正文（不是只追加变更记录）", req_now)
    check("## 变更记录" in req_now and "改第 2 节" in req_now, "文末追加了变更记录", req_now)
    # \n（两个字符）当段落分隔，decode 成真正的换行（内容不能有 ASCII 空格，分段/换行走这个转义）
    e1b = engine(p)
    e1b.v3 = ctx
    e1b.run("用包 v3\n改需求 3 第一段" + chr(92) + "n第二段\n")
    check(e1b.halted is None, "两段式改需求没有终止失败", e1b.halted)
    check("## 3 进度\n第一段\n第二段" in req_file.read_text(encoding="utf-8"), "\\n 解码成了真正的换行", req_file.read_text(encoding="utf-8"))
    # E3：中文数字节号（## 五、做题），改完不吞掉后面没编号的「## 通用」
    rf2 = fresh("req_cn") / "req.md"
    rf2.write_text("## 一、角色\naaa\n\n## 五、做题\nbbb\n\n## 通用\nccc\n", encoding="utf-8")
    ctx2 = core.Ctx(p, out, "x", None, req_path=rf2)
    e1c = engine(p)
    e1c.v3 = ctx2
    e1c.run("用包 v3\n改需求 五 新正文" + chr(92) + "_带空格\n")
    cn = rf2.read_text(encoding="utf-8")
    check(e1c.halted is None and "## 五、做题\n新正文 带空格\n" in cn and "## 通用\nccc" in cn and "## 一、角色\naaa" in cn,
          "改需求认中文数字节号，\\_ 还原成空格，不吞后面的无编号节", (e1c.halted, cn))
    # 新增模块：改 top.zs + 登记 pending_contracts（空串＝走全流程）
    e2 = engine(p)
    e2.v3 = ctx
    e2.run("用包 v3\n设 r = 新增模块 tutor 依赖=graph 说明=按知识点练习\n返回 {r}\n")
    check(e2.halted is None and e2.returned[0] == {"name": "tutor"}, "新增模块返回模块名", (e2.halted, e2.returned))
    top_now = (p / "plan" / "top.zs").read_text(encoding="utf-8")
    check("模块 tutor 依赖 graph" in top_now and "# 按知识点练习" in top_now, "新增模块的行加进了 top.zs（带说明注释）", top_now)
    check(ctx.pending_contracts.get("tutor") == "", "新增模块登记了空目标（还没约定过，走全流程）", ctx.pending_contracts)
    # 改约定：只登记，不改 top.zs
    e3 = engine(p)
    e3.v3 = ctx
    e3.run("用包 v3\n设 r = 改约定 progress 加一个按知识点统计的接口\n返回 {r}\n")
    check(e3.halted is None and e3.returned[0] == {"module": "progress"}, "改约定返回模块名", (e3.halted, e3.returned))
    check(ctx.pending_contracts.get("progress") == "- 加一个按知识点统计的接口", "改约定登记了条目（走强制问题通道）", ctx.pending_contracts)
    check("模块 progress" in top_now, "改约定没有碰 top.zs")
    # 删除模块：改 top.zs + 清理文件/state + 从 pending_contracts 里撤销登记
    e4 = engine(p)
    e4.v3 = ctx
    e4.run("用包 v3\n设 r = 删除模块 vocab\n返回 {r}\n")
    check(e4.halted is None and e4.returned[0] == {"name": "vocab"}, "删除模块返回模块名", (e4.halted, e4.returned))
    top_now = (p / "plan" / "top.zs").read_text(encoding="utf-8")
    check("模块 vocab" not in top_now and "模块 graph        # 知识图谱" in top_now,
          "删除模块的行从 top.zs 去掉了，别的行（含注释）不受影响", top_now)
    check(not (p / "contracts" / "vocab.md").exists(), "删除模块复用了「清理删掉的模块」，vocab 的约定文件被删了")
    check("vocab" not in ctx.load_state().get("模块", {}), "删除模块后 state.json 里 vocab 的记录也清掉了")
    check((p / "contracts" / "graph.md").is_file() and (p / "contracts" / "progress.md").is_file(), "别的模块没受影响")
    # 出错场景：节号不存在、没有 req_path、模块不存在/重名
    ctx2 = core.Ctx(p, fresh("out"), "x", None)
    e5 = engine(p)
    e5.v3 = ctx2
    e5.run("用包 v3\n改需求 1 随便改点什么\n")
    check(e5.halted is not None and e5.halted["status"] == "失败" and "req_path" in e5.halted["reason"],
          "有「改需求」但没设需求文件路径：终止失败，不是悄悄跳过", e5.halted)
    ctx3 = core.Ctx(p, out, "需求全文", None, req_path=req_file)
    e6 = engine(p)
    e6.v3 = ctx3
    e6.run("用包 v3\n改需求 99 x\n")
    check(e6.halted is not None and "找不到第 99 节" in e6.halted["reason"], "需求文件里没有这一节：终止失败", e6.halted)
    e7 = engine(p)
    e7.v3 = ctx3
    e7.run("用包 v3\n新增模块 graph 说明=重名\n")
    check(e7.halted is not None and "已经存在" in e7.halted["reason"], "新增模块重名：终止失败", e7.halted)
    e8 = engine(p)
    e8.v3 = ctx3
    e8.run("用包 v3\n改约定 nosuch x\n")
    check(e8.halted is not None and "不在 plan/top.zs" in e8.halted["reason"], "改约定的模块不存在：终止失败", e8.halted)
    e9 = engine(p)
    e9.v3 = ctx3
    e9.run("用包 v3\n删除模块 nosuch\n")
    check(e9.halted is not None and "不在 plan/top.zs" in e9.halted["reason"], "删除模块不存在：终止失败", e9.halted)


def test_plan_script_flow():
    print("D3：计划就是一份 .zs，用「执行」直接跑——新增模块（走写约定+复核全流程）与改约定（强制问题带条目，只跑程序检查），"
          "固定末行 落实修改 按依赖分层写/重写约定、同步顶层依赖")
    p = project_with_contracts(("graph", "vocab", "progress"))
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(TOP3, encoding="utf-8")
    SF.gen_skeleton(p, VT.load(TOP3))
    out = fresh("out")
    for m in ("graph", "vocab", "progress"):
        core.Ctx(p, out, "x", None).mark_done(m)
    plan_dir = p / "plan" / "changes"
    plan_dir.mkdir(parents=True)
    (plan_dir / "1.zs").write_text(
        "# 对应问题 1\n"
        "新增模块 tutor 依赖=无 说明=独立小模块（供测试）\n"
        "# 对应问题 2\n"
        "改约定 progress 加一句无意义的小改动（供测试）\n"
        "落实修改\n",
        encoding="utf-8")
    fk = Fake(scripts={
        "v3_contract_tutor": [TUTOR_NEW],
        "v3_review_tutor": ['{"通过": "是", "问题列表": []}'],
        "v3_contract_progress": [contract_text("progress")],
    })
    M = V2.Model(out, backend=fk)
    ctx = core.Ctx(p, out, "需求全文", M)
    eng = core.V3Engine(V2.Client(M), workdir=p, verbose=False, verbs_root=CM.VERBS)
    eng.v3, ctx.usage = ctx, eng.usage
    eng.run("用包 v3\n执行 plan/changes/1.zs 需求=需求全文\n")
    check(eng.halted is None, "直接执行计划文件（不经过一个专门的「执行修改计划」动词），没有终止失败", eng.halted)
    check((p / "contracts" / "tutor.md").is_file(), "新增模块：约定写出来了")
    check(fk.n("v3_contract_tutor") == 1 and fk.n("v3_review_tutor") == 1, "新增模块走的是正常全流程：写一次、复核一次", [c["tag"] for c in fk.calls])
    check(fk.n("v3_contract_progress") == 1, "改约定：重写了一次", [c["tag"] for c in fk.calls])
    check(fk.n("v3_review_progress") == 0, "改约定走强制问题通道：没有调复核", [c["tag"] for c in fk.calls])
    cu = [c for c in fk.calls if c["tag"] == "v3_contract_progress"][0]["user"]
    check("加一句无意义的小改动（供测试）" in cu and "【你上次写的内容】" in cu, "改约定重写时带了上一版约定和改动条目", cu[-400:])
    top_now = (p / "plan" / "top.zs").read_text(encoding="utf-8")
    check("模块 tutor" in top_now, "新增模块留在 top.zs 里（同步顶层依赖没有误删）", top_now)
    check(ctx.pending_contracts == {}, "落实修改消费完登记表后清空了")
    # 没有内容动词（只有 改需求/删除模块），落实修改 只跑 同步顶层依赖，不报错
    (plan_dir / "2.zs").write_text("# 对应问题 1\n删除模块 tutor\n落实修改\n", encoding="utf-8")
    ctx2 = core.Ctx(p, out, "x", None)
    eng2 = core.V3Engine(V2.Client(V2.Model(out, backend=fk)), workdir=p, verbose=False, verbs_root=CM.VERBS)
    eng2.v3 = ctx2
    eng2.run("用包 v3\n执行 plan/changes/2.zs\n")
    check(eng2.halted is None, "只删模块、不写约定：落实修改照样能跑完（同步顶层依赖，不报错）", eng2.halted)
    check(ctx2.pending_contracts == {}, "没有登记过模块，落实修改消费后登记表仍是空的")
    check(not (p / "contracts" / "tutor.md").exists(), "删除模块真的清理了约定文件")


def test_audit_entry():
    print("D3：核查.zs（假模型，顶层脚本参数用中文）出问题清单；tools.dslagent v3 的 audit 入口（core.run_entry）")
    p = fresh("audit_p")
    (p / "plan").mkdir(parents=True)
    (p / "plan" / "top.zs").write_text("项目 demo\n模块 a\n模块 b\n", encoding="utf-8")
    (p / "contracts").mkdir()
    (p / "contracts" / "a.md").write_text(DUP_A, encoding="utf-8")
    (p / "contracts" / "b.md").write_text(DUP_B, encoding="utf-8")
    out = fresh("audit_out")
    fk = Fake(scripts={"v3_audit": ['[{"问题": "需求第 3 节要求的导出功能两个模块都没做", "涉及模块": ["a", "b"], "依据": "需求第 3 节"}]']})
    res = core.run_entry("核查", p, out, "需求全文", extra_vars={"task": "", "llm": "sonnet"}, backend=fk)
    check(res["status"] == "成功", "核查.zs 跑成功", res)
    ret = res.get("returned") or {}
    check(ret.get("count") == 3, "问题清单：程序检查（a/b 路径重复）2 条 + 模型 1 条", ret)
    path = Path(p) / ret["path"]
    check(path.is_file() and path.name == "1.md", "问题清单存盘到 plan/issues/1.md", ret)
    text = path.read_text(encoding="utf-8")
    check("需求第 3 节要求的导出功能两个模块都没做" in text and "GET /dup/x" in text, "程序检查和模型发现的问题都在清单里", text)
    check(fk.n("v3_audit") == 1, "调了一次模型", [c["tag"] for c in fk.calls])
    # audit.md 现在要求模型回英文键 issue/modules/basis，核查.zs 照样能处理（新旧键都认）
    p1b, out1b = fresh("audit_p1b"), fresh("audit_out1b")
    (p1b / "plan").mkdir(parents=True)
    (p1b / "plan" / "top.zs").write_text("项目 demo\n模块 a\n", encoding="utf-8")
    fk1b = Fake(scripts={"v3_audit": ['[{"issue": "新键回复也要能用", "modules": "a", "basis": "需求第 1 节"}]']})
    res1b = core.run_entry("核查", p1b, out1b, "需求全文", extra_vars={"task": "", "llm": "sonnet"}, backend=fk1b)
    ret1b = res1b.get("returned") or {}
    check(ret1b.get("count") == 1, "模型回新键 issue/modules/basis 一样能被核查.zs 消费", ret1b)
    check("新键回复也要能用" in (Path(p1b) / ret1b["path"]).read_text(encoding="utf-8"), "新键问题进了清单", ret1b)
    # 没有 plan/top.zs 时也能跑（纯模型找问题，程序检查部分是空）
    p2, out2 = fresh("audit_p2"), fresh("audit_out2")
    fk2 = Fake(scripts={"v3_audit": ["[]"]})
    res2 = core.run_entry("核查", p2, out2, "需求全文", extra_vars={"task": "", "llm": "sonnet"}, backend=fk2)
    check(res2["status"] == "成功" and (res2.get("returned") or {}).get("count") == 0, "还没有 plan/top.zs 时核查照样能跑，程序检查部分是空", res2)


def test_modify_entry():
    print("D3：修改.zs（假模型）全流程——读问题清单 → 写修改计划（自己存盘）→ 检查修改计划（不过带问题重写）→ "
          "执行 这份计划 → 生成骨架/生成分配 → build")
    p = project_with_contracts(("graph", "vocab", "progress"))
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(TOP3, encoding="utf-8")
    SF.gen_skeleton(p, VT.load(TOP3))
    req_dir = fresh("req")
    req_file = req_dir / "req.md"
    req_file.write_text("## 1 概述\nx\n", encoding="utf-8")
    out, state = fresh("modify_out"), fresh("modify_st") / "state"
    stub_env(state)
    for m in ("graph", "vocab", "progress"):
        core.Ctx(p, out, "x", None).mark_done(m)
    (p / "plan" / "issues").mkdir(parents=True)
    (p / "plan" / "issues" / "1.md").write_text(
        "# 问题清单 1\n\n1. progress 缺一个按知识点统计的接口\n   涉及模块：progress\n", encoding="utf-8")
    BAD_PLAN = "这不是合法的计划格式\n"
    GOOD_PLAN = "# 对应问题 1\n改约定 progress 加一个按知识点统计的接口\n落实修改\n"
    fk = Fake(scripts={
        "v3_change_plan": [BAD_PLAN, GOOD_PLAN],
        "v3_contract_progress": [contract_text("progress")],
    })
    res = core.run_entry("修改", p, out, req_file.read_text(encoding="utf-8"),
                          extra_vars={"issues": "latest", "task": "", "llm": "sonnet", "retries": "3"},
                          backend=fk, req_path=req_file, module_cmd=CMD)
    cpu = [c for c in fk.calls if c["tag"] == "v3_change_plan"][0]["user"]
    check("【涉及模块的约定（去掉用例）】" in cpu and "### progress" in cpu, "写修改计划的 user 里真的带了涉及模块的约定", cpu[-300:])
    check(res["status"] == "成功", "修改.zs 跑成功（第一次写的计划格式不对，重写一次才过）", res)
    check(fk.n("v3_change_plan") == 2, "写修改计划调了两次（不过带问题重写）", [c["tag"] for c in fk.calls])
    check(fk.n("v3_contract_progress") == 1, "改约定：重写了一次约定，走强制问题通道", [c["tag"] for c in fk.calls])
    check(fk.n("v3_review_progress") == 0, "改约定没有调复核", [c["tag"] for c in fk.calls])
    plans = sorted((p / "plan" / "changes").glob("*.zs"), key=lambda f: int(f.stem))
    check(len(plans) == 2, "两次写修改计划都存盘了（没通过检查的那份也留着痕迹）", [f.name for f in plans])
    check(plans[-1].read_text(encoding="utf-8").strip() == GOOD_PLAN.strip(), "最后一份是通过检查、真正执行的那份", plans[-1].read_text(encoding="utf-8"))
    check(res["reason"] == "全部模块完成", "一路跑到 build、build 自己也成功（终止 {b.状态} {b.原因} 带出来的）", res)


def test_modify_retries_exhausted():
    print("D3：修改.zs——写了 次数 次都没通过检查就终止失败，不往下跑 执行/build")
    p = project_with_contracts(("graph",))
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text("项目 demo\n模块 graph\n", encoding="utf-8")
    out = fresh("modify_out")
    (p / "plan" / "issues").mkdir(parents=True)
    (p / "plan" / "issues" / "1.md").write_text("# 问题清单 1\n\n1. 随便一个问题\n", encoding="utf-8")
    fk = Fake(scripts={"v3_change_plan": ["这不是合法的计划格式\n"]})
    res = core.run_entry("修改", p, out, "需求全文",
                          extra_vars={"issues": "latest", "task": "", "llm": "sonnet", "retries": "2"}, backend=fk)
    check(res["status"] == "失败" and "没通过检查" in res["reason"], "两次都没通过检查：终止失败", res)
    check(fk.n("v3_change_plan") == 2, "正好调了 次数 次模型，不多不少", [c["tag"] for c in fk.calls])


def test_change_plan_contracts():
    print("I1：写修改计划把涉及模块的现有约定（去掉用例）附进 user_text")
    from tools.dslagent.v3 import change_plan as CP
    p = project_with_contracts(("graph", "vocab", "progress"))
    top = VT.load(TOP3)
    (p / "contracts" / "progress.md").unlink()
    iss = "1. a\n   涉及模块：graph、vocab\n2. b\n   涉及模块：不存在,graph\n"
    t = CP.involved_contracts_text(p, top, iss)
    check("### graph" in t and "### vocab" in t and "### progress" not in t, "(a) 只含 modules 里的模块", t[:200])
    full = (p / "contracts" / "graph.md").read_text(encoding="utf-8")
    check("## 用例" in full and "## 用例" not in t, "(a) 不含用例", t)
    check(t.index("### graph") < t.index("### vocab"), "按模块名排序")
    t2 = CP.involved_contracts_text(p, top, "1. a\n")
    check("### graph" in t2 and "### vocab" in t2 and "### progress" not in t2, "(b)(c) modules 为空取全部模块，没有约定文件的跳过", t2[:200])
    f = p / "contracts" / "graph.md"
    f.write_text(full.replace("## 用例", "长" * 13000 + "\n\n## 用例", 1), encoding="utf-8")
    t3 = CP.involved_contracts_text(p, top, "1. a\n   涉及模块：graph\n")
    check("（后面略）" in t3 and len(t3) < 12100, "(d) 超长截断", len(t3))


def test_check_plan_arg_count():
    print("E3：检查修改计划——改需求 / 改约定 带 ASCII 空格（参数超过 2 个）要在检查阶段挡住，别等执行才炸")
    from tools.dslagent.v3 import change_plan as CP
    top = VT.load(TOP3)
    issues = [{"问题": "x"}]
    bad = "# 对应问题 1\n改需求 1 ## 概述\\n正文\n落实修改\n"
    probs = CP.check_plan(bad, issues, top, "## 1 概述\nx\n")
    check(any("改需求只接受 2 个参数" in x for x in probs), "改需求正文带空格被挡", probs)
    bad2 = "# 对应问题 1\n改约定 graph 加 一个 接口\n落实修改\n"
    probs2 = CP.check_plan(bad2, issues, top, "")
    check(any("改约定只接受 2 个参数" in x for x in probs2), "改约定条目带空格被挡", probs2)
    nz = CP.normalize_plan("# 对应问题 1\n改需求 1 ## 概述 a b\\n正文\n改约定 graph 加 一个 接口\n落实修改")
    check(CP.check_plan(nz, issues, top, "## 1 概述\nx\n") == [] and nz.splitlines()[1].count(" ") == 2 and "\\_" in nz, "normalize_plan 把自由文本里的空格换成全角后通过检查", (CP.check_plan(nz, issues, top, "## 1 概述\nx\n"), nz.splitlines()[1]))
    ok = "# 对应问题 1\n改需求 1 正文\\n第二段\n改约定 graph 加一个接口\n落实修改\n"
    check(CP.check_plan(ok, issues, top, "## 1 概述\nx\n") == [], "没有空格的写法通过", CP.check_plan(ok, issues, top, "## 1 概述\nx\n"))


if __name__ == "__main__":
    try:
        test_top()
        test_smoke_actor_failures()
        test_contract_check()
        test_auth_contract()
        test_prompt_example()
        test_skeleton_build_state()
        test_learner_record_scaffold()
        test_upload_scaffold()
        test_upload_multipart()
        test_module_cleanup()
        test_sync_deps()
        test_engine_bits()
        test_full_flow_clean()
        test_review()
        test_catalog()
        test_global_check()
        test_global_check_flow()
        test_stop_after()
        test_top_fails()
        test_group_retry()
        test_cost_cap()
        test_full_regression()
        test_interface_smoke_migrate()
        test_interface_smoke()
        test_interface_smoke_auth()
        test_verb_decls()
        test_plan_verbs()
        test_plan_script_flow()
        test_audit_entry()
        test_modify_entry()
        test_modify_retries_exhausted()
        test_check_plan_arg_count()
        test_change_plan_contracts()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
