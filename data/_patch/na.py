import shutil, sys
p = '/home/ysc/mcp/tools/ui.py'
shutil.copy(p, '/tmp/ui.py.bak3')
L = open(p, encoding='utf-8').read().split('\n')
s = '\n'.join(L)

# 1. 注册节点图（插在 FLAG_MODIFIERS 定义前）
if 'LINE_KEYWORDS | {"节点图"}' not in s:
    i = [k for k, l in enumerate(L) if l.startswith('FLAG_MODIFIERS =')]
    assert len(i) == 1, 'FLAG_MODIFIERS 命中 %d' % len(i)
    L[i[0]:i[0]] = [
        '# 「节点图」：有向无环图（Vue Flow + dagre）。不叫「图」——「图」是静态图片。',
        'LINE_KEYWORDS = LINE_KEYWORDS | {"节点图"}',
        'LINE_PARENT["节点图"] = {"界面", "区域", "分组", "浮层"}',
        '',
    ]
    print('1 注册节点图')
else:
    print('1 已注册')


def ind(l):
    return l[:len(l) - len(l.lstrip())]


# 2. _shared_defaults 里的图块：kind 改成节点图、选中改直接赋 None；找不到就新插
idx = [k for k, l in enumerate(L)
       if l.strip() in ('if n.kind == "图":', 'if n.kind == "节点图":')
       and k + 1 < len(L) and '"nodes": []' in L[k + 1]]
print('2 图块位置', idx)
if idx:
    k = idx[0]
    L[k] = L[k].replace('"图"', '"节点图"')
    j = [t for t in range(k, k + 8) if 'getattr(n, "selects"' in L[t]]
    if j and '_put_path(shared, n.selects, None)' in L[j[0] + 1]:
        d = ind(L[j[0] + 1])
        L[j[0] + 1:j[0] + 2] = [
            d + '# 直接赋 None，不用 setdefault：同界面有「显示 sel.label」时它会先把 sel',
            d + '# 建成 {label:""}，那样「当 shared.sel」没选中也为真。',
            d + '_box = shared',
            d + 'for _k in n.selects.split(".")[:-1]:',
            d + '    _box = _box.setdefault(_k, {})',
            d + '_box[n.selects.split(".")[-1]] = None',
        ]
        print('2 选中改为直接赋 None')
    else:
        print('2 选中已是直接赋值或无此行')
else:
    st = [k for k, l in enumerate(L) if l.startswith('def _shared_defaults(')]
    assert len(st) == 1, '_shared_defaults 命中 %d' % len(st)
    r = next(t for t in range(st[0], len(L)) if L[t].strip() == 'return shared')
    L[r:r] = [
        '    # 节点图数据整块放共享状态，后端用 state 换掉整个对象即可。',
        '    for s in screens:',
        '        for n in s.walk():',
        '            if n.kind == "节点图":',
        '                _put_path(shared, n.bind or n.name, {"nodes": [], "edges": []})',
        '                if getattr(n, "selects", ""):',
        '                    _box = shared',
        '                    for _k in n.selects.split(".")[:-1]:',
        '                        _box = _box.setdefault(_k, {})',
        '                    _box[n.selects.split(".")[-1]] = None',
    ]
    print('2 新插节点图块')

# 3. has_graphs
idx = [k for k, l in enumerate(L) if '"has_graphs":' in l]
assert len(idx) == 1, 'has_graphs 命中 %d' % len(idx)
L[idx[0]] = L[idx[0]].replace('n.kind == "图"', 'n.kind == "节点图"')
print('3', L[idx[0]].strip())
print('剩余 kind==图 的行:', [(k + 1, L[k].strip()) for k in range(len(L)) if 'kind == "图"' in L[k]])
open(p, 'w', encoding='utf-8').write('\n'.join(L))

# 验证
sys.path.insert(0, '/home/ysc/mcp')
from tools import ui
a = ui.parse('界面 自定义 T\n  分组 g 竖排\n    节点图 deps 绑 graph 选中 sel 高 420px 方向 纵向\n    显示 sel.label\n  结束\n结束\n')
n = a[0].children[0].children[0]
print('验证 节点图:', n.kind, n.bind, n.selects, n.direction, n.size, repr(n.label))
print('验证 节点图 shared:', ui._shared_defaults(a))
try:
    b = ui.parse('界面 自定义 P\n  分组 g 竖排\n    图 logo 绑 logo_url 高 80px 标志\n  结束\n结束\n')
    print('验证 静态图 shared:', ui._shared_defaults(b))
except Exception as e:
    print('静态图解析:', type(e).__name__, e)
