# 知识点的列表和全貌。
#
# 全貌一次返回三组列表：lists 里按数据键给，界面上三个列表各取各的。
# 数据键默认是表名，「绑」能另指一个。

# 列表页。
接口 POST /node/list 动作 node_list
  用包 db http
  设 行表 = 查询 app.db node_all 条数=500
  设 组.nodes = {行表}
  响应 lists {组}
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
  设 词表 = 查询 app.db word_by_point point={code} 条数=200
  设 三组.prereq = {前置}
  设 三组.children = {后续}
  设 三组.point_words = {词表}
  响应 form {一条}
  响应 lists {三组}
结束
