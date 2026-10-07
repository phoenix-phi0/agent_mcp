"""在沙箱的 .py 里按正则搜，返回「文件:行号: 那一行」。例如 设 r = 搜索代码 def\\s+pace

plan3：命中超过 30 条时返回 总命中数 + 按文件分组的命中数（每文件一行）+ 前 30 条 + 一句「结果太多，请换更精确的关键词」。
正则写错返回错误说明（不抛），让模型改。每次搜索写一行到状态目录的 verb_log.jsonl。
"""

import json
import re
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")
LIMIT = 30


def _log(root, rec):
    from _sandbox import state_dir
    try:
        with open(state_dir(root) / "verb_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def 搜索代码(正则: str = "") -> str:
    sys.path.insert(0, str(Path(__file__).parent))
    from _sandbox import py_files
    root = Path(WORKSPACE).resolve()
    if not str(正则).strip():
        return "[搜索] 没给正则"
    try:
        pat = re.compile(str(正则))
    except re.error as e:
        _log(root, {"verb": "搜索代码", "pat": str(正则), "err": str(e)})
        return f"[搜索] 正则写错了（{e}）：{正则}"
    hits, total, per = [], 0, {}
    for rel in py_files(root):
        for i, line in enumerate((root / rel).read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                total += 1
                per[rel] = per.get(rel, 0) + 1
                if len(hits) < LIMIT:
                    hits.append(f"{rel}:{i}: {line.rstrip()}")
    _log(root, {"verb": "搜索代码", "pat": str(正则), "total": total, "files": len(per), "over": total > LIMIT})
    if not hits:
        return f"[搜索] 没有匹配：{正则}"
    if total <= LIMIT:
        return "\n".join(hits)
    groups = "\n".join(f"  {f}：{c} 条" for f, c in sorted(per.items(), key=lambda x: -x[1]))
    return (f"[搜索] 共 {total} 条命中，分布在 {len(per)} 个文件：\n{groups}\n"
            f"前 {LIMIT} 条：\n" + "\n".join(hits)
            + "\n结果太多，请换更精确的关键词（例如具体的标识符、编号、函数名）")
