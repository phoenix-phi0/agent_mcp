#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kg_v4 浏览器走查（K97）：起真服务、用真浏览器把学生端/教师端每个界面各开一遍，
再走一遍科目管理的完整流程。收进仓库，不依赖 /tmp 里的旧走查脚本。

    cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/e2e_walk.py
    .venv/bin/python tests/kg_v4/e2e_walk.py --no-subject-mgmt   # 基线（合并前）也该全过
    .venv/bin/python tests/kg_v4/e2e_walk.py --no-kg-mgmt       # 图谱管理未合并时跑全过

浏览器：playwright + 系统 Chrome（/usr/bin/google-chrome 作 executable_path，
不 playwright install 下载浏览器）。没装 playwright 就打「跳过」并退出码 2
（环境缺依赖，不算走查失败）。

自己搭环境：拷 kg_v4 到临时目录（不带 app.db / web / uploads），裁小的内容
（同 test_project 口径）经 init_data 灌库，建测试账号 t1、t2（教师）、s1、s2
（学生；口令是脚本内常量，只用于本走查自建的临时库，不读任何真实凭据），
1 号科目按 migrate_subject 的口径生成（负责人 = id 最小的教师 = t1）；
`gen run --登录` 离线假模型、临时端口；结束按进程组停服、删临时目录。

断言与数据内容无关：不数具体条数，只查「界面开得开、结构对不对、流程通不通」。

覆盖（--no-subject-mgmt 去掉带 * 的，--no-kg-mgmt 去掉带 ** 的）：
  1.  学生端根地址 / 落在问老师
  2.  学生端 6 个界面都能打开且无 JS 错误（忽略 unpkg vue-flow 的
      「production is not defined」告警，见 kg_v4/README.md）
  3.  教师端 6 个界面都能打开（学情、教师助手、学生管理、科目管理*、AI老师设定、教材导入；
      图谱管理** 合并后是第 7 个）
  3b. 教师助手草稿（M4-P1）：发「出3道题」→ 消息里出现 确认 / 放弃 按钮 → 点确认 → 待确认列表
      状态「已执行」→ 撤销 →「已撤销」；发传达草稿 → 放弃 →「已放弃」（假模型走 DSL_MOCK_SCRIPT）
      （M4-P1b）设定草稿确认 → 列表「已执行」→ AI老师设定页可见新值；知识点草稿确认 → 列表「已执行」
  4.  导航分组：学生端右侧「看看」、教师端右侧「管理」
  5.* 科目管理流程：t1 建科目（私有草稿）→ 成员浮层加 t2 协作 → 分配 s1 →
      启用 → s1 顶栏可切到新科目 → t2 在该科目行只见「成员」→ t1 停用后
      s1 回落日语 → 停用日语提示 409 原文（先打接口取原文，再点按钮对文字）
  6.  390px 视口：学生端首页与科目管理页*、图谱管理页** 不横向溢出
  7.** 图谱管理流程：t1 建知识点×2 → 建条目 → 加前置边 → 加反向的成环边看到
      400 提示 → 导入预检（含一行错）确认导入按钮不出现 → 导出文本出现；
      协作教师 t2 可写；公共科目其他教师 t3 只读（看不到写按钮）。t3 是
      init_data 之后才建的账号，所以没被登记进 1 号科目（迁移会把先前已有
      的教师全登记成协作）。断言与数据内容无关：只认本段自建的 walk99.* 编号
