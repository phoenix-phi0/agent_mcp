import sys, re
P = '/home/ysc/mcp'
sys.path.insert(0, P)
from tools.ui import compile_ui
ui = open(P + '/kg/ui/node.ui', encoding='utf-8').read()
r = compile_ui(ui, backend='vue', options={'title': '知识图谱', 'endpoints': {'node_list': '/a', 'node_detail': '/b', 'close': '/c'}})
js = r['result']['files']['app.js']
css = r['result']['files'].get('style.css', '')
tpl = re.search(r'template: `(.*)`', js, re.S).group(1)
out = []
# 主界面 form 里的直接结构（去掉浮层）
main = tpl.split('<div class="overlay"')[0]
main = re.sub(r'<template #node-kg.*?</template>', '<template #node-kg>…</template>', main, flags=re.S)
main = re.sub(r'\s+', ' ', main)
out.append('== 主界面模板（压缩）\n' + main[:2500])
for sel in ['.graph-wrap', '.kg-legend', '.screen >', '.screen>', '.grow', '.copy', '.kg-node', '.kg-sub', '.kg-layer']:
    out.append('== css ' + sel + '\n' + '\n'.join(l for l in css.split('\n') if sel in l)[:800])
open(P + '/data/_patch/layout_probe.txt', 'w', encoding='utf-8').write('\n\n'.join(out))
print('ok')
