# -*- coding: utf-8 -*-
"""脚本末尾的多行段（#改法 / #清单）和「预算」语句，在引擎这一层（不涉及 dslagent 的 改文件 动词）。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_edit_budget.py

  一、#改法 段：解析成 {edits, files}、多对、多段、同名合并、按字面不展开、CRLF 脚本、行号不变、
      #清单、子脚本自己的段、写错运行前就报
  二、预算：调用数（第 N+1 次不发出）、秒数、可只写其一、变量、覆盖、写错运行前就报、
      派任务 / 并行派任务 / 子脚本都算、子脚本里用完回到调用方也停、每次 run 重新计
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import DSLEngine                         # noqa: E402
from tools.dsl_sections import split_sections       # noqa: E402
from tools.mock import MockClient                   # noqa: E402

VERBS = ROOT / "verbs"
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(script, handler=None, workdir=None, eng=None):
    """返回 (输出或报错文本, 引擎, 假客户端)。"""
    m = MockClient(handler=handler or (lambda p, s=None: "嗯"), offline=True)
    eng = eng or DSLEngine(m, workdir=workdir, verbose=False, verbs_root=VERBS)
    try:
        out = eng.run(script)
    except Exception as e:
        out = f"{type(e).__name__}: {e}"
    return out.strip(), eng, m


EDIT = """打印 {e1.edits.0.file}
#改法 e1
@@ 改 pkg/a.py
<<<<<<< 原文
def f(x):
    return {x}  # 注释
=======
def f(x):
    return x + 1
>>>>>>> 新文
<<<<<<< 原文
B = 1
=======
B = 2
>>>>>>> 新文
@@ 新建 pkg/new.md
<<<<<<< 内容
# 标题
=======
{不展开}
>>>>>>> 新文

#改法 e2
@@ 改 pkg/b.py
<<<<<<< 原文
y = 1
=======
>>>>>>> 新文
#改法 e1
@@ 改 pkg/c.py
<<<<<<< 原文
z = 1
=======
z = 2
>>>>>>> 新文

