"""把「=== 路径 ===」分隔的多文件文本拆成 {files:[{file, content}], n}，可直接喂 写文件。
去代码围栏；只留以前缀开头的路径；路径含 .. / 绝对路径 / 反斜杠的丢掉（记在 rejected 里）。
例如 设 blocks = 拆分隔块 {sqlTxt} queries/
"""
import re

WORKSPACE = None
PACK_DIR = None
HEAD = re.compile(r"^=== (\S+) ===[ \t]*$", re.M)
FENCE = re.compile(r"^```[^\n]*\n(.*?)\n?```[ \t]*$", re.S)


def 拆分隔块(文本: str = "", 前缀: str = "") -> dict:
    text = str(文本 or "").replace("\r\n", "\n")
    prefix = str(前缀 or "").strip()
    out, rejected = [], []
    if not prefix:
        return {"files": [], "n": 0, "rejected": [], "msg": "没给路径前缀"}
    parts = HEAD.split(text)
    for i in range(1, len(parts) - 1, 2):
        name, body = parts[i], parts[i + 1].strip()
        m = FENCE.match(body)
        if m:
            body = m.group(1).strip()
        if ".." in name.split("/") or name.startswith("/") or "\\" in name or ".." in name:
            rejected.append(name)
            continue
        if not name.startswith(prefix):
            rejected.append(name)
            continue
        out.append({"file": name, "content": body + "\n"})
    return {"files": out, "n": len(out), "rejected": rejected}
