P = '/home/ysc/mcp/templates/frontend/app.js.j2'
L = open(P, encoding='utf-8').read().split('\n')
out = []
for a, b in [(180, 215), (505, 600)]:
    out.append('---- %d-%d' % (a, b))
    out += ['%4d| %s' % (i + 1, L[i]) for i in range(a - 1, min(b, len(L)))]
open('/home/ysc/mcp/data/_patch/app_overlay.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
