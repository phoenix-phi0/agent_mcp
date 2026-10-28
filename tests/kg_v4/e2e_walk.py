#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kg_v4 浏览器走查（K97）：起真服务、用真浏览器把学生端/教师端每个界面各开一遍，
再走一遍科目管理的完整流程。收进仓库，不依赖 /tmp 里的旧走查脚本。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/e2e_walk.py
    .venv/bin/python tests/kg_v4/e2e_walk.py --no-subject-mgmt   # 基线（合并前）也该全过

浏览器：playwright + 系统 Chrome（/usr/bin/google-chrome 作 executable_path，
不 playwright install 下载浏览器）。没装 playwright 就打「跳过」并退出码 2
（环境缺依赖，不算走查失败）。

自己搭环境：拷 kg_v4 到临时目录（不带 app.db / web / uploads），裁小的内容
（同 test_project 口径）经 init_data 灌库，建测试账号 t1、t2（教师）、s1、s2
（学生；口令是脚本内常量，只用于本走查自建的临时库，不读任何真实凭据），
1 号科目按 migrate_subject 的口径生成（负责人 = id 最小的教师 = t1）；
`gen run --登录` 离线假模型、临时端口；结束按进程组停服、删临时目录。

断言与数据内容无关：不数具体条数，只查「界面开得开、结构对不对、流程通不通」。

覆盖（--no-subject-mgmt 去掉带 * 的）：
  1.  学生端根地址 / 落在问老师
  2.  学生端 6 个界面都能打开且无 JS 错误（忽略 unpkg vue-flow 的
      「production is not defined」告警，见 kg_v4/README.md）
  3.  教师端 6 个界面都能打开（学情、教师助手、学生管理、科目管理*、AI老师设定、教材导入）
  4.  导航分组：学生端右侧「看看」、教师端右侧「管理」
  5.* 科目管理流程：t1 建科目（私有草稿）→ 成员浮层加 t2 协作 → 分配 s1 →
      启用 → s1 顶栏可切到新科目 → t2 在该科目行只见「成员」→ t1 停用后
      s1 回落日语 → 停用日语提示 409 原文（先打接口取原文，再点按钮对文字）
  6.  390px 视口：学生端首页与科目管理页* 不横向溢出
输出「通过 x/共 y」，失败列原因；退出码 0 全过 / 1 有失败 / 2 环境起不来。
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
# 仓库自己的解释器：起服务、init_data 都用它（脚本本身可以在任何装了
# playwright 的解释器下跑，比如装在 /tmp venv 里的那份）
REPO_PY = REPO / ".venv" / "bin" / "python"

IGNORE_CONSOLE = ("production is not defined",)   # unpkg vue-flow 的兼容告警，见 README

STUDENT_PAGES = ["问老师", "做题", "默写", "教材", "知识图谱", "学习进度"]
TEACHER_PAGES = ["学情", "教师助手", "学生管理", "科目管理", "AI老师设定", "教材导入"]
TEACHER_USER = "t1"
STUDENT_NAME = "s1"
TEST_PASSWORD = "k97-walk-临时口令"     # 只进本走查自建的临时库
SUBJ_CODE = "walk97"
SUBJ_NAME = "走查物理"


