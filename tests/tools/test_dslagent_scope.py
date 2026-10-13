# -*- coding: utf-8 -*-
"""派任务入参自动附原文（各种写法、越界说明、CRLF 文件）+ 搜索代码的「范围」参数。不调模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_scope.py
"""

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_scope_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")

from tools.dsl_task import collect_inputs      # noqa: E402

DEFS = ROOT / "tools" / "dslagent" / "verbs" / "code" / "defs"
PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"：{extra}" if extra else ""))


def verb(name, ws):
    spec = importlib.util.spec_from_file_location(f"_t_{name}", DEFS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.WORKSPACE = Path(ws)
    return getattr(m, name)


def project():
    ws = TMP / "ws"
    shutil.rmtree(ws, ignore_errors=True)
    (ws / "pkg" / "sub").mkdir(parents=True)
    (ws / "a.py").write_text("".join(f"line_a{i}\n" for i in range(1, 21)), encoding="utf-8")
    (ws / "pkg" / "b.py").write_text("".join(f"line_b{i}\n" for i in range(1, 11)) + "TARGET b\n", encoding="utf-8")
    (ws / "pkg" / "sub" / "c.py").write_text("TARGET c\n", encoding="utf-8")
    (ws / "pkg2.py").write_text("TARGET pkg2\n", encoding="utf-8")
    (ws / "crlf.py").write_bytes(b"one\r\ntwo\r\nthree\r\n")
    return ws


def body(inputs, ws):
    return "\n".join(f"{t}\n{c}" for t, c in collect_inputs(inputs, ws))


def test_inputs():
    print("\n── 派任务入参自动附原文 ──")
    ws = project()
    one = collect_inputs({"src": "a.py:3-5"}, ws)
    check(len(one) == 1 and one[0][0] == "src" and "   3| line_a3" in one[0][1] and "   5| line_a5" in one[0][1]
          and "line_a6" not in one[0][1], "单段 文件:起-止（旧写法不变）", one)
    one = collect_inputs("a.py:7", ws)
    check("   7| line_a7" in one[0][1] and "line_a8" not in one[0][1] and one[0][0] == "a.py:7", "文件:行（单行，字符串入参）")
    t = body({"src": "a.py:1-2,5-6,19-20"}, ws)
    check(all(k in t for k in ("line_a1\n", "line_a2\n", "line_a5\n", "line_a6\n", "line_a19\n", "line_a20"))
          and "line_a3" not in t and "line_a10" not in t, "多段 a-b,c-d,e-f 每段都附上", t)
    t = body({"src": "a.py:1-2, 5-6，9"}, ws)
    check("line_a2\n" in t and "line_a5\n" in t and "line_a6\n" in t and "   9| line_a9" in t, "多段逗号后带空格 / 全角逗号 / 含单行", t)
    t = body({"src": "a.py:1-2,pkg/b.py:3-4"}, ws)
    check("line_a2\n" in t and "line_b3\n" in t and "line_b4" in t, "同一值里逗号分隔的两个文件", t)
    t = body({"src": "看 a.py:2-3 和 pkg/b.py:9-10 这两处"}, ws)
    check(t.startswith("src\n看 a.py:2-3 和") and "line_a3\n" in t and "line_b9\n" in t, "夹在句子中间也读出，原文字保留", t)
    t = body(["a.py:1-2,9-10", "pkg/b.py:1-1"], ws)
    check("line_a10" in t and "   1| line_b1" in t, "数组入参：每项多段", t)
    t = body("a.py:1-2,9-10,pkg/b.py:4-5", ws)
    check("line_a10" in t and "line_b4\n" in t and "line_b5" in t and t.count("◆") == 0, "纯文本逗号分隔：区间后的 9-10 不被当成独立一项", t)
    items = collect_inputs("a.py:1-2,9-10,pkg/b.py:4-5", ws)
    check(len(items) == 2, "…拆成两项（a.py 多段 / pkg/b.py）", [i[0] for i in items])
    t = body({"src": "a.py:1-2,a.py:1-2"}, ws)
    check(t.count("   1| line_a1") == 1, "重复的段只附一次", t)
    t = body({"src": "pkg/b.py"}, ws)
    check("   1| line_b1" in t and "共 11 行" in t, "只写存在的文件名＝整份")
    t = body({"note": "把 foo.bar 改成 3，比例 1.5:3，网址 http://x.com:80/y"}, ws)
    check("读不到" not in t and t.count("\n") == 1, "普通句子里的 1.5:3 / host:port 不当成文件", t)
    print("  -- 越界说明 --")
    t = body({"src": "nope.py:1-5"}, ws)
    check("[读不到 nope.py:1-5：文件不存在]" in t, "文件不存在 → 说明", t)
    t = body({"src": "a.py:1-2,90-95"}, ws)
    check("line_a2\n" in t and "[读不到 a.py:90-95：行号越界，文件共 20 行]" in t, "起点越界 → 说明，其余段照读", t)
    t = body({"src": "a.py:18-99"}, ws)
    check("line_a20" in t and "要求到第 99 行，文件只有 20 行" in t and "第 18-20 行" in t, "止点越界 → 读到末尾并说明", t)
    t = body({"src": "a.py:9-3"}, ws)
    check("起止写反了" in t, "起止写反 → 说明", t)
    t = body({"src": "../outside.py:1-2"}, ws)
    check("越出工作目录" in t, "越出工作目录 → 说明", t)
    t = body({"src": "文件 nope.py:3 里"}, ws)
    check("[读不到 nope.py:3：文件不存在]" in t and t.startswith("src\n文件 nope.py:3 里"), "句子中间的坏引用也有说明")
    print("  -- 换行格式 --")
    t = body({"src": "crlf.py:1-3"}, ws)
    check("   2| two\n" in t and "\r" not in t, "CRLF 文件读出来按行干净附上", repr(t))
    check((ws / "crlf.py").read_bytes() == b"one\r\ntwo\r\nthree\r\n", "读取不改原文件的换行")


def test_search():
    print("\n── 搜索代码 范围 ──")
    ws = project()
    s = verb("搜索代码", ws)
    allr = s("TARGET")
    check(all(k in allr for k in ("pkg/b.py:11", "pkg/sub/c.py:1", "pkg2.py:1")), "不给范围：搜全部（行为不变）", allr)
    check(s("TARGET", "") == allr and s("TARGET", "  ") == allr, "范围空串 / 空白 同不给")
    r = s("TARGET", "pkg/b.py")
    check(r == "pkg/b.py:11: TARGET b", "范围＝单个文件", r)
    r = s("TARGET", "pkg")
    check("pkg/b.py:11" in r and "pkg/sub/c.py:1" in r and "pkg2.py" not in r, "范围＝目录（含子目录，不误含 pkg2.py）", r)
    r = s("TARGET", "pkg/sub")
    check(r == "pkg/sub/c.py:1: TARGET c", "范围＝子目录", r)
    r = s("TARGET", "pkg/b.py,pkg2.py")
    check("pkg/b.py:11" in r and "pkg2.py:1" in r and "pkg/sub" not in r, "多个范围逗号隔开", r)
    r = s("TARGET", "pkg/sub/,./pkg2.py")
    check("pkg/sub/c.py:1" in r and "pkg2.py:1" in r and "pkg/b.py" not in r, "带尾斜杠 / ./ 前缀", r)
    r = s("TARGET", ".")
    check(r == allr, "范围＝. 等于全部", r)
    r = s("line_a1", "pkg")
    check(r.startswith("[搜索] 没有匹配") and "范围 pkg" in r, "范围内没有命中", r)
    r = s("TARGET", "nope/x.py")
    check(r.startswith("[搜索] 范围 nope/x.py 不存在"), "范围不存在 → 说明不抛错", r)
    r = s("TARGET", "../etc")
    check("范围 ../etc 不行" in r and "越界" in r, "范围越出项目 → 说明", r)
    r = s("(", "pkg")
    check("正则写错了" in r, "正则错误照旧")
    check(s("") == "[搜索] 没给正则", "没给正则照旧")
    for i in range(35):
        (ws / "pkg" / f"m{i}.py").write_text("MANY\n", encoding="utf-8")
    (ws / "other.py").write_text("MANY\n", encoding="utf-8")
    r = s("MANY", "pkg")
    check("共 35 条命中" in r and "other.py" not in r, "命中超限的汇总只统计范围内", r[:120])


def test_prompts():
    print("\n── 规划提示 ──")
    from tools.dslagent import prompts as PR
    i = PR.VERBS.index("- 搜索代码")
    seg = PR.VERBS[i:i + 400]
    check("范围：文件或目录" in seg and "tools/dsl_core.py" in seg, "VERBS 里 搜索代码 写了范围参数")


def main():
    test_inputs()
    test_search()
    test_prompts()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
