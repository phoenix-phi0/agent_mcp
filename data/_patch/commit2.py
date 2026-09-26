import subprocess

def run(*a):
    r = subprocess.run(list(a), cwd='/home/ysc/mcp', capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print('$ ' + ' '.join(a))
    if out:
        print(out)
    return r.returncode

files = [
    'templates/frontend/graph.j2',
    'templates/frontend/app.js.j2',
    'templates/frontend/style.css.j2',
]
run('git', 'diff', '--stat', '--', *files)
run('git', 'add', '--', *files)
msg = (
    '节点图：kg 样式（三态、角标、对照边）+ 横向连接点\n'
    '\n'
    '- 节点 state=done/open/locked（或 掌握/可学/锁定）→ 实心 / 粗描边 / 淡出，'
    '另可直接给 class、style\n'
    '- 节点 badge → 右上角角标（自定义节点模板 #node-kg）\n'
    '- 边 kind=对照 或 layout:false → 不参与 dagre 布局，从侧面连；对照边画虚线\n'
    '- 横向时连接点改为右出左进——之前 Vue Flow 默认上进下出，横向图的线全绕到上下边\n'
    '- 渲染尺寸与布局尺寸一致（默认 118×40，同 kg_svg），层距 104 与 kg_svg 相同\n'
    '- VueFlow 按节点数/边数取 :key，数据到了会重建并重新取景\n'
    '- 注册 Handle 组件'
)
rc = run('git', 'commit', '-m', msg)
run('git', 'log', '--oneline', '-3')
print('commit 返回码:', rc)