class Checks:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.fails = []

    def __call__(self, ok, msg, detail=""):
        if ok:
            self.passed += 1
            print(f"  ✓ {msg}")
        else:
            self.failed += 1
            self.fails.append(msg + (f"\n      {detail}" if detail else ""))
            print(f"  ✗ {msg}\n      {detail}")
        return ok

    def done(self):
        total = self.passed + self.failed
        print(f"\n通过 {self.passed}/共 {total}")
        for f in self.fails:
            print(f"  失败：{f}")
        return 1 if self.failed else 0


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def build_workspace(tmp, src):
    """拷 kg_v4、裁内容、建账号、灌库。返回项目目录。"""
    proj = tmp / "kg_v4"
    shutil.copytree(src, proj, ignore=shutil.ignore_patterns(
        "app.db", "web", "uploads", "sessions", ".auth_secret", "__pycache__"))
    # 裁小的内容（test_project 口径）：走查不数条数，够页面有东西就行
    content = tmp / "content"
    shutil.copytree(REPO / "kg" / "content", content,
                    ignore=shutil.ignore_patterns("translate", "series"))
    for f in ("words.jsonl", "words_jlpt.jsonl"):
        p = content / f
        lines = p.read_text(encoding="utf-8").splitlines()[:100]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    quiz = tmp / "quiz_empty"
    quiz.mkdir()
    # 账号要赶在 init_data 前建好：它里面的 ensure_subject（migrate_subject 口径）
    # 才会把学生登记进 1 号科目、教师登记为协作；负责人 = id 最小的教师 = t1。
    # 这步用仓库解释器的子进程做（要 Flask 和 tools.auth，脚本本身用的解释器不一定有）
    accounts = [(TEACHER_USER, "teacher"), ("t2", "teacher"),
                (STUDENT_NAME, "student"), ("s2", "student")]
    code = (
        "import json,sqlite3,sys,time;sys.path.insert(0,%r);"
        "from gen.project import ensure_db;from pathlib import Path;"
        "proj=Path(sys.argv[1]);print(ensure_db(proj));"
        "from tools.auth import hash_password;"
        "now=time.strftime('%%Y-%%m-%%d %%H:%%M:%%S');"
        "con=sqlite3.connect(proj/'app.db');"
        "sql='INSERT INTO account_user(username,password_hash,display_name,role,disabled,created_at) '"
        "'VALUES(?,?,?,?,0,?)';"
        "[con.execute(sql,(u,hash_password(sys.argv[2]),u,role,now)) "
        "for u,role in json.loads(sys.argv[3])];"
        "con.commit();con.close()" % str(REPO))
    r = subprocess.run([str(REPO_PY), "-c", code, str(proj), TEST_PASSWORD,
                        json.dumps(accounts)], cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"建账号失败：{(r.stdout + r.stderr)[-500:]}")
    cmd = [str(REPO_PY), str(REPO / "kg_v4" / "setup" / "init_data.py"), str(proj),
           "--content", str(content), "--quiz", str(quiz)]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"init_data 失败：{(r.stdout + r.stderr)[-500:]}")
    return proj


def start_server(proj, port, log):
    """gen run --登录，离线假模型，临时端口。返回 Popen（独立进程组）。"""
    proc = subprocess.Popen(
        [str(REPO_PY), "-m", "gen", "run", str(proj), "--登录",
         "--port", str(port), "--不开浏览器", "--host", "127.0.0.1"],
        cwd=REPO, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"服务起完就退了（退出码 {proc.returncode}）")
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close()
            return proc
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("60 秒端口还没起来（日志在临时目录 server.log）")


def stop_server(proc):
    """按进程组杀：gen run 会派子进程握着端口，只杀父进程会留下孤儿。"""
    if proc is None or proc.poll() is not None:
        return
    for sig in (15, 9):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


# ---------------------------------------------------------------- 浏览器侧
_ALL_PAGES = []      # 本进程开过的所有页面，错误收集按它来


def snapshot(marks):
    """记住此刻各页已见错误数；之后 drain_errors(marks) 收新出现的。"""
    marks.update({p: len(p._js_errors) for p in _ALL_PAGES})
    return marks


def drain_errors(marks):
    """返回上次 snapshot/drain 之后新出现的、不忽略的 JS 错误。"""
    out = []
    for p in list(_ALL_PAGES):
        seen = marks.get(p, 0)
        marks[p] = len(p._js_errors)
        out += [f"[{p._tag}] {t}" for t in p._js_errors[seen:]]
    return out


def attach(page, tag):
    page._js_errors = []
    page._tag = tag
    page._allowed_status = ()   # 故意打的 HTTP 状态（比如日语停用的 409）不算 JS 错误

    def console(msg):
        if msg.type != "error" or any(x in msg.text for x in IGNORE_CONSOLE):
            return
        if "Failed to load resource" in msg.text and any(
                f"status of {c}" in msg.text for c in page._allowed_status):
            return
        page._js_errors.append(msg.text[:300])

    def pageerror(e):
        t = str(e)[:300]
        if not any(x in t for x in IGNORE_CONSOLE):
            page._js_errors.append(t)

    page.on("console", console)
    page.on("pageerror", pageerror)
    return page


def screen_name(page):
    return page.evaluate(
        "decodeURIComponent(location.hash.replace(/^#\\/?/, '')).split('?')[0]")


def wait_screen(page, name, timeout=15000):
    page.wait_for_function(
        "n => decodeURIComponent(location.hash.replace(/^#\\/?/, '')).split('?')[0] === n",
        arg=name, timeout=timeout)


