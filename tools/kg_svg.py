# -*- coding: utf-8 -*-
"""知识图谱可视化：把库里的节点和边画成 SVG。

    py -m tools.kg_svg                      画 kg/app.db，写到 kg/web/kg.svg
    py -m tools.kg_svg --db 别的.db --out x.svg
    py -m tools.kg_svg --mastered a,b,c     标出已掌握的

数据全部来自库（node / prereq / contrast 三张表），不再读 tools/kg.py 里
那份写死的节点表——那份是早期的，它用的字段（名称、层、类型、解锁）现在
都没有了。

## 纵向位置是算出来的，不是标出来的

早先每个节点上有个「层」字段，是人工分的组。现在图里只有节点和边，纵向
位置用 kg_levels.sql 算出的**依赖深度**：从根出发的最长路径。按它排就保证
每个节点画在它所有前置的下面。

代价是没有了「文字/音韵/词类」这种主题分组，配色也就跟着去掉了——颜色原本
按类型分，一眼能看出哪片是活用、哪片是助词。现在统一一个色，只用深浅区分
状态（已掌握、可学、未解锁），枢纽节点仍然标下游数量。真需要主题分组的话，
那是展示用的元数据，该另存一个文件，不该塞回图里。

## 布局

层从上到下。同层内先按「主前置」（第一个前置）分簇，簇内把「对照」关系拉到
相邻——たら 和 ば 挨着，学的时候正好对比。

超过 8 个就折行，尽量不拆簇。不折的话节点多的那层会把画布拉成一条细长带子。
折行不改变层级——同层的几个子行仍是同一层，左边的层标签只标一次。

## 为什么自己画而不用图库

一百多个节点、一百多条边，手写布局就够；引 d3 或 mermaid 要么带来构建步骤，
要么没法控制配色和状态标记。SVG 是纯文本，能直接嵌进生成的页面。
"""

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "kg" / "app.db"
QDIR = ROOT / "kg" / "queries"
OUT = ROOT / "kg" / "web" / "kg.svg"

COL = 150          # 同行相邻节点的中心距
ROW = 104          # 子行间距
GAP = 40           # 簇之间的额外间隔
PAD = 56
BOX_W, BOX_H = 118, 40
MAX_PER_ROW = 8    # 一行最多几个节点，超了折行

ACCENT = "#4a7a8c"   # 主色：已掌握实心、可学描边
DIM = "#ddd8d0"      # 未解锁的描边


def load(db=DB) -> list:
    """从库里读节点，带上前置、对照、下游数和依赖深度。"""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        nodes = {r["code"]: {"id": r["code"], "label": r["label"],
                             "prereq": [], "contrast": [], "unlock": 0}
                 for r in con.execute("SELECT code, label FROM node")}
        for r in con.execute("SELECT src, dst FROM prereq ORDER BY src, dst"):
            if r["dst"] in nodes and r["src"] in nodes:
                nodes[r["dst"]]["prereq"].append(r["src"])
                nodes[r["src"]]["unlock"] += 1
        for r in con.execute("SELECT a, b FROM contrast"):
            if r["a"] in nodes and r["b"] in nodes:
                nodes[r["a"]]["contrast"].append(r["b"])
                nodes[r["b"]]["contrast"].append(r["a"])
        # 依赖深度用现成的查询，跟接口那边算的是同一套
        sql = (QDIR / "kg_levels.sql").read_text(encoding="utf-8")
        for r in con.execute(sql):
            if r["code"] in nodes:
                nodes[r["code"]]["depth"] = r["depth"]
    finally:
        con.close()

    # 环上的节点从根走不到，没有 depth。库里本该无环，真有就画在最前面，
    # 不静默丢掉
    for n in nodes.values():
        n.setdefault("depth", 0)
    return list(nodes.values())


