# -*- coding: utf-8 -*-
"""tools/dslagent/infer.py：Datalog 求值器、事实抽取（自带小 fixture 项目）、打分排序确定性、
合并去重与 675 行上限、异常/超时回退、开关关闭时与原行为一致；
实验场景在本机时（/home/ysc/dslagent_exp、/home/ysc/dslagent_archive）对照 plan15 冻结版 dl.py 逐段一致，不在就跳过。不调模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_infer.py
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_infer_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["CBATCH_CLAUDE"] = "/bin/true"      # 执行器开头的预热换成马上退出的程序
sys.dont_write_bytecode = True

from tools.dslagent.legacy import infer as I         # noqa: E402
from tools.dslagent import runner as R        # noqa: E402
from tools.dslagent.legacy import template as T      # noqa: E402

EXP = Path("/home/ysc/dslagent_exp")
AR = Path("/home/ysc/dslagent_archive")
FROZEN = EXP / "plan15" / "frozen" / "dl.py"
FROZEN_SHA = "79be439b41cce5cab371962f7106b0038b83d790a2082836cb36b6a650b272e2"
PASS = FAIL = SKIP = 0
CLEAN = []


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{extra}" if extra else ""))


def skip(msg):
    global SKIP
    SKIP += 1
    print("  - 跳过：" + msg)


def project(name, files):
    d = TMP / name
    for rel, text in files.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return d


# 小 fixture：测试 → Cart.total（方法）→ fee → RATES 常量表；fee 里有舍入。根因是 RATES 里 east 的值。
FIX = {
    "pkg/__init__.py": "",
    "pkg/rates.py": "RATES = {\n    \"east\": 12,\n    \"west\": 15,\n}\nFREE_OVER = 99\n",
    "pkg/ship.py": ("from pkg.rates import RATES, FREE_OVER\n\n\n"
                    "def fee(region, kg):\n    base = RATES[region]\n    return base + round(kg * 0.5)\n\n\n"
                    "def label(region):\n    return region.upper()\n"),
    "pkg/cart.py": ("from pkg.ship import fee\n\n\nclass Cart:\n    def __init__(self, region):\n"
                    "        self.region = region\n        self.items = []\n\n"
                    "    def add(self, price, kg):\n        self.items.append((price, kg))\n\n"
                    "    def total(self):\n        s = sum(p for p, _ in self.items)\n"
                    "        return s + fee(self.region, sum(k for _, k in self.items))\n"),
    "tests/__init__.py": "",
    "tests/test_cart.py": ("import unittest\nfrom pkg.cart import Cart\n\n\nclass CartTest(unittest.TestCase):\n"
                           "    def test_total_east(self):\n        c = Cart(\"east\")\n        c.add(50, 4)\n"
                           "        self.assertEqual(c.total(), 66)\n"),
}
DESC = "华东运费少算了 2 元。失败的测试：tests.test_cart.CartTest.test_total_east"


def test_datalog():
    print("Datalog 求值器：递归闭包、多规则合并、内建过滤")
    rules = I.parse_rules("path(X,Y) :- e(X,Y).\npath(X,Z) :- path(X,Y), e(Y,Z).\n"
                          "near(X,Y) :- e(X,Y).\nnear(X,Y) :- e(Y,X).\nbig(X) :- n(X), lim(L), gt(X,L).\n")
    dl = I.Datalog(rules, {"gt": lambda a, b: int(a) > int(b)})
    for a, b in (("a", "b"), ("b", "c"), ("c", "d"), ("d", "b")):
        dl.add("e", a, b)
    for x in ("1", "3", "5"):
        dl.add("n", x)
    dl.add("lim", "2")
    out = dl.run()
    want = {(x, y) for x in "abcd" for y in "bcd"}
    check(out["path"] == want, "递归传递闭包（含环 b→c→d→b）", sorted(out["path"]))
    check(out["near"] == {("a", "b"), ("b", "a"), ("b", "c"), ("c", "b"), ("c", "d"), ("d", "c"), ("d", "b"), ("b", "d")},
          "同一个头的两条规则结果合并", sorted(out["near"]))
    check(out["big"] == {("3",), ("5",)}, "内建谓词在变量全绑定后过滤", out["big"])
    check(len(I.parse_rules(I.RULES)) == 31, "规则全部解析（31 条）")
    try:
        I.Datalog(rules, deadline=time.time() - 1).run()
        check(False, "过了 deadline → Timeout")
    except I.Timeout:
        check(True, "过了 deadline → Timeout")


def test_extract(fx, summary):
    print("事实抽取（fixture 项目）")
    ex = I.extract(fx)
    F = ex.F
    check(("pkg.ship.fee", "pkg/ship.py", "4", "6") in F["def"], "函数定义带行范围", sorted(F["def"])[:4])
    check(("pkg.cart.Cart.total", "pkg.ship.fee") in F["call"], "from-import 的函数调用解析成强边")
    check(("tests.test_cart.CartTest.test_total_east", "pkg.cart.Cart.add") in F["call_weak"],
          "对象方法调用按同名方法连弱边")
    check(("pkg.ship.fee", "pkg.rates.RATES") in F["uses_global"], "读模块常量 → uses_global")
    check(("pkg.rates.RATES", "east", "2") in F["data_lit"] and ("pkg.rates.RATES", "east", "12") in F["data_key"],
          "常量表里的字面量和键", [t for t in F["data_lit"] if t[0] == "pkg.rates.RATES"])
    check(("pkg.ship.fee", "round") in F["rounding"], "舍入调用 → rounding")
    check(("tests.test_cart.CartTest.test_total_east", "tests.test_cart") in F["test"], "测试函数")
    check(("tests.test_cart.CartTest.test_total_east", "66") in F["asserts"], "断言里的字面量")
    r = I.locate(fx, summary, DESC, k=8)
    qs = [x["q"] for x in r["segs"]]
    check(r["segs"] and all(x["file"] in FIX for x in r["segs"]) and not any(x["file"].startswith("tests/") for x in r["segs"]),
          "候选段都在源码里、不含测试文件", r["seg_str"])
    check("pkg.rates.RATES" in qs or any(x["file"] == "pkg/rates.py" for x in r["segs"]), "根因常量表进候选", r["seg_str"])
    check(all(x["a"] == 1 for x in r["segs"]), "≤60 行的小文件整份给", r["seg_str"])


def test_determinism(fx, summary):
    print("打分排序确定性：同进程重复一致；不同 PYTHONHASHSEED 的子进程候选段集合与分数序列一致")
    # 冻结版对同分的段不再排序（按集合迭代序），换 hash 种子时同分段的先后、理由里列的名字可能换——保持冻结版原样，
    # 这里只要求：段（文件、行区间、分数）的集合一样，按名次的分数序列一样
    a = I.locate(fx, summary, DESC, k=8)
    b = I.locate(fx, summary, DESC, k=8)
    check(a["segs"] == b["segs"], "同进程两次逐项一致")
    code = ("import sys, json; sys.path.insert(0, %r); from tools.dslagent.legacy import infer as I; "
            "print(json.dumps(I.locate(%r, sys.stdin.read(), %r, k=8)['segs'], ensure_ascii=False))") % (str(ROOT), str(fx), DESC)
    key = lambda segs: (sorted((x["file"], x["a"], x["b"], x["score"]) for x in segs), [x["score"] for x in segs])
    outs = []
    for seed in ("0", "1", "12345"):
        p = subprocess.run([sys.executable, "-B", "-c", code], input=summary, capture_output=True, text=True,
                           env=dict(os.environ, PYTHONHASHSEED=seed), timeout=60)
        outs.append(key(json.loads(p.stdout)))
    check(a["segs"] and all(o == key(a["segs"]) for o in outs), "三个 hash 种子：段集合、分数序列一致", outs[:1])


def test_merge(fx):
    print("合并：去重、整份文件写法、675 行上限")
    big = project("big", {"m/a.py": "x = 1\n" * 500, "m/b.py": "y = 2\n" * 400, "m/c.py": "z = 3\n" * 30})
    tpl = [("m/a.py", 1, 300)]
    m = I.merge(tpl, [("m/a.py", 10, 50), ("m/b.py", 1, 400), ("m/c.py", 1, 30), ("m/a.py", 280, 350)], 675)
    check(m == [("m/a.py", 1, 300), ("m/c.py", 1, 30), ("m/a.py", 280, 350)],
          "被模板段包住的跳过、加上超 675 的跳过、后面放得下的照加", m)
    check(I.nlines(m) <= 675, "总行数 ≤ 675", I.nlines(m))
    check(I.pre_str(m, big) == "m/a.py:1-300,m/c.py,m/a.py:280-350", "整份文件只写文件名", I.pre_str(m, big))
    check(I.parse_segs("m/c.py,m/a.py:3-9", big) == [("m/c.py", 1, 30), ("m/a.py", 3, 9)] and I.parse_segs("", big) == [],
          "pre 串解析（整份 / 区间 / 空）")
    p = {"kw": "x", "kw_why": [], "pre": "m/a.py:1-300", "pre_lines": 300}
    orig = I.rank
    I.rank = lambda *a, **k: {"segs": [{"q": f"m.{i}", "file": f, "a": a_, "b": b_, "score": 1.0, "why": []}
                                       for i, (f, a_, b_) in enumerate([("m/b.py", 1, 400), ("m/c.py", 1, 30)])],
                              "seg_str": ["m/b.py:1-400", "m/c.py:1-30"], "ms_infer": 0, "ms_rank": 0}
    try:
        q = I.augment(I.start(big), p, "d", "t", big)
    finally:
        I.rank = orig
    check(q["pre"] == "m/a.py:1-300,m/c.py" and q["pre_lines"] == 330 and q["infer"]["added"] == 1
          and q["infer"]["tpl_pre"] == "m/a.py:1-300" and not q["infer"]["fallback"], "augment：模板段在前、候选并入、记原预读",
          q.get("infer"))
    check(q["kw"] == "x" and p["pre"] == "m/a.py:1-300", "kw 不动、不改传入的 p")


def test_fallback(fx, summary):
    print("回退：异常 / 超时 / 文件太多 → 模板预读原样，原因有记录")
    p = T.extract(DESC, summary, fx)
    orig = I.rank

    def boom(*a, **k):
        raise ValueError("坏了")
    I.rank = boom
    try:
        q = I.augment(I.start(fx), p, DESC, summary, fx)
    finally:
        I.rank = orig
    check(q["pre"] == p["pre"] and q["pre_lines"] == p["pre_lines"] and "ValueError" in q["infer"]["fallback"],
          "推理抛异常 → 回退", q["infer"]["fallback"])

    def slow(*a, **k):
        time.sleep(1.0)
        return orig(*a, **k)
    I.rank = slow
    try:
        t0 = time.time()
        q = I.augment(I.start(fx, timeout=0.3), p, DESC, summary, fx)
        dt = time.time() - t0
    finally:
        I.rank = orig
    check(q["pre"] == p["pre"] and "Timeout" in q["infer"]["fallback"] and dt < 0.9, f"推理超时 → 回退（{dt:.2f}s）",
          q["infer"]["fallback"])
    origx = I.Extractor.run

    def xboom(self):
        raise OSError("读不了")
    I.Extractor.run = xboom
    try:
        q = I.augment(I.start(fx), p, DESC, summary, fx)
    finally:
        I.Extractor.run = origx
    check(q["pre"] == p["pre"] and "抽事实出错" in q["infer"]["fallback"], "抽事实出错 → 回退", q["infer"]["fallback"])
    q = I.augment(I.Job(fx).start(max_files=2), p, DESC, summary, fx)
    check(q["pre"] == p["pre"] and "超过 2" in q["infer"]["fallback"], "文件太多 → 回退", q["infer"]["fallback"])
    q = I.augment(I.start(fx), p, DESC, summary, fx)
    check(not q["infer"]["fallback"] and q["infer"]["cands"] and q["infer"]["ms_local"] >= 0
          and "ms_extract" in q["infer"], "正常时记候选段和耗时", q["infer"])


def test_switch(fx, summary):
    print("开关：DSLAGENT_INFER=0 / infer=False 时与原行为一致")
    old = os.environ.pop("DSLAGENT_INFER", None)
    try:
        check(I.enabled() and not I.enabled(False) and I.enabled(True), "默认开；参数优先")
        for v in ("0", "false", "off"):
            os.environ["DSLAGENT_INFER"] = v
            check(not I.enabled() and I.enabled(True), f"DSLAGENT_INFER={v} → 关（参数 True 仍可开）")
        os.environ["DSLAGENT_INFER"] = "1"
        check(I.enabled(), "DSLAGENT_INFER=1 → 开")
    finally:
        os.environ.pop("DSLAGENT_INFER", None)
        if old is not None:
            os.environ["DSLAGENT_INFER"] = old
    s0, p0 = T.build(DESC, summary, fx)
    s1, p1 = T.build(DESC, summary, fx, augment=None)
    check(s0 == s1 and p0 == p1 and "infer" not in p0, "build 不给 augment → 脚本和参数与原来逐字一致")
    s2, p2 = T.build(DESC, summary, fx, augment=lambda p: I.augment(I.start(fx), p, DESC, summary, fx))
    check(p2["kw"] == p0["kw"] and set(I.parse_segs(p0["pre"], fx)) <= set(I.parse_segs(p2["pre"], fx)) and "推理候选" in s2,
          "给了 augment → kw 不变、模板预读都还在、注释标出推理候选", p2["pre"])

    seen = []
    orig = T.build

    def spy(desc, test, repo, augment=None):
        seen.append(augment)
        out = orig(desc, test, repo, augment)
        seen.append(out[1])
        raise RuntimeError("测试：不往下跑")
    T.build = spy
    try:
        r_off = R.run(fx, DESC, TMP / "out_off", max_plan=0, infer=False)
        r_on = R.run(fx, DESC, TMP / "out_on", max_plan=0)
    finally:
        T.build = orig
    check(seen[0] is None and "infer" not in seen[1] and r_off["infer"] == {"on": False}, "runner infer=False → 不传 augment",
          r_off.get("infer"))
    check(seen[2] is not None and "infer" in seen[3] and r_on["infer"]["on"] and r_on["calls"] == 0,
          "runner 默认 → 传 augment、开局测试期间已起抽事实", seen[3].get("infer"))


def _load_frozen():
    spec = importlib.util.spec_from_file_location("_frozen_dl", FROZEN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def scenarios():
    """(名字, 项目目录, 测试摘要, 描述)。N：plan13 记下的开局摘要；B：场景副本上实跑 test_cmd。"""
    out = []
    tasks = {}
    for f in (AR / "route/tasks.json", AR / "plan7/tasks.json"):
        if f.is_file():
            tasks.update(json.loads(f.read_text()))
    for i in range(1, 11):
        s = f"N{i}"
        repo = AR / ("plan7" if i >= 7 else "route") / "scen" / s
        rj = EXP / "plan13" / "runs" / f"R_{s}_1" / "run.json"
        if repo.is_dir() and rj.is_file() and s in tasks:
            out.append((s, repo, json.loads(rj.read_text())["agent"]["initial"]["summary"], tasks[s]["desc"]))
    # 冻结版按绝对路径跳过隐藏目录：副本不能放在 ~/.cache 之类下面，放到实验目录的 tmp/ 里（用完删）
    scen_tmp = Path(tempfile.mkdtemp(prefix="infer_test_", dir=EXP / "plan15" / "tmp")) if (EXP / "plan15" / "tmp").is_dir() \
        else TMP / "scen"
    CLEAN.append(scen_tmp)
    for i in range(1, 9):
        s = f"B{i}"
        sd = EXP / "plan15" / "scen" / s
        if not (sd / "scenario.json").is_file():
            continue
        sc = json.loads((sd / "scenario.json").read_text())
        work = scen_tmp / s
        shutil.copytree(sd, work, ignore=shutil.ignore_patterns("__pycache__", "scenario.json", "ref_fix.patch"))
        out.append((s, work, R.test_state(work, sc["test_cmd"])["summary"], sc["task"]))
    return out


def test_frozen():
    print("与 plan15 冻结版 dl.py 对照（N1–N10、B1–B8；k=8/3 的候选段逐项一致）")
    if not FROZEN.is_file():
        skip(f"{FROZEN} 不在")
        return
    sha = hashlib.sha256(FROZEN.read_bytes()).hexdigest()
    check(sha == FROZEN_SHA, "冻结版 sha256 对得上", sha)
    dl = _load_frozen()
    check(dl.RULES == I.RULES and dl.W == I.W and dl.STOP == I.STOP, "规则文本、权重、停用词逐字一致")
    import inspect
    sig = inspect.signature(dl.locate).parameters
    check((sig["pad"].default, sig["max_seg"].default, sig["small_file"].default) == (I.PAD, I.MAX_SEG, I.SMALL_FILE),
          "段长参数 pad/max_seg/small_file 一致", (I.PAD, I.MAX_SEG, I.SMALL_FILE))
    sc = scenarios()
    if len(sc) < 18:
        skip(f"场景只找到 {len(sc)}/18 个")
    if not sc:
        return
    bad, empty, first = [], [], []
    for name, repo, test, desc in sc:
        for k in (8, 3):
            a, b = dl.locate(repo, test, desc, k=k), I.locate(repo, test, desc, k=k)
            if a["segs"] != b["segs"] or a["facts"] != b["facts"] or a["derived"] != b["derived"]:
                bad.append((name, k, a["seg_str"], b["seg_str"]))
            if k == 8:
                ref = a["segs"]
                empty += [] if ref else [name]
                first.append(f"{name}:{b['seg_str'][0] if b['seg_str'] else '无'}")
        # runner 走的路径：后台 Job 抽事实 + rank
        j = I.start(repo)
        j.done.wait(30)
        r = I.rank(j.ex, repo, test, desc, k=8)
        if r["segs"] != ref:
            bad.append((name, "job", r["seg_str"]))
    check(not empty, "每个场景冻结版都有候选（排除两边都空的假一致）", empty)
    check(not bad, f"{len(sc)} 个场景 × k=8/3 + 后台抽取路径：候选段（含分数/理由/合并名）、事实数、推导数全一致",
          bad[:3])
    print("    首段：" + " ".join(first[:4]) + " …")


def main():
    fx = project("fx", FIX)
    st = R.test_state(fx, f"{sys.executable} -m unittest discover -s tests")
    summary = st["summary"]
    print(f"fixture 开局：failing={st['failing']}")
    test_datalog()
    test_extract(fx, summary)
    test_determinism(fx, summary)
    test_merge(fx)
    test_fallback(fx, summary)
    test_switch(fx, summary)
    test_frozen()
    for d in [TMP] + CLEAN:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}，跳过 {SKIP}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
