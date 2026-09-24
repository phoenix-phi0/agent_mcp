# -*- coding: utf-8 -*-
"""生成器的桌面入口：双击就开窗口。

    py gen/app.pyw          开发时
    双击 app.pyw            平时

沿用 app2/app.py 那套：起 Flask 在随机空端口，等它活过来，用 pywebview
开一个原生窗口。**关窗口就退出**——`webview.start()` 是阻塞的，窗口关了
函数返回，进程结束；服务线程是 daemon，跟着没。

那比 Edge 的 `--app` 模式干净：不用找浏览器路径，也不会留下「窗口关了
但进程还在」的尾巴。

装依赖：
    pip install flask pywebview
"""

import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TITLE = "实体生成器"
ENTITY_DIR = ROOT / "entities"


def free_port(start: int = 8100) -> int:
    """找一个没被占用的端口。

    多开或者上次的进程没退干净时，写死端口会直接起不来。往上找五十个，
    够用了。
    """
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def check() -> list:
    """开窗之前看看东西齐不齐。返回 [(名字, 说明), ...]。

    缺东西时弹个说明窗口，而不是闷声退出或者开个空白页——那两种都要人
    去翻日志才知道怎么回事。
    """
    missing = []

    if not ENTITY_DIR.is_dir():
        missing.append((str(ENTITY_DIR.name) + "/",
                        "实体定义目录不存在，建一个再放 .entity 进去"))
    elif not list(ENTITY_DIR.glob("*.entity")):
        missing.append((str(ENTITY_DIR.name) + "/",
                        "目录里没有 .entity 文件"))

    try:
        import flask                                    # noqa: F401
    except ImportError:
        missing.append(("flask", "pip install flask"))

    for name in ("queries", "routes", "ui"):
        d = ROOT / name
        if not d.is_dir():
            # 不算缺失，写盘时会自动建——但先说一声，省得人以为写错地方
            pass
    return missing


def error_window(missing: list) -> None:
    """资源缺失时弹一个说明窗口。

    纯手写 HTML 不走生成链：这个窗口恰恰是「环境不齐」时才弹的，
    不该在最脆弱的时刻引入最多依赖。
    """
    import webview

    rows = "".join(
        f"<tr><td style='padding:6px 14px 6px 0;color:#888'>{w}</td>"
        f"<td style='padding:6px 0'>{t}</td></tr>"
        for w, t in missing)
    html = (
        "<!doctype html><meta charset='utf-8'>"
        "<body style=\"font:14px system-ui,'Microsoft YaHei';"
        "background:#111;color:#ddd;padding:28px\">"
        "<h2 style='margin:0 0 6px'>启动前还差点东西</h2>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        "</body>")
    webview.create_window(TITLE, html=html, width=620, height=380)
    webview.start()


def main() -> int:
    try:
        import webview
    except ImportError:
        print("缺 pywebview：pip install pywebview")
        return 1

    missing = check()
    if missing:
        error_window(missing)
        return 1

    from gen.web import make_app

    port = free_port()
    # 第二个参数是**输出目录**不是项目根——传 ROOT 的话产物会散在
    # mcp/<实体>/ 下而不是 gen/out/<实体>/。不传就用默认的 OUT_DIR。
    app = make_app(ENTITY_DIR)

    # daemon：窗口关了之后这个线程跟着没，不用另外发停止信号
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port,
                               threaded=True, debug=False),
        daemon=True).start()

    # 等服务活过来再开窗。不等的话窗口打开时服务还没绑上端口，
    # 显示的是「无法访问」，而那时人多半以为程序坏了。
    for _ in range(60):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)

    webview.create_window(
        TITLE, f"http://127.0.0.1:{port}",
        width=1100, height=800, min_size=(720, 520))
    webview.start()          # 阻塞到窗口关闭
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
