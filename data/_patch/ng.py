import os, shutil
S = '/home/ysc/mcp/templates/frontend'
B = '/tmp/tpl_bak5'
os.makedirs(B, exist_ok=True)
for f in ['graph.j2', 'app.js.j2', 'style.css.j2']:
    shutil.copy(S + '/' + f, B + '/' + f)

# ---------------------------------------------------------------- graph.j2
GRAPH = r'''<% from "widgets.j2" import 当, 尺寸 with context %>
{#- 「节点图」控件：有向无环图，Vue Flow 画、dagre 布局。单独一个文件：它是
    唯一带外部依赖的控件，分开放好找也好删。

    数据形状（从「绑」指定的共享路径读）：

        shared.graph = {
          nodes: [{ id, label, x?, y?, width?, height?, state?, badge?,
                    class?, style?, ...自定义 }],
          edges: [{ from, to, kind?, layout?, type?, class?, style?, label? }]
        }

    节点：
      x/y       给了就按给的放（左上角），都没给才跑 dagre。后端想跟
                kg_svg 排得一模一样，就把它算好的坐标原样送来。
      state     done/open/locked（或 掌握/可学/锁定）→ 实心 / 粗描边 / 淡出
      badge     右上角的小圆角标，比如下游节点数
      class     额外的 class，跟 state 合并
    边：
      kind 对照  虚线、从侧面连、不参与布局
      layout:false  同上但不加虚线样式
    其余字段原样挂在 data 上，点节点时整个对象写进「选中」路径。

    :key 取节点数和边数：数据是后端一次性给全的，换一批数据时让 VueFlow
    重建，fit-view-on-init 才会对新数据重新取景——否则第一次渲染时数据还
    是空的，取景就落空了。

    只读：不能拖、不能连线。要编辑得先想清楚改动怎么回传后端。 -#}
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
  fit-view-on-init
  @node-click="onGraphNode('<%= n.selects %>', $event)"
  @pane-click="onGraphNode('<%= n.selects %>', null)">
<template #node-kg="p">
<div class="kg-node">
<Handle id="in" type="target" :position="p.targetPosition" />
<Handle id="pt" type="target" :position="p.sourcePosition === 'right' ? 'top' : 'left'" />
<Handle id="ps" type="source" :position="p.sourcePosition === 'right' ? 'top' : 'left'" />
<span class="kg-label">{{ p.label }}</span>
<span v-if="p.data.badge != null && p.data.badge !== ''" class="kg-badge">{{ p.data.badge }}</span>
<Handle id="qt" type="target" :position="p.sourcePosition === 'right' ? 'bottom' : 'right'" />
<Handle id="qs" type="source" :position="p.sourcePosition === 'right' ? 'bottom' : 'right'" />
<Handle id="out" type="source" :position="p.sourcePosition" />
</div>
</template>
</VueFlow>
</div>
<%- endmacro -%>
'''
open(S + '/graph.j2', 'w', encoding='utf-8').write(GRAPH)
print('graph.j2 已重写')

# ---------------------------------------------------------------- app.js.j2
RT = r'''<% if has_graphs %>
    // 节点图：数据从共享路径读 {nodes, edges}，dagre 算坐标，Vue Flow 画。
    // 按数据内容缓存：模板里 nodes/edges/key 各调一次，不缓存的话每次渲染都跑 dagre。
    const _graphCache = new Map();
    function _graphGet(obj, path) { return path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj); }
    function _graphPut(obj, path, value) { const parts = path.split('.'); let box = obj; for (const k of parts.slice(0, -1)) box = box[k] || (box[k] = {}); box[parts[parts.length - 1]] = value; }
    // 节点状态 -> class。后端也可以直接给 class，两者合并。
    const _kgState = { done: 'kg-done', open: 'kg-open', locked: 'kg-locked', '掌握': 'kg-done', '可学': 'kg-open', '锁定': 'kg-locked' };
    // 不参与布局的边：显式 layout:false，或 kind 为「对照」。照样画，但 dagre
    // 不算——否则同层的对照关系会把本该并排的两个节点拉成上下两层。
    function _kgSide(e) { return e.layout === false || e.kind === '对照'; }
    function graphOf(path, dir) {
      const raw = _graphGet(shared.value, path) || {};
      const src = raw.nodes || [], links = raw.edges || [];
      const key = path + '|' + dir + '|' + JSON.stringify(raw);
      if (_graphCache.has(key)) return _graphCache.get(key);
      const lr = dir === '横向';
      const W = 118, H = 40, pos = {};
      const wOf = n => n.width || W, hOf = n => n.height || H;
      // 节点自带 x/y 就按给的放；只要有一个没给就整张图跑布局，混用会叠在原点
      if (src.some(n => n.x == null || n.y == null) && typeof dagre !== 'undefined') {
        const g = new dagre.graphlib.Graph();
        g.setDefaultEdgeLabel(() => ({}));
        g.setGraph({ rankdir: lr ? 'LR' : 'TB', nodesep: 32, ranksep: 64 });
        src.forEach(n => g.setNode(String(n.id), { width: wOf(n), height: hOf(n) }));
        links.filter(e => !_kgSide(e)).forEach(e => g.setEdge(String(e.from), String(e.to)));
        dagre.layout(g);
        // dagre 给中心点，Vue Flow 要左上角
        src.forEach(n => { const v = g.node(String(n.id)); if (v) pos[n.id] = { x: v.x - wOf(n) / 2, y: v.y - hOf(n) / 2 }; });
      }
      const at = {};
      const nodes = src.map(n => {
        const p = (n.x != null && n.y != null) ? { x: n.x, y: n.y } : (pos[n.id] || { x: 0, y: 0 });
        at[String(n.id)] = p;
        return {
          id: String(n.id), type: 'kg', position: p,
          label: n.label != null ? String(n.label) : String(n.id),
          class: [_kgState[n.state], n.class].filter(Boolean).join(' '),
          // 渲染尺寸跟布局尺寸一致，否则 dagre 按 118 宽排、画出来却是别的宽度
          style: Object.assign({ width: wOf(n) + 'px', height: hOf(n) + 'px' }, n.style || {}),
          // 横向时从左右出入。不设的话 Vue Flow 默认上进下出，横向图的线全绕到上下边
          targetPosition: lr ? 'left' : 'top',
          sourcePosition: lr ? 'right' : 'bottom',
          data: n,
        };
      });
      const edges = links.map((e, i) => {
        const s = String(e.from), t = String(e.to), side = _kgSide(e);
        const r = {
          id: e.id != null ? String(e.id) : 'e' + i, source: s, target: t,
          type: e.type || (side ? 'straight' : 'default'),
          class: [e.kind === '对照' ? 'kg-contrast' : '', e.class].filter(Boolean).join(' '),
        };
        if (side) {
          // 侧面连线：沿「垂直于层」的方向比位置，往远端那侧出、从近端那侧进
          const a = at[s] || { x: 0, y: 0 }, b = at[t] || { x: 0, y: 0 };
          const far = lr ? b.y >= a.y : b.x >= a.x;
          r.sourceHandle = far ? 'qs' : 'ps';
          r.targetHandle = far ? 'pt' : 'qt';
        } else {
          r.sourceHandle = 'out'; r.targetHandle = 'in';
        }
        if (e.style) r.style = e.style;
        if (e.label != null) r.label = String(e.label);
        return r;
      });
      const out = { nodes, edges };
      _graphCache.clear(); _graphCache.set(key, out);
      return out;
    }
    // 点节点：整个节点对象写进「选中」路径；点空白清掉。之后用「当 shared.sel」
    // 控制显隐、「显示 sel.label」展示内容，都是现成词汇。
    function onGraphNode(path, ev) { if (path) _graphPut(shared.value, path, ev && ev.node ? ev.node.data : null); }
<% endif %>'''

