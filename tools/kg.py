# -*- coding: utf-8 -*-
"""日语学习知识图谱：节点表与关系推导。

两种跑法都行：

    py -m tools.kg          从 mcp/ 目录，作为包运行
    py kg.py                直接跑这个文件

产物路径自动找：从本文件往上找含 workspace/japanese 的目录，找不到就落在
本文件旁边的 content/ 里。

为什么是脚本而不是直接存 JSON：
「解锁」是「前置」的反向、「对照」是双向的，两边都手写必然写歪——加一条
边要改两处，漏一处就出现 A 说解锁 B、B 却不认 A。这里只声明「前置」和
「对照」的一侧，反向自动推出来，再校验环、悬空引用、层级单调。

边的四种关系，只有前两种决定解锁顺序：

    前置   学 B 必须先掌握 A          辞书形 → て形
    构成   B 由 A 变形而来            并入「前置」，形态上是一回事
    对照   B 要跟 A 对比才讲得清      は ↔ が、たら ↔ ば
    应用   B 是 A 的具体用法          て形 → てください，也并入「前置」

「对照」是横向连接，不影响解锁，用来组织复习和挑干扰项——出题时优先从
对照组里选干扰项，比随机抽的更能考出区别。

掌握判据挂在节点上，出题时按「考点」去题库筛。图谱和题库因此解耦：
图谱说「现在该考て形变化」，题库按考点供题，两边各自演进。
"""

import json
import sys
from collections import Counter, deque
from pathlib import Path

