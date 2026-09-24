# -*- coding: utf-8 -*-
"""并发下的身份隔离。

    cd /home/ysc/mcp && .venv/bin/python tests/auth/test_concurrency.py

路由器把「当前用户」放在线程局部变量里，Flask 的线程会被复用。要是哪儿
清理漏了，高并发时 A 的请求就可能带着上一个请求的 B 的身份跑——那种错
在单个请求的测试里永远测不出来。

这里起真服务（多线程），六个用户各自登录，然后几十个线程交错着发几百个
请求：查列表、新建。每个响应都核对只含自己的数据；最后到库里核对每条
记录的归属跟标题里写的主人一致。
"""

import http.cookiejar
import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "bin" / "python")
PORT = 8195
BASE = f"http://127.0.0.1:{PORT}"
USERS = [f"u{i}" for i in range(6)]

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def opener():
    """每个用户一个自带 cookie 罐的客户端，跟一个浏览器一样。"""
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(op, path, **form):
    req = urllib.request.Request(
        BASE + path, data=json.dumps({"form": form}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with op.open(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    proj = Path(tempfile.mkdtemp(prefix="conc_")) / "app"
    run = lambda *a: subprocess.run([PY, "-m", "gen", *a], cwd=ROOT,
                                    check=True, capture_output=True)
    run("init", str(proj), "--空")
    run("auth", str(proj))
    (proj / "entities" / "note.entity").write_text(
        "实体 note 笔记\n  字段 title 文本 必填 标题\n  字段 owner 文本 必填 索引 归属\n结束\n",
        encoding="utf-8")
    run("gen", str(proj), "--模板", "private")

    # 新会话起服务：结束时按进程组杀，连它派生的子进程一起——只杀父进程
    # 会留下占着端口的孤儿。
    #
    # 错误输出写文件，不接管道：Flask 每个请求往 stderr 写一行日志，几百个
    # 请求就超过管道缓冲区（64KB），服务会卡在写日志上，看着像挂了。
    log_path = proj.parent / "server.log"
    log_file = open(log_path, "wb")
    server = subprocess.Popen(
        [PY, "-m", "gen", "run", str(proj), "--port", str(PORT), "--不开浏览器"],
        cwd=ROOT, stdout=log_file, stderr=log_file,
        start_new_session=True)
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(BASE + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        else:
            print("服务没起来")
            return 1

        ops = {u: opener() for u in USERS}
        for u, op in ops.items():
            st, _ = call(op, "/auth/register", username=u, password=f"{u}-pass")
            assert st == 200, (u, st)

        print("一、交错新建：六个人各建 15 条，32 个线程乱序发")
        jobs = [(u, i) for u in USERS for i in range(15)]
        random.shuffle(jobs)

        def create(job):
            u, i = job
            return call(ops[u], "/note/create", title=f"{u}的第{i}条")

        with ThreadPoolExecutor(32) as pool:
            results = list(pool.map(create, jobs))
        codes = [st for st, _ in results]
        check(all(c == 200 for c in codes), f"90 次新建全部 200（{codes.count(200)}/90）")
        for st, body in [r for r in results if r[0] != 200][:3]:
            print(f"      {st}：{json.dumps(body, ensure_ascii=False)[:300]}")

        con = sqlite3.connect(proj / "app.db")
        rows = con.execute("SELECT title, owner FROM note").fetchall()
        con.close()
        wrong = [(t, o) for t, o in rows if not t.startswith(o + "的")]
        check(len(rows) == 90 and not wrong,
              f"库里 90 条，每条的归属都是标题里写的那个人（错的 {wrong[:3]}）")

        print("二、交错查询：六个人乱序查 400 次列表")
        reqs = [random.choice(USERS) for _ in range(400)]

        def listing(u):
            st, body = call(ops[u], "/note/list")
            titles = [r["title"] for r in (body.get("lists") or {}).get("notes", [])]
            return u, st, titles

        with ThreadPoolExecutor(32) as pool:
            results = list(pool.map(listing, reqs))
        bad = [(u, st, t[:2]) for u, st, t in results
               if st != 200 or len(t) != 15 or any(not x.startswith(u + "的") for x in t)]
        check(not bad, f"400 次查询，每次都恰好是自己的 15 条（出错的 {bad[:3]}）")

        print("三、登录和查询混在一起")
        mix = []
        for _ in range(200):
            u = random.choice(USERS)
            mix.append(("login", u) if random.random() < 0.3 else ("list", u))

        def act(job):
            kind, u = job
            if kind == "login":
                return kind, u, call(ops[u], "/auth/login", username=u,
                                     password=f"{u}-pass")[0], []
            st, body = call(ops[u], "/note/list")
            return kind, u, st, [r["title"] for r in (body.get("lists") or {}).get("notes", [])]

        with ThreadPoolExecutor(32) as pool:
            out = list(pool.map(act, mix))
        bad = [(k, u, st) for k, u, st, t in out
               if st != 200 or any(not x.startswith(u + "的") for x in t)]
        check(not bad, f"200 次混合请求，没有串号（出错的 {bad[:3]}）")
    finally:
        try:
            os.killpg(os.getpgid(server.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass

    # 服务停了再看日志
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    log_file.close()
    err = log_path.read_bytes()
    check(b"Traceback" not in err, "服务端没有 Traceback")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
