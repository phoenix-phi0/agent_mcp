# 知识图谱的导入，用引擎自己写（原来是 Python 导入器）。
#
# 读 JSONL 是内置语句：`读JSONL 名 = 文件`，不是动词，所以不能写成
# `设 表 = 读JSONL 文件`——那样整行会被当成一段文本存进变量，遍历它得到
# 一项，而且不报错。踩过。
#
# 加边走 kg_edge_add.sql，那条 SQL 自带环检查：会成环就影响 0 行。所以
# 「拒绝」的计数就是被环检查挡下的加上重复的边。要区分原因得再查
# kg_edge_why，这里只统计条数——逐条的原因留给 Python 导入器那条路。

接口 POST /kg/import 动作 kg_import
  用包 common db http

  读JSONL 节点表 = content/kg.jsonl
  读JSONL 对照表 = content/contrast.jsonl

  设 节点数 = 0
  设 边数 = 0
  设 拒绝 = 0
  设 对照数 = 0

  事务 app.db
    # 先全部节点：文件里可以先引用、后定义
    遍历 项 于 {节点表}
      设 点.code = {项.id}
      设 点.label = {项.label}
      设 影响 = 写库表 app.db kg_node_upsert {点}
      设 节点数 = 相加 {节点数} 1
    结束

    # 再全部边
    遍历 项 于 {节点表}
      遍历 前 于 {项.prereq}
        设 边.src = {前}
        设 边.dst = {项.id}
        设 影响 = 写库表 app.db kg_edge_add {边}
        如果 {影响} 等于 0
          设 拒绝 = 相加 {拒绝} 1
        否则
          设 边数 = 相加 {边数} 1
        结束
      结束
    结束

    # 对照：无向的易混对，不参与环检查
    遍历 对 于 {对照表}
      设 双.x = {对.a}
      设 双.y = {对.b}
      设 影响 = 写库表 app.db kg_contrast_add {双}
      设 对照数 = 相加 {对照数} {影响}
    结束
  结束

  返回 {"nodes":"{节点数}","edges":"{边数}","rejected":"{拒绝}","contrast":"{对照数}"}
结束
