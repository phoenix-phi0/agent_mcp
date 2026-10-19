# -*- coding: utf-8 -*-
"""modular 的试调检查（tools/dslagent/trial.py）+ 可选参数空串保护（modbuild.check_optional_sql）+ 计划里的「可选」标记。不调模型。

    .venv/bin/python tests/tools/test_dslagent_trial.py

一、造数：建空库、外键 / 枚举 / 唯一 / 必填都满足，user 表按角色造合成账号
二、判定：外键 409、500 不过（报错带接口 / 入参 / 账号 / 响应原话）；业务 4xx（手写 409、400、404）算正常
三、入参：必填给值；可选入参分别「不传」「传空串」；没写角色的接口按每个角色各调一遍
四、副本：不改原项目；跑不起来记「跳过」而不是判接口不过
五、可选参数空串保护的静态检查
六、单文件计划里的「可选参数」「可选入参」
七、接口约定的响应键（带「响应」的接口项：200 的响应缺约定的 state / lists 键或 messages 判不过）
"""
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools/dslagent/verbs/newproj/defs"))

from gen import project as P            # noqa: E402
import _gencore as GC                   # noqa: E402
from tools.dslagent import trial as T, modbuild as MB      # noqa: E402

PASS = FAIL = 0
TMP = Path(tempfile.mkdtemp(prefix="trial_t_"))


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  ✓ " if cond else "  ✗ ") + msg + ("" if cond or extra == "" else f"\n      {str(extra)[:900]}"))


ENTS = ("实体 learner 学习者\n  字段 name 文本 必填 唯一 名\n  字段 level 枚举 easy,hard 必填 等级\n结束\n\n"
        "实体 sess 会话\n  字段 learner_id 整数 必填 关联 learner 学习者\n  字段 note 文本 备注\n  字段 done 布尔 必填 完成\n  字段 at 日期 必填 时间\n结束\n")


def mkproj(tag, tpl="private", roles=("teacher", "student"), ents=ENTS):
    root = TMP / tag / "p"
    root.mkdir(parents=True)
    P.init(root, sample=False)
    (root / "entities" / "q.entity").write_text(ents, encoding="utf-8")
    r = GC.generate(root, tpl, roles=list(roles) if roles else None)
    assert r["ok"] == "是", r
    return root


def add(root, rel, text, sqls=None):
    f = root / rel
    f.write_text((f.read_text(encoding="utf-8") if f.is_file() else "") + text, encoding="utf-8")
    for n, s in (sqls or {}).items():
        (root / "queries" / f"{n}.sql").write_text(s, encoding="utf-8")


