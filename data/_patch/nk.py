import shutil, os
P = '/home/ysc/mcp'
os.makedirs('/tmp/bak7', exist_ok=True)
for f in ['tools/ui.py', 'templates/frontend/layout.j2', 'templates/frontend/style.css.j2']:
    shutil.copy(P + '/' + f, '/tmp/bak7/' + f.replace('/', '_'))

# ------------------------------------------------------------------ ui.py
# 列表写了「绑」就从共享路径读数据，这里给它开个空数组的槽。插在节点图块
# 之前：节点图会把「选中」路径强制设成 None，要让它最后执行才压得住。
p = P + '/tools/ui.py'
L = open(p, encoding='utf-8').read().split('\n')
if not any('n.kind == "列表" and n.bind' in l for l in L):
    i = [k for k, l in enumerate(L) if l.strip().startswith('# 节点图数据整块放共享状态')]
    assert len(i) == 1, '节点图块标记命中 %d' % len(i)
    L[i[0]:i[0]] = [
        '    # 列表写了「绑」就从共享路径读，不再用全局那一个 rows——一个界面可以有',
        '    # 多个列表，浮层里也能列出选中节点包含的东西（绑 sel.points）。',
        '    for s in screens:',
        '        for n in s.walk():',
        '            if n.kind == "列表" and n.bind:',
        '                _put_path(shared, n.bind, [])',
    ]
    open(p, 'w', encoding='utf-8').write('\n'.join(L))
    print('ui: 列表绑定开槽')

# ------------------------------------------------------------------ layout.j2
p = P + '/templates/frontend/layout.j2'
s = open(p, encoding='utf-8').read()
old = '<tr v-for="(row, i) in rows" :key="i">'
new = ('<tr v-for="(row, i) in <% if node.bind %>(getPath(shared, \'<%= node.bind %>\') || [])'
       '<% else %>rows<% endif %>" :key="i" :class="row.state ? \'row-\' + row.state : \'\'">')
if 'getPath(shared, \'<%= node.bind %>\')' not in s:
    assert s.count(old) == 1, 'layout 列表 v-for 命中 %d' % s.count(old)
    s = s.replace(old, new)
    open(p, 'w', encoding='utf-8').write(s)
    print('layout: 列表认「绑」')

# ------------------------------------------------------------------ style.css.j2
p = P + '/templates/frontend/style.css.j2'
s = open(p, encoding='utf-8').read()
if '.row-done' not in s:
    s = s.rstrip('\n') + '''

/* 列表行按 state 上色，跟节点图同一套状态：已掌握 / 可学 / 锁定 */
tr.row-done td { color:#4a7a8c; font-weight:600; }
tr.row-open td { color:var(--ink); }
tr.row-locked td { opacity:.55; }
.overlay-box table { margin:4px 0; }
'''
    open(p, 'w', encoding='utf-8').write(s)
    print('style: 行状态样式')
print('完成')
