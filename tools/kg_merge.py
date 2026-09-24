# -*- coding: utf-8 -*-
"""把新节点并进 kg.jsonl。

    cd /home/ysc/mcp && .venv/bin/python tools/kg_merge.py kg/content/new_nodes.jsonl

图存成 JSONL，一行一个知识点，三个键：

    {"id": "katakana", "label": "片假名", "prereq": ["hiragana"]}

改一个节点只动一行，diff 看得清；导入器报错的行号也直接对得上。

这个脚本只做三件检查，有一项不过就一条都不写——改一半的图比不改更难收拾：

  前置指向的编号存不存在
  有没有环（加边时一条条查是导入器的事，这里整体查一遍）
  已存在的 id 会被更新（label、prereq 以新的为准），不会重复

早先它还负责算「解锁」和补「对照」双向，那两个字段已经从文件里去掉了：
解锁是前置的反向，查库里的边表就有；对照不是图的边，在 contrast.jsonl 里。
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

KG = Path(__file__).resolve().parent.parent / "kg" / "content" / "kg.jsonl"
KEYS = ["id", "label", "prereq"]


def load(path: Path) -> list:
    """JSONL 或 JSON 数组都认。"""
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        return json.loads(text)
    return [json.loads(x) for x in text.splitlines()
            if x.strip() and not x.lstrip().startswith("#")]


def merge(kg_path: Path, new_path: Path) -> str:
    nodes = load(kg_path) if kg_path.is_file() else []
    incoming = load(new_path)

    by_id = {n["id"]: n for n in nodes}
    order = [n["id"] for n in nodes]
    added, updated = [], []
    for n in incoming:
        if n["id"] in by_id:
            by_id[n["id"]].update(n)
            updated.append(n["id"])
        else:
            by_id[n["id"]] = dict(n)
            order.append(n["id"])
            added.append(n["id"])

    missing = sorted({p for n in by_id.values() for p in n.get("prereq", [])
                      if p not in by_id})
    if missing:
        raise SystemExit(f"[出错] 这些前置不存在：{'、'.join(missing)}")

    g = defaultdict(list)
    for n in by_id.values():
        for p in n.get("prereq", []):
            g[p].append(n["id"])
    state, cycles = {}, []

    def walk(u, path):
        state[u] = 1
        path.append(u)
        for v in g[u]:
            if state.get(v) == 1:
                cycles.append(" → ".join(path[path.index(v):] + [v]))
            elif v not in state:
                walk(v, path)
        path.pop()
        state[u] = 2

    for i in order:
        if i not in state:
            walk(i, [])
    if cycles:
        raise SystemExit("[出错] 成环了：\n  " + "\n  ".join(cycles))

    # 键的顺序固定，不然每次合并整个文件的 diff 都在动
    lines = []
    for i in order:
        n = by_id[i]
        n["prereq"] = sorted(n.get("prereq", []))
        ordered = {k: n[k] for k in KEYS if k in n}
        ordered.update({k: v for k, v in n.items() if k not in KEYS})
        lines.append(json.dumps(ordered, ensure_ascii=False))
    kg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = f"新增 {len(added)}，更新 {len(updated)}，现在共 {len(order)} 个节点"
    return out + (f"\n  新增：{'、'.join(added)}" if added else "")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("用法：python tools/kg_merge.py <新节点.jsonl>")
    print(merge(KG, Path(sys.argv[1])))
