import subprocess, os, re, sys
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
FILES = ['templates/frontend/graph.j2', 'templates/frontend/style.css.j2']


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

    p = T + '/graph.j2'
    s = open(p, encoding='utf-8').read()
    # 「占满」：外框加 grow，在界面的纵向 flex 里吃掉剩下的高度。早先外框没接这个
    # 旗标，高度只有 min-height 240px，图压在顶上一窄条，下面一大片空白
    s = sub1(s, '<div class="graph-wrap"<%= 当(n) %><%= 尺寸(n) %>>',
             '<div class="graph-wrap<% if n.has("占满") %> grow<% endif %>"<%= 当(n) %><%= 尺寸(n) %>>', '外框')
    # 图例挪进外框、浮在左下角，不再单独占一行
    s = sub1(s, '</VueFlow>\n</div>\n<% if n.has("图例") %>\n'
                '<p class="kg-legend"<%= 当(n) %>>{{ graphOf(\'<%= path %>\', \'<%= dir %>\', <%= opts %>).legend }}</p>\n'
                '<% endif %>\n',
             '</VueFlow>\n<% if n.has("图例") %>\n'
             '<p class="kg-legend">{{ graphOf(\'<%= path %>\', \'<%= dir %>\', <%= opts %>).legend }}</p>\n'
             '<% endif %>\n</div>\n', '图例')
    open(p, 'w', encoding='utf-8').write(s)
    print('graph.j2: 占满 / 图例进框')

    p = T + '/style.css.j2'
    s = open(p, encoding='utf-8').read()
    if '.graph-wrap > .kg-legend' not in s:
        s = s.rstrip('\n') + '''

/* 图例浮在图的左下角，不单独占一行；不接鼠标，不挡拖动 */
.graph-wrap { position:relative; }
.graph-wrap > .kg-legend {
  position:absolute; left:10px; bottom:8px; margin:0; z-index:5; pointer-events:none;
  padding:3px 8px; border-radius:6px; background:rgba(250,249,247,.88);
}
'''
        open(p, 'w', encoding='utf-8').write(s)
    print('style: 图例浮层')

    # 验证
    sys.path.insert(0, P)
    from tools.ui import compile_ui
    ui = open(P + '/kg/ui/node.ui', encoding='utf-8').read()
    r = compile_ui(ui, backend='vue', options={'title': '知识图谱', 'endpoints': {'node_list': '/a', 'node_detail': '/b', 'close': '/c'}})
    js = r['result']['files']['app.js']
    tpl = re.search(r'template: `(.*)`', js, re.S).group(1)
    main_tpl = tpl.split('<div class="overlay"')[0]
    ok = True
    c1 = main_tpl.count('class="graph-wrap grow"') == 1
    c2 = re.search(r'</VueFlow>\s*<p class="kg-legend">.*?</p>\s*</div>', main_tpl, re.S) is not None
    c3 = tpl.count('class="graph-wrap"') == 4          # 浮层里 4 张图没写占满，不加 grow
    print('主图 grow:', c1, '| 图例在框里:', c2, '| 浮层里 4 张不加 grow:', c3)
    ok &= c1 and c2 and c3
    os.makedirs('/tmp/g', exist_ok=True)
    open('/tmp/g/lg.js', 'w', encoding='utf-8').write(js)
    rc = subprocess.run(['node', '--check', '/tmp/g/lg.js'], capture_output=True, text=True)
    print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:200])
    ok &= rc.returncode == 0
    for tag in ['VueFlow', 'template', 'div', 'p']:
        o = len(re.findall(r'<%s[\s>]' % tag, tpl)); cc = tpl.count('</%s>' % tag)
        ok &= o == cc
    print('全部通过:', ok)
    if not ok:
        abort('验证没过')
    git('add', '--', *FILES)
    rc, out = git('commit', '-m', '节点图：「占满」撑满剩余高度，图例浮在左下角\n\n'
                  '- 外框此前没接「占满」，高度只有 min-height 240px，图压在顶上一窄条\n'
                  '- 图例挪进外框，浮在左下角，不再单独占一行')
    print('commit:', rc, out.splitlines()[:1])


if __name__ == '__main__':
    main()