# (id, 名称, 层, 类型, 前置, 对照, 掌握考点)
#
# 层只是粗分，真正的顺序由「前置」决定——校验会保证前置的层不高于自己。
# 分层用来排版，以及回答「这个阶段能学什么」。
RAW = [
    # 层0 文字 —— 一切的起点
    ("hiragana", "平假名", 0, "文字", [], [], "假名认读"),
    ("katakana", "片假名", 0, "文字", ["hiragana"], ["hiragana"], "假名认读"),
    ("kanji-basic", "汉字与音训读", 0, "文字", ["hiragana"], [], "汉字读法"),

    # 层1 音韵 —— 不掌握的话后面所有变形都读不对
    ("dakuon", "浊音半浊音", 1, "音韵", ["hiragana"], [], "浊音辨别"),
    ("youon", "拗音", 1, "音韵", ["dakuon"], [], "拗音辨别"),
    ("sokuon", "促音", 1, "音韵", ["youon"], [], "促音辨别"),
    ("chouon", "长音", 1, "音韵", ["sokuon"], [], "长音辨别"),
    ("pitch", "高低音调", 1, "音韵", ["chouon"], [], "音调辨别"),

    # 层2 词类 —— 动词三类划分是后面所有活用的地基
    ("noun", "名词", 2, "词类", ["kanji-basic", "chouon"], [], "词义"),
    ("verb-groups", "动词三类划分", 2, "词类", ["kanji-basic", "chouon"], [], "动词分类"),
    ("i-adj", "い形容词", 2, "词类", ["noun"], ["na-adj"], "词义"),
    ("na-adj", "な形容词", 2, "词类", ["noun"], ["i-adj"], "词义"),
    ("adverb", "副词", 2, "词类", ["noun"], [], "词义"),
    ("onomatopoeia", "拟声拟态词", 2, "词类", ["adverb"], [], "词义"),

    # 层3 基本活用 —— て形是整棵树最大的枢纽
    ("masu-form", "ます形", 3, "活用", ["verb-groups"], [], "ます形变化"),
    ("dict-form", "辞书形", 3, "活用", ["masu-form"], [], "辞书形变化"),
    ("nai-form", "ない形", 3, "活用", ["dict-form"], [], "ない形变化"),
    ("te-form", "て形", 3, "活用", ["dict-form"], ["ta-form"], "て形变化"),
    ("ta-form", "た形", 3, "活用", ["te-form"], ["te-form"], "た形变化"),
    ("i-adj-conj", "い形容词活用", 3, "活用", ["i-adj"], ["na-adj-conj"], "形容词活用"),
    ("na-adj-conj", "な形容词活用", 3, "活用", ["na-adj"], ["i-adj-conj"], "形容词活用"),
    ("plain-polite", "简体与敬体", 3, "活用", ["nai-form", "ta-form"], [], "文体辨别"),

    # 层4 助词 —— 有词类和ます形就能开始，不必等活用学完
    ("wa-ga", "は と が", 4, "助词", ["noun", "masu-form"], [], "助词选择"),
    ("wo", "を", 4, "助词", ["wa-ga"], [], "助词选择"),
    ("ni-de", "に と で", 4, "助词", ["wo"], [], "助词选择"),
    ("he-to", "へ と と", 4, "助词", ["ni-de"], [], "助词选择"),
    ("kara-made", "から まで より", 4, "助词", ["ni-de"], [], "助词选择"),
    ("no", "の", 4, "助词", ["noun"], [], "助词选择"),
    ("mo", "も", 4, "助词", ["wa-ga"], [], "助词选择"),
    ("ka-ne-yo", "终助词 か ね よ", 4, "助词", ["plain-polite"], [], "语气辨别"),

    # 层5 句型 —— 多数挂在て形和た形下，可以并行学
    ("te-iru", "ている", 5, "句型", ["te-form"], [], "句型运用"),
    ("te-kudasai", "てください", 5, "句型", ["te-form"], [], "句型运用"),
    ("te-kara", "てから", 5, "句型", ["te-form"], [], "句型运用"),
    ("te-mo-ii", "てもいい", 5, "句型", ["te-form"], ["te-wa-ikenai"], "句型运用"),
    ("te-wa-ikenai", "てはいけない", 5, "句型", ["te-form"], ["te-mo-ii"], "句型运用"),
    ("te-oku", "ておく", 5, "句型", ["te-form"], [], "句型运用"),
    ("te-shimau", "てしまう", 5, "句型", ["te-form"], [], "句型运用"),
    ("te-miru", "てみる", 5, "句型", ["te-form"], [], "句型运用"),
    ("ta-koto-ga-aru", "たことがある", 5, "句型", ["ta-form"], [], "句型运用"),
    ("ta-hou-ga-ii", "たほうがいい", 5, "句型", ["ta-form"], [], "句型运用"),
    ("nakereba", "なければならない", 5, "句型", ["nai-form"], ["nakute-mo-ii"], "句型运用"),
    ("nakute-mo-ii", "なくてもいい", 5, "句型", ["nai-form"], ["nakereba"], "句型运用"),
    ("naide-kudasai", "ないでください", 5, "句型", ["nai-form"], ["te-kudasai"], "句型运用"),
    ("tai", "たい", 5, "句型", ["masu-form"], ["hoshii"], "句型运用"),
    ("hoshii", "ほしい", 5, "句型", ["i-adj-conj"], ["tai"], "句型运用"),
    ("to-omou", "と思う", 5, "句型", ["plain-polite"], ["to-iu"], "句型运用"),
    ("to-iu", "という", 5, "句型", ["plain-polite"], ["to-omou"], "句型运用"),
    ("node-kara", "ので と から", 5, "句型", ["plain-polite"], [], "接续辨别"),
    ("ga-kedo", "が と けど", 5, "句型", ["plain-polite"], ["node-kara"], "接续辨别"),
    # 四个条件句互为对照——它们的区别正是 N3 的高频考点
    ("conditional-tara", "たら", 5, "句型", ["ta-form"], ["conditional-ba"], "条件句辨别"),
    ("conditional-ba", "ば", 5, "句型", ["dict-form"], ["conditional-tara"], "条件句辨别"),
    ("conditional-to", "と（条件）", 5, "句型", ["dict-form"], ["conditional-ba"], "条件句辨别"),
    ("conditional-nara", "なら", 5, "句型", ["plain-polite"], ["conditional-tara"], "条件句辨别"),

    # 层6 高级活用 —— 受身和使役要先有助词基础，否则讲不清施受关系
    ("potential", "可能形", 6, "活用", ["dict-form", "wo"], [], "可能形变化"),
    ("volitional", "意志形", 6, "活用", ["masu-form"], [], "意志形变化"),
    ("imperative", "命令形", 6, "活用", ["dict-form"], ["volitional"], "命令形变化"),
    ("passive", "受身形", 6, "活用", ["nai-form", "ni-de"], ["causative"], "受身形变化"),
    ("causative", "使役形", 6, "活用", ["nai-form", "wo"], ["passive"], "使役形变化"),
    ("causative-passive", "使役受身形", 6, "活用", ["passive", "causative"], [], "使役受身变化"),
    ("transitive-pair", "自他动词对", 6, "活用", ["verb-groups", "wo"], ["passive"], "自他动词辨别"),

    # 层7 待遇表现 —— 尊敬语要先学受身，因为れる/られる形态相同
    ("ageru-kureru", "授受 あげる くれる もらう", 7, "待遇", ["te-form", "ni-de"], [], "授受辨别"),
    ("te-ageru", "てあげる てくれる てもらう", 7, "待遇", ["ageru-kureru"], [], "授受辨别"),
    ("sonkeigo", "尊敬语", 7, "待遇", ["plain-polite", "passive"], ["kenjougo"], "敬语辨别"),
    ("kenjougo", "谦让语", 7, "待遇", ["plain-polite"], ["sonkeigo"], "敬语辨别"),
    ("teineigo", "丁宁语", 7, "待遇", ["plain-polite"], ["sonkeigo", "kenjougo"], "敬语辨别"),

    # 层8 综合 —— 现有 N2N3 词汇题库挂在这一层
    ("keigo-usage", "敬语综合运用", 8, "待遇",
     ["sonkeigo", "kenjougo", "teineigo", "te-ageru"], [], "敬语辨别"),
    ("synonym-nuance", "近义词辨析", 8, "语感",
     ["i-adj-conj", "na-adj-conj", "te-iru"], [], "词义"),
    ("kanji-writing", "汉字书写", 8, "语感", ["kanji-basic", "synonym-nuance"], [], "汉字书写"),
    ("collocation", "惯用搭配", 8, "语感", ["synonym-nuance", "onomatopoeia"], [], "搭配辨别"),
]

