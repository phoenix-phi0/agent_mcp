src = open('/home/ysc/mcp/data/_patch/drop_top.py', encoding='utf-8').read()
old = ("         '进入时仍会跑 node_list': re.search(r'const enters = (\\{.*?\\});', js) is not None and 'node_list' in re.search(r'const enters = (\\{.*?\\});', js).group(1)}")
new = "         '进入时仍会跑 node_list': '{\"知识图谱\": [\"node_list\"]}' in js}"
assert src.count(old) == 1, src.count(old)
src = src.replace(old, new)
exec(compile(src, 'drop_top', 'exec'), {'__name__': '__main__'})
