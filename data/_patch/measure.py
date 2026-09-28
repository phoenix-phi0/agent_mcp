import subprocess, os, re, json, sqlite3, sys
P = '/home/ysc/mcp'
db = sqlite3.connect(P + '/kg/app.db')
db.row_factory = sqlite3.Row
names = [r[0] for r in db.execute("select name from sqlite_master where name like '%graph%' or name like 'kg_%'")]
print('库里相关的表/视图:', names)

def rows(sql):
    return [dict(r) for r in db.execute(sql)]

nodes = edges = None
for cand in ['kg_graph_nodes', 'kg_nodes', 'node']:
    if cand in names:
        try:
            nodes = rows('select * from %s' % cand); print('节点来自', cand, len(nodes), '| 字段', list(nodes[0].keys())[:8]); break
        except Exception as e:
            print(cand, e)
for cand in ['kg_graph_edges', 'kg_edges', 'edge']:
    if cand in names:
        try:
            edges = rows('select * from %s' % cand); print('边来自', cand, len(edges), '| 字段', list(edges[0].keys())[:6]); break
        except Exception as e:
            print(cand, e)
if not nodes or not edges:
    # 查询可能写在 .zs 的查询定义里而不是视图——去找 SQL 原文
    r = subprocess.run("grep -rn -A6 -e 'kg_graph_nodes' -e 'kg_graph_edges' kg --include='*.sql' --include='*.zs' --include='*.txt' | head -40",
                       shell=True, cwd=P, capture_output=True, text=True)
    print(r.stdout[:1500])
    sys.exit(0)

def pick(d, *ks):
    for k in ks:
        if k in d and d[k] is not None:
            return d[k]
g = {'nodes': [{'id': str(pick(n, 'id', 'code')), 'label': pick(n, 'label', 'name')} for n in nodes],
     'edges': [{'from': str(pick(e, 'from', 'src', 'source', 'parent')), 'to': str(pick(e, 'to', 'dst', 'target', 'child')),
                **({'kind': e['kind']} if e.get('kind') else {})} for e in edges]}
json.dump(g, open('/tmp/g/real.json', 'w'), ensure_ascii=False)
print('真实图: %d 个节点, %d 条边（对照 %d）' % (len(g['nodes']), len(g['edges']), sum(1 for e in g['edges'] if e.get('kind') == '对照')))

sys.path.insert(0, P)
from tools.ui import compile_ui
r = compile_ui('界面 自定义 T\n  节点图 kg 绑 graph 选中 sel 占满\n结束\n', backend='vue', options={'title': 't'})
js = r['result']['files']['app.js']
seg = re.search(r'(function _graphGet.*?function onGraphNode\(path, ev, popup, carry\) \{.*?\n    \})', js, re.S).group(1)

A = seg
B = seg.replace("const _KG = { BW: 180, BH: 64, NODESEP: 40, RANKSEP: 64, PAD: 56 };",
                "const _KG = { BW: 150, BH: 52, NODESEP: 16, RANKSEP: 40, PAD: 40 };") \
       .replace("g.setGraph({ rankdir: lr ? 'LR' : 'TB', nodesep: NODESEP, ranksep: RANKSEP });",
                "g.setGraph({ rankdir: lr ? 'LR' : 'TB', nodesep: NODESEP, ranksep: RANKSEP, edgesep: 8 });")
C = B.replace("src.forEach(n => pre[K(n)].forEach(p => g.setEdge(p, K(n), { minlen: Math.max(1, depth[K(n)] - depth[p]) })));",
              "src.forEach(n => pre[K(n)].forEach(p => { if (depth[K(n)] - depth[p] === 1) g.setEdge(p, K(n), { minlen: 1 }); }));")
assert B != A and C != B, '替换没生效'
out = {}
for name, s in [('A 现在', A), ('B 收紧尺寸', B), ('C 收紧+跨层边不参与排布', C)]:
    test = ("globalThis.dagre = require('/tmp/g/dagre.js');\n"
            "const shared = { value: { graph: " + json.dumps(g, ensure_ascii=False) + " } };\n"
            "const lists = { value: {} }; function showOverlay(){} function reset(){} const current={value:{name:'T'}}; const openOverlay={value:null};\n"
            + s + r'''
const o = graphOf('graph', '纵向', {});
const kg = o.nodes.filter(v => v.type === 'kg');
const W = parseFloat(kg[0].style.width), H = parseFloat(kg[0].style.height);
const xs = kg.map(v => v.position.x), ys = kg.map(v => v.position.y);
const w = Math.max(...xs) + W - Math.min(...xs), h = Math.max(...ys) + H - Math.min(...ys);
const rows = new Set(ys.map(Math.round)).size;
const byRow = {}; kg.forEach(v => { const k = Math.round(v.position.y); byRow[k] = (byRow[k] || 0) + 1; });
const widest = Math.max(...Object.values(byRow));
// 卡片面积占整张图的比例：越低越「散」
const fill = kg.length * W * H / (w * h);
console.log(JSON.stringify({ w: Math.round(w), h: Math.round(h), rows, widest, fill: Math.round(fill * 1000) / 10 }));
''')
    open('/tmp/g/m.js', 'w', encoding='utf-8').write(test)
    rc = subprocess.run(['node', '/tmp/g/m.js'], capture_output=True, text=True)
    print(name, rc.stdout.strip() or rc.stderr[:300])
# 跨层边有多少
dep = {}
pre = {}
for n in g['nodes']: pre[n['id']] = []
for e in g['edges']:
    if e.get('kind') != '对照' and e['from'] in pre and e['to'] in pre: pre[e['to']].append(e['from'])
def d(k, seen=()):
    if k in dep: return dep[k]
    if k in seen: return 0
    dep[k] = max([d(p, seen + (k,)) + 1 for p in pre[k]], default=0); return dep[k]
for k in pre: d(k)
span = [dep[t] - dep[f] for t in pre for f in pre[t]]
print('前置边 %d 条，跨 1 层 %d，跨 2 层以上 %d（最长跨 %d 层）' % (len(span), sum(1 for x in span if x == 1), sum(1 for x in span if x > 1), max(span)))
