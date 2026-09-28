import subprocess, os, re, sys, json
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
FILES = ['templates/frontend/app.js.j2', 'templates/frontend/graph.j2', 'templates/frontend/style.css.j2']


def git(*a):
    r = subprocess.run(['git', *a], cwd=P, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def abort(msg):
    git('checkout', 'HEAD', '--', *FILES)
    raise SystemExit('失败，已恢复到 HEAD：' + msg)


def sub1(s, old, new, what):
    if s.count(old) != 1:
        abort('%s 命中 %d' % (what, s.count(old)))
    return s.replace(old, new)


def main():
    print('HEAD:', git('log', '--oneline', '-1')[1])
    rc, st = git('status', '--porcelain', '--', *FILES)
    if st:
        raise SystemExit('文件有未提交改动，不动：\n' + st)

    p = T + '/app.js.j2'
    s = open(p, encoding='utf-8').read()
    s = sub1(s, "    const _KG = { BW: 180, BH: 64, NODESEP: 40, RANKSEP: 64, PAD: 56 };",
             "    // 卡片 150×52，横距 16、层距 40（层与层中心相距 92）。原先 180×64 / 40 / 64，\n"
             "    // 在 69 个点的真实图上卡片只占画面 6%，太散\n"
             "    const _KG = { BW: 150, BH: 52, NODESEP: 16, RANKSEP: 40, PAD: 40 };", '_KG')
    s = sub1(s, "        g.setGraph({ rankdir: lr ? 'LR' : 'TB', nodesep: NODESEP, ranksep: RANKSEP });",
             "        g.setGraph({ rankdir: lr ? 'LR' : 'TB', nodesep: NODESEP, ranksep: RANKSEP, edgesep: 8 });", 'setGraph')
    s = sub1(s, "        src.forEach(n => pre[K(n)].forEach(p => g.setEdge(p, K(n), { minlen: Math.max(1, depth[K(n)] - depth[p]) })));",
             "        // 只拿跨一层的边去排。跨多层的边 dagre 会在经过的每一层塞一个占位点，每个\n"
             "        // 都占横向位置——真实图 112 条前置边里 35 条跨 2 层以上（最长 9 层），最宽\n"
             "        // 的一层只有 12 张卡片，却被撑到 7770px 宽。跨层边照样画，只是不参与排。\n"
             "        // 层不受影响：每个点都有一条从最深前置来的、正好跨一层的边，它决定这个点的层\n"
             "        src.forEach(n => pre[K(n)].forEach(p => { if (depth[K(n)] - depth[p] === 1) g.setEdge(p, K(n), { minlen: 1 }); }));",
             'setEdge')
    s = s.replace("    //   卡片 = 180×64；层距 = 卡片高 + ranksep = 128（横向 244）\n",
                  "    //   卡片 = 150×52；层距 = 卡片高 + ranksep = 92（横向 190）\n")
    open(p, 'w', encoding='utf-8').write(s)
    print('app: 收紧 + 跨层边不参与排布')

    p = T + '/graph.j2'
    s = open(p, encoding='utf-8').read()
    s = s.replace('      卡片    180×64：', '      卡片    150×52：')
    s = s.replace('      间距    nodesep 40、ranksep 64；层距 = 卡片高 + ranksep = 128（横向 244）\n',
                  '      间距    nodesep 16、ranksep 40；层距 = 卡片高 + ranksep = 92（横向 190）\n'
                  '              跨多层的边照样画，但不参与排布——否则 dagre 给它经过的每层塞占位点，\n'
                  '              图会被撑得很宽\n')
    open(p, 'w', encoding='utf-8').write(s)

    p = T + '/style.css.j2'
    s = open(p, encoding='utf-8').read()
    if '/* 卡片收紧到 150×52 */' not in s:
        s = s.rstrip('\n') + '''

/* 卡片收紧到 150×52 */
.kg-node { padding:6px 10px; gap:3px; }
'''
        open(p, 'w', encoding='utf-8').write(s)
    print('style: 卡片内边距')

    # ---------------------------------------------------- 验证：真实数据
    import sqlite3
    db = sqlite3.connect(P + '/kg/app.db'); db.row_factory = sqlite3.Row
    def q(name):
        sql = open(P + '/kg/queries/%s.sql' % name, encoding='utf-8').read()
        for a in (sql, re.sub(r'\{(\w+)\}', r':\1', sql)):
            try:
                return [dict(r) for r in (db.execute(a, {'learner': '', 'code': ''}) if ':' in a else db.execute(a))]
            except Exception as e:
                err = e
        raise err
    g = {'nodes': [{'id': str(n['id']), 'label': n['label'], 'state': n.get('state')} for n in q('kg_graph_nodes')],
         'edges': [{'from': str(e['from']), 'to': str(e['to']), **({'kind': e['kind']} if e.get('kind') else {})} for e in q('kg_graph_edges')]}
    pre = {n['id']: [] for n in g['nodes']}
    for e in g['edges']:
        if e.get('kind') != '对照' and e['from'] in pre and e['to'] in pre:
            pre[e['to']].append(e['from'])
    dep = {}
    def d(k, seen=()):
        if k in dep: return dep[k]
        if k in seen: return 0
        dep[k] = max([d(x, seen + (k,)) + 1 for x in pre[k]], default=0); return dep[k]
    for k in pre: d(k)

    sys.path.insert(0, P)
    from tools.ui import compile_ui
    r = compile_ui('界面 自定义 T\n  节点图 kg 绑 graph 选中 sel 占满\n结束\n', backend='vue', options={'title': 't'})
    js = r['result']['files']['app.js']
    os.makedirs('/tmp/g', exist_ok=True)
    open('/tmp/g/tight.js', 'w', encoding='utf-8').write(js)
    ok = subprocess.run(['node', '--check', '/tmp/g/tight.js'], capture_output=True).returncode == 0
    print('node --check:', ok)
    seg = re.search(r'(function _graphGet.*?function onGraphNode\(path, ev, popup, carry\) \{.*?\n    \})', js, re.S).group(1)
    test = ("globalThis.dagre = require('/tmp/g/dagre.js');\n"
            "const shared = { value: { graph: " + json.dumps(g, ensure_ascii=False) + " } };\n"
            "const lists = { value: {} }; function showOverlay(){} function reset(){} const current={value:{name:'T'}}; const openOverlay={value:null};\n"
            + seg + r'''
for (const dir of ['纵向', '横向']) {
  const o = graphOf('graph', dir, {});
  const kg = o.nodes.filter(v => v.type === 'kg');
  const W = parseFloat(kg[0].style.width), H = parseFloat(kg[0].style.height);
  const xs = kg.map(v => v.position.x), ys = kg.map(v => v.position.y);
  const w = Math.max(...xs) + W - Math.min(...xs), h = Math.max(...ys) + H - Math.min(...ys);
  const ax = dir === '横向' ? xs : ys;
  const vals = [...new Set(ax.map(Math.round))].sort((a, b) => a - b);
  const rank = {}; kg.forEach(v => rank[v.id] = vals.indexOf(Math.round(dir === '横向' ? v.position.x : v.position.y)));
  const gaps = [...new Set(vals.slice(1).map((v, i) => v - vals[i]))];
  const drawn = o.edges.filter(e => e.type === 'smoothstep').length;
  console.log(JSON.stringify({ dir, w: Math.round(w), h: Math.round(h), fill: Math.round(kg.length * W * H / (w * h) * 1000) / 10, gaps, drawn, rank }));
}
''')
    open('/tmp/g/tight_logic.js', 'w', encoding='utf-8').write(test)
    rc = subprocess.run(['node', '/tmp/g/tight_logic.js'], capture_output=True, text=True)
    if rc.returncode != 0:
        print(rc.stderr[:500]); abort('JS 出错')
    n_pre = sum(len(v) for v in pre.values())
    for line in rc.stdout.strip().split('\n'):
        j = json.loads(line)
        diff = [k for k in dep if j['rank'].get(k) != dep[k]]
        print(j['dir'], '宽', j['w'], '高', j['h'], '| 卡片占比', str(j['fill']) + '%', '| 层距', j['gaps'],
              '| 画出的前置线', j['drawn'], '/', n_pre, '| 层≠步数', len(diff))
        want = [92] if j['dir'] == '纵向' else [190]
        ok &= not diff and j['gaps'] == want and j['drawn'] == n_pre
        if j['dir'] == '纵向':
            ok &= j['w'] < 4000
    print('全部通过:', ok)
    if not ok:
        abort('验证没过')
    git('add', '--', *FILES)
    rc, out = git('commit', '-m', '节点图收紧：卡片 150×52，跨多层的边不参与排布\n\n'
                  '- 真实图 69 点 112 条前置边：宽 7770 → 约 3400px，卡片占画面 6.4% → 约 14%\n'
                  '- 散的主因是 35 条跨 2 层以上的边：dagre 在它经过的每层塞占位点撑宽画面。'
                  '现在只拿跨一层的边去排，跨层边照样画；层仍等于最长前置链步数\n'
                  '- 横距 16、层距 40，edgesep 8')
    print('commit:', rc, out.splitlines()[:1])


if __name__ == '__main__':
    main()
