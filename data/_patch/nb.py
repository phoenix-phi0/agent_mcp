import shutil, os
S = '/home/ysc/mcp/templates/frontend'
os.makedirs('/tmp/tpl_bak4', exist_ok=True)
for f in ['layout.j2', 'index.html.j2', 'style.css.j2', 'app.js.j2', 'graph.j2']:
    if os.path.exists(S + '/' + f):
        shutil.copy(S + '/' + f, '/tmp/tpl_bak4/' + f)

# graph.j2
g = open(S + '/graph.j2', encoding='utf-8').read()
print('graph.j2 宏名 节点图:', 'macro 节点图(' in g)
assert 'macro 节点图(' in g, 'graph.j2 里没有 节点图 宏'

# layout.j2：插在第一个「<% elif node.kind」行之前，不依赖具体是哪个分支
p = S + '/layout.j2'
s = open(p, encoding='utf-8').read()
s = s.replace('<% from "graph.j2" import 图 with context %>\n', '')
L = s.split('\n')
print('layout 里所有分派行:', [(k + 1, l.strip()) for k, l in enumerate(L) if 'node.kind' in l])
if not any('import 节点图' in l for l in L):
    assert L[0].startswith('<% from "widgets.j2"'), 'layout 第一行: ' + L[0][:50]
    L.insert(1, '<% from "graph.j2" import 节点图 with context %>')
    print('layout 加 import')
if not any('node.kind == "节点图"' in l for l in L):
    i = [k for k, l in enumerate(L) if l.strip().startswith('<% elif node.kind')]
    assert i, 'layout 里找不到任何 <% elif node.kind'
    L[i[0]:i[0]] = ['<% elif node.kind == "节点图" %>', '<%= 节点图(node) %>']
    print('layout 加分支，位于第 %d 行' % (i[0] + 1))
open(p, 'w', encoding='utf-8').write('\n'.join(L))

# index.html.j2
p = S + '/index.html.j2'
s = open(p, encoding='utf-8').read()
if 'set has_graphs' not in s:
    s = ('<% set has_graphs = has_graphs if has_graphs is defined else false %>\n'
         '<% set graph_js = graph_js if graph_js is defined else "https://unpkg.com/@vue-flow/core@1.48.2/dist/vue-flow-core.iife.js" %>\n'
         '<% set graph_css = graph_css if graph_css is defined else "https://unpkg.com/@vue-flow/core@1.48.2/dist/style.css" %>\n'
         '<% set dagre_js = dagre_js if dagre_js is defined else "https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js" %>\n') + s
    print('index 加默认值')
if 'graph_js %>' not in s:
    assert s.count('</head>') == 1, '</head> 命中 %d' % s.count('</head>')
    s = s.replace('</head>',
                  '<% if has_graphs %>\n'
                  '  <link rel="stylesheet" href="<%= graph_css %>">\n'
                  '  <script src="<%= graph_js %>"></script>\n'
                  '  <script src="<%= dagre_js %>"></script>\n'
                  '<% endif %>\n</head>')
    print('index 加 CDN')
open(p, 'w', encoding='utf-8').write(s)

# style.css.j2
p = S + '/style.css.j2'
s = open(p, encoding='utf-8').read()
if '.graph-wrap' not in s:
    s = s.rstrip('\n') + (
        '\n\n/* 节点图：高度由 .ui 里的「高」给（内联 style），这里让 Vue Flow 撑满容器。 */\n'
        '.graph-wrap { width:100%; min-height:240px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }\n'
        '.graph-wrap > .vue-flow { width:100%; height:100%; }\n')
    open(p, 'w', encoding='utf-8').write(s)
    print('style 追加')

