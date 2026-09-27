import subprocess, os, re, sys, json, random
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
FILES = ['tools/ui.py', 'templates/frontend/graph.j2', 'templates/frontend/app.js.j2',
         'templates/frontend/style.css.j2']

GRAPH_J2 = r'''<% from "widgets.j2" import 当, 尺寸 with context %>
{#- 「节点图」：Vue Flow 画（能缩放、平移、点选），dagre 排，游戏科技树的样子。
    只有这一种排布。

      层      给 dagre 的每条边设最短长度 = 两端「最长前置链步数」之差，dagre 排出
              来的层就正好等于步数，「第 N 步」是真的第 N 步
      卡片    180×64：状态图标 + 名字 + 一行说明，学习中的带进度条，右上角角标。
              说明行：后端给 sub 就显示它；不给就按状态——已掌握 / 可学 /
              学习中 N%（给了 progress）/ 需要 XX（锁定时列出没掌握的前置）
      间距    nodesep 40、ranksep 64；层距 = 卡片高 + ranksep = 128（横向 244）
      同层    顺序交给 dagre 减少交叉。dagre 不会折行：同层很多时会往横向铺开
      层带    隔层浅底、「第 N 步」，做成铺在最底下的 kglayer 节点，半透明、不接鼠标
      连线    smoothstep 直角折线；前置已掌握的线着主色，没掌握的淡灰
      对照    同一层的才连，虚线
      方向    默认从上到下；「方向 横向」从左往右，层带竖过来

    数据（从「绑」指定的共享路径读）：{nodes, edges}，或直接是节点数组
      nodes: [{ id, label, state?, sub?, progress?, icon?, badge?, x?, y?, class?, style?, ...自定义 }]
      edges: [{ from, to, kind? }]    kind 为「对照」画虚线、不参与布局
      layerNames: { 0: "文字", ... }  可选，给层起名
    state:    done/open/locked（或 掌握/可学/锁定）→ 实心带勾 / 亮边 / 灰色带锁
    progress: 0~1，给了就画进度条
    icon:     一个字或 emoji，替换状态图标
    x/y:      全部节点都给了就按给的放（左上角），不跑 dagre，也不画层带

    点节点：原样节点对象写进「选中」路径，有「点开」就弹浮层；点空白处清掉。
    :key 取节点数和边数：数据换一批时让 VueFlow 重建，fit-view-on-init 才会对
    新数据重新取景。 -#}
<%- macro 节点图(n) -%>
<%- set path = n.bind or n.name -%>
<%- set dir = n.direction or "纵向" -%>
<div class="graph-wrap"<%= 当(n) %><%= 尺寸(n) %>>
<VueFlow
  :key="graphOf('<%= path %>', '<%= dir %>').nodes.length + ':' + graphOf('<%= path %>', '<%= dir %>').edges.length"
  :nodes="graphOf('<%= path %>', '<%= dir %>').nodes"
  :edges="graphOf('<%= path %>', '<%= dir %>').edges"
  :nodes-draggable="false"
  :nodes-connectable="false"
  :elements-selectable="true"
  :max-zoom="1.5"
  fit-view-on-init
  @node-click="onGraphNode('<%= n.selects %>', $event, '<%= n.popup %>')"
  @pane-click="onGraphNode('<%= n.selects %>', null, '')">
<template #node-kglayer="p">
<div class="kg-layer" :class="{ shaded: p.data.shaded }"><span class="kg-layer-t">{{ p.data.text }}</span></div>
</template>
<template #node-kg="p">
<div class="kg-node">
<Handle id="in" type="target" position="top" />
<Handle id="pt" type="target" position="left" />
<Handle id="ps" type="source" position="left" />
<div class="kg-head"><span class="kg-ico" v-html="p.data.__view.icon"></span><span class="kg-label">{{ p.label }}</span></div>
<div v-if="p.data.__view.sub" class="kg-sub">{{ p.data.__view.sub }}</div>
<div v-if="p.data.__view.bar != null" class="kg-bar"><i :style="{ width: p.data.__view.bar + '%' }"></i></div>
<span v-if="p.data.badge != null && p.data.badge !== ''" class="kg-badge">{{ p.data.badge }}</span>
<Handle id="qt" type="target" position="right" />
<Handle id="qs" type="source" position="right" />
<Handle id="out" type="source" position="bottom" />
</div>
</template>
</VueFlow>
</div>
<% if n.has("图例") %>
<p class="kg-legend"<%= 当(n) %>>{{ graphOf('<%= path %>', '<%= dir %>').legend }}</p>
<% endif %>
<%- endmacro -%>
'''