输出「通过 x/共 y」，失败列原因；退出码 0 全过 / 1 有失败 / 2 环境起不来。
"""
import argparse
import json
import os
import shutil
import socket
import sqlite3
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
# 图谱管理段（K99b）自建的编号/名称：断言只认这些，与种子数据内容无关
KG_P1, KG_T1T = "walk99.p1", "走查点甲"
KG_P2, KG_T2T = "walk99.p2", "走查点乙"
KG_I1, KG_IT1 = "walk99.i1", "走查条目一"
KG_T2P = "walk99.t2p"
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


def build_workspace(tmp, src, kg_mgmt=False):
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
    if kg_mgmt:
        # t3 必须赶在 init_data 之后建：迁移会把之前就存在的教师全登记成 1 号
        # 科目的协作（can_write=1）；图谱管理段要一个「没登记的公共科目其他教师」。
        r = subprocess.run([str(REPO_PY), "-c", code, str(proj), TEST_PASSWORD,
                            json.dumps([("t3", "teacher")])],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"建 t3 失败：{(r.stdout + r.stderr)[-500:]}")
    return proj


def start_server(proj, port, log, env=None):
    """gen run --登录，离线假模型，临时端口。返回 Popen（独立进程组）。env：额外环境变量（如 DSL_MOCK_SCRIPT）。"""
    proc = subprocess.Popen(
        [str(REPO_PY), "-m", "gen", "run", str(proj), "--登录",
         "--port", str(port), "--不开浏览器", "--host", "127.0.0.1"],
        cwd=REPO, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        env={**os.environ, **(env or {})})
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


def track_posts(page, path):
    """从现在起记下发往 path 的 POST；返回 (记录列表, 停止函数)。"""
    hits = []

    def on_req(r):
        if r.method == "POST" and r.url.split("?")[0].endswith(path):
            hits.append(r.url)
    page.on("request", on_req)
    return hits, lambda: page.remove_listener("request", on_req)


def hash_of(page):
    """解码后的地址 #… 部分（参数是 URLSearchParams 编的，+ 还原成空格）。"""
    return page.evaluate("decodeURIComponent(location.hash.replace(/\\+/g, ' '))")


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


def walk_teacher(page, base, ck, marks, subject_mgmt, kg_mgmt=False):
    links = nav_links(page)
    expect = sorted(p for p in TEACHER_PAGES if subject_mgmt or p != "科目管理")
    kg_ok = kg_mgmt
    if kg_mgmt:
        if "图谱管理" in links:
            expect = sorted(expect + ["图谱管理"])
        else:
            # 实现未合并：只报一条清楚的失败，后面的图谱管理段整体跳过（不然会 30 秒超时崩掉）
            kg_ok = False
            ck(False, "教师端导航有「图谱管理」页（实现缺失？未合并时请用 --no-kg-mgmt）", links)
    ck(links == expect, f"教师端导航 {len(expect)} 项齐全", links)
    ck(page.locator(".nav-side-h", has_text="管理").count() == 1,
       "教师端导航分组「管理」在")
    for n in expect:
        err = visit(page, n, marks)
        ck(not err, f"教师端「{n}」打开且无 JS 错误", err)
    return kg_ok


def write_assist_mock(proj, tmp):
    """教师助手段用的假模型规则（DSL_MOCK_SCRIPT）：意图分类和草稿生成各回一份合法 JSON。
    出题要用库里真有的条目编号，所以建好库之后从 app.db 取一个。→ 规则文件路径"""
    con = sqlite3.connect(proj / "app.db")
    try:
        row = con.execute("SELECT code FROM kg_item ORDER BY code LIMIT 1").fetchone()
    finally:
        con.close()
    if not row:
        raise RuntimeError("库里没有条目，出题草稿造不出来")
    qs = [{"stem": f"走查题{i}", "options": ["甲", "乙", "丙"], "answer": "B", "explain": "走查", "item_code": row[0]}
          for i in (1, 2, 3)]
    rules = [
        # 放最前：分类器提示里带着【最近对话】，前面几轮的「走查加知识点」等字样会让靠前的规则先中
        {"when": ["意图分类器", "总结走查附件"],
         "reply": json.dumps({"intent": "file_qa"}, ensure_ascii=False)},
        {"when": ["意图分类器", "走查加知识点"],
         "reply": json.dumps({"intent": "make_draft", "draft_kind": "kg_add"}, ensure_ascii=False)},
        {"when": ["往图谱里加知识点", "points"],
         "reply": json.dumps({"title": "走查加知识点", "points": [{"code": "WK134P", "title": "走查知识点"}], "items": [], "edges": []},
                             ensure_ascii=False)},
        {"when": ["意图分类器", "走查记设定"],
         "reply": json.dumps({"intent": "make_draft", "draft_kind": "setting_save"}, ensure_ascii=False)},
        {"when": ["起草AI老师设定", "settings"],
         "reply": json.dumps({"title": "走查记设定", "settings": [{"kind": "memory", "content": "走查设定内容K134"}]}, ensure_ascii=False)},
        {"when": ["意图分类器", "发传达"],
         "reply": json.dumps({"intent": "make_draft", "draft_kind": "relay_add", "student": "s1"}, ensure_ascii=False)},
        {"when": ["意图分类器", "出3道题"],
         "reply": json.dumps({"intent": "make_draft", "draft_kind": "quiz_add", "count": "3"}, ensure_ascii=False)},
        {"when": ["【资料】", "走查附件正文"], "reply": "走查附件回答：这份资料讲了走查附件正文。"},
        {"when": ["item_code", "questions"],
         "reply": json.dumps({"title": "走查出3道题", "questions": qs}, ensure_ascii=False)},
        {"when": ["must_info", "urgency"],
         "reply": json.dumps({"title": "给s1发传达", "students": ["s1"], "must_info": "周五小测", "facts": "",
                              "urgency": "normal", "rounds": 2}, ensure_ascii=False)},
    ]
    f = tmp / "assist_mock.json"
    f.write_text(json.dumps({"rules": rules}, ensure_ascii=False), encoding="utf-8")
    return f