#清单
改 pkg/a.py:f
- 新建 `pkg/new.md`
删 pkg/old.py
随便一行说明
提示 先改 f 再补文档
"""


def test_sections(tmp):
    print("一、#改法 / #清单 段")
    out, eng, _ = run(EDIT)
    e1, e2 = eng.vars.get("e1"), eng.vars.get("e2")
    check(out == "pkg/a.py", f"段拿出来以后主脚本照常跑，{{e1.edits.0.file}} 取得到：{out!r}")
    check(e1 and [x["file"] for x in e1["edits"]] == ["pkg/a.py", "pkg/a.py", "pkg/c.py"],
          f"一个 @@ 改 下连写两对、同名段合并：{e1 and [x['file'] for x in e1['edits']]}")
    check(e1["edits"][0] == {"file": "pkg/a.py", "old": "def f(x):\n    return {x}  # 注释",
                             "new": "def f(x):\n    return x + 1"},
          f"原文/新文按字面（缩进、{{x}}、# 都不动）：{e1['edits'][0]!r}")
    check(e1["files"] == [{"file": "pkg/new.md", "content": "# 标题\n=======\n{不展开}\n"}],
          f"@@ 新建 的内容整份照抄（含 ======= 行），末尾补换行：{e1['files']!r}")
    check(e2 == {"edits": [{"file": "pkg/b.py", "old": "y = 1", "new": ""}]}, f"新文可以为空（删掉原文），没有 files 键：{e2!r}")
    check(eng.checklist == {"items": [["改", "pkg/a.py", "f"], ["新建", "pkg/new.md", ""], ["删", "pkg/old.py", ""]],
                            "hint": "先改 f 再补文档"}, f"#清单 → engine.checklist：{eng.checklist}")
    out, eng, _ = run("打印 甲")
    check(eng.checklist is None and "e1" not in eng.vars, "没写段时 checklist 是 None、不多变量")

    crlf = EDIT.replace("\n", "\r\n")
    out, eng, _ = run(crlf)
    check(out == "pkg/a.py" and eng.vars["e1"]["edits"][0]["old"] == "def f(x):\n    return {x}  # 注释",
          "CRLF 的脚本：段内文本里不带 \\r")

    rest, edits, cl, probs = split_sections("打印 1\n#改法 a\n@@ 改 x.py\n<<<<<<< 原文\nq\n=======\nw\n>>>>>>> 新文\n"
                                            "#子脚本 s.zs\n打印 2")
    check(rest.split("\n") == ["打印 1", "", "", "", "", "", "", "", "#子脚本 s.zs", "打印 2"] and not probs,
          f"段换成空行（行号不变），#子脚本 标题结束段、后面的行留着：{rest!r}")

    out, eng, _ = run("终止 成功 好\n#改法 e1\n@@ 改 a.py\n<<<<<<< 原文\nx\n=======\ny\n>>>>>>> 新文")
    check(eng.halted == {"status": "成功", "reason": "好", "at": "第 1 行"}, f"带段的脚本照常 终止：{eng.halted}")

    def err(script):
        out, _, _ = run("打印 甲\n" + script)
        return out
    o = err("#改法 e1\n@@ 改 a.py\n<<<<<<< 原文\nx\n=======\ny\n>>>>>>> 新文\n打印 段后面的语句")
    check(o.startswith("DSLError") and "第 9 行" in o and "认不出" in o and "甲" not in o,
          f"段后面写语句：运行前就报（不会被静悄悄吞掉），行号对：{o}")
    o = err("#改法 e1\n@@ 改 a.py\n<<<<<<< 原文\nx\n>>>>>>> 新文")
    check("缺 =======" in o, f"缺 =======：{o}")
    o = err("#改法 e1\n@@ 改 a.py\n<<<<<<< 原文\nx\n=======\ny")
    check("缺结尾的 >>>>>>>" in o, f"缺 >>>>>>>：{o}")
    o = err("#改法 e1\n<<<<<<< 原文\nx\n=======\ny\n>>>>>>> 新文")
    check("前面缺「@@ 改 文件」" in o, f"<<<<<<< 前没有 @@：{o}")
    o = err("#改法 e1\n@@ 改 a.py\n@@ 改 b.py\n<<<<<<< 原文\nx\n=======\ny\n>>>>>>> 新文")
    check("第 3 行" in o and "下面没有 <<<<<<< 块" in o, f"@@ 下面没写块：{o}")
    o = err("#改法 e1\n@@ 改 a.py\n<<<<<<< 原文\n\n=======\ny\n>>>>>>> 新文")
    check("原文是空的" in o, f"@@ 改 的原文为空：{o}")

    sub = tmp / "sub.zs"
    sub.write_text("返回 {s1.edits.0.new}\n#改法 s1\n@@ 改 a.py\n<<<<<<< 原文\nx\n=======\n子脚本的\n>>>>>>> 新文\n",
                   encoding="utf-8")
    out, eng, _ = run("设 r = 执行 sub.zs\n打印 {r}|{s1 或 无}", workdir=tmp)
    check(out == "子脚本的|无", f"子脚本自己的段只在子脚本里：{out!r}")


def test_budget(tmp):
    print("二、预算")
    out, eng, m = run("预算 调用 2\n问 a = x\n打印 {a}\n问 b = y\n问 c = z\n打印 不该到这")
    check(out.endswith("[终止] 超出预期：预算用完：模型调用已用 2 次，上限 2 次，第 3 次没有发出（停在 第 5 行）")
          and "不该" not in out and len(m.calls) == 2, f"第 3 次调用不发出，按 终止 超出预期 结束：{out!r} calls={len(m.calls)}")
    check(eng.halted and eng.halted["status"] == "超出预期" and eng.halted["reason"].startswith("预算用完："),
          f"engine.halted：{eng.halted}")
    out, eng, m = run("预算 调用 2\n问 a = x\n问 b = y\n打印 够用")
    check(out == "够用" and eng.halted is None, f"刚好用完不算超：{out!r}")
    out, eng, m = run("设 n = 1\n预算 调用 {n} 秒 60\n问 a = x\n问 b = y")
    check(eng.halted and "上限 1 次" in eng.halted["reason"], f"次数可以是变量，两项都写：{eng.halted}")
    out, eng, m = run("预算 调用 1\n预算 调用 3\n问 a = x\n问 b = y\n打印 好")
    check(out == "好", f"再写一次覆盖：{out!r}")
    out, eng, m = run("问 a = x\n问 b = y\n预算 调用 1\n打印 不该")
    check(eng.halted and eng.halted["at"] == "第 4 行" and "已用 2 次" in eng.halted["reason"],
          f"预算前已经用超的，下一条语句就停：{eng.halted}")
    out, eng, m = run("问 a = x\n打印 {a}")
    check(out == "嗯" and eng.usage.calls == 1 and not eng.usage.limited, "不写预算照常，引擎照样计数")

    def slow(p, s=None):
        time.sleep(0.6)
        return "慢"
    t0 = time.time()
    out, eng, m = run("预算 秒 1\n重复 5 次 计数 i\n  问 a = 第{i}次\n结束\n打印 不该", handler=slow)
    check(eng.halted and "上限 1 秒" in eng.halted["reason"] and len(m.calls) == 2 and time.time() - t0 < 2.5,
          f"秒数用完下一条语句就停：{eng.halted} calls={len(m.calls)}")

    for bad, want in (("预算", "写法"), ("预算 调用 x", "「调用」后面是「x」"), ("预算 次数 3", "写法"),
                      ("预算 调用 1 调用 2", "写法"), ("预算 秒 0", "「秒」后面是「0」")):
        out, _, _ = run(f"打印 甲\n如果 1 等于 2\n  {bad}\n结束")
        check(out.startswith("DSLError: 第 3 行") and want in out and "甲" not in out,
              f"「{bad}」在没走到的分支里也运行前就报：{out}")
    out, _, _ = run("设 n = 0\n预算 调用 {n}")
    check("要是正整数" in out, f"变量展开后不是正整数报错：{out}")

    # 派任务：重答也算一次
    bad = lambda p, s=None: "不是JSON"   # noqa: E731
    out, eng, m = run("用包 common\n预算 调用 1\n设 r = 派任务 做事\n打印 不该", handler=bad)
    check(eng.halted and eng.halted["at"] == "第 3 行" and len(m.calls) == 1,
          f"派任务的重答撞上预算：停在派任务那行，不当成子任务失败：{eng.halted} calls={len(m.calls)}")
    ok = lambda p, s=None: json.dumps({"result": "好", "status": "成功", "reason": ""}, ensure_ascii=False)  # noqa: E731
    out, eng, m = run("用包 common\n预算 调用 2\n设 rs = 并行派任务 [\"甲\",\"乙\",\"丙\"] 3\n打印 不该", handler=ok)
    check(eng.halted and "预算用完" in eng.halted["reason"] and len(m.calls) == 2 and "不该" not in out,
          f"并行派任务里撞上预算整组结束：{eng.halted} calls={len(m.calls)}")
    out, eng, m = run("用包 common\n预算 调用 3\n设 rs = 并行派任务 [\"甲\",\"乙\",\"丙\"] 3\n打印 {rs.2.result}", handler=ok)
    check(out == "好" and len(m.calls) == 3, f"够用时并行派任务照常：{out!r}")

    (tmp / "sub2.zs").write_text("问 a = 子1\n问 b = 子2\n返回 子脚本跑完\n", encoding="utf-8")
    out, eng, m = run("预算 调用 2\n问 a = 主\n设 r = 执行 sub2.zs\n打印 子脚本交回 {r.status}\n打印 不该", workdir=tmp)
    check(eng.halted and eng.halted["at"] == "第 4 行" and "第 3 次没有发出" in eng.halted["reason"]
          and len(m.calls) == 2 and "子脚本交回" not in out,
          f"子脚本的调用算进同一份预算；子脚本里用完，回到调用方下一条也停：{eng.halted} {out!r}")
    out, eng, m = run("预算 调用 3\n问 a = 主\n设 r = 执行 sub2.zs\n打印 {r}", workdir=tmp)
    check(out == "子脚本跑完" and len(m.calls) == 3, f"够用时子脚本照常：{out!r}")

    script = "预算 调用 1\n问 a = x\n问 b = y"
    _, eng, m = run(script)
    first = dict(eng.halted or {})
    out, eng, _ = run(script, eng=eng)
    check(first and eng.halted == first and eng.usage.calls == 1, f"同一个引擎再跑一次，用量重新计：{eng.halted}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="dsl_edit_budget_"))
    try:
        test_sections(tmp)
        test_budget(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
