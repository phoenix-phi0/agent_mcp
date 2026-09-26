# 知识点：列表、全貌、整张图。
#
# 图的数据走 state 而不是 lists：节点图是从共享路径读 {nodes, edges} 的，
# 那是一整个对象，不是表格的行。

# 列表页，同时把整张图也给出去——一次请求把这一页要的都拿齐。
接口 POST /node/list 动作 node_list
  用包 db http
  设 行表 = 查询 app.db node_all 条数=500
  设 组.nodes = {行表}
  响应 lists {组}

  # 图的数据：节点和边，不带坐标——布局是「节点图」控件的事。
  # 早先在 Python 里算好坐标塞进来，那是把引擎该做的事挪进了应用。
  设 点表 = 查询 app.db kg_all_nodes
  设 边表 = 查询 app.db kg_all_edges
  设 图.nodes = {点表}
  设 图.edges = {边表}
  设 状态.graph = {图}
  响应 state {状态}
结束


# 一个知识点的全貌：直接前置、直接后续、挂着的词。
接口 POST /node/one 动作 node_detail
  用包 db http
  设 一条 = 查一行 app.db node_one code={code}
  如果 {一条.code} 为空
    返回 {"error":"没有这个知识点"} 404
  结束
  设 前置 = 查询 app.db kg_parents code={code}
  设 后续 = 查询 app.db kg_children code={code}
  设 条目 = 查询 app.db item_by_point point={code}
  设 接续 = 查询 app.db item_by_form code={code}
  设 词表 = 查询 app.db word_by_point point={code} 条数=200
  设 三组.prereq = {前置}
  设 三组.children = {后续}
  设 三组.items = {条目}
  设 三组.forms = {接续}
  设 三组.point_words = {词表}
  响应 form {一条}
  响应 lists {三组}
结束
