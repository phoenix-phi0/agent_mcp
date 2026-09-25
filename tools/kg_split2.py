# -*- coding: utf-8 -*-
"""把图里剩下的具体文法也拆成条目，一次性的迁移脚本。

    cd /home/ysc/mcp && .venv/bin/python tools/kg_split2.py --试
    cd /home/ysc/mcp && .venv/bin/python tools/kg_split2.py

上一轮（kg_split.py）拆掉了「搭在形式上的固定表达」，图从 128 缩到 65。
剩下的 65 个里还有 10 个是具体文法——助词和固定说法：

    は と が、を、に と で、へ と と、から まで より、の、も
    ている、ので と から、が と けど

它们跟「ておく」「ざるを得ない」是同一类：具体的一条说法，不是能生成无数
实例的类别。留在图里只是因为当初我把它们写成了别的节点的前置。

## 拆法

新增一个类别节点「助词」（particle），它才是结构点：「学会助词怎么用」是
一件事，「は と が」是它下面的一条。ている 归到「て形」下面。

原来依赖这些具体文法的节点（可能形依赖 を、受身形依赖 に と で……），
改成依赖「助词」这个类别——依赖的本来就是「会用助词」，不是「会用を」
这一条。
"""

import json
import sys
from pathlib import Path

KG = Path(__file__).resolve().parent.parent / "kg" / "content"

# 具体文法 -> 它属于哪个类别
MOVE = {
    "wa-ga": "particle", "wo": "particle", "ni-de": "particle",
    "he-to": "particle", "kara-made": "particle", "no": "particle",
    "mo": "particle", "node-kara": "particle", "ga-kedo": "particle",
    "te-iru": "te-form",
}

# 新增的类别节点。前置取原来那批助词里最早的那个的前置。
NEW_NODES = [
    {"id": "particle", "label": "助词", "prereq": ["masu-form", "noun"]},
]


def main() -> int:
    dry = "--试" in sys.argv
    kg_path, items_path = KG / "kg.jsonl", KG / "items.jsonl"
    nodes = [json.loads(l) for l in kg_path.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines()
             if l.strip()] if items_path.is_file() else []

    by = {n["id"]: n for n in nodes}
    moved = [n for n in nodes if n["id"] in MOVE]
    kept = [n for n in nodes if n["id"] not in MOVE]

    # 新类别节点插在被移走的那批之前
    have = {n["id"] for n in kept}
    for nn in NEW_NODES:
        if nn["id"] not in have:
            kept.append(nn)
            by[nn["id"]] = nn

    def redirect(code: str) -> str:
        """指向被移走的节点 -> 改指它所属的类别。"""
        seen = set()
        while code in MOVE and code not in seen:
            seen.add(code)
            code = MOVE[code]
        return code

    # 留下的节点：前置里指向被移走的，改指类别
    fixed = 0
    for n in kept:
        new = []
        for p in n["prereq"]:
            q = redirect(p)
            if q != n["id"] and q not in new:
                if q != p:
                    fixed += 1
                new.append(q)
        n["prereq"] = sorted(new)

    # 被移走的变成条目。它们之间的先后（を 在 は と が 之后）用 after 记
    new_items = []
    for n in moved:
        point = redirect(MOVE[n["id"]])
        after = next((p for p in n["prereq"] if p in MOVE), "")
        new_items.append({"code": n["id"], "label": n["label"],
                          "point": point, "after": after})

    # 已有条目里，point 指向被移走的节点的，也要改指
    for it in items:
        it["point"] = redirect(it["point"])

    all_items = items + new_items
    print(f"结构点 {len(kept)}（原 {len(nodes)}，移走 {len(moved)}，新增 {len(NEW_NODES)}）")
    print(f"条目 {len(all_items)}（原 {len(items)}，新增 {len(new_items)}）")
    print(f"改指的前置 {fixed}")
    print("移走的：" + "、".join(n["label"] for n in moved))
    if dry:
        print("（试跑，没写文件）")
        return 0

    kg_path.write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in kept),
                       encoding="utf-8")
    items_path.write_text(
        "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in all_items),
        encoding="utf-8")
    print(f"写了 {kg_path.name}（{len(kept)} 行）和 {items_path.name}（{len(all_items)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
