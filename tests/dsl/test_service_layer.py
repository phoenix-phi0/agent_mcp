# -*- coding: utf-8 -*-
"""业务层（services/<模块>.zs）：HTTP 层真调。

    cd /workspace/agent_mcp && .venv/bin/python tests/dsl/test_service_layer.py

用 tests/dsl/fixtures/service_layer 这个小项目（graph、progress、loop 三个模块），拷到临时目录、
建库，Flask 测试客户端打接口。覆盖：正常返回、业务错误 404 透传、事务中途报错整体回滚、外层事务里调
函数并入同一事务、调非公开函数被拒、未声明依赖被拒、缺必填 / 多传参数被拒、依赖成环加载报错、
递归超深度报错、出错时接住、services 文件改了自动重载、旧的「执行」不受影响，以及加载检查。
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl import DSLError                      # noqa: E402
from tools.dsl_http import Router                   # noqa: E402
from tools.dsl_service import parse_module, ServiceProblem  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "service_layer"

SCHEMA = """
CREATE TABLE point(id INTEGER PRIMARY KEY, code TEXT UNIQUE, title TEXT);
CREATE TABLE answer(id INTEGER PRIMARY KEY, learner TEXT, point_id INTEGER, question_no TEXT, correct INTEGER);
CREATE TABLE mastery(learner TEXT, point_id INTEGER, score REAL, mastered INTEGER, UNIQUE(learner, point_id));
INSERT INTO point(code, title) VALUES('P1', '一次函数');
"""

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def make_project():
    ws = Path(tempfile.mkdtemp(prefix="svc_"))
    for sub in ("services", "routes", "queries", "scripts"):
        shutil.copytree(FIX / sub, ws / sub)
    con = sqlite3.connect(ws / "app.db")
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    return ws


def main():
    ws = make_project()
    router = Router(ws / "routes", ws, ws / "sessions", real=False)
    c = router.app().test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {}), r.get_data(as_text=True)

    def rows(sql):
        con = sqlite3.connect(ws / "app.db")
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    print("一、正常调用：接口 → 记作答 → 取知识点 / 重算得分")
    st, body, text = post("/progress/answer", learner="u1", point_code="P1", question_no="q1", correct="1")
    check(st == 200 and body.get("score") == 100 and body.get("mastered") == 1,
          f"一道全对：{st} {body}")
    st, body, _ = post("/progress/answer", learner="u1", point_code="P1", question_no="q2", correct="0",
                       pass_line="60", fall_line="40")
    check(st == 200 and body.get("score") == 50 and body.get("mastered") == 0 and body.get("weak") == 0,
          f"可选参数 pass_line/fall_line 传进去了：{body}")
    check(rows("select count(*) from answer") == [(2,)] and rows("select score, mastered from mastery") == [(50.0, 0)],
          "库里两条作答，掌握度被重算得分更新")

    print("二、业务错误 404 沿调用链透传成 HTTP")
    st, body, _ = post("/progress/answer", learner="u1", point_code="NOPE", question_no="q9", correct="1")
    check(st == 404 and body == {"error": "没有这个知识点"}, f"取知识点返回空 → 记作答 报错 404：{st} {body}")
    check(rows("select count(*) from answer") == [(2,)], "没写库")

    print("三、事务中途报错：整体回滚")
    st, body, _ = post("/progress/answer", learner="u2", point_code="P1", question_no="boom", correct="1")
    check(st == 409 and body == {"error": "中途失败"}, f"事务里 报错 409：{st} {body}")
    check(rows("select count(*) from answer where learner='u2'") == [(0,)]
          and rows("select count(*) from mastery where learner='u2'") == [(0,)],
          "answer 的插入和 重算得分 的 mastery 写入都回滚了")

    print("四、外层事务里调函数：写库并入同一个事务")
    st, body, _ = post("/progress/recalc_then_fail", learner="u1", point_code="P1")
    check(st == 409 and body == {"error": "外层中途失败"}, f"外层事务里调 重算（它自己也写「事务」）后报错：{st} {body}")
    check(rows("select score from mastery where learner='u1'") == [(50.0,)],
          "重算得分写的 mastery 被外层回滚（仍是 50，没被重算成别的值）")
    post("/progress/answer", learner="u1", point_code="P1", question_no="q3", correct="1")   # 现在 2/3
    st, body, _ = post("/progress/recalc_then_fail", learner="u1", point_code="P1")
    check(rows("select round(score) from mastery where learner='u1'") == [(67.0,)], "answer 后 mastery 是 67，外层失败不改它")
    st, body, _ = post("/progress/recalc", learner="u1", point_code="P1")
    check(st == 200 and abs(body.get("score", 0) - 66.67) < 0.01, f"自己开事务的函数单独调用也能提交：{st} {body}")

    print("五、出错时接住")
    st, body, _ = post("/progress/answer_try", learner="u3", point_code="NOPE", question_no="q1", correct="1")
    check(st == 200 and body.get("handled") is True and body.get("code") == "404"
          and body.get("msg") == "没有这个知识点", f"接口自己处理：{body}")
    st, body, _ = post("/progress/answer_try", learner="u3", point_code="P1", question_no="q1", correct="1")
    check(st == 200 and body.get("score") == 100, f"没出错 e 是空串，走正常返回：{body}")

    print("六、规则：非公开 / 依赖 / 参数")
    st, body, text = post("/progress/private", learner="u1")
    check(st == 500 and "不是公开函数" in text, f"接口调本模块非公开函数被拒：{st}")
    st, body, text = post("/graph/internal")
    check(st == 500 and "不是公开函数" in text, f"调别的模块的非公开函数被拒：{st}")
    st, body, text = post("/graph/undeclared")
    check(st == 500 and "没有声明依赖" in text and "依赖 graph" not in text.replace("依赖「progress」", ""),
          f"graph 没声明依赖 progress：{st}")
    check("加一行「依赖 progress」" in text, "报错告诉怎么改")
    st, body, text = post("/progress/missing", learner="u1", point_code="P1")
    check(st == 500 and "缺少必填参数：question_no、correct" in text, f"缺必填被拒：{st}")
    st, body, text = post("/progress/extra", learner="u1", point_code="P1")
    check(st == 500 and "不认识的参数：foo" in text, f"多传未知键被拒：{st}")
    st, body, _ = post("/graph/point", code="P1")
    check(st == 200 and body.get("code") == "P1", f"本模块接口调本模块公开函数：{body}")

    print("七、递归超深度")
    st, body, text = post("/loop/run")
    check(st == 500 and "业务函数调用深度超过 32" in text, f"默认上限 32：{st}")
    os.environ["DSL_SERVICE_MAX_DEPTH"] = "4"
    try:
        st, body, text = post("/loop/run")
        check(st == 500 and "深度超过 4" in text and "loop.自转 → loop.自转" in text, f"上限可配（环境变量）：{text[:120]}")
    finally:
        del os.environ["DSL_SERVICE_MAX_DEPTH"]

    print("八、旧机制不受影响")
    st, body, _ = post("/progress/legacy", who="张三")
    check(st == 200 and body == {"hello": "张三"}, f"执行 scripts/x.zs 照常：{body}")

    print("九、依赖成环 / 不存在 / 模块名与文件名不符：加载报错")
    bad = Path(tempfile.mkdtemp(prefix="svc_bad_"))
    (bad / "routes").mkdir()
    (bad / "services").mkdir()
    (bad / "services" / "a.zs").write_text("业务 a\n  依赖 b\n  公开 函数 f\n    返回 1\n  结束\n结束\n", encoding="utf-8")
    (bad / "services" / "b.zs").write_text("业务 b\n  依赖 a\n  公开 函数 g\n    返回 1\n  结束\n结束\n", encoding="utf-8")
    try:
        Router(bad / "routes", bad, bad / "sessions", real=False)
        check(False, "依赖成环应当加载失败")
    except DSLError as e:
        check("业务模块依赖成环：" in str(e) and "a → b → a" in str(e), f"成环：{str(e).splitlines()[-1]}")
    (bad / "services" / "b.zs").write_text("业务 b\n  依赖 zzz\n  公开 函数 g\n    返回 1\n  结束\n结束\n", encoding="utf-8")
    try:
        Router(bad / "routes", bad, bad / "sessions", real=False)
        check(False, "依赖不存在应当加载失败")
    except DSLError as e:
        check("services/b.zs（第 2 行）" in str(e) and "依赖的业务模块「zzz」不存在" in str(e), "依赖指向不存在的模块")
    try:
        parse_module("业务 x\n结束\n", Path("services/y.zs"))
        check(False, "模块名和文件名不符应当报错")
    except ServiceProblem as e:
        check("要和文件名一致" in str(e), "模块名和文件名要一致")

    print("十、services 文件改了，下个请求自动重载")
    time.sleep(0.01)
    p = ws / "services" / "graph.zs"
    p.write_text(p.read_text(encoding="utf-8").replace("返回 {p}", '返回 {"id": "{p.id}", "code": "{p.code}", "v": 2}'),
                 encoding="utf-8")
    os.utime(p, (time.time() + 5, time.time() + 5))
    st, body, _ = post("/graph/point", code="P1")
    check(st == 200 and body.get("v") == 2, f"重载后用新版本：{body}")

    print("十一、加载检查（loadcheck）：不起服务就能查出来")
    sys.path.insert(0, str(ROOT / "tools" / "dslagent" / "verbs" / "newproj" / "defs"))
    from tools.dslagent.loadcheck import check_project, check_file          # noqa: E402
    import _params as P                                                     # noqa: E402

    probs = check_project(FIX)
    joined = "\n".join(probs)
    check(len(probs) == 5, f"示例项目里故意写错的 5 个接口都查到了（共 {len(probs)} 条）")
    check("graph.内部统计 不是公开函数" in joined and "routes/graph_api.zs 接口 POST /graph/internal" in joined, "调非公开函数：点名文件、接口、行号")
    check("业务模块「graph」没有声明依赖「progress」" in joined, "跨模块未声明依赖")
    check("缺少必填参数：question_no、correct" in joined and "不认识的参数：foo" in joined, "缺必填 / 多出未知键")
    bad = Path(tempfile.mkdtemp(prefix="svc_lc_"))
    for sub in ("services", "routes", "queries", "scripts"):
        shutil.copytree(FIX / sub, bad / sub)
    (bad / "services" / "progress.zs").write_text("""业务 progress
  依赖 graph
  依赖 nobody
  公开 函数 a x y?
    设 r = 调用 graph.不存在 code=1
    设 r = 调用 graph.内部统计
    设 r = 调用 graph.取知识点
    报错 500 x
    如果 {x} 乱七八糟
    结束
  结束
