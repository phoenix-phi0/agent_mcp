# -*- coding: utf-8 -*-
"""知识图谱的桌面入口：双击就开窗口。

    py kg/app.pyw          开发时
    双击 app.pyw           平时

跟 gen/app.pyw 同一套：起 Flask 在随机空端口，等它活过来，用 pywebview 开
一个原生窗口，关窗口就退出（webview.start() 阻塞到关闭，服务线程是 daemon）。

多做的一件事：**开窗之前先把数据准备好**——建库（已有的库按实体只加不改，
引擎的 tools/migrate.py）、导入知识点和单词、编译界面。命令行那边是
`py -m kg`，这里调的是同一个 setup()，所以双击和敲命令的结果一样。第一次
跑要几秒。

装依赖：
    pip install flask pywebview
"""

import socket
import sys
import threading
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent
ROOT = PROJ.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TITLE = "知识图谱"
# .pyw 没有控制台：启动的模式行、服务日志、模型调用的报错都写这里（*.log 已 gitignore）
LOG = PROJ / "app.log"


def free_port(start: int = 8180) -> int:
    """找一个没被占用的端口。上次的进程没退干净时，写死端口会直接起不来。"""
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

    缺东西时弹个说明窗口，而不是闷声退出或者开个空白页——那两种都要人去翻
    日志才知道怎么回事。
    """
    missing = []
    src = PROJ / "content" / "kg.jsonl"
    if not src.is_file():
        missing.append(("content/kg.jsonl", "知识点数据不在，没有它画不出图"))
    for name in ("flask", "webview"):
        try:
            __import__(name)
        except ImportError:
            pkg = "pywebview" if name == "webview" else name
            missing.append((name, f"pip install {pkg}"))
    return missing


def error_window(missing: list) -> None:
    """资源缺失时弹一个说明窗口。

    纯手写 HTML 不走生成链：这个窗口恰恰是「环境不齐」时才弹的，不该在最
    脆弱的时刻引入最多依赖。
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


def start_log() -> None:
    """把 stdout / stderr 接到 app.log。pythonw 下它们是 None，print 会直接抛。"""
    f = open(LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f
    print(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 ====")


def build_app(argv: list, environ=None):
    """按命令行和环境变量决定真模型还是模拟，造出 Flask 应用。

    返回 (app, mock, title)。不开窗口、不起服务，测试直接调它。
    --mock / KG_MOCK 的判断跟 py -m kg 是同一个函数（kg.__main__.parse_mode），
    --登录 / KG_LOGIN（多人模式，要登录）也是（parse_login）。默认单人、不登录。
    """
    from gen.project import make_app
    from kg.__main__ import login_line, mode_label, mode_line, parse_login, parse_mode

    mock, _ = parse_mode(argv, environ)
    login, secure, _ = parse_login(argv, environ)
    print(mode_line(mock))
    print(login_line(login))
    # 单人模式照旧只传 real：跟改之前一模一样的调用
    extra = {"login": True, "secure_cookie": secure} if login else {}
    app, _ = make_app(PROJ, real=not mock, **extra)
    title = f"{TITLE}（{mode_label(mock)}{'，多人登录' if login else ''}）"
    return app, mock, title


def main(argv: list = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    start_log()
    missing = check()
    if missing:
        try:
            error_window(missing)
        except ImportError:
            # 连 pywebview 都没有，弹不出窗口，只能往控制台写
            for w, t in missing:
                print(f"{w}：{t}")
        return 1

    import webview

    from kg.__main__ import setup

    # 建库（老库只加不改）、导入、编译。跟 py -m kg 走的是同一段。
    setup(quiet=True)

    port = free_port()
    app, _mock, title = build_app(argv)
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port,
                               threaded=True, debug=False),
        daemon=True).start()

    # 等服务活过来再开窗。不等的话窗口打开时服务还没绑上端口，显示的是
    # 「无法访问」，而那时人多半以为程序坏了。
    for _ in range(60):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)

    webview.create_window(
        title, f"http://127.0.0.1:{port}",
        width=1200, height=860, min_size=(820, 560))
    webview.start()          # 阻塞到窗口关闭
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
