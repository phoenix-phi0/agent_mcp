# -*- coding: utf-8 -*-
"""知识图谱一键生成：校验、SVG、可交互网页。

两种跑法都行：

    py -m tools.kg_build        从 mcp/ 目录，作为包运行
    py kg_build.py              直接跑这个文件

    --mastered a,b,c        手动指定已掌握节点
    --from-progress φ-0     从学习者进度里读
    --png                   顺便转 PNG（需要 cairosvg）

产物都在 workspace/japanese/content/：

    kg.json    节点表，给程序读
    kg.svg     静态图，能嵌页面或贴文档
    kg.html    可交互，点节点高亮整条依赖链
    kg.png     可选，分享用

为什么合成一个入口：三个产物同源，分开跑容易出现 json 是新的、svg 是旧的。
改了 kg.py 的节点表之后跑这一个就全同步——跟 app2 那边 .ui 改完必须重跑
build.py 是同一个道理，那次就因为产物没更新绕了好几轮。
"""

import json
import sys
from pathlib import Path

# 包内运行走相对导入，直接跑脚本时退回同目录导入
try:
    from .kg import build, check, out_dir, summary, unlocked
    from .kg_svg import COLORS, render
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kg import build, check, out_dir, summary, unlocked
    from kg_svg import COLORS, render


def read_progress(learner: str) -> set[str]:
    """从学习者进度里读已掌握的节点。

    约定 progress.json 里有 kg_mastered 字段，是节点 id 列表。
    没有这个字段就返回空集——图谱是新加的，老档案里不会有。
    """
    p = out_dir().parent / "memory" / learner / "progress.json"
    if not p.is_file():
        print(f"找不到 {p}，当作没有掌握记录")
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"进度文件读不了（{e}），当作没有掌握记录")
        return set()
    return set(data.get("kg_mastered") or [])


def make_html(nodes: list[dict], mastered: set[str]) -> str:
    """可交互版：点节点高亮整条依赖链。

    整张图是 SVG，交互靠外层一点 JS。没引任何库——高亮无非是加减 class，
    用框架反而要多一个构建步骤。
    """
    svg = render(nodes, mastered)
    # 给节点文字打上 id，JS 才能定位；渲染时不加是为了让 SVG 本身保持干净
    for n in nodes:
        svg = svg.replace(f'>{n["名称"]}</text>',
                          f' data-id="{n["id"]}">{n["名称"]}</text>', 1)

    data = json.dumps(
        {n["id"]: {"名称": n["名称"], "类型": n["类型"], "层": n["层"],
                   "前置": n["前置"], "解锁": n["解锁"], "对照": n["对照"],
                   "考点": n["掌握判据"]["考点"]}
         for n in nodes}, ensure_ascii=False)

    legend = "".join(f'<span class="tag"><i style="background:{c}"></i>{k}</span>'
                     for k, c in COLORS.items())

    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>日语学习知识图谱</title>
