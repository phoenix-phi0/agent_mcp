import subprocess, os, re, sys, json
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
FILES = ['templates/frontend/app.js.j2', 'templates/frontend/graph.j2']


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


COMPACT = r'''        // 压紧：每一层按 dagre 排出来的先后重新挨着放，超过 8 张折成几行，每行居中。
        // dagre 负责分层和减少交叉，这一步只管紧凑——它为了上下对齐会在同层卡片之间
        // 留空档，最宽的那层还会一字排开，左右都是空白
        {
          const MAXR = 8, SUBGAP = 16;
          const along = lr ? 'x' : 'y', across = lr ? 'y' : 'x';
          const stepA = lr ? BW + RANKSEP : BH + RANKSEP;   // 层与层
          const stepC = lr ? BH + NODESEP : BW + NODESEP;   // 同一行相邻两张
          const stepS = lr ? BW + SUBGAP : BH + SUBGAP;     // 同一层折出来的几行之间
          const byL = new Map();
          src.forEach(n => { if (!pos[K(n)]) return; const L = depth[K(n)]; if (!byL.has(L)) byL.set(L, []); byL.get(L).push(n); });
          let cur = 0;
          [...byL.keys()].sort((a, b) => a - b).forEach(L => {
            const row = byL.get(L).sort((a, b) => pos[K(a)][across] - pos[K(b)][across]);
            const lines = Math.ceil(row.length / MAXR), per = Math.ceil(row.length / lines);
            for (let i = 0; i < lines; i++) {
              const part = row.slice(i * per, (i + 1) * per);
              const start = -(part.length - 1) * stepC / 2;
              part.forEach((n, j) => { pos[K(n)] = { [across]: start + j * stepC, [along]: cur + i * stepS }; });
            }
            cur += (lines - 1) * stepS + stepA;
          });
        }
'''


def main():
    print('HEAD:', git('log', '--oneline', '-1')[1])
    rc, st = git('status', '--porcelain', '--', *FILES)
    if st:
        raise SystemExit('文件有未提交改动，不动：\n' + st)

    p = T + '/app.js.j2'
    s = open(p, encoding='utf-8').read()
    anchor = "        src.forEach(n => { const v = g.node(K(n)); if (v) pos[K(n)] = { x: v.x, y: v.y }; });\n"
    s = sub1(s, anchor, anchor + COMPACT, 'dagre 结果')
    # 层带要盖住这一层折出来的所有行
    s = sub1(s, "            ? { x: Math.min(...at.map(c => c.x)) - BW / 2 - RANKSEP / 2, y: minY, w: BW + RANKSEP, h: maxY - minY }\n",
             "            ? { x: Math.min(...at.map(c => c.x)) - BW / 2 - RANKSEP / 2, y: minY, w: Math.max(...at.map(c => c.x)) - Math.min(...at.map(c => c.x)) + BW + RANKSEP, h: maxY - minY }\n",
             '横向层带')
    s = sub1(s, "            : { x: minX, y: Math.min(...at.map(c => c.y)) - BH / 2 - RANKSEP / 2, w: maxX - minX, h: BH + RANKSEP };\n",
             "            : { x: minX, y: Math.min(...at.map(c => c.y)) - BH / 2 - RANKSEP / 2, w: maxX - minX, h: Math.max(...at.map(c => c.y)) - Math.min(...at.map(c => c.y)) + BH + RANKSEP };\n",
             '纵向层带')
    s = s.replace("    //   同层 = dagre 排，减少交叉；不折行\n",
                  "    //   同层 = dagre 定先后（减少交叉），再挨着排、超过 8 张折行、每行居中\n")
    open(p, 'w', encoding='utf-8').write(s)
    print('app: 压紧 + 折行')

    p = T + '/graph.j2'
    s = open(p, encoding='utf-8').read()
    s = s.replace('      同层    顺序交给 dagre 减少交叉。dagre 不会折行：同层很多时会往横向铺开\n',
                  '      同层    dagre 定先后（减少交叉），然后挨着排、超过 8 张折成几行、每行居中\n')
    open(p, 'w', encoding='utf-8').write(s)

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
    open('/tmp/g/cmp.js', 'w', encoding='utf-8').write(js)
    ok = subprocess.run(['node', '--check', '/tmp/g/cmp.js'], capture_output=True).returncode == 0
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
  const along = dir === '横向' ? 'x' : 'y', across = dir === '横向' ? 'y' : 'x';
  const at = {}; kg.forEach(v => at[v.id] = { a: v.position[along], c: v.position[across] });
  // 卡片之间有没有重叠
  let overlap = 0;
  for (let i = 0; i < kg.length; i++) for (let j = i + 1; j < kg.length; j++) {
    const p = kg[i].position, q = kg[j].position;
    if (Math.abs(p.x - q.x) < W && Math.abs(p.y - q.y) < H) overlap++;
  }
  const perRow = {}; kg.forEach(v => { const k = Math.round(v.position[along]); perRow[k] = (perRow[k] || 0) + 1; });
  const bands = o.nodes.filter(v => v.type === 'kglayer').length;
  console.log(JSON.stringify({ dir, w: Math.round(w), h: Math.round(h), fill: Math.round(kg.length * W * H / (w * h) * 1000) / 10,
    rows: Object.keys(perRow).length, widest: Math.max(...Object.values(perRow)), overlap, bands, drawn: o.edges.filter(e => e.type === 'smoothstep').length, at }));
}
''')
    open('/tmp/g/cmp_logic.js', 'w', encoding='utf-8').write(test)
    rc = subprocess.run(['node', '/tmp/g/cmp_logic.js'], capture_output=True, text=True)
    if rc.returncode != 0:
        print(rc.stderr[:500]); abort('JS 出错')
    n_pre = sum(len(v) for v in pre.values())
    for line in rc.stdout.strip().split('\n'):
        j = json.loads(line)
        # 分层还对不对：第 L 层所有卡片都在第 L+1 层所有卡片之前
        by = {}
        for k, v in j['at'].items():
            by.setdefault(dep[k], []).append(v['a'])
        order_ok = all(max(by[L]) < min(by[L + 1]) for L in sorted(by) if L + 1 in by)
        print(j['dir'], '宽', j['w'], '高', j['h'], '| 卡片占比', str(j['fill']) + '%', '| 行数', j['rows'], '每行最多', j['widest'],
              '| 重叠', j['overlap'], '| 层带', j['bands'], '| 前置线', j['drawn'], '/', n_pre, '| 分层次序对:', order_ok)
        ok &= order_ok and j['overlap'] == 0 and j['widest'] <= 8 and j['drawn'] == n_pre and j['bands'] == len(by)
    print('全部通过:', ok)
    if not ok:
        abort('验证没过')
    git('add', '--', *FILES)
    rc, out = git('commit', '-m', '节点图压紧：每层按 dagre 的先后挨着排，超过 8 张折行\n\n'
                  '- dagre 负责分层和减少交叉；排完后每层重新挨着放、超过 8 张折成几行、每行居中\n'
                  '- 层带盖住这一层折出来的所有行\n'
                  '- 真实图 69 点：见提交前的测量')
    print('commit:', rc, out.splitlines()[:1])


if __name__ == '__main__':
    main()
