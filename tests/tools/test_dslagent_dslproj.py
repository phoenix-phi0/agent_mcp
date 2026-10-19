# -*- coding: utf-8 -*-
"""dslproj 资料包：约定解析 / 检查、比对约定、跑用例（空库、固定时间、单模块）、验收、资料、动词、整条流程（假模型）。不调真模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_dslproj.py

参考实现（graph：知识点 + 加边带环检查；progress：作答 + 记作答，依赖 graph）在 tests/tools/fixtures/dslproj_solution/，约定和用例也在那里。
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_dslproj_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"
os.environ["DSLAGENT_DATASET"] = str(TMP / "dataset")
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
for k in ("DSLAGENT_PLANNER", "DSLAGENT_PACK", "DSLAGENT_VERIFY", "DSLAGENT_PLAN_MODE", "DSL_NOW"):
    os.environ.pop(k, None)

from tools.dslagent import entry, packs, scope as SC, v2 as V      # noqa: E402
from tools.dslagent import plan as DP                              # noqa: E402
from tools.dslagent.engine import AgentEngine                      # noqa: E402
from tools.dslagent.packs.dslproj import cases as CS, contract as C, project as P  # noqa: E402

DP_PACK = packs.pick("dslproj")
SOL = ROOT / "tests" / "tools" / "fixtures" / "dslproj_solution"
PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def copy_sol(name, skip=()):
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    shutil.copytree(SOL, p, ignore=shutil.ignore_patterns(*skip) if skip else None)
    return p


def skeleton(name, modules=("graph",)):
    """contracts 齐全、已做好的上游用参考实现，要做的模块只有 services 骨架（函数体 报错 501 未实现）。"""
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    (p / "contracts").mkdir(parents=True)
    for f in (SOL / "contracts").glob("*.md"):
        shutil.copy(f, p / "contracts" / f.name)
    done = [m for m in ("graph", "progress") if m not in modules]
    for m in done:
        for g in P.scope_globs(m):
            for f in SOL.glob(g):
                dst = p / f.relative_to(SOL)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dst)
    (p / "services").mkdir(exist_ok=True)
    if "graph" in modules:
        (p / "services" / "graph.zs").write_text(GRAPH_SKEL, encoding="utf-8")
    if "progress" in modules:
        (p / "services" / "progress.zs").write_text(PROGRESS_SKEL, encoding="utf-8")
    return p


GRAPH_SKEL = """业务 graph
  用包 db

  公开 函数 取知识点 code
    报错 501 未实现
  结束

  公开 函数 加边 src dst
    报错 501 未实现
  结束
结束
"""
PROGRESS_SKEL = """业务 progress
  依赖 graph
  用包 db

  公开 函数 记作答 learner point_code correct
    报错 501 未实现
  结束
结束
"""


def edits_block(project, files, name="e1"):
    """files：{相对路径: 新内容}。文件已存在 → @@ 改（原文 = 现有全文），否则 @@ 新建。返回 #改法 段文本。"""
    out = [f"#改法 {name}"]
    for rel, new in files.items():
        f = Path(project) / rel
        if f.is_file():
            out += [f"@@ 改 {rel}", "<<<<<<< 原文", f.read_text(encoding="utf-8").rstrip("\n"), "=======", new.rstrip("\n"), ">>>>>>> 新文"]
        else:
            out += [f"@@ 新建 {rel}", "<<<<<<< 内容", new.rstrip("\n"), ">>>>>>> 新文"]
    return "\n".join(out) + "\n"


def solution_files(module):
    return {str(f.relative_to(SOL)): f.read_text(encoding="utf-8") for g in P.scope_globs(module) for f in sorted(SOL.glob(g)) if f.is_file()}


def plan_for(module, project, files=None, tail="终止 成功 做完了"):
    head = (f"用包 common text code dslproj\n预算 调用 4 秒 600\n设 m = {module}\n设 res = 改文件 {{e1}}\n如果 {{res.ok}} 不等于 是\n  终止 失败 改法没套上：{{res.msg}}\n结束\n"
            "设 c = 加载检查 {m}\n设 d = 比对约定 {m}\n设 t = 跑用例 {m}\n"
            "如果 {c.ok} 等于 是 且 {d.一致} 等于 是 且 {t.全过} 等于 是\n  终止 成功 三项检查都过\n结束\n" + tail + "\n\n")
    return head + edits_block(project, files if files is not None else solution_files(module))


