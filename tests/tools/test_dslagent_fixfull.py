# -*- coding: utf-8 -*-
"""补改入参要看得到报错涉及的原文：读片段「文件:全文」、派任务整份分段不丢后半段、fix_input 全文 / 报错行前后各 30 行。不调模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_fixfull.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "dslagent" / "verbs" / "code" / "defs"))
sys.path.insert(0, str(ROOT / "tools" / "dslagent" / "verbs" / "common"))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_fixfull_"))

from tools import dsl_task as DT                                       # noqa: E402
from tools.dslagent.packs import dslproj as DPJ                        # noqa: E402
from tools.dslagent.verbs.code.defs import _read as RD                 # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  ✓ " if cond else "  ✗ ") + msg + ("" if cond or extra == "" else f"\n      {str(extra)[:900]}"))


def big_project(name, n=700):
    p = TMP / name
    shutil.copytree(ROOT / "tests" / "tools" / "fixtures" / "dslproj_solution", p)
    f = p / "services" / "progress.zs"
    head = f.read_text(encoding="utf-8").splitlines()
    pad = [f"    # 占位第 {i} 行" for i in range(len(head), n)]
    f.write_text("\n".join(head + pad) + "\n", encoding="utf-8")
    return p, f


def t_read():
    print("一、读片段 文件:全文")
    from _sandbox import resolve
    p, f = big_project("rd", 735)
    n = len(f.read_text(encoding="utf-8").splitlines())
    snip, err = RD.one(p, "services/progress.zs", resolve)
    check(not err and snip["b"] == RD.BIG_HEAD and snip["big"], "不加「:全文」：超过 500 行只给前 120 行（原行为不变）", (err, snip and snip["b"]))
    snip, err = RD.one(p, "services/progress.zs:全文", resolve)
    check(not err and snip["b"] == n and snip["full"] and not snip["trunc"], "加「:全文」：全部行", (err, snip and (snip["b"], n)))
    check("占位第 %d 行" % (n - 1) in snip["body"] and "300| " in snip["body"], "第 300 行和最后一行都在")
    got = RD.split_segs("services/progress*.zs:全文,queries/progress_*.sql:全文", p)
    check(got and all(g.endswith(":全文") for g in got) and "services/progress.zs:全文" in got, "通配 + :全文 展开成逐个文件", got)
    big = p / "services" / "huge.zs"
    big.write_text("\n".join("x" * 100 for _ in range(1200)) + "\n", encoding="utf-8")
    snip, err = RD.one(p, "services/huge.zs:全文", resolve)
    check(snip["b"] < 1200 and "第 %d 行后省略" % snip["b"] in snip["trunc"], "超过字数上限的文件末尾说明读到哪、怎么接着读", snip["trunc"])


def t_task():
    print("二、派任务 整份文件分段全部给出")
    w = TMP / "wk"
    w.mkdir()
    (w / "a.zs").write_text("\n".join(f"line{i}" for i in range(1, 1001)) + "\n", encoding="utf-8")
    out = DT.collect_inputs(["a.zs"], w)
    txt = out[0][1]
    check("line1000" in txt and "line300" in txt and "第 1-400 行" in txt and "第 801-1000 行" in txt, "整份 1000 行：按 400 行一段全部给出", txt[-200:])
    out = DT.collect_inputs(["a.zs:1-900"], w)[0][1]
    check("line400" in out and "line401" not in out and "只给到第 400 行" in out and "a.zs:401-900" in out, "写了超长区间：截到 400 行并说明怎么接着读", out[-200:])
    out = DT.collect_inputs(["a.zs:300"], w)[0][1]
    check("line300" in out, "单行引用")


def t_fix_input():
    print("三、fix_input 补改入参")
    p, f = big_project("fx", 700)
    lines = f.read_text(encoding="utf-8").splitlines()
    lines[299] = "    设 报错行 = 转大写 a b"
    lines[649] = "    设 后半段错 = 转大写 c d"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    probs = ["加载检查：services/progress.zs 第 300 行 转大写 给了 2 个参数", "加载检查：services/progress.zs 第 650 行 转大写 给了 2 个参数"]
    inp = DPJ.fix_input(p, {"task": "做模块\n模块 progress"}, probs)
    check(" 300|     设 报错行 = 转大写 a b" in inp, "报错行在第 300 行：补改入参里能看到第 300 行原文")
    check(" 650|     设 后半段错 = 转大写 c d" in inp and "占位第 699 行" in inp, "超长文件后半段不丢（第 650 行、最后一行都在）")
    check("全文" in inp and "文件太长" not in inp, "总量在预算内 → 全文")
    txt = DPJ.fix_files_text(p, "progress", probs, total=3000)
    check(" 300|     设 报错行 = 转大写 a b" in txt and " 650|     设 后半段错" in txt, "超预算：两处报错行都在")
    check(" 270| " in txt and " 330| " in txt and " 269| " not in txt and " 331| " not in txt, "超预算：第 300 行前后各 30 行（270-330）")
    check(" 100| " not in txt and "略第" in txt and "文件太长" in txt, "超预算：其余行省略并写明")
    txt = DPJ.fix_files_text(p, "progress", ["比对约定：x"], total=3000)
    check("开头（问题里没有行号）" in txt, "超预算又没有行号：给开头并说明")
    other = DPJ.fix_files_text(p, "progress", ["加载检查：routes/progress.zs 第 3 行 x"], total=3000)
    check(" 300| " not in other, "问题点名别的文件时，行号不算到这个文件上")


def main():
    try:
        t_read()
        t_task()
        t_fix_input()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
