# -*- coding: utf-8 -*-
"""dslproj 资料包：约定解析 / 检查、比对约定、跑用例（空库、固定时间、单模块）、验收、资料、动词、整条流程（假模型）。不调真模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_dslproj.py

参考实现（graph：知识点 + 加边带环检查；progress：作答 + 记作答，依赖 graph）在 tests/tools/fixtures/dslproj_solution/，约定和用例也在那里。
"""
import json
import inspect
import os
import re
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
    """files：{相对路径: 新内容}。文件已存在 → old = 现有全文，否则 old 空串（新建）。返回 #改法 段文本（JSON 列表）。"""
    items = []
    for rel, new in files.items():
        f = Path(project) / rel
        items.append({"file": rel, "old": f.read_text(encoding="utf-8").rstrip("\n") if f.is_file() else "", "new": new.rstrip("\n")})
    return f"#改法 {name}\n[\n" + ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in items) + "\n]\n"


def solution_files(module):
    return {str(f.relative_to(SOL)): f.read_text(encoding="utf-8") for g in P.scope_globs(module) for f in sorted(SOL.glob(g)) if f.is_file()}


def plan_for(module, project, files=None, tail="终止 成功 做完了"):
    head = (f"用包 common text code dslproj\n预算 调用 4 秒 600\n设 m = {module}\n设 res = 改文件 {{e1}}\n如果 {{res.ok}} 不等于 是\n  终止 失败 改法没套上：{{res.msg}}\n结束\n"
            "设 c = 加载检查 {m}\n设 d = 比对约定 {m}\n设 t = 跑用例 {m}\n"
            "如果 {c.ok} 等于 是 且 {d.consistent} 等于 是 且 {t.all_passed} 等于 是\n  终止 成功 三项检查都过\n结束\n" + tail + "\n\n")
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
    # B1：表 <名> 学习记录 标注
    lr, lr_probs = C.parse("模块 x\n## 表\n表 x_log 学习记录\n  id 整数 主键\n## 函数\n公开 函数 f a\n## 用例\n用例 u1\n  调用 f a=1\n  得 有返回\n")
    check(not lr_probs and lr["表"][0]["学习记录"] is True, "表 后面加「学习记录」→ 标记为真", lr_probs)
    plain, plain_probs = C.parse("模块 x\n## 表\n表 x_t\n  id 整数 主键\n## 函数\n公开 函数 f a\n## 用例\n用例 u1\n  调用 f a=1\n  得 有返回\n")
    check(not plain_probs and plain["表"][0]["学习记录"] is False, "表 不加标注 → 学习记录是 False", plain_probs)
    _, bad_flag_probs = C.parse("模块 x\n## 表\n表 x_t 乱写\n")
    check(any("表 <表名> [学习记录]" in x for x in bad_flag_probs), "表名后面不是「学习记录」的乱写标注 → 报错", bad_flag_probs)
    # B1：用例「先 文件 <路径> [内容=…]」
    uf, uf_probs = C.parse("模块 x\n## 函数\n公开 函数 f a\n## 用例\n用例 u1\n  先 文件 uploads/a.md 内容=第一行\\n第二行\n  调用 f a=1\n  得 有返回\n")
    st = uf["用例"][0]["先"][0]
    check(not uf_probs and st == {"种类": "文件", "路径": "uploads/a.md", "内容": "第一行\\n第二行", "行": st["行"]}, "先 文件 解析：路径 + 内容（字面 \\n，写文件时再还原）", (uf_probs, st))
    check(any("相对路径且不含 .." in x for x in C.check(C.parse('模块 x\n## 函数\n公开 函数 f a\n## 用例\n用例 u1\n  先 文件 /etc/passwd\n  调用 f a=1\n  得 有返回\n')[0], "x", {}, ["x"])),
          "先 文件 的路径不能是绝对路径 → 约定检查报错")
    check(any("相对路径且不含 .." in x for x in C.check(C.parse('模块 x\n## 函数\n公开 函数 f a\n## 用例\n用例 u1\n  先 文件 a/../../b.md\n  调用 f a=1\n  得 有返回\n')[0], "x", {}, ["x"])),
          "先 文件 的路径含 .. → 约定检查报错")
    # B2：接口「上传 <字段> [类型 …] [上限 …]」
    up_text = ("模块 x\n## 函数\n公开 函数 f file_path\n## 接口\nPOST /x/f -> f 上传 file 类型 pdf,docx,md,txt 上限 20MB 角色 teacher\n"
               "## 用例\n用例 u1\n  先 文件 uploads/a.md 内容=x\n  调用 f file_path=uploads/a.md\n  得 有返回\n")
    uc, up_probs = C.parse(up_text)
    i0 = uc["接口"][0]
    check(not up_probs and i0["上传"] == {"字段": "file", "类型": "pdf,docx,md,txt", "上限": "20MB"} and i0["角色"] == "teacher",
          "接口「上传 字段 类型 … 上限 …」解析（标记顺序不限）", (up_probs, i0))
    nc, nprobs = C.parse("模块 x\n## 函数\n公开 函数 f a\n## 接口\nGET /x/f -> f\n## 用例\n用例 u1\n  调用 f a=1\n  得 有返回\n")
    check(not nprobs and nc["接口"][0]["上传"] is None, "没写「上传」→ 上传是 None", nprobs)
    _, bad_size_probs = C.parse(up_text.replace("上限 20MB", "上限 不知道"))
    check(any("上限 不知道" in x and "写错了" in x for x in bad_size_probs), "上限格式不对 → 报错", bad_size_probs)
    _, bad_tok_probs = C.parse(up_text.replace("角色 teacher", "乱写 teacher"))
    check(any("不认识的接口标记" in x for x in bad_tok_probs), "不认识的接口标记 → 报错", bad_tok_probs)
    mc, mprobs = C.parse("模块 x\n## 函数\n公开 函数 f a\n## 接口\nPOST /x/f -> f 上传 file\n## 用例\n用例 u1\n  调用 f a=1\n  得 有返回\n")
    check(not mprobs, "基本解析通过（函数缺 <字段>_path 的检查放在 check() 里）", mprobs)
    check_probs = C.check(mc, "x", {}, ["x"])
    check(any("没有入参「file_path」" in x for x in check_probs), "上传声明了字段但函数没有 <字段>_path 入参 → 检查报错", check_probs)
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
    _, pr_priv = C.parse("模块 x\n## 函数\n私有 函数 f a\n")
    check(any("不用写「私有」前缀" in x for x in pr_priv), "「私有 函数」→ 清楚提示去掉前缀", pr_priv)
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
    check(any("多余依赖" in x for x in C.check({**cc, "依赖": ["y"]}, "x", {"y": {"函数": [{"名": "ok", "公开": True}]}}, ["x", "y"])),
          "依赖声明了但伪代码 / 用例里都没调用过 → 多余依赖")
    used = C.parse("模块 x\n依赖 y\n## 函数\n公开 函数 f a\n  伪代码 调用 y.ok\n## 用例\n用例 u1\n  调用 f a=1\n  得 k=v\n")[0]
    check(C.check(used, "x", {"y": {"函数": [{"名": "ok", "公开": True}]}}, ["x", "y"]) == [], "依赖在伪代码里调用过 → 不是多余依赖")


# ------------------------------------------------------------------ 二、项目约定


