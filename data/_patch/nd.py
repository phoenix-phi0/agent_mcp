import shutil, sys
p = '/home/ysc/mcp/tools/ui.py'
shutil.copy(p, '/tmp/ui.py.bak5')
L = open(p, encoding='utf-8').read().split('\n')

st = [k for k, l in enumerate(L) if l.startswith('def _shared_defaults(')]
assert len(st) == 1
end_fn = next(t for t in range(st[0] + 1, len(L)) if L[t].startswith('def '))

hits = [k for k in range(st[0], end_fn) if L[k].strip() == 'elif n.kind == "图":']
print('_shared_defaults 里「图」分支:', [h + 1 for h in hits])

removed = 0
for k in reversed(hits):
    base = len(L[k]) - len(L[k].lstrip())
    e = k + 1
    while e < end_fn and (L[e].strip() == '' or len(L[e]) - len(L[e].lstrip()) > base):
        e += 1
    while e > k + 1 and L[e - 1].strip() == '':
        e -= 1
    body = L[k:e]
    print('--- 分支内容 (%d-%d) ---' % (k + 1, e))
    for b in body:
        print('   ', b)
    if any('nodes' in b for b in body):
        del L[k:e]
        removed += 1
        print('   => 含 nodes，是节点图旧写法，已删除')
    else:
        print('   => 不含 nodes，保留')

if removed:
    open(p, 'w', encoding='utf-8').write('\n'.join(L))

sys.path.insert(0, '/home/ysc/mcp')
from tools import ui
a = ui.parse('界面 自定义 T\n  分组 g 竖排\n    节点图 deps 绑 graph 选中 sel 高 420px 方向 纵向\n    显示 sel.label\n  结束\n结束\n')
print('验证 节点图 shared:', ui._shared_defaults(a))
b = ui.parse('界面 自定义 P\n  分组 g 竖排\n    图 logo 绑 logo_url 高 80px 标志\n  结束\n结束\n')
print('验证 静态图 shared:', ui._shared_defaults(b))
