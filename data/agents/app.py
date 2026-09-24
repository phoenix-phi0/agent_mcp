"""JP-E01-π 桌面程序。

开发时运行：
    pip install pywebview
    py -m agents.app

打包成 exe：
    pip install pyinstaller
    见本文件末尾的说明，或用项目根目录的 build.bat

路径策略：
    打包后 PyInstaller 会把代码解压到临时目录，__file__ 指向那里，
    所以「程序自己的代码」和「用户要改的资源」必须分开定位：

        CODE_DIR  ← 代码所在（打包后是临时目录）
        DATA_DIR  ← exe 或项目所在（放 config.json / flows / verbs / workspace）

    flows、verbs、workspace、config.json 全部走 DATA_DIR，
    这样打包后你仍然可以直接编辑 .zs 和动词包，改完重启程序即可生效。
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

# 让 tools/agents 里那些按目录定位的代码找到正确的位置
os.environ.setdefault("ZHIPU_CONFIG", str(DATA_DIR / "config.json"))
os.environ.setdefault("JP_DATA_DIR", str(DATA_DIR))

TITLE = "JP-E01-π 日语教师"


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


def check_resources() -> list[str]:
    """启动前检查必需的资源，缺什么直接说清楚。"""
    missing = []
    if not (DATA_DIR / "config.json").is_file():
        missing.append(
            f"缺少 config.json（应放在 {DATA_DIR}）\n"
            '  内容示例：{"api_key": "你的智谱key", "model": "glm-4.6"}'
        )
    if not (DATA_DIR / "flows").is_dir():
        missing.append(f"缺少 flows 目录（应放在 {DATA_DIR}）")
    if not (DATA_DIR / "verbs").is_dir():
        missing.append(f"缺少 verbs 目录（应放在 {DATA_DIR}）")
    content = DATA_DIR / "workspace" / "japanese" / "content"
    if not content.is_dir():
        missing.append(f"缺少教材目录（应放在 {content}）")
    return missing


def error_window(lines: list[str]) -> None:
    """资源缺失时弹一个说明窗口，而不是闷声退出。"""
    import webview
    body = "<br>".join(
        l.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
        for l in lines
    )
    html = f"""<!doctype html><meta charset="utf-8">
<body style="font:14px/1.8 -apple-system,'Microsoft YaHei',sans-serif;
             padding:28px;color:#2b2825;background:#faf9f7">
<h2 style="margin:0 0 14px;font-size:16px">启动前还差点东西</h2>
<div style="background:#fff;border:1px solid #e6e2dc;border-radius:8px;
            padding:16px;font-family:ui-monospace,Menlo,monospace;
            font-size:13px;line-height:1.9">{body}</div>
<p style="color:#8a827a;font-size:13px;margin-top:16px">
补齐之后重新打开程序。</p></body>"""
    webview.create_window(TITLE, html=html, width=680, height=420)
    webview.start()


def main() -> None:
    import webview

    missing = check_resources()
    if missing:
        error_window(missing)
        return

    import uvicorn
    from agents.serve import app

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
