# -*- coding: utf-8 -*-
"""路由器的会话读写：用得到才读，变了才写。

    cd /home/ysc/mcp && .venv/bin/python tests/http/test_session.py

直接调 Router.handle，不起服务——测的是路由器自己的行为。

五种情况：
  一、接口一处会话都不用     → 不读、不写、不建 sessions/
  二、接口写会话            → 写进 sessions/<learner>.json
  三、下一个请求接着用       → 读到上次写的值
  四、接口只读会话          → 文件不被重写（看修改时间）
  五、子脚本                → 显式传 会话={会话} 才读得到；不传读不到，
                              因为子脚本是独立作用域
"""

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl_http import Router      # noqa: E402

ROUTES = """\
接口 POST /plain
  返回 {"ok":true}
结束


接口 POST /count
  用包 common
  如果 {会话.次数} 为空
    设 会话.次数 = 1
  否则
    设 会话.次数 = 相加 {会话.次数} 1
  结束
  返回 {"n":"{会话.次数}"}
结束


接口 POST /peek
  返回 {"n":"{会话.次数}"}
结束


接口 POST /viasub
  设 结果 = 执行 子.zs 会话={会话}
  返回 {"n":"{结果}"}
结束


接口 POST /viasub_nopass
  设 结果 = 执行 子.zs
  返回 {"n":"{结果}"}
结束
"""

# 子脚本是独立作用域：看不到父脚本的变量，会话要显式传进来。
# 结果用「返回」交回父脚本（设 x = 执行 …）。
SUB = "返回 {会话.次数}\n"

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sess_"))
    (tmp / "routes").mkdir()
    (tmp / "routes" / "t.zs").write_text(ROUTES, encoding="utf-8")
    (tmp / "子.zs").write_text(SUB, encoding="utf-8")
    sessions = tmp / "sessions"
    router = Router(tmp / "routes", tmp, sessions, real=False)
    ep = lambda path: router.table[("POST", path)]
    call = lambda path, **form: router.handle(ep(path), {"learner": "u1", **form})
    f = sessions / "u1.json"

    print("一、不用会话的接口")
    body, status = call("/plain")
    check(status == 200, f"正常返回：{body}")
    check(not sessions.exists(), "没有建 sessions/，也没写任何文件")

    print("二、写会话")
    body, _ = call("/count")
    check(f.is_file(), f"写进了 {f.name}")
    check('"n":"1"' in str(body).replace(" ", "") or "1" in str(body), f"第一次是 1：{body}")

    print("三、下一个请求接着用")
    body, _ = call("/count")
    check("2" in str(body), f"第二次是 2：{body}")

    print("四、只读会话的接口不重写文件")
    mtime = f.stat().st_mtime_ns
    time.sleep(0.05)
    body, _ = call("/peek")
    check("2" in str(body), f"读到 2：{body}")
    check(f.stat().st_mtime_ns == mtime, "文件修改时间没变")

    print("五、子脚本和会话")
    body, _ = call("/viasub")
    check("2" in str(body), f"显式传进去，子脚本读到了：{body}")
    body, _ = call("/viasub_nopass")
    check("2" not in str(body),
          f"不传就读不到——子脚本是独立作用域，跟会话读没读无关：{body}")

    print("  另一个 learner 看不到 u1 的会话")
    body, _ = router.handle(ep("/peek"), {"learner": "u2"})
    check("2" not in str(body), f"u2 读到的：{body}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
