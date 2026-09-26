import shutil, os
P = '/home/ysc/mcp'
os.makedirs('/tmp/bak6', exist_ok=True)
for f in ['tools/ui.py', 'templates/frontend/graph.j2', 'templates/frontend/app.js.j2']:
    shutil.copy(P + '/' + f, '/tmp/bak6/' + f.replace('/', '_'))

# ------------------------------------------------------------------ ui.py
p = P + '/tools/ui.py'
L = open(p, encoding='utf-8').read().split('\n')
s = '\n'.join(L)

# 1. 带参修饰「点开」
if 'KEYED_MODIFIERS | {"点开"}' not in s:
    i = [k for k, l in enumerate(L) if l.startswith('SCREEN_ROLES =')]
    assert len(i) == 1, 'SCREEN_ROLES 命中 %d' % len(i)
    L[i[0]:i[0]] = ['# 节点图「点开 <浮层>」：点中节点就直接弹出这个浮层，一步看详情。',
                    'KEYED_MODIFIERS = KEYED_MODIFIERS | {"点开"}', '']
    print('ui 1: 加「点开」修饰')

# 2. Node 字段
if not any(l.strip().startswith('popup: str') for l in L):
    i = [k for k, l in enumerate(L) if l.strip().startswith('required: Optional[bool]')]
    assert len(i) == 1, 'Node.required 命中 %d' % len(i)
    L.insert(i[0], '    popup: str = ""              # 「点开 节点详情」：点中节点时弹出的浮层')
    print('ui 2: Node 加 popup')

# 3. _apply_keyed
if not any('node.popup = keyed' in l for l in L):
    i = [k for k, l in enumerate(L) if l.startswith('def _apply_keyed(')]
    assert len(i) == 1, '_apply_keyed 命中 %d' % len(i)
    L[i[0] + 1:i[0] + 1] = ['    if "点开" in keyed:', '        node.popup = keyed["点开"]']
    print('ui 3: _apply_keyed 解析「点开」')

# 4. validate：「点开」指向的浮层要在同一界面里
if 'code="unknown_popup"' not in '\n'.join(L):
    v = [k for k, l in enumerate(L) if l.startswith('def validate(')]
    assert len(v) == 1, 'validate 命中 %d' % len(v)
    end = next(t for t in range(v[0] + 1, len(L)) if L[t].startswith('def '))
    anchor = [t for t in range(v[0], end) if L[t].strip() == 'issues.extend(_check_state_paths(screens))']
    if not anchor:
        anchor = [t for t in range(v[0], end) if L[t].strip() == 'return issues']
    assert anchor, 'validate 里找不到插入点'
    L[anchor[0]:anchor[0]] = [
        '    # 节点图「点开」指向的浮层要在同一界面里。写错了不报错、点节点也不弹，',
        '    # 跟「打开」「切到」写错是同一类静默失败，所以一样拦一道。',
        '    for screen in screens:',
        '        here = {o.name for o in screen.overlays()}',
        '        for n in screen.walk():',
        '            if n.kind == "节点图" and getattr(n, "popup", "") and n.popup not in here:',
        '                issues.append(Issue(',
        '                    f"节点图「{n.name}」要点开浮层「{n.popup}」，"',
        '                    f"但界面「{screen.name}」里没有这个浮层",',
        '                    line=n.line, code="unknown_popup"))',
        '',
    ]
    print('ui 4: validate 加检查')
open(p, 'w', encoding='utf-8').write('\n'.join(L))

# ------------------------------------------------------------------ graph.j2
p = P + '/templates/frontend/graph.j2'
s = open(p, encoding='utf-8').read()
old = "@node-click=\"onGraphNode('<%= n.selects %>', $event)\""
new = "@node-click=\"onGraphNode('<%= n.selects %>', $event, '<%= n.popup %>')\""
if new not in s:
    assert s.count(old) == 1, 'graph.j2 node-click 命中 %d' % s.count(old)
    s = s.replace(old, new)
    s = s.replace('    其余字段原样挂在 data 上，点节点时整个对象写进「选中」路径。',
                  '    其余字段原样挂在 data 上，点节点时整个对象写进「选中」路径。\n'
                  '    「点开 <浮层>」让点节点同时弹出那个浮层，一步看详情。')
    open(p, 'w', encoding='utf-8').write(s)
    print('graph.j2: node-click 带上 popup')

# ------------------------------------------------------------------ app.js.j2
p = P + '/templates/frontend/app.js.j2'
s = open(p, encoding='utf-8').read()
old = "    function onGraphNode(path, ev) { if (path) _graphPut(shared.value, path, ev && ev.node ? ev.node.data : null); }"
new = ("    function onGraphNode(path, ev, popup) {\n"
       "      if (path) _graphPut(shared.value, path, ev && ev.node ? ev.node.data : null);\n"
       "<% if has_overlays %>\n"
       "      // 「点开 浮层」：点中节点就直接弹详情，省掉「先选中、再点查看」那一步。\n"
       "      // 点空白处（ev 为 null）不弹。\n"
       "      if (popup && ev && ev.node) openOverlay.value = popup;\n"
       "<% endif %>\n"
       "    }")
if 'function onGraphNode(path, ev, popup)' not in s:
    assert s.count(old) == 1, 'app onGraphNode 命中 %d' % s.count(old)
    s = s.replace(old, new)
    open(p, 'w', encoding='utf-8').write(s)
    print('app: onGraphNode 支持点开')
print('完成')
