import re, sqlite3, runpy, sys
P = '/home/ysc/mcp'
src = open(P + '/data/_patch/measure.py', encoding='utf-8').read()
# 把「从视图取数」那段换成：读 kg/queries 下的两条 SQL 执行
new_fetch = r'''
def run_sql(name):
    sql = open(P + '/kg/queries/%s.sql' % name, encoding='utf-8').read()
    params = {'learner': '', 'code': ''}
    # 占位写法可能是 :learner / {learner} / ?，逐个试
    for attempt in (sql, re.sub(r'\{(\w+)\}', r':\1', sql)):
        try:
            return rows_of(attempt, params)
        except Exception as e:
            err = e
    raise err
def rows_of(sql, params):
    cur = db.execute(sql, params) if (':' in sql) else db.execute(sql)
    return [dict(r) for r in cur]
nodes = run_sql('kg_graph_nodes'); print('节点', len(nodes), '| 字段', list(nodes[0].keys())[:10])
edges = run_sql('kg_graph_edges'); print('边', len(edges), '| 字段', list(edges[0].keys())[:6])
'''
a = src.index('nodes = edges = None')
b = src.index('def pick(d, *ks):')
src = src[:a] + new_fetch + '\n' + src[b:]
exec(compile(src, 'measure', 'exec'), {'__name__': '__main__'})
