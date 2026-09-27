import subprocess
P = '/home/ysc/mcp'
T = P + '/templates/frontend/'
L = open(T + 'app.js.j2', encoding='utf-8').read().split('\n')
g0 = [k for k, l in enumerate(L) if l.strip().startswith('function _graphGet(')]
st = max(k for k in range(g0[0]) if L[k].strip() == '<% if has_graphs %>')
og = [k for k in range(g0[0], len(L)) if 'function onGraphNode(' in L[k]]
close = next(k for k in range(og[0] + 1, len(L)) if L[k] == '    }')
en = next(k for k in range(close + 1, len(L)) if L[k].strip())
open(P + '/data/_patch/cur_graph_block.txt', 'w', encoding='utf-8').write('\n'.join(L[st:en + 1]))
open(P + '/data/_patch/cur_graph_j2.txt', 'w', encoding='utf-8').write(open(T + 'graph.j2', encoding='utf-8').read())
r = subprocess.run('git show --stat 7248201 | head -30', shell=True, cwd=P, capture_output=True, text=True)
open(P + '/data/_patch/cur_7248201.txt', 'w', encoding='utf-8').write(r.stdout + r.stderr)
print('block lines', st + 1, en + 1, 'ok')