RT = r'''<% if has_graphs %>
    // 节点图：Vue Flow 画，dagre 排，游戏科技树的样子。只有这一种排布。
    //   层   = 最长前置链步数。给每条边设 minlen = 两端步数之差，dagre 的网络单纯形
    //          会让每条边都取到最短长度（那样总长最小），于是层恰好等于步数
    //   卡片 = 180×64；层距 = 卡片高 + ranksep = 128（横向 244）
    //   同层 = dagre 排，减少交叉；不折行
    function _graphGet(obj, path) { return path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj); }
    function _graphPut(obj, path, value) { const parts = path.split('.'); let box = obj; for (const k of parts.slice(0, -1)) box = box[k] || (box[k] = {}); box[parts[parts.length - 1]] = value; }
    const _KG = { BW: 180, BH: 64, NODESEP: 40, RANKSEP: 64, PAD: 56 };
    // 状态图标：内联 SVG，不依赖图标字体
    const _kgIcon = {
      'kg-done': '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      'kg-open': '<svg viewBox="0 0 16 16" width="13" height="13"><path d="M9 1.5L3.5 9H8l-1 5.5L12.5 7H8z" fill="currentColor"/></svg>',
      'kg-locked': '<svg viewBox="0 0 16 16" width="13" height="13"><rect x="3" y="7" width="10" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>',
    };
    const _kgEsc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const _kgState = { done: 'kg-done', open: 'kg-open', locked: 'kg-locked', '掌握': 'kg-done', '可学': 'kg-open', '锁定': 'kg-locked' };
    // 按路径各缓存一份：外面的大图和浮层里的小图同时在页面上，不能互相挤掉
    const _graphCache = new Map();
    function graphOf(path, dir) {
      const raw0 = _graphGet(shared.value, path);
      // 也收纯数组：没有连线的一组知识点（比如详情浮层里的 sel.points）直接给数组，排成一层
      const raw = Array.isArray(raw0) ? { nodes: raw0 } : (raw0 || {});
      const key = (dir || '') + '|' + JSON.stringify(raw);
      const hit = _graphCache.get(path);
      if (hit && hit.key === key) return hit.out;
      const { BW, BH, NODESEP, RANKSEP, PAD } = _KG;
      const lr = dir === '横向';
      // 没给 id 的用 label 顶上：手写的子知识点通常只有 label
      const src = (raw.nodes || []).map((n, i) => n.id != null ? n : Object.assign({}, n, { id: n.label != null ? n.label : 'n' + i }));
      const K = n => String(n.id);
      const byId = {}, pre = {}, con = {};
      src.forEach(n => { byId[K(n)] = n; pre[K(n)] = []; con[K(n)] = []; });
      (raw.edges || []).forEach(e => {
        const a = String(e.from), b = String(e.to);
        if (!(a in pre) || !(b in pre)) return;
        if (e.kind === '对照') { con[a].push(b); con[b].push(a); }   // 对照不参与布局
        else if (e.layout !== false) pre[b].push(a);
      });
      // 步数：最长前置链。环在导入时已被拒掉，seen 只防死循环
      const depth = {};
      const dep = (k, seen) => {
        if (k in depth) return depth[k];
        if (seen.has(k)) return 0;
        seen.add(k);
        let d = 0;
        for (const p of pre[k]) d = Math.max(d, dep(p, seen) + 1);
        seen.delete(k);
        return (depth[k] = d);
      };
      src.forEach(n => dep(K(n), new Set()));

      const pos = {};
      const given = src.length > 0 && src.every(n => n.x != null && n.y != null);
      if (given) {
        src.forEach(n => { pos[K(n)] = { x: n.x + BW / 2, y: n.y + BH / 2 }; });
      } else if (src.length && typeof dagre !== 'undefined') {
        const g = new dagre.graphlib.Graph();
        g.setDefaultEdgeLabel(() => ({}));
        g.setGraph({ rankdir: lr ? 'LR' : 'TB', nodesep: NODESEP, ranksep: RANKSEP });
        src.forEach(n => g.setNode(K(n), { width: BW, height: BH }));
        src.forEach(n => pre[K(n)].forEach(p => g.setEdge(p, K(n), { minlen: Math.max(1, depth[K(n)] - depth[p]) })));
        // 虚拟根连到所有第 0 步的节点：不连的话，互不相连的几块图 dagre 会各自上下
        // 平移（平移不改变总边长），第 0 步就不在同一层了
        const ROOT = '__kg_root__';
        g.setNode(ROOT, { width: 1, height: 1 });
        src.forEach(n => { if (depth[K(n)] === 0) g.setEdge(ROOT, K(n), { minlen: 1, weight: 1 }); });
        dagre.layout(g);
        src.forEach(n => { const v = g.node(K(n)); if (v) pos[K(n)] = { x: v.x, y: v.y }; });
      } else {
        // dagre 没加载上（断网又没配本地文件）：退回按步数分层、同层依次排开
        const seenAt = {};
        src.forEach(n => { const d = depth[K(n)], i = (seenAt[d] = (seenAt[d] || 0) + 1) - 1;
          pos[K(n)] = lr ? { x: d * (BW + RANKSEP), y: i * (BH + NODESEP) } : { x: i * (BW + NODESEP), y: d * (BH + RANKSEP) }; });
      }

      // 层带和「第 N 步」：按步数分组。纵向时是横条，横向时是竖条。只有一层（比如详情
      // 里并列的一排子知识点）或节点自带坐标时不画
      const nodes = [];
      const steps = [...new Set(src.map(n => depth[K(n)]))].sort((a, b) => a - b);
      if (!given && steps.length > 1) {
        const all = src.map(n => pos[K(n)]).filter(Boolean);
        const minX = Math.min(...all.map(c => c.x)) - BW / 2 - PAD, maxX = Math.max(...all.map(c => c.x)) + BW / 2 + PAD;
        const minY = Math.min(...all.map(c => c.y)) - BH / 2 - PAD, maxY = Math.max(...all.map(c => c.y)) + BH / 2 + PAD;
        const names = raw.layerNames || {};
        steps.forEach(L => {
          const at = src.filter(n => depth[K(n)] === L).map(n => pos[K(n)]).filter(Boolean);
          if (!at.length) return;
          const text = names[L] != null ? L + '\u3000' + names[L] : '第 ' + L + ' 步';
          const box = lr
            ? { x: Math.min(...at.map(c => c.x)) - BW / 2 - RANKSEP / 2, y: minY, w: BW + RANKSEP, h: maxY - minY }
            : { x: minX, y: Math.min(...at.map(c => c.y)) - BH / 2 - RANKSEP / 2, w: maxX - minX, h: BH + RANKSEP };
          // 放在最前面、zIndex -1：先画的在下面，连线和卡片都盖在它上面
          nodes.push({
            id: '__layer' + L, type: 'kglayer', position: { x: box.x, y: box.y },
            selectable: false, draggable: false, focusable: false, connectable: false, zIndex: -1,
            style: { width: box.w + 'px', height: box.h + 'px' }, data: { text, shaded: L % 2 === 1 },
          });
        });
      }
      // 卡片上显示什么：后端给了 sub 就用；给了 progress 显示「学习中 N%」和进度条；
      // 否则按状态——已掌握 / 可学 / 需要 XX（锁定时列出还没掌握的前置，最多两个）
      const view = n => {
        const st = _kgState[n.state] || '';
        const bar = typeof n.progress === 'number' ? Math.max(0, Math.min(100, Math.round(n.progress * 100))) : null;
        let sub = n.sub != null ? String(n.sub) : '';
        if (n.sub == null) {
          if (bar != null) sub = '学习中 ' + bar + '%';
          else if (st === 'kg-done') sub = '已掌握';
          else if (st === 'kg-open') sub = '可学';
          else if (st === 'kg-locked') {
            const miss = pre[K(n)].filter(p => _kgState[(byId[p] || {}).state] !== 'kg-done')
              .map(p => byId[p] && byId[p].label != null ? String(byId[p].label) : p);
            sub = miss.length ? '需要 ' + miss.slice(0, 2).join('、') + (miss.length > 2 ? ' 等' : '') : '未解锁';
          }
        }
        const icon = n.icon != null ? _kgEsc(n.icon) : (_kgIcon[st] || '');
        return { icon, sub, bar };
      };
      src.forEach(n => {
        const c = pos[K(n)];
        if (!c) return;
        nodes.push({
          id: K(n), type: 'kg', position: { x: c.x - BW / 2, y: c.y - BH / 2 },
          label: n.label != null ? String(n.label) : K(n),
          class: [_kgState[n.state], n.class].filter(Boolean).join(' '),
          style: Object.assign({ width: BW + 'px', height: BH + 'px' }, n.style || {}),
          // 卡片显示用的东西放 __view，点中时剥掉，写进「选中」的仍是后端原样节点
          draggable: false, data: Object.assign({}, n, { __view: view(n) }),
        });
      });
      const edges = [];
      src.forEach(n => pre[K(n)].forEach(p => {
        if (!pos[p] || !pos[K(n)]) return;
        edges.push({
          // 直角折线。纵向下出上进，横向右出左进；前置已掌握的线着主色，没掌握的淡灰
          id: 'p:' + p + '>' + K(n), source: p, target: K(n), type: 'smoothstep',
          pathOptions: { borderRadius: 8 },
          sourceHandle: lr ? 'qs' : 'out', targetHandle: lr ? 'pt' : 'in',
          class: _kgState[(byId[p] || {}).state] === 'kg-done' ? 'kg-live' : 'kg-dim',
        });
      }));
      // 对照只连同一层的：跨层连会穿过别的卡片，看着像接错了。纵向从侧面连，横向从上下连
      src.forEach(n => con[K(n)].forEach(c => {
        if (c <= K(n) || depth[c] !== depth[K(n)]) return;
        const a = pos[K(n)], b = pos[c];
        if (!a || !b) return;
        let s = K(n), t = c, sh, th;
        if (lr) { if (b.y < a.y) { s = c; t = K(n); } sh = 'out'; th = 'in'; }
        else { const far = b.x >= a.x; sh = far ? 'qs' : 'ps'; th = far ? 'pt' : 'qt'; }
        edges.push({ id: 'c:' + K(n) + '~' + c, source: s, target: t, type: 'straight', class: 'kg-contrast', sourceHandle: sh, targetHandle: th });
      }));
      const longest = src.length ? Math.max(...src.map(n => depth[K(n)])) + 1 : 0;
      const legend = '实心带勾=已掌握\u3000亮边=可学\u3000灰色带锁=未解锁\u3000角标=下游节点数\u3000虚线=对照关系\u3000共 '
        + src.length + ' 个节点，最长链 ' + longest + ' 步';
      const out = { nodes, edges, legend };
      _graphCache.set(path, { key, out });
      return out;
    }
    // 点节点：原样节点对象写进「选中」路径；点空白清掉。之后用「当 shared.sel」
    // 控制显隐、「显示 sel.label」展示内容，都是现成词汇。层带节点不算。
    function onGraphNode(path, ev, popup) {
      if (ev && ev.node && ev.node.type === 'kglayer') return;
      let d = ev && ev.node ? ev.node.data : null;
      if (d && d.__view) { d = Object.assign({}, d); delete d.__view; }
      if (path) _graphPut(shared.value, path, d);
<% if has_overlays %>
      // 「点开 浮层」：点中节点就直接弹详情。点空白处（ev 为 null）不弹。
      if (popup && ev && ev.node) openOverlay.value = popup;
<% endif %>
    }
<% endif %>'''

