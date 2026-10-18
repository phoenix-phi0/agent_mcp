# -*- coding: utf-8 -*-
"""dslagent v2 拆分（规划核心 / 资料包 packs/ / 验收 verify/）的回归：不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_split.py            # 跑测试
    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_split.py --record   # 重录基线（只在有意改提示时）

  一、提示逐字一致：同一假模型输入，各场景里发给模型的每次 system / user 文本，逐字等于拆分前录下的基线
     （fixtures/dslagent_v2_prompts.json；基线是拆分前的 v2.py + v2pack.py 录的）。full 规划方式删除后，基线里只有 full 才有的条目
     （preq、规划 plan / plan_fix 的 system / user、PRE_SYS、plan_system）和 query 场景已从基线里删掉，其余条目（子任务 / 补改 / 边界）没重录；
     比对时也跳过这些 tag
  二、DSLAGENT_PACK / DSLAGENT_VERIFY 取值校验：缺省 code；verify 缺省跟随 pack；别的取值报错并列出可用的
  三、旧 import 路径兼容：from tools.dslagent import v2pack、v2.<搬走的名字>
  四、cbatch：dsl_options.pack 透传成 DSLAGENT_PACK，写错在提交时就报错（行为测试在 test_cbatch.py）
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_dslagent_v2 as T                  # noqa: E402  复用它的假项目 / 假模型 / 计划

GOLDEN = HERE / "fixtures" / "dslagent_v2_prompts.json"
V = T.V
PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


OLD_RX = "预算 调用 4 秒 300\n# 旧写法: return x \\* 2$\n"
SUB_PLAN = T.plan('''
设 r = 派任务 改double {task} 改好 edits:列表
设 res = 改文件 {r.结果}
终止 成功 好
''')
BAD = "用包 common text code\n预算 调用 2 秒 60\n设 x = 转大写 ls\n终止 成功 好\n\n#清单\n改 pkg/util.py:double\n"
FIXREP = {"结果": {"edits": [{"file": "pkg/other.py", "old": "    return x * 2", "new": "    return x + x"}],
                   "说明": "twice 也改"}, "状态": "成功", "原因": ""}


def scenarios():
    """场景名 → Fake 的参数。覆盖：补查、重写、子任务、残留补改、清单缺口、边界补改、用例自身错误。"""
    harness = T.BOUND_OK.replace("class B(unittest.TestCase):\n", "class B(unittest.TestCase):\n    f = double\n\n") \
        .replace("double(0)", "self.f(0)")
    body = T.PLAN_OK.split("预算 调用 4 秒 300\n", 1)[1].split("\n\n#改法")[0]
    return {
        "ok": {},
        "rewrite": {"plan": BAD, "plan_fix": T.PLAN_OK},
        "resid_fix": {"plan": T.PLAN_OK.replace("预算 调用 4 秒 300\n", OLD_RX), "fix": FIXREP},
        "checklist": {"plan": T.plan(body, checklist="改 pkg/util.py:double\n改 pkg/other.py:twice"),
                      "fix": {"结果": {"edits": []}, "状态": "失败", "原因": "不会"}},
        "bound_fix": {"bound": T.BOUND_RAISE, "bfix": T.FIX_CLAMP},
        "bound_case": {"bound": harness, "bfix": {"结果": {"edits": [], "用例代码": "```python\n" + T.BOUND_OK + "```",
                                                           "说明": "用例把函数存成类属性"}, "状态": "成功", "原因": ""}},
        "subtask": {"plan": SUB_PLAN, "dsl": {"结果": {"edits": [{"file": "pkg/util.py", "old": "    return x * 2\n", "new": "    return x + x\n"}]},
                                              "状态": "成功", "原因": ""}},
    }


FULL_ONLY = {"preq", "plan", "plan_fix"}      # 基线里只有 full 规划方式才有的调用（已删）


def record_all():
    """跑全部场景，返回 {场景: [{tag, system, user}], ...}（逐次调用，按调用顺序）。"""
    out = {}
    for name, kw in scenarios().items():
        f = T.Fake(**kw)
        T.go("g_" + name, f)
        out[name] = [{"tag": t, "system": s, "user": u} for t, s, u in f.log if t not in FULL_ONLY]
    out["_static"] = [{"tag": n, "system": getattr(V, n, None) or "", "user": ""} for n in ("FIX_SYS", "BOUND_SYS", "BFIX_SYS", "SUB_SYS")]
    return out


def sha(s):
    """哈希前把每次运行都不同的东西抹平：单测耗时（Ran 2 tests in 0.001s）、随机临时目录名（dslagent_v2_xxxx）、
    临时目录前缀（tempfile.gettempdir()，随 TMPDIR 变，traceback 路径长度跟着变）。"""
    s = re.sub(r"in \d+\.\d+s", "in Ns", s)
    s = s.replace(tempfile.gettempdir(), "TMPROOT")
    return hashlib.sha256(re.sub(r"dslagent_v2_\w+", "dslagent_v2_TMP", s).encode("utf-8")).hexdigest()


def compact(rec):
    """基线只存哈希 + 长度；文本太长，且哈希已经能证明逐字一致。失败时靠长度和首个不同位置定位。"""
    return {n: [{"tag": c["tag"], "sys": sha(c["system"]), "user": sha(c["user"]), "sys_len": len(c["system"]),
                 "user_len": len(c["user"])} for c in calls] for n, calls in rec.items()}


def t_prompts():
    print("一、提示逐字一致（拆分前后）")
    cur = compact(record_all())
    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))
    check(set(cur) == set(gold), "场景集合一致", (sorted(cur), sorted(gold)))
    total = 0
    for name in gold:
        g, c = gold[name], cur.get(name, [])
        total += len(g)
        check([x["tag"] for x in g] == [x["tag"] for x in c], f"{name}：调用顺序（tag）一致", ([x["tag"] for x in c]))
        for a, b in zip(g, c):
            ok = a["sys"] == b["sys"] and a["user"] == b["user"]
            check(ok, f"{name}/{a['tag']}：system / user 逐字一致", f"长度 sys {a['sys_len']}→{b['sys_len']} user {a['user_len']}→{b['user_len']}")
    check(total >= 14, f"共比对 {total} 次调用（含静态提示）", total)


def t_select():
    print("二、PACK / VERIFY 取值")
    from tools.dslagent import packs, verify
    env = {k: os.environ.pop(k, None) for k in ("DSLAGENT_PACK", "DSLAGENT_VERIFY")}
    try:
        check(packs.available() == ["code", "newproj"] and verify.available() == ["code"], "资料包有 code、newproj；验收目前只有 code", (packs.available(), verify.available()))
        check(packs.current().NAME == "code" and verify.current().NAME == "code", "缺省 code")
        os.environ["DSLAGENT_PACK"] = "code"
        check(packs.current().NAME == "code" and verify.current().NAME == "code", "显式 code")
        os.environ["DSLAGENT_PACK"] = "docs"
        try:
            packs.current()
            check(False, "PACK=docs 要报错")
        except ValueError as e:
            check("docs" in str(e) and "code" in str(e), "PACK 取值不对：报错并列出可用的", str(e))
        try:
            verify.current()           # verify 缺省跟随 PACK
            check(False, "VERIFY 跟随 PACK=docs 要报错")
        except ValueError as e:
            check("docs" in str(e) and "code" in str(e), "VERIFY 缺省跟随 PACK，同样报错", str(e))
        os.environ["DSLAGENT_PACK"] = "code"
        os.environ["DSLAGENT_VERIFY"] = "nope"
        try:
            verify.current()
            check(False, "VERIFY=nope 要报错")
        except ValueError as e:
            check("nope" in str(e) and "code" in str(e), "VERIFY 取值不对：报错并列出可用的", str(e))
        # run() 遇到坏取值：不抛异常，按失败收尾，原因写明
        os.environ["DSLAGENT_PACK"] = "docs"
        os.environ.pop("DSLAGENT_VERIFY", None)
        f = T.Fake()
        r, p, _ = T.go("badpack", f)
        check(r["reply"]["状态"] == "失败" and "DSLAGENT_PACK" in r["reply"]["原因"] and "code" in r["reply"]["原因"] and f.log == []
              and T.util(p) == T.UTIL, "run：PACK 取值不对 → 失败、不调模型、不动项目", r["reply"])
    finally:
        for k, v in env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def t_compat():
    print("三、旧 import 路径兼容")
    from tools.dslagent import packs, v2pack
    from tools.dslagent.packs import code as PC
    from tools.dslagent.verify import code as VC
    check(v2pack.build is PC.build and v2pack.is_test is PC.is_test, "v2pack 转发到 packs.code")
    check(v2pack.test_asserts is PC.test_asserts and v2pack.PACK_CHARS == PC.PACK_CHARS, "v2pack 的私有名 / 常量也在")
    for n in ("_fix_user", "dispatch_fix", "full_test", "apply_edits", "run_boundary", "residuals", "checklist_gaps",
              "enclosing", "func_span", "strip_code", "_changed_funcs"):
        check(getattr(V, n) is getattr(VC, n), f"v2.{n} 转发到 verify.code")
    for n in ("FIX_SYS", "BOUND_SYS", "BFIX_SYS"):
        check(isinstance(getattr(V, n), str) and getattr(V, n), f"v2.{n} 还在")
    for n in ("snapshot", "changed", "restore", "diff_text", "code_hash"):
        check(callable(getattr(V, n)), f"v2.{n} 还在")


def t_cbatch():
    print("四、cbatch 透传 pack（假 dsl 进程的完整验证在 test_cbatch.py）")
    from tools import cbatch as CB
    src = Path(CB.__file__).read_text(encoding="utf-8")
    check('o.get("pack")' in src and 'env["DSLAGENT_PACK"]' in src, "_run_dsl 把 dsl_options.pack 设成 DSLAGENT_PACK")
    check("_packs.pick" in src, "提交时校验 pack 取值")


def main():
    if "--record" in sys.argv:
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(compact(record_all()), ensure_ascii=False, indent=1), encoding="utf-8")
        print("基线已写入", GOLDEN)
        shutil.rmtree(T.TMP, ignore_errors=True)
        return 0
    try:
        t_prompts()
        t_select()
        t_compat()
        t_cbatch()
    finally:
        shutil.rmtree(T.TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