def assist_send(page, text):
    box = page.locator("textarea").last
    box.fill(text)
    page.locator("button", has_text="发送").last.click()


def assist_flow(t1, ck, marks):
    """M4-P1：教师助手草稿。发「出3道题」→ 消息里出现草稿按钮 → 点确认 → 待确认列表变「已执行」→ 撤销 → 「已撤销」；
    发传达草稿 → 放弃 → 「已放弃」。假模型走 write_assist_mock 的规则。"""
    name = "教师助手草稿"
    try:
        t1.evaluate("location.hash = encodeURIComponent('教师助手')")
        wait_screen(t1, "教师助手")
        t1.wait_for_timeout(1500)
        assist_send(t1, "出3道题")
        btn = t1.locator(".smsg-actions button", has_text="确认")
        btn.first.wait_for(timeout=90000)
        labels = t1.locator(".smsg-actions button").all_inner_texts()
        ck("确认" in labels and "放弃" in labels, f"{name}：出题草稿消息里有 确认 / 放弃 按钮", labels)
        t1.get_by_text("待确认", exact=True).first.wait_for(timeout=8000)
        ck(t1.locator("table tbody tr, .list-row, tr").filter(has_text="待确认").count() >= 1,
           f"{name}：右边待确认列表出现这份草稿（状态待确认）")
        btn.first.click()
        t1.locator("tr", has_text="已执行").first.wait_for(timeout=30000)
        ck(True, f"{name}：点确认后列表状态变「已执行」")
        t1.locator("tr", has_text="已执行").first.get_by_text("撤销", exact=True).click(timeout=8000)
        t1.locator("tr", has_text="已撤销").first.wait_for(timeout=30000)
        ck(True, f"{name}：点撤销后列表状态变「已撤销」")
        # 传达草稿 → 放弃
        assist_send(t1, "给s1发传达：周五小测")
        t1.locator("tr", has_text="待确认").first.wait_for(timeout=90000)
        t1.locator("tr", has_text="待确认").first.get_by_text("放弃", exact=True).click(timeout=8000)
        t1.locator("tr", has_text="已放弃").first.wait_for(timeout=30000)
        ck(True, f"{name}：传达草稿点放弃后状态变「已放弃」")
        # P1b：设定草稿确认后，AI 老师设定页可见新值
        assist_send(t1, "走查记设定：记住这条")
        row = t1.locator("tr", has_text="走查记设定").filter(has_text="待确认")
        row.first.wait_for(timeout=90000)
        row.first.get_by_text("确认", exact=True).click(timeout=8000)
        t1.locator("tr", has_text="走查记设定").filter(has_text="已执行").first.wait_for(timeout=30000)
        t1.evaluate("location.hash = encodeURIComponent('AI老师设定')")
        wait_screen(t1, "AI老师设定")
        t1.get_by_text("走查设定内容K134").first.wait_for(timeout=15000)
        ck(True, f"{name}：设定草稿确认后 AI老师设定页可见新值")
        # P1b：知识点草稿确认后列表状态变「已执行」
        t1.evaluate("location.hash = encodeURIComponent('教师助手')")
        wait_screen(t1, "教师助手")
        t1.wait_for_timeout(1500)
        assist_send(t1, "走查加知识点：加一个知识点")
        row = t1.locator("tr", has_text="走查加知识点").filter(has_text="待确认")
        row.first.wait_for(timeout=90000)
        row.first.get_by_text("确认", exact=True).click(timeout=8000)
        t1.locator("tr", has_text="走查加知识点").filter(has_text="已执行").first.wait_for(timeout=30000)
        ck(True, f"{name}：知识点草稿点确认后状态变「已执行」")
    except Exception as e:
        ck(False, name, f"{type(e).__name__}: {str(e)[:300]}")
    err = drain_errors(marks)
    ck(not err, f"{name}流程无 JS 错误", err)
    t1.evaluate("location.hash = ''")