def cluster(row: list) -> list:
    """同层节点按主前置分簇，簇内把对照关系排到相邻。"""
    groups = defaultdict(list)
    for n in row:
        groups[n["prereq"][0] if n["prereq"] else "_"].append(n)

    out = []
    for g in groups.values():
        placed, rest = [], list(g)
        while rest:
            cur = rest.pop(0)
            placed.append(cur)
            for c in cur["contrast"]:
                m = next((x for x in rest if x["id"] == c), None)
                if m:
                    rest.remove(m)
                    placed.append(m)
        out.append(placed)
    return out


def wrap(clusters: list, limit: int) -> list:
    """把簇装进若干子行，尽量不拆簇。"""
    lines, cur = [], []
    for c in clusters:
        if cur and sum(len(x) for x in cur) + len(c) > limit:
            lines.append(cur)
            cur = []
        if len(c) > limit:          # 单个簇就超限，独占若干行
            if cur:
                lines.append(cur)
                cur = []
            for i in range(0, len(c), limit):
                lines.append([c[i:i + limit]])
            continue
        cur.append(c)
    if cur:
        lines.append(cur)
    return lines


def layout(nodes: list):
    """算坐标。返回 (坐标表, 每层的子行范围, 画布宽, 画布高)。"""
    layers = defaultdict(list)
    for n in nodes:
        layers[n["depth"]].append(n)

    plan = {L: wrap(cluster(layers[L]), MAX_PER_ROW) for L in layers}

    def width_of(line):
        return sum(len(c) for c in line) * COL + (len(line) - 1) * GAP

    canvas_w = max(width_of(ln) for lines in plan.values() for ln in lines) + PAD * 2

    pos, layer_rows, r = {}, {}, 0
    for L in sorted(plan):
        layer_rows[L] = (r, r + len(plan[L]) - 1)
        for line in plan[L]:
            y = PAD + r * ROW
            x = PAD + (canvas_w - PAD * 2 - width_of(line)) / 2
            for c in line:
                for n in c:
                    pos[n["id"]] = (x + COL / 2, y)
                    x += COL
                x += GAP
            r += 1

    return pos, layer_rows, int(canvas_w), int(PAD * 2 + r * ROW)


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def render(nodes: list, mastered=None) -> str:
    mastered = set(mastered or ())
    pos, layer_rows, W, H = layout(nodes)

    ready = {n["id"] for n in nodes
             if n["id"] not in mastered and all(p in mastered for p in n["prereq"])}

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="-apple-system,\'Hiragino Sans\','
        f'\'Noto Sans CJK SC\',\'Microsoft YaHei\',sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#faf9f7"/>',
    ]

    # 层带：交替浅底，折行的层一眼能看出是同一层
    for L, (r0, r1) in layer_rows.items():
        if L % 2:
            y = PAD + r0 * ROW - BOX_H / 2 - 12
            h = (r1 - r0 + 1) * ROW
            out.append(f'<rect x="0" y="{y:.0f}" width="{W}" height="{h:.0f}" '
                       f'fill="#f3f0eb"/>')

    # 边先画，压在节点下面才不会盖住文字
    out.append('<g fill="none">')
    for n in nodes:
        x2, y2 = pos[n["id"]]
        for p in n["prereq"]:
            if p not in pos:
                continue
            x1, y1 = pos[p]
            y1 += BOX_H / 2
            y2t = y2 - BOX_H / 2
            # 竖直控制点：线从节点底部垂直出发再拐弯。直线连的话跨层的边
            # 会斜着穿过中间那层的节点框。
            mid = (y1 + y2t) / 2
            live = p in mastered
            out.append(
                f'<path d="M{x1:.0f},{y1:.0f} C{x1:.0f},{mid:.0f} '
                f'{x2:.0f},{mid:.0f} {x2:.0f},{y2t:.0f}" '
                f'stroke="{"#b9ad9c" if live else "#e2ddd5"}" '
                f'stroke-width="{1.6 if live else 1}"/>'
            )
    # 对照虚线只画同一子行的：跨行连会穿过别的节点，看着像接错了
    drawn = set()
    for n in nodes:
        for c in n["contrast"]:
            key = tuple(sorted((n["id"], c)))
            if c not in pos or key in drawn:
                continue
            drawn.add(key)
            x1, y1 = pos[n["id"]]
            x2, y2 = pos[c]
            if abs(y1 - y2) > 1:
                continue
            out.append(
                f'<path d="M{x1:.0f},{y1 + BOX_H / 2 + 5:.0f} '
                f'L{x2:.0f},{y2 + BOX_H / 2 + 5:.0f}" '
                f'stroke="#cfc4b4" stroke-width="1" stroke-dasharray="3,3"/>'
            )
    out.append("</g>")

    for L, (r0, _) in layer_rows.items():
        y = PAD + r0 * ROW
        out.append(
            f'<text x="12" y="{y + 5:.0f}" font-size="12" fill="#a89f93">'
            f'第 {L} 步</text>'
        )

    for n in nodes:
        x, y = pos[n["id"]]
        done, can = n["id"] in mastered, n["id"] in ready

        if done:
            fill, stroke, sw, tc, op = ACCENT, ACCENT, 1.5, "#fff", 1
        elif can:
            fill, stroke, sw, tc, op = "#fff", ACCENT, 2.2, ACCENT, 1
        else:
            fill, stroke, sw, tc, op = "#fff", DIM, 1, "#b5aca1", 0.72

        rx, ry = x - BOX_W / 2, y - BOX_H / 2
        out.append(
            f'<g opacity="{op}">'
            f'<rect x="{rx:.0f}" y="{ry:.0f}" width="{BOX_W}" height="{BOX_H}" '
            f'rx="7" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )
        # 长名字缩字号而不折行：折了行高不齐，整排看着毛躁
        name = n["label"]
        size = 13 if len(name) <= 7 else (11 if len(name) <= 10 else 9.5)
        out.append(
            f'<text x="{x:.0f}" y="{y + 4:.0f}" text-anchor="middle" '
            f'font-size="{size}" fill="{tc}">{esc(name)}</text></g>'
        )
        # 枢纽角标：下游 5 个以上标出数量，瓶颈一眼可见
        if n["unlock"] >= 5:
            cx, cy = x + BOX_W / 2 - 3, ry + 3
            out.append(
                f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="9" fill="{ACCENT}"/>'
                f'<text x="{cx:.0f}" y="{cy + 4:.0f}" text-anchor="middle" '
                f'font-size="10" fill="#fff">{n["unlock"]}</text>'
            )

    deepest = max(n["depth"] for n in nodes) + 1
    out.append(
        f'<text x="{PAD}" y="{H - 20}" font-size="11" fill="#8a827a">'
        f'实心=已掌握　粗描边=可学　淡出=未解锁　角标=下游节点数　'
        f'虚线=对照关系　共 {len(nodes)} 个节点，最长链 {deepest} 步</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def arg(name: str, default: str) -> str:
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main() -> int:
    db = Path(arg("--db", str(DB)))
    out = Path(arg("--out", str(OUT)))
    if not db.is_file():
        print(f"没有这个库：{db}")
        return 1

    mastered = {x.strip() for x in arg("--mastered", "").split(",") if x.strip()}
    nodes = load(db)
    if not nodes:
        print(f"{db} 里一个知识点都没有——先导入（py -m kg import）")
        return 1

    svg = render(nodes, mastered)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"已写入 {out}（{len(svg):,} 字节，{len(nodes)} 个节点）")

    ready = [n["label"] for n in nodes
             if n["id"] not in mastered and all(p in mastered for p in n["prereq"])]
    print(f"已掌握 {len(mastered)} 个，现在可学：{'、'.join(ready[:10])}"
          + ("…" if len(ready) > 10 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