class Fake:
    def __init__(self, **replies):
        self.replies, self.log = replies, []

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.log.append((tag, system, user))
        key = next((k for k in sorted(self.replies, key=len, reverse=True) if tag.startswith(k)), None)
        r = self.replies.get(key)
        if callable(r):
            r = r(user)
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, dict):
            r = json.dumps(r, ensure_ascii=False)
        return {"text": r or "", "cost": 0.01, "sec": 0.0}


# ------------------------------------------------------------------ 一、约定解析 / 检查


def t_contract():
    print("一、约定解析 / 检查")
    g, probs = C.parse((SOL / "contracts" / "graph.md").read_text(encoding="utf-8"))
    check(not probs and g["模块"] == "graph" and g["依赖"] == [] and [t["名"] for t in g["表"]] == ["point", "edge"], "graph 约定：模块 / 依赖 / 表", probs)
    check([(f["名"], f["公开"], f["入参"]) for f in g["函数"]] == [("取知识点", True, ["code"]), ("加边", True, ["src", "dst"])]
          and g["函数"][1]["报错"][1]["码"] == 409 and len(g["函数"][1]["伪代码"]) == 3, "函数：名字 / 公开 / 入参 / 报错 / 伪代码")
    check([(i["方法"], i["路径"], i["函数"]) for i in g["接口"]] == [("GET", "/graph/point", "取知识点"), ("POST", "/graph/edge", "加边")], "接口")
    u = next(x for x in g["用例"] if x["名"] == "加边_成功")
    check(len(g["用例"]) == 7 and u["先"][0] == {"种类": "数据", "表": "point", "值": {"code": "P1", "title": "甲"}, "行": u["先"][0]["行"]}
          and u["调用"]["参数"] == {"src": "P1", "dst": "P2"} and u["得"] == {"ok": "1"}
          and u["库"][0] == {"表": "edge", "种类": "共", "行数": 1, "行": u["库"][0]["行"]} and u["库"][1]["种类"] == "含", "用例：先 / 调用 / 得 / 库")
    check(next(x for x in g["用例"] if x["名"] == "加边_自环")["报错"] == 409 and next(x for x in g["用例"] if x["名"] == "取知识点_没有")["为空"], "用例：报错码 / 得 为空")
    p, probs = C.parse((SOL / "contracts" / "progress.md").read_text(encoding="utf-8"))
    check(not probs and p["依赖"] == ["graph"] and next(x for x in p["用例"] if x["名"] == "记作答_累计正确率")["先"][1]["种类"] == "调用", "progress 约定：依赖 graph、先 调用")
    check(C.check(g, "graph", {}, ["graph", "progress"]) == [] and C.check(p, "progress", {"graph": g}, ["graph", "progress"]) == [], "两份约定检查通过")
    check(C.hash_of("a\r\nb  \n") == C.hash_of("a\nb\n"), "hash_of：换行 / 行尾空白不影响")
    heads = C.public_heads(g)
    check("公开 函数 取知识点 code" in heads and "报错 409 会形成环" in heads and "伪代码" not in heads, "public_heads：函数头 + 返回 / 报错，不含伪代码")
    # 错误
    bad = [("模块 x\n## 乱写\n", "不认识的小节"), ("模块 x\n## 函数\n公开 函数 f\n  报错 500 坏\n  伪代码 x\n", None),
           ("模块 x\n## 用例\n用例 a\n  调用 f\n  调用 g\n", "只写一条"), ("## 函数\n函数 f\n", "缺「模块"),
           ("模块 x\n## 用例\n用例 a\n  得 k\n", "得 写法"), ("模块 x\n## 接口\nGET /a\n", "接口写法"),
           ("模块 x\n## 用例\n用例 a\n  库 t 多少\n", "库 写法")]
    for text, want in bad:
        _, pr = C.parse(text)
        if want:
            check(any(want in x for x in pr), f"解析问题：{want}", pr)
    c2, pr = C.parse("模块 x\n依赖 y\n## 表\n表 Bad\n  a 文本\n## 函数\n函数 f A\n  报错 500 坏\n公开 函数 g b\n  伪代码 调用 z.q\n  伪代码 调用 y.nope\n## 接口\nGET /a -> f\nGET a -> g\n"
                     "## 用例\n用例 u1\n  调用 g\n用例 u1\n  调用 g b=1 c=2\n  得 k=v\n  先 调用 y.nope\n")
    pr = pr + C.check(c2, "x", {"y": {"函数": [{"名": "ok", "公开": True}]}}, ["x", "y"])
    for want in ("表名「Bad」", "入参 ['A'] 不合法", "报错码 500 不是 4xx", "z.q，但 z 不在", "y.nope，但 y 的约定里没有公开函数", "调的函数「f」不是本模块的公开函数",
                 "路径「a」要以 /", "用例「u1」重名", "缺必填入参", "传了函数没有的入参"):
        check(any(want in x for x in pr), f"检查：{want}", pr)
    _, pr = C.parse("模块 x\n## 函数\n公开 函数 f a\n")
    cc, _ = C.parse("模块 x\n## 函数\n公开 函数 f a\n  伪代码 x\n")
    check(any("一条验收用例都没有" in x for x in C.check(cc, "x", {}, ["x"])), "公开函数没有用例 → 报")
    check(any("依赖的模块「q」" in x for x in C.check({**cc, "依赖": ["q"]}, "x", {}, ["x"])), "依赖的模块没有约定文件 → 报")


