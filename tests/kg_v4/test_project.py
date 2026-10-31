# -*- coding: utf-8 -*-
"""kg_v4 项目级最小检查：约定检查、全量回归、编译、数据初始化脚本。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_project.py

拷一份 kg_v4（不带 app.db / web / uploads）到临时目录再检查，不动仓库里的文件。离线，不调模型。
  一、17 个模块的约定检查 + 全局检查 + 加载检查 + 跨模块调用核对（xcall，见 test_xcall.py）
  二、全量回归（每个模块的约定用例在临时库上跑）17/17
  三、gen build：112 个接口（K159 退出接口带上动作 auth_logout 后 +1）
  四、setup/init_data.py：用裁小的单词表（200 条）+ 仓库题库灌一遍，各类条数对；
      再跑一次，已有数据全部跳过、条数不变
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "kg_v4"
sys.path.insert(0, str(ROOT))

passed = failed = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {detail}"))


NAMES = ("subject kg lesson progress account quiz vocab dictation teacher_rules tutor report textbook_import "
         "assist_common assist_kg assist_setting assist_draft assist_file assist_material assist_insight teacher_assist").split()
tmp = Path(tempfile.mkdtemp(prefix="kg_v4_test_"))
proj = tmp / "kg_v4"
shutil.copytree(SRC, proj, ignore=shutil.ignore_patterns("app.db", "web", "uploads", "sessions", ".auth_secret", "__pycache__"))
try:
    print("一、约定检查")
    from tools.dslagent import loadcheck
    from tools.dslagent.packs.dslproj import contract as C
    from tools.dslagent.v3 import globalcheck, top as vtop

    mods, probs = {}, []
    for n in NAMES:
        c, p = C.parse((proj / "contracts" / f"{n}.md").read_text(encoding="utf-8"))
        mods[n] = c
        probs += [f"[{n}] {x}" for x in p]
    for n in NAMES:
        c = mods[n]
        probs += [f"[{n}] {x}" for x in C.check(c, n, {d: mods[d] for d in c["依赖"] if d in mods}, NAMES)]
    check(not probs, f"{len(NAMES)} 个模块的约定检查通过", probs[:3])
    tp, tprobs = vtop.parse((proj / "plan" / "top.zs").read_text(encoding="utf-8"))
    check(not tprobs, "plan/top.zs 能解析", tprobs)
    gp = globalcheck.check(str(proj), tp)
    check(not (gp.get("条数", 0) if isinstance(gp, dict) else len(gp)), "全局检查 0 重复", gp)
    lp = loadcheck.check_project(str(proj), scripts=True)
    check(not lp, "加载检查 0 问题", lp[:3])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_xcall                       # 跨模块调用参数名核对（常驻；K79 固化）
    xr = test_xcall.run_xcall(proj)
    xbad = [f"[{c}] {w}: {m}" for c, w, m in xr["跨模块不一致"] + xr["模块内疑点"]] + xr["top问题"] + xr["提供未列"]
    check(not xbad, f"跨模块调用核对（xcall）{xr['总数']} 处 0 不一致", xbad[:3])

    print("二、全量回归")
    from tools.dslagent.v3 import regress as R
    fails = []
    for n in NAMES:
        ok, why = R._accept_module(str(proj), n, NAMES)
        if not ok:
            fails.append((n, str(why)[:200]))
    check(not fails, f"全量回归 {len(NAMES) - len(fails)}/{len(NAMES)}", fails)

    print("三、编译")
    r = subprocess.run([sys.executable, "-m", "gen", "build", str(proj)], cwd=ROOT, capture_output=True, text=True)
    check(r.returncode == 0 and "112 个接口" in r.stdout, "gen build：112 个接口", (r.stdout + r.stderr)[-300:])

    print("四、数据初始化脚本")
    content = tmp / "content"
    shutil.copytree(ROOT / "kg" / "content", content, ignore=shutil.ignore_patterns("translate", "series"))
    for f in ("words.jsonl", "words_jlpt.jsonl"):
        lines = (content / f).read_text(encoding="utf-8").splitlines()[:100]
        (content / f).write_text("\n".join(lines) + "\n", encoding="utf-8")
    quiz = ROOT / "workspace" / "japanese" / "content" / "bunpou" / "题库"
    cmd = [sys.executable, str(SRC / "setup" / "init_data.py"), str(proj), "--content", str(content), "--quiz", str(quiz)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    import sqlite3

    def counts():
        con = sqlite3.connect(proj / "app.db")
        try:
            return {t: con.execute(f"select count(*) from {t}").fetchone()[0]
                    for t in ("kg_point", "kg_edge", "kg_item", "kg_contrast", "lesson_text", "vocab_word", "quiz_question")}
        finally:
            con.close()
    c1 = counts() if (proj / "app.db").is_file() else {}
    check(r.returncode == 0 and c1 == {"kg_point": 69, "kg_edge": 112, "kg_item": 192, "kg_contrast": 20,
                                      "lesson_text": 125, "vocab_word": 200, "quiz_question": 466},
          "初始化：69/112/192/20/125 课/200 词/466 题", (c1, r.stdout[-300:], r.stderr[-300:]))
    def subj():
        con = sqlite3.connect(proj / "app.db")
        try:
            return (con.execute("select id, code, visibility, status from subject_info").fetchall(),
                    con.execute("select count(*) from subject_student").fetchone()[0],
                    con.execute("select count(*) from subject_teacher").fetchone()[0])
        finally:
            con.close()
    s1 = subj() if (proj / "app.db").is_file() else None
    check(s1 is not None and s1[0] == [(1, "jp_grammar", "public", "active")],
          "初始化：建好 1 号科目（日语语法，公共，启用）", s1)
    r2 = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    check(r2.returncode == 0 and r2.stdout.count("已有数据，跳过") == 7 and counts() == c1,
          "再跑一次：7 类全部跳过、条数不变", r2.stdout[-300:])
    check(subj() == s1, "再跑一次：科目、登记行数不变（幂等）", (s1, subj()))
    r3 = subprocess.run(cmd[:2] + ["/nonexistent"], capture_output=True, text=True)
    check(r3.returncode == 2, "项目目录不对：退出码 2")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