def attach_flow(t1, tmp, ck, marks):
    """M4-P2：教师助手附件。传 txt → 附件条显示 → 问一句（假模型）→ 移除附件 → 附件条消失；传 xlsx → 提示另存 csv 原文。"""
    name = "教师助手附件"
    try:
        t1.evaluate("location.hash = encodeURIComponent('教师助手')")
        wait_screen(t1, "教师助手")
        t1.wait_for_timeout(1500)
        txt = tmp / "walk_attach.txt"
        txt.write_text("走查附件正文：第一段。\n\n第二段讲授今天的语法。\n", encoding="utf-8")
        t1.locator("input[type=file]").first.set_input_files(str(txt))
        t1.locator("textarea").last.fill("总结走查附件")
        t1.locator("button", has_text="传附件").last.click()
        bar = t1.locator("text=附件：walk_attach.txt")
        bar.first.wait_for(timeout=90000)
        ck(True, f"{name}：传 txt 后附件条显示文件名")
        t1.get_by_text("走查附件回答", exact=False).first.wait_for(timeout=90000)
        ck(True, f"{name}：带着附件问一句，助手按资料回答（假模型）")
        t1.locator("button", has_text="移除附件").first.click(timeout=8000)
        t1.locator("button", has_text="移除附件").first.wait_for(state="detached", timeout=30000)
        ck(t1.locator("button", has_text="移除附件").count() == 0, f"{name}：移除附件后附件条消失")
        t1._allowed_status = ("400",)   # xlsx 被拒是故意的 400，不算 JS 错误
        xls = tmp / "walk_attach.xlsx"
        xls.write_bytes(b"PK\x03\x04walk")
        t1.locator("input[type=file]").first.set_input_files(str(xls))
        t1.locator("button", has_text="传附件").last.click()
        t1.get_by_text("请在 Excel 里另存为 csv", exact=False).first.wait_for(timeout=30000)
        ck(True, f"{name}：传 xlsx 提示「另存为 csv」")
    except Exception as e:
        try:
            seen = t1.locator(".screen").first.inner_text(timeout=3000)[-600:]
        except Exception:
            seen = ""
        ck(False, name, f"{type(e).__name__}: {str(e)[:300]} 页面末尾：{seen!r}")
    err = drain_errors(marks)
    t1._allowed_status = ()
    ck(not err, f"{name}流程无 JS 错误", err)
    t1.evaluate("location.hash = ''")


WITHDRAW_SERIES = "wk117"
WITHDRAW_NOTE = "撤下了：这个系列已经撤下，教材页的下拉里不再有它。"


def seed_imported_series(proj):
    """教材导入撤下段的前置：直接往库里放一个已导入的系列和它的任务。
    走真导入要调模型解析，离线假模型走不通；确认导入这一步由接口测试
    （contracts/textbook_import.md 的用例）覆盖，这里只验撤下后的页面。"""
    con = sqlite3.connect(proj / "app.db")
    try:
        con.execute("INSERT INTO lesson_series(code,name,sort_order,subject_id) VALUES(?,?,?,1)",
                    (WITHDRAW_SERIES, "走查撤下系列", 900))
        con.execute("INSERT INTO textbook_import_task(series_code,series_name,file_name,raw_text,"
                    "status,created_at,subject_id) VALUES(?,?,?,?,?,?,1)",
                    (WITHDRAW_SERIES, "走查撤下系列", "walk.md", "x", "已导入", "2026-01-01 00:00:00"))
        con.commit()
    finally:
        con.close()


