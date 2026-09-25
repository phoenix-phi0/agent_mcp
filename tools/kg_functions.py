# -*- coding: utf-8 -*-
"""给条目加一层「功能」节点，一次性的迁移脚本。

    cd /home/ysc/mcp && .venv/bin/python tools/kg_functions.py --试
    cd /home/ysc/mcp && .venv/bin/python tools/kg_functions.py

## 为什么

拆完之后条目是按「接在哪个形式后面」挂的，结果很怪：

    助词       24 个：における、こそ、にもかかわらず、おかげで、ゆえに……
    简体与敬体  14 个：と思う、に関して、に違いない、ようだ、らしい……

「にもかかわらず」（逆接）和「おかげで」（原因）挤在一起，只因为它们都接
名词或助词。学生要找的是「表示逆接的有哪些」，不是「接在助词后面的有哪些」。

## 功能是不是节点

是——功能有前置：要学「条件表达」，得先会辞书形、た形、ない形，因为四个
条件形接在它们后面。所以功能节点的前置 = 它下面所有条目原本挂的那些形式。
这样图仍然是「学这个之前要先会那些」，没有破坏。

形式那条信息不丢：记在条目的 form 列上（接续和变形要用），而 point 改指
功能（决定什么时候用）。
"""

import json
import sys
from pathlib import Path

KG = Path(__file__).resolve().parent.parent / "kg" / "content"

# 功能节点：编号 -> 中文名
FUNCS = {
    "f-condition": "条件表达",
    "f-cause": "原因理由",
    "f-concession": "逆接让步",
    "f-obligation": "义务许可禁止",
    "f-desire": "意愿希望",
    "f-conjecture": "推量判断",
    "f-time": "时间关系",
    "f-emphasis": "限定强调",
    "f-aspect": "体与补助动词",
    "f-written": "书面提示",
    "f-request": "请求指示",
    "f-quote": "引用与传闻",
    "f-evaluate": "建议评价",
}

# 条目 -> 功能。没列到的留在原处（格助词、终助词本来就属于「助词」）。
OF = {
    "f-condition": ["conditional-ba", "conditional-to", "conditional-tara",
                    "conditional-nara"],
    "f-cause": ["node-kara", "okage-sei", "yueni", "dake-ni", "ijou-wa"],
    "f-concession": ["ga-kedo", "nimo-kakawarazu", "monono", "tsutsumo",
                     "kuseni", "tokoroga"],
    "f-obligation": ["nakereba", "nakute-mo-ii", "te-mo-ii", "te-wa-ikenai",
                     "zaru-wo-enai", "wake-ni-wa-ikanai", "hoka-nai",
                     "zu-ni-wa-irarenai"],
    "f-desire": ["tai", "hoshii"],
    "f-conjecture": ["ni-chigainai", "you-mitai", "rashii", "souda-youtai",
                     "kanenai", "ppoi", "ge", "to-omou"],
    "f-time": ["te-kara", "aida-ni", "uchi-ni", "totanni", "shidai",
               "tsutsu-aru", "kake", "ta-koto-ga-aru"],
    "f-emphasis": ["koso", "sae", "bakari-ka", "dake-de-naku", "hodo",
                   "ni-kagitte"],
    "f-aspect": ["te-iru", "te-oku", "te-shimau", "te-miru", "te-ageru"],
    "f-written": ["ni-okeru", "ni-kanshite", "wo-megutte", "ni-motozuite",
                  "to-shite", "ni-totte", "ni-taishite", "ni-yotte"],
    "f-request": ["te-kudasai", "naide-kudasai"],
    "f-quote": ["to-iu", "souda-densetsu"],
    "f-evaluate": ["ta-hou-ga-ii"],
}


def main() -> int:
    dry = "--试" in sys.argv
    kg_path, items_path = KG / "kg.jsonl", KG / "items.jsonl"
    nodes = [json.loads(l) for l in kg_path.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    by_item = {i["code"]: i for i in items}

    where = {}
    for func, codes in OF.items():
        for c in codes:
            if c in by_item:
                where[c] = func
            else:
                print(f"[警告] 没有这个条目：{c}")

    # 功能节点的前置 = 它下面条目原本挂的那些形式
    pre = {f: set() for f in FUNCS}
    for code, func in where.items():
        pre[func].add(by_item[code]["point"])

    have = {n["id"] for n in nodes}
    added = []
    for f, label in FUNCS.items():
        if f in have:
            continue
        if not pre[f]:
            print(f"[跳过] {label} 下面一个条目都没有")
            continue
        added.append({"id": f, "label": label, "prereq": sorted(pre[f])})
    nodes += added

    # 条目：point 改指功能，原来的形式记到 form 上——接续和变形要用它
    #
    # 已经改过的不再动：这个脚本跑两遍的话，第二遍 point 已经是功能了，
    # form = point 会把形式覆盖成功能。一次性脚本被重复执行是常事，宁可
    # 写成可重入的。
    moved = 0
    for i in items:
        if i["code"] in where and i["point"] != where[i["code"]]:
            i["form"] = i["point"]
            i["point"] = where[i["code"]]
            moved += 1

    left = {}
    for i in items:
        if i["code"] not in where:
            left.setdefault(i["point"], []).append(i["label"])

    print(f"功能节点 {len(added)}，改挂的条目 {moved}/{len(items)}")
    for n in added:
        n_items = [by_item[c]["label"] for c, f in where.items() if f == n["id"]]
        print(f"  {n['label']:<10} <- {'、'.join(n['prereq']):<28} "
              f"{len(n_items)} 条：{'、'.join(n_items[:5])}"
              + ("…" if len(n_items) > 5 else ""))
    print(f"没改挂的 {sum(len(v) for v in left.values())} 条：")
    for k, v in left.items():
        print(f"  留在 {k}：{'、'.join(v)}")

    if dry:
        print("（试跑，没写文件）")
        return 0

    kg_path.write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in nodes),
                       encoding="utf-8")
    items_path.write_text(
        "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items),
        encoding="utf-8")
    print(f"写了 {kg_path.name}（{len(nodes)} 行）和 {items_path.name}（{len(items)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
