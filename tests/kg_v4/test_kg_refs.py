#!/usr/bin/env python
# -*- coding: utf-8 -*-
# kg_v4 整库引用保护测试（K99b）。只按约定写、不看实现（K99b 的规矩）：
# 在 init_data 灌出来的整库（日语数据）上，按 K98 约定调 kg 的公开函数做删除，核对——
#   1) 被引用的知识点/条目：409，报错原文以约定前缀开头，整库一行不动；
#   2) 无引用的知识点/条目：可删，前置边、对照随删；
#   3) 别的科目的编号：404（当不存在）。
#
#     cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_kg_refs.py
#
# 实现没合并时（services/kg.zs 里还没有 删知识点/删条目 等函数），逐项打
# 「待实现」并退出码 0——脚本本身要能跑、不给实现背锅；实现合并后这些项
# 全部变成真断言，缺函数仍打待实现、别的失败照样算失败。
# 环境：拷 kg_v4 到临时目录（不带 app.db/web/uploads）→ init_data 灌库（裁小的
# 单词表 + 仓库题库，同 test_project 口径）→ 直接补跨科目行和作答/掌握/得分/
# 默写记录 → DSL 引擎进程内调公开函数 → 结束删临时目录。
# 离线，不调模型，不起服务，不碰仓库里的文件。
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
REPO_PY = REPO / ".venv" / "bin" / "python"
SRC = REPO / "kg_v4"
sys.path.insert(0, str(REPO))

from tools.dslagent.packs.dslproj import cases as K  # noqa: E402

passed = failed = pend = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
        print("  OK " + msg)
    else:
        failed += 1
        print("  XX " + msg + ("" if detail is None else "\n      " + str(detail)[:400]))


def todo(msg, why=""):
    global pend
    pend += 1
    print("  -- 待实现 " + msg + ("" if not why else "（" + str(why)[:160] + "）"))


# 引用保护快照要盖住的表：kg 自己的 + K98 约定 §4 列的全部下游表
TABLES = ("kg_point", "kg_edge", "kg_item", "kg_contrast",
          "lesson_point_link", "lesson_item_link", "vocab_word", "quiz_question",
          "progress_answer", "progress_mastery", "progress_score", "dictation_progress")

