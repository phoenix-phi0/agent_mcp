import sys, os, re, subprocess
sys.path.insert(0, '/home/ysc/mcp')
from tools.ui import compile_ui
os.makedirs('/tmp/g', exist_ok=True)

A = '''界面 自定义 图测
  分组 图区 竖排
    节点图 deps 绑 graph 选中 sel 高 420px 方向 纵向
    动作 详情 次要 当 shared.sel 查看
    显示 sel.label
  结束
结束
'''
r = compile_ui(A, backend='vue', options={'title': '图测'})
print('[节点图] ISSUES:', [str(i) for i in r['issues']] or '无')
js = r['result']['files']['app.js']
html = r['result']['files']['index.html']
open('/tmp/g/a.js', 'w', encoding='utf-8').write(js)
print('[节点图] <VueFlow', '<VueFlow' in js,
      '| node-click', 'node-click' in js,
      '| graphOf', 'function graphOf' in js,
      '| 注册', 'VueFlowCore.VueFlow' in js,
      '| CDN', 'vue-flow-core.iife.js' in html and 'dagre.min.js' in html)
m = re.search(r'const shared = ref\((.*?)\);', js)
print('[节点图] shared:', m.group(1) if m else '(无)')

B = '''界面 自定义 图片页
  分组 g 竖排
    图 logo 绑 logo_url 高 80px 标志
  结束
结束
'''
try:
    r2 = compile_ui(B, backend='vue', options={'title': '图片页'})
    js2 = r2['result']['files']['app.js']
    html2 = r2['result']['files']['index.html']
    open('/tmp/g/b.js', 'w', encoding='utf-8').write(js2)
    print('[静态图] 误加载 CDN', 'vue-flow-core' in html2,
          '| 误生成 graphOf', 'function graphOf' in js2,
          '| <VueFlow', '<VueFlow' in js2)
except Exception as e:
    print('[静态图] 编译报错:', type(e).__name__, e)

for f in ['/tmp/g/a.js', '/tmp/g/b.js']:
    if os.path.exists(f):
        rc = subprocess.run(['node', '--check', f], capture_output=True, text=True)
        print('node --check', f, '->', 'OK' if rc.returncode == 0 else rc.stderr.strip()[:300])