def snap(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def one(rel, path, ins, opts=(), role=""):
    return {rel: [{"路径": path, "入参": list(ins), "可选入参": list(opts), "角色": role}]}


def main():
    print("一、造数")
    root = mkproj("a")
    from tools.entity import parse
    text = "\n\n".join(f.read_text(encoding="utf-8") for f in sorted((root / "entities").glob("*.entity")))
    ents = parse(text)
    db = TMP / "seed.db"
    data, acc = T.seed(db, ents, ["teacher", "student"], 3, text)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    check(con.execute("PRAGMA foreign_key_check").fetchall() == [], "外键全部指向已造的行")
    check(con.execute("SELECT COUNT(*) FROM sess WHERE learner_id = 4").fetchone()[0] == 0, "备用行（第 4 行）没有任何行引用，子表只引用前 3 行")
    check(con.execute("SELECT COUNT(*) FROM learner").fetchone()[0] == 4 and con.execute("SELECT COUNT(DISTINCT name) FROM learner").fetchone()[0] == 4, "每表 4 行（3 行互相引用 + 1 行备用），唯一列各不相同")
    check({r[0] for r in con.execute("SELECT level FROM learner")} <= {"easy", "hard"}, "枚举取选项里的值")
    check(con.execute("SELECT COUNT(*) FROM sess WHERE learner_id IS NULL OR at IS NULL OR done IS NULL").fetchone()[0] == 0, "必填列都有值")
    check(acc == {"teacher": "trial_teacher", "student": "trial_student"} and
          {r[0]: r[1] for r in con.execute("SELECT username, role FROM user WHERE username LIKE 'trial_%'")}.get("trial_student") == "student", "user 表按角色造合成账号（trial_teacher / trial_student）", acc)
    con.close()

    print("二、判定")
    add(root, "routes/sess.zs", """
接口 POST /sess/fk 动作 sess_fk 角色 student
  用包 db http
  设 args.learner_id = 9999
  设 args.note = x
  设 args.done = 0
  设 args.at = 2026-01-01
  设 n = 写库表 app.db sess_insert {args}
  返回 {"ok":"1"}
结束

接口 POST /sess/biz 动作 sess_biz 角色 student
  用包 db http
  返回 {"error":"已经存在，换一个"} 409
结束

接口 POST /sess/bad_arg 动作 sess_bad_arg 角色 student
  用包 db http
  返回 {"error":"参数错"} 400
结束

接口 POST /sess/nf 动作 sess_nf 角色 teacher
  用包 db http
  返回 {"error":"查无此项"} 404
结束

接口 POST /sess/boom 动作 sess_boom 角色 teacher
  用包 db http
  设 rows = 查询 app.db sess_boom
  返回 {"rows":"{rows}"}
结束

接口 POST /sess/ok 动作 sess_ok 角色 student
  用包 db http
  设 rows = 查询 app.db sess_ok
  返回 {"rows":"{rows}"}
结束
""", {"sess_boom": "SELECT nonexistent_col FROM sess\n", "sess_ok": "SELECT id, note FROM sess\n"})
    before = snap(root)
    its = {"routes/sess.zs": [{"路径": p, "入参": [], "角色": ""} for p in ("/sess/fk", "/sess/biz", "/sess/bad_arg", "/sess/nf", "/sess/boom", "/sess/ok")]}
    res = T.run(root, its)
    pr = res["problems"].get("routes/sess.zs", [])
    fk = [x for x in pr if "/sess/fk" in x]
    check(res["skipped"] == "" and len(fk) == 1 and "409" in fk[0] and "数据库约束错误" in fk[0] and "FOREIGN KEY" in fk[0] and "trial_student" in fk[0] and "角色 student" in fk[0], "外键错误（学生账号调）→ 不过，报错带接口 / 状态码 / 约束原话 / 账号", fk)
    check(len(fk[0]) < 900 and "响应：" in fk[0] and "入参 {" in fk[0], "报错带入参与响应原话")
    boom = [x for x in pr if "/sess/boom" in x]
    check(len(boom) == 1 and "500" in boom[0] and "接口出错" in boom[0] and "trial_teacher" in boom[0], "500（sql 列不存在）→ 不过", boom)
    check(not any(k in " ".join(pr) for k in ("/sess/biz", "/sess/bad_arg", "/sess/nf", "/sess/ok")), "手写的 409 / 400 / 404 与正常查询算业务正常，不误报", pr)
    check(snap(root) == before, "不改原项目（含 app.db）")
    check(res["calls"] == 6, f"每个无可选入参的接口调一次（共 6 次，实际 {res['calls']}）")

    print("三、入参")
    root = mkproj("b")
    add(root, "routes/sess.zs", """
接口 POST /sess/add 动作 sess_add 角色 student
  用包 db http
  设 args.learner_id = {learner_id}
  设 args.note = {note}
  设 args.done = 0
  设 args.at = 2026-01-01
  设 n = 写库表 app.db sess_insert {args}
  返回 {"ok":"1"}
结束

接口 POST /sess/add_d 动作 sess_add_d 角色 student
  用包 db http
  设 args.name = {name}
  设 n = 写库表 app.db learner_named {args}
  返回 {"ok":"1"}
结束

接口 POST /sess/any 动作 sess_any
  用包 db http
  返回 {"who":"{current_user}","role":"{current_role}"}
结束
""", {"learner_named": "INSERT INTO learner(name, level) VALUES(NULLIF(:name, ''), 'easy')\n"})
    res = T.run(root, {"routes/sess.zs": [{"路径": "/sess/add", "入参": ["learner_id", "note"], "可选入参": ["learner_id"], "角色": "student"}]})
    pr = res["problems"].get("routes/sess.zs", [])
    check(res["calls"] == 2 and len(pr) == 1 and "可选入参 learner_id 不传" in pr[0] and "FOREIGN KEY" in pr[0] and '"learner_id"' not in pr[0].split("入参 ", 2)[-1].split(" →")[0],
          "必填给值通过；可选入参 learner_id 不传时外键错 → 不过并说明是哪个变体（同一接口同一角色报一次就停）", (res["calls"], pr))
    res = T.run(root, {"routes/sess.zs": [{"路径": "/sess/add_d", "入参": ["name"], "可选入参": ["name"], "角色": "student"}]})
    pr = res["problems"].get("routes/sess.zs", [])
    check(res["calls"] == 3 and len(pr) == 1 and "可选入参 name 传空串" in pr[0] and '"name": ""' in pr[0] and "不能为空" in pr[0], "可选入参 name：不传能过；传空串触发非空约束 → 不过并说明变体", (res["calls"], pr))
    res = T.run(root, {"routes/sess.zs": [{"路径": "/sess/add", "入参": ["learner_id", "note"], "可选入参": ["note"], "角色": "student"}]})
    check(res["calls"] == 3 and not res["problems"], f"可选入参 note：全给 + 不传 + 传空串 共 3 次都过（{res['calls']}）", res["problems"])
    res = T.run(root, {"routes/sess.zs": [{"路径": "/sess/any", "入参": [], "角色": ""}]})
    check(res["calls"] == 2 and not res["problems"], f"没写角色的接口按每个角色各调一遍（教师、学生共 2 次，实际 {res['calls']}）")
    # 单人项目（没有认证）：不带账号
    r2 = mkproj("c", tpl="full", roles=None)
    add(r2, "routes/sess.zs", "\n接口 POST /sess/me 动作 sess_me\n  用包 db http\n  返回 {\"who\":\"x\"}\n结束\n")
    res = T.run(r2, {"routes/sess.zs": [{"路径": "/sess/me", "入参": [], "角色": ""}]})
    check(res["skipped"] == "" and res["calls"] == 1 and not res["problems"], "单人项目（没开登录）：不造账号，直接调", res)

    print("四、跑不起来")
    res = T.run(TMP / "nonexistent", {"routes/x.zs": [{"路径": "/x", "入参": []}]})
    check(res["skipped"] and not res["problems"], "项目目录不存在 → 记跳过，不当成接口不过", res["skipped"])

    print("五、可选参数空串保护（静态）")
    c = MB.check_optional_sql
    check(c("a", "SELECT * FROM t WHERE (:q IS NULL OR :q = '' OR name = :q)", ["q"]) == [], "标准写法通过")
    check(c("a", "SELECT * FROM t WHERE x=1 AND (:q IS NULL OR :q = '' OR name LIKE '%' || :q || '%')", ["q"]) == [], "模糊匹配也通过")
    check(c("a", "SELECT * FROM t WHERE (COALESCE(:q,'')='' OR name = :q)", ["q"]) == [], "COALESCE(:q,'')='' 写法通过")
    check(c("a", "SELECT * FROM t WHERE (:q = '' OR :q IS NULL OR name = :q)", ["q"]) == [], "顺序颠倒通过")
    e = c("quiz_find", "SELECT * FROM t WHERE name = :q", ["q"])
    check(len(e) == 1 and "quiz_find" in e[0] and ":q" in e[0] and "IS NULL OR" in e[0], "直接比较 → 不过（默写空串过滤的问题）", e)
    check(len(c("a", "SELECT * FROM t WHERE (:q IS NULL OR name = :q)", ["q"])) == 1, "只防 NULL 不防空串 → 不过")
    check(len(c("a", "SELECT * FROM t WHERE :q IS NULL OR :q = '' OR name = :q AND x = 1", ["q"])) == 1, "保护式没整体括起来 → 不过（AND 优先级会让它失效）")
    check(c("a", "SELECT * FROM t WHERE name = :q", []) == [], "没标可选的参数不管")
    check(len(c("a", "SELECT * FROM t WHERE (:p IS NULL OR :p = '' OR a = :p) AND b = :q", ["p", "q"])) == 1, "多个可选参数：漏保护的那个报")
    check(c("a", "SELECT * FROM t -- name = :q\nWHERE (:q IS NULL OR :q = '' OR name = :q)", ["q"]) == [], "注释里的 :q 不算")

    print("六、单文件计划里的「可选」标记")
    sq, errs = MB.plan_sqls({"sql": [{"名": "quiz_find", "参数": ["a", "b"], "可选参数": ["b"], "说明": "x", "规则": []}]}, "quiz", set(), set(), set())
    check(not errs and sq["sql"][0]["可选参数"] == ["b"], "sql 计划接受 可选参数（参数的子集）", errs)
    sq, errs = MB.plan_sqls({"sql": [{"名": "quiz_find", "参数": ["a"], "可选参数": ["zz"], "说明": "x", "规则": []}]}, "quiz", set(), set(), set())
    check(any("可选参数" in x and "zz" in x for x in errs), "可选参数不在参数里 → 计划不过", errs)
    sq, errs = MB.plan_sqls({"sql": [{"名": "quiz_find", "参数": ["a"], "说明": "x", "规则": []}]}, "quiz", set(), set(), set())
    check(not errs and sq["sql"][0]["可选参数"] == [], "不写可选参数 = 空（老计划兼容）")
    ia = {"路径": "/q/a", "动作": "q_a", "角色": "", "入参": ["x", "y"], "可选入参": ["y"], "用sql": [], "用流程": [], "调用": {}, "规则": [], "说明": "s"}
    fp, errs = MB.plan_ifaces({"接口": [ia]}, [], set(), set(), set(), set(), {}, [])
    check(not errs and fp["接口"][0]["可选入参"] == ["y"], "接口计划接受 可选入参（入参的子集）", errs)
    fp, errs = MB.plan_ifaces({"接口": [dict(ia, 可选入参=["zz"])]}, [], set(), set(), set(), set(), {}, [])
    check(any("可选入参" in x and "zz" in x for x in errs), "可选入参不在入参里 → 计划不过", errs)
    check(MB.norm_fp("sql", {"sql": [{"名": "a", "参数": ["p"], "可选参数": ["p"]}]})["sql"][0]["可选参数"] == ["p"]
          and MB.norm_fp("接口", {"接口": [ia]})["接口"][0]["可选入参"] == ["y"], "resume 还原计划时保留这两个标记")

    print("七、接口约定的响应键（接口项带「响应」）")
    root = mkproj("r", tpl="default", roles=None)
    add(root, "routes/r.zs", """
接口 POST /r/state 动作 r_state
  用包 db http
  状态 ok 1
  消息 bot hi
结束

接口 POST /r/top 动作 r_top
  用包 db http
  返回 {"ok":"1"}
结束

接口 POST /r/none 动作 r_none
  用包 db http
  返回 {"x":"1"}
结束

接口 POST /r/nf 动作 r_nf
  用包 db http
  返回 {"error":"查无此项"} 404
结束
""")
    spec = lambda st=(), li=(), msg="否": {"state": list(st), "lists": list(li), "messages": msg}      # noqa: E731

    def run1(path, **kw):
        res = T.run(root, {"routes/r.zs": [{"路径": path, "入参": [], "可选入参": [], "角色": "", "响应": spec(**kw)}]})
        return res, [x for xs in res["problems"].values() for x in xs]
    res, pr = run1("/r/state", st=["ok"], msg="是")
    check(res["skipped"] == "" and pr == [], "状态 + 消息 的接口：约定 state.ok / messages=是 都有 → 过", (res, pr))
    res, pr = run1("/r/top", st=["ok"])
    check(pr == [], "返回 {\"ok\":…} 的顶层键也认作约定的 state 键 → 过", pr)
    res, pr = run1("/r/none", st=["ok"])
    check(len(pr) == 1 and "响应缺约定里的键" in pr[0] and "state.ok" in pr[0] and "/r/none" in pr[0], "响应缺约定里的 state 键 → 不过，报错点名缺哪个", pr)
    res, pr = run1("/r/state", st=["zz"])
    check(len(pr) == 1 and "state.zz" in pr[0], "约定 state 里有响应里没有的键 → 不过", pr)
    res, pr = run1("/r/top", st=["ok"], msg="是")
    check(len(pr) == 1 and "messages" in pr[0], "约定 messages=是 但响应没有消息 → 不过", pr)
    res, pr = run1("/r/state", li=["rows"])
    check(len(pr) == 1 and "lists.rows" in pr[0], "约定 lists 键缺 → 不过", pr)
    res, pr = run1("/r/nf", st=["ok"], msg="是")
    check(pr == [], "业务错误（404）不查响应键，算正常", pr)
    res = T.run(root, {"routes/r.zs": [{"路径": "/r/none", "入参": [], "可选入参": [], "角色": ""}]})
    check(res["problems"] == {}, "接口项不带「响应」（老计划）→ 不查响应键")
    check(T.missing_keys("不是 json", spec(st=["a"])) == ["state.a"] and T.missing_keys('{"state":{"a":1},"lists":{"b":[]}}', spec(st=["a"], li=["b"])) == [], "missing_keys：非 JSON 当全缺；state / lists 下的键认")

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