# app.js.j2
RT = r"""<% if has_graphs %>
    // 节点图：数据从共享路径读 {nodes, edges}，dagre 算坐标，Vue Flow 画。
    // 按数据内容缓存：模板里 nodes/edges 各调一次，不缓存的话每次渲染都跑 dagre。
    const _graphCache = new Map();
    function _graphGet(obj, path) { return path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj); }
    function _graphPut(obj, path, value) { const parts = path.split('.'); let box = obj; for (const k of parts.slice(0, -1)) box = box[k] || (box[k] = {}); box[parts[parts.length - 1]] = value; }
    function graphOf(path, dir) {
      const raw = _graphGet(shared.value, path) || {};
      const src = raw.nodes || [], links = raw.edges || [];
      const key = path + '|' + dir + '|' + JSON.stringify(raw);
      if (_graphCache.has(key)) return _graphCache.get(key);
      const W = 160, H = 40, pos = {};
      // 节点自带 x/y 就按给的放；只要有一个没给就整张图跑布局，混用会叠在原点
      if (src.some(n => n.x == null || n.y == null) && typeof dagre !== 'undefined') {
        const g = new dagre.graphlib.Graph();
        g.setDefaultEdgeLabel(() => ({}));
        g.setGraph({ rankdir: dir === '横向' ? 'LR' : 'TB', nodesep: 40, ranksep: 60 });
        src.forEach(n => g.setNode(String(n.id), { width: n.width || W, height: n.height || H }));
        links.forEach(e => g.setEdge(String(e.from), String(e.to)));
        dagre.layout(g);
        // dagre 给中心点，Vue Flow 要左上角
        src.forEach(n => { const v = g.node(String(n.id)); if (v) pos[n.id] = { x: v.x - (n.width || W) / 2, y: v.y - (n.height || H) / 2 }; });
      }
      const out = {
        nodes: src.map(n => ({ id: String(n.id), position: (n.x != null && n.y != null) ? { x: n.x, y: n.y } : (pos[n.id] || { x: 0, y: 0 }), label: n.label != null ? String(n.label) : String(n.id), data: n })),
        edges: links.map((e, i) => { const r = { id: e.id != null ? String(e.id) : 'e' + i, source: String(e.from), target: String(e.to) }; if (e.label != null) r.label = String(e.label); return r; }),
      };
      _graphCache.clear(); _graphCache.set(key, out);
      return out;
    }
    // 点节点：整个节点对象写进「选中」路径；点空白清掉。之后用「当 shared.sel」
    // 控制显隐、「显示 sel.label」展示内容，都是现成词汇。
    function onGraphNode(path, ev) { if (path) _graphPut(shared.value, path, ev && ev.node ? ev.node.data : null); }
<% endif %>"""

p = S + '/app.js.j2'
s = open(p, encoding='utf-8').read()
if 'set has_graphs' not in s:
    L = s.split('\n')
    i = [k for k, l in enumerate(L[:40]) if l.startswith('<% set has_')]
    assert i, '开头没找到 <% set has_'
    L.insert(i[-1] + 1, '<% set has_graphs = has_graphs if has_graphs is defined else false %>')
    s = '\n'.join(L)
    print('app 加默认值')
if 'function graphOf' not in s:
    L = s.split('\n')
    i = [k for k, l in enumerate(L) if l.strip().startswith('return { route')]
    assert len(i) == 1, 'return { route 命中 %d' % len(i)
    L[i[0]:i[0]] = RT.split('\n')
    s = '\n'.join(L)
    print('app 加运行时')
if 'graphOf, onGraphNode' not in s:
    L = s.split('\n')
    i = [k for k, l in enumerate(L) if l.strip().startswith('return { route')]
    assert len(i) == 1
    l = L[i[0]].rstrip()
    assert l.endswith('};'), 'return 结尾: ' + l[-40:]
    L[i[0]] = l[:-2].rstrip() + '<% if has_graphs %>, graphOf, onGraphNode<% endif %> };'
    s = '\n'.join(L)
    print('app 加导出')
if 'VueFlowCore.VueFlow' not in s:
    if 'const _app = createApp({' not in s:
        assert s.count('createApp({') == 1, 'createApp 命中 %d' % s.count('createApp({')
        s = s.replace('createApp({', 'const _app = createApp({')
    if '}).mount("#app");' in s:
        s = s.replace('}).mount("#app");',
                      '});\n<% if has_graphs %>_app.component("VueFlow", VueFlowCore.VueFlow);<% endif %>\n_app.mount("#app");')
    else:
        assert s.count('_app.mount(') == 1, '_app.mount 命中 %d' % s.count('_app.mount(')
        s = s.replace('_app.mount(', '<% if has_graphs %>_app.component("VueFlow", VueFlowCore.VueFlow);<% endif %>\n_app.mount(', 1)
    print('app 加组件注册')
open(p, 'w', encoding='utf-8').write(s)
print('完成')
