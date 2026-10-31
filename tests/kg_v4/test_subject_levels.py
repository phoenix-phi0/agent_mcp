#!/usr/bin/env python
# -*- coding: utf-8 -*-
# kg_v4 各科目自定义等级（K161）整库测试：在 init_data 灌出来的整库（日语 1 号科目）上
# 再补一个 Python 类科目（2 号，levels=入门,基础,进阶，没有课文），DSL 引擎进程内调公开函数，核对——
#   1) 日语科目行为不变：做题下拉 全部+N5..N1、「全部」从 N5 出题、学情各等级 5 项按 N5..N1；
#   2) Python 科目：做题下拉是 全部+入门/基础/进阶；「全部」按科目顺序逐级（先插进阶题也先出基础）；
#      题卡抬头显示自定义等级名；等级不在本科目里开始被拒；
#   3) 取知识点等级 / 学情各等级统计在无课文科目按题目等级兜底；
#   4) 导入题库：等级不在本科目等级里整批 400，报错带行号和等级，库不动；
#   5) 改科目：删除在用等级 400 且库不动；新增、调顺序、删没在用的等级可以；
#   6) 新建通用科目默认 入门,基础,进阶；
#   7) 非日语科目教材导入入口关闭（403），日语科目照常过门控。
#
#     cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_subject_levels.py
#
# 环境同 test_kg_refs.py：拷 kg_v4 到临时目录 → init_data 灌库 → 直接补 2 号科目的行 →
# 进程内调函数 → 结束删临时目录。离线，不调模型，不起服务，不碰仓库里的文件。
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

passed = failed = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
        print("  OK " + msg)
    else:
        failed += 1
        print("  XX " + msg + ("" if detail is None else "\n      " + str(detail)[:400]))