CSS = '''

/* 节点图（科技树）：底色、层带、「第 N 步」、图例 */
.graph-wrap { background:#faf9f7; }
.graph-wrap .vue-flow__node-kglayer { padding:0; border:0; background:transparent; pointer-events:none !important; }
.kg-layer { width:100%; height:100%; position:relative; }
.kg-layer.shaded { background:rgba(214,203,186,.28); }
.kg-layer-t { position:absolute; left:12px; top:50%; transform:translateY(-50%); font-size:12px; color:#a89f93; white-space:nowrap; }
.kg-legend { font-size:11px; color:#8a827a; margin:6px 0 0 8px; }
/* 科技树卡片：状态图标 + 名字 + 说明行 + 进度条。写在最后，覆盖前面小方块的样式 */
.kg-node {
  display:flex; flex-direction:column; justify-content:center; align-items:stretch; gap:4px;
  padding:8px 12px; border-radius:10px; text-align:left; background:#fff; border:1px solid #ddd8d0;
}
.kg-head { display:flex; align-items:center; gap:6px; min-width:0; font-size:13px; font-weight:600; color:#2b2825; }
.kg-head .kg-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.kg-ico { flex:none; width:16px; height:16px; display:inline-flex; align-items:center; justify-content:center; font-size:14px; line-height:1; }
.kg-ico:empty { display:none; }
.kg-sub { font-size:11px; color:#8a827a; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.kg-bar { height:4px; border-radius:2px; background:#ece7df; overflow:hidden; }
.kg-bar > i { display:block; height:100%; background:#4a7a8c; }
.vue-flow__node.kg-done .kg-node { background:#4a7a8c; border-color:#4a7a8c; }
.vue-flow__node.kg-done .kg-head { color:#fff; }
.vue-flow__node.kg-done .kg-sub { color:rgba(255,255,255,.8); }
.vue-flow__node.kg-done .kg-bar { background:rgba(255,255,255,.3); }
.vue-flow__node.kg-done .kg-bar > i { background:#fff; }
.vue-flow__node.kg-open .kg-node { border:2px solid #4a7a8c; }
.vue-flow__node.kg-open .kg-head { color:#2f5563; }
.vue-flow__node.kg-open .kg-ico { color:#4a7a8c; }
.vue-flow__node.kg-locked { opacity:1; }
.vue-flow__node.kg-locked .kg-node { background:#f5f2ed; border-color:#e6e0d6; }
.vue-flow__node.kg-locked .kg-head { color:#a89f93; }
.vue-flow__node.kg-locked .kg-sub { color:#b5aca1; }
.vue-flow__node.selected .kg-node { box-shadow:0 0 0 3px rgba(74,122,140,.3); }
/* 直角折线：已解锁的着主色，没解锁的淡灰 */
.graph-wrap .vue-flow__edge.kg-live .vue-flow__edge-path { stroke:#4a7a8c; stroke-width:2; }
.graph-wrap .vue-flow__edge.kg-dim .vue-flow__edge-path { stroke:#d6cfc4; stroke-width:1.5; }
'''