def login(page, base, user, end=""):
    """打开某一端，被 401 弹到登录页就登录；返回时顶栏已是这个人。"""
    page.goto(base + end, wait_until="domcontentloaded")
    page.wait_for_selector("form.screen", timeout=20000)
    if page.locator('form.screen input[type="password"]').count():
        page.locator('form.screen input:not([type="password"])').first.fill(user)
        page.locator('form.screen input[type="password"]').first.fill(TEST_PASSWORD)
        page.locator('form.screen button:has-text("登录")').first.click()
    page.wait_for_function(
        "u => { const el = document.querySelector('.nav-user-name');"
        " return el && el.textContent.trim() === u; }",
        arg=user, timeout=20000)
    return page


def nav_links(page):
    names = page.eval_on_selector_all(
        "nav a[href='#']", "els => els.map(e => e.textContent.trim())")
    return sorted(n for n in names if n != "改密码")


def visit(page, name, marks, settle=1200):
    """点导航开一个界面，等地址切过去、进入时的请求落定，收 JS 错误。"""
    page.locator("nav a[href='#']", has_text=name).first.click()
    wait_screen(page, name)
    page.wait_for_timeout(settle)
    return drain_errors(marks)


def toast(page, kind="", timeout=8000):
    """等提示条出来、读文字、点掉它（不点的话下一次断言会读到旧的）。"""
    sel = ".toast" + ("-no" if kind == "no" else "")
    page.wait_for_selector(sel, timeout=timeout)
    text = page.locator(sel).first.inner_text().strip()
    page.locator(sel).first.click()
    page.wait_for_selector(".toast", state="detached", timeout=4000)
    return text


def clear_toast(page):
    """把上一条还挂着的提示条点掉，免得下一次读到旧字。"""
    if page.locator(".toast").count():
        page.locator(".toast").first.click()
        page.wait_for_selector(".toast", state="detached", timeout=4000)


def selected_label(page, sel):
    return page.evaluate(
        "s => { const e = document.querySelector(s);"
        " return e && e.selectedOptions[0] ? e.selectedOptions[0].textContent.trim() : ''; }",
        sel)


def no_overflow(page, label, ck):
    w = page.evaluate(
        "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)")
    inner = page.evaluate("window.innerWidth")
    ck(w <= inner + 1, f"390px 不横向溢出：{label}", f"scrollWidth={w} > innerWidth={inner}")


def walk_student(s1, base, ck, marks, subject_mgmt):
    ck(screen_name(s1) in ("", "问老师")
       and s1.locator("nav a.active", has_text="问老师").count() == 1,
       "学生端根地址 / 落在问老师", f"hash={screen_name(s1)!r}")
    links = nav_links(s1)
    ck(links == sorted(STUDENT_PAGES), "学生端导航 6 项齐全", links)
    ck(s1.locator(".nav-side-h", has_text="看看").count() == 1,
       "学生端导航分组「看看」在")
    for n in STUDENT_PAGES:
        err = visit(s1, n, marks)
        ck(not err, f"学生端「{n}」打开且无 JS 错误", err)


def student_switch(s1, ck, marks):
    """建科目、分配、启用之后：s1 顶栏可切到新科目（要刷新拉新 auth_me）。"""
    s1.reload(wait_until="domcontentloaded")
    s1.wait_for_function(
        "u => { const el = document.querySelector('.nav-user-name');"
        " return el && el.textContent.trim() === u; }",
        arg=STUDENT_NAME, timeout=20000)
    s1.wait_for_timeout(500)
    sw = s1.locator("select.nav-subject")
    ck(sw.count() == 1 and sw.is_visible(),
       "s1 顶栏出现科目下拉（可见科目多于 1 个）")
    sw.select_option(label=SUBJ_NAME)
    s1.wait_for_timeout(1500)            # switchSubject 提交后整页刷新
    s1.wait_for_function(
        "u => { const el = document.querySelector('.nav-user-name');"
        " return el && el.textContent.trim() === u; }",
        arg=STUDENT_NAME, timeout=20000)
    ck(selected_label(s1, "select.nav-subject") == SUBJ_NAME,
       "s1 顶栏可切到新科目，刷新后仍是它",
       "下拉选项：「" + selected_label(s1, "select.nav-subject") + "」")
    err = drain_errors(marks)
    ck(not err, "s1 页面整个流程无 JS 错误", err)


def walk_teacher(page, base, ck, marks, subject_mgmt):
    links = nav_links(page)
    expect = sorted(p for p in TEACHER_PAGES if subject_mgmt or p != "科目管理")
    ck(links == expect, f"教师端导航 {len(expect)} 项齐全", links)
    ck(page.locator(".nav-side-h", has_text="管理").count() == 1,
       "教师端导航分组「管理」在")
    for n in expect:
        err = visit(page, n, marks)
        ck(not err, f"教师端「{n}」打开且无 JS 错误", err)


