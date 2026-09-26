import sys, os, re, subprocess
sys.path.insert(0, '/home/ysc/mcp')
from tools.ui import compile_ui, parse
os.makedirs('/tmp/g', exist_ok=True)
ok = True

UI = '''界面 自定义 学习路径
  分组 图区 竖排 占满
    节点图 kg 绑 graph 选中 sel 点开 节点详情 高 640px 方向 纵向
  结束
  浮层 节点详情 宽 420px
    显示 sel.label
    显示 sel.desc 当 shared.sel&&shared.sel.desc
    显示 sel.need 前置
    动作 收起 次要 关闭 收起
  结束
结束
'''
n = parse(UI)[0].children[0].children[0]
print('解析:', n.kind, 'selects=', n.selects, 'popup=', n.popup, 'size=', n.size, 'label=', repr(n.label))
ok &= (n.popup == '节点详情' and n.label in ('', 'kg'))

r = compile_ui(UI, backend='vue', options={'title': '学习路径'})
iss = [str(i) for i in r['issues']]
print('ISSUES:', iss or '无')
ok &= not iss
js = r['result']['files']['app.js']
open('/tmp/g/p.js', 'w', encoding='utf-8').write(js)
c1 = "onGraphNode('sel', $event, '节点详情')" in js
c2 = 'openOverlay.value = popup' in js
c3 = "v-if=\"shared.sel&&shared.sel.desc\"" in js
print('node-click 带 popup:', c1, '| 开浮层:', c2, '| 条件显示:', c3)
ok &= c1 and c2 and c3
rc = subprocess.run(['node', '--check', '/tmp/g/p.js'], capture_output=True, text=True)
print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:300])
ok &= rc.returncode == 0

# 写错浮层名要报出来
bad = UI.replace('点开 节点详情', '点开 不存在')
r2 = compile_ui(bad, backend='text')
msgs = [str(i) for i in r2['issues']]
print('写错浮层名:', msgs)
ok &= any('不存在' in m for m in msgs)

# 没有「点开」的节点图照旧能生成（popup 为空）
r3 = compile_ui('界面 自定义 T\n  分组 g 竖排\n    节点图 kg 绑 graph 选中 sel\n  结束\n结束\n', backend='vue')
js3 = r3['result']['files']['app.js']
print('无点开:', "onGraphNode('sel', $event, '')" in js3)
ok &= "onGraphNode('sel', $event, '')" in js3

print('全部通过:', ok)
if ok:
    files = ['tools/ui.py', 'templates/frontend/graph.j2', 'templates/frontend/app.js.j2']
    subprocess.run(['git', 'add', '--', *files], cwd='/home/ysc/mcp')
    msg = ('节点图：「点开 <浮层>」一步弹详情\n\n'
           '- 点中节点时写入「选中」路径并弹出指定浮层，不用再点一次「查看」\n'
           '- 点空白处只清选中、不弹\n'
           '- validate 检查「点开」的浮层是否在同一界面，写错报 unknown_popup')
    c = subprocess.run(['git', 'commit', '-m', msg], cwd='/home/ysc/mcp', capture_output=True, text=True)
    print('commit:', c.returncode, (c.stdout + c.stderr).strip().splitlines()[:2])
else:
    print('有检查没过，不提交')
