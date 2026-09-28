import subprocess, os, re, sys
P = '/home/ysc/mcp'
T = P + '/templates/frontend'
FILES = ['tools/ui.py', 'templates/frontend/widgets.j2', 'templates/frontend/app.js.j2', 'kg/ui/node.ui']


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

    sys.path.insert(0, P)
    import tools.ui as U0
    if '隐藏' in (set(U0.KEYED_MODIFIERS) | set(U0.FLAG_MODIFIERS) | set(U0.LINE_KEYWORDS) | set(U0.BLOCK_RULES)):
        raise SystemExit('「隐藏」已被占用')
    for mod in [k for k in list(sys.modules) if k.startswith('tools')]:
        del sys.modules[mod]

    # ui.py：「隐藏」旗标
    p = P + '/tools/ui.py'
    L = open(p, encoding='utf-8').read().split('\n')
    i = [k for k, l in enumerate(L) if l.startswith('SCREEN_ROLES =')]
    if len(i) != 1: abort('SCREEN_ROLES 命中 %d' % len(i))
    L[i[0]:i[0]] = ['# 动作「隐藏」：不画按钮，别的照旧——配「进入时」就是进页面自动拉数据、',
                    '# 却不在界面上摆一个没人点的「刷新」。',
                    'FLAG_MODIFIERS = FLAG_MODIFIERS | {"隐藏"}', '']
    open(p, 'w', encoding='utf-8').write('\n'.join(L))
    print('ui: 隐藏')

    # widgets.j2：动作宏整个包一层
    p = T + '/widgets.j2'
    s = open(p, encoding='utf-8').read()
    m = re.search(r'(<%- macro 动作\(a\) -%>\n)(.*?)(<%- endmacro -%>)', s, re.S)
    if not m: abort('widgets.j2 找不到动作宏')
    if 'a.has("隐藏")' not in m.group(2):
        s = s[:m.start()] + m.group(1) + '<%- if not a.has("隐藏") -%>\n' + m.group(2) + '<%- endif -%>\n' + m.group(3) + s[m.end():]
    open(p, 'w', encoding='utf-8').write(s)
    print('widgets: 隐藏的动作不画按钮')

    # app.js.j2：只有一个界面时不出导航
    p = T + '/app.js.j2'
    s = open(p, encoding='utf-8').read()
    s = sub1(s, '<% elif not has_goto %>\n    <nav>',
             '<% elif not has_goto and screens|length > 1 %>\n    <nav>', 'nav 条件')
    open(p, 'w', encoding='utf-8').write(s)
    print('app: 单界面不出导航')

    # node.ui：去掉顶栏
    p = P + '/kg/ui/node.ui'
    s = open(p, encoding='utf-8').read()
    s = sub1(s, '''  分组 顶栏 横排 顶栏
    动作 node_list 远程 进入时 刷新
    显示 code 当前
    显示 label 名称
  结束
''', '''  # 进页面自动拉图，不摆按钮。原来的顶栏还有「当前」「名称」两个显示，后端
  # 从没往共享状态里写 code / label，一直是空的，一起去掉，图从最上面开始
  动作 node_list 远程 进入时 隐藏 刷新
''', '顶栏')
    open(p, 'w', encoding='utf-8').write(s)
    print('node.ui: 去掉顶栏')

    # 验证
    for mod in [k for k in list(sys.modules) if k.startswith('tools')]:
        del sys.modules[mod]
    from tools.ui import compile_ui
    ok = True
    r = compile_ui(s, backend='vue', options={'title': '知识图谱', 'endpoints': {'node_list': '/a', 'node_detail': '/b', 'close': '/c'}})
    iss = [str(i) for i in r['issues']]
    print('ISSUES:', iss or '无')
    js = r['result']['files']['app.js']
    tpl = re.search(r'template: `(.*)`', js, re.S).group(1)
    top = tpl.split('<VueFlow')[0]
    c = {'无导航': '<nav>' not in top, '无刷新按钮': '刷新' not in tpl, '无顶栏': 'bar-top' not in top,
         '进入时仍会跑 node_list': re.search(r'const enters = (\{.*?\});', js) is not None and 'node_list' in re.search(r'const enters = (\{.*?\});', js).group(1)}
    print(c)
    ok &= all(c.values())
    # 多界面、没用「切到」的页面还要有导航；没写「隐藏」的动作照常出按钮
    r2 = compile_ui('界面 自定义 甲\n  动作 a 次要 按钮甲\n结束\n界面 自定义 乙\n  文案 乙\n结束\n', backend='vue', options={'title': 't'})
    t2 = r2['result']['files']['app.js']
    c2 = {'多界面有导航': '<nav>' in t2, '普通动作有按钮': '按钮甲' in t2}
    print(c2)
    ok &= all(c2.values())
    os.makedirs('/tmp/g', exist_ok=True)
    open('/tmp/g/top.js', 'w', encoding='utf-8').write(js)
    ok &= subprocess.run(['node', '--check', '/tmp/g/top.js'], capture_output=True).returncode == 0
    for tag in ['div', 'template', 'section', 'form']:
        o = len(re.findall(r'<%s[\s>]' % tag, tpl)); cc = tpl.count('</%s>' % tag)
        ok &= o == cc
    print('全部通过:', ok)
    if not ok:
        abort('验证没过')
    git('add', '--', *FILES)
    rc, out = git('commit', '-m', '知识图谱页去掉顶上的导航和刷新按钮\n\n'
                  '- 引擎：只有一个界面时不生成切换导航\n'
                  '- 引擎：动作加「隐藏」旗标，不画按钮、别的照旧（配「进入时」即进页面自动拉数据）\n'
                  '- node.ui：顶栏整个去掉；「当前」「名称」两个显示一直是空的，一起去掉')
    print('commit:', rc, out.splitlines()[:1])


if __name__ == '__main__':
    main()
