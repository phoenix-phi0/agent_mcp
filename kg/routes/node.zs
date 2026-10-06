# 知识点：列表、全貌、整张图。
#
# 图的数据走 state 而不是 lists：节点图是从共享路径读 {nodes, edges} 的，
# 那是一整个对象，不是表格的行。

# 列表页，同时把整张图也给出去——一次请求把这一页要的都拿齐。
接口 POST /node/list 动作 node_list 只许 学生
  用包 db http
  # 左边的列表和右边的图用同一份数据：都带 state（掌握/可学/锁定），
  # 引擎按它给列表行加 row-done / row-open / row-locked，跟图上的颜色一致。
  # 早先列表走 node_all（只有编号和名称），行就没有状态色。
  # {learner} 由路由器注入（单人模式没给是 me，多人模式是登录的人）。早先这里
  # 默认是空串：答题记在 me 名下、图按「没有人」去查，图上什么都不变，也不报错。
  设 who.learner = {learner}
  设 nodes = 查询表 app.db kg_graph_nodes {who}
  设 group.nodes = {nodes}
  响应 lists {group}

  # 图的数据。节点带 state（掌握/可学/锁定）和 badge（下游节点数），
  # 引擎按 state 上色、按 badge 画角标；边里对照那些带 kind=对照，画成
  # 虚线且不参与布局——不然同层的一对会被拉成上下两层。
  #
  # 布局交给控件（dagre）：这是「节点图」该管的事，后端只给数据。
  设 edges = 查询 app.db kg_graph_edges
  设 graph.nodes = {nodes}
  设 graph.edges = {edges}
  设 state.graph = {graph}
  响应 state {state}
结束


# 一个知识点的全貌：直接前置、直接后续、挂着的词，还有自己答对/答题和
# 掌握得分。
接口 POST /node/one 动作 node_detail 只许 学生
  用包 db http
  设 record = 查一行 app.db node_one code={code}
  如果 {record.code} 为空
    返回 {"error":"没有这个知识点"} 404
  结束
  设 parents = 查询 app.db kg_parents code={code}
  设 children = 查询 app.db kg_children code={code}
  设 items = 查询 app.db item_by_point point={code}
  设 forms = 查询 app.db item_by_form code={code}
  设 words = 查询 app.db word_by_point point={code} limit=200
  设 lists_out.prereq = {parents}
  设 lists_out.children = {children}
  设 lists_out.items = {items}
  设 lists_out.forms = {forms}
  设 lists_out.point_words = {words}
  响应 form {record}
  响应 lists {lists_out}

  # 这个点答对几道、答了几道（mastery 左连接，没做过说「还没做过」）。
  # {learner} 由路由器注入，跟 node_list 同一个
  设 this_point.learner = {learner}
  设 this_point.code = {code}
  设 tally = 查一值表 app.db node_tally {this_point}
  设 state.node_tally = {tally}
  # 掌握得分（没打过分是空串，浮层上那一格不显示）
  设 score = 查一值表 app.db node_score {this_point}
  设 state.node_score = {score}
  响应 state {state}
结束