NOW = "2026-01-01 09:00:00"
JP = ["N5", "N4", "N3", "N2", "N1"]
PY = ["入门", "基础", "进阶"]
tmp = Path(tempfile.mkdtemp(prefix="subj_levels_"))
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
    jp_levels = con.execute("select levels from subject_info where id=1").fetchone()
    check(jp_levels is not None, "1 号日语科目在库里", jp_levels)
    # 2 号 Python 类科目：通用、没开教材导入、三档等级、没有课文
    con.execute("insert into subject_info(code,name,intro,kind,caps,levels,qtypes,visibility,"
                "owner,status,created_at,updated_at) values('python','Python入门','','general',"
                "'{\"kg\":1,\"quiz\":1,\"progress\":1,\"tutor\":1}','入门,基础,进阶','choice,fill',"
                "'public','t1','active',?,?)", (NOW, NOW))
    sid = con.execute("select id from subject_info where code='python'").fetchone()[0]
    for code, title in (("python.env", "环境"), ("python.list", "列表"), ("python.class", "类")):
        con.execute("insert into kg_point(code,title,subject_id) values(?,?,?)", (code, title, sid))
        con.execute("insert into kg_item(code,name,point_code,after_form,prev_code,subject_id)"
                    " values(?,?,?,'','',?)", (code + "_i", title + "条目", code, sid))
    # 先插进阶题、再插基础题：「全部」若按插入顺序会先出进阶，按科目顺序应先出基础
    for no, lv, item in (("python.q_class_1", "进阶", "python.class_i"),
                         ("python.q_list_1", "基础", "python.list_i"),
                         ("python.q_list_2", "基础", "python.list_i")):
        con.execute("insert into quiz_question(question_no,course,level,category,stem,options,answer,"
                    "accepted,explain,item_code,subject_id) values(?,'',?,'选择','题干','甲^乙','A','','',?,?)",
                    (no, lv, item, sid))
    con.commit()
    py_q_before = con.execute("select count(*) from quiz_question where subject_id=?", (sid,)).fetchone()[0]
    con.close()
    S = str(sid)

    os.environ.setdefault("DSL_NOW", K.DEFAULT_NOW)
    eng = K.make_engine(ws)
    tag = [0]

    def call(mod, fn, **args):
        tag[0] += 1
        try:
            r, err = K.call(eng, mod, fn, args, "t%d" % tag[0])
            K.settle()
        except Exception as e:  # noqa: BLE001
            return None, {"code": "exc", "error": type(e).__name__ + ": " + str(e)[:400]}
        return r, (err or None)

    def q1(sql, *a):
        cn = sqlite3.connect(db)
        try:
            return cn.execute(sql, a).fetchone()
        finally:
            cn.close()

    def opt_values(r):
        return [o.get("value") for o in (r or {}).get("level_options") or []]

    print("一、日语科目行为不变")
    r, err = call("subject", "科目等级", subject_id="1")
    check(err is None and r.get("levels") == JP and r.get("first") == "N5",
          "科目等级（日语）= N5..N1", (r, err))
    r, err = call("quiz", "做题页面", learner="k161j")
    check(err is None and opt_values(r) == ["全部"] + JP, "日语做题下拉：全部+N5..N1", (r, err))
    r, err = call("quiz", "开始页面", learner="k161j", pick_level="全部")
    head = ((r or {}).get("card") or {}).get("head", "")
    check(err is None and head.startswith("N5・"), "日语「全部」从 N5 出题，题卡抬头 N5・…", (head, err))
    check(err is None and opt_values(r) == ["全部"] + JP, "开始页面也回 level_options", opt_values(r))
    r, err = call("progress", "按级统计掌握", learner="k161j")
    lv = [x.get("level") for x in (r or {}).get("levels") or []]
    tot = sum(int(x.get("total") or 0) for x in (r or {}).get("levels") or [])
    check(err is None and lv == JP and str(r.get("level_count")) == "5",
          "日语学情各等级：5 项按 N5..N1", (lv, err))
    check(err is None and int(r.get("covered_count") or 0) > 0 and tot == int(r.get("covered_count")),
          "日语学情：有等级的点 > 0 且各级合计等于 covered_count", (r or {}).get("covered_count"))

    print("二、Python 科目：下拉、逐级、题卡")
    r, err = call("subject", "科目等级", subject_id=S)
    check(err is None and r.get("levels") == PY and r.get("first") == "入门" and r.get("text") == "入门,基础,进阶",
          "科目等级（Python）= 入门,基础,进阶", (r, err))
    r, err = call("quiz", "做题页面", learner="k161p", subject=S)
    check(err is None and opt_values(r) == ["全部"] + PY, "Python 做题下拉：全部+入门/基础/进阶", (r, err))
    r, err = call("quiz", "开始页面", learner="k161p", pick_level="全部", subject=S)
    head = ((r or {}).get("card") or {}).get("head", "")
    check(err is None and head.startswith("基础・"),
          "「全部」按科目顺序逐级：入门没题→先出基础（进阶题先插也不先出）", (head, err))
    check(head == "基础・选择", "题卡抬头显示自定义等级名「基础・选择」", head)
    row = q1("select level, current_no from quiz_progress where learner='k161p' and subject_id=?", sid)
    check(row is not None and row[0] == "基础" and row[1].startswith("python.q_list"),
          "quiz_progress 记的等级是基础", row)
    for fn in ("下一题页面", "判答案页面"):
        args = {"learner": "k161p", "subject": S}
        if fn == "判答案页面":
            args["choice"] = "A"
            r, err = call("quiz", fn, **args)
        else:
            r, err = call("quiz", "判答案页面", learner="k161p", subject=S, choice="A")
            r, err = call("quiz", fn, **args)
        check(err is None and opt_values(r) == ["全部"] + PY, "%s 也回 level_options" % fn, (opt_values(r), err))
    r, err = call("quiz", "开始页面", learner="k161p", pick_level="N5", subject=S)
    check(err is not None and str(err.get("code")) == "400", "Python 科目选 N5 开始：400", (r, err))

    print("三、无课文科目按题目等级兜底")
    r, err = call("lesson", "取知识点等级", point_code="python.class", subject=S)
    check(err is None and r.get("level") == "进阶" and str(r.get("lesson_count")) == "0",
          "取知识点等级（没有课文）：从题目取到进阶，lesson_count 0", (r, err))
    r, err = call("lesson", "取知识点等级", point_code="python.env", subject=S)
    check(err is None and r.get("level") == "", "没有题也没有课的点：等级为空串", (r, err))
    r, err = call("progress", "按级统计掌握", learner="k161z", subject=S)
    lv = [x.get("level") for x in (r or {}).get("levels") or []]
    tl = [int(x.get("total") or 0) for x in (r or {}).get("levels") or []]
    check(err is None and lv == PY and tl == [0, 1, 1] and str(r.get("covered_count")) == "2",
          "学情各等级：3 项按 入门/基础/进阶，总数 0/1/1（题目兜底）", (lv, tl, r and r.get("covered_count"), err))
    r, err = call("progress", "进度页面", learner="k161z", subject=S)
    rows = (r or {}).get("levels") or []
    check(err is None and [x.get("level") for x in rows] == PY and rows and rows[1].get("tally") == "0/1",
          "进度页 levels：每个本科目等级一行（基础 0/1）", (rows, err))

    print("四、导入题库的等级校验")
    imp = ws / "imports"
    imp.mkdir(exist_ok=True)
    (imp / "py_bad.md").write_text(
        "# 题库\npython.q_new_1||入门|选择|题一|甲^乙|A|||python.env_i\n"
        "python.q_new_2||N5|选择|题二|甲^乙|A|||python.env_i\n", encoding="utf-8")
    r, err = call("quiz", "导入题库", file_path="imports/py_bad.md", subject=S)
    msg = str((err or {}).get("error", ""))
    check(err is not None and str(err.get("code")) == "400" and msg.startswith("题库有坏题")
          and "N5" in msg and "第3行" in msg,
          "等级不在本科目里：400「题库有坏题」，带行号和等级", (r, err))
    n = q1("select count(*) from quiz_question where subject_id=?", sid)[0]
    check(n == py_q_before, "导入被拒后 Python 题一道没动", n)
    (imp / "py_ok.md").write_text("python.q_new_1||入门|选择|题一|甲^乙|A|||python.env_i\n", encoding="utf-8")
    r, err = call("quiz", "导入题库", file_path="imports/py_ok.md", subject=S)
    check(err is None and str(r.get("imported")) == "1", "对照：等级在本科目里的能导入", (r, err))
    jp_n = q1("select count(*) from quiz_question where subject_id=1")[0]
    check(jp_n > 0, "日语题库没受影响（%d 题）" % jp_n)
    # 重灌把 Python 题换成了 1 道入门题；补回基础、进阶题，后面的「在用」检查要用
    cn = sqlite3.connect(db)
    for no, lvl, item in (("python.q_class_1", "进阶", "python.class_i"), ("python.q_list_1", "基础", "python.list_i")):
        cn.execute("insert into quiz_question(question_no,course,level,category,stem,options,answer,"
                   "accepted,explain,item_code,subject_id) values(?,'',?,'选择','题干','甲^乙','A','','',?,?)",
                   (no, lvl, item, sid))
    cn.commit()
    cn.close()

    print("五、改科目：删除在用等级被拒，新增/调顺序可以")
    r, err = call("subject", "改科目", learner="t1", subject_id=S, name="Python入门", levels="入门,基础")
    msg = str((err or {}).get("error", ""))
    check(err is not None and str(err.get("code")) == "400" and "进阶" in msg and "在用" in msg,
          "删掉在用的「进阶」：400 且提示哪一级还在用", (r, err))
    check(q1("select levels from subject_info where id=?", sid)[0] == "入门,基础,进阶", "被拒后等级没变")
    r, err = call("subject", "改科目", learner="t1", subject_id=S, name="Python入门", levels="入门,基础,进阶改")
    check(err is not None and str(err.get("code")) == "400", "把在用的「进阶」改名：同样 400", (r, err))
    r, err = call("subject", "改科目", learner="t1", subject_id=S, name="Python入门", levels="基础,入门,进阶,高级")
    check(err is None and q1("select levels from subject_info where id=?", sid)[0] == "基础,入门,进阶,高级",
          "调顺序 + 新增「高级」：可以", (r, err))
    r, err = call("subject", "改科目", learner="t1", subject_id=S, name="Python入门", levels="基础,入门,进阶")
    check(err is None and q1("select levels from subject_info where id=?", sid)[0] == "基础,入门,进阶",
          "删掉没在用的「高级」：可以", (r, err))
    r, err = call("subject", "改科目", learner="t1", subject_id="1", name="日语语法", levels="N5,N4,N3,N2")
    check(err is not None and str(err.get("code")) == "400" and "N1" in str(err.get("error")),
          "日语科目删 N1（有题在用）：400", (r, err))

    print("六、新建通用科目默认三档")
    r, err = call("subject", "建科目", learner="t1", code="k161g", name="通用科目")
    row = q1("select kind, levels from subject_info where code='k161g'")
    check(err is None and row == ("general", "入门,基础,进阶"), "新建通用科目 levels=入门,基础,进阶", (row, err))
    r, err = call("subject", "建科目", learner="t1", code="k161l", name="语言科目", kind="language")
    row = q1("select levels from subject_info where code='k161l'")
    check(err is None and row == ("N5,N4,N3,N2,N1",), "新建语言科目 levels=N5..N1", (row, err))

    print("七、非日语科目教材导入入口关闭")
    (imp / "tb.md").write_text("第1课 列表\n内容\n", encoding="utf-8")
    t_before = q1("select count(*) from textbook_import_task")[0]
    r, err = call("textbook_import", "新建导入", series_code="py_s", series_name="Python教材",
                  code_prefix="python.", file_path="imports/tb.md", file_name="tb.md", subject=S)
    check(err is not None and str(err.get("code")) == "403" and "没开教材导入" in str(err.get("error")),
          "Python 科目新建导入：403 本科目没开教材导入", (r, err))
    r, err = call("textbook_import", "新建导入", series_code="hanabira", series_name="x",
                  code_prefix="x", file_path="imports/tb.md", subject="1")
    check(err is not None and str(err.get("code")) == "400" and "hanabira" in str(err.get("error")),
          "对照：日语科目过了门控（走到后面的 hanabira 校验 400）", (r, err))
    check(q1("select count(*) from textbook_import_task")[0] == t_before, "没建任何导入任务")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n通过 %d，失败 %d" % (passed, failed))
sys.exit(1 if failed else 0)