# ------------------------------------------------------------------ 二、项目约定


def t_project():
    print("二、项目约定：模块名 / 范围 / 约定读取 / 依赖闭包")
    check(P.module_of("请做\n模块 graph\n补充说明") == "graph" and P.module_of("模块: progress") == "progress" and P.module_of("没有") is None, "module_of")
    check(P.scope_globs("graph") == ["entities/graph.entity", "services/graph.zs", "routes/graph*.zs", "queries/graph_*.sql", "tests/graph_*"], "范围 = 5 类路径")
    sc = SC.parse(P.scope_globs("graph"))
    check(all(SC.inside(x, sc) for x in ("entities/graph.entity", "services/graph.zs", "routes/graph.zs", "routes/graph_api.zs", "queries/graph_edge_insert.sql", "tests/graph_cases.zs"))
          and not any(SC.inside(x, sc) for x in ("contracts/graph.md", "services/progress.zs", "routes/progress.zs", "queries/progress_x.sql", "entities/progress.entity")),
          "范围 glob：本模块的文件在内，contracts / 别的模块不在")
    try:
        P.require_module("没有模块行")
        check(False, "require_module 缺模块行报错")
    except P.ProjError as e:
        check("模块" in str(e), "require_module：任务里没有「模块 <名>」→ 报错")
    check(P.all_modules(SOL) == ["graph", "progress"] and P.closure(SOL, "progress") == ["graph", "progress"] and P.closure(SOL, "graph") == ["graph"], "all_modules / closure（上游在前）")
    c, text = P.load_contract(SOL, "progress")
    check(c["模块"] == "progress" and "记作答" in text, "load_contract")
    for mod, want in (("nope", "没有约定文件"),):
        try:
            P.load_contract(SOL, mod)
            check(False, "load_contract 缺文件报错")
        except P.ProjError as e:
            check(want in str(e), f"load_contract：{want}")
    p = copy_sol("pj_bad")
    (p / "contracts" / "progress.md").write_text("模块 progress\n依赖 nope\n", encoding="utf-8")
    try:
        P.load_contract(p, "progress")
        check(False, "约定有问题报错")
    except P.ProjError as e:
        check("依赖的模块「nope」" in str(e), "load_contract：约定检查不过 → ProjError 带问题", e)
    p = copy_sol("pj_routes")
    (p / "routes" / "graph_api.zs").write_text("接口 GET /x\n  返回 {}\n结束\n", encoding="utf-8")
    names = [f.name for f in P.route_files(p, "graph", ["graph", "progress"])]
    check(names == ["graph.zs", "graph_api.zs"] and [f.name for f in P.route_files(p, "progress", ["graph", "progress"])] == ["progress.zs"], "route_files：按最长模块名前缀归属", names)


# ------------------------------------------------------------------ 三、比对约定