def t_project():
    print("二、项目约定：模块名 / 范围 / 约定读取 / 依赖闭包")
    check(P.module_of("请做\n模块 graph\n补充说明") == "graph" and P.module_of("模块: progress") == "progress" and P.module_of("没有") is None, "module_of")
    check(P.scope_globs("graph") == ["entities/graph.entity", "services/graph.zs", "routes/graph*.zs", "queries/graph_*.sql", "scripts/graph_*.zs", "tests/graph_*"], "范围 = 6 类路径（含 scripts/<模块>_*.zs）")
    sc = SC.parse(P.scope_globs("graph"))
    check(all(SC.inside(x, sc) for x in ("entities/graph.entity", "services/graph.zs", "routes/graph.zs", "routes/graph_api.zs", "queries/graph_edge_insert.sql", "scripts/graph_run.zs", "tests/graph_cases.zs"))
          and not any(SC.inside(x, sc) for x in ("contracts/graph.md", "services/progress.zs", "routes/progress.zs", "queries/progress_x.sql", "entities/progress.entity", "scripts/progress_run.zs", "scripts/helper.zs")),
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
    # B1：表带「学习记录」标注 → 比对约定要求 routes/ 下有「迁移 只加」声明（骨架生成 routes/_project.zs）
    lr_proj = TMP / "cmp_lr"
    (lr_proj / "routes").mkdir(parents=True, exist_ok=True)
    lr_contract = C.parse("模块 lrmod\n## 表\n表 lrmod_log 学习记录\n  id 整数 主键\n## 函数\n公开 函数 f a\n## 用例\n用例 u\n  调用 f a=1\n  得 有返回\n")[0]
    d = P.compare(lr_proj, "lrmod", lr_contract, ["lrmod"])["差异"]
    check(any("学习记录" in x and "迁移 只加" in x for x in d), "表带「学习记录」但 routes/ 没开「迁移 只加」→ 比对约定报差异", d)
    (lr_proj / "routes" / "_project.zs").write_text("迁移 只加\n", encoding="utf-8")
    d2 = P.compare(lr_proj, "lrmod", lr_contract, ["lrmod"])["差异"]
    check(not any("学习记录" in x for x in d2), "加上 routes/_project.zs「迁移 只加」后这条差异消失", d2)


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
    r = CS.run(SOL, "progress")
    check(r["全过"], "未设 DSL_NOW 时默认固定为 2026-01-01，用例确定", r)
    os.environ["DSL_NOW"] = "2030-05-06 07:08:09"
    try:
        r = CS.run(SOL, "progress")
        check(not r["全过"], "环境已设 DSL_NOW 时不覆盖（沿用 2030，依赖 2026-01-01 的用例失败）", r)
        check(os.environ.get("DSL_NOW") == "2030-05-06 07:08:09", "已设的 DSL_NOW 跑完原样保留")
    finally:
        os.environ.pop("DSL_NOW", None)
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


def t_case_files():
    print("四之零：用例「先 文件 <路径> [内容=…]」——跑的时候在临时项目里造出文件，调用时直接传 file_path，跑完删除；没有表的模块不要求 entities 文件")
    p = TMP / "cs_files"
    shutil.rmtree(p, ignore_errors=True)
    (p / "services").mkdir(parents=True)
    (p / "contracts").mkdir(parents=True)
    check(not (p / "entities" / "upl.entity").exists(), "没有表的模块：entities/upl.entity 不存在")
    (p / "services" / "upl.zs").write_text(
        "业务 upl\n  用包 common\n  公开 函数 读内容 file_path\n    读取 content = {file_path}\n    返回 {\"content\": content}\n  结束\n结束\n",
        encoding="utf-8")
    (p / "contracts" / "upl.md").write_text(
        "模块 upl\n## 函数\n公开 函数 读内容 file_path\n  返回 {content}\n"
        "## 用例\n用例 读内容_有文件\n  先 文件 uploads/a.md 内容=第一行\\n第二行\n  调用 读内容 file_path=uploads/a.md\n  得 有返回\n"
        "用例 读内容_没文件\n  调用 读内容 file_path=uploads/a.md\n  得 有返回\n", encoding="utf-8")
    r = CS.run(p, "upl")
    check(r["总数"] == 2, "没有表的模块（没有 entities/upl.entity）也能正常跑用例，不报缺实体", r)
    fails = {f["名"]: f["原因"] for f in r["失败"]}
    check("读内容_有文件" not in fails, "先 文件 造出的文件，业务函数当场能读到", fails.get("读内容_有文件"))
    check("读内容_没文件" in fails and "文件不存在" in fails.get("读内容_没文件", ""), "上一个用例的文件跑完就删了，不留给下一个用例", fails.get("读内容_没文件"))
    # 路径限相对、不含 ..：直接调用写文件的动词也要拦一道（约定检查已经拦过，这里是跑的时候再保险一次）
    why = CS.write_case_files(p, {"先": [{"种类": "文件", "路径": "/etc/passwd", "内容": "x"}]})
    check("相对路径且不含 .." in why, "write_case_files 对绝对路径再保险拦一次", why)
    why = CS.write_case_files(p, {"先": [{"种类": "文件", "路径": "a/../../b.md", "内容": "x"}]})
    check("相对路径且不含 .." in why, "write_case_files 对含 .. 的路径再保险拦一次", why)


def t_settle():
    print("四之一：cases.settle 等「后台执行」的后台任务跑完")
    import threading
    import time as _time
    from tools.dsl import _submit_background

    done = threading.Event()
    _submit_background(lambda: (_time.sleep(0.15), done.set()))
    check(not done.is_set(), "后台任务刚提交，还没跑完（故意睡一下）")
    CS.settle(timeout=3)
    check(done.is_set(), "settle() 等到后台任务真的跑完才返回，不是掐时间猜")
    held = threading.Event()
    _submit_background(lambda: held.wait(2))
    try:
        CS.settle(timeout=0.05)
        check(False, "跑不完该抛 TimeoutError")
    except TimeoutError as e:
        check("秒内没跑完" in str(e), "settle() 超时抛 TimeoutError（不是悄悄放过去对还没写完的库）", e)
    finally:
        held.set()
    src = inspect.getsource(CS.seed_case) + inspect.getsource(CS.run_case)
    check(src.count("settle()") >= 2, "run_case（靠 seed_case 造「先」数据）里每次「调用」（先 的和正式的）后都 settle()，不止查最后一次", src)


# ------------------------------------------------------------------ 五、验收 / 资料 / 动词


def t_scripts():
    print("六、模块脚本（scripts/<模块>_*.zs）：范围 / ## 脚本 约定 / 比对 / 加载检查 / 后台任务实跑")
    from tools.dslagent import loadcheck as LC
    BG = ROOT / "tests" / "tools" / "fixtures" / "dslproj_bg"

    # ---- 范围：scripts/<m>_*.zs，同前缀按最长模块名归属
    check("scripts/jobs_*.zs" in P.scope_globs("jobs"), "scope_globs 含 scripts/<模块>_*.zs")
    p = TMP / "sc_scope"
    shutil.rmtree(p, ignore_errors=True)
    (p / "contracts").mkdir(parents=True)
    (p / "scripts").mkdir()
    for m in ("quiz", "quiz_knowledge", "graph"):
        (p / "contracts" / f"{m}.md").write_text("模块 x\n", encoding="utf-8")
    for f in ("quiz_run.zs", "quiz_knowledge_import.zs", "quiz_extra.zs", "graph_run.zs", "helper.zs"):
        (p / "scripts" / f).write_text("# x\n", encoding="utf-8")
    g = P.scope_globs("quiz", p)
    check("scripts/quiz_*.zs" not in g and "scripts/quiz_run.zs" in g and "scripts/quiz_extra.zs" in g
          and "scripts/quiz_knowledge_import.zs" not in g and not any(SC.inside("scripts/quiz_knowledge_import.zs", SC.parse([x])) for x in g if "scripts" in x),
          "同前缀模块（quiz / quiz_knowledge）：quiz 的范围不含 quiz_knowledge 的脚本", g)
    check(any(SC.inside("scripts/quiz_newone.zs", SC.parse([x])) for x in g) and not any(SC.inside("scripts/quiz_knowledge_new.zs", SC.parse([x])) for x in g),
          "quiz 仍能新建 scripts/quiz_newone.zs，但新建不了 quiz_knowledge_ 开头的", g)
    check("scripts/quiz_knowledge_*.zs" in P.scope_globs("quiz_knowledge", p) and "scripts/graph_*.zs" in P.scope_globs("graph", p), "没有同前缀模块的仍是前缀 glob")
    check(P.scope_files(p, "quiz") == ["scripts/quiz_extra.zs", "scripts/quiz_run.zs"], "scope_files(quiz) 的脚本不含 quiz_knowledge、helper", P.scope_files(p, "quiz"))
    check(P.scope_files(p, "quiz_knowledge") == ["scripts/quiz_knowledge_import.zs"] and P.scope_files(p, "graph") == ["scripts/graph_run.zs"], "scope_files 另两个模块")
    mods = ["graph", "quiz", "quiz_knowledge"]
    check(P.script_owner("quiz_knowledge_import", mods) == "quiz_knowledge" and P.script_owner("quiz_run", mods) == "quiz" and P.script_owner("helper", mods) is None,
          "script_owner：最长模块名归属，没有前缀的无主")

    # ---- ## 脚本 解析
    c, probs = C.parse((BG / "contracts" / "jobs.md").read_text(encoding="utf-8"))
    check(not probs and len(c["脚本"]) == 1, "fixture 约定（带 ## 脚本）解析无问题", probs)
    sc = c["脚本"][0]
    check(sc["路径"] == "scripts/jobs_run.zs" and sc["入参"] == ["job_id"] and sc["出错"] == "scripts/jobs_run_fail.zs" and "逐项处理" in sc["作用"],
          "## 脚本 一行解析：路径 / 入参 / 出错 / 作用", sc)
    check(C.declared_scripts(c) == ["scripts/jobs_run.zs", "scripts/jobs_run_fail.zs"], "declared_scripts 含出错脚本")
    base = "模块 jobs\n## 函数\n公开 函数 f a\n## 用例\n用例 u\n  调用 f a=1\n  得 有返回\n"
    c0, p0 = C.parse(base)
    check(not p0 and c0["脚本"] == [] and C.check(c0, "jobs", {}, ["jobs"]) == [], "不写 ## 脚本：脚本为空，约定检查不变")
    c1, p1 = C.parse(base + "## 脚本\nscripts/jobs_x.zs\n")
    check(not p1 and c1["脚本"][0]["入参"] == [] and c1["脚本"][0]["出错"] == "" and c1["脚本"][0]["作用"] == "", "入参 / 出错 / 作用 都可省")
    c2, p2 = C.parse(base + "## 脚本\nscripts/jobs_x.zs 入参 a,b;出错 scripts/jobs_x_fail.zs;做事 # 注释\n")
    check(not p2 and c2["脚本"][0]["入参"] == ["a", "b"] and c2["脚本"][0]["出错"] == "scripts/jobs_x_fail.zs" and c2["脚本"][0]["作用"] == "做事", "半角分号、行尾注释也行", c2["脚本"])
    for bad, why in (("jobs_x.zs", "不带 scripts/"), ("scripts/Jobs X.zs", "大写 / 空格"), ("scripts/jobs_x.zs 参数 a", "不是「入参」"), ("scripts/jobs_x.zs 入参 A", "入参非 snake"),
                     ("scripts/jobs_x.zs；出错 helper.zs", "出错脚本写法不对")):
        _, pb = C.parse(base + f"## 脚本\n{bad}\n")
        check(pb, f"## 脚本 写错被指出：{why}", bad)

    # ---- 约定检查：归属本模块
    mods2 = ["jobs", "jobs_extra", "graph"]
    for line, want in (("scripts/graph_x.zs", "不属于本模块"), ("scripts/helper.zs", "不属于本模块"),
                       ("scripts/jobs_extra_x.zs", "归 jobs_extra"), ("scripts/jobs_x.zs；出错 scripts/graph_f.zs", "不属于本模块")):
        cc, _ = C.parse(base + f"## 脚本\n{line}\n")
        pr = C.check(cc, "jobs", {}, mods2)
        check(any(want in x for x in pr), f"脚本归属检查：{line} → {want}", pr)
    cc, _ = C.parse(base + "## 脚本\nscripts/jobs_x.zs\nscripts/jobs_x.zs\n")
    check(any("重复" in x for x in C.check(cc, "jobs", {}, mods2)), "脚本重复声明被指出")
    cc, _ = C.parse(base + "## 脚本\nscripts/jobs_x.zs；出错 scripts/jobs_y.zs\nscripts/jobs_y.zs\n")
    check(any("不能同时是别的脚本" in x for x in C.check(cc, "jobs", {}, mods2)), "出错脚本不能同时是主脚本")
    check(C.check(c, "jobs", {}, ["jobs"]) == [], "fixture 约定通过约定检查")

    # ---- 比对约定：缺文件 / 多出 / 归属错；fixture 一致
    def cmp(proj, module="jobs", mm=("jobs",)):
        cc, _ = P.load_contract(proj, module)
        return P.compare(proj, module, cc, list(mm))["差异"]
    fx = TMP / "sc_fx"
    shutil.rmtree(fx, ignore_errors=True)
    shutil.copytree(BG, fx)
    check(cmp(fx) == [], "fixture 项目：比对约定一致", cmp(fx))
    (fx / "scripts" / "jobs_run_fail.zs").rename(fx / "scripts" / "jobs_run_fail.bak")
    d = cmp(fx)
    check(any("缺脚本 scripts/jobs_run_fail.zs" in x for x in d), "声明的出错脚本不存在 → 缺脚本", d)
    (fx / "scripts" / "jobs_run_fail.bak").rename(fx / "scripts" / "jobs_run_fail.zs")
    (fx / "scripts" / "jobs_run.zs").unlink()
    check(any("缺脚本 scripts/jobs_run.zs" in x for x in cmp(fx)), "声明的主脚本不存在 → 缺脚本")
    shutil.copy(BG / "scripts" / "jobs_run.zs", fx / "scripts" / "jobs_run.zs")
    (fx / "scripts" / "jobs_extra_job.zs").write_text("# 没声明\n", encoding="utf-8")
    d = cmp(fx)
    check(any("多了约定里没有声明的脚本 scripts/jobs_extra_job.zs" in x for x in d), "scripts/<模块>_* 多出没声明的 → 差异", d)
    (fx / "scripts" / "jobs_extra_job.zs").unlink()
    # 别的模块的脚本不算本模块多出的；同前缀更长模块认走的也不算
    (fx / "scripts" / "other_run.zs").write_text("# x\n", encoding="utf-8")
    check(cmp(fx) == [], "别的前缀（other_）的脚本不算本模块多出")
    (fx / "contracts" / "jobs_extra.md").write_text("模块 jobs_extra\n", encoding="utf-8")
    (fx / "scripts" / "jobs_extra_x.zs").write_text("# x\n", encoding="utf-8")
    cc, _ = P.load_contract(fx, "jobs")
    check(P.compare(fx, "jobs", cc, ["jobs", "jobs_extra"])["差异"] == [], "同前缀更长的模块 jobs_extra 的脚本不算 jobs 多出的")
    # 不写 ## 脚本 的旧约定：没有脚本文件时行为不变；有 scripts/<m>_* 文件则算多出
    for m in ("graph", "progress"):
        cc, _ = P.load_contract(SOL, m)
        check(P.script_diffs(SOL, m, cc, ["graph", "progress"]) == [], f"旧约定 {m}（无 ## 脚本、无脚本文件）：脚本差异为空")
    old = copy_sol("sc_old")
    (old / "scripts").mkdir()
    (old / "scripts" / "graph_x.zs").write_text("# x\n", encoding="utf-8")
    cc, _ = P.load_contract(old, "graph")
    check(any("多了约定里没有声明的脚本" in x for x in P.script_diffs(old, "graph", cc, ["graph", "progress"])), "旧约定但 scripts/graph_* 有文件 → 多出")
    # 声明的脚本文件名归属错（约定检查会拦，这里比对也指出）
    wrong = TMP / "sc_wrong"
    shutil.rmtree(wrong, ignore_errors=True)
    shutil.copytree(BG, wrong)
    cc, _ = C.parse((BG / "contracts" / "jobs.md").read_text(encoding="utf-8").replace("scripts/jobs_run.zs 入参", "scripts/graph_run.zs 入参"))
    (wrong / "scripts" / "graph_run.zs").write_text("# x\n", encoding="utf-8")
    d = P.script_diffs(wrong, "jobs", cc, ["jobs", "graph"])
    check(any("不属于本模块" in x for x in d), "声明的脚本文件名不归本模块 → 比对指出", d)

    # ---- 骨架：不生成脚本；函数伪代码里的「后台执行 …」写进注释，模型照着实现
    from tools.dslagent.v3 import scaffold as SCF
    st = SCF.service_text("jobs", c)
    check("# 伪代码" not in st and "事务结束之后 后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/jobs_run_fail.zs" in st and "scripts" not in SCF.service_text("graph", P.load_contract(SOL, "graph")[0]),
          "骨架：services 注释里能看到后台执行伪代码；骨架不生成脚本文件")

    # ---- 加载检查：执行 / 后台执行 scripts/…
    check(LC.check_project(BG, scripts=True) == [], "fixture 项目：加载检查无问题", LC.check_project(BG, scripts=True))
    gen_lc = TMP / "lc_gen"
    shutil.rmtree(gen_lc, ignore_errors=True)
    shutil.copytree(BG, gen_lc)
    (gen_lc / "scripts" / "jobs_run.zs").unlink()
    check(LC.check_project(gen_lc) == [] and any("找不到脚本 scripts/jobs_run.zs" in x for x in LC.check_project(gen_lc, scripts=True)),
          "默认（生成阶段）不查脚本调用，核查阶段（scripts=True / load_problems）才查：脚本还没写出来时生成阶段不误拦")

    def lc_proj(name, svc_body="", script_files=None, route=""):
        q = TMP / name
        shutil.rmtree(q, ignore_errors=True)
        shutil.copytree(BG, q)
        if svc_body:
            t = (q / "services" / "jobs.zs").read_text(encoding="utf-8")
            a = "    后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/jobs_run_fail.zs\n    返回 {\"job_id\": {job_id}}"
            assert a in t
            (q / "services" / "jobs.zs").write_text(t.replace(a, "    " + svc_body + "\n    返回 {\"job_id\": {job_id}}", 1), encoding="utf-8")
        for rel, txt in (script_files or {}).items():
            (q / rel).write_text(txt, encoding="utf-8")
        if route:
            (q / "routes" / "jobs.zs").write_text(route, encoding="utf-8")
        return q
    q = lc_proj("lc1", "后台执行 scripts/jobs_nope.zs job_id={job_id}")
    pr = LC.check_project(q, scripts=True)
    check(any("services/jobs.zs 函数 提交任务" in x and "找不到脚本 scripts/jobs_nope.zs" in x for x in pr), "加载检查：后台执行的脚本不存在", pr)
    q = lc_proj("lc2", "后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/jobs_gone.zs")
    pr = LC.check_project(q, scripts=True)
    check(any("找不到on_error 脚本 scripts/jobs_gone.zs" in x for x in pr), "加载检查：on_error 指向的脚本不存在", pr)
    q = lc_proj("lc3", "后台执行 scripts/other_run.zs job_id={job_id}", {"scripts/other_run.zs": "设 x = 1\n"})
    pr = LC.check_project(q, scripts=True)
    check(any("scripts/other_run.zs 不属于本模块 jobs" in x for x in pr), "加载检查：业务函数后台执行不以「<本模块>_」开头的脚本", pr)
    q = lc_proj("lc4", "执行 scripts/graph_run.zs job_id={job_id}", {"scripts/graph_run.zs": "设 x = 1\n"})
    (q / "contracts" / "graph.md").write_text("模块 graph\n", encoding="utf-8")
    pr = LC.check_project(q, scripts=True)
    check(any("它归 graph" in x and "跨模块不能执行别人的脚本" in x for x in pr), "加载检查：跨模块执行别人的脚本（执行 与 后台执行 同规则）", pr)
    q = lc_proj("lc5", "后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/graph_fail.zs", {"scripts/graph_fail.zs": "设 x = 1\n"})
    (q / "contracts" / "graph.md").write_text("模块 graph\n", encoding="utf-8")
    check(any("on_error 脚本 scripts/graph_fail.zs 不属于本模块" in x for x in LC.check_project(q, scripts=True)), "加载检查：on_error 脚本归别的模块")
    q = lc_proj("lc6", "", {"scripts/jobs_run.zs": "执行 scripts/jobs_nope2.zs a=1\n" + (BG / "scripts" / "jobs_run.zs").read_text(encoding="utf-8")})
    check(any("scripts/jobs_run.zs: 第 1 行" in x and "找不到脚本 scripts/jobs_nope2.zs" in x for x in LC.check_project(q, scripts=True)), "加载检查：脚本里 执行 的脚本不存在")
    q = lc_proj("lc7", "", route='接口 POST /jobs/x\n  后台执行 scripts/jobs_none.zs a=1\n  返回 {"ok": 1}\n结束\n')
    check(any("routes/jobs.zs 接口 POST /jobs/x" in x and "找不到脚本 scripts/jobs_none.zs" in x for x in LC.check_project(q, scripts=True)), "加载检查：接口里 后台执行 的脚本不存在")
    q = lc_proj("lc8", "后台执行 scripts/jobs_run.zs job_id={job_id}")
    check(LC.check_project(q, scripts=True) == [], "on_error 可省；本模块脚本（存在、前缀对）无问题")
    q = lc_proj("lc9", "", {"scripts/jobs_run.zs": "设 s = 调用 jobs.待处理项 job_id={job_id}\n"})
    t = (q / "services" / "jobs.zs").read_text(encoding="utf-8").replace("公开 函数 待处理项", "函数 待处理项")
    (q / "services" / "jobs.zs").write_text(t, encoding="utf-8")
    pr = LC.check_project(q, scripts=True)
    check(any("scripts/jobs_run.zs" in x and "不是公开函数" in x for x in pr), "加载检查：脚本里调本模块私有函数被拒（脚本只能调公开函数）", pr)
    keys = P.load_problems(lc_proj("lc10", "后台执行 scripts/jobs_nope.zs a=1"), "jobs", ["jobs"])
    check(any("找不到脚本" in x for x in keys), "load_problems（核查阶段）带出本模块脚本调用的问题", keys)
    kg_like = TMP / "lc_legacy"
    shutil.rmtree(kg_like, ignore_errors=True)
    (kg_like / "scripts").mkdir(parents=True)
    (kg_like / "routes").mkdir()
    (kg_like / "scripts" / "pick.zs").write_text("设 x = 1\n", encoding="utf-8")
    (kg_like / "routes" / "a.zs").write_text('接口 POST /a/x\n  执行 scripts/pick.zs k=1\n  后台执行 scripts/pick.zs k=2\n  返回 {"ok": 1}\n结束\n', encoding="utf-8")
    check(LC.check_project(kg_like, scripts=True) == [], "不属于任何模块的老项目（无 services / contracts）：执行 / 后台执行 scripts/ 只查存在，无问题")

    # ---- 实跑（不调模型）：业务函数里后台执行脚本、脚本调本模块函数、on_error 记失败、跑用例 settle 等后台完成
    r = CS.run(BG, "jobs")
    check(r["全过"] and r["总数"] == 17, "fixture 17 条用例全过：提交→后台逐项处理→某项为空记失败原因；任务级出错走 on_error；重试", r["原因"])
    names = {u["名"] for u in c["用例"]}
    check({"提交任务_全成功", "提交任务_某项为空记失败原因", "提交任务_任务级出错走on_error", "重试失败项_失败项重新处理"} <= names, "覆盖后台完成 / 失败项 / on_error / 重试用例")
    # 用例的期望没有 settle 就对不上：把脚本里的处理去掉，后台跑完后库里仍是待处理 → 用例要判失败（证明不是碰巧对上）
    brk = TMP / "sc_brk"
    shutil.rmtree(brk, ignore_errors=True)
    shutil.copytree(BG, brk)
    (brk / "scripts" / "jobs_run.zs").write_text("设 s = 调用 jobs.开始 job_id={job_id}\n", encoding="utf-8")
    r2 = CS.run(brk, "jobs")
    check(not r2["全过"] and any(f["名"] == "提交任务_全成功" for f in r2["失败"]), "脚本不处理各项 → 用例失败（后台真的在跑，不是同步碰巧对）", r2["原因"][:300])
    # 脚本里调私有函数：运行期同样被拒，on_error 把任务标失败
    prv = TMP / "sc_prv"
    shutil.rmtree(prv, ignore_errors=True)
    shutil.copytree(BG, prv)
    t = (prv / "services" / "jobs.zs").read_text(encoding="utf-8").replace("公开 函数 开始", "函数 开始")
    (prv / "services" / "jobs.zs").write_text(t, encoding="utf-8")
    cp = (prv / "contracts" / "jobs.md").read_text(encoding="utf-8").replace("公开 函数 开始", "函数 开始")
    cp = re.sub(r"(?ms)^用例 开始_[^\n]*\n.*?(?=^用例 |\Z)", "", cp)
    (prv / "contracts" / "jobs.md").write_text(cp.rstrip() + "\n", encoding="utf-8")
    r3 = CS.run(prv, "jobs")
    check(any(f["名"] == "提交任务_全成功" for f in r3["失败"]), "脚本调私有函数「开始」：运行期被拒，任务不会完成（用例失败）", r3["原因"][:300])


def t_content():
    print("七、模块内容文件（content/<模块>/…）：## 内容文件 约定 / 比对 / 写路径加载检查 / 临时 workspace 实跑")
    from tools.dslagent import loadcheck as LC
    CT = ROOT / "tests" / "tools" / "fixtures" / "dslproj_ct"

    # ---- 范围：content/<模块>/** 不进写入范围（运行期写盘不经 STRICT_SCOPE，模型也不用建这些文件）
    check(not any("content" in g for g in P.scope_globs("cards")), "scope_globs 不含 content/（内容文件是运行期写出来的，不是模型写的代码）", P.scope_globs("cards"))
    SC.activate(P.scope_globs("cards"))
    try:
        check(SC.guard("content/cards/cards.jsonl") != "" and SC.guard("services/cards.zs") == "", "STRICT_SCOPE 只拦构建阶段 code 包的写（scope.guard）：模型写 content/ 被拦，写 services 放行")
    finally:
        SC.activate(None)

    # ---- ## 内容文件 解析
    c, probs = C.parse((CT / "contracts" / "cards.md").read_text(encoding="utf-8"))
    check(not probs and len(c["内容文件"]) == 2, "fixture 约定（带 ## 内容文件）解析无问题", probs)
    x = c["内容文件"][0]
    check(x["路径"] == "content/cards/cards.jsonl" and x["字段"] == ["card_no", "front", "back"] and x["写"] == ["保存卡片", "撤下全部"]
          and x["读"] == ["按文件重灌", "读回卡片", "撤下全部"] and "库按它重灌" in x["作用"], "## 内容文件 一行解析：路径 / 字段 / 写 / 读 / 作用", x)
    check(C.declared_content(c) == ["content/cards/cards.jsonl", "content/cards/cards.withdrawn.jsonl"], "declared_content")
    check(C.check(c, "cards", {}, ["cards"]) == [], "fixture 约定检查无问题")
    base = "模块 cards\n## 函数\n公开 函数 f a\n公开 函数 g\n## 用例\n用例 u\n  调用 f a=1\n  得 有返回\n用例 u2\n  调用 g\n  得 有返回\n"
    c0, p0 = C.parse(base)
    check(not p0 and c0["内容文件"] == [] and C.check(c0, "cards", {}, ["cards"]) == [], "不写 ## 内容文件：为空，约定检查不变")
    c1, p1 = C.parse(base + "## 内容文件\ncontent/cards/a.jsonl\n")
    check(not p1 and c1["内容文件"][0]["字段"] == [] and c1["内容文件"][0]["写"] == [] and c1["内容文件"][0]["作用"] == "" and C.check(c1, "cards", {}, ["cards"]) == [], "字段 / 写 / 读 / 作用 都可省")
    c2, p2 = C.parse(base + "## 内容文件\ncontent/cards/{deck}/a.json 字段 a;写:f;读:无;作用 # 注释\n")
    check(not p2 and c2["内容文件"][0]["写"] == ["f"] and c2["内容文件"][0]["读"] == [] and C.check(c2, "cards", {}, ["cards"]) == [], "半角分号冒号、读：无、路径带 {变量}、.json、行尾注释", c2["内容文件"])
    for bad, why in (("cards/a.jsonl", "不带 content/"), ("content/cards/a.jsonl 列 a", "不是「字段」"), ("content/cards/a.jsonl 字段 A", "字段非 snake"),
                     ("content/cards/a.jsonl；写：本模块函数 f；写：本模块函数 g", None)):
        cb, pb = C.parse(base + f"## 内容文件\n{bad}\n")
        pk = pb + C.check(cb, "cards", {}, ["cards"])
        check(why is None or pk, f"## 内容文件 写错被指出：{why}", bad)
    for line, want in (("content/other/a.jsonl", "不属于本模块"), ("content/cards2/a.jsonl", "不属于本模块"), ("data/a.jsonl", "内容文件写法是"),
                       ("content/cards/a.md", "后缀只能是 .jsonl 或 .json"), ("content/cards/a.txt", "后缀只能是"), ("content/cards/../x/a.jsonl", "不能含 .."),
                       ("content/cards/a.jsonl；写：本模块函数 nope", "没有这个函数"), ("content/cards/a.jsonl；读：本模块函数 nope", "没有这个函数")):
        cc, pc = C.parse(base + f"## 内容文件\n{line}\n")
        pk = pc + C.check(cc, "cards", {}, ["cards"])
        check(any(want in q for q in pk), f"约定检查：{line} → {want}", pk)
    cd, _ = C.parse(base + "## 内容文件\ncontent/cards/a.jsonl\ncontent/cards/a.jsonl\n")
    check(any("重复" in q for q in C.check(cd, "cards", {}, ["cards"])), "约定检查：内容文件路径重复")

    # ---- 比对约定：代码里写 / 读的本模块 content 路径要在 ## 内容文件 里声明
    def proj(name, svc=None, contract=None):
        q = TMP / name
        shutil.rmtree(q, ignore_errors=True)
        shutil.copytree(CT, q)
        if svc:
            (q / "services" / "cards.zs").write_text(svc((q / "services" / "cards.zs").read_text(encoding="utf-8")), encoding="utf-8")
        if contract:
            (q / "contracts" / "cards.md").write_text(contract((q / "contracts" / "cards.md").read_text(encoding="utf-8")), encoding="utf-8")
        return q

    def cmp(q):
        cc, _ = C.parse((q / "contracts" / "cards.md").read_text(encoding="utf-8"))
        return P.compare(q, "cards", cc, ["cards"])
    r = cmp(CT)
    check(r["一致"] and r["差异"] == [] and r["提示"] == [], "fixture 比对一致、没有提示", r)
    q = proj("ct_c1", svc=lambda s: s.replace("content/cards/cards.withdrawn.jsonl", "content/cards/other.jsonl", 1))
    r = cmp(q)
    check(not r["一致"] and any("content/cards/other.jsonl" in d and "没有在约定「## 内容文件」里声明" in d and "读回卡片" in d for d in r["差异"]), "函数里写了约定没声明的内容文件 → 差异", r["差异"])
    q = proj("ct_c2", contract=lambda s: re.sub(r"(?m)^content/cards/cards\.withdrawn\.jsonl.*\n", "", s))
    r = cmp(q)
    check(not r["一致"] and any("cards.withdrawn.jsonl" in d for d in r["差异"]), "约定少声明了一个文件（代码在读写）→ 差异", r["差异"])
    q = proj("ct_c3", contract=lambda s: s.replace("## 用例", "content/cards/unused.jsonl 字段 a；备用\n\n## 用例", 1))
    r = cmp(q)
    check(r["一致"] and any("unused.jsonl" in h and "写它" in h for h in r["提示"]) and any("unused.jsonl" in h and "读它" in h for h in r["提示"]),
          "声明了但没有任何函数写 / 读 → 只记提示，不判不一致", r)
    q = proj("ct_c4", svc=lambda s: s.replace("content/cards/cards.jsonl {rows}", "content/cards/{deck}.jsonl {rows}", 1),
             contract=lambda s: s.replace("content/cards/cards.jsonl 字段", "content/cards/{deck}.jsonl 字段", 1))
    r = cmp(q)
    check(not any("{deck}" in d for d in r["差异"]), "路径带 {变量}：和约定里同样带 {变量} 的声明对得上", r["差异"])
    q = proj("ct_c5", svc=lambda s: s.replace("content/cards/cards.jsonl {rows}", "content/cards/{deck}/all.jsonl {rows}", 1))
    r = cmp(q)
    check(any("{deck}/all.jsonl" in d for d in r["差异"]), "路径带 {变量}：前缀不在任何声明下 → 差异", r["差异"])
    old = TMP / "ct_old"
    shutil.rmtree(old, ignore_errors=True)
    shutil.copytree(SOL, old)
    ms = P.all_modules(old)
    okc = all(P.compare(old, m, P.load_contract(old, m)[0], ms)["一致"] for m in ms)
    check(okc and not P.content_uses(old, ms[0], ms), "旧约定（无 ## 内容文件、代码不碰 content/）：比对行为不变", ms)
    check(P.compare(old, ms[0], P.load_contract(old, ms[0])[0], ms)["提示"] == [], "旧约定没有内容文件提示")

    # ---- 加载检查：写路径规则
    def lc(name, body, module="cards", extra=None):
        q = proj(name)
        sv = (q / "services" / "cards.zs").read_text(encoding="utf-8")
        sv = sv.rstrip()[:-len("结束")].rstrip() + "\n\n  公开 函数 额外 a\n" + "".join(f"    {ln}\n" for ln in body.splitlines()) + "    返回 {\"ok\": 1}\n  结束\n结束\n"
        (q / "services" / "cards.zs").write_text(sv, encoding="utf-8")
        for rel, txt in (extra or {}).items():
            (q / rel).parent.mkdir(parents=True, exist_ok=True)
            (q / rel).write_text(txt, encoding="utf-8")
        return LC.check_project(q, scripts=True)
    check(LC.check_project(CT, scripts=True) == [], "fixture 加载检查无问题（本模块写 / 读 / 删自己的 content 路径）")
    check(lc("lw1", "设 w = 写JSONL content/cards/b.jsonl {a}\n设 w = 写JSON content/cards/c.json {a}\n设 d = 删文件 content/cards/b.jsonl\n写JSONL content/cards/d.jsonl {a}") == [],
          "本模块 content/<本模块>/ 下的 写JSONL / 写JSON / 删文件（含不带 设 的写法）通过")
    check(lc("lw2", "设 w = 写JSONL content/cards/{a}/x.jsonl {a}") == [], "路径带 {变量} 且前缀是 content/<本模块>/ 通过")
    pr = lc("lw3", "设 w = 写JSONL content/other/b.jsonl {a}")
    check(any("services/cards.zs 函数 额外" in x and "写JSONL" in x and "不是本模块的内容文件目录" in x for x in pr), "写别的模块的 content/ 目录 → 问题", pr)
    pr = lc("lw4", "设 w = 写JSON data/out.json {a}")
    check(any("写JSON" in x and "不在 content/cards/ 下" in x for x in pr), "写 content/ 以外的路径 → 问题", pr)
    pr = lc("lw5", "设 d = 删文件 uploads/x.pdf")
    check(any("删文件" in x and "不在 content/cards/ 下" in x for x in pr), "删 content/ 以外的文件 → 问题", pr)
    pr = lc("lw6", "设 w = 写JSONL content/{m}/b.jsonl {a}")
    check(any("content/{m}/b.jsonl" in x and "不是本模块的内容文件目录" in x for x in pr), "路径带 {变量} 但前缀在 {变量} 就断了（content/{m}/）→ 问题", pr)
    pr = lc("lw7", "设 f = content/cards/b.jsonl\n设 w = 写JSONL {f} {a}")
    check(any("整个是变量" in x for x in pr), "整个路径是变量（核不了归属）→ 问题", pr)
    check(lc("mv1", "设 m = 移动文件 content/cards/a.jsonl content/cards/a.withdrawn.jsonl\n移动文件 content/cards/{d}/a.jsonl content/cards/{d}/b.jsonl") == [],
          "移动文件 源和目标都在本模块 content/<本模块>/ 下（含不带 设、带 {变量}）通过")
    pr = lc("mv2", "设 m = 移动文件 content/cards/a.jsonl content/other/a.jsonl")
    check(any("移动文件" in x and "content/other/a.jsonl" in x and "不是本模块的内容文件目录" in x for x in pr), "移动文件 目标在别的模块 → 问题", pr)
    pr = lc("mv3", "设 m = 移动文件 content/other/a.jsonl content/cards/a.jsonl")
    check(any("移动文件" in x and "content/other/a.jsonl" in x for x in pr), "移动文件 源在别的模块 → 问题", pr)
    pr = lc("mv4", "设 m = 移动文件 content/cards/a.jsonl data/a.jsonl")
    check(any("移动文件" in x and "不在 content/cards/ 下" in x for x in pr), "移动文件 目标在 content/ 外 → 问题", pr)
    pr = lc("mv5", "设 m = 移动文件 uploads/a.jsonl content/cards/a.jsonl")
    check(any("移动文件" in x and "不在 content/cards/ 下" in x for x in pr), "移动文件 源在 content/ 外 → 问题", pr)
    # 比对约定：移动文件 的源和目标都按「写」算，约定没声明就是差异
    q = proj("ct_mv", svc=lambda s: s.replace("cards.jsonl content/cards/cards.withdrawn.jsonl", "cards.jsonl content/cards/moved.jsonl", 1))
    cc_, _ = C.parse((q / "contracts" / "cards.md").read_text(encoding="utf-8"))
    r = P.compare(q, "cards", cc_, ["cards"])
    check(not r["一致"] and any("content/cards/moved.jsonl" in d and "没有在约定「## 内容文件」里声明" in d for d in r["差异"]), "比对约定：移动文件 的目标路径没声明 → 差异", r["差异"])
    pr = lc("lw8", "设 w = 写JSONL content/cards/../other/b.jsonl {a}")
    check(any("不能含 .." in x for x in pr), "路径含 .. → 问题", pr)
    pr = lc("lw9", "读JSONL rows = content/other/x.jsonl")
    check(any("读JSONL" in x and "读别的模块的 content/ 不允许" in x for x in pr), "读别的模块的 content/（读JSONL 语句）→ 问题", pr)
    pr = lc("lw10", "读JSON r = content/other/x.json\n设 e = 存在 content/other/x.json\n设 l = 列文件 content/other")
    check(sum("读别的模块的 content/ 不允许" in x for x in pr) == 3, "读别的模块的 content/（读JSON / 存在 / 列文件）都报", pr)
    check(lc("lw11", "读JSONL rows = uploads/x.jsonl\n设 e = 存在 data/x.md") == [], "读 content/ 以外的路径不管")
    check(lc("lw12", "读JSONL rows = {f}") == [], "读的路径整个是变量：不查")
    pr = lc("lw13", "", extra={"scripts/cards_run.zs": "用包 data\n设 w = 写JSONL content/other/x.jsonl {a}\n写JSONL content/cards/ok.jsonl {a}\n读JSONL r = content/other/y.jsonl\n"})
    check(any("scripts/cards_run.zs: 第 2 行" in x and "不是本模块的内容文件目录" in x for x in pr) and any("scripts/cards_run.zs: 第 4 行" in x and "读别的模块" in x for x in pr)
          and not any("scripts/cards_run.zs: 第 3 行" in x for x in pr), "脚本里同样检查：写别的模块、读别的模块报，写本模块不报", pr)
    qr = proj("lw14")
    (qr / "routes" / "cards.zs").write_text('接口 POST /cards/x\n  设 w = 写JSONL content/other/b.jsonl {a}\n  返回 {"ok": 1}\n结束\n', encoding="utf-8")
    check(any("routes/cards.zs 接口 POST /cards/x" in x and "不是本模块的内容文件目录" in x for x in LC.check_project(qr, scripts=True)), "接口里写别的模块的 content/ 也报")
    q = proj("lw15")
    (q / "services" / "cards.zs").write_text((q / "services" / "cards.zs").read_text(encoding="utf-8").replace("content/cards/cards.jsonl {rows}", "content/other/cards.jsonl {rows}", 1), encoding="utf-8")
    kp = P.load_problems(q, "cards", ["cards"])
    check(any("写JSONL" in x for x in kp), "load_problems（核查阶段）带出本模块写路径的问题", kp)
    check(not any("写JSONL" in x for x in LC.check_project(q)), "生成阶段（scripts=False，默认）不查内容文件路径，不误拦")
    kg_like = TMP / "ct_legacy"
    shutil.rmtree(kg_like, ignore_errors=True)
    (kg_like / "routes").mkdir(parents=True)
    (kg_like / "routes" / "a.zs").write_text('接口 POST /a/x\n  用包 data\n  设 w = 写JSONL content/series.jsonl {k}\n  读JSONL r = content/words.jsonl\n  返回 {"ok": 1}\n结束\n', encoding="utf-8")
    check(LC.check_project(kg_like, scripts=True) == [], "不属于任何模块的老项目：不查内容文件路径")

    # ---- 移动文件 动词本身（verbs/data/_verbs.py:181）
    from tools import packs as PK
    mw = TMP / "mv_ws"
    shutil.rmtree(mw, ignore_errors=True)
    (mw / "content" / "m").mkdir(parents=True)
    (mw / "content" / "m" / "a.jsonl").write_text('{"k": 1}\n{"k": 2}\n', encoding="utf-8")

    def mv(*a):
        return PK.call_verb_text("移动文件", *a, packs=["data"], workspace=mw)
    check(mv("content/m/a.jsonl", "content/m/a.withdrawn.jsonl") == "是" and not (mw / "content/m/a.jsonl").exists()
          and (mw / "content/m/a.withdrawn.jsonl").read_text(encoding="utf-8") == '{"k": 1}\n{"k": 2}\n', "移动文件：成功返回是，源消失、目标内容一致")
    check(mv("content/m/none.jsonl", "content/m/x.jsonl") == "否" and not (mw / "content/m/x.jsonl").exists(), "移动文件：源不存在返回否（与 删文件 一致）")
    (mw / "content/m/b.jsonl").write_text("new\n", encoding="utf-8")
    check(mv("content/m/b.jsonl", "content/m/a.withdrawn.jsonl") == "是" and (mw / "content/m/a.withdrawn.jsonl").read_text(encoding="utf-8") == "new\n", "移动文件：目标已存在被覆盖")
    (mw / "content/m/c.jsonl").write_text("c\n", encoding="utf-8")
    check(mv("content/m/c.jsonl", "content/m/deep/er/c.jsonl") == "是" and (mw / "content/m/deep/er/c.jsonl").is_file(), "移动文件：目标父目录自动建")
    for src, dst, why in (("content/m/deep/er/c.jsonl", "../out.jsonl", "目标越界"), ("../x.jsonl", "content/m/x.jsonl", "源越界"),
                          ("content/m/deep", "content/m/deep2", "源是目录")):
        try:
            out = mv(src, dst)
        except ValueError as e:
            out = str(e)
        else:
            out = "未报错：" + out
        check(("越界" in out or "目录" in out) and not out.startswith("未报错"), f"移动文件：{why}报错", out)
    check((mw / "content/m/deep/er/c.jsonl").is_file() and (mw / "content/m/deep").is_dir() and not (mw.parent / "out.jsonl").exists(), "移动文件：报错时没动任何文件")

    # ---- 实跑（不调模型）：保存→写文件→按文件重灌库；读回核对；撤下挪文件；跑用例在临时 workspace 不污染项目
    before = sorted(str(f.relative_to(CT)) for f in CT.rglob("*"))
    r = CS.run(CT, "cards")
    after = sorted(str(f.relative_to(CT)) for f in CT.rglob("*"))
    check(r["全过"] and r["总数"] == 10, "fixture 10 条用例全过：保存 / 覆盖 / 读回 / 按文件重灌 / 撤下 / 撤下后重灌", r["原因"])
    check(before == after and not (CT / "content").exists(), "跑用例后项目里没有 content/（文件写在临时 workspace，不污染项目）")
    ws = TMP / "ct_ws"
    shutil.rmtree(ws, ignore_errors=True)
    shutil.copytree(CT, ws)
    sql = CS.build_sql(ws, ["cards"])
    u1 = next(u for u in c["用例"] if u["名"] == "保存卡片_写文件并重灌库")
    check(CS.run_case(ws, sql, "cards", u1) == "" and (ws / "content" / "cards" / "cards.jsonl").is_file(), "run_case 后文件在临时 workspace 里（用例之间靠 reset_content 清）")
    rows = [json.loads(l) for l in (ws / "content" / "cards" / "cards.jsonl").read_text(encoding="utf-8").splitlines()]
    check(rows == [{"card_no": "C1", "front": "猫", "back": "cat"}, {"card_no": "C2", "front": "狗", "back": "dog"}], "文件内容 = 保存的两张卡片（JSONL 一行一条）", rows)
    # 不写文件（保存函数只写库）→ 读回用例判失败；文件没写 / 没重灌都不会碰巧过
    brk = proj("ct_brk", svc=lambda s: s.replace("    设 w = 写JSONL content/cards/cards.jsonl {rows}\n", "", 1))
    r2 = CS.run(brk, "cards")
    check(not r2["全过"] and any(f["名"] == "读回卡片_文件内容" for f in r2["失败"]), "保存函数不写文件 → 读回用例失败（文件真的在被核对）", r2["原因"][:200])
    brk2 = proj("ct_brk2", svc=lambda s: s.replace("      设 m = 移动文件 content/cards/cards.jsonl content/cards/cards.withdrawn.jsonl\n", "", 1))
    r3 = CS.run(brk2, "cards")
    check(not r3["全过"] and any(f["名"] == "撤下全部_文件已挪走" for f in r3["失败"]), "撤下函数不删旧文件 → 「文件已挪走」用例失败", r3["原因"][:200])
    # 接口冒烟用的内容快照 / 还原
    snap = CS.snapshot_content(ws)
    (ws / "content" / "cards" / "cards.jsonl").write_text("x\n", encoding="utf-8")
    (ws / "content" / "cards" / "new.jsonl").write_text("y\n", encoding="utf-8")
    CS.restore_content(ws, snap)
    check(sorted(snap) == ["cards/cards.jsonl"] and not (ws / "content" / "cards" / "new.jsonl").exists() and len(rows) == 2
          and (ws / "content" / "cards" / "cards.jsonl").read_text(encoding="utf-8").count("\n") == 2, "snapshot_content / restore_content 还原到种子状态（接口冒烟直接调用后再走 HTTP 用）")
    u2 = next(u for u in c["用例"] if u["名"] == "读回卡片_没有文件_上个用例的文件不留")
    check(CS.run_case(ws, sql, "cards", u2) == "", "下一个用例开始前内容文件被清空（空库一样从空开始）")
    # 上游模块的 content 也一并清（用例的上游调用留下的文件不影响下一个用例）
    up = TMP / "ct_up"
    shutil.rmtree(up, ignore_errors=True)
    (up / "contracts").mkdir(parents=True)
    (up / "contracts" / "a.md").write_text("模块 a\n", encoding="utf-8")
    (up / "contracts" / "b.md").write_text("模块 b\n依赖 a\n", encoding="utf-8")
    for m in ("a", "b", "c"):
        (up / "content" / m).mkdir(parents=True)
        (up / "content" / m / "x.jsonl").write_text("1\n", encoding="utf-8")
    CS.reset_content(up, "b")
    check(not (up / "content" / "a").exists() and not (up / "content" / "b").exists() and (up / "content" / "c" / "x.jsonl").exists(), "reset_content 清本模块和上游，不碰无关模块")


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
    check("### auth 包" in s and "要先 用包 auth http" in s and "### doc 包" in s and "要先 用包 doc" in s and "读文档" in s,
          "动词表：auth / doc 包，注明要先 用包", s)
    check(V.plan_system(DP_PACK, "claude") == s, "v2.plan_system 用包的 PLAN_SYSTEM")
    # 示例 .zs 自己要过检查（白名单 + #改法 对着骨架 + 假模型空跑）
    ex = (ROOT / "tools" / "dslagent" / "packs" / "dslproj" / "prompts" / "example.zs").read_text(encoding="utf-8")
    p = skeleton("ex_skel")
    err, *_ = V.check(p, TMP / "ex_work", ex, "模块 graph", pack=DP_PACK)
    check(err == "", "示例 example.zs：白名单 / 改法 / 空跑都通过", err)
    # 计划检查：没有 跑用例
    bad = ex.replace("设 t = 跑用例 {m}", "设 t = 加载检查 {m}").replace("{t.all_passed}", "{t.ok}").replace("设 t2 = 跑用例 {m}", "设 t2 = 加载检查 {m}").replace("{t2.all_passed}", "{t2.ok}").replace("{t.failures}", "{t.problems}").replace("{t2.failures}", "{t2.problems}")
    err, *_ = V.check(p, TMP / "ex_work2", bad, "模块 graph", pack=DP_PACK)
    check("跑用例" in err, "计划检查（包专属）：计划里没有 跑用例 → 报", err)
    # 动词：引擎里直接跑
    eng = AgentEngine(client=None, workdir=SOL, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    eng.run("用包 common text code dslproj\n设 c = 加载检查 graph\n设 d = 比对约定 graph\n设 t = 跑用例 graph\n设 u = 跑用例 progress")
    v = eng.vars
    check(v["c"]["ok"] == "是" and v["d"]["consistent"] == "是" and v["t"]["all_passed"] == "是" and v["t"]["total"] == 7 and v["u"]["total"] == 5, "动词 加载检查 / 比对约定 / 跑用例", {k: v[k] for k in "cdtu"})
    p = copy_sol("vb_bad")
    (p / "services" / "graph.zs").write_text((p / "services" / "graph.zs").read_text(encoding="utf-8").replace("公开 函数 加边 src dst", "公开 函数 加边 dst src"), encoding="utf-8")
    eng = AgentEngine(client=None, workdir=p, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    eng.run("用包 common text code dslproj\n设 d = 比对约定 graph\n设 t = 跑用例 graph")
    check(eng.vars["d"]["consistent"] == "否" and "入参约定" in eng.vars["d"]["diffs"] and eng.vars["d"]["count"] >= 1, "动词 比对约定：不一致时给差异文本", eng.vars["d"])
    eng = AgentEngine(client=None, workdir=SOL, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    try:
        eng.run("用包 common text code dslproj\n设 t = 跑用例 nope")
        check(False, "动词：模块不存在报错")
    except Exception as e:  # noqa: BLE001
        check("没有约定文件" in str(e), "动词：模块不存在 → 报错带原因")
    eng = AgentEngine(client=None, workdir=SOL, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
    eng.dry_run = True
    eng.run("用包 common text code dslproj\n设 t = 跑用例 nope\n设 d = 比对约定 nope")
    check(eng.vars["t"]["all_passed"] == "是" and eng.vars["d"]["consistent"] == "是", "空跑（计划检查）时不碰项目，给占位结果")


# ------------------------------------------------------------------ 六、整条流程（假模型）


def t_flow():
    print("六、整条流程（假模型，pack=dslproj）")
    # 1 计划一次做对：成功、无补改、1 次调用
    p = skeleton("fl_ok")
    f = Fake(plan=plan_for("graph", p))
    r = V.run(p, "模块 graph", TMP / "out_fl_ok", model=f, pack="dslproj")
    check(r["status"] == "成功" and r["calls"] == 1 and [t for t, _, _ in f.log] == ["plan"], "一次做对：成功、只有 plan 一次调用", (r["stop"], [t for t, _, _ in f.log]))
    check(sorted(r["changed_files"]) == sorted(solution_files("graph")), "改动文件 = 范围内的文件", r["changed_files"])
    check(r["v2"]["验收"]["通过"] and "用例 7/7 通过" in r["v2"]["验收"]["测试摘要"] and "边界复核" in r["reply"]["result"], "验收：通过（加载检查 + 比对 + 用例）", r["v2"]["验收"])
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
    fixed = {"result": {"edits": [{"file": "services/graph.zs", "old": "    设 n = 写库 app.db graph_edge_insert",
                                "new": "    如果 {hit.yes} 等于 1\n      报错 409 会形成环\n    结束\n    设 n = 写库 app.db graph_edge_insert"}], "说明": "补上环检查"},
             "status": "成功", "reason": ""}
    plan3 = plan_for("graph", p3, buggy).replace("  终止 成功 三项检查都过\n结束\n", "  终止 成功 三项检查都过\n结束\n终止 成功 先这样交给验收\n", 1)
    plan3 = plan3.replace("终止 成功 做完了\n", "", 1)
    f = Fake(plan=plan3, fix=fixed)
    r = V.run(p3, "模块 graph", TMP / "out_fl_fix", model=f, pack="dslproj")
    check([t for t, _, _ in f.log] == ["plan", "fix"] and r["status"] == "成功" and r["v2"]["验收"]["补改"]["套用"] is True, "实现有 bug：验收不过 → 补改 1 次 → 补改后通过", (r["stop"], [t for t, _, _ in f.log]))
    fu = f.log[1][2]
    check("用例 加边_成环：应该报错 409" in fu and "【本模块约定（不能改）】" in fu and "services/graph.zs" in fu and "## DSL 项目写法速查" in fu
          and "contracts/graph.md" not in fu.split("【本模块现有文件")[1], "补改入参：失败用例原因 + 约定 + 本模块现有文件 + 写法速查", fu[:300])
    check("【本模块与全部上游的 entities 原文】" in fu and "entities/graph.entity" in fu and "实体 point" in fu
          and fu.find("【本模块与全部上游的 entities 原文】") < fu.find("【验收发现的问题】"), "补改入参：带本模块（与上游）的 entities 原文", fu[:300])
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
    # entities_text：本模块与全部上游（闭包），每个上限 8000 字；progress 依赖 graph，闭包是 graph + progress
    pe = copy_sol("fl_ents")
    et = DP_PACK.entities_text(pe, "progress")
    check("entities/graph.entity" in et and "实体 point" in et and "entities/progress.entity" in et and "实体 answer" in et,
          "entities_text：本模块与上游闭包", et[:300])
    long_entity = "实体 progress_answer x\n" + "  字段 note 文本 " + "很长的说明" * 2000 + "\n结束\n"
    (pe / "entities" / "progress.entity").write_text(long_entity, encoding="utf-8")
    et2 = DP_PACK.entities_text(pe, "progress")
    pblock = et2.split("### entities/progress.entity")[1]
    check("（文件过长，后面略）" in pblock and len(pblock) < 8200, "entities_text：每个文件上限 8000 字", len(pblock))
    # 读本模块文件上限 40000 字（之前是 12000）：规划 materials 和补改 fix_input 都用 current_files
    pf = skeleton("fl_bigfile")
    big = ("业务 graph\n  用包 db\n\n" + ("  # " + "占位" * 20 + "\n") * 700
           + "  # 标记_文件末尾\n  公开 函数 取知识点 code\n    报错 501 未实现\n  结束\n结束\n")
    check(12000 < len(big) < 40000, "测试用大文件长度在 12000 和 40000 之间", len(big))
    (pf / "services" / "graph.zs").write_text(big, encoding="utf-8")
    mt = DP_PACK.materials("模块 graph", pf, None)["text"]
    check("后面略" not in mt and "标记_文件末尾" in mt, "materials：本模块现有文件读到 40000 字，不再在 12000 处截断", len(mt))
    # 4 计划想改 contracts / 别的模块的文件：被拦（整体没写），失败、项目回滚
    p4 = skeleton("fl_oos", modules=("progress",))
    oos = {"contracts/progress.md": "模块 progress\n", "services/graph.zs": "业务 graph\n结束\n"}
    f = Fake(plan=plan_for("progress", p4, oos))
    before = {str(x.relative_to(p4)): x.read_text(encoding="utf-8") for x in p4.rglob("*") if x.is_file()}
    r = V.run(p4, "模块 progress", TMP / "out_fl_oos", model=f, pack="dslproj")
    after = {str(x.relative_to(p4)): x.read_text(encoding="utf-8") for x in p4.rglob("*") if x.is_file()}
    check(r["status"] == "失败" and "范围拦截" in r["stop"] and before == after, "改 contracts / 上游文件 → 被拦、失败、项目原样", r["stop"])
    # 5 写进范围内但内容不合约定（函数头改了）：比对约定不过 → 补改
    p5 = skeleton("fl_head")
    wrong = dict(files)
    wrong["services/graph.zs"] = files["services/graph.zs"].replace("公开 函数 加边 src dst", "公开 函数 加边 dst src")
    plan5 = plan_for("graph", p5, wrong).replace("  终止 成功 三项检查都过\n结束\n", "  终止 成功 先这样\n结束\n", 1)
    f = Fake(plan=plan5.replace("终止 成功 做完了\n", "终止 成功 到此\n"),
             fix={"result": {"edits": [{"file": "services/graph.zs", "old": "公开 函数 加边 dst src", "new": "公开 函数 加边 src dst"}], "说明": "函数头改回约定"}, "status": "成功", "reason": ""})
    r = V.run(p5, "模块 graph", TMP / "out_fl_head", model=f, pack="dslproj")
    check(r["status"] in ("成功", "失败") and "比对约定：函数「加边」入参约定是 src dst" in f.log[1][2], "函数头与约定不符：问题里带比对约定的差异", f.log[1][2][-900:] if len(f.log) > 1 else r["stop"])
    # 6 入口 run_task：失败 / 成功 + 模块名缺失
    p6 = skeleton("fl_entry")
    r = entry.run_task(p6, "模块 graph", "dslproj", model=Fake(plan=plan_for("graph", p6)), out=TMP / "out_fl_entry")
    check(r["status"] == "成功" and r["reason"] == "" and abs(r["花费"] - 0.01) < 1e-9, "run_task(pack=dslproj)：{status, reason, 花费}", r)
    r = entry.run_task(skeleton("fl_nomod"), "做点什么", "dslproj", model=Fake(plan="x"))
    check(r["status"] == "失败" and "模块" in r["reason"], "任务里没有模块行 → 失败并说明", r)
    check(SC.guard("services/progress.zs") == "", "流程结束后范围拦截关闭")


def t_mock_json():
    print("跑用例里的模型调用（问JSON 按格式示例回）")
    ws = TMP / "mockjson"
    (ws / "services").mkdir(parents=True)
    (ws / "services" / "m.zs").write_text(
        "业务 m\n  用包 common\n  公开 函数 问 q\n    问JSON r = 回答 {q} 格式 reply:文本 score:数字\n    返回 {\"reply\": \"{r.reply}\", \"score\": \"{r.score}\"}\n  结束\n结束\n",
        encoding="utf-8")
    eng = CS.make_engine(ws)
    res, err = CS.call(eng, "m", "问", {"q": "你好"})
    check(not err and isinstance(res, dict) and "reply" in res and "score" in res, "函数里的 问JSON 在用例的假模型下能拿到格式齐全的结构", (res, err))


def main():
    try:
        t_contract()
        t_project()
        t_compare()
        t_cases()
        t_mock_json()
        t_case_files()
        t_settle()
        t_scripts()
        t_content()
        t_accept_materials()
        t_flow()
    finally:
        SC.activate(None)
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
