# -*- coding: utf-8 -*-
"""资料包接口（tools/dslagent/packs/__init__.py）：声明校验、白名单由包生成、范围拦截（写类动词 + 补改套用）、验收接口（accept → Simple）、
code 包回归（假模型走一遍修 bug / 任务路径）、统一入口 run_task / --pack。不调真模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_packs.py
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_packs_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"
os.environ["DSLAGENT_DATASET"] = str(TMP / "dataset")
for k in ("DSLAGENT_PLANNER", "DSLAGENT_PACK", "DSLAGENT_VERIFY", "DSLAGENT_PLAN_MODE"):
    os.environ.pop(k, None)

from tools.dslagent import entry, packs, scope as SC, v2 as V       # noqa: E402
from tools.dslagent import plan as DP                               # noqa: E402
from tools.dslagent.engine import AgentEngine                       # noqa: E402
from tools.dslagent.verify import simple                            # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1200]}" if extra != "" else ""))


# ------------------------------------------------------------------ 一、包加载与声明校验


def t_load():
    print("一、包加载与声明校验")
    check(packs.available() == ["code", "dslproj", "newproj"], "登记了 code / dslproj / newproj", packs.available())
    check(packs.pick(None).NAME == "code" and packs.pick("dslproj").NAME == "dslproj", "缺省 code，按名取")
    try:
        packs.pick("nope")
        check(False, "不认识的名字报错")
    except ValueError as e:
        check("code" in str(e) and "dslproj" in str(e), "不认识的名字：报错并列出可用的", e)
    mod = packs.pick("code")
    check(packs.pick(mod) is mod, "传包对象原样返回")
    check(packs.validate(packs.pick("code")) == [] and packs.validate(packs.pick("dslproj")) == [], "code / dslproj 声明合格",
          (packs.validate(packs.pick("code")), packs.validate(packs.pick("dslproj"))))

    def fake(**kw):
        m = types.SimpleNamespace(NAME="x", VERBS=("读片段",), VERB_PACKS=("code",), WRITE_VERBS=(), PLAN_SYSTEM="s",
                                  accept=lambda p, c: {"通过": True, "问题": []})
        m.__dict__.update(kw)
        for k, v in list(m.__dict__.items()):
            if v is None:
                del m.__dict__[k]
        return m
    check(packs.validate(fake()) == [], "最小合格声明：NAME + VERBS + 验收 + 规划说明")
    check(any("VERBS" in p for p in packs.validate(fake(VERBS=None))), "缺 VERBS → 报")
    check(any("不存在" in p and "飞天" in p for p in packs.validate(fake(VERBS=("读片段", "飞天")))), "VERBS 里有不存在的动词 → 报")
    check(any("WRITE_VERBS" in p for p in packs.validate(fake(WRITE_VERBS=("写文件",)))), "WRITE_VERBS 不在 VERBS 里 → 报")
    check(any("GATED_VERBS" in p for p in packs.validate(fake(GATED_VERBS=("跑测试",)))), "GATED_VERBS 不在 VERBS 里 → 报")
    check(any("动词包" in p for p in packs.validate(fake(VERB_PACKS=("code", "没有这个包")))), "VERB_PACKS 里的动词包不存在 → 报")
    check(any("验收" in p for p in packs.validate(fake(accept=None))), "缺验收（accept / verifier）→ 报")
    check(any("规划说明" in p for p in packs.validate(fake(PLAN_SYSTEM=None))), "缺规划说明 → 报")
    check(any("NAME" in p for p in packs.validate(fake(NAME=""))), "缺 NAME → 报")
    check(any("必须是函数" in p for p in packs.validate(fake(scope_for="a/"))), "scope_for 不是函数 → 报")

    # v2.run 遇到不合格的包：直接判失败，不执行
    bad = fake(VERBS=("飞天",))
    p = TMP / "badpack"
    p.mkdir()
    r = V.run(p, "x", TMP / "out_badpack", model=lambda *a, **k: "", pack=bad)
    check(r["status"] == "失败" and "声明不合格" in r["stop"] and r["calls"] == 0, "v2.run：声明不合格 → 失败、0 次调用", r["stop"])


# ------------------------------------------------------------------ 二、白名单由包生成


def t_whitelist():
    print("二、语句 / 动词白名单由包生成")
    code, dp = packs.pick("code"), packs.pick("dslproj")
    check(packs.verbs_of(code) == DP.ALLOWED_VERBS, "code：白名单 = 旧 ALLOWED_VERBS（行为不变）")
    check(packs.verbs_of(dp) == DP.BASE_VERBS | set(dp.VERBS) and "跑用例" in packs.verbs_of(dp) and "跑测试" not in packs.verbs_of(dp)
          and "运行代码" not in packs.verbs_of(dp), "dslproj：BASE ∪ VERBS（有 跑用例，没有 跑测试 / 运行代码）")
    check(set(packs.use_of(code)) == {"common", "text", "code"} and "dslproj" in packs.use_of(dp), "用包 可写的包名由 VERB_PACKS 生成",
          (packs.use_of(code), packs.use_of(dp)))
    nw = packs.pick("newproj")
    check(packs.verbs_of(nw) == DP.ALLOWED_VERBS | set(nw.EXTRA_VERBS) and "newproj" in packs.use_of(nw), "旧包（只有 EXTRA_VERBS）：旧白名单 ∪ 额外")
    s = "用包 common text code dslproj\n预算 调用 2 秒 60\n设 t = 跑用例 graph\n终止 成功 好\n"
    check(DP.whitelist_check(s, {}, libs=(), only=(packs.verbs_of(dp), packs.use_of(dp))) == [], "dslproj 计划里用 跑用例 → 通过")
    probs = DP.whitelist_check(s, {}, libs=(), only=(packs.verbs_of(code), packs.use_of(code)))
    check(any("跑用例" in p for p in probs) and any("dslproj" in p for p in probs), "同一份计划按 code 包检查 → 动词 / 包名都被拒", probs)
    s2 = "用包 common text code\n预算 调用 2 秒 60\n设 t = 跑测试\n终止 成功 好\n"
    probs = DP.whitelist_check(s2, {}, libs=(), only=(packs.verbs_of(dp), packs.use_of(dp)))
    check(any("跑测试" in p and "白名单" in p for p in probs), "dslproj 计划里用 跑测试 → 被拒", probs)
    check(DP.whitelist_check(s2, {}) == [], "不传 only 的旧调用方式不变（旧路径）")
    # v2.check 用包生成的白名单
    proj = TMP / "wl"
    proj.mkdir()
    err, *_ = V.check(proj, TMP / "wl_work", s2, "t", pack=dp)
    check("跑测试" in err, "v2.check(pack=dslproj) 同样拒绝", err)


# ------------------------------------------------------------------ 三、范围拦截


def t_scope():
    print("三、范围拦截（写类动词 + 补改套用）")
    check(SC.parse("routes/graph*.zs, a/ ,b.py") == ["routes/graph*.zs", "a/", "b.py/"], "scope.parse：glob 原样、目录补 /", SC.parse("routes/graph*.zs, a/ ,b.py"))
    check(SC.inside("routes/graph.zs", ["routes/graph*.zs"]) and SC.inside("routes/graph_x.zs", ["routes/graph*.zs"])
          and not SC.inside("routes/progress.zs", ["routes/graph*.zs"]) and SC.inside("a/b/c.py", ["a/"]) and SC.inside("b.py", ["b.py/"])
          and not SC.inside("ab/c.py", ["a/"]), "scope.inside：glob / 目录 / 精确文件")
    check(SC.guard("x/y.py") == "", "没启用范围 → 不拦")
    proj = TMP / "sc"
    shutil.rmtree(proj, ignore_errors=True)
    (proj / "services").mkdir(parents=True)
    (proj / "routes").mkdir()
    (proj / "services" / "graph.zs").write_text("业务 graph\n结束\n", encoding="utf-8")
    (proj / "services" / "progress.zs").write_text("业务 progress\n结束\n", encoding="utf-8")
    SC.activate(["services/graph.zs", "routes/graph*.zs"])
    try:
        eng = AgentEngine(client=None, workdir=proj, verbose=False, verbs_root=ROOT / "tools" / "dslagent" / "verbs")
        eng.vars["w1"] = {"file": "services/progress.zs", "content": "x\n"}
        eng.vars["w2"] = {"file": "routes/graph_api.zs", "content": "接口 GET /g\n结束\n"}
        eng.vars["e1"] = {"file": "services/progress.zs", "old": "业务 progress", "new": "业务 progress2"}
        eng.run("用包 common text code\n设 a = 写文件 {w1}\n设 b = 写文件 {w2}\n设 c = 改文件 {e1}\n设 d = 删文件 services/progress.zs")
        a, b, c, d = (eng.vars[k] for k in "abcd")
        check(a["ok"] == "否" and "范围拦截" in a["msg"], "写范围外文件 → 被拒（写文件）", a)
        check(b["ok"] == "是" and (proj / "routes" / "graph_api.zs").is_file(), "写范围内（glob 命中）→ 通过", b)
        check(c["ok"] == "否" and "范围拦截" in c["msg"] and "业务 progress2" not in (proj / "services" / "progress.zs").read_text(encoding="utf-8"),
              "改范围外文件 → 被拒、文件没动（改文件）", c)
        check(d["ok"] == "否" and "范围拦截" in d["msg"] and (proj / "services" / "progress.zs").is_file(), "删范围外文件 → 被拒、文件还在（删文件）", d)
        from tools.dslagent.verify import code as VC
        ok, msg = VC.apply_edits(proj, [{"file": "services/progress.zs", "old": "业务 progress", "new": "x"}])
        check(not ok and "范围拦截" in msg, "补改套用（apply_edits）同样按范围拦", msg)
        ok, msg = VC.apply_edits(proj, [{"file": "services/graph.zs", "old": "业务 graph", "new": "业务 graph  # 补改"}])
        check(ok, "补改套用范围内 → 通过", msg)
        check(os.environ.get(SC.ENV), "范围同时写进环境变量（给 dslmcp 子进程）")
    finally:
        SC.activate(None)
    check(SC.ENV not in os.environ and SC.guard("services/progress.zs") == "", "activate(None) 关闭并清环境变量")
    # 环境变量路径（子进程里没有 activate）
    os.environ[SC.ENV] = json.dumps(["a/"])
    try:
        check("范围拦截" in SC.guard("b/x.py") and SC.guard("a/x.py") == "", "子进程只有环境变量时也按范围拦")
    finally:
        os.environ.pop(SC.ENV)
    # STRICT_SCOPE 没声明的包（code）：--scope 仍是事后闸（老行为）：写了范围外的文件能写成，执行后恢复
    check(not getattr(packs.pick("code"), "STRICT_SCOPE", False) and packs.pick("dslproj").STRICT_SCOPE, "STRICT_SCOPE：code 不拦写（事后闸），dslproj 拦写")
    check(packs.scope_of(packs.pick("code"), "t", ".", None) == [] and packs.scope_of(packs.pick("code"), "t", ".", "kg/") == ["kg/"],
          "scope_of：code 无默认范围，命令行优先")
    check(SC.inside("entities/graph.entity", packs.scope_of(packs.pick("dslproj"), "模块 graph", ".", None))
          and not SC.inside("entities/progress.entity", packs.scope_of(packs.pick("dslproj"), "模块 graph", ".", None))
          and packs.scope_of(packs.pick("dslproj"), "模块 graph", ".", "services/") == ["services/"], "scope_of：dslproj 按模块名生成，命令行优先")


# ------------------------------------------------------------------ 四、验收接口（accept → Simple）


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


def t_accept():
    print("四、验收接口：accept(project, ctx) → {通过, 问题}，补改循环")
    calls = []

    def accept(project, ctx):
        calls.append(ctx["stage"])
        t = (Path(project) / "out.txt").read_text(encoding="utf-8") if (Path(project) / "out.txt").is_file() else ""
        probs = [] if "ok" in t else ["out.txt 里要有 ok"]
        return {"通过": not probs, "问题": probs, "摘要": "摘要:" + t.strip()}
    pk = types.SimpleNamespace(NAME="tiny", VERBS=("读片段", "写文件", "改文件"), VERB_PACKS=("code",), WRITE_VERBS=("写文件", "改文件"),
                               PLAN_SYSTEM="你是规划者。输出 .zs。", accept=accept,
                               scope_for=lambda task, project, given: ["out.txt"], STRICT_SCOPE=True,
                               materials=lambda task, project, scope: {"text": "## 资料\n范围 " + ",".join(scope), "记录": {"自定义": 1}},
                               files=lambda project: ((f.name, f) for f in Path(project).glob("*.txt")))
    check(packs.validate(pk) == [], "自定义包声明合格", packs.validate(pk))
    ver = packs.verifier_of(pk)
    check(isinstance(ver, simple.Simple), "只写 accept → verify/simple.py 包成完整验收")
    plan = ("用包 common text code\n预算 调用 2 秒 60\n设 w = 写文件 {e}\n终止 成功 写了\n")
    plan_bad = plan.replace("设 w = 写文件 {e}", '设 e = {"file": "out.txt", "content": "nope"}\n设 w = 写文件 {e}')
    plan_ok = plan.replace("设 w = 写文件 {e}", '设 e = {"file": "out.txt", "content": "ok"}\n设 w = 写文件 {e}')
    fix = {"结果": {"edits": [{"file": "out.txt", "old": "nope", "new": "ok"}], "说明": "改成 ok"}, "状态": "成功", "原因": ""}
    # 1 一次通过
    p = TMP / "ac1"
    p.mkdir()
    f = Fake(plan=plan_ok)
    r = V.run(p, "任务", TMP / "out_ac1", model=f, pack=pk)
    check(r["status"] == "成功" and r["calls"] == 1 and (p / "out.txt").read_text(encoding="utf-8") == "ok", "验收通过 → 成功、不补改", (r["stop"], f.log[:1]))
    check("## 资料\n范围 out.txt/" in f.log[0][2] and r["v2"]["自定义"] == 1 and r["v2"]["pack"] == "tiny", "资料进规划 user、记录并进 v2.*")
    check(f.log[0][1] == "你是规划者。输出 .zs。", "规划 system = 包的 PLAN_SYSTEM")
    # 2 没过 → 补改 → 再验
    calls.clear()
    p = TMP / "ac2"
    p.mkdir()
    f = Fake(plan=plan_bad, fix=fix)
    r = V.run(p, "任务", TMP / "out_ac2", model=f, pack=pk)
    check(r["status"] == "成功" and [t for t, _, _ in f.log] == ["plan", "fix"] and calls == ["验收", "补改后"], "验收没过 → 派 1 次补改 → 补改后再验 → 成功",
          (r["stop"], [t for t, _, _ in f.log], calls))
    fu = f.log[1][2]
    check("out.txt 里要有 ok" in fu and "【任务原文】" in fu and "nope" in fu, "补改入参：任务 + 问题 + 范围内现有文件", fu[:400])
    check(r["v2"]["验收"]["补改"]["套用"] is True and len(r["v2"]["验收"]["验收记录"]) == 2, "记录：补改套用、两次验收记录")
    # 3 补改后仍不过 → 失败
    p = TMP / "ac3"
    p.mkdir()
    f = Fake(plan=plan_bad, fix={"结果": {"edits": [], "说明": "不会"}, "状态": "失败", "原因": "不会改"})
    r = V.run(p, "任务", TMP / "out_ac3", model=f, pack=pk)
    check(r["status"] == "失败" and "out.txt 里要有 ok" in r["stop"], "补改后仍不过 → 失败并给出验收问题", r["stop"])
    # 4 计划写范围外的文件：被拦（STRICT_SCOPE），计划自己看到原因
    p = TMP / "ac4"
    p.mkdir()
    out_scope = plan_ok.replace('"file": "out.txt"', '"file": "other.txt"')
    plan_oos = out_scope.replace("终止 成功 写了", "如果 {w.ok} 不等于 是\n  终止 失败 {w.msg}\n结束\n终止 成功 写了")
    f = Fake(plan=plan_oos)
    r = V.run(p, "任务", TMP / "out_ac4", model=f, pack=pk)
    check(r["status"] == "失败" and "范围拦截" in r["stop"] and not (p / "other.txt").exists(), "计划写范围外 → 被拦、没写出文件", r["stop"])
    # 5 命令行 / 参数的 scope 优先于包的 scope_for
    p = TMP / "ac5"
    p.mkdir()
    f = Fake(plan=plan_ok.replace("终止 成功 写了", "如果 {w.ok} 不等于 是\n  终止 失败 {w.msg}\n结束\n终止 成功 写了"))
    r = V.run(p, "任务", TMP / "out_ac5", model=f, pack=pk, scope="other/")
    check(r["status"] == "失败" and "范围拦截" in r["stop"], "run(scope=…) 优先于包的 scope_for", r["stop"])
    check(SC.guard("anything") == "" and SC.ENV not in os.environ, "run 结束后范围拦截已关闭")


# ------------------------------------------------------------------ 五、code 包回归（假模型）

UTIL = "def double(x):\n    return x * 2\n"
BUG_TESTS = ("import unittest\n\nfrom pkg.util import double\n\n\nclass T(unittest.TestCase):\n    def test_double(self):\n"
             "        self.assertEqual(double(2), 4)\n\n    def test_triple(self):\n        from pkg.util import triple\n        self.assertEqual(triple(2), 6)\n")
PLAN_BUG = """用包 common text code
预算 调用 4 秒 300
设 res = 改文件 {e1}
如果 {res.ok} 不等于 是
  终止 失败 没套上：{res.msg}
