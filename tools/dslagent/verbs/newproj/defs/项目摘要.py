"""项目现状摘要，给提示词用：queries 语句名、routes/*.zs 里的「接口 方法 路径 动作」（带所在文件）、已有界面名。
参数 JSON：{项目目录: 默认 ".", 含参数: 是|否}（也可直接给目录名）；含参数=是时 queries 行写成 名(参数,…)（split 模板给模型看已有 sql 的参数）。返回 {text, queries, routes, uis}；失败时 text 以 [项目摘要] 开头。
"""
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
API = re.compile(r"^接口\s+(\w+)\s+(\S+)(?:\s+动作\s+(\S+))?", re.M)
PARAM = re.compile(r"(?<![:\w]):(\w+)")
SCREEN = re.compile(r"^界面\s+\S+\s+(\S+)", re.M)


def 项目摘要(参数: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    arg = 参数 if isinstance(参数, dict) else str(参数 or "").strip()
    if isinstance(arg, str) and arg and not arg.startswith("{"):
        arg = {"项目目录": arg}
    o, err = G.parse_obj(arg)
    if err:
        return {"text": f"[项目摘要] {err}", "queries": [], "routes": [], "uis": []}
    root, err = G.project_root(WORKSPACE, o.get("项目目录"))
    if err:
        return {"text": f"[项目摘要] {err}", "queries": [], "routes": [], "uis": []}
    if G.is_dry():
        return {"text": "queries 语句名: a_list\nroutes/a.zs: POST /a/list 动作=a_list\ngen 已有界面名: a列表",
                "queries": ["a_list"], "routes": [{"file": "routes/a.zs", "method": "POST", "path": "/a/list", "action": "a_list"}],
                "uis": ["a列表"]}

    def rel(f):
        return str(f.relative_to(root))
    qfiles = sorted((root / "queries").rglob("*.sql"), key=lambda f: f.stem)
    queries = [f.stem for f in qfiles]
    show = queries
    if str(o.get("含参数") or "").strip() == "是":
        show = [f"{f.stem}({','.join(sorted(set(PARAM.findall(f.read_text(encoding='utf-8', errors='replace')))))})" for f in qfiles]
    routes = []
    for f in sorted((root / "routes").rglob("*.zs")):
        for m in API.finditer(f.read_text(encoding="utf-8", errors="replace")):
            routes.append({"file": rel(f), "method": m.group(1), "path": m.group(2), "action": m.group(3) or ""})
    uis = [n for f in sorted((root / "ui").rglob("*.ui")) for n in SCREEN.findall(f.read_text(encoding="utf-8", errors="replace"))]
    lines = ["queries 语句名: " + ", ".join(show)]
    lines += [f"{r['file']}: {r['method']} {r['path']} 动作={r['action'] or '-'}" for r in routes]
    lines.append("gen 已有界面名: " + ", ".join(uis))
    return {"text": "\n".join(lines), "queries": queries, "routes": routes, "uis": uis}
