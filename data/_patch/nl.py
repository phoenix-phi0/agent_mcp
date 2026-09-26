import sys, os, re, subprocess
sys.path.insert(0, '/home/ysc/mcp')
from tools.ui import compile_ui, parse, _shared_defaults
os.makedirs('/tmp/g', exist_ok=True)
ok = True

UI = '''界面 自定义 学习路径
  分组 图区 竖排 占满
    节点图 kg 绑 graph 选中 sel 点开 节点详情 高 640px 方向 纵向
  结束
  浮层 节点详情 宽 480px
    显示 sel.label
    显示 sel.desc 当 shared.sel&&shared.sel.desc
    列表 包含 绑 sel.points 当 shared.sel&&shared.sel.points&&shared.sel.points.length
      列 label 知识点
      列 state 状态
    结束
    动作 收起 次要 关闭 收起
  结束
结束
'''
scr = parse(UI)
lst = [n for n in scr[0].walk() if n.kind == '列表'][0]
print('解析 列表:', 'name=', lst.name, 'bind=', lst.bind, 'when=', lst.when)
ok &= lst.bind == 'sel.points' and lst.name == '包含'

sh = _shared_defaults(scr)
print('shared 初值:', sh)
ok &= sh.get('sel', 'x') is None     # 节点图的 None 压过列表开的槽

r = compile_ui(UI, backend='vue', options={'title': '学习路径'})
iss = [str(i) for i in r['issues']]
print('ISSUES:', iss or '无')
ok &= not iss
js = r['result']['files']['app.js']
open('/tmp/g/l.js', 'w', encoding='utf-8').write(js)
c1 = "(getPath(shared, 'sel.points') || [])" in js
c2 = "'row-' + row.state" in js
c3 = 'v-if="shared.sel&&shared.sel.points&&shared.sel.points.length"' in js
print('列表读 sel.points:', c1, '| 行状态 class:', c2, '| 空时隐藏:', c3)
ok &= c1 and c2 and c3
rc = subprocess.run(['node', '--check', '/tmp/g/l.js'], capture_output=True, text=True)
print('node --check:', 'OK' if rc.returncode == 0 else rc.stderr[:300])
ok &= rc.returncode == 0

# 不写「绑」的列表照旧读 rows
r2 = compile_ui('界面 列表 文章\n  列表 articles\n    列 title 标题\n  结束\n结束\n', backend='vue')
js2 = r2['result']['files']['app.js']
c4 = 'v-for="(row, i) in rows"' in js2
print('无绑定仍读 rows:', c4)
ok &= c4

# 独立路径的列表：shared 里要有空数组，页面不因 getPath 未定义而报错
r3 = compile_ui('界面 自定义 两表\n  列表 a 绑 left\n    列 x X\n  结束\n  列表 b 绑 right\n    列 y Y\n  结束\n结束\n', backend='vue')
js3 = r3['result']['files']['app.js']
m = re.search(r'const shared = ref\((.*?)\);', js3)
print('两个列表的 shared:', m.group(1) if m else '(无 shared)', '| getPath 已定义:', 'function getPath' in js3)
ok &= bool(m) and '"left": []' in m.group(1) and '"right": []' in m.group(1) and 'function getPath' in js3

print('全部通过:', ok)
if ok:
    files = ['tools/ui.py', 'templates/frontend/layout.j2', 'templates/frontend/style.css.j2']
    subprocess.run(['git', 'add', '--', *files], cwd='/home/ysc/mcp')
    msg = ('列表支持「绑」：从共享路径读数据\n\n'
           '- 列表写了「绑 路径」就读 shared 里那个数组，不写照旧读全局 rows\n'
           '- 一个界面可以有多个列表；浮层里能列出选中节点包含的知识点（绑 sel.points）\n'
           '- 行按 state 上色（done / open / locked），跟节点图同一套状态')
    c = subprocess.run(['git', 'commit', '-m', msg], cwd='/home/ysc/mcp', capture_output=True, text=True)
    print('commit:', c.returncode, (c.stdout + c.stderr).strip().splitlines()[:1])
else:
    print('有检查没过，不提交')
