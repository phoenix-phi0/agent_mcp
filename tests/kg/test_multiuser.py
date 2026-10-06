# -*- coding: utf-8 -*-
"""kg 的多人模式：登录、教师 / 学生、数据隔离、停用、改密、限流、命令行账号。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_multiuser.py

临时工作区（照 kg 搭，导入知识点、课文、题目、单词），不碰 kg/app.db。同一个
工作区起两个应用：单人模式（make_app 默认）和多人模式（login=True）。模型是
离线假客户端。

  一、单人模式照旧：不用登录、learner 没给是 me、给了照用、管理接口能调、
      /auth/me 是空的
  二、命令行：建教师（--密码环境变量、--库）、重名拒绝、改密
  三、多人模式：没登录 401、/auth/me 公开、没有注册接口、教师登录
  四、教师建学生：学生管理页的接口；页面上建不出教师
  五、学生：/auth/me 的 hide 有「管理」；所有「角色 teacher」接口 403「需要教师
      权限」，教师调同样的接口不是 403（对照）；请求体伪造 current_role 无效
  六、伪造 learner：学生 A 在请求体里写学生 B，记录仍记在 A 名下
  七、两个学生的数据隔离：做题、默写、问老师、进度、教材偏好
  八、停用：已登录的令牌下一个请求就 401、cookie 被删；登录也不行；启用后恢复
  九、改密码：旧密码不对 400；改了之后旧密码登不上、新密码能登；教师重置
  十、限流：同一用户名连续错 5 次锁住，第 6 次密码对也 429；不存在的用户名一样；
      同一来源换着用户名错 5 次也锁；说明不泄露用户存不存在
  十一、并入 me：单人模式 me 的记录归到一个账号，先备份；账号已有记录就不做
  十二、--登录 的接线：py -m kg --登录 / KG_LOGIN 交给 gen run；app.pyw 的
      build_app 传 login；没写「认证 可选」的项目开登录报错
"""

import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.kg.helpers import import_graph, import_words, make_ws   # noqa: E402
from kg.__main__ import BANK, read_bank                             # noqa: E402
from tools.auth import COOKIE, LIMITER                              # noqa: E402
from tools.mock import MockClient                                   # noqa: E402

PY = str(ROOT / ".venv" / "bin" / "python")
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def handler(prompt, system):
    """问老师的假模型：判意图一律回讲解，回答回固定的一句。"""
    if "意图分类器" in (system or ""):
        return '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}'
    return "老师的回答"


def make(ws, login):
    from gen.project import make_app
    app, router = make_app(ws, real=False, login=login) if login else make_app(ws, real=False)
    mock = MockClient(handler=handler, offline=True)
    router.client_factory = lambda: mock
    return app, router


