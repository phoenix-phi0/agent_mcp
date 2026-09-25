# -*- coding: utf-8 -*-
"""把「条目」从图里拆出来，一次性的迁移脚本。

    cd /home/ysc/mcp && .venv/bin/python tools/kg_split.py --试   # 只看不写
    cd /home/ysc/mcp && .venv/bin/python tools/kg_split.py        # 真写

## 为什么拆

图里 128 个节点，72 个是叶子——不是任何节点的前置，除了「有前置」之外在
图里没有结构作用。「ざるを得ない」和「とても」的区别只有一条：前者有前置。
但「有前置」不构成图：一个单词同样可以说「学它之前要先会平假名」。

所以图只留**被别的东西依赖的结构点**，条目挪到 item 表：

    node   文字、音韵、词类、活用形、助词、基本句型        ~64 个
    item   てください、ざるを得ない、にもかかわらず……      ~64 个

## 拆完之后

item.point 指向所属的结构点（取条目前置里第一个结构点）。
item.after 记条目之间的先后（条目的前置里如果有别的条目，取第一个）——
那不是图的边，不参与环检查，只用来排同一个结构点下面的学习顺序。

结构点若依赖了某个条目（比如「简体与敬体」依赖「なければならない」），
那条边改指向该条目所属的结构点——否则图里会留下指向不存在节点的边。
"""

import json
import sys
from pathlib import Path

KG = Path(__file__).resolve().parent.parent / "kg" / "content"

# 条目：搭在某个形式上的固定表达
ITEM_PREFIX = ("te-", "ta-", "nakute", "naide", "nakereba", "conditional-")
ITEM_IDS = {
    "tai", "hoshii", "to-omou", "to-iu", "ka-ne-yo", "te-ageru",
    "ni-okeru", "ni-kanshite", "wo-megutte", "ni-motozuite", "to-shite",
    "ni-totte", "ni-yotte", "ni-taishite", "koso", "sae", "bakari-ka",
    "ni-kagitte", "dake-de-naku", "hodo", "nimo-kakawarazu", "monono",
    "tsutsumo", "kuseni", "tokoroga", "okage-sei", "yueni", "dake-ni",
    "ijou-wa", "zaru-wo-enai", "wake-ni-wa-ikanai", "zu-ni-wa-irarenai",
    "hoka-nai", "shidai", "totanni", "kake", "tsutsu-aru", "uchi-ni",
    "aida-ni", "ni-chigainai", "kanenai", "ppoi", "ge", "you-mitai",
    "rashii", "souda-densetsu", "souda-youtai",
}
# 形式本身，不是条目——它们下面挂着一堆条目
KEEP = {"te-form", "ta-form", "te-iru", "ageru-kureru", "dict-form", "nai-form"}


def is_item(code: str) -> bool:
    if code in KEEP:
        return False
    return code in ITEM_IDS or code.startswith(ITEM_PREFIX)


def main() -> int:
    dry = "--试" in sys.argv
    src = KG / "kg.jsonl"
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    by = {r["id"]: r for r in rows}

    items, nodes = [], []
    for r in rows:
        (items if is_item(r["id"]) else nodes).append(r)
    item_ids = {r["id"] for r in items}

    def anchor(code: str, seen=None) -> str:
        """顺着前置往上找第一个结构点。条目挂条目时要往上追。"""
        seen = seen or set()
        for p in by[code]["prereq"]:
            if p in seen:
                continue
            if p not in item_ids:
                return p
        for p in by[code]["prereq"]:
            if p in item_ids and p not in seen:
                got = anchor(p, seen | {code})
                if got:
                    return got
        return ""

    out_items = []
    for r in items:
        a = anchor(r["id"])
        if not a:
            print(f"[跳过] {r['id']} 找不到所属的结构点")
            continue
        after = next((p for p in r["prereq"] if p in item_ids), "")
        out_items.append({"code": r["id"], "label": r["label"],
                          "point": a, "after": after})

    # 结构点依赖条目的边：改指向该条目所属的结构点
    fixed = 0
    for r in nodes:
        new = []
        for p in r["prereq"]:
            if p in item_ids:
                a = anchor(p)
                if a and a != r["id"] and a not in new:
                    new.append(a)
                    fixed += 1
            elif p not in new:
                new.append(p)
        r["prereq"] = sorted(new)

    print(f"结构点 {len(nodes)}，条目 {len(out_items)}，改指的边 {fixed}")
    if dry:
        print("（试跑，没写文件）")
        return 0

    src.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in nodes),
                   encoding="utf-8")
    (KG / "items.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_items),
        encoding="utf-8")
    print(f"写了 {src.name}（{len(nodes)} 行）和 items.jsonl（{len(out_items)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
