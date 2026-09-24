# -*- coding: utf-8 -*-
"""`.ui` 编辑器的桌面入口：双击就开窗口。

    双击 gen/edit.pyw
    py gen/edit.pyw          开发时这么跑，控制台留着能看报错

左边写 `.ui`，右边实时渲染成界面。改的是 `gen/out/ui/` 下的东西——
生成器出骨架，这儿接着改，改完再复制进项目。

跟 `gen/app.pyw`（生成器）是两个入口、两个窗口。工作节奏不同：生成是
偶尔点一下，编辑是一直在敲。

**关窗口就退出**——`webview.start()` 阻塞到窗口关闭，服务线程是 daemon
跟着没。不用找浏览器路径，也不会留「窗口关了进程还在」的尾巴。

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

TITLE = ".ui 编辑器"


def free_port(start: int = 8110) -> int:
    """找一个没被占用的端口。

    多开或者上次的进程没退干净时，写死端口会直接起不来。
    """
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def error_window(lines) -> None:
    """东西不齐时弹个说明窗口。

    纯手写 HTML 不走生成链——这个窗口恰恰是「环境不齐」时才弹的，不该
    在最脆弱的时刻引入最多依赖。
    """
    import webview

    rows = "".join(f"<li style='margin:6px 0'>{x}</li>" for x in lines)
    html = (
        "<!doctype html><meta charset='utf-8'>"
        "<body style=\"font:14px system-ui,'Microsoft YaHei';"
        "background:#111;color:#ddd;padding:28px\">"
        "<h2 style='margin:0 0 10px'>还差点东西</h2>"
        f"<ul style='margin:0;padding-left:20px;line-height:1.7'>{rows}</ul>"
        "</body>")
    webview.create_window(TITLE, html=html, width=640, height=380)
    webview.start()


def main() -> int:
    try:
        import webview
    except ImportError:
        print("缺 pywebview：pip install pywebview")
        return 1

    from gen.editor import UI_DIR, make_app

    问题 = []
    if not UI_DIR.is_dir():
        问题.append(f"没有 {UI_DIR}<br>"
                   "<code>先跑一次生成器：py -m gen --all --write</code>")
    elif not list(UI_DIR.glob("*.ui")):
        问题.append(f"{UI_DIR} 里没有 .ui 文件<br>"
                   "<code>py -m gen --all --write</code>")
    try:
        import flask                                    # noqa: F401
    except ImportError:
        问题.append("缺 flask：<code>pip install flask</code>")

    if 问题:
        error_window(问题)
        return 1

    port = free_port()
    app = make_app()

    # daemon：窗口关了之后这个线程跟着没，不用另外发停止信号
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port,
                               threaded=True, debug=False),
        daemon=True).start()

    # 等服务活过来再开窗。不等的话窗口打开时显示「无法访问」，而那时
    # 人多半以为程序坏了。
    for _ in range(60):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)

    webview.create_window(TITLE, f"http://127.0.0.1:{port}",
                          width=1200, height=820, min_size=(760, 540))
    webview.start()          # 阻塞到窗口关闭
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