DEFAULT_RULE = {"正确率": 80, "最少题数": 8}


def out_dir() -> Path:
    """产物目录：往上找含 workspace/japanese 的目录，找不到就用本文件旁边。

    这样不管文件放在 mcp/tools/ 还是 mcp/data/tools/，产物都落在同一处；
    两处都找不到时退回本地，至少能跑起来看结果。
    """
    here = Path(__file__).resolve()
    for base in here.parents:
        cand = base / "workspace" / "japanese" / "content"
        if cand.parent.is_dir():
            return cand
    return here.parent / "content"


def build() -> list[dict]:
    """从 RAW 推出完整节点表：解锁是前置的反向，对照补成双向。"""
    nodes = [
        {
            "id": nid, "名称": name, "层": layer, "类型": kind,
            "前置": list(pre), "对照": list(contrast), "解锁": [],
            "掌握判据": {"考点": point, **DEFAULT_RULE},
        }
        for nid, name, layer, kind, pre, contrast, point in RAW
    ]
    by_id = {n["id"]: n for n in nodes}

    for n in nodes:
        for p in n["前置"]:
            if p in by_id:
                by_id[p]["解锁"].append(n["id"])
    for n in nodes:
        for c in n["对照"]:
            if c in by_id and n["id"] not in by_id[c]["对照"]:
                by_id[c]["对照"].append(n["id"])
    return nodes