<style>
  body {{ margin:0; background:#faf9f7; color:#2b2825;
    font:14px/1.7 -apple-system,"Hiragino Sans","Noto Sans CJK SC",
         "Microsoft YaHei",sans-serif; }}
  header {{ padding:14px 20px; border-bottom:1px solid #e6e2dc; background:#fff;
    display:flex; align-items:center; gap:16px; flex-wrap:wrap;
    position:sticky; top:0; z-index:3; }}
  h1 {{ font-size:15px; margin:0; font-weight:600; }}
  .tag {{ font-size:12px; color:#8a827a; display:inline-flex;
    align-items:center; gap:5px; }}
  .tag i {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
  .sp {{ flex:1; }}
  #wrap {{ padding:20px; overflow:auto; }}
  svg {{ max-width:100%; height:auto; }}
  /* 高亮时把无关节点压暗，而不是把相关的调亮——
     后者在已经有三种状态配色的图上会打架 */
  svg.focus g[data-node] {{ opacity:.12 !important; }}
  svg.focus g[data-node].on {{ opacity:1 !important; }}
  svg.focus path {{ opacity:.06; }}
  #panel {{ position:fixed; right:20px; bottom:20px; width:280px;
    background:#fff; border:1px solid #e6e2dc; border-radius:10px;
    padding:14px 16px; font-size:13px; display:none;
    box-shadow:0 4px 16px rgba(0,0,0,.06); }}
  #panel h2 {{ font-size:14px; margin:0 0 8px; }}
  #panel dl {{ margin:0; }}
  #panel dt {{ color:#8a827a; font-size:12px; margin-top:8px; }}
  #panel dd {{ margin:2px 0 0; }}
  .hint {{ color:#8a827a; font-size:12px; }}
</style></head><body>

<header>
  <h1>日语学习知识图谱</h1>
  {legend}
  <span class="sp"></span>
  <span class="hint">点节点看依赖链，点空白取消，Esc 也行</span>
</header>

<div id="wrap">{svg}</div>
<div id="panel"></div>

<script>
const DATA = {data};
const svg = document.querySelector("svg");
const panel = document.getElementById("panel");

// 渲染时只在 text 上留了 data-id，高亮要作用于整个框，所以往上找一层
document.querySelectorAll("text[data-id]").forEach(t => {{
  const g = t.closest("g");
  if (g) {{ g.dataset.node = t.dataset.id; g.style.cursor = "pointer"; }}
}});

// 整条依赖链：所有祖先 + 所有后代。只看直接邻居的话，点了て形只能看到
// 一层，看不出它到底撑起了多大一片。
function chain(id) {{
  const up = new Set(), down = new Set();
  (function anc(x) {{
    for (const p of DATA[x].前置) if (!up.has(p)) {{ up.add(p); anc(p); }}
  }})(id);
  (function desc(x) {{
    for (const u of DATA[x].解锁) if (!down.has(u)) {{ down.add(u); desc(u); }}
  }})(id);
  return new Set([id, ...up, ...down]);
}}

function show(id) {{
  const set = chain(id);
  svg.classList.add("focus");
  document.querySelectorAll("g[data-node]").forEach(g => {{
    g.classList.toggle("on", set.has(g.dataset.node));
  }});
  const d = DATA[id];
  const list = ids => ids.length ? ids.map(i => DATA[i].名称).join("、") : "无";
  panel.innerHTML = `<h2>${{d.名称}}</h2><dl>
    <dt>类型</dt><dd>${{d.类型}}　层 ${{d.层}}</dd>
    <dt>前置</dt><dd>${{list(d.前置)}}</dd>
    <dt>解锁</dt><dd>${{list(d.解锁)}}</dd>
    <dt>对照</dt><dd>${{list(d.对照)}}</dd>
    <dt>掌握判据</dt><dd>考点「${{d.考点}}」</dd>
    <dt>整条链</dt><dd>${{set.size}} 个节点</dd></dl>`;
  panel.style.display = "block";
}}

function clear() {{
  svg.classList.remove("focus");
  document.querySelectorAll("g[data-node].on")
    .forEach(g => g.classList.remove("on"));
  panel.style.display = "none";
}}

svg.addEventListener("click", ev => {{
  const g = ev.target.closest("g[data-node]");
  if (g) show(g.dataset.node); else clear();
}});
document.addEventListener("keydown", ev => {{
  if (ev.key === "Escape") clear();
}});
</script>
</body></html>"""


def main() -> int:
    args = sys.argv[1:]
    nodes = build()

    errs = check(nodes)
    print(summary(nodes))
    print()
    if errs:
        print(f"校验发现 {len(errs)} 个问题，先修好再生成：")
        for e in errs[:20]:
            print("  ", e)
        return 1
    print("校验通过")

    mastered: set[str] = set()
    if "--mastered" in args:
        i = args.index("--mastered")
        if i + 1 < len(args):
            mastered = {x.strip() for x in args[i + 1].split(",") if x.strip()}
    elif "--from-progress" in args:
        i = args.index("--from-progress")
        learner = args[i + 1] if i + 1 < len(args) else "φ-0"
        mastered = read_progress(learner)
        print(f"从 {learner} 的进度里读到 {len(mastered)} 个已掌握节点")

    # 进度里有图谱中不存在的节点，说明两边脱节了，提醒一下再忽略
    unknown = mastered - {n["id"] for n in nodes}
    if unknown:
        print(f"进度里有图谱中不存在的节点，已忽略：{sorted(unknown)}")
        mastered -= unknown

    out = out_dir()
    out.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(nodes, ensure_ascii=False, indent=2)
    (out / "kg.json").write_text(payload, encoding="utf-8")
    svg = render(nodes, mastered)
    (out / "kg.svg").write_text(svg, encoding="utf-8")
    html = make_html(nodes, mastered)
    (out / "kg.html").write_text(html, encoding="utf-8")

    print(f"\n输出目录 {out}")
    print(f"  kg.json　{len(payload):>8,} 字节")
    print(f"  kg.svg 　{len(svg):>8,} 字节")
    print(f"  kg.html　{len(html):>8,} 字节")

    if "--png" in args:
        try:
            import cairosvg
            cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                             write_to=str(out / "kg.png"), scale=2)
            print("  kg.png 　已生成（2 倍分辨率）")
        except ImportError:
            print("  kg.png 　跳过：pip install cairosvg 之后再试")

    can = unlocked(nodes, mastered)
    by_id = {n["id"]: n for n in nodes}
    print(f"\n已掌握 {len(mastered)} 个，现在可学 {len(can)} 个：")
    print("  " + "、".join(by_id[i]["名称"] for i in can))
    print(f"\n打开 {out / 'kg.html'} 看可交互版")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
