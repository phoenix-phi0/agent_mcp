import shutil, sys
p = '/home/ysc/mcp/tools/ui.py'
shutil.copy(p, '/tmp/ui.py.bak4')
L = open(p, encoding='utf-8').read().split('\n')

# 删掉恢复回来的旧补丁：_shared_defaults 里把「图」当节点图的那个 elif 分支。
# 只删「elif n.kind == "图":」且下一行含 "nodes": [] 的那一处——那是节点图的
# 旧写法；如果「图」还有别的合法分支（比如静态图片自己的），不碰。
hits = [k for k, l in enumerate(L)
        if l.strip() == 'elif n.kind == "图":'
        and k + 1 < len(L) and '"nodes": []' in L[k + 1]]
print('旧分支位置:', [h + 1 for h in hits])
assert len(hits) <= 1, '命中多处，不自动删'
if hits:
    k = hits[0]
    base = len(L[k]) - len(L[k].lstrip())
    end = k + 1
    while end < len(L):
        line = L[end]
        if line.strip() == '':
            end += 1
            continue
        if len(line) - len(line.lstrip()) <= base:
            break
        end += 1
    # 回退掉结尾的空行，保持原有空行
    while end > k + 1 and L[end - 1].strip() == '':
        end -= 1
    print('删除的行:')
    for t in range(k, end):
        print('   %d: %s' % (t + 1, L[t]))
    del L[k:end]
    open(p, 'w', encoding='utf-8').write('\n'.join(L))
else:
    print('没有旧分支，不改')

print('剩余 kind==图 的行:', [(k + 1, L[k].strip()) for k in range(len(L)) if 'kind == "图"' in L[k]])

sys.path.insert(0, '/home/ysc/mcp')
from tools import ui
a = ui.parse('界面 自定义 T\n  分组 g 竖排\n    节点图 deps 绑 graph 选中 sel 高 420px 方向 纵向\n    显示 sel.label\n  结束\n结束\n')
print('验证 节点图 shared:', ui._shared_defaults(a))
b = ui.parse('界面 自定义 P\n  分组 g 竖排\n    图 logo 绑 logo_url 高 80px 标志\n  结束\n结束\n')
print('验证 静态图 shared:', ui._shared_defaults(b))
