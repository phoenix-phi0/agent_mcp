import subprocess, os
P = '/home/ysc/mcp'
def sh(c):
    r = subprocess.run(c, shell=True, cwd=P, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()
print('== git log'); print(sh('git log --oneline -12'))
print('== git status'); print(sh('git status --short -- tools templates | head -20'))
T = P + '/templates/frontend/'
def has(f, *keys):
    try:
        s = open(f, encoding='utf-8').read()
    except Exception as e:
        return 'ERR ' + str(e)
    return ' '.join('%s=%s' % (k, 'Y' if k in s else '-') for k in keys)
print('== ui.py:', has(P + '/tools/ui.py', '"节点图"', '选中', '点开', '图例', '排布', 'unknown_popup', '最后再把所有「选中」', '_file_fields', 'has_graphs'))
print('== graph.j2:', has(T + 'graph.j2', 'macro 节点图', 'kg-head', '#node-kglayer', 'VueFlow', 'kgOf'))
print('== app.js.j2:', has(T + 'app.js.j2', 'function graphOf', 'minlen', 'smoothstep', '_kgIcon', 'kgLayout', 'onGraphNode', 'VueFlowCore.VueFlow', 'Array.isArray(raw0)'))
print('== index.html.j2:', has(T + 'index.html.j2', 'vue-flow-core', 'dagre_js %>"></script>'))
print('== layout.j2:', has(T + 'layout.j2', 'import 节点图', 'kind == "节点图"'))
print('== style.css.j2:', has(T + 'style.css.j2', '.kg-node', '.kg-head', '.kg-layer', 'kg-dim'))
print('== reflog'); print(sh('git reflog -12'))