p = S + '/app.js.j2'
L = open(p, encoding='utf-8').read().split('\n')
mark = [k for k, l in enumerate(L) if '// 节点图：数据从共享路径读' in l]
assert len(mark) == 1, '运行时段标记命中 %d' % len(mark)
st = max(k for k in range(mark[0]) if L[k].strip() == '<% if has_graphs %>')
en = next(k for k in range(mark[0], len(L)) if L[k].strip() == '<% endif %>')
assert mark[0] - st <= 2, '标记与 if 相隔太远: %d' % (mark[0] - st)
L[st:en + 1] = RT.split('\n')
s = '\n'.join(L)
old = '<% if has_graphs %>_app.component("VueFlow", VueFlowCore.VueFlow);<% endif %>'
new = '<% if has_graphs %>_app.component("VueFlow", VueFlowCore.VueFlow); _app.component("Handle", VueFlowCore.Handle);<% endif %>'
if 'VueFlowCore.Handle' not in s:
    assert s.count(old) == 1, '组件注册行命中 %d' % s.count(old)
    s = s.replace(old, new)
    print('app 注册 Handle')
open(p, 'w', encoding='utf-8').write(s)
print('app 运行时段已替换（%d-%d 行）' % (st + 1, en + 1))

# ---------------------------------------------------------------- style.css.j2
p = S + '/style.css.j2'
s = open(p, encoding='utf-8').read()
if '.kg-node' not in s:
    s = s.rstrip('\n') + '''

/* 节点图的节点：照 kg_svg 的样子。未标状态时是淡色，三态由 state 给。 */
.graph-wrap .vue-flow__node-kg { padding:0; border:0; background:transparent; }
.kg-node {
  box-sizing:border-box; width:100%; height:100%; position:relative;
  display:flex; align-items:center; justify-content:center;
  background:#fff; border:1px solid #ddd8d0; border-radius:7px;
  font-size:13px; color:#b5aca1; cursor:pointer;
}
.vue-flow__node.kg-open .kg-node { border:2.2px solid #4a7a8c; color:#4a7a8c; }
.vue-flow__node.kg-done .kg-node { background:#4a7a8c; border-color:#4a7a8c; color:#fff; }
.vue-flow__node.kg-locked { opacity:.72; }
.vue-flow__node.selected .kg-node { box-shadow:0 0 0 3px rgba(74,122,140,.25); }
.kg-badge {
  position:absolute; top:-7px; right:-7px; min-width:18px; height:18px;
  padding:0 4px; border-radius:9px; background:#4a7a8c; color:#fff;
  font-size:10px; line-height:18px; text-align:center;
}
/* 连接点只用来定线的起止位置，不给人看也不给人拖 */
.kg-node .vue-flow__handle { opacity:0; pointer-events:none; }
.graph-wrap .vue-flow__edge-path { stroke:#e2ddd5; stroke-width:1; }
.graph-wrap .vue-flow__edge.kg-contrast .vue-flow__edge-path { stroke:#cfc4b4; stroke-dasharray:3 3; }
'''
    open(p, 'w', encoding='utf-8').write(s)
    print('style 追加节点图样式')
print('完成')
