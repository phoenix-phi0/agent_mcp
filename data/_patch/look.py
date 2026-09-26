p = '/home/ysc/mcp/templates/frontend/layout.j2'
L = open(p, encoding='utf-8').read().split('\n')
i = [k for k, l in enumerate(L) if 'node.kind == "列表"' in l]
print('列表分支起始行:', [k + 1 for k in i])
if i:
    for k in range(i[0], min(i[0] + 45, len(L))):
        print('%4d| %s' % (k + 1, L[k]))
        if k > i[0] and L[k].lstrip().startswith('<% elif'):
            break
print('--- 所有 v-for 行 ---')
for k, l in enumerate(L):
    if 'v-for' in l:
        print('%4d| %s' % (k + 1, l.strip()[:160]))