def import_withdraw_flow(t1, ck, marks):
    """K117：教材导入页管理系列 → 撤下 → 提示可见 → 重新载入（刷新）提示仍在。"""
    t1.evaluate("location.hash = encodeURIComponent('教材导入') + '?manage=%s'" % WITHDRAW_SERIES)
    try:
        t1.get_by_text("撤下这个系列", exact=True).first.click(timeout=15000)
        t1.wait_for_selector(".overlay", timeout=8000)
        t1.locator(".overlay").get_by_text("确认撤下", exact=True).last.click(timeout=8000)
        t1.get_by_text(WITHDRAW_NOTE, exact=False).first.wait_for(timeout=15000)
        ck(True, "教材导入：撤下后提示「撤下了：…」可见")
    except Exception as e:
        ck(False, "教材导入：撤下后提示「撤下了：…」可见", f"{type(e).__name__}: {str(e)[:200]}")
        return
    t1.reload()
    try:
        t1.get_by_text(WITHDRAW_NOTE, exact=False).first.wait_for(timeout=15000)
        ck(True, "教材导入：撤下后重新载入，提示仍在")
    except Exception as e:
        ck(False, "教材导入：撤下后重新载入，提示仍在", f"{type(e).__name__}: {str(e)[:200]}")
    err = drain_errors(marks)
    ck(not err, "教材导入撤下流程无 JS 错误", err)
    t1.evaluate("location.hash = ''")


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
    # K112：科目管理有界面级「触发 subject_members」，原先 runTrigger 把浮层参数从
    # 地址里抹掉（刷新浮层就关了）；带参刷新时载入和触发各发一次 members。
    hits, stop = track_posts(t1, "/account/subject/members")
    row.locator('button:has-text("成员")').first.click()
    t1.wait_for_selector(".overlay", timeout=8000)
    t1.wait_for_timeout(1500)
    stop()
    h = hash_of(t1)
    ck("浮层=科目成员" in h and "subj_id=" in h,
       "从行上开成员浮层：地址里的浮层参数还在", h)
    ck(len(hits) == 1, "从行上开成员浮层：members 只发一次", f"{len(hits)} 次")
    hits, stop = track_posts(t1, "/account/subject/members")
    t1.reload(wait_until="domcontentloaded")
    try:
        t1.wait_for_selector('.overlay tr:has-text("t1")', timeout=15000)
        ok = True
    except Exception:
        ok = False
    t1.wait_for_timeout(1500)
    stop()
    ck(ok and "浮层=科目成员" in hash_of(t1),
       "成员浮层开着刷新：浮层还开着、成员表拉回来了", hash_of(t1))
    ck(len(hits) == 1, "成员浮层带参刷新：members 只发一次", f"{len(hits)} 次")
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


def pick_label(page, sel, needle):
    """下拉里挑一条含 needle 的选项文字；挑不到就退而取最后一项。没选项返回 None。"""
    # eval_on_selector_all 传给页面函数的是「匹配元素数组」，不是单个元素（K103 实测：
    # 写成 e => [...e.options] 会 TypeError: e.options is not iterable）
    labels = page.eval_on_selector_all(
        sel, "els => els.flatMap(el => [...el.options].map(o => o.textContent.trim()))")
    if not labels:
        return None
    hit = [x for x in labels if needle in x]
    return hit[0] if hit else labels[-1]


def kg_create_point(page, code, title, ck, label):
    """顶栏「新建知识点」浮层建一个点，断言它出现在知识点表里。"""
    clear_toast(page)
    page.locator('button:has-text("新建知识点")').first.click()
    page.wait_for_selector(".overlay", timeout=8000)
    page.locator('.overlay label.field:has-text("编号") input').first.fill(code)
    page.locator('.overlay label.field:has-text("名称") input').first.fill(title)
    page.locator('.overlay button:has-text("保存")').first.click()
    page.wait_for_selector(".overlay", state="detached", timeout=10000)
    clear_toast(page)
    page.wait_for_selector(f'tr:has-text("{code}")', timeout=10000)
    ck(page.locator("tr", has_text=code).count() >= 1,
       f"{label}：知识点 {code} 建成且在表里")