def subject_flow(t1, base, ck, marks):
    """科目管理前半段（都在 t1 的教师端页面上做）。"""
    visit(t1, "科目管理", marks)
    row = t1.locator("tr", has_text=SUBJ_CODE)

    # 1) t1 建科目：新建 → 浮层填编码/名称/类型 → 保存
    t1.locator('button:has-text("新建科目")').first.click()
    t1.wait_for_selector(".overlay", timeout=8000)
    t1.locator('.overlay label.field:has-text("编码") input').first.fill(SUBJ_CODE)
    t1.locator('.overlay label.field:has-text("名称") input').first.fill(SUBJ_NAME)
    t1.locator(".overlay label.opt", has_text="通用").first.click()
    t1.locator('.overlay button:has-text("保存")').first.click()
    t1.wait_for_selector(".overlay", state="detached", timeout=10000)
    ck(toast(t1) == "科目已保存", "t1 建科目：保存成功有提示")
    ck(row.count() == 1 and SUBJ_NAME in row.inner_text()
       and "私有" in row.inner_text() and "草稿" in row.inner_text()
       and "负责" in row.inner_text(),
       "新科目在表里：私有、草稿，t1 是负责", row.inner_text()[:200])

    # 2) 成员浮层：加 t2 协作、批量分配 s1
    row.locator('button:has-text("成员")').first.click()
    t1.wait_for_selector(".overlay", timeout=8000)
    t1.locator('.overlay label.field:has-text("教师") select').first.select_option("t2")
    t1.locator('.overlay label.field:has-text("角色") select').first.select_option("协作")
    t1.locator('.overlay button:has-text("加入")').first.click()
    t1.wait_for_selector('.overlay tr:has-text("t2")', timeout=10000)
    ck(t1.locator('.overlay tr:has-text("t2")', has_text="协作").count() == 1,
       "t2 加进新科目，角色协作")
    batch = t1.locator(".overlay section.group", has=t1.locator("textarea")).first
    batch.locator("textarea").fill(STUDENT_NAME)
    batch.locator('button:has-text("分配")').first.click()
    t1.wait_for_selector(f'.overlay tr:has-text("{STUDENT_NAME}")', timeout=10000)
    ck(t1.locator(".overlay table tr", has_text=STUDENT_NAME).count() >= 1,
       "s1 分配进新科目")
    t1.locator('.overlay button:has-text("返回")').first.click()
    t1.wait_for_selector(".overlay", state="detached", timeout=8000)

    # 3) 启用
    clear_toast(t1)
    row.locator('button:has-text("启用")').first.click()
    got = toast(t1)
    ck(got == "科目已启用", "t1 启用新科目有提示", f"提示条：「{got}」")
    ck("启用" in row.inner_text(), "新科目状态变启用", row.inner_text()[:200])


def subject_flow_after(t2, s1, t1, ck, marks):
    """科目管理后半段：t2 权限、停用回落、日语 409。"""
    # t2 在新科目行只见「成员」
    visit(t2, "科目管理", marks)
    t2row = t2.locator("tr", has_text=SUBJ_CODE)
    ck(t2row.count() == 1 and t2row.locator('button:has-text("成员")').count() == 1,
       "t2 在新科目行有「成员」按钮")
    extra = [b for b in ("编辑", "启用", "停用", "设为公共", "设为私有")
             if t2row.locator(f'button:has-text("{b}")').count()]
    ck(not extra, "t2 在新科目行只有「成员」，没有负责人按钮", f"多了：{extra}")

    # 停用后 s1 回落日语
    clear_toast(t1)
    t1.locator("tr", has_text=SUBJ_CODE).locator('button:has-text("停用")').first.click()
    got = toast(t1)
    ck(got == "科目已停用", "t1 停用新科目有提示", f"提示条：「{got}」")
    s1.reload(wait_until="domcontentloaded")
    s1.wait_for_selector("nav", timeout=20000)
    s1.wait_for_timeout(800)
    ck(selected_label(s1, "select.nav-subject") != SUBJ_NAME,
       "新科目停用后，s1 顶栏不再停在新科目（回落日语）",
       "下拉选项：「" + (selected_label(s1, "select.nav-subject") or "（下拉已隐藏）") + "」")

    # 日语（1 号科目）不能停用：提示条显示 409 原文（先取原文再对，不写死）
    t1._allowed_status = ("409",)   # 故意打的 409，不算 JS 错误
    status, body = t1.evaluate("""async () => {
      const r = await fetch('/subject/manage/disable', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'subject_disable', form: {subj_id: '1'}})});
      return [r.status, await r.json()];
    }""")
    ck(status == 409 and body.get("error"), "接口层：停用日语回 409 且有原文",
       f"{status} {body}")
    clear_toast(t1)
    t1.locator("tr", has_text="日语语法").locator('button:has-text("停用")').first.click()
    got = toast(t1, kind="no")
    ck(got == body.get("error"), "页面上停用日语：提示条显示 409 原文",
       f"页面：「{got}」")


