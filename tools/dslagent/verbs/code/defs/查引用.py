"""查一个名字在项目里的所有引用位置。例如 设 refs = 查引用 parse_date py

返回 {n, files, refs:[{file, line, text}], text}：text 每行「文件:行号: 那一行」（超过 200 行只列前 200，
refs 是全部）。按整词匹配（名字两边不能紧挨字母、数字、下划线），名字带点号（pkg.mod）也照字面找。
第二个参数写 py（或 仅py / .py）只看 .py 文件，不写看所有文本文件（二进制、超过 2MB 的跳过）。
排除 .venv、.git 等点开头的目录、__pycache__、node_modules、site-packages。
    设 refs = 查引用 old_name py
    如果 {refs.n} 大于 0 … 结束
"""

import re
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
SKIP_DIRS = {"__pycache__", "node_modules", "site-packages"}
MAX_BYTES = 2 * 1024 * 1024
TEXT_LIMIT = 200


def _skipped(parts):
    return any(p.startswith(".") or p in SKIP_DIRS for p in parts)


def 查引用(名字: str = "", 范围: str = "") -> dict:
    name = str(名字).strip()
    if not name:
        return {"n": 0, "files": 0, "refs": [], "text": "[查引用] 没给名字"}
    only_py = str(范围).strip().lower().lstrip("仅.") == "py"
    left = r"(?<![\w])" if re.match(r"\w", name[0]) else ""
    right = r"(?![\w])" if re.match(r"\w", name[-1]) else ""
    pat = re.compile(left + re.escape(name) + right)
    root = Path(WORKSPACE).resolve()
    refs, files = [], set()
    for p in sorted(root.rglob("*.py" if only_py else "*")):
        rel = p.relative_to(root)
        if _skipped(rel.parts[:-1]) or not p.is_file():
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue
        for i, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            if pat.search(line):
                refs.append({"file": rel.as_posix(), "line": i, "text": line.rstrip()})
                files.add(rel.as_posix())
    lines = [f"{r['file']}:{r['line']}: {r['text']}" for r in refs[:TEXT_LIMIT]]
    if len(refs) > TEXT_LIMIT:
        lines.append(f"……共 {len(refs)} 处，只列了前 {TEXT_LIMIT} 处（全部在 refs 里）")
    return {"n": len(refs), "files": len(files), "refs": refs,
            "text": "\n".join(lines) if refs else f"[查引用] 没有引用：{name}"}