def git(*a):
    r = subprocess.run(['git', *a], cwd=P, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def abort(msg):
    git('checkout', 'HEAD', '--', *FILES)
    raise SystemExit('失败，已恢复到 HEAD：' + msg)


def main():
    print('HEAD:', git('log', '--oneline', '-1')[1], 'pid=%d' % os.getpid())
    rc, st = git('status', '--porcelain', '--', *FILES)
    if st:
        raise SystemExit('这几个文件有未提交改动，不动：\n' + st)

    # ui.py：「图例」旗标
    p = P + '/tools/ui.py'
    L = open(p, encoding='utf-8').read().split('\n')
    if not any('FLAG_MODIFIERS | {"图例"}' in l for l in L):
        i = [k for k, l in enumerate(L) if l.startswith('SCREEN_ROLES =')]
        if len(i) != 1:
            abort('SCREEN_ROLES 命中 %d' % len(i))
        L[i[0]:i[0]] = ['# 节点图「图例」：图下面那行「实心带勾=已掌握　亮边=可学……」。浮层里的小图用不着。',
                        'FLAG_MODIFIERS = FLAG_MODIFIERS | {"图例"}', '']
        open(p, 'w', encoding='utf-8').write('\n'.join(L))
    print('ui: 图例旗标')

    # graph.j2：整份重写（这个文件只放节点图）
    open(T + '/graph.j2', 'w', encoding='utf-8').write(GRAPH_J2)
    print('graph.j2: 科技树 + 层带 + 图例')

    # app.js.j2：替换节点图那一段
    p = T + '/app.js.j2'
    L = open(p, encoding='utf-8').read().split('\n')
    g0 = [k for k, l in enumerate(L) if l.strip().startswith('function _graphGet(')]
    if len(g0) != 1:
        abort('_graphGet 命中 %d' % len(g0))
    st = max(k for k in range(g0[0]) if L[k].strip() == '<% if has_graphs %>')
    og = [k for k in range(g0[0], len(L)) if 'function onGraphNode(path, ev, popup) {' in L[k]]
    if len(og) != 1:
        abort('onGraphNode 命中 %d' % len(og))
    close = next(k for k in range(og[0] + 1, len(L)) if L[k] == '    }')
    en = next(k for k in range(close + 1, len(L)) if L[k].strip())
    if L[en].strip() != '<% endif %>':
        abort('onGraphNode 后不是 endif')
    L[st:en + 1] = RT.split('\n')
    open(p, 'w', encoding='utf-8').write('\n'.join(L))
    print('app: dagre + 科技树')

    # index.html.j2：确认 Vue Flow 和 dagre 都在
    ih = open(T + '/index.html.j2', encoding='utf-8').read()
    if 'graph_js %>' not in ih or 'dagre_js %>"></script>' not in ih:
        abort('index.html.j2 里 Vue Flow 或 dagre 的 script 不全')

    # style.css.j2
    p = T + '/style.css.j2'
    s = open(p, encoding='utf-8').read()
    if '.kg-head' not in s:
        open(p, 'w', encoding='utf-8').write(s.rstrip('\n') + CSS)
    print('style: 层带 / 卡片 / 连线')

    # ======================================================== 验证
    for mod in [k for k in list(sys.modules) if k.startswith('tools')]:
        del sys.modules[mod]
    sys.path.insert(0, P)
    from tools.ui import compile_ui
    ok = True
    UI = '''界面 自定义 科技树
  分组 a 竖排
    节点图 kg 绑 graph 选中 sel 图例 高 600px
    节点图 h 绑 graph2 高 300px 方向 横向
  结束
结束
'''
    r = compile_ui(UI, backend='vue', options={'title': 't'})
    iss = [str(i) for i in r['issues']]
    print('ISSUES:', iss or '无')
    ok &= not iss
    js, html = r['result']['files']['app.js'], r['result']['files']['index.html']
    os.makedirs('/tmp/g', exist_ok=True)
    open('/tmp/g/rb.js', 'w', encoding='utf-8').write(js)
    c = {'卡片': 'kg-head' in js, '直角线': "type: 'smoothstep'" in js, 'minlen': 'minlen' in js,
         '层带': '#node-kglayer' in js, '图例只一处': js.count('.legend }}') == 1,
         'CDN': 'vue-flow-core' in html and 'dagre.min.js' in html}
    print(c)
    ok &= all(c.values())
    rc = subprocess.run(['node', '--check', '/tmp/g/rb.js'], capture_output=True, text=True)
    print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:300])
    ok &= rc.returncode == 0
    tpl = re.search(r'template: `(.*)`', js, re.S).group(1)
    for tag in ['VueFlow', 'template', 'div']:
        o = len(re.findall(r'<%s[\s>]' % tag, tpl)); cc = tpl.count('</%s>' % tag)
        print('标签 %-8s 开 %d 闭 %d %s' % (tag, o, cc, 'OK' if o == cc else '!!'))
        ok &= o == cc

    if not os.path.exists('/tmp/g/dagre.js'):
        import urllib.request
        open('/tmp/g/dagre.js', 'w').write(urllib.request.urlopen(
            'https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js', timeout=30).read().decode())
    seg = re.search(r'(function _graphGet.*?function onGraphNode\(path, ev, popup\) \{.*?\n    \})', js, re.S).group(1)

    # 一、卡片内容和连线
    small = {'nodes': [
        {'id': 'hira', 'label': '平假名', 'state': 'done'},
        {'id': 'kata', 'label': '片假名', 'state': 'open', 'progress': 0.6},
        {'id': 'daku', 'label': '浊音', 'state': 'open'},
        {'id': 'you', 'label': '拗音', 'state': 'locked'},
        {'id': 'kanji', 'label': '汉字', 'state': 'locked', 'sub': '常用 300 字', 'icon': '漢'},
        {'id': 'mix', 'label': '综合', 'state': 'locked'}],
        'edges': [{'from': 'hira', 'to': 'kata'}, {'from': 'hira', 'to': 'daku'}, {'from': 'daku', 'to': 'you'},
                  {'from': 'kata', 'to': 'kanji'}, {'from': 'you', 'to': 'mix'}, {'from': 'kanji', 'to': 'mix'},
                  {'from': 'kata', 'to': 'daku', 'kind': '对照'}]}
    # 二、层 = 步数（38 个节点，含一块不相连的小图）
    random.seed(7)
    nodes, done = [], []
    for Lr, cnt in enumerate([1, 3, 5, 11, 4, 9, 2]):
        lower = list(done)
        for i in range(cnt):
            prer = random.sample(lower, k=min(len(lower), random.choice([1, 1, 2]))) if lower else []
            nodes.append({'id': 'n%d_%02d' % (Lr, i), 'pre': prer})
        done += [x['id'] for x in nodes[-cnt:]]
    nodes += [{'id': 'z0', 'pre': []}, {'id': 'z1', 'pre': ['z0']}, {'id': 'z2', 'pre': ['z1']}]
    dd = {}
    def pd(k):
        if k not in dd:
            dd[k] = max([pd(q) + 1 for q in next(x for x in nodes if x['id'] == k)['pre']], default=0)
        return dd[k]
    for x in nodes:
        pd(x['id'])
    big = {'nodes': [{'id': x['id'], 'label': x['id']} for x in nodes],
           'edges': [{'from': q, 'to': x['id']} for x in nodes for q in x['pre']]}
    test = ("globalThis.dagre = require('/tmp/g/dagre.js');\n"
            "const shared = { value: { s: " + json.dumps(small, ensure_ascii=False) + ", b: " + json.dumps(big) + " } };\n"
            + seg + r'''
for (const dir of ['纵向', '横向']) {
  const g = graphOf('s', dir);
  const kg = g.nodes.filter(v => v.type === 'kg');
  const axis = dir === '横向' ? 'x' : 'y';
  const vals = [...new Set(kg.map(v => Math.round(v.position[axis])))].sort((a, b) => a - b);
  console.log('S', dir, '层距', JSON.stringify([...new Set(vals.slice(1).map((v, i) => v - vals[i]))]),
    '| 线', [...new Set(g.edges.map(e => e.type + ':' + e.class))].join(' '));
}
graphOf('s', '纵向').nodes.filter(v => v.type === 'kg').forEach(v => console.log('C', v.id, v.data.__view.sub, 'bar=' + v.data.__view.bar,
  'icon=' + (v.data.__view.icon.startsWith('<svg') ? 'svg' : v.data.__view.icon)));
onGraphNode('sel', { node: { type: 'kg', data: graphOf('s', '纵向').nodes.find(v => v.id === 'you').data } }, '');
console.log('SEL', !('__view' in shared.value.sel), shared.value.sel.label);
const gb = graphOf('b', '纵向');
const kb = gb.nodes.filter(v => v.type === 'kg');
const ys = [...new Set(kb.map(v => Math.round(v.position.y)))].sort((a, b) => a - b);
const rank = {}; kb.forEach(v => rank[v.id] = ys.indexOf(Math.round(v.position.y)));
console.log('RANK ' + JSON.stringify(rank));
console.log('LAYERS', gb.nodes.filter(v => v.type === 'kglayer').length);
''')
    open('/tmp/g/rb_logic.js', 'w', encoding='utf-8').write(test)
    rc = subprocess.run(['node', '/tmp/g/rb_logic.js'], capture_output=True, text=True)
    out = rc.stdout.strip() or rc.stderr[:600]
    if rc.returncode != 0:
        print(out); ok = False
    else:
        for line in out.split('\n'):
            if not line.startswith('RANK'):
                print(line)
        rank = json.loads(re.search(r'^RANK (.*)$', out, re.M).group(1))
        diff = [k for k in dd if rank.get(k) != dd[k]]
        print('层≠步数:', len(diff), diff[:6])
        ok &= not diff
        ok &= 'S 纵向 层距 [128]' in out and 'S 横向 层距 [244]' in out
        ok &= '学习中 60%' in out and 'bar=60' in out and '需要 浊音' in out and '常用 300 字' in out and 'icon=漢' in out
        ok &= 'smoothstep:kg-live' in out and 'smoothstep:kg-dim' in out and 'SEL true' in out
        ok &= ('LAYERS %d' % (max(dd.values()) + 1)) in out

    print('全部通过:', ok)
    if not ok:
        abort('验证没过')
    git('add', '--', *FILES)
    rc, out = git('commit', '-m',
                  '节点图重写：只用 dagre，游戏科技树的样子（回滚后重做）\n\n'
                  '- 层 = 最长前置链步数：每条边 minlen = 两端步数之差，虚拟根连所有第 0 步\n'
                  '- 卡片 180×64：状态图标 + 名字 + 说明行 + 进度条 + 角标；'
                  '说明行按 sub / progress / 状态生成，锁定时列出没掌握的前置\n'
                  '- smoothstep 直角折线，已解锁主色、没解锁淡灰；对照只连同一层\n'
                  '- 层带与「第 N 步」（layerNames 可起名），横向时竖过来；「图例」旗标\n'
                  '- 默认从上到下，「方向 横向」从左到右；dagre 没加载时按步数排开')
    print('commit:', rc, out.splitlines()[:1])


if __name__ == '__main__':
    main()