def kg_mgmt_flow(t1, t2, t3, ck, marks, tmp):
    """图谱管理段（K99b，约定 k98_design/kg_manage.ui）。断言与数据内容无关：
    只认本段自建的 walk99.* 编号和自取的提示条文字，不写死种子数据的任何内容。"""
    t1._allowed_status = ("400", "409")   # 成环 400 / 引用 409 是故意打的，不算 JS 错误
    visit(t1, "图谱管理", marks)
    # 等 kgm_home（进入时）回来：三个写按钮挂在 shared.can_write 上，没回来时只剩「导出」
    t1.wait_for_selector('button:has-text("新建知识点")', timeout=15000)
    btns = [b for b in ("新建知识点", "新建条目", "批量导入", "导出")
            if t1.locator(f'button:has-text("{b}")').count()]
    ck(btns == ["新建知识点", "新建条目", "批量导入", "导出"],
       "负责人（t1）顶栏四个按钮齐全", f"实际有：{btns}")

    # 1) 建两个知识点（后面加边、成环要用一对）
    kg_create_point(t1, KG_P1, KG_T1T, ck, "建知识点1")
    kg_create_point(t1, KG_P2, KG_T2T, ck, "建知识点2")

    # 1b) K112：节点图点一个节点（「点开 编辑知识点 带 code」），载入和界面级触发都是
    #     kgm_point_open，原先一次点击发两遍、地址里的浮层参数被抹掉
    node = t1.locator(".vue-flow__node", has_text=KG_T1T).first
    try:
        node.wait_for(timeout=10000)
        hits, stop = track_posts(t1, "/kg/manage/point/open")
        # 不用 click()：节点在 Vue Flow 变换过的画布里，取景后常在可视区外，
        # Playwright 判为不可点、等满 30 秒。直接派 click，Vue Flow 照样发 node-click
        node.dispatch_event("click")
        t1.wait_for_selector(".overlay", timeout=8000)
        t1.wait_for_function(
            "t => [...document.querySelectorAll('.overlay label.field input')]"
            ".some(e => e.value === t)", arg=KG_T1T, timeout=10000)
        t1.wait_for_timeout(1500)
        stop()
        h = hash_of(t1)
        ck("浮层=编辑知识点" in h and f"code={KG_P1}" in h,
           "节点图点开：地址里的浮层参数还在", h)
        ck(len(hits) == 1, "节点图点一次：kgm_point_open 只发一次", f"{len(hits)} 次")
        t1.keyboard.press("Escape")
        t1.wait_for_selector(".overlay", state="detached", timeout=8000)
    except Exception as e:
        ck(False, "节点图点开编辑知识点浮层", f"{type(e).__name__}: {str(e)[:200]}")

    # 2) 建条目：挂到「所属知识点」下拉的第一项上——挂谁都行，与数据内容无关
    clear_toast(t1)
    t1.locator('button:has-text("新建条目")').first.click()
    t1.wait_for_selector(".overlay", timeout=8000)
    t1.locator('.overlay label.field:has-text("编号") input').first.fill(KG_I1)
    t1.locator('.overlay label.field:has-text("名称") input').first.fill(KG_IT1)
    # 不能 select_option(index=0)：下拉第一项是 <option value="" disabled>请选择</option>
    # 占位项，选它提交 kgi_point 为空 → 404 没有这个知识点（K103 实测）。按值选刚建的点。
    t1.wait_for_function(
        "c => { for (const el of document.querySelectorAll('.overlay label.field')) {"
        " if (el.textContent.indexOf('所属知识点') < 0) continue;"
        " const sel = el.querySelector('select');"
        " if (sel && [...sel.options].some(o => o.value === c)) return true; } return false; }",
        arg=KG_P1, timeout=10000)
    t1.locator('.overlay label.field:has-text("所属知识点") select').first.select_option(KG_P1)
    t1.locator('.overlay button:has-text("保存")').first.click()
    t1.wait_for_selector(".overlay", state="detached", timeout=10000)
    clear_toast(t1)
    # 等整页状态（kgm_item_save 返回）把条目表刷出来再数，跟建知识点同款
    t1.wait_for_selector(f'tr:has-text("{KG_I1}")', timeout=10000)
    ck(t1.locator("tr", has_text=KG_I1).count() >= 1, "条目 walk99.i1 建成且在表里")

    # 3) 加前置边 p1→p2；再加反向 p2→p1（成环）看到 400 提示、表不多行
    l1 = pick_label(t1, 'label.field:has-text("先学") select', KG_P1)
    l2 = pick_label(t1, 'label.field:has-text("后学") select', KG_P2)
    ck(bool(l1) and bool(l2) and l1 != l2, "前置边两个下拉有可选项", f"{l1!r} {l2!r}")
    if l1 and l2 and l1 != l2:
        pre = t1.locator('label.field:has-text("先学") select').first
        post = t1.locator('label.field:has-text("后学") select').first
        n0 = t1.locator("tr", has_text=KG_T1T).count()
        pre.select_option(label=l1)
        post.select_option(label=l2)
        t1.locator('button:has-text("加前置边")').first.click()
        # 等整页状态（kgm_edge_add 返回）把前置边表刷出来再数：刷新是异步的，数早了差一行
        t1.wait_for_function(
            "([t, n]) => [...document.querySelectorAll('tr')]"
            ".filter(r => r.textContent.indexOf(t) >= 0).length === n + 1",
            arg=[KG_T1T, n0], timeout=10000)
        n1 = t1.locator("tr", has_text=KG_T1T).count()
        ck(n1 == n0 + 1, "前置边加上（前置边表多一行）", f"{n0} → {n1}")
        pre.select_option(label=l2)
        post.select_option(label=l1)
        t1.locator('button:has-text("加前置边")').first.click()
        try:
            got = toast(t1, kind="no")
        except Exception:
            try:
                got = toast(t1)
            except Exception:
                got = ""
        ck(bool(got.strip()), "成环的边被拒：提示条有 400 原文", f"提示条：「{got}」")
        n2 = t1.locator("tr", has_text=KG_T1T).count()
        ck(n2 == n1, "成环的边没进表", f"{n1} → {n2}")

    # 4) 导入预检：一行好一行坏 → 逐行结果出来、确认导入按钮不出现
    clear_toast(t1)
    t1.locator('button:has-text("批量导入")').first.click()
    t1.wait_for_selector(".overlay", timeout=8000)
    # 上传文件不能在预检后立刻删：图谱管理页每个动作的 FormData 都带着 imp_upload，
    # 文件没了后面的请求（如导出）会在发出前失败（K105）。建在走查 tmp 里，随 rmtree 删
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8", dir=tmp)
    f.write(KG_P1 + "imp|预检好的行\n坏 编号|预检坏行\n")
    f.close()
    t1.locator('.overlay input[type="file"]').first.set_input_files(f.name)
    # 不能 index=0：下拉第一项是「请选择」占位（imp_kind 空 → 400 导入类型不对）
    t1.locator('.overlay label.field:has-text("类型") select').first.select_option(label="知识点")
    t1.locator('.overlay button:has-text("预检")').first.click()
    t1.wait_for_selector(".overlay tr", timeout=10000)
    ck(t1.locator(".overlay tr").count() >= 1, "预检出了逐行结果")
    ck(t1.locator('.overlay button:has-text("确认导入")').count() == 0,
       "有一行错：确认导入按钮不出现")
    t1.locator('.overlay button:has-text("返回")').first.click()
    t1.wait_for_selector(".overlay", state="detached", timeout=8000)
    clear_toast(t1)

    # 5) 导出：生成后有文本（约定：不做文件下载；.ui 里导出文本走「显示」读 shared，
    #    不是多行框——多行框绑 form，而 kgm_export 回的是页面状态，不会回填）
    t1.locator('button:has-text("导出")').first.click()
    t1.wait_for_selector(".overlay", timeout=8000)
    t1.locator('.overlay label.field:has-text("类型") select').first.select_option(label="全部")
    t1.locator('.overlay button:has-text("生成")').first.click()
    try:
        t1.wait_for_function(
            "() => [...document.querySelectorAll('.overlay .dyn-v')]"
            ".some(e => e.textContent.trim().length > 50)", timeout=15000)
        ck(True, "导出生成了文本")
    except Exception as e:
        ck(False, "导出生成了文本", type(e).__name__)
    t1.locator('.overlay button:has-text("返回")').first.click()
    t1.wait_for_selector(".overlay", state="detached", timeout=8000)
    clear_toast(t1)

    # 6) 协作教师（t2）可写：有写按钮、真能建一个点
    visit(t2, "图谱管理", marks)
    t2.wait_for_selector('button:has-text("新建知识点")', timeout=15000)  # 等 kgm_home 回来
    ck(t2.locator('button:has-text("新建知识点")').count() == 1, "协作教师（t2）有写按钮")
    kg_create_point(t2, KG_T2P, "走查协作点", ck, "协作教师写")

    # 7) 公共科目其他教师（t3，init 后才建、没登记）只读：没有写按钮、能导出
    visit(t3, "图谱管理", marks)
    t3.wait_for_selector('button:has-text("导出")', timeout=15000)  # 等 kgm_home 回来
    extra = [b for b in ("新建知识点", "新建条目", "批量导入")
             if t3.locator(f'button:has-text("{b}")').count()]
    ck(not extra, "公共科目其他教师（t3）看不到写按钮", f"多了：{extra}")
    ck(t3.locator('button:has-text("导出")').count() == 1, "t3 仍能导出")
    # 文案挂在 shared.can_write===0 上（kgm_home 回来才出现），直接等它
    try:
        t3.wait_for_selector("text=公共只读", timeout=15000)
        ck(True, "t3 页面有「公共只读」说明")
    except Exception:
        ck(False, "t3 页面有「公共只读」说明", "15 秒没出现（can_write 没到 0？）")