结束
设 t = 跑测试
如果 {t.passed} 不等于 是
  终止 失败 测试没过：{t.summary}
结束
终止 成功 补上 triple

#改法 e1
@@ 改 pkg/util.py
<<<<<<< 原文
def double(x):
    return x * 2
=======
def double(x):
    return x * 2


def triple(x):
    return x * 3
>>>>>>> 新文
#清单
改 pkg/util.py:double
"""
PLAN_NEW = """用包 common text code
预算 调用 4 秒 300
设 e = {"file": "pkg/extra.py", "content": "def hello():\\n    return 'hi'\\n"}
设 f = 写文件 {e}
设 r = 读片段 pkg/util.py:1-2
终止 成功 新建 pkg/extra.py

#清单
新建 pkg/extra.py
"""
BOUND = "import unittest\n\nfrom pkg.util import double\n\n\nclass B(unittest.TestCase):\n    def test_zero(self):\n        \"\"\"0 的两倍还是 0\"\"\"\n        self.assertEqual(double(0), 0)\n"


def code_proj(name, tests):
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    (p / "pkg").mkdir(parents=True)
    (p / "tests").mkdir()
    (p / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (p / "pkg" / "util.py").write_text(UTIL, encoding="utf-8")
    (p / "tests" / "test_util.py").write_text(tests, encoding="utf-8")
    return p


def t_code_regression():
    print("五、code 包回归（假模型：修 bug 路径 + 任务路径；与改前产物一致的对比见报告里的 regress.py）")
    cmd = "python3 -m unittest discover -s tests"
    for name, tests, plan, task, changed in (("bug", BUG_TESTS, PLAN_BUG, "test_triple 失败：pkg/util.py 里补上 triple", ["pkg/util.py"]),
                                             ("new", BUG_TESTS.split("\n    def test_triple")[0] + "\n", PLAN_NEW, "新建 pkg/extra.py 写 hello", ["pkg/extra.py"])):
        p = code_proj("cr_" + name, tests)
        f = Fake(plan=plan, bound=BOUND)
        out = TMP / f"out_cr_{name}"
        r = V.run(p, task, out, test_cmd=cmd, model=f)
        v = r["v2"]
        check(r["status"] == "成功" and r["fixed"] and r["changed_files"] == changed, f"[{name}] 成功、改动 {changed}", (r["stop"], r["changed_files"]))
        check([t for t, _, _ in f.log] == ["plan", "bound"] and r["calls"] == 2, f"[{name}] 调用：plan + bound（边界复核旧路径）", [t for t, _, _ in f.log])
        check(list(v["步骤秒"]) == ["1大纲", "3规划", "4执行", "5验收", "6边界复核"], f"[{name}] 步骤同改前", list(v["步骤秒"]))
        check(r["test_cmd"] == cmd and v["验收"]["测试"][0]["方式"] == "真跑" and v["测试闸门"] is not None, f"[{name}] 验收跑全量测试、闸门同改前")
        check("pkg/util.py" in (out / "outline.md").read_text(encoding="utf-8") and "## 文件大纲" in f.log[0][2], f"[{name}] 资料 = 文件大纲，进规划 user")
        check(f.log[0][1] == V.plan_system(packs.pick("code")) and "跑测试" in f.log[0][1], f"[{name}] 规划 system = agents/plan.md（code 的）")
    # 显式 pack="code" / 包名字符串与缺省完全一致
    p1, p2 = code_proj("cr_a", BUG_TESTS), code_proj("cr_b", BUG_TESTS)
    f1, f2 = Fake(plan=PLAN_BUG, bound=BOUND), Fake(plan=PLAN_BUG, bound=BOUND)
    r1 = V.run(p1, "补上 triple", TMP / "out_cr_a", test_cmd=cmd, model=f1)
    r2 = V.run(p2, "补上 triple", TMP / "out_cr_b", test_cmd=cmd, model=f2, pack="code")
    check([(t, s, u) for t, s, u in f1.log] == [(t, s, u) for t, s, u in f2.log] and r1["status"] == r2["status"], "pack='code' 与缺省：调用 / 提示词逐字一致")
    # 没有测试命令：沿用原来的失败原因
    p = TMP / "cr_nocmd"
    p.mkdir()
    r = V.run(p, "t", TMP / "out_cr_nocmd", model=Fake())
    check(r["status"] == "失败" and "探测不到测试" in r["stop"] and r["calls"] == 0, "项目里探测不到测试 → 原失败原因", r["stop"])
    # code 包的 GATED_VERBS 驱动 test_gate
    g = V.test_gate("设 t = 跑测试\n如果 {t.passed} 不等于 是\n  终止 失败 x\n结束\n终止 成功 好")
    check(g == {0: False} and V.test_gate("设 t = 跑用例 m\n设 u = {t.全过}\n终止 成功 好", ("跑用例",)) == {0: True}
          and V.test_gate("设 t = 跑测试\n设 u = {t.passed}\n终止 成功 好", ("跑用例",)) == {}, "test_gate：闸门动词由包的 GATED_VERBS 给")


# ------------------------------------------------------------------ 六、统一入口


def t_entry():
    print("六、统一入口 run_task / --pack")
    cmd = "python3 -m unittest discover -s tests"
    p = code_proj("en_code", BUG_TESTS)
    f = Fake(plan=PLAN_BUG, bound=BOUND)
    r = entry.run_task(p, "补上 triple", "code", model=f, test_cmd=cmd, out=TMP / "out_en_code")
    check(set(r) >= {"状态", "原因", "花费"} and r["状态"] == "成功" and abs(r["花费"] - 0.02) < 1e-9 and r["原因"] == "", "run_task：{状态, 原因, 花费}", r)
    p = code_proj("en_fail", BUG_TESTS)
    r = entry.run_task(p, "补上 triple", "code", model=Fake(plan="用包 common text code\n预算 调用 2 秒 60\n终止 失败 做不到\n\n#清单\n改 pkg/util.py:double\n"), test_cmd=cmd)
    check(r["状态"] == "失败" and "做不到" in r["原因"] and Path(r["记录目录"]).is_dir(), "run_task：失败带原因；out 缺省建临时记录目录", r)
    try:
        entry.run_task(p, "x", "没有这个包")
        check(False, "run_task 包名不对报错")
    except ValueError as e:
        check("没有这个包" in str(e), "run_task：包名不对 → ValueError")
    # 命令行
    from tools.dslagent import __main__ as M
    seen = {}
    orig = entry.run_pack
    entry.run_pack = lambda project, task, pack, out, **kw: seen.update(project=project, pack=pack, kw=kw) or {"kind": "task", "fixed": True, "cost": 0}
    try:
        tf = TMP / "task.txt"
        tf.write_text("模块 graph", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            M.main(["run", "--pack", "dslproj", "--project", "/p", "--task-file", str(tf), "--out", "/o", "--scope", "services/graph.zs"])
    finally:
        entry.run_pack = orig
    check(seen.get("pack") == "dslproj" and seen["kw"]["scope"] == "services/graph.zs", "命令行 --pack / --scope 传到 run_pack", seen)


def main():
    try:
        t_load()
        t_whitelist()
        t_scope()
        t_accept()
        t_code_regression()
        t_entry()
    finally:
        SC.activate(None)
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