NOW = "2026-01-01 09:00:00"
tmp = Path(tempfile.mkdtemp(prefix="kg_refs_"))
try:
    ws = tmp / "kg_v4"
    shutil.copytree(SRC, ws, ignore=K.COPY_IGNORE, symlinks=True)
    content = tmp / "content"
    shutil.copytree(REPO / "kg" / "content", content,
                    ignore=shutil.ignore_patterns("translate", "series"))
    for f in ("words.jsonl", "words_jlpt.jsonl"):
        p = content / f
        lines = p.read_text(encoding="utf-8").splitlines()[:100]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    quiz = REPO / "workspace" / "japanese" / "content" / "bunpou" / "题库"
    r = subprocess.run([str(REPO_PY), str(SRC / "setup" / "init_data.py"), str(ws),
                        "--content", str(content), "--quiz", str(quiz)],
                       cwd=REPO, capture_output=True, text=True)
    check(r.returncode == 0, "init_data 灌库成功", (r.stdout + r.stderr)[-400:])
    db = ws / "app.db"

    con = sqlite3.connect(db)
    # 挑「最被引用」的知识点/条目：种子固定（69 点/112 边/192 条目/129 课文条目挂接/
    # 200 词/466 题），按阻断引用计数从大到小挑。下挂条目、题目基本必有，单词、
    # 课文挂接有多少算多少（断言只依赖「至少有一个阻断引用」）。
    prow = con.execute(
        "select p.code,"
        " (select count(*) from kg_item i where i.point_code=p.code) as items,"
        " (select count(*) from vocab_word w where w.point_code=p.code) as words,"
        " (select count(*) from lesson_point_link l where l.point_code=p.code) as links"
        " from kg_point p where p.subject_id=1"
        " order by items+words+links desc, p.id limit 1").fetchone()
    P_REF, n_items, n_words, n_links = prow
    check(n_items >= 1, "挑中的知识点 %s 有下挂条目（%d 条目/%d 词/%d 课文挂接）" % prow, prow)
    irow = con.execute(
        "select i.code,"
        " (select count(*) from quiz_question q where q.item_code=i.code) as qs,"
        " (select count(*) from lesson_item_link l where l.item_code=i.code) as links,"
        " (select count(*) from kg_item n where n.prev_code=i.code) as nxt"
        " from kg_item i where i.subject_id=1"
        " order by qs+links+nxt desc, i.id limit 1").fetchone()
    I_REF, n_q, n_il, n_nx = irow
    check(n_q >= 1, "挑中的条目 %s 有题目（%d 题/%d 课文挂接/%d 后一个）" % irow, irow)

    # 自己造学习记录（init_data 不灌学习记录；「学习记录从不清」→ 它们必须挡删）
    con.execute("insert into progress_answer(learner,point_code,question_no,correct,answer,at,subject_id)"
                " values('k99b',?,'K99B-1',1,'',?,1)", (P_REF, NOW))
    con.execute("insert into progress_mastery(learner,point_code,right_count,total_count,"
                "mastered,updated_at,subject_id) values('k99b',?,1,2,0,?,1)", (P_REF, NOW))
    con.execute("insert into progress_score(learner,point_code,score,at,subject_id)"
                " values('k99b',?,0,?,1)", (P_REF, NOW))
    con.execute("insert into dictation_progress(learner,direction,level,source,current_word_id,"
                "answered,hinted,asked_ids,asked_count,right_count,round_start,subject_id)"
                " values('k99b','zh2jp','',?,0,0,0,'',0,0,0,1)", (P_REF,))
    # 单词挡删：单词挂在知识点上（种子有 200 词、分在几个点），挑最多两个
    # 别的、有单词的知识点各删一次，核对 409 且明细含「单词」。
    word_pts = [r0 for (r0,) in con.execute(
        "select distinct point_code from vocab_word where subject_id=1 and point_code<>''"
        " and point_code<>? order by point_code limit 2", (P_REF,)).fetchall()]
    # 跨科目：2 号科目 + 它自己的知识点/条目（日语数据全在 1 号，这里手工补一行）
    con.execute("insert into subject_info(code,name,intro,kind,caps,levels,qtypes,visibility,"
                "owner,status,created_at,updated_at) values('k99x','引用保护二号科目','',"
                "'language','','','','public','t1','active',?,?)", (NOW, NOW))
    con.execute("insert into kg_point(code,title,subject_id) values('other.p','别的科目的点',2)")
    con.execute("insert into kg_item(code,name,point_code,after_form,prev_code,subject_id)"
                " values('other.i','别的科目的条目','other.p','','',2)")
    con.commit()
    con.close()

    def snap():
        cn = sqlite3.connect(db)
        try:
            return {t: sorted(map(repr, cn.execute("select * from " + t))) for t in TABLES}
        finally:
            cn.close()

    os.environ.setdefault("DSL_NOW", K.DEFAULT_NOW)
    eng = K.make_engine(ws)
    tag = [0]

    def call_fn(fn_name, **args):
        # 调 kg 公开函数 → ("ok", r) / ("err", err) / ("missing", 说明) / ("fail", 说明)
        # 形参不能叫 name：建条目的入参里也有 name，关键字撞车
        tag[0] += 1
        try:
            r, err = K.call(eng, "kg", fn_name, args, "t%d" % tag[0])
            K.settle()
        except Exception as e:  # noqa: BLE001
            m = str(e)
            if "里没有函数" in m or "没有业务模块" in m:
                return ("missing", m)
            return ("fail", type(e).__name__ + ": " + m[:400])
        if err not in ("", None):
            return ("err", err)
        return ("ok", r)

    def step(fn, label, **args):
        kind, got = call_fn(fn, **args)
        if kind == "missing":
            todo(label, "services/kg.zs 还没有 " + fn)
        elif kind == "fail":
            check(False, label, got)
        return kind, got

    def expect_block(fn, code, want, prefix, label):
        # 期望被拒（409/404）：核对状态码和报错原文前缀
        kind, got = step(fn, label, code=code)
        if kind not in ("ok", "err"):
            return None
        if kind == "ok":
            check(False, label, "应该报错 %s，实际成功返回 %r" % (want, got))
            return None
        err = got
        gcode = err.get("code") if isinstance(err, dict) else None
        gmsg = str(err.get("error", "")) if isinstance(err, dict) else str(err)
        check(str(gcode) == str(want) and gmsg.startswith(prefix),
              "%s：%s 且原文以「%s」开头" % (label, want, prefix), "实际 %r" % (err,))
        return gmsg

    print("一、被引用的拒绝删（409 + 原文前缀 + 整库不动）")
    before = snap()
    msg = expect_block("删知识点", P_REF, 409, "知识点还被引用，不能删除",
                       "删被引用的知识点 %s" % P_REF)
    if msg is not None:
        check("下挂条目" in msg, "409 明细含「下挂条目」", msg)
    check(snap() == before, "整库一行没动（知识点 409 后）")
    msg = expect_block("删条目", I_REF, 409, "条目还被引用，不能删除",
                       "删被引用的条目 %s" % I_REF)
    if msg is not None:
        check("题目" in msg, "409 明细含「题目」", msg)
    check(snap() == before, "整库一行没动（条目 409 后）")
    for wp in word_pts:
        msg = expect_block("删知识点", wp, 409, "知识点还被引用，不能删除",
                           "删有单词的知识点 %s" % wp)
        if msg is not None:
            check("单词" in msg, "409 明细含「单词」", msg)
    check(snap() == before, "整库一行没动（单词点 409 后）")

    print("二、无引用的可删（前置边、对照随删）")
    PA, PB, PI = "kgrefs.pa", "kgrefs.pb", "kgrefs.i1"
    k1 = step("建知识点", "建知识点 %s" % PA, code=PA, title="引用保护甲")[0]
    k2 = step("建知识点", "建知识点 %s" % PB, code=PB, title="引用保护乙")[0]
    k3 = step("加前置边", "加前置边 %s→%s" % (PA, PB), pre_code=PA, point_code=PB)[0]
    k4 = step("加对照", "加对照 %s~%s" % (PA, PB), a_code=PA, b_code=PB)[0]
    if "missing" not in (k1, k2, k3, k4) and failed == 0:
        kind, got = call_fn("删知识点", code=PA)
        if kind == "ok":
            check(got.get("edges_removed") == 1 and got.get("contrasts_removed") == 1,
                  "删 %s：返回随删计数 前置边1/对照1" % PA, repr(got))
        else:
            check(False, "删 %s 应成功" % PA, repr(got))
        cn = sqlite3.connect(db)
        # 各表各自的列（kg_point 只有 code；三张表不能共用一组列名，会 no such column）
        left = []
        for t, cols in (("kg_point", ("code",)),
                        ("kg_edge", ("pre_code", "point_code")),
                        ("kg_contrast", ("a_code", "b_code"))):
            sql = "select count(*) from " + t + " where " + " or ".join(c + "=?" for c in cols)
            n = cn.execute(sql, (PA,) * len(cols)).fetchone()[0]
            if n:
                left.append((t, n))
        keep = cn.execute("select count(*) from kg_point where code=?", (PB,)).fetchone()[0]
        cn.close()
        check(not left and keep == 1, "%s 删干净（前置边、对照随删），%s 还在" % (PA, PB), left)
        kind, got = call_fn("删知识点", code=PB)
        check(kind == "ok", "删 %s（已无边和对照）应成功" % PB,
              repr(got) if kind != "ok" else None)
        # 条目要挂在一个活着的点上：PB 刚删掉，另建一个 PC 挂它（挂 PB 会 404，后面全空转）
        PC = "kgrefs.pc"
        k4b = step("建知识点", "建知识点 %s（挂条目用）" % PC, code=PC, title="引用保护丙")[0]
        k5 = step("建条目", "建条目 %s 挂 %s" % (PI, PC), code=PI, name="引用保护条目",
                  point_code=PC)[0]
        k6 = step("加对照", "加对照 %s~%s" % (PI, PC), a_code=PI, b_code=PC)[0]
        if "missing" not in (k5, k6) and failed == 0:
            kind, got = call_fn("删条目", code=PI)
            if kind == "ok":
                check(got.get("contrasts_removed") == 1, "删条目 %s：对照随删（计数1）" % PI, repr(got))
            else:
                check(False, "删条目 %s 应成功" % PI, repr(got))
            cn = sqlite3.connect(db)
            gone = all(cn.execute(
                "select count(*) from " + t + " where " +
                " or ".join(c + "=?" for c in cols), (PI,) * len(cols)).fetchone()[0] == 0
                for t, cols in (("kg_item", ("code",)), ("kg_contrast", ("a_code", "b_code"))))
            cn.close()
            check(gone, "%s 删干净（对照随删）" % PI)

    print("三、跨科目：别的科目的编号当不存在（404）")
    expect_block("删知识点", "other.p", 404, "没有这个知识点", "删 2 号科目的知识点 other.p")
    expect_block("删条目", "other.i", 404, "没有这个条目", "删 2 号科目的条目 other.i")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n通过 %d，失败 %d，待实现 %d" % (passed, failed, pend))
if failed:
    sys.exit(1)
if pend:
    print("（待实现 = 约定已定、实现未合并，不算失败；实现合并后自动变成真断言）")
sys.exit(0)
