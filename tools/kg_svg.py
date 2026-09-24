# -*- coding: utf-8 -*-
"""知识图谱可视化：把 kg.py 的节点表画成 SVG。

两种跑法都行：

    py -m tools.kg_svg      从 mcp/ 目录，作为包运行
    py kg_svg.py            直接跑这个文件

    加 --mastered a,b,c 标出已掌握状态

布局思路：

    层从上到下。同层内先按「主前置」（第一个前置）分簇，簇内把「对照」
    关系拉到相邻——たら 和 ば 挨着，学的时候正好对比。

    超过 8 个就折行，尽量不拆簇。不折的话层5 那 23 个节点会把画布拉到
    3800 宽，别的层才 1000 出头，成了一条细长带子。折完 1550×1250。

    折行不改变层级——同层的几个子行仍是同一层，只是排不下才换行，
    左边的层标签也只标一次。

为什么自己画而不用图库：
    69 个节点、86 条边，手写布局就够；引 d3 或 mermaid 要么带来构建步骤，
    要么没法控制配色和状态标记。SVG 是纯文本，能直接嵌进生成的页面。
"""

import sys
from collections import defaultdict
from pathlib import Path

# 包内运行走相对导入，直接跑脚本时退回同目录导入
try:
    from .kg import build, depth_of, out_dir
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kg import build, depth_of, out_dir

COL = 150          # 同行相邻节点的中心距
ROW = 104          # 子行间距
GAP = 40           # 簇之间的额外间隔
PAD = 56
BOX_W, BOX_H = 118, 40
MAX_PER_ROW = 8    # 一行最多几个节点，超了折行

# 按类型配色：层已经由纵向位置表达了，颜色再重复一遍是浪费，
# 用来区分类型更有信息量——一眼看出哪片是活用、哪片是助词。
COLORS = {
    "文字": "#7c6a9c", "音韵": "#5b7fa6", "词类": "#4a8a72",
    "活用": "#b07d48", "助词": "#a35c6d", "句型": "#6b8e4e",
    "待遇": "#8a6a4a", "语感": "#6a6a8a",
}

LAYER_NAME = {0: "文字", 1: "音韵", 2: "词类", 3: "基本活用", 4: "助词",
              5: "句型", 6: "高级活用", 7: "待遇表现", 8: "综合"}


def cluster(row: list[dict]) -> list[list[dict]]:
    """同层节点按主前置分簇，簇内把对照关系排到相邻。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for n in row:
        groups[n["前置"][0] if n["前置"] else "_"].append(n)

    out = []
    for g in groups.values():
        placed, rest = [], list(g)
        while rest:
            cur = rest.pop(0)
            placed.append(cur)
            for c in cur["对照"]:
                m = next((x for x in rest if x["id"] == c), None)
                if m:
                    rest.remove(m)
                    placed.append(m)
        out.append(placed)
    return out


def wrap(clusters: list[list[dict]], limit: int) -> list[list[list[dict]]]:
    """把簇装进若干子行，尽量不拆簇。"""
    lines: list[list[list[dict]]] = []
    cur: list[list[dict]] = []
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


def layout(nodes: list[dict]):
    """算坐标。返回 (坐标表, 每层的子行范围, 画布宽, 画布高)。"""
    layers: dict[int, list[dict]] = defaultdict(list)
    for n in nodes:
        layers[n["层"]].append(n)

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


def render(nodes: list[dict], mastered: set[str] | None = None) -> str:
    mastered = mastered or set()
    pos, layer_rows, W, H = layout(nodes)
    depth = depth_of(nodes)

    ready = {n["id"] for n in nodes
             if n["id"] not in mastered and all(p in mastered for p in n["前置"])}

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
        for p in n["前置"]:
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
    for n in nodes:
        for c in n["对照"]:
            if c not in pos or c <= n["id"]:
                continue
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
            f'{L}　{esc(LAYER_NAME.get(L, ""))}</text>'
        )

    for n in nodes:
        x, y = pos[n["id"]]
        color = COLORS.get(n["类型"], "#888")
        done, can = n["id"] in mastered, n["id"] in ready

        if done:
            fill, stroke, sw, tc, op = color, color, 1.5, "#fff", 1
        elif can:
            fill, stroke, sw, tc, op = "#fff", color, 2.2, color, 1
        else:
            fill, stroke, sw, tc, op = "#fff", "#ddd8d0", 1, "#b5aca1", 0.72

        rx, ry = x - BOX_W / 2, y - BOX_H / 2
        out.append(
            f'<g opacity="{op}">'
            f'<rect x="{rx:.0f}" y="{ry:.0f}" width="{BOX_W}" height="{BOX_H}" '
            f'rx="7" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )
        # 长名字缩字号而不折行：折了行高不齐，整排看着毛躁
        name = n["名称"]
        size = 13 if len(name) <= 7 else (11 if len(name) <= 10 else 9.5)
        out.append(
            f'<text x="{x:.0f}" y="{y + 4:.0f}" text-anchor="middle" '
            f'font-size="{size}" fill="{tc}">{esc(name)}</text></g>'
        )
        # 枢纽角标：下游 5 个以上标出数量，瓶颈一眼可见
        if len(n["解锁"]) >= 5:
            cx, cy = x + BOX_W / 2 - 3, ry + 3
            out.append(
                f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="9" fill="{color}"/>'
                f'<text x="{cx:.0f}" y="{cy + 4:.0f}" text-anchor="middle" '
                f'font-size="10" fill="#fff">{len(n["解锁"])}</text>'
            )

    out.append(
        f'<text x="{PAD}" y="{H - 20}" font-size="11" fill="#8a827a">'
        f'实心=已掌握　粗描边=可学　淡出=未解锁　角标=下游节点数　'
        f'虚线=对照关系　共 {len(nodes)} 个节点，最长链 '
        f'{max(depth.values()) + 1} 步</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    nodes = build()
    mastered = set()
    if "--mastered" in sys.argv:
        i = sys.argv.index("--mastered")
        if i + 1 < len(sys.argv):
            mastered = {x.strip() for x in sys.argv[i + 1].split(",") if x.strip()}

    svg = render(nodes, mastered)
    out = out_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "kg.svg").write_text(svg, encoding="utf-8")
    print(f"已写入 {out / 'kg.svg'}（{len(svg):,} 字节）")

    ready = [n["名称"] for n in nodes
             if n["id"] not in mastered and all(p in mastered for p in n["前置"])]
    print(f"已掌握 {len(mastered)} 个，现在可学：{'、'.join(ready)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
