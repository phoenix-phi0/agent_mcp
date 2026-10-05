# 知识图谱导入，用引擎自己写（原来是 Python：tools/kg_dag.py）。
#
# 顺序是有讲究的：
#   节点 → 条目 → 边 → 对照
#   条目的 point 指向节点（外键），所以节点要先；
#   对照的两端可能是条目（なければならない ↔ なくてもいい），所以对照要后；
#   边放在条目之后没有硬性要求，但这样一趟读完三个文件更顺。
#
# **加边走 kg_edge_add.sql，那条 SQL 自带环检查**：会成环就影响 0 行。
# 被拒之后再查 kg_edge_why 问原因，成环的还查一次 kg_path 拿到库里那条
# 已有的路径——「c → a 被拒，因为库里已经有 a → b → c」比只说「会成环」
# 有用得多。
#
# 整个导入在一个事务里：文件中途坏掉全部回滚，不会导一半。被拒的边不算
# 意外，照常提交。

接口 POST /kg/import2 动作 kg_import2
  用包 common db http

  读JSONL node_rows = content/kg.jsonl
  读JSONL item_rows = content/items.jsonl
  读JSONL contrast_rows = content/contrast.jsonl

  设 node_n = 0
  设 item_n = 0
  设 edge_n = 0
  设 existing = 0
  设 rejected = 0
  设 contrast_n = 0
  设 note = 

  事务 app.db
    # 一、节点。先全部插入，文件里可以先引用后定义
    遍历 item 于 {node_rows} 序号 row
      设 point.code = {item.id 或}
      设 point.label = {item.label 或}
      如果 {point.code} 为空
        设 note = {note} 第{row}行缺 id；
      否则
        设 affected = 写库表 app.db kg_node_upsert {point}
        设 node_n = 相加 {node_n} 1
      结束
    结束

    # 二、条目。point 指向节点，所以要在节点之后
    遍历 entry 于 {item_rows} 序号 row
      设 catalog_args.code = {entry.code 或}
      设 catalog_args.label = {entry.label 或}
      设 catalog_args.point = {entry.point 或}
      设 catalog_args.form = {entry.form 或}
      设 catalog_args.after = {entry.after 或}
      如果 {catalog_args.code} 为空
        设 note = {note} 条目第{row}行缺 code；
      否则
        设 affected = 写库表 app.db item_upsert {catalog_args}
        设 item_n = 相加 {item_n} 1
      结束
    结束

    # 三、前置边。SQL 自带环检查，被拒的逐条问原因
    遍历 item 于 {node_rows} 序号 row
      遍历 prev 于 {item.prereq 或}
        设 edge.src = {prev}
        设 edge.dst = {item.id}
        设 affected = 写库表 app.db kg_edge_add {edge}
        如果 {affected} 等于 1
          设 edge_n = 相加 {edge_n} 1
        否则
          设 reason = 查一值表 app.db kg_edge_why {edge}
          如果 {reason} 等于 已存在
            设 existing = 相加 {existing} 1
          否则
            设 rejected = 相加 {rejected} 1
            设 path_args.from = {item.id}
            设 path_args.to = {prev}
            设 path = 查一值表 app.db kg_path {path_args}
            设 note = {note} 第{row}行 {prev}→{item.id} {reason}{path}；
          结束
        结束
      结束
    结束

    # 四、对照。两端可以是节点也可以是条目，所以放在最后
    遍历 pair 于 {contrast_rows} 序号 row
      设 pair_args.x = {pair.a 或}
      设 pair_args.y = {pair.b 或}
      设 affected = 写库表 app.db kg_contrast_add {pair_args}
      设 contrast_n = 相加 {contrast_n} {affected}
    结束
  结束

  返回 {"nodes":"{node_n}","items":"{item_n}","edges":"{edge_n}","existing":"{existing}","rejected":"{rejected}","contrast":"{contrast_n}","note":"{note}"}
结束