def t_compare():
    print("三、比对约定")
    mods = ["graph", "progress"]
    for m in mods:
        c, _ = P.load_contract(SOL, m)
        r = P.compare(SOL, m, c, mods)
        check(r["一致"] and not r["差异"], f"参考实现 {m}：一致", r)

    def variant(name, module, fn):
        p = copy_sol(name)
        fn(p)
        c, _ = P.load_contract(p, module)
        return P.compare(p, module, c, mods)["差异"]

    def sub(rel, a, b):
        def f(p):
            t = (p / rel).read_text(encoding="utf-8")
            assert a in t, (rel, a)
            (p / rel).write_text(t.replace(a, b, 1), encoding="utf-8")
        return f
    d = variant("cmp1", "graph", sub("services/graph.zs", "公开 函数 加边 src dst", "公开 函数 加边 dst src"))
    check(any("入参约定是 src dst，实际是 dst src" in x for x in d), "入参顺序不同 → 差异", d)
    d = variant("cmp2", "graph", sub("services/graph.zs", "公开 函数 取知识点 code", "函数 取知识点 code"))
    check(any("约定是公开，实际是私有" in x for x in d), "公开变私有 → 差异", d)
    d = variant("cmp3", "graph", sub("services/graph.zs", "公开 函数 取知识点 code", "公开 函数 取点 code"))
    check(any("缺函数「取知识点」" in x for x in d) and any("多了约定里没有的公开函数「取点」" in x for x in d), "函数改名 → 缺 + 多", d)
    d = variant("cmp4", "progress", sub("services/progress.zs", "  依赖 graph\n", ""))
    check(any("「依赖」是 无，约定是 ['graph']" in x for x in d), "业务文件少写依赖 → 差异", d)
    d = variant("cmp5", "graph", sub("routes/graph.zs", "接口 POST /graph/edge", "接口 POST /graph/edges"))
    check(any("缺接口 POST /graph/edge" in x for x in d) and any("多了约定里没有的接口 POST /graph/edges" in x for x in d), "接口路径不同 → 缺 + 多", d)
    d = variant("cmp6", "graph", sub("routes/graph.zs", "调用 graph.加边", "调用 graph.取知识点"))
    check(any("应只调 graph.加边" in x for x in d), "接口调错函数 → 差异", d)
    d = variant("cmp7", "graph", sub("entities/graph.entity", "实体 edge 依赖边", "实体 edges 依赖边"))
    check(any("表「edge」" in x for x in d), "约定里的表没有对应实体 → 差异", d)
    d = variant("cmp8", "graph", lambda p: (p / "services" / "graph.zs").unlink())
    check(any("缺 services/graph.zs" in x for x in d), "缺业务文件 → 差异", d)
    d = variant("cmp9", "graph", lambda p: (p / "services" / "graph.zs").write_text("业务 graph\n  公开 函数 取知识点 code\n", encoding="utf-8"))
    check(any("解析失败" in x for x in d), "业务文件解析失败 → 差异", d)


# ------------------------------------------------------------------ 四、跑用例


def t_cases():
    print("四、跑用例：空库 / 固定时间 / 单模块 / 失败原因")
    r = CS.run(SOL, "graph")
    check(r["全过"] and r["总数"] == 7, "graph 用例全过（7 个）", r)
    r = CS.run(SOL, "progress")
    check(r["全过"] and r["总数"] == 5, "progress 用例全过（5 个，含固定时间 at=2026-01-01、上游 graph 的表和函数）", r)
    check(not list(SOL.rglob("*.db")), "不改项目（没有在项目里留下 app.db）")
    # 单模块：只有 graph 的文件时 graph 能单独跑；progress 缺上游实体 → 建表失败
    p = copy_sol("cs_single", skip=("progress*",))
    check(CS.run(p, "graph")["全过"], "单模块可单独跑（项目里没有 progress 的文件）")
    p2 = copy_sol("cs_noup")
    (p2 / "entities" / "graph.entity").unlink()
    r = CS.run(p2, "progress")
    check(not r["全过"] and "entities/graph.entity" in r["原因"], "上游实体缺 → 建表失败并说明", r["原因"])
    # 固定时间：换 DSL_NOW 就会变（at 不再是 2026-01-01）；默认固定
    r = CS.run(SOL, "progress", now="2030-05-06 07:08:09")
    check(not r["全过"] and any("记作答_答对" == f["名"] and "没有" in f["原因"] for f in r["失败"]), "now 可调：换时间后依赖 2026-01-01 的用例失败（说明时间确实被固定）", r)
    check("DSL_NOW" not in os.environ, "跑完恢复 DSL_NOW 环境变量")
    # 失败原因：去掉成环检查
    p = copy_sol("cs_nocycle")
    t = (p / "services" / "graph.zs").read_text(encoding="utf-8")
    t = t.replace("    如果 {hit.yes} 等于 1\n      报错 409 会形成环\n    结束\n", "")
    (p / "services" / "graph.zs").write_text(t, encoding="utf-8")
    r = CS.run(p, "graph")
    check([f["名"] for f in r["失败"]] == ["加边_成环"] and "应该报错 409" in r["失败"][0]["原因"], "去掉环检查 → 只有 加边_成环 失败，原因可读", r["失败"])
    # 业务错误码不对 / 少写库
    p = copy_sol("cs_code")
    t = (p / "services" / "graph.zs").read_text(encoding="utf-8").replace("报错 404 没有这个知识点", "报错 400 没有这个知识点")
    (p / "services" / "graph.zs").write_text(t, encoding="utf-8")
    r = CS.run(p, "graph")
    check(any(f["名"] == "加边_没有知识点" and "应该报错 404" in f["原因"] for f in r["失败"]), "报错码不对 → 失败", r["失败"])
    p = copy_sol("cs_nowrite")
    t = (p / "services" / "graph.zs").read_text(encoding="utf-8").replace("    设 n = 写库 app.db graph_edge_insert src={src} dst={dst}\n", "")
    (p / "services" / "graph.zs").write_text(t, encoding="utf-8")
    r = CS.run(p, "graph")
    check(any(f["名"] == "加边_成功" and "库 edge 应有 1 行" in f["原因"] for f in r["失败"]), "没写库 → 库核对失败", r["失败"])
    # 空库：用例之间互不影响（加边_成功 写了边，后面的 加边_成环 仍是只有它自己造的 2 条）
    r = CS.run(SOL, "graph")
    check(r["全过"], "用例之间互不影响（每个用例新库）")
    # 业务层加载失败
    p = copy_sol("cs_syntax")
    (p / "services" / "graph.zs").write_text("业务 graph\n  公开 函数 取知识点\n", encoding="utf-8")
    r = CS.run(p, "graph")
    check(not r["全过"], "业务文件有语法问题 → 用例不过", r["原因"][:200])
    check(CS.main(["--project", str(SOL), "--module", "graph"]) == 0, "命令行 main：退出码 0")


