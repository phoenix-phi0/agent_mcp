import subprocess

def run(*a):
    r = subprocess.run(list(a), cwd='/home/ysc/mcp', capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print('$ ' + ' '.join(a))
    if out:
        print(out)
    return r.returncode

files = [
    'tools/ui.py',
    'templates/frontend/graph.j2',
    'templates/frontend/layout.j2',
    'templates/frontend/app.js.j2',
    'templates/frontend/index.html.j2',
    'templates/frontend/style.css.j2',
]

print('=== 提交前状态 ===')
run('git', 'status', '--short')
run('git', 'diff', '--stat', '--', *files)

# 只加这六个文件，其余改动（如果有）不碰
run('git', 'add', '--', *files)
print('=== 暂存区 ===')
run('git', 'diff', '--cached', '--stat')

msg = (
    '接回节点图：有向无环图（Vue Flow + dagre）\n'
    '\n'
    '- ui.py：注册「节点图」行节点；选中/方向两个修饰；_shared_defaults 给节点图开槽，'
    '选中路径直接赋 None（同界面有「显示 sel.label」时 setdefault 会让「当 shared.sel」恒真）；'
    'has_graphs 只认节点图\n'
    '- ui.py：删掉把「图」当节点图的旧分支——它把静态图片的绑定路径建成 {nodes, edges}\n'
    '- graph.j2：节点图宏（新文件）\n'
    '- layout.j2：import 节点图并加分派分支\n'
    '- app.js.j2：graphOf（dagre 布局、按数据缓存）、onGraphNode（点击写入选中路径）、'
    '导出、VueFlow 组件注册\n'
    '- index.html.j2：有节点图才插 Vue Flow 和 dagre 的 CDN，地址可用 graph_js/graph_css/dagre_js 覆盖\n'
    '- style.css.j2：.graph-wrap\n'
    '\n'
    '不叫「图」：「图」已经是静态图片。'
)
rc = run('git', 'commit', '-m', msg)
print('=== 结果 ===')
run('git', 'log', '--oneline', '-3')
run('git', 'status', '--short')
print('commit 返回码:', rc)