def kg_cli(*args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([PY, "-m", "kg", *args], cwd=ROOT, env=e,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


def main():
    ws = make_ws(Path(tempfile.mkdtemp(prefix="multiuser_")))
    db = ws / "app.db"
    import_graph(ws)
    import_words(ws)
    solo_app, _ = make(ws, False)
    solo = solo_app.test_client()
    solo.post("/lesson/import", json={"form": {}})
    bank = read_bank(BANK)
    r = solo.post("/quiz/import", json={"form": {"rows": bank}})
    check(r.status_code == 200, f"题目导入：{r.status_code}")

    def rows(sql, *args):
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            return [dict(x) for x in con.execute(sql, args)]
        finally:
            con.close()

    def n(table, where="1", *args):
        return rows(f"SELECT count(*) n FROM {table} WHERE {where}", *args)[0]["n"]

    def post(c, path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {}), r

    # ------------------------------------------------------------------
    print("一、单人模式照旧")
    st, b, _ = post(solo, "/auth/me")
    check(st == 200 and b.get("user") == "" and b.get("mode") == "off" and b.get("hide") == [],
          f"/auth/me：没人登录、mode=off、不藏：{b}")
    st, b, _ = post(solo, "/quiz/start", pick_level="全部", pick_kind="全部")
    check(st == 200 and n("quiz_state", "learner = 'me'") == 1, "没给 learner：记在 me 名下")
    st, b, _ = post(solo, "/quiz/start", learner="solo2", pick_level="全部", pick_kind="全部")
    check(st == 200 and n("quiz_state", "learner = 'solo2'") == 1,
          "给了 learner 照用（单人模式下测试靠它分开学习者）")
    st, b, _ = post(solo, "/import/home")
    check(st == 200, f"管理接口不用登录、不查角色：{st}")
    st, b, _ = post(solo, "/student/home")
    check(st == 200 and "students" in (b.get("lists") or {}), f"学生管理页单人模式也能开：{st}")
    check(not (ws / ".auth_secret").exists(), "单人模式不生成签名密钥")

    # ------------------------------------------------------------------
    print("二、命令行建教师、改密")
    env = {"KG_TEST_PW": "teach-pass-1"}
    code, out = kg_cli("建教师", "t1", "--显示名", "王老师", "--库", str(db),
                       "--密码环境变量", "KG_TEST_PW", env=env)
    u = rows("SELECT username, role, display_name, disabled, password_hash FROM user WHERE username='t1'")
    check(code == 0 and u and u[0]["role"] == "teacher" and u[0]["display_name"] == "王老师"
          and u[0]["disabled"] == 0, f"建教师：{code} {out.strip()[-60:]}")
    check(u and u[0]["password_hash"].startswith("scrypt$") and "teach-pass-1" not in out,
          "库里是哈希，输出里没有密码")
    code, out = kg_cli("建教师", "t1", "--库", str(db), "--密码环境变量", "KG_TEST_PW", env=env)
    check(code == 1 and "已经有了" in out, "重名拒绝")
    code, out = kg_cli("建教师", "坏 名", "--库", str(db), "--密码环境变量", "KG_TEST_PW", env=env)
    check(code != 0, "用户名带空格拒绝")
    code, out = kg_cli("建教师", "t9", "--库", str(db), "--密码环境变量", "KG_TEST_PW",
                       env={"KG_TEST_PW": "123"})
    check(code != 0 and n("user", "username='t9'") == 0, "密码太短拒绝，没建")
    old_hash = u[0]["password_hash"]
    code, out = kg_cli("改密", "t1", "--库", str(db), "--密码环境变量", "KG_TEST_PW",
                       env={"KG_TEST_PW": "teach-pass-2"})
    check(code == 0 and rows("SELECT password_hash h FROM user WHERE username='t1'")[0]["h"] != old_hash,
          f"改密：{out.strip()[-40:]}")
    code, out = kg_cli("改密", "nobody", "--库", str(db), "--密码环境变量", "KG_TEST_PW", env=env)
    check(code == 1, "改不存在的账号：拒绝")

    # ------------------------------------------------------------------
    print("三、多人模式：要登录")
    LIMITER.reset()
    app, router = make(ws, True)
    check(router.auth_required, "login=True 的路由要求登录")
    anon = app.test_client()
    for path in ("/quiz/start", "/teacher/state", "/progress/page", "/lesson/list", "/import/home"):
        st, b, _ = post(anon, path)
        check(st == 401, f"没登录 {path} → {st}")
    st, b, _ = post(anon, "/auth/me")
    check(st == 200 and b.get("user") == "" and b.get("mode") == "on", f"/auth/me 公开：{b}")
    st, b, _ = post(anon, "/auth/register", username="x", password="123456")
    check(st in (404, 405) and n("user", "username='x'") == 0, f"没有注册接口：{st}")

    teacher = app.test_client()
    st, b, r = post(teacher, "/auth/login", username="t1", password="teach-pass-1")
    check(st == 400, "旧密码登不上（刚用命令行改过）")
    st, b, r = post(teacher, "/auth/login", username="t1", password="teach-pass-2")
    setc = r.headers.get("Set-Cookie", "")
    check(st == 200 and COOKIE in setc and "HttpOnly" in setc and "SameSite=Lax" in setc
          and "Secure" not in setc, f"教师登录：{st}，cookie HttpOnly+Lax、本机不加 Secure")
    st, b, _ = post(teacher, "/auth/me")
    check(b.get("user") == "t1" and b.get("label") == "王老师" and b.get("role") == "teacher"
          and b.get("hide") == [], f"/auth/me：{b}")

    # ------------------------------------------------------------------
    print("四、教师建学生")
    st, b, _ = post(teacher, "/student/create", username="s1", display_name="小一", password="s1-pass")
    check(st == 200 and rows("SELECT role FROM user WHERE username='s1'") == [{"role": "student"}],
          f"建 s1：{st} {b.get('messages')}")
    st, b, _ = post(teacher, "/student/create", username="s2", display_name="小二", password="s2-pass",
                    role="teacher")
    check(st == 200 and rows("SELECT role FROM user WHERE username='s2'") == [{"role": "student"}],
          "请求里塞 role=teacher 也只建得出学生")
    st, b, _ = post(teacher, "/student/create", username="s1", password="whatever1")
    check(st == 400 and "占用" in b.get("error", ""), f"重名：{b}")
    st, b, _ = post(teacher, "/student/create", username="s3", password="123")
    check(st == 400 and n("user", "username='s3'") == 0, "密码太短：400，没建")
    st, b, _ = post(teacher, "/student/home")
    names = [x["username"] for x in (b.get("lists") or {}).get("students", [])]
    check(st == 200 and set(names) == {"s1", "s2"}, f"学生表只有学生：{names}")

    s1, s2 = app.test_client(), app.test_client()
    st, *_ = post(s1, "/auth/login", username="s1", password="s1-pass")
    st2, *_ = post(s2, "/auth/login", username="s2", password="s2-pass")
    check(st == 200 and st2 == 200, "两个学生都能登录")

    # ------------------------------------------------------------------
    print("五、学生碰不了管理侧")
    st, b, _ = post(s1, "/auth/me")
    check(b.get("role") == "student" and b.get("hide") == ["管理"] and b.get("label") == "小一",
          f"/auth/me：{b}")
    role_eps = sorted(p for (m, p), ep in router.table.items() if ep.role == "teacher")
    want = {"/import/home", "/import/create", "/import/confirm", "/import/series_withdraw",
            "/kg/import2", "/kg/export", "/lesson/import", "/quiz/import", "/word/import2",
            "/word/import", "/word/create", "/word/update", "/word/delete", "/score/rebuild",
            "/score/add", "/student/home", "/student/create", "/student/reset",
            "/student/disable", "/student/enable"}
    check(want <= set(role_eps), f"管理接口都标了角色（{len(role_eps)} 个），缺 {sorted(want - set(role_eps))}")
    bad = []
    for path in role_eps:
        st, b, _ = post(s1, path)
        if st != 403 or b.get("error") != "需要教师权限":
            bad.append((path, st, b))
    check(not bad, f"学生调 {len(role_eps)} 个管理接口全是 403「需要教师权限」（不对的 {bad[:3]}）")
    st, b, _ = post(s1, "/student/home", current_role="teacher")
    check(st == 403, "请求体伪造 current_role=teacher：仍 403")
    st, b, _ = post(teacher, "/import/home")
    st2, b2, _ = post(teacher, "/score/rebuild")
    check(st == 200 and st2 == 200, f"对照：教师调同样的接口 200（{st} {st2}）")
    check(n("user", "username='hacker'") == 0, "（没人建出 hacker）")
    st, b, _ = post(s1, "/student/create", username="hacker", password="hacker-1")
    check(st == 403 and n("user", "username='hacker'") == 0, "学生建不了账号")

    # ------------------------------------------------------------------
    print("六、伪造 learner")
    before_s2 = n("quiz_state", "learner = 's2'")
    st, b, _ = post(s1, "/quiz/start", learner="s2", pick_level="全部", pick_kind="全部")
    check(st == 200 and n("quiz_state", "learner = 's1'") == 1 and n("quiz_state", "learner = 's2'") == before_s2,
          "s1 请求体写 learner=s2：进度记在 s1 名下，s2 没动")
    card = (b.get("state") or {}).get("card") or {}
    opts = card.get("options") or []
    st, b, _ = post(s1, "/quiz/answer", learner="s2", choice=(opts[0]["key"] if opts else "A"),
                    given="x")
    check(n("attempt", "learner = 's1'") >= 1 and n("attempt", "learner = 's2'") == 0
          and n("attempt", "learner = 'me'") == 0,
          f"作答记在 s1（{n('attempt', 'learner = ' + chr(39) + 's1' + chr(39))}），s2、me 一条都没有")

    # ------------------------------------------------------------------
    print("七、两个学生互相看不到")
    st, b, _ = post(s2, "/learn/status")
    check(st == 200, f"s2 看学习状态：{st}")
    st, b, _ = post(s2, "/quiz/state")
    check(not ((b.get("state") or {}).get("card") or {}).get("code") or n("quiz_state", "learner='s2'") == 0,
          "s2 的做题进度是空的")
    # 默写
    st, b, _ = post(s1, "/dictation/start", dict_direction="看中文写日语", dict_level="全部", dict_source="随机")
    st, b, _ = post(s1, "/dictation/answer", dict_answer="ちがう", learner="s2")
    check(n("word_attempt", "learner='s1'") == 1 and n("word_attempt", "learner='s2'") == 0,
          "默写：s1 的作答记在 s1（请求体的 learner=s2 不算）")
    st, b, _ = post(s2, "/dictation/book")
    check(st == 200 and not (b.get("lists") or {}).get("dict_book"),
          f"s2 的错词本是空的：{str(b.get('lists'))[:80]}")
    # 问老师
    st, b, _ = post(s1, "/teacher/send", content="てから怎么用")
    check(st == 200 and n("chat_message", "learner='s1'") == 2, f"s1 问老师：{st}，两条记录")
    st, b, _ = post(s2, "/teacher/state", learner="s1")
    check(st == 200 and (b.get("state") or {}).get("talk") == [],
          "s2 进问老师页（请求体写 learner=s1）：对话是空的")
    st, b, _ = post(s1, "/teacher/state")
    check(len((b.get("state") or {}).get("talk") or []) == 2, "s1 看得到自己的两条")
    # 进度
    st, b1, _ = post(s1, "/progress/page")
    st2, b2, _ = post(s2, "/progress/page")
    check(st == 200 and st2 == 200 and json.dumps(b1, ensure_ascii=False) != json.dumps(b2, ensure_ascii=False),
          "进度页：两个人的不一样（s1 答过题）")
    # 教材偏好
    st, b, _ = post(s1, "/lesson/list", series="hanabira", learner="s2")
    pref = {r["learner"]: r["series"] for r in rows("SELECT learner, series FROM learner_pref")}
    check(pref == {"s1": "hanabira"}, f"教材偏好只记 s1（请求体的 learner=s2 不算）：{pref}")
    # 会话文件按人分（kg 的接口不用会话，引擎按用户名分文件）
    check(router._session_path("s1") != router._session_path("s2"), "会话文件按用户名分")

    # ------------------------------------------------------------------
    print("八、停用")
    st, b, _ = post(s2, "/quiz/state")
    check(st == 200, "对照：停用之前 s2 能用")
    st, b, _ = post(teacher, "/student/disable", username="s2")
    check(st == 200 and rows("SELECT disabled FROM user WHERE username='s2'")[0]["disabled"] == 1, "教师停用 s2")
    st, b, r = post(s2, "/quiz/state")
    check(st == 401 and COOKIE in r.headers.get("Set-Cookie", ""), f"s2 下一个请求就 401，并删了 cookie：{st}")
    st, b, _ = post(s2, "/auth/me")
    check(b.get("user") == "", "s2 的 /auth/me 是空的")
    st, b, _ = post(app.test_client(), "/auth/login", username="s2", password="s2-pass")
    check(st == 400 and b.get("error") == "用户名或密码不对", f"停用的登不上，说明跟密码错一样：{b}")
    st, b, _ = post(teacher, "/student/disable", username="t1")
    check(rows("SELECT disabled FROM user WHERE username='t1'")[0]["disabled"] == 0, "页面上停不了教师")
    st, b, _ = post(teacher, "/student/enable", username="s2")
    st, b, _ = post(s2, "/auth/login", username="s2", password="s2-pass")
    st2, *_ = post(s2, "/quiz/state")
    check(st == 200 and st2 == 200, "启用后能登录、能用")

    # ------------------------------------------------------------------
    print("九、改密码")
    st, b, _ = post(s2, "/auth/password", old_password="wrong-old", new_password="s2-new-1",
                    new_password2="s2-new-1")
    check(st == 400 and "旧密码" in b.get("error", ""), f"旧密码不对：{b}")
    st, b, _ = post(s2, "/auth/password", old_password="s2-pass", new_password="s2-new-1",
                    new_password2="s2-new-2")
    check(st == 400 and "不一样" in b.get("error", ""), f"两次不一样：{b}")
    st, b, _ = post(s2, "/auth/password", old_password="s2-pass", new_password="s2-new-1",
                    new_password2="s2-new-1", username="s1")
    check(st == 200, f"改密码：{st} {b}")
    st, *_ = post(app.test_client(), "/auth/login", username="s2", password="s2-pass")
    st2, *_ = post(app.test_client(), "/auth/login", username="s2", password="s2-new-1")
    st3, *_ = post(app.test_client(), "/auth/login", username="s1", password="s1-pass")
    check(st == 400 and st2 == 200 and st3 == 200,
          "旧密码登不上、新的能登；请求体里写 username=s1 改不到 s1")
    st, b, _ = post(teacher, "/student/reset", reset_user="s2", new_password="reset-pw-1")
    st2, *_ = post(app.test_client(), "/auth/login", username="s2", password="reset-pw-1")
    check(st == 200 and st2 == 200, f"教师重置 s2 的密码：{st} {st2}")
    st, b, _ = post(teacher, "/student/reset", reset_user="t1", new_password="reset-pw-1")
    check(st == 400, "重置不了教师的密码")
    st, b, _ = post(solo, "/auth/password", old_password="a", new_password="bbbbbb")
    check(st == 400, "单人模式没有账号，改密码 400")

    # ------------------------------------------------------------------
    print("十、登录限流")
    LIMITER.reset()
    c = app.test_client()
    for i in range(5):
        st, b, _ = post(c, "/auth/login", username="s1", password=f"wrong{i}")
    check(st == 400 and b.get("error") == "用户名或密码不对", "前 5 次：400 用户名或密码不对")
    st, b, r = post(c, "/auth/login", username="s1", password="s1-pass")
    check(st == 429 and "次数太多" in b.get("error", "") and COOKIE not in r.headers.get("Set-Cookie", ""),
          f"第 6 次密码对也 429：{b}")
    LIMITER.reset()
    for i in range(5):
        post(c, "/auth/login", username="ghost", password="x")
    st_ghost, b_ghost, _ = post(c, "/auth/login", username="ghost", password="x")
    check(st_ghost == 429 and b_ghost == b, "不存在的用户名锁住时，说明一字不差（看不出存不存在）")
    LIMITER.reset()
    for i in range(5):
        post(c, "/auth/login", username=f"guess{i}", password="x")
    st, b, _ = post(c, "/auth/login", username="s1", password="s1-pass")
    check(st == 429, "同一来源换着用户名错 5 次：也锁")
    LIMITER.reset()
    st, *_ = post(c, "/auth/login", username="s1", password="s1-pass")
    check(st == 200, "锁清掉（过期）后能登")
    # 过期：用 now 参数模拟时间
    from tools.auth import LoginLimiter
    lim = LoginLimiter(fails=5, seconds=300)
    for _ in range(5):
        lim.fail(["k"], now=1000)
    check(lim.locked(["k"], now=1200) and not lim.locked(["k"], now=1301), "锁 5 分钟，到点自己解开")
    lim.fail(["k"], now=1302)
    check(not lim.locked(["k"], now=1303), "解开后重新数，错一次不会马上又锁")
    LIMITER.reset()

    # ------------------------------------------------------------------
    print("十一、并入 me")
    st, b, _ = post(solo, "/quiz/start", pick_level="全部", pick_kind="全部")
    card = (b.get("state") or {}).get("card") or {}
    opts = card.get("options") or []
    post(solo, "/quiz/answer", choice=(opts[0]["key"] if opts else "A"), given="x")
    me_rows = n("attempt", "learner='me'")
    me_stat = (post(solo, "/quiz/state")[1].get("state") or {}).get("stat")
    check(me_rows >= 1, f"单人模式下 me 有作答 {me_rows} 条")
    code, out = kg_cli("并入", "me", "s9", "--库", str(db))
    check(code == 1 and "没有 s9" in out, "账号不在：拒绝")
    code, out = kg_cli("并入", "me", "s1", "--库", str(db))
    check(code == 1 and "已经有学习记录" in out and n("attempt", "learner='me'") == me_rows,
          "账号已有记录：不合并，me 的没动")
    post(teacher, "/student/create", username="s4", display_name="小四", password="s4-pass")
    baks = set(ws.glob("app.db.merge_*.bak"))
    code, out = kg_cli("并入", "me", "s4", "--库", str(db))
    new_baks = set(ws.glob("app.db.merge_*.bak")) - baks
    check(code == 0 and n("attempt", "learner='me'") == 0 and n("attempt", "learner='s4'") == me_rows
          and n("quiz_state", "learner='s4'") == 1, f"合并：{out.strip()[-80:]}")
    check(len(new_baks) == 1 and _count(list(new_baks)[0], "attempt", "me") == me_rows,
          "合并前的备份里 me 的记录还在")
    s4 = app.test_client()
    post(s4, "/auth/login", username="s4", password="s4-pass")
    st, b, _ = post(s4, "/quiz/state")
    check(st == 200 and me_stat and (b.get("state") or {}).get("stat") == me_stat
          and (post(solo, "/quiz/state")[1].get("state") or {}).get("stat") != me_stat,
          f"s4 登录后看到的是原来 me 的做题统计（{me_stat}），单人模式的 me 从头开始")
    code, out = kg_cli("并入", "me", "s4", "--库", str(db))
    check(code == 0 and "没有学习记录" in out, "再来一次：me 没东西了，什么都不做")

    # ------------------------------------------------------------------
    print("十二、开关的接线")
    import gen.project
    import kg.__main__ as kgmain
    seen = {}
    old_main, old_setup = gen.project.main, kgmain.setup
    gen.project.main = lambda argv: seen.update(argv=argv) or 0
    kgmain.setup = lambda quiet=False: 0
    try:
        for argv, env, want in ((["--登录"], {}, True), ([], {"KG_LOGIN": "1"}, True),
                                ([], {"KG_LOGIN": "0"}, False), ([], {}, False)):
            old_env = dict(os.environ)
            os.environ.pop("KG_LOGIN", None)
            os.environ.update(env)
            try:
                with redirect_stdout(io.StringIO()) as buf:
                    kgmain.main(argv)
            finally:
                os.environ.clear()
                os.environ.update(old_env)
            got = "--登录" in seen["argv"]
            check(got == want and ("多人模式" in buf.getvalue()) == want,
                  f"py -m kg {argv} {env} → gen run {'带' if got else '不带'} --登录")
    finally:
        gen.project.main, kgmain.setup = old_main, old_setup

    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    path = str(ROOT / "kg" / "app.pyw")
    mod = module_from_spec(spec_from_loader("kg_app_pyw", SourceFileLoader("kg_app_pyw", path)))
    mod.__spec__.loader.exec_module(mod)
    got = {}
    old = gen.project.make_app
    gen.project.make_app = lambda root, real=False, **kw: got.update(kw) or (None, None)
    try:
        with redirect_stdout(io.StringIO()):
            _, _, title = mod.build_app(["--mock"], {"KG_LOGIN": "1"})
            check(got.get("login") is True and "多人" in title, f"app.pyw + KG_LOGIN=1：login=True，标题 {title}")
            got.clear()
            _, _, title = mod.build_app(["--mock"], {})
            check("login" not in got, "app.pyw 默认：不传 login（单人）")
    finally:
        gen.project.make_app = old

    from tools.dsl import DSLError
    from tools.dsl_http import Router, listen_warning
    plain = Path(tempfile.mkdtemp(prefix="nologin_"))
    (plain / "routes").mkdir()
    (plain / "routes" / "a.zs").write_text("接口 POST /a\n  返回 ok\n结束\n", encoding="utf-8")
    try:
        Router(plain / "routes", plain, plain / "sessions", login=True)
        check(False, "没写「认证」的项目开登录应该报错")
    except DSLError as e:
        check("认证 可选" in str(e), f"没写「认证」的项目开登录：报错 {str(e)[:40]}")
    check(listen_warning("127.0.0.1", True) == "", "本机监听不提醒")
    w = listen_warning("0.0.0.0", True)
    check("https" in w and "--安全cookie" in w, "0.0.0.0 + 登录：提醒 https、--安全cookie")
    _, r2 = make_app_secure(ws)
    c = r2.app().test_client()
    st, b, r = post(c, "/auth/login", username="s1", password="s1-pass")
    check(st == 200 and "Secure" in r.headers.get("Set-Cookie", ""), "--安全cookie：cookie 带 Secure")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


def make_app_secure(ws):
    from gen.project import make_app
    LIMITER.reset()
    return make_app(ws, real=False, login=True, secure_cookie=True)


def _count(dbfile, table, learner):
    con = sqlite3.connect(dbfile)
    try:
        return con.execute(f"SELECT count(*) FROM {table} WHERE learner = ?", (learner,)).fetchone()[0]
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
