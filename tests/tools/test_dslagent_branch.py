# -*- coding: utf-8 -*-
"""dslagent 的分支式规划：查引用、白名单 / 空跑认识 终止 和 派任务、示例 lib/示例_分支规划.zs 三路空跑。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_branch.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dslagent import plan as P              # noqa: E402
from tools.dslagent import prompts as PR          # noqa: E402
from tools.dslagent.engine import AgentEngine     # noqa: E402
from tools.mock import MockClient                 # noqa: E402

EXAMPLE = P.PKG / "lib" / "示例_分支规划.zs"
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def write(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def agent(workdir, handler=None):
    m = MockClient(handler=handler or (lambda p, s=None: "嗯"), offline=True)
    return AgentEngine(client=m, workdir=workdir, verbose=False, verbs_root=P.PKG / "verbs"), m


def test_refs(tmp):
    print("一、查引用")
    repo = tmp / "refs"
    write(repo, {"pkg/a.py": "def load_cfg():\n    return 1\n",
                 "pkg/b.py": "from pkg.a import load_cfg\nx = load_cfg()\ny = load_cfg_v2()\n",
                 "docs/notes.md": "调用 load_cfg 读配置\n",
                 ".venv/lib/c.py": "load_cfg()\n",
                 "pkg/__pycache__/a.cpython-314.py": "load_cfg\n",
                 ".git/x.py": "load_cfg\n"})
    (repo / "pkg" / "blob.bin").write_bytes(b"\0load_cfg\0")
    eng, _ = agent(repo)
    eng.run("用包 common text code\n设 all = 查引用 load_cfg\n设 py = 查引用 load_cfg py\n设 none = 查引用 nothing_here")
    allr, pyr, none = eng.vars["all"], eng.vars["py"], eng.vars["none"]
    where = [f"{r['file']}:{r['line']}" for r in allr["refs"]]
    check(where == ["docs/notes.md:1", "pkg/a.py:1", "pkg/b.py:1", "pkg/b.py:2"],
          f"所有文本文件里的引用（文件:行），排除 .venv/__pycache__/.git/二进制，整词匹配不算 load_cfg_v2：{where}")
    check(allr["n"] == 4 and allr["files"] == 3, f"n={allr['n']} files={allr['files']}")
    check(allr["text"].splitlines()[1] == "pkg/a.py:1: def load_cfg():", f"text 每行「文件:行: 那一行」：{allr['text']!r}")
    check([r["file"] for r in pyr["refs"]] == ["pkg/a.py", "pkg/b.py", "pkg/b.py"], "写 py 只看 .py")
    check(none["n"] == 0 and "没有引用" in none["text"], "没有引用时 n=0")
    eng.run("用包 common text code\n设 r = 查引用 pkg.a py")
    check([f"{x['file']}:{x['line']}" for x in eng.vars["r"]["refs"]] == ["pkg/b.py:1"], "带点号的名字照字面找")
    out = eng.run("用包 common text code\n设 refs = 查引用 load_cfg py\n如果 {refs.n} 大于 2\n  打印 多\n结束")
    check(out.strip().endswith("多"), "条件里直接比 {refs.n}")


def test_whitelist():
    print("二、白名单与提示")
    check({"派任务", "并行派任务", "查引用"} <= P.ALLOWED_VERBS, "ALLOWED_VERBS 有 派任务 / 并行派任务 / 查引用")
    check({"派任务", "并行派任务", "查引用"} <= P.ALL_VERBS, "ALL_VERBS 认得出新动词")
    script = ("用包 common text code\n设 r = 派任务 {task}\n设 rs = 并行派任务 {jobs} 2\n设 f = 查引用 x py\n"
              "如果 {r.状态} 等于 失败\n  终止 失败 {r.原因}\n结束\n终止 成功 好")
    check(P.whitelist_check(script, {}) == [], f"新语句、新动词过白名单：{P.whitelist_check(script, {})}")
    check(P.whitelist_check(EXAMPLE.read_text(encoding="utf-8"), {}) == [], "示例脚本过白名单")
    for word in ("终止 成功|失败|超出预期", "派任务", "并行派任务", "查引用"):
        check(word in PR.SYSTEM, f"规划系统提示的速查里有「{word}」")
    check(P.autoclose("用包 common\n如果 {a} 等于 1\n  终止 失败 x")[1] == 1, "补结束照常（终止 不是块）")


def test_dry(tmp):
    print("三、空跑")
    proj = tmp / "proj"
    write(proj, {"pkg/__init__.py": "import json\n\n\ndef total(xs):\n    return sum(xs)\n",
                 "tests/__init__.py": "",
                 "tests/test_t.py": "import unittest\nfrom pkg import total\n\n\nclass T(unittest.TestCase):\n"
                                    "    def test_a(self):\n        self.assertEqual(total([1, 2]), 3)\n"})

    def dry(script, subs=None):
        return P.dry_run(proj, tmp / "work", script, subs or {}, "示例任务",
                         lambda d, s: {f"_plan/{k}": Path(d) / k for k in s}, "平衡")

    err, n, out = dry("用包 common text code\n设 r = 派任务 {task} 无 无 edits:列表,note:文本\n"
                      "设 rs = 并行派任务 [\"甲\",\"乙\"] 2\n打印 {r.状态} {r.空跑} {rs.1.状态}\n打印 结论：没修好 示意")
    check(not err and n == 0 and "成功 是 成功" in out, f"派任务 / 并行派任务 空跑不调假模型、给合法假结果：err={err!r} calls={n} {out!r}")
    err, n, out = dry("用包 common text code\n终止 超出预期 前提不对")
    check(not err and "[终止] 超出预期：前提不对" in out, f"以 终止 收尾的计划没打印「结论：」也算过：{err!r}")
    err, n, out = dry("用包 common text code\n打印 什么也没说")
    check("结论" in err, "既没 结论 也没 终止 照旧不过")
    err, n, out = dry("用包 common text code\n设 r = 执行 _plan/s.zs\n打印 结论：没修好 {r.状态}|{r.停在}",
                      {"s.zs": "用包 common text code\n设 x = 派任务 做事\n终止 {x.状态} 子脚本{x.空跑}"})
    check(not err and "结论：没修好 成功|_plan/s.zs 第 3 行" in out,
          f"子脚本里空跑标志传下去、子脚本终止交回调用方：{err!r} {out!r}")

    script = EXAMPLE.read_text(encoding="utf-8")
    head = "设 mod = {mod 或 pkg}"
    for extra, want in (("", "[终止] 成功：导入只用"),
                        ("设 fast = 0\n", "第 1 次派任务：成功"),
                        ("设 fast = 0\n设 slow = 0\n", "并行查：成功")):
        err, n, out = dry(script.replace(head, extra + head))
        ok = not err and n == 0 and want in out and "[终止]" in out
        check(ok, f"示例脚本空跑通（{extra.strip() or '快'}）：err={err!r} calls={n}")
        if not ok:
            print(out)
    err, n, out = dry(script.replace(head, "设 fast = 0\n设 tries = 1\n" + head))
    check(not err and "[终止] 失败：试了 1 次没成" in out, "改法没套上 → 用完次数终止 失败")


def test_example_real(tmp):
    print("四、示例脚本：假模型给真改法 → 套上 → 测试过 → 终止 成功")
    proj = tmp / "real"
    write(proj, {"pkg/__init__.py": "import json\n\n\ndef total(xs):\n    return sum(xs)\n",
                 "tests/__init__.py": "",
                 "tests/test_t.py": "import unittest\nfrom pkg import total\n\n\nclass T(unittest.TestCase):\n"
                                    "    def test_a(self):\n        self.assertEqual(total([1, 2]), 3)\n"})
    n = {"i": 0}

    def handler(prompt, system=None):
        n["i"] += 1
        if n["i"] == 1:      # 第一次给个对不上原文的改法，看重试
            edits = [{"file": "pkg/__init__.py", "old": "import yaml", "new": ""}]
        else:
            edits = [{"file": "pkg/__init__.py", "old": "import json\n", "new": ""}]
        return json.dumps({"结果": {"edits": edits, "note": f"第{n['i']}版"}, "状态": "成功", "原因": ""},
                          ensure_ascii=False)
    import os
    old = os.environ.get("DSLAGENT_STATE")
    os.environ["DSLAGENT_STATE"] = str(tmp / "state")
    try:
        eng, m = agent(proj, handler)
        eng.vars.update(fast="0", src="pkg/__init__.py:1-5")
        out = eng.run(EXAMPLE.read_text(encoding="utf-8"))
    finally:
        if old is None:
            os.environ.pop("DSLAGENT_STATE", None)
        else:
            os.environ["DSLAGENT_STATE"] = old
    check(eng.halted and eng.halted["状态"] == "成功" and "第2版" in eng.halted["原因"],
          f"第 2 次改法通过测试后终止 成功：{eng.halted}")
    first = m.calls[0]["messages"][-1]["content"] if m.calls else ""
    check("   1| import json" in first, "入参 src=文件:起-止 被读出附在子任务提示里")
    second = m.calls[1]["messages"][-1]["content"] if len(m.calls) > 1 else ""
    check("第1次改法没套上" in second, "上一次失败的原因带进下一次子任务")
    check("import json" not in (proj / "pkg" / "__init__.py").read_text(encoding="utf-8"), "改法真的套上了")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="dslagent_branch_"))
    try:
        test_refs(tmp)
        test_whitelist()
        test_dry(tmp)
        test_example_real(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