def main(argv=None):
    ap = argparse.ArgumentParser(description="kg_v4 浏览器走查（真浏览器，自己起服务）")
    ap.add_argument("--no-subject-mgmt", dest="no_subject", action="store_true",
                    help="跳过科目管理相关断言（给合并前的基线跑，证明脚本本身没错）")
    ap.add_argument("--no-kg-mgmt", dest="no_kg", action="store_true",
                    help="跳过图谱管理段（默认开；实现未合并时用它跑基线）")
    ap.add_argument("--src", default=str(REPO / "kg_v4"),
                    help="被走查的 kg_v4 目录（默认仓库里的；基线 worktree 传它的）")
    ap.add_argument("--keep", action="store_true", help="留着临时目录（排查用）")
    ap.add_argument("--timeout", type=int, default=600,
                    help="整个走查的秒数上限（默认 600）；到点打出卡在哪一行，"
                         "按失败收尾并停服务；0 = 不限")
    a = ap.parse_args(argv)
    if a.timeout > 0:
        import signal
        import traceback

        def _on_alarm(sig, frame):
            print(f"\n!! 走查超过 {a.timeout} 秒，卡在：")
            traceback.print_stack(frame, limit=6, file=sys.stdout)
            sys.stdout.flush()
            raise TimeoutError(f"整个走查超过 {a.timeout} 秒")
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(a.timeout)
    subject_mgmt = not a.no_subject
    kg_mgmt = not a.no_kg

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
        proj = build_workspace(tmp, Path(a.src), kg_mgmt=kg_mgmt)
        seed_imported_series(proj)
        with open(tmp / "server.log", "w") as log:
            proc = start_server(proj, port, log, env={"DSL_MOCK_SCRIPT": str(write_assist_mock(proj, tmp))})
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
                kg_mgmt = walk_teacher(t1, base, ck, marks, subject_mgmt, kg_mgmt)
                import_withdraw_flow(t1, ck, marks)
                assist_flow(t1, ck, marks)
                attach_flow(t1, tmp, ck, marks)
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

                # ---- 图谱管理（K99b）----
                if kg_mgmt:
                    t2k = t2 if subject_mgmt else new_page(browser.new_context(), "t2")
                    if not subject_mgmt:
                        login(t2k, base, "t2", end="/teacher")
                        snapshot(marks)   # t2 登录前的 401 不计
                    t3 = new_page(browser.new_context(), "t3")
                    login(t3, base, "t3", end="/teacher")
                    snapshot(marks)
                    kg_mgmt_flow(t1, t2k, t3, ck, marks, tmp)
                    err = drain_errors(marks)
                    ck(not err, "图谱管理流程无 JS 错误", err)

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
                if kg_mgmt:
                    mk = new_page(
                        browser.new_context(viewport={"width": 390, "height": 844}),
                        "390-t1kg")
                    login(mk, base, TEACHER_USER, end="/teacher")
                    mk.evaluate("location.hash = encodeURIComponent('图谱管理')")
                    mk.wait_for_timeout(1200)
                    no_overflow(mk, "图谱管理页", ck)
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
