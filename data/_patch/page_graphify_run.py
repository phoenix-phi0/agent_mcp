src = open('/home/ysc/mcp/data/_patch/page_graphify.py', encoding='utf-8').read()
inject = open('/home/ysc/mcp/data/_patch/pg_inject.txt', encoding='utf-8').read()

def rep(a, b):
    global src
    assert src.count(a) == 1, ('命中', src.count(a), a[:40])
    src = src.replace(a, b)

# 邻域图层名改用 layerTitles（只显示名字，不带层号）
rep("layerNames: ps.length ?", "layerTitles: ps.length ?")
anchor = '    s = sub1(s, "          class: [_kgState[n.state], n.class].filter(Boolean).join(\' \'),\\n",'
rep(anchor, inject + anchor)
# 验证条件跟着改
rep("'直接前置/当前/直接后续' in out", "'layers 直接前置/当前/直接后续' in out")
rep("'layers 当前/直接后续' in out", "'NB2 nodes a,c | layers 当前/直接后续' in out")
exec(compile(src, 'page_graphify', 'exec'), {'__name__': '__main__'})