def check(nodes: list[dict]) -> list[str]:
    """校验：id 唯一、引用存在、前置无环、层级单调、正反向一致。"""
    errs: list[str] = []
    by_id = {n["id"]: n for n in nodes}

    if len(by_id) != len(nodes):
        dup = [i for i, c in Counter(n["id"] for n in nodes).items() if c > 1]
        errs.append(f"重复 id：{dup}")

    for n in nodes:
        for key in ("前置", "对照", "解锁"):
            for ref in n.get(key, []):
                if ref not in by_id:
                    errs.append(f"{n['id']}.{key} 指向不存在的 {ref}")

    # 拓扑排序查环。有环的话学习者会卡死：A 要先学 B，B 又要先学 A
    indeg = {i: 0 for i in by_id}
    adj: dict[str, list[str]] = {i: [] for i in by_id}
    for n in nodes:
        for p in n["前置"]:
            if p in by_id:
                adj[p].append(n["id"])
                indeg[n["id"]] += 1
    q = deque(i for i, d in indeg.items() if d == 0)
    done = 0
    while q:
        cur = q.popleft()
        done += 1
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    if done != len(by_id):
        stuck = sorted(i for i, d in indeg.items() if d > 0)
        errs.append(f"前置存在环，涉及 {len(stuck)} 个：{stuck[:8]}")

    for n in nodes:
        for p in n["前置"]:
            if p in by_id and by_id[p]["层"] > n["层"]:
                errs.append(
                    f"{n['id']}(层{n['层']}) 的前置 {p}(层{by_id[p]['层']}) 层级更高")

    for n in nodes:
        for u in n["解锁"]:
            if u in by_id and n["id"] not in by_id[u]["前置"]:
                errs.append(f"{n['id']}.解锁 含 {u}，但对方前置里没有")

    return errs


def depth_of(nodes: list[dict]) -> dict[str, int]:
    """到根的最长路径，就是真实的学习步数。"""
    by_id = {n["id"]: n for n in nodes}
    memo: dict[str, int] = {}

    def walk(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        pre = by_id[nid]["前置"]
        memo[nid] = 0 if not pre else 1 + max(walk(p) for p in pre)
        return memo[nid]

    for n in nodes:
        walk(n["id"])
    return memo


def unlocked(nodes: list[dict], mastered: set[str]) -> list[str]:
    """给定已掌握的节点，返回现在可以学的。"""
    return [n["id"] for n in nodes
            if n["id"] not in mastered and all(p in mastered for p in n["前置"])]


def summary(nodes: list[dict]) -> str:
    by_id = {n["id"]: n for n in nodes}
    depth = depth_of(nodes)
    roots = [n["名称"] for n in nodes if not n["前置"]]
    hub = max(nodes, key=lambda n: len(n["解锁"]))

    far = max(depth, key=lambda k: depth[k])
    path, cur = [far], far
    while by_id[cur]["前置"]:
        cur = max(by_id[cur]["前置"], key=lambda p: depth[p])
        path.append(cur)

    return "\n".join([
        f"节点 {len(nodes)} 个，最长学习链 {depth[far] + 1} 步",
        f"按层：{dict(sorted(Counter(n['层'] for n in nodes).items()))}",
        f"按类型：{dict(Counter(n['类型'] for n in nodes))}",
        f"根节点：{'、'.join(roots)}",
        f"最大枢纽：{hub['名称']}（解锁 {len(hub['解锁'])} 个）",
        "最长链：" + " → ".join(by_id[i]["名称"] for i in reversed(path)),
    ])


def main() -> int:
    nodes = build()
    errs = check(nodes)

    print(summary(nodes))
    print()
    if errs:
        print(f"校验发现 {len(errs)} 个问题：")
        for e in errs[:20]:
            print("  ", e)
        return 1
    print("校验通过：无重复 id、无悬空引用、无环、层级单调、正反向一致")

    by_id = {n["id"]: n for n in nodes}
    print("\n从零开始可以学：",
          "、".join(by_id[i]["名称"] for i in unlocked(nodes, set())))

    if "--check" in sys.argv:
        return 0

    out = out_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "kg.json").write_text(
        json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入 {out / 'kg.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
