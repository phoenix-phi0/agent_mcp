# -*- coding: utf-8 -*-
"""dslagent 里的「#改法」段和「预算」：改文件 {e1} 一次套全部条目（原子、报出现次数、CRLF 按原换行写回、
套前过 reason.check）、plan.py 的 strip_prose / split_subs / autoclose / whitelist_check / 空跑认识 #改法 #清单 预算、
规划提示的速查。不调模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_edits.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_edits_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ.pop("DSLAGENT_RULES", None)
(TMP / "state").mkdir()

from tools.dslagent import plan as P              # noqa: E402
from tools.dslagent import prompts as PR          # noqa: E402
from tools.dslagent import reason as R            # noqa: E402
from tools.dslagent.engine import ALLOWED_HEADS, AgentEngine   # noqa: E402
from tools.mock import MockClient                 # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


SRC = {"pkg/__init__.py": "",
       "pkg/a.py": "import json\n\n\ndef f(x):\n    return x\n\n\nB = 1\n",
       "pkg/b.py": "y = 1\ny = 1\n",
       "data/books.csv": "bid,title\n1,书一\n",
       "tests/__init__.py": "",
       "tests/test_a.py": "import unittest\nfrom pkg.a import f\n\n\nclass T(unittest.TestCase):\n"
                          "    def test_f(self):\n        self.assertEqual(f(1), 1)\n"}


def project(name, files=SRC):
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    for rel, text in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    return d


def apply(proj, sections, use="e1"):
    """跑「设 res = 改文件 {e1}」，返回 res。"""
    m = MockClient(handler=lambda p, s=None: "嗯", offline=True)
    eng = AgentEngine(client=m, workdir=proj, verbose=False, verbs_root=P.PKG / "verbs")
    eng.run(f"用包 common text code\n设 res = 改文件 {{{use}}}\n" + sections)
    return eng.vars["res"]


def blk(path, old, new):
    return f"@@ 改 {path}\n<<<<<<< 原文\n{old}\n=======\n{new}\n>>>>>>> 新文\n"


def test_apply():
    print("一、改文件 {e1}：套全部条目")
    p = project("all")
    sec = ("#改法 e1\n@@ 改 pkg/a.py\n<<<<<<< 原文\nimport json\n\n\ndef f(x):\n=======\ndef f(x):\n    import json\n"
           ">>>>>>> 新文\n<<<<<<< 原文\nB = 1\n=======\nB = 2\n>>>>>>> 新文\n"
           "@@ 新建 pkg/c.py\n<<<<<<< 内容\ndef g():\n    return 1\n>>>>>>> 新文\n"
           + blk("pkg/c.py", "    return 1", "    return 2") + blk("pkg/b.py", "y = 1\ny = 1", "y = 2"))
    r = apply(p, sec)
    a = (p / "pkg/a.py").read_text(encoding="utf-8")
    check(r["ok"] == "是" and r["n"] == 5, f"两处改 a.py、新建 c.py 再改它、改 b.py 全套上：{r}")
    check(a == "def f(x):\n    import json\n    return x\n\n\nB = 2\n", f"a.py 改后内容：{a!r}")
    check((p / "pkg/c.py").read_text(encoding="utf-8") == "def g():\n    return 2\n", "新建的文件同一份改法里还能接着改")
    check("新建 1 个文件" in r["msg"] and "pkg/c.py（新建" in r["msg"], f"msg 说明新建了什么：{r['msg']}")

    p = project("atomic")
    before = {k: (p / k).read_bytes() for k in SRC}
    r = apply(p, "#改法 e1\n" + blk("pkg/a.py", "B = 1", "B = 3") + blk("pkg/a.py", "C = 9", "C = 1")
              + "@@ 新建 pkg/d.py\n<<<<<<< 内容\nx = 1\n>>>>>>> 新文\n")
    check(r["ok"] == "否" and "出现 0 次" in r["msg"] and "整体没有改动" in r["msg"], f"原文对不上：ok=否、报 0 次：{r['msg']}")
    check(all((p / k).read_bytes() == v for k, v in before.items()) and not (p / "pkg/d.py").exists(),
          "原子：别的条目也都没套、新文件没建")
    r = apply(p, "#改法 e1\n" + blk("pkg/b.py", "y = 1", "y = 3"))
    check(r["ok"] == "否" and "出现了 2 次" in r["msg"], f"原文不唯一：报出现次数：{r['msg']}")
    r = apply(p, "#改法 e1\n@@ 新建 pkg/a.py\n<<<<<<< 内容\nx\n>>>>>>> 新文\n")
    check(r["ok"] == "否" and "已存在" in r["msg"] and (p / "pkg/a.py").read_bytes() == before["pkg/a.py"],
          f"@@ 新建 不覆盖已有文件：{r['msg']}")
    r = apply(p, "#改法 e1\n@@ 新建 tests/test_new.py\n<<<<<<< 内容\nx\n>>>>>>> 新文\n")
    check(r["ok"] == "否" and "测试文件" in r["msg"] and not (p / "tests/test_new.py").exists(), f"不许新建测试文件：{r['msg']}")
    r = apply(p, "#改法 e1\n" + blk("tests/test_a.py", "f(1), 1", "f(1), 2"))
    check(r["ok"] == "否" and "测试文件" in r["msg"], f"不许改测试文件：{r['msg']}")
    r = apply(p, "#改法 e2\n" + blk("pkg/a.py", "B = 1", "B = 2"), use="e2")
    check(r["ok"] == "是" and "B = 2" in (p / "pkg/a.py").read_text(encoding="utf-8"), "段名随意，{e2} 也行")


def test_crlf():
    print("二、CRLF 按原换行写回")
    p = project("crlf")
    raw = b"import json\r\n\r\n\r\ndef f(x):\r\n    return x\r\n\r\n\r\nB = 1\r\n"
    (p / "pkg/a.py").write_bytes(raw)
    r = apply(p, "#改法 e1\n" + blk("pkg/a.py", "def f(x):\n    return x", "def f(x):\n    y = x\n    return y")
              + "@@ 新建 pkg/n.py\n<<<<<<< 内容\nz = 1\n>>>>>>> 新文\n")
    got = (p / "pkg/a.py").read_bytes()
    check(r["ok"] == "是", f"LF 写的原文对得上 CRLF 文件：{r}")
    check(got == b"import json\r\n\r\n\r\ndef f(x):\r\n    y = x\r\n    return y\r\n\r\n\r\nB = 1\r\n",
          f"整份仍是 CRLF，新加的行也是 CRLF：{got!r}")
    check((p / "pkg/n.py").read_bytes() == b"z = 1\n", "新建文件照段里的换行（LF）")
    mixed = b"a = 1\r\nb = 2\nc = 3\r\n"
    (p / "pkg/m.py").write_bytes(mixed)
    r = apply(p, "#改法 e1\n" + blk("pkg/m.py", "b = 2", "b = 9"))
    check(r["ok"] == "是" and (p / "pkg/m.py").read_bytes() == b"a = 1\r\nb = 9\nc = 3\r\n", "混合换行：没动的行一字不变")
    r = apply(p, "#改法 e1\n" + blk("pkg/a.py", "B = 2", "B = 3"))
    check(r["ok"] == "否" and "出现 0 次" in r["msg"] and (p / "pkg/a.py").read_bytes() == got, "CRLF 文件对不上同样报次数、不动")


def test_reason():
    print("三、套前过 reason.check")
    p = project("safe")
    snap = R.all_files(p)
    R.setup(p, snap, "把 f 改一下。data/books.csv 不要动。")
    try:
        r = apply(p, "#改法 e1\n" + blk("pkg/a.py", "B = 1", "B = 2") + blk("data/books.csv", "书一", "书二"))
        check(r["ok"] == "否" and "安全约束" in r["msg"] and R.all_files(p) == snap,
              f"一处被安全约束拦下 → 整体不写：{r['msg']}")
        r = apply(p, "#改法 e1\n" + blk("pkg/a.py", "B = 1", "B = 2"))
        check(r["ok"] == "是", f"只改源码放行：{r['msg']}")
    finally:
        R.STATE.update(snap=None, task="", log=[])


ART = ("#改法 e1\n@@ 改 pkg/a.py\n<<<<<<< 原文\nB = 1\n=======\nB = 2\n>>>>>>> 新文\n\n"
       "#清单\n改 pkg/a.py:B\n提示 只改 B")


def test_plan():
    print("四、plan.py 认识 #改法 / #清单 / 预算")
    check("budget" in ALLOWED_HEADS, "语句白名单有 预算（budget）")
    main = "用包 common text code\n预算 调用 3 秒 120\n设 res = 改文件 {e1}\n打印 {res.ok}\n打印 结论：修好 套上了\n"
    txt = "好的，计划如下：\n```\n" + main + ART + "\n```\n"
    script, _ = P.strip_prose(txt)
    check(script.startswith("用包") and script.endswith("提示 只改 B") and "<<<<<<< 原文" in script,
          f"strip_prose：去掉开头说明和围栏，段整段留着：{script[-30:]!r}")
    check(P.whitelist_check(script, {}) == [], f"预算 + 段过白名单（段里的代码原文不当语句查）：{P.whitelist_check(script, {})}")
    only = ("说明一句\n#改法 e1\n@@ 新建 pkg/n.py\n<<<<<<< 内容\nimport os\n设 x = 1\n>>>>>>> 新文\n" + blk("pkg/a.py", "B = 1", "B = 2")
            + "\n#清单\n新建 pkg/n.py\n改 pkg/a.py:B")
    s2, _ = P.strip_prose(only)
    check(s2.startswith("#改法 e1") and s2.endswith("改 pkg/a.py:B") and P.whitelist_check(*P.split_subs(s2)) == [],
          f"只有段、没写主脚本：从第一个段开始留（段里像语句的行不当开头），过白名单：{s2[:30]!r}")
    probs = P.whitelist_check(main + "#改法 e1\n@@ 改 a.py\n<<<<<<< 原文\nx\n>>>>>>> 新文\n打印 尾巴", {})
    check(any("#改法 e1" in x and "缺 =======" in x for x in probs) and any("认不出" in x for x in probs),
          f"段写错：白名单检查就报出来：{probs}")
    check(any("不在白名单" in x for x in P.whitelist_check("用包 common text code\n读取 x = a.txt", {})), "别的照旧拦")

    m, subs = P.split_subs("用包 common text code\n执行 _plan/s.zs\n#子脚本 s.zs\n打印 子\n" + ART)
    check("#改法 e1" in m and "#清单" in m and list(subs) == ["s.zs"] and subs["s.zs"].strip() == "打印 子",
          f"写在子脚本后面的段归到主脚本：sub={subs}")
    check("<<<<<<<" not in subs["s.zs"], "子脚本里不带段")

    s = "用包 common text code\n如果 {a} 等于 1\n  打印 x\n" + \
        "#改法 e1\n@@ 改 pkg/a.py\n<<<<<<< 原文\nif x:\n    遍历 y\n=======\nif y:\n    如果 z\n>>>>>>> 新文"
    new, n, _ = P.autoclose(s)
    check(n == 1 and "  打印 x\n结束\n#改法 e1" in new and new.endswith("    如果 z\n>>>>>>> 新文"),
          f"autoclose 不看段里的代码（段里的「遍历」「如果」不算块），结束补在段前：{new!r}")

    proj = project("dry")
    before = (proj / "pkg/a.py").read_bytes()
    err, n, out = P.dry_run(proj, TMP / "work", P.split_subs(script)[0], {}, "改 B", lambda d, s: {}, "平衡")
    check(not err and "是" in out and "结论：修好" in out, f"空跑认识 #改法 / #清单 / 预算：err={err!r} out={out!r}")
    check((proj / "pkg/a.py").read_bytes() == before, "空跑改的是拷贝，项目不动")
    err, n, out = P.dry_run(proj, TMP / "work", "用包 common text code\n预算 调用 1\n问 a = x\n问 b = y\n打印 结论：修好",
                            {}, "t", lambda d, s: {}, "平衡")
    check(not err and "[终止] 超出预期：预算用完" in out, f"空跑里预算用完按 终止 收尾，不算没过：{err!r} {out!r}")

    for w in ("预算 调用 N 秒 M", "#改法 名", "@@ 改", "@@ 新建", "<<<<<<< 原文", ">>>>>>> 新文", "#清单", "改文件 {e1}"):
        check(w in PR.SYSTEM, f"规划系统提示里有「{w}」")
    ex = (P.PKG / "lib" / "示例_分支规划.zs").read_text(encoding="utf-8")
    check("预算 调用" in ex and "#改法 e1" in ex and "改文件 {e1}" in ex and "#清单" in ex, "示例脚本用上 预算 和 #改法 / #清单")


def test_check_plan():
    print("计划检查：#改法 原文对着真实文件核对（只读）")
    from tools.dslagent import dslcheck as DC
    from tools.dslagent import v2 as V
    files = dict(SRC, **{"pkg/m.py": "a = 1\nx = 0\nb = 2\nx = 0\nc = 3\nx = 0\n"})
    p = project("chk", files)
    snap = {f.relative_to(p): f.read_bytes() for f in p.rglob("*") if f.is_file()}

    def probs(sec):
        return DC.edit_problems(p, "用包 common text code\n预算 调用 1 秒 60\n终止 成功 好\n" + sec)
    pr = probs("#改法 e1\n" + blk("pkg/a.py", "return x", "return x + 1"))
    check(pr == [], f"唯一匹配没问题：{pr}")
    pr = probs("#改法 e1\n" + blk("pkg/a.py", "没有这行", "x"))
    check(len(pr) == 1 and "#改法 e1" in pr[0] and "第 1 处" in pr[0] and "pkg/a.py" in pr[0] and "出现 0 次" in pr[0], f"0 次：{pr}")
    pr = probs("#改法 e1\n" + blk("pkg/m.py", "x = 0", "x = 1"))
    check(len(pr) == 1 and "出现 3 次" in pr[0] and "第 2 行" in pr[0] and "第 4 行" in pr[0] and "第 6 行" in pr[0]
          and "a = 1" in pr[0] and "b = 2" in pr[0] and "多带几行上下文" in pr[0], f"多次：次数、行号、前后各 1 行、建议：{pr}")
    pr = probs("#改法 e1\n" + blk("pkg/nope.py", "x", "y"))
    check(len(pr) == 1 and "pkg/nope.py 不存在" in pr[0], f"文件不存在：{pr}")
    pr = probs("#改法 e1\n@@ 新建 pkg/a.py\n<<<<<<< 内容\nz = 1\n>>>>>>> 新文\n")
    check(len(pr) == 1 and "pkg/a.py 已存在" in pr[0] and "新建" in pr[0], f"新建的文件已存在：{pr}")
    # 顺序套用：第 1 处把 B = 1 改成 B = 2，第 2 处再找 B = 1 就找不到；第 2 处找 B = 2 才对
    pr = probs("#改法 e1\n" + blk("pkg/a.py", "B = 1", "B = 2") + blk("pkg/a.py", "B = 1", "B = 3"))
    check(len(pr) == 1 and "第 2 处" in pr[0] and "出现 0 次" in pr[0] and "前面几处改过之后" in pr[0], f"顺序套用（前一对改完再找）：{pr}")
    pr = probs("#改法 e1\n" + blk("pkg/a.py", "import json", "import json\nimport os") + blk("pkg/a.py", "B = 1", "B = 2"))
    check(pr == [], f"顺序套用：前一对改变了长度，后一对照样找得到、不误报重叠：{pr}")
    # 后一对的 old 落在前一对的新文本里：改文件 顺序套用时能套上，检查也要通过
    seq1 = blk("pkg/a.py", "B = 1", "B = 2") + blk("pkg/a.py", "B = 2", "B = 3")
    seq2 = (blk("pkg/a.py", "def f(x):\n    return x", "def f(x):\n    return 0")
            + blk("pkg/a.py", "return 0\n\n\nB", "return 0\n\nB"))
    for tag, seq, want in (("seq1", seq1, "B = 3\n"), ("seq2", seq2, "    return 0\n\nB = 1\n")):
        pr = probs("#改法 e1\n" + seq)
        q = project("chk_" + tag)
        res = apply(q, "#改法 e1\n" + seq)
        check(pr == [] and res["ok"] == "是" and (q / "pkg/a.py").read_text(encoding="utf-8").endswith(want),
              f"old 落在前一对新文本里：检查通过、改文件 也套得上（{tag}）：{pr} {res}")
    pr = probs("#改法 e1\n" + blk("pkg/a.py", "没有", "x") + "#改法 e2\n" + blk("pkg/m.py", "x = 0", "x = 1"))
    check(len(pr) == 2 and "#改法 e1" in pr[0] and "#改法 e2" in pr[1], f"每段各自核对、文案带段名：{pr}")
    check(all(f.read_bytes() == snap[f.relative_to(p)] for f in p.rglob("*") if f.is_file()) and len(list(p.rglob("*"))) == len(snap) + 3,
          "核对只读，项目文件不变")
    # v2.check：静态过后接着核对，问题进检查错误（交给规划重写）
    plan = "用包 common text code\n预算 调用 3 秒 60\n设 res = 改文件 {e1}\n终止 成功 好\n#改法 e1\n" + blk("pkg/m.py", "x = 0", "x = 1") + "#清单\n改 pkg/m.py:x\n"
    problem, *_ = V.check(p, TMP / "dry_chk", plan, "改 x")
    check("出现 3 次" in problem and "pkg/m.py" in problem and "第 2 行" in problem, f"v2.check 报出：{problem[:200]}")
    # 复用 改文件 的匹配：CRLF 文件、old 只用 LF 也能唯一匹配
    q = project("chk_crlf", {"pkg/a.py": "def f(x):\r\n    return x\r\n", "pkg/__init__.py": ""})
    pr = DC.edit_problems(q, "#改法 e1\n" + blk("pkg/a.py", "def f(x):\n    return x", "def f(x):\n    return 1"))
    check(pr == [], f"CRLF 文件按改文件的方式匹配：{pr}")


def test_create_json():
    print("改文件：old 为空且文件不存在 = 新建")
    p = project("mk")
    ed = lambda f, old, new: {"file": f, "old": old, "new": new}  # noqa: E731
    apply_e = lambda e: apply_json(p, e)  # noqa: E731
    r = apply_e({"edits": [ed("pkg/new/safe.py", "", "def s():\n    return 1\n")]})
    check(r["ok"] == "是" and (p / "pkg/new/safe.py").read_text(encoding="utf-8") == "def s():\n    return 1\n" and "新建" in r["msg"],
          f"old 空 + 文件不存在：新建（父目录自动建）：{r}")
    r = apply_e({"edits": [ed("pkg/a.py", "", "x = 1\n")]})
    check(r["ok"] == "否" and "已存在" in r["msg"] and "old 不能为空" in r["msg"] and "写文件" in r["msg"]
          and (p / "pkg/a.py").read_text(encoding="utf-8") == SRC["pkg/a.py"], f"old 空 + 文件已存在：报错、不改：{r}")
    r = apply_e({"edits": [{"file": "pkg/n2.py", "new": "k = 1\n"}]})
    check(r["ok"] == "是" and (p / "pkg/n2.py").is_file(), f"old 缺省也算空：{r}")
    # 混合原子性：新建 + 改，其中一处不行 → 一个文件都不建
    r = apply_e({"edits": [ed("pkg/n3.py", "", "k = 1\n"), ed("pkg/a.py", "没有这行", "x")]})
    check(r["ok"] == "否" and "整体没有改动" in r["msg"] and not (p / "pkg/n3.py").exists(), f"混合：后面的改失败，前面的新建也不落盘：{r}")
    r = apply_e({"edits": [ed("pkg/n3.py", "", "k = 1\n"), ed("pkg/a.py", "B = 1", "B = 9"), ed("pkg/n3.py", "k = 1", "k = 2")]})
    check(r["ok"] == "是" and (p / "pkg/n3.py").read_text(encoding="utf-8") == "k = 2\n" and "B = 9" in (p / "pkg/a.py").read_text(encoding="utf-8")
          and "新建 1 个文件" in r["msg"], f"混合成功：新建 + 改，新建的文件后面还能接着改：{r}")
    r = apply_e({"edits": [ed("pkg/n4.py", "", "a\n"), ed("pkg/n4.py", "", "b\n")]})
    check(r["ok"] == "否" and not (p / "pkg/n4.py").exists(), f"同批两次新建同一文件：报错不落盘：{r}")
    r = apply_e({"edits": [ed("tests/test_new.py", "", "x = 1\n")]})
    check(r["ok"] == "否" and "测试文件" in r["msg"] and not (p / "tests/test_new.py").exists(), f"安全约束照旧：不许新建测试文件：{r}")
    r = apply_e({"edits": [ed("../escape.py", "", "x = 1\n")]})
    check(r["ok"] == "否" and not (p.parent / "escape.py").exists(), f"安全约束照旧：不许越出项目：{r}")


def apply_json(proj, e):
    import json
    m = MockClient(handler=lambda p, s=None: "嗯", offline=True)
    eng = AgentEngine(client=m, workdir=proj, verbose=False, verbs_root=P.PKG / "verbs")
    eng.vars["e"] = json.dumps(e, ensure_ascii=False)
    eng.run("用包 common text code\n设 res = 改文件 {e}\n")
    return eng.vars["res"]


def main():
    try:
        test_apply()
        test_crlf()
        test_reason()
        test_plan()
        test_check_plan()
        test_create_json()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
