import subprocess, os, re, sys, json
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
FILES = ['tools/ui.py', 'templates/frontend/graph.j2', 'templates/frontend/app.js.j2',
         'templates/frontend/style.css.j2', 'kg/ui/node.ui']

NODE_UI = '''# 知识图谱：整页一张科技树，详情在浮层里，浮层里也全是节点图。
#
# 为什么不再有列表：列表只能回答「有哪些」，回答不了「怎么连」；知识点之间
# 的先后才是这一页要看的东西。按名字找点，缩放拖一下图比翻列表快。
#
#   点图上的节点   → 打开 节点详情，「带 code」进地址，浮层的「载入」拉详情
#   邻域图         → 从主图截出：直接前置 → 当前 → 直接后续；点前置或后续，
#                    浮层就换成那个点
#   条目 / 接续 / 挂着的词 → 各一张节点图，卡片排开，超过 6 个排成网格
#
# 后端不用改：邻域从主图（state.graph）截，条目这些照旧走 lists，节点图
# 在共享状态里找不到就去 lists 里找。

界面 自定义 知识图谱 载入 node_detail
  分组 顶栏 横排 顶栏
    动作 node_list 远程 进入时 刷新
    显示 code 当前
    显示 label 名称
  结束

  节点图 kg 绑 graph 选中 sel 点开 节点详情 带 code 图例 占满 方向 纵向

  浮层 节点详情 宽 760px
    分组 抬头 横排 间距 12px
      显示 sel.label 知识点
      显示 sel.desc 学之前要先会
      显示 sel.badge 往下解锁
    结束

    文案 直接前置 → 当前 → 直接后续
    节点图 邻域 绑 graph 围绕 sel 选中 sel 点开 节点详情 带 code 高 320px

    文案 当 lists.items&&lists.items.length 这个功能下的说法
    节点图 条目 绑 items 标题 label 说明 form 高 160px 当 lists.items&&lists.items.length

    文案 当 lists.forms&&lists.forms.length 接在这个形式后面的
    节点图 接续 绑 forms 标题 label 说明 point 高 160px 当 lists.forms&&lists.forms.length

    文案 当 lists.point_words&&lists.point_words.length 挂着的词
    节点图 词 绑 point_words 标题 kanji,kana 说明 kana,meaning 高 260px 当 lists.point_words&&lists.point_words.length

    分组 底栏 横排 底栏
      动作 close 次要 关闭 收起
    结束
  结束
结束
'''


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
        raise SystemExit('这几个文件有未提交改动（可能另一个会话正在改），不动：\n' + st)

    # 新词不能跟现有词汇撞
    sys.path.insert(0, P)
    import tools.ui as U0
    words = set(U0.KEYED_MODIFIERS) | set(U0.FLAG_MODIFIERS) | set(U0.LINE_KEYWORDS) | set(U0.BLOCK_RULES)
    clash = [w for w in ['围绕', '标题', '说明'] if w in words]
    if clash:
        raise SystemExit('新词已被占用：%s' % clash)
    for mod in [k for k in list(sys.modules) if k.startswith('tools')]:
        del sys.modules[mod]

    # ------------------------------------------------ ui.py
    p = P + '/tools/ui.py'
    L = open(p, encoding='utf-8').read().split('\n')
    i = [k for k, l in enumerate(L) if l.startswith('SCREEN_ROLES =')]
    if len(i) != 1: abort('SCREEN_ROLES 命中 %d' % len(i))
    L[i[0]:i[0]] = ['# 节点图：「围绕 sel」只画选中点和它的直接前置、直接后续（详情里的邻域图）；',
                    '# 「标题 字段」「说明 字段」指定卡片拿哪个字段当名字和说明行，可写几个、逗号隔开，',
                    '# 取第一个有值的——条目、词这些数据没有 label/sub 字段也能画成卡片。',
                    'KEYED_MODIFIERS = KEYED_MODIFIERS | {"围绕", "标题", "说明"}', '']
    i = [k for k, l in enumerate(L) if l.strip().startswith('required: Optional[bool]')]
    if len(i) != 1: abort('Node.required 命中 %d' % len(i))
    L[i[0]:i[0]] = ['    around: str = ""             # 节点图「围绕 sel」',
                    '    title_f: str = ""            # 节点图「标题 kanji,kana」',
                    '    sub_f: str = ""              # 节点图「说明 kana,meaning」']
    i = [k for k, l in enumerate(L) if l.startswith('def _apply_keyed(')]
    if len(i) != 1: abort('_apply_keyed 命中 %d' % len(i))
    L[i[0] + 1:i[0] + 1] = ['    if "围绕" in keyed:', '        node.around = keyed["围绕"]',
                            '    if "标题" in keyed:', '        node.title_f = keyed["标题"]',
                            '    if "说明" in keyed:', '        node.sub_f = keyed["说明"]']
    s = '\n'.join(L)
    # 「带」配「点开」也算数：节点图点开浮层时把 code 带进地址
    s = sub1(s, 'getattr(node, "carry", "") and not getattr(node, "goto", "")',
             'getattr(node, "carry", "") and not getattr(node, "goto", "") and not getattr(node, "popup", "")',
             'check_loaders 的带/切到判断')
    open(p, 'w', encoding='utf-8').write(s)
    print('ui: 围绕 / 标题 / 说明，带+点开')

    # ------------------------------------------------ graph.j2
    p = T + '/graph.j2'
    s = open(p, encoding='utf-8').read()
    s = sub1(s, '<%- set dir = n.direction or "纵向" -%>\n',
             '<%- set dir = n.direction or "纵向" -%>\n'
             '<%- set opts = "{ around: \'" ~ n.around ~ "\', title: \'" ~ n.title_f ~ "\', sub: \'" ~ n.sub_f ~ "\' }" -%>\n',
             'graph.j2 set dir')
    old_key = (":key=\"graphOf('<%= path %>', '<%= dir %>').nodes.length + ':' + "
               "graphOf('<%= path %>', '<%= dir %>').edges.length\"")
    s = sub1(s, old_key, ":key=\"graphOf('<%= path %>', '<%= dir %>', <%= opts %>).vkey\"", ':key')
    n = s.count("graphOf('<%= path %>', '<%= dir %>')")
    if n != 3: abort('graph.j2 其余 graphOf 调用 %d 处（应为 3）' % n)
    s = s.replace("graphOf('<%= path %>', '<%= dir %>')", "graphOf('<%= path %>', '<%= dir %>', <%= opts %>)")
    s = sub1(s, "@node-click=\"onGraphNode('<%= n.selects %>', $event, '<%= n.popup %>')\"",
             "@node-click=\"onGraphNode('<%= n.selects %>', $event, '<%= n.popup %>', '<%= n.carry %>')\"",
             'node-click')
    s = s.replace('    点节点：原样节点对象写进「选中」路径，有「点开」就弹浮层；点空白处清掉。\n',
                  '    点节点：原样节点对象写进「选中」路径，有「点开」就弹浮层；点空白处清掉。\n'
                  '    「带 code」：点开时把节点 id 以 code 放进地址，浮层的「载入」据此拉详情。\n'
                  '    「围绕 sel」：只画选中点和它的直接前置、直接后续，当前点高亮。\n'
                  '    「标题 / 说明 字段」：卡片的名字和说明行取哪个字段（逗号隔开取第一个有值的）。\n'
                  '    共享状态里找不到「绑」的路径时，去后端返回的 lists 里找。\n'
                  '    没有任何先后关系的一组东西，多于 6 个时排成网格。\n')
    open(p, 'w', encoding='utf-8').write(s)
    print('graph.j2: 传 opts / 带')

    # ------------------------------------------------ app.js.j2
    p = T + '/app.js.j2'
    s = open(p, encoding='utf-8').read()
    s = sub1(s, '    function graphOf(path, dir) {\n      const raw0 = _graphGet(shared.value, path);\n',
             '    function graphOf(path, dir, opts) {\n'
             '      opts = opts || {};\n'
             '      // 共享状态里没有就去 lists 里找：详情里的条目、词这些是后端按表格行给的\n'
             '      let raw0 = _graphGet(shared.value, path);\n'
             "      if (raw0 == null && typeof lists !== 'undefined') raw0 = (lists.value || {})[path];\n",
             'graphOf 开头')
    s = sub1(s, "      const raw = Array.isArray(raw0) ? { nodes: raw0 } : (raw0 || {});\n"
                "      const key = (dir || '') + '|' + JSON.stringify(raw);\n",
             "      let raw = Array.isArray(raw0) ? { nodes: raw0 } : (raw0 || {});\n"
             "      const center0 = opts.around ? _graphGet(shared.value, opts.around) : null;\n"
             "      const cid = center0 ? String(center0.id != null ? center0.id : center0.label) : '';\n"
             "      const key = (dir || '') + '|' + JSON.stringify(opts) + '|' + cid + '|' + JSON.stringify(raw);\n",
             'raw/key')
    s = sub1(s, "      const src = (raw.nodes || []).map((n, i) => n.id != null ? n : Object.assign({}, n, { id: n.label != null ? n.label : 'n' + i }));\n",
             "      // 「标题 / 说明」：卡片的名字和说明行取哪个字段，逗号隔开取第一个有值的\n"
             "      const pick = (n, spec) => { for (const f of String(spec || '').split(',').filter(Boolean)) { if (n[f] != null && n[f] !== '') return String(n[f]); } return null; };\n"
             "      let src = (raw.nodes || []).map((n, i) => {\n"
             "        let m = n;\n"
             "        const t = opts.title ? pick(n, opts.title) : null;\n"
             "        if (t != null || opts.sub) {\n"
             "          m = Object.assign({}, n);\n"
             "          if (t != null) m.label = t;\n"
             "          if (opts.sub) {\n"
             "            const sv = String(opts.sub).split(',').filter(Boolean).map(f => n[f])\n"
             "              .filter(v => v != null && v !== '' && String(v) !== t).join('\\u3000');\n"
             "            if (sv) m.sub = sv;\n"
             "          }\n"
             "        }\n"
             "        // 没给 id 的（条目、词这些）按位置编一个，名字可能重复\n"
             "        return m.id != null ? m : Object.assign({}, m, { id: 'n' + i + ':' + (m.label != null ? m.label : '') });\n"
             "      });\n",
             'src')
    s = sub1(s, "      // 步数：最长前置链。环在导入时已被拒掉，seen 只防死循环\n",
             "      // 「围绕 sel」：只留选中点和它的直接前置、直接后续，只留跟它相连的边——\n"
             "      // 详情里的邻域图。层就成了 前置 / 当前 / 后续 三层\n"
             "      if (opts.around) {\n"
             "        if (!cid || !(cid in pre)) src = [];\n"
             "        else {\n"
             "          const ps = pre[cid].slice(), cs = src.filter(n => pre[K(n)].includes(cid)).map(K);\n"
             "          const keep = new Set([cid, ...ps, ...cs]);\n"
             "          src = src.filter(n => keep.has(K(n)));\n"
             "          Object.keys(pre).forEach(k => { pre[k] = keep.has(k) ? pre[k].filter(q => keep.has(q) && (k === cid || q === cid)) : []; });\n"
             "          Object.keys(con).forEach(k => { con[k] = []; });\n"
             "          raw = Object.assign({}, raw, { layerNames: ps.length ? { 0: '直接前置', 1: '当前', 2: '直接后续' } : { 0: '当前', 1: '直接后续' } });\n"
             "        }\n"
             "      }\n"
             "      // 步数：最长前置链。环在导入时已被拒掉，seen 只防死循环\n",
             '围绕')
    s = sub1(s, "      } else if (src.length && typeof dagre !== 'undefined') {\n",
             "      } else if (src.length > 6 && src.every(n => !pre[K(n)].length)) {\n"
             "        // 一组并列的东西（没有任何先后），多于 6 个排成网格，不拉成一长排\n"
             "        const C = 6;\n"
             "        src.forEach((n, i) => { pos[K(n)] = { x: (i % C) * (BW + NODESEP), y: Math.floor(i / C) * (BH + NODESEP) }; });\n"
             "      } else if (src.length && typeof dagre !== 'undefined') {\n",
             '网格')
    s = sub1(s, "          class: [_kgState[n.state], n.class].filter(Boolean).join(' '),\n",
             "          class: [_kgState[n.state], n.class, opts.around && K(n) === cid ? 'kg-center' : ''].filter(Boolean).join(' '),\n",
             '当前点高亮')
    s = sub1(s, "      const out = { nodes, edges, legend };\n",
             "      // vkey：VueFlow 的 :key。数据或当前点一换就重建、重新取景\n"
             "      const out = { nodes, edges, legend, vkey: nodes.length + ':' + edges.length + ':' + cid };\n",
             'vkey')
    s = sub1(s, "    function onGraphNode(path, ev, popup) {\n", "    function onGraphNode(path, ev, popup, carry) {\n", 'onGraphNode 签名')
    s = sub1(s, "      if (popup && ev && ev.node) openOverlay.value = popup;\n",
             "      // 「带 code」：走 showOverlay，参数进地址，浮层的「载入」据此把这个点的详情\n"
             "      // 拉回来。先清空表单：上一个点的前置、条目不能还挂着\n"
             "      if (popup && ev && ev.node) {\n"
             "        if (carry && typeof showOverlay === 'function') {\n"
             "          reset(current.value.name);\n"
             "          showOverlay(popup, { [carry]: ev.node.id });\n"
             "        } else openOverlay.value = popup;\n"
             "      }\n",
             'onGraphNode 点开')
    open(p, 'w', encoding='utf-8').write(s)
    print('app: lists 回退 / 围绕 / 标题说明 / 网格 / 带')

    # ------------------------------------------------ style.css.j2
    p = T + '/style.css.j2'
    s = open(p, encoding='utf-8').read()
    if '.kg-center' not in s:
        s = s.rstrip('\n') + '''

/* 邻域图里的当前点 */
.vue-flow__node.kg-center .kg-node { box-shadow:0 0 0 3px rgba(74,122,140,.45); }
'''
        open(p, 'w', encoding='utf-8').write(s)

    # ------------------------------------------------ kg/ui/node.ui
    open(P + '/kg/ui/node.ui', 'w', encoding='utf-8').write(NODE_UI)
    print('node.ui: 整页节点图')

    # ================================================ 验证
    for mod in [k for k in list(sys.modules) if k.startswith('tools')]:
        del sys.modules[mod]
    from tools.ui import compile_ui, parse
    ok = True
    g = [x for x in parse(NODE_UI)[0].walk() if x.kind == '节点图']
    for x in g:
        print('  解析', x.name, '| bind', x.bind, '| 围绕', x.around, '| 标题', x.title_f, '| 说明', x.sub_f,
              '| 带', x.carry, '| 点开', x.popup, '| 当', x.when, '| label', repr(x.label))
    ok &= len(g) == 5 and all(x.label in ('', x.name) for x in g)
    ok &= g[1].around == 'sel' and g[4].title_f == 'kanji,kana' and g[0].carry == 'code'
    r = compile_ui(NODE_UI, backend='vue',
                   options={'title': '知识图谱', 'endpoints': {'node_list': '/node/list', 'node_detail': '/node/one', 'close': '/x'}})
    iss = [str(i) for i in r['issues']]
    print('ISSUES:', iss or '无')
    ok &= not any('带' in m or 'carry' in m or 'popup' in m for m in iss)
    js = r['result']['files']['app.js']
    os.makedirs('/tmp/g', exist_ok=True)
    open('/tmp/g/pg.js', 'w', encoding='utf-8').write(js)
    rc = subprocess.run(['node', '--check', '/tmp/g/pg.js'], capture_output=True, text=True)
    print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:300])
    ok &= rc.returncode == 0
    tpl = re.search(r'template: `(.*)`', js, re.S).group(1)
    for tag in ['VueFlow', 'template', 'div']:
        o = len(re.findall(r'<%s[\s>]' % tag, tpl)); cc = tpl.count('</%s>' % tag)
        ok &= o == cc
        print('标签 %-8s 开 %d 闭 %d' % (tag, o, cc))
    print('列表已去掉:', '<table' not in tpl)
    ok &= '<table' not in tpl

    seg = re.search(r'(function _graphGet.*?function onGraphNode\(path, ev, popup, carry\) \{.*?\n    \})', js, re.S).group(1)
    graph = {'nodes': [{'id': k, 'label': k.upper(), 'state': 'done' if k in 'ab' else 'open'} for k in 'abcdex'],
             'edges': [{'from': 'a', 'to': 'c'}, {'from': 'b', 'to': 'c'}, {'from': 'c', 'to': 'd'},
                       {'from': 'c', 'to': 'e'}, {'from': 'x', 'to': 'd'}, {'from': 'a', 'to': 'b', 'kind': '对照'}]}
    lists = {'items': [{'label': '〜たら', 'form': 'た形'}, {'label': '〜ば', 'form': '条件形'}],
             'point_words': [{'kanji': '', 'kana': 'たべる%d' % i, 'meaning': '吃'} for i in range(14)]}
    test = ("globalThis.dagre = require('/tmp/g/dagre.js');\n"
            "const shared = { value: { graph: " + json.dumps(graph) + ", sel: { id: 'c', label: 'C' } } };\n"
            "const lists = { value: " + json.dumps(lists, ensure_ascii=False) + " };\n"
            "const calls = []; function showOverlay(n, p) { calls.push(['show', n, p]); } function reset(n) { calls.push(['reset', n]); }\n"
            "const current = { value: { name: '知识图谱' } }; const openOverlay = { value: null };\n"
            + seg + r'''
const nb = graphOf('graph', '纵向', { around: 'sel', title: '', sub: '' });
console.log('NB nodes', nb.nodes.filter(v => v.type === 'kg').map(v => v.id + (v.class.includes('kg-center') ? '*' : '')).sort().join(','),
  '| edges', nb.edges.map(e => e.source + '>' + e.target).sort().join(','),
  '| layers', nb.nodes.filter(v => v.type === 'kglayer').map(v => v.data.text).join('/'));
shared.value.sel = { id: 'a', label: 'A' };
const nb2 = graphOf('graph', '纵向', { around: 'sel', title: '', sub: '' });
console.log('NB2 nodes', nb2.nodes.filter(v => v.type === 'kg').map(v => v.id).sort().join(','),
  '| layers', nb2.nodes.filter(v => v.type === 'kglayer').map(v => v.data.text).join('/'));
shared.value.sel = null;
console.log('NB0', graphOf('graph', '纵向', { around: 'sel' }).nodes.length);
const it = graphOf('items', '纵向', { title: 'label', sub: 'form' });
console.log('IT', it.nodes.map(v => v.label + '/' + v.data.__view.sub).join(' '));
const w = graphOf('point_words', '纵向', { title: 'kanji,kana', sub: 'kana,meaning' });
const ws = w.nodes.filter(v => v.type === 'kg');
console.log('W', ws.length, 'rows', new Set(ws.map(v => v.position.y)).size, 'first', ws[0].label + '/' + ws[0].data.__view.sub);
onGraphNode('sel', { node: { id: 'd', type: 'kg', data: { id: 'd', label: 'D', __view: {} } } }, '节点详情', 'code');
console.log('CLICK', JSON.stringify(calls), 'sel', shared.value.sel.id, '__view' in shared.value.sel);
''')
    open('/tmp/g/pg_logic.js', 'w', encoding='utf-8').write(test)
    rc = subprocess.run(['node', '/tmp/g/pg_logic.js'], capture_output=True, text=True)
    out = rc.stdout.strip() or rc.stderr[:800]
    print(out)
    ok &= rc.returncode == 0
    ok &= 'NB nodes a,b,c*,d,e' in out and 'edges a>c,b>c,c>d,c>e' in out and '直接前置/当前/直接后续' in out
    ok &= 'NB2 nodes a,c' in out and 'layers 当前/直接后续' in out and 'NB0 0' in out
    ok &= 'IT 〜たら/た形 〜ば/条件形' in out
    ok &= 'W 14 rows 3 first たべる0/吃' in out
    ok &= '["reset","知识图谱"],["show","节点详情",{"code":"d"}]' in out and 'sel d false' in out

    print('全部通过:', ok)
    if not ok:
        abort('验证没过')
    git('add', '--', *FILES)
    rc, out = git('commit', '-m',
                  '知识图谱页整页改成节点图；节点图补 围绕 / 标题 / 说明 / 带\n\n'
                  '- node.ui：去掉左边的知识点列表，整页一张科技树；浮层里前置/后续换成邻域图，'
                  '条目、接续、挂着的词各一张节点图\n'
                  '- 「围绕 sel」：只画选中点和直接前置、直接后续，当前点高亮，层名 直接前置/当前/直接后续\n'
                  '- 「标题 / 说明 字段」：卡片名字和说明行取哪个字段，逗号隔开取第一个有值的\n'
                  '- 共享状态里找不到就去 lists 找；没有先后的一组多于 6 个排成网格\n'
                  '- 点节点「带 code」：走 showOverlay 把参数放进地址，浮层的「载入」据此拉详情。'
                  '此前点图上的节点只开浮层不带参数，详情不会载入\n'
                  '- 后端不用改')
    print('commit:', rc, out.splitlines()[:1])


if __name__ == '__main__':
    main()