def main(argv=None):
    ap = argparse.ArgumentParser(description="kg_v4 浏览器走查（真浏览器，自己起服务）")
    ap.add_argument("--no-subject-mgmt", dest="no_subject", action="store_true",
                    help="跳过科目管理相关断言（给合并前的基线跑，证明脚本本身没错）")
    ap.add_argument("--src", default=str(REPO / "kg_v4"),
                    help="被走查的 kg_v4 目录（默认仓库里的；基线 worktree 传它的）")
    ap.add_argument("--keep", action="store_true", help="留着临时目录（排查用）")
    a = ap.parse_args(argv)
    subject_mgmt = not a.no_subject

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("跳过：没装 playwright（pip install playwright 到临时 venv，"
              "Chrome 用系统的 /usr/bin/google-chrome）。环境缺依赖，不算走查失败。")
        return 2
    if not Path("/usr/bin/google-chrome").exists():
        print("跳过：/usr/bin/google-chrome 不在。环境缺依赖，不算走查失败。")
        return 2

    ck = Checks()
    tmp = Path(tempfile.mkdtemp(prefix="k97_walk_"))
    port = free_port()
    proc = None
    print(f"临时目录 {tmp}，端口 {port}")
    try:
        proj = build_workspace(tmp, Path(a.src))
        with open(tmp / "server.log", "w") as log:
            proc = start_server(proj, port, log)
            base = f"http://127.0.0.1:{port}"
            print("服务起来了")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path="/usr/bin/google-chrome", headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"])
                _ALL_PAGES.clear()

                def new_page(ctx, tag):
                    p = attach(ctx.new_page(), tag)
                    _ALL_PAGES.append(p)
                    return p

                # ---- 学生端（s1）----
                s1 = new_page(browser.new_context(), "s1")
                login(s1, base, STUDENT_NAME)
                marks = snapshot({})
                walk_student(s1, base, ck, marks, subject_mgmt)

                # ---- 教师端（t1）----
                t1 = new_page(browser.new_context(), "t1")
                login(t1, base, TEACHER_USER, end="/teacher")
                snapshot(marks)      # 登录前 401 跳登录页是预期行为，不计 JS 错误
                walk_teacher(t1, base, ck, marks, subject_mgmt)
                if subject_mgmt:
                    subject_flow(t1, base, ck, marks)
                    student_switch(s1, ck, marks)

                    # ---- t2 教师端 ----
                    t2 = new_page(browser.new_context(), "t2")
                    login(t2, base, "t2", end="/teacher")
                    marks_t2 = snapshot({})   # 同 t1：登录前的 401 不计
                    subject_flow_after(t2, s1, t1, ck, marks)
                    err = drain_errors(marks_t2)
                    ck(not err, "t2 页面无 JS 错误", err)

                # ---- 390px 视口 ----
                m = new_page(browser.new_context(viewport={"width": 390, "height": 844}),
                             "390-s1")
                login(m, base, STUDENT_NAME)
                m.wait_for_timeout(800)
                no_overflow(m, "学生端首页", ck)
                if subject_mgmt:
                    mt = new_page(
                        browser.new_context(viewport={"width": 390, "height": 844}),
                        "390-t1")
                    login(mt, base, TEACHER_USER, end="/teacher")
                    mt.evaluate("location.hash = encodeURIComponent('科目管理')")
                    mt.wait_for_timeout(1200)
                    no_overflow(mt, "科目管理页", ck)
                browser.close()
    except Exception as e:
        ck(False, "走查中途异常", f"{type(e).__name__}: {e}")
    finally:
        stop_server(proc)
        if a.keep:
            print(f"临时目录留着：{tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    return ck.done()


if __name__ == "__main__":
    sys.exit(main())