结束
""", encoding="utf-8")
    (bad / "scripts" / "s.zs").write_text("设 r = 调用 progress.a x=1\n设 q = 调用 nomod.f\n", encoding="utf-8")
    joined = "\n".join(check_project(bad))
    check("services/progress.zs（第 3 行）: 依赖的业务模块「nobody」不存在" in joined, "依赖指向不存在的模块（文件、行号）")
    check("services/progress.zs 函数 a: 第 5 行：业务模块「graph」里没有函数「不存在」" in joined, "调用不存在的函数（文件、函数、行号）")
    check("第 6 行：graph.内部统计 不是公开函数" in joined and "第 7 行：graph.取知识点 缺少必填参数：code" in joined, "函数里的非公开 / 缺必填")
    check("业务错误的码要是 400–499，现在是 500" in joined and "看不懂的条件" in joined, "报错码不是 4xx、函数体的语法错")
    check("scripts/s.zs" in joined and "没有业务模块「nomod」" in joined, "scripts 里的调用也查")
    (bad / "services" / "a.zs").write_text("业务 a\n  依赖 b\n结束\n", encoding="utf-8")
    (bad / "services" / "b.zs").write_text("业务 b\n  依赖 a\n结束\n", encoding="utf-8")
    check("业务模块依赖成环：" in "\n".join(check_file(bad / "services" / "a.zs", "services/a.zs")), "单个业务文件检查也报依赖成环")
    for text, want in [
        ("业务 x\n  函数 f\n    如果 1 等于 1\n结束\n", "函数没有对应的「结束」"),
        ("业务 x\n  函数 f a a\n  结束\n结束\n", "入参「a」重复"),
        ("业务 x\n  函数 f\n  结束\n  函数 f\n  结束\n结束\n", "函数「f」重复定义"),
        ("业务 x\n  设 a = 1\n结束\n", "业务块里只能写"),
        ("业务 x\n  函数 f\n  结束\n", "业务块没有对应的「结束」"),
        ("函数 f\n结束\n", "文件第一句应是「业务 模块名」"),
    ]:
        try:
            parse_module(text, Path("services/x.zs"))
            check(False, f"应当报错：{want}")
        except ServiceProblem as e:
            check(want in str(e), f"解析错误「{want}」")

    print("十二、参数核对：函数入参是函数体里已定义的变量")
    qd = FIX / "queries"
    errs, n = P.check_text((FIX / "services" / "progress.zs").read_text(encoding="utf-8"), "services/progress.zs", qd, None)
    check(not errs and n == 4, f"示例业务文件通过，检查了 {n} 处调用：{errs}")
    errs, _ = P.check_text("业务 m\n  公开 函数 f learner\n    设 n = 写库 app.db answer_insert learner={learner} point_id={pid} question_no=1 correct=1\n  结束\n结束\n",
                           "services/m.zs", qd, None)
    check(any("point_id={pid} 没有来源" in e or "{pid}" in e for e in errs), f"没声明的入参当来源会被查出来：{errs}")
    errs, _ = P.check_text("业务 m\n  公开 函数 f learner\n    设 n = 写库表 app.db answer_insert {request}\n  结束\n结束\n", "services/m.zs", qd, None)
    check(any("{request}" in e for e in errs), "函数里没有 {request}：用它当参数表会被查出来")

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
