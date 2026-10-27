# -*- coding: utf-8 -*-
"""K84：v2 改法检查的整份重写缺口（K83 诊断的复现 A/B/C/D 做成回归）。不调模型。

- A：先 删文件 再 改文件 old=""（整份新建）→ 静态检查放行，运行期写成新内容；删写在改之后仍报「已存在」
- B / C：#改法 段只写 {file, content} → 归入 files；写文件 {e2} 或 设 w2.files = {e2} 再 写文件 {w2}，检查通过、运行期覆盖成功
- D：old = 整个原文（文档写法）照旧通过
- 写文件 覆盖 CRLF 文件保持 CRLF，新文件 LF；报错提示给两条走得通的写法

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_k84.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_k84_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ.pop("DSLAGENT_RULES", None)
(TMP / "state").mkdir()

from tools.dsl_sections import split_sections      # noqa: E402
from tools.dslagent import dslcheck as DC           # noqa: E402
from tools.dslagent import plan as P                # noqa: E402
from tools.dslagent import v2 as V                  # noqa: E402
from tools.dslagent.engine import AgentEngine       # noqa: E402
from tools.mock import MockClient                   # noqa: E402

passed = failed = 0

OLD = "业务 m\n  依赖 account\n  公开 函数 f a\n    返回 {a}\n  结束\n"
NEW = "业务 m\n  依赖 account subject\n  公开 函数 f a subject?\n    返回 {a}\n  结束\n"
J_OLD = OLD.replace("\n", "\\n")
J_NEW = NEW.replace("\n", "\\n")
HEAD = "用包 common text code\n预算 调用 3 秒 60\n"


def check(ok, msg, got=None):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or got is None else f"：{got}"))


def project(name, files=None):
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    for rel, text in (files or {"services/m.zs": OLD, "services/k.zs": "业务 k\n"}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        with open(d / rel, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return d


def run(proj, script):
    """真跑一遍计划（引擎 + code 包），返回引擎变量。"""
    eng = AgentEngine(client=MockClient(handler=lambda p, s=None: "嗯", offline=True), workdir=proj, verbose=False,
                      verbs_root=P.PKG / "verbs")
    eng.run(script)
    return eng.vars


def read(proj, rel):
    return (proj / rel).read_bytes().decode("utf-8")


def sec_edit(old):
    return '#改法 e2\n[\n{"file":"services/m.zs","old":"%s","new":"%s"}\n]\n' % (old, J_NEW)


SEC_CONTENT = '#改法 e2\n[\n{"file":"services/m.zs","content":"%s"}\n]\n' % J_NEW


def test_parse():
    print("一、JSON 段：只有 {file, content} 的条目进 files")
    _, secs, _, probs = split_sections(SEC_CONTENT)
    check(probs == [] and secs["e2"] == {"files": [{"file": "services/m.zs", "content": NEW}]}, "{file, content} → files", secs)
    _, secs, _, _ = split_sections('#改法 e2\n[\n{"file":"a.zs","old":"x","new":"y"},\n{"file":"b.zs","content":"z"}\n]\n')
    check(secs["e2"] == {"edits": [{"file": "a.zs", "old": "x", "new": "y"}], "files": [{"file": "b.zs", "content": "z"}]},
          "混写：old/new 进 edits，{file, content} 进 files", secs)
    _, secs, _, _ = split_sections('#改法 e2\n[\n{"file":"a.zs","old":"x","new":"y","content":"z"}\n]\n')
    check(list(secs["e2"]) == ["edits"], "带 old/new 的（哪怕也有 content）仍是 edits", secs)


def test_delete_then_create():
    print("二、A：删文件 在前、改文件 old 为空新建")
    p = project("a")
    plan = HEAD + "设 dr = 删文件 services/m.zs\n设 res = 改文件 {e2}\n" + sec_edit("")
    pr = DC.edit_problems(p, plan)
    check(pr == [], "静态检查放行（删在前）", pr)
    v = run(p, plan)
    check(v["res"]["ok"] == "是" and read(p, "services/m.zs") == NEW, "运行期：删后新建，内容是新的", v.get("res"))
    p = project("a2")
    pr = DC.edit_problems(p, HEAD + "设 res = 改文件 {e2}\n设 dr = 删文件 services/m.zs\n" + sec_edit(""))
    check(len(pr) == 1 and "已存在" in pr[0] and "old 不能为空" in pr[0], "删文件 写在 改文件 之后：仍报已存在", pr)
    pr = DC.edit_problems(p, HEAD + "设 dr = 删文件 services/k.zs\n设 res = 改文件 {e2}\n" + sec_edit(""))
    check(len(pr) == 1 and "已存在" in pr[0], "删的是别的文件：不放行", pr)
    pr = DC.edit_problems(p, HEAD + "设 dr = 删文件 services/m.zs\n设 res = 改文件 {e2}\n" + sec_edit(J_OLD))
    check(len(pr) == 1 and "没有这个文件" in pr[0] and "删文件" in pr[0], "删后又按原文改：报没有这个文件", pr)
    pr = DC.edit_problems(p, HEAD + "设 res = 改文件 {e2}\n" + sec_edit(""))
    check(len(pr) == 1 and "old 取整个原文" in pr[0] and "{file, content}" in pr[0] and "写文件" in pr[0],
          "提示给两条走得通的写法（old 取整个原文；{file, content} + 写文件）", pr)
    check(p.joinpath("services/m.zs").read_text(encoding="utf-8") == OLD, "检查只读，没动文件")
    problem, *_ = V.check(p, TMP / "dry_a", HEAD + "设 dr = 删文件 services/m.zs\n设 res = 改文件 {e2}\n终止 成功 好\n"
                          + sec_edit("") + "#清单\n改 services/m.zs\n", "整份重写 m")
    check(problem == "", "v2.check（静态 + 空跑）整体通过", problem)


def test_write_content():
    print("三、B / C：{file, content} + 写文件 整份覆盖")
    for tag, body in (("B", "设 w2.files = {e2}\n设 res = 写文件 {w2}\n"), ("C", "设 res = 写文件 {e2}\n")):
        p = project("bc_" + tag)
        plan = HEAD + body + SEC_CONTENT
        pr = DC.edit_problems(p, plan)
        check(pr == [], f"{tag}：静态检查通过（覆盖已有文件允许）", pr)
        v = run(p, plan)
        check(v["res"]["ok"] == "是" and "覆盖" in v["res"]["msg"] and read(p, "services/m.zs") == NEW,
              f"{tag}：运行期写入成功", v.get("res"))
        problem, *_ = V.check(p, TMP / f"dry_{tag}", HEAD + body + "终止 成功 好\n" + SEC_CONTENT + "#清单\n改 services/m.zs\n",
                              "整份重写 m")
        check(problem == "", f"{tag}：v2.check（静态 + 空跑）整体通过", problem)
    p = project("bc_x")
    pr = DC.edit_problems(p, HEAD + "设 res = 改文件 {e2}\n" + SEC_CONTENT)
    check(len(pr) == 1 and "已存在" in pr[0] and "写文件" in pr[0], "{file, content} 交给 改文件 覆盖已有：报已存在并指向 写文件", pr)
    pr = DC.edit_problems(p, HEAD + "设 res = 写文件 {e2}\n"
                          + '#改法 e2\n[\n{"file":"services/m.zs","old":"业务 m\\n","new":"业务 m\\n","content":"%s"}\n]\n' % J_NEW)
    check(len(pr) == 1 and "写文件 只收" in pr[0], "old==new 占位 + content 交给 写文件：明确报只收 {file, content}", pr)
    v = run(p, HEAD + "设 res = 写文件 {e2}\n" + sec_edit(J_OLD))
    check(v["res"]["ok"] == "否" and "改文件" in v["res"]["msg"] and read(p, "services/m.zs") == OLD,
          "运行期 写文件 收到 old/new 改法：报错指向 改文件、不写", v.get("res"))
    pr = DC.edit_problems(p, HEAD + "设 res = 写文件 {e2}\n" + '#改法 e2\n[\n{"file":"tests/test_x.py","content":"x"}\n]\n')
    check(len(pr) == 1 and "测试文件" in pr[0], "写文件 段照查测试文件", pr)
    pr = DC.edit_problems(p, HEAD + "设 res = 写文件 {e2}\n" + '#改法 e2\n[\n{"file":"../out.zs","content":"x"}\n]\n')
    check(len(pr) == 1 and "out.zs" in pr[0], "写文件 段照查越界路径", pr)


def test_doc_way():
    print("四、D：old = 整个原文（文档写法）")
    p = project("d")
    plan = HEAD + "设 res = 改文件 {e2}\n" + sec_edit(J_OLD)
    pr = DC.edit_problems(p, plan)
    check(pr == [], "静态检查通过", pr)
    v = run(p, plan)
    check(v["res"]["ok"] == "是" and read(p, "services/m.zs") == NEW, "运行期改成新内容", v.get("res"))


def test_crlf():
    print("五、写文件 保持换行")
    p = project("crlf", {"services/m.zs": OLD.replace("\n", "\r\n")})
    v = run(p, HEAD + "设 res = 写文件 {e2}\n" + SEC_CONTENT + '\n')
    check(v["res"]["ok"] == "是" and (p / "services/m.zs").read_bytes() == NEW.replace("\n", "\r\n").encode("utf-8"),
          "原文件 CRLF：覆盖后仍是 CRLF", (p / "services/m.zs").read_bytes()[:60])
    v = run(p, HEAD + "设 res = 写文件 {e2}\n" + '#改法 e2\n[\n{"file":"services/n.zs","content":"%s"}\n]\n' % J_NEW)
    check(v["res"]["ok"] == "是" and (p / "services/n.zs").read_bytes() == NEW.encode("utf-8"), "新文件按内容原样（LF）",
          (p / "services/n.zs").read_bytes()[:60])
    q = project("lf")
    run(q, HEAD + "设 res = 写文件 {e2}\n" + SEC_CONTENT)
    check(b"\r" not in (q / "services/m.zs").read_bytes(), "原文件 LF：覆盖后仍是 LF")


def main():
    try:
        test_parse()
        test_delete_then_create()
        test_write_content()
        test_doc_way()
        test_crlf()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
