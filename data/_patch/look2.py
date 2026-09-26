p = '/home/ysc/mcp/templates/frontend/layout.j2'
L = open(p, encoding='utf-8').read().split('\n')
for k in range(76, 96):
    print('%d| %s' % (k + 1, L[k][:150]))
