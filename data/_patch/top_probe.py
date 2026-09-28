import sys, re, subprocess
P = '/home/ysc/mcp'
sys.path.insert(0, P)
from tools.ui import compile_ui
ui = open(P + '/kg/ui/node.ui', encoding='utf-8').read()
r = compile_ui(ui, backend='vue', options={'title': '知识图谱', 'endpoints': {'node_list': '/a', 'node_detail': '/b', 'close': '/c'}})
js = r['result']['files']['app.js']
tpl = re.search(r'template: `(.*)`', js, re.S).group(1)
top = tpl.split('<VueFlow')[0]
top = re.sub(r'\s+', ' ', top)
out = ['== 图上面的模板\n' + top[:1800]]
def sh(c):
    return subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True).stdout
out.append('== ui.py 里 进入时 / 隐藏\n' + sh("grep -n -e '进入时' -e '隐藏' -e 'on_enter' -e 'enter' tools/ui.py | head -30"))
out.append('== app.js.j2 里 进入时\n' + sh("grep -n -e 'onEnter' -e 'enters' -e '进入时' templates/frontend/app.js.j2 | head -20"))
out.append('== widgets.j2 里 进入时 / 隐藏\n' + sh("grep -n -e '进入时' -e '隐藏' templates/frontend/widgets.j2 | head -20"))
out.append('== app.js.j2 nav 条件\n' + sh("grep -n -B2 -A2 '<nav>' templates/frontend/app.js.j2"))
open(P + '/data/_patch/top_probe.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