# ------------------------------------------------------------------ 五、验收 / 资料 / 动词


def t_accept_materials():
    print("五、验收 / 资料 / 规划说明 / 动词")
    for m in ("graph", "progress"):
        r = DP_PACK.accept(SOL, {"task": f"模块 {m}"})
        check(r["通过"] and not r["问题"] and "比对约定 一致" in r["摘要"], f"accept {m}：加载检查无错 + 比对一致 + 用例全过", r)
    p = skeleton("ac_skel")
    r = DP_PACK.accept(p, {"task": "模块 graph"})
    check(not r["通过"] and any(x.startswith("比对约定：") for x in r["问题"]) or not r["通过"], "骨架（函数体 501）：验收不过", r["摘要"][:300])
    check(any(x.startswith("用例 取知识点_取到：") for x in r["问题"]) or any("建表失败" in x or "建表" in x for x in r["问题"]), "骨架：用例不过（缺实体 / 501）", r["问题"][:4])
    p = copy_sol("ac_loaderr")
    (p / "routes" / "graph.zs").write_text("接口 POST /graph/edge\n  如果 {a} 乱写 {b}\n    返回 {}\n  结束\n结束\n", encoding="utf-8")
    r = DP_PACK.accept(p, {"task": "模块 graph"})
    check(any(x.startswith("加载检查：") for x in r["问题"]), "接口文件里有看不懂的条件 → 加载检查报错", r["问题"][:3])
    r = DP_PACK.accept(SOL, {"task": "没有模块行"})
    check(not r["通过"] and "模块" in r["问题"][0], "任务里没有模块行 → 验收不过并说明", r)
    r = DP_PACK.accept(SOL, {"task": "模块 nope"})
    check(not r["通过"] and "没有约定文件" in r["问题"][0], "没有约定文件 → 验收不过并说明", r)

    # 资料
    m = DP_PACK.materials("模块 progress\n加油", SOL, DP_PACK.scope_for("模块 progress", SOL))
    t = m["text"]
    check("## 本模块约定（contracts/progress.md" in t and "用例 记作答_答对" in t and "记作答 learner point_code correct" in t, "资料：本模块约定全文（表、函数头 + 伪代码、接口、用例）")
    check("### 上游模块 graph" in t and "公开 函数 取知识点 code" in t and "公开 函数 加边 src dst" in t and "伪代码 按 code 查 point" not in t.split("## 本模块现有文件")[0].split("## 上游模块")[1],
          "资料：上游公开函数头（不带上游的伪代码）")
    check("## DSL 项目写法速查" in t and "事务 app.db" in t and "实体 answer 作答" in t and "接口 POST /progress/answer" in t, "资料：DSL 语法速查（业务层 / 实体 / 接口）")
    check("services/progress.zs" in t and "entities/progress.entity" in t and "services/graph.zs" not in t.split("## 本模块现有文件")[1], "资料：本模块现有文件（不含上游模块的文件）")
    check(m["记录"]["模块"] == "progress" and m["记录"]["依赖"] == ["graph"], "资料：记录", m["记录"])
    p = skeleton("mt_skel")
    check("报错 501 未实现" in DP_PACK.materials("模块 graph", p, [])["text"], "骨架文件进资料")
    try:
        DP_PACK.materials("没有模块行", SOL, [])
        check(False, "资料：没有模块行报错")
    except P.ProjError:
        check(True, "资料：没有模块行报错")
    # 规划说明
    s = DP_PACK.PLAN_SYSTEM()
    check("加载检查" in s and "比对约定" in s and "跑用例" in s and "用包 common text code dslproj" in s and "#改法 段" in s and "## 示例" in s
          and "跑测试" not in s.split("## 这类任务的规划要点")[0].split("### code 包")[1].split("### dslproj 包")[0], "规划说明：角色 + 速查 + dslproj 动词 + 要点 + 示例", s[:100])
    check("自带的只读工具" in DP_PACK.PLAN_SYSTEM("grok") and "dsl 工具读" in DP_PACK.PLAN_SYSTEM("claude"), "规划说明：grok 变体")
    check(V.plan_system(DP_PACK, "claude") == s, "v2.plan_system 用包的 PLAN_SYSTEM")
    # 示例 .zs 自己要过检查（白名单 + #改法 对着骨架 + 假模型空跑）
    ex = (ROOT / "tools" / "dslagent" / "packs" / "dslproj" / "prompts" / "example.zs").read_text(encoding="utf-8")
    p = skeleton("ex_skel")
    err, *_ = V.check(p, TMP / "ex_work", ex, "模块 graph", pack=DP_PACK)
    check(err == "", "示例 example.zs：白名单 / 改法 / 空跑都通过", err)
    # 计划检查：没有 跑用例
    bad = ex.replace("设 t = 跑用例 {m}", "设 t = 加载检查 {m}").replace("{t.全过}", "{t.ok}").replace("设 t2 = 跑用例 {m}", "设 t2 = 加载检查 {m}").replace("{t2.全过}", "{t2.ok}").replace("{t.失败}", "{t.问题}").replace("{t2.失败}", "{t2.问题}")
    err, *_ = V.check(p, TMP / "ex_work2", bad, "模块 graph", pack=DP_PACK)
    check("跑用例" in err, "计划检查（包专属）：计划里没有 跑用例 → 报", err)
    # 动词：引擎里直接跑
    eng = AgentEngine(client=None, workdir=SOL, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    eng.run("用包 common text code dslproj\n设 c = 加载检查 graph\n设 d = 比对约定 graph\n设 t = 跑用例 graph\n设 u = 跑用例 progress")
    v = eng.vars
    check(v["c"]["ok"] == "是" and v["d"]["一致"] == "是" and v["t"]["全过"] == "是" and v["t"]["总数"] == 7 and v["u"]["总数"] == 5, "动词 加载检查 / 比对约定 / 跑用例", {k: v[k] for k in "cdtu"})
    p = copy_sol("vb_bad")
    (p / "services" / "graph.zs").write_text((p / "services" / "graph.zs").read_text(encoding="utf-8").replace("公开 函数 加边 src dst", "公开 函数 加边 dst src"), encoding="utf-8")
    eng = AgentEngine(client=None, workdir=p, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    eng.run("用包 common text code dslproj\n设 d = 比对约定 graph\n设 t = 跑用例 graph")
    check(eng.vars["d"]["一致"] == "否" and "入参约定" in eng.vars["d"]["差异"] and eng.vars["d"]["条数"] >= 1, "动词 比对约定：不一致时给差异文本", eng.vars["d"])
    eng = AgentEngine(client=None, workdir=SOL, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    try:
        eng.run("用包 common text code dslproj\n设 t = 跑用例 nope")
        check(False, "动词：模块不存在报错")
    except Exception as e:  # noqa: BLE001
        check("没有约定文件" in str(e), "动词：模块不存在 → 报错带原因")
    eng = AgentEngine(client=None, workdir=SOL, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    eng.dry_run = True
    eng.run("用包 common text code dslproj\n设 t = 跑用例 nope\n设 d = 比对约定 nope")
    check(eng.vars["t"]["全过"] == "是" and eng.vars["d"]["一致"] == "是", "空跑（计划检查）时不碰项目，给占位结果")


# ------------------------------------------------------------------ 六、整条流程（假模型）


def t_flow():
    print("六、整条流程（假模型，pack=dslproj）")
    # 1 计划一次做对：成功、无补改、1 次调用
    p = skeleton("fl_ok")
    f = Fake(plan=plan_for("graph", p))
    r = V.run(p, "模块 graph", TMP / "out_fl_ok", model=f, pack="dslproj")
    check(r["status"] == "成功" and r["calls"] == 1 and [t for t, _, _ in f.log] == ["plan"], "一次做对：成功、只有 plan 一次调用", (r["stop"], [t for t, _, _ in f.log]))
    check(sorted(r["changed_files"]) == sorted(solution_files("graph")), "改动文件 = 范围内的文件", r["changed_files"])
    check(r["v2"]["验收"]["通过"] and "用例 7/7 通过" in r["v2"]["验收"]["测试摘要"] and "边界复核" in r["reply"]["结果"], "验收：通过（加载检查 + 比对 + 用例）", r["v2"]["验收"])
    check(r["v2"]["pack"] == "dslproj" and r["v2"]["模块"] == "graph" and (TMP / "out_fl_ok" / "outline.md").read_text(encoding="utf-8").startswith("## 本次要做的模块：graph"), "记录：pack / 模块 / outline.md（= 资料）")
    sysm, user = f.log[0][1], f.log[0][2]
    check(sysm == DP_PACK.PLAN_SYSTEM("claude") and "用例 加边_成环" in user and "报错 501 未实现" in user, "规划 system = 包的规划说明；user = 任务 + 资料（约定、用例、骨架）")
    check(not (p / "app.db").exists() and (p / "contracts" / "graph.md").read_text(encoding="utf-8") == (SOL / "contracts" / "graph.md").read_text(encoding="utf-8"), "约定文件没动、项目里没有 app.db")
    # 2 依赖上游的模块：先 graph 后 progress
    p2 = skeleton("fl_prog", modules=("progress",))
    f = Fake(plan=plan_for("progress", p2))
    r = V.run(p2, "模块 progress", TMP / "out_fl_prog", model=f, pack="dslproj")
    check(r["status"] == "成功" and "用例 5/5 通过" in r["v2"]["验收"]["测试摘要"], "progress（依赖 graph）一次做对", r["stop"])
    check("### 上游模块 graph" in f.log[0][2] and "services/graph.zs" not in f.log[0][2].split("## 本模块现有文件")[1].split("## DSL 项目写法")[0], "资料里有上游公开函数头、没有上游的文件")
    # 3 第一次实现有 bug（少了环检查）→ 计划里自查不过终止 成功？这里计划不自查，直接终止 成功 → 验收不过 → 补改 → 通过
    files = solution_files("graph")
    buggy = dict(files)
    buggy["services/graph.zs"] = files["services/graph.zs"].replace("    如果 {hit.yes} 等于 1\n      报错 409 会形成环\n    结束\n", "")
    p3 = skeleton("fl_fix")
    fixed = {"结果": {"edits": [{"file": "services/graph.zs", "old": "    设 n = 写库 app.db graph_edge_insert",
                                "new": "    如果 {hit.yes} 等于 1\n      报错 409 会形成环\n    结束\n    设 n = 写库 app.db graph_edge_insert"}], "说明": "补上环检查"},
             "状态": "成功", "原因": ""}
    plan3 = plan_for("graph", p3, buggy).replace("  终止 成功 三项检查都过\n结束\n", "  终止 成功 三项检查都过\n结束\n终止 成功 先这样交给验收\n", 1)
    plan3 = plan3.replace("终止 成功 做完了\n", "", 1)
    f = Fake(plan=plan3, fix=fixed)
    r = V.run(p3, "模块 graph", TMP / "out_fl_fix", model=f, pack="dslproj")
    check([t for t, _, _ in f.log] == ["plan", "fix"] and r["status"] == "成功" and r["v2"]["验收"]["补改"]["套用"] is True, "实现有 bug：验收不过 → 补改 1 次 → 补改后通过", (r["stop"], [t for t, _, _ in f.log]))
    fu = f.log[1][2]
    check("用例 加边_成环：应该报错 409" in fu and "【本模块约定（不能改）】" in fu and "services/graph.zs" in fu and "## DSL 项目写法速查" in fu
          and "contracts/graph.md" not in fu.split("【本模块现有文件")[1], "补改入参：失败用例原因 + 约定 + 本模块现有文件 + 写法速查", fu[:300])
    check(f.log[1][1] == DP_PACK.FIX_SYSTEM, "补改 system = 包的 FIX_SYSTEM")
    check("## 本模块可用的动词" in fu and "已加载的包：db" in fu and "【db】" in fu and "查一行 <库> <查询名>" in fu and "写库 <库> <语句名>" in fu,
          "补改入参：带本模块可用的动词表（含签名）", fu[fu.find("## 本模块可用的动词"):][:200])
    check("补改入参里的" not in fu and fu.find("## DSL 项目写法速查") < fu.find("## 本模块可用的动词"), "补改入参：写法速查在前、动词表在后")
    # 按 services 里 用包 点名的包列出
    pv = skeleton("fl_verbs")
    sv = pv / "services" / "graph.zs"
    sv.write_text(sv.read_text(encoding="utf-8").replace("业务 graph\n", "业务 graph\n  用包 text\n", 1), encoding="utf-8")
    vt = DP_PACK.service_verbs(pv, "graph")
    check("已加载的包：db、text" in vt and "【text】" in vt and "【db】" in vt, "service_verbs：services 里 用包 的包 + db", vt[:200])
    check("【db】" in DP_PACK.materials("模块 graph", pv, None)["text"] and "## 本模块可用的动词" in DP_PACK.materials("模块 graph", pv, None)["text"], "做模块规划的资料里也带动词表")
    check(len(r["v2"]["验收"]["验收记录"]) == 2 and not r["v2"]["验收"]["验收记录"][0]["通过"] and r["v2"]["验收"]["验收记录"][1]["通过"], "验收记录：第一次不过、补改后通过")
    # 4 计划想改约定 / 别的模块的文件：被拦（整体没写），失败、项目回滚
    p4 = skeleton("fl_oos", modules=("progress",))
    oos = {"contracts/progress.md": "模块 progress\n", "services/graph.zs": "业务 graph\n结束\n"}
    f = Fake(plan=plan_for("progress", p4, oos))
    before = {str(x.relative_to(p4)): x.read_text(encoding="utf-8") for x in p4.rglob("*") if x.is_file()}
    r = V.run(p4, "模块 progress", TMP / "out_fl_oos", model=f, pack="dslproj")
    after = {str(x.relative_to(p4)): x.read_text(encoding="utf-8") for x in p4.rglob("*") if x.is_file()}
    check(r["status"] == "失败" and "范围拦截" in r["stop"] and before == after, "改约定 / 上游文件 → 被拦、失败、项目原样", r["stop"])
    # 5 写进范围内但内容不合约定（函数头改了）：比对约定不过 → 补改
    p5 = skeleton("fl_head")
    wrong = dict(files)
    wrong["services/graph.zs"] = files["services/graph.zs"].replace("公开 函数 加边 src dst", "公开 函数 加边 dst src")
    plan5 = plan_for("graph", p5, wrong).replace("  终止 成功 三项检查都过\n结束\n", "  终止 成功 先这样\n结束\n", 1)
    f = Fake(plan=plan5.replace("终止 成功 做完了\n", "终止 成功 到此\n"),
             fix={"结果": {"edits": [{"file": "services/graph.zs", "old": "公开 函数 加边 dst src", "new": "公开 函数 加边 src dst"}], "说明": "函数头改回约定"}, "状态": "成功", "原因": ""})
    r = V.run(p5, "模块 graph", TMP / "out_fl_head", model=f, pack="dslproj")
    check(r["status"] in ("成功", "失败") and "比对约定：函数「加边」入参约定是 src dst" in f.log[1][2], "函数头与约定不符：问题里带比对约定的差异", f.log[1][2][-900:] if len(f.log) > 1 else r["stop"])
    # 6 入口 run_task：失败 / 成功 + 模块名缺失
    p6 = skeleton("fl_entry")
    r = entry.run_task(p6, "模块 graph", "dslproj", model=Fake(plan=plan_for("graph", p6)), out=TMP / "out_fl_entry")
    check(r["状态"] == "成功" and r["原因"] == "" and abs(r["花费"] - 0.01) < 1e-9, "run_task(pack=dslproj)：{状态, 原因, 花费}", r)
    r = entry.run_task(skeleton("fl_nomod"), "做点什么", "dslproj", model=Fake(plan="x"))
    check(r["状态"] == "失败" and "模块" in r["原因"], "任务里没有模块行 → 失败并说明", r)
    check(SC.guard("services/progress.zs") == "", "流程结束后范围拦截关闭")


def main():
    try:
        t_contract()
        t_project()
        t_compare()
        t_cases()
        t_accept_materials()
        t_flow()
    finally:
        SC.activate(None)
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
