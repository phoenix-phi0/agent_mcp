p = '/home/ysc/mcp/templates/frontend/app.js.j2'
L = open(p, encoding='utf-8').read().split('\n')
hits = [k for k, l in enumerate(L) if 'rowsOf' in l or 'const lists' in l or 'resp.lists' in l]
print('命中行:', [k + 1 for k in hits])
for k in hits:
    for j in range(max(0, k - 2), min(len(L), k + 8)):
        print('%d| %s' % (j + 1, L[j][:140]))
    print('----')
