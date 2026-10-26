# -*- coding: utf-8 -*-
"""服务并发：一个慢请求在跑时，快请求不被挡住。

    cd /workspace/agent_mcp && .venv/bin/python tests/http/test_concurrent.py

走真实的起服务路径（gen.project.run → Flask app.run），不是自己拼 werkzeug：
  一、app.run 带 threaded=True（单线程的话第二个请求要等第一个跑完）
  二、一个慢接口（DSL 里大循环，几秒）在跑，同时发一个只返回常量的快接口：
      快接口在慢接口跑完之前就回来了，而且不超过 1.5 秒
  三、两个并发请求各自拿到自己的结果（互不串）
"""

import socket
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import run                                # noqa: E402

SLOW_ITEMS = 500        # 两层遍历，500 x 500 次，本机约 3 秒

ENTITY = """\
实体 note note
  字段 title 文本 必填 标题
结束
"""

# 慢接口：两层遍历（路由解析目前只认 如果/遍历/事务 这类块，
# 「重复」「当」写在接口里会被当成接口收尾，所以用遍历）
ROUTES = """\
接口 POST /slow
  设 xs = 解析JSON [%s]
  设 n = 0
  遍历 x 于 {xs}
    遍历 y 于 {xs}
      设 n = 计算 {n} + 1
    结束
  结束
  返回 {"who":"slow","n":"{n}"}
结束


接口 POST /fast
  返回 {"who":"fast"}
结束
""" % ",".join(str(i) for i in range(SLOW_ITEMS))

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def post(base, path):
    t = time.time()
    req = urllib.request.Request(base + path, data=b"{}",
                                 headers={"content-type": "application/json"})
    body = urllib.request.urlopen(req, timeout=120).read().decode()
    return time.time() - t, body


def main():
    # 一、起服务时传给 Flask 的 threaded 参数
    import flask
    seen = {}
    real_run = flask.Flask.run

    def spy(self, *a, **kw):
        seen.update(kw)
        raise SystemExit(0)          # 只看参数，不真的监听

    flask.Flask.run = spy
    tmp = Path(tempfile.mkdtemp(prefix="conc_"))
    (tmp / "entities").mkdir()
    (tmp / "routes").mkdir()
    (tmp / "entities" / "n.entity").write_text(ENTITY, encoding="utf-8")
    (tmp / "routes" / "t.zs").write_text(ROUTES, encoding="utf-8")
    try:
        run(tmp, port=free_port(), open_browser=False)
    except SystemExit:
        pass
    finally:
        flask.Flask.run = real_run
    print("一、gen run 的 app.run 参数")
    check(seen.get("threaded") is True, f"threaded=True（实际 {seen.get('threaded')!r}）")

    # 二、真起服务，一慢一快并发
    port = free_port()
    th = threading.Thread(target=lambda: run(tmp, port=port, open_browser=False), daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            break
        except OSError:
            time.sleep(0.25)

    t_one, body = post(base, "/slow")             # 先单独量一下慢接口要多久
    print(f"（慢接口单独跑 {t_one:.1f} 秒）")
    res = {}

    def slow():
        res["slow"] = post(base, "/slow")

    s = threading.Thread(target=slow)
    t0 = time.time()
    s.start()
    time.sleep(0.5)
    t_fast, fast_body = post(base, "/fast")
    fast_done_at = time.time() - t0
    slow_alive = s.is_alive()
    s.join()
    print("二、慢接口在跑时发快接口")
    check(t_one > 2.0, f"慢接口够慢（{t_one:.1f} 秒），测得出阻塞")
    check(slow_alive, f"快接口回来时慢接口还没跑完（快接口在 {fast_done_at:.1f} 秒回来）")
    check(t_fast < 1.5, f"快接口 {t_fast:.2f} 秒内返回，没被慢接口挡住")
    print("三、各拿各的结果")
    check('"who":"fast"' in fast_body.replace(" ", ""), f"快接口：{fast_body.strip()}")
    check('"who":"slow"' in res["slow"][1].replace(" ", ""), f"慢接口：{res['slow'][1].strip()}")

    print(f"\n通过 {passed} / {passed + failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
