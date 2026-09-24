# -*- coding: utf-8 -*-
"""app2 入口。跟旧版 agents/app.py 结构一样，只有界面来源不同。

开发时：
    py app2/build.py     # 先生成界面
    py app2/app.py

路径策略沿用旧版：代码目录和数据目录分开，这样打包成 exe 之后
flows、verbs、web 这些仍然可以直接编辑，改完重启即可。
"""

import os
import socket
import sys
import threading
import time
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# 代码目录：打包后是 PyInstaller 的临时解压目录
CODE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

# 数据目录：打包后是 exe 所在目录，开发时是项目根目录
if FROZEN:
    DATA_DIR = Path(sys.executable).resolve().parent
else:
    DATA_DIR = Path(__file__).resolve().parent.parent

for p in (str(CODE_DIR), str(DATA_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("ZHIPU_CONFIG", str(DATA_DIR / "config.json"))
os.environ.setdefault("JP_DATA_DIR", str(DATA_DIR))

TITLE = "JP-E01-π 日语教师"
HERE = Path(__file__).resolve().parent


def free_port(start: int = 8765) -> int:
    """找一个没被占用的端口，避免多开或残留进程时冲突。"""
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def check_resources() -> list:
    """启动前检查必需的资源，缺什么直接说清楚。

    返回 [(名字, 说明), ...]，交给启动窗口分两栏显示。
    """
    missing = []
    if not (DATA_DIR / "config.json").is_file():
        missing.append(("config.json",
                        '应放在数据目录，内容示例：'
                        '{"api_key": "你的智谱key", "model": "glm-4.6"}'))
    if not (DATA_DIR / "flows").is_dir():
        missing.append(("flows", "缺少流程目录"))
    if not (DATA_DIR / "verbs").is_dir():
        missing.append(("verbs", "缺少动词包目录"))
    if not (DATA_DIR / "workspace" / "japanese" / "content").is_dir():
        missing.append(("content", "缺少教材目录"))
    if not (HERE / "web" / "index.html").is_file():
        missing.append(("web", "界面还没生成，跑一次：py app2/build.py"))
    return missing


def error_window(missing) -> None:
    """资源缺失时弹一个说明窗口，而不是闷声退出。

    页面由 ui/startup.ui 描述，build.py 烤成 startup_html.py 里的一个
    字符串常量。这里只填数据——运行时不碰模板引擎，因为这个窗口恰恰是
    「环境不齐」时才弹的，不该在最脆弱的时刻引入最多依赖。
    """
    import webview
    try:
        from app2.startup_html import fill
        html = fill(missing, DATA_DIR)
    except ImportError:
        # 连启动窗口都还没生成，只能退回纯文本
        body = "<br>".join(f"{w}：{t}" for w, t in missing)
        html = ("<!doctype html><meta charset='utf-8'><body style='font:14px "
                "sans-serif;padding:28px'><h2>启动前还差点东西</h2>"
                f"<p>{body}</p><p>先跑一次 py app2/build.py</p></body>")
    webview.create_window(TITLE, html=html, width=680, height=460)
    webview.start()


def main() -> None:
    import webview

    missing = check_resources()
    if missing:
        error_window(missing)
        return

    import uvicorn
    from app2.serve import app

    port = free_port()

    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

    threading.Thread(target=run_server, daemon=True).start()

    # 等服务器起来再开窗口，否则会闪一下空白页
    for _ in range(60):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)

    webview.create_window(
        TITLE,
        f"http://127.0.0.1:{port}",
        width=920,
        height=740,
        min_size=(560, 480),
    )
    webview.start()


if __name__ == "__main__":
    main()
