业务 graph
  用包 db

  公开 函数 取知识点 code
    设 p = 查一行 app.db graph_point_by_code code={code}
    返回 {p}
  结束

  公开 函数 加边 src dst
    设 a = 调用 取知识点 code={src}
    设 b = 调用 取知识点 code={dst}
    如果 {a} 为空 或 {b} 为空
      报错 404 没有这个知识点
    结束
    如果 {src} 等于 {dst}
      报错 409 会形成环
    结束
    设 hit = 调用 能到达 start={dst} goal={src}
    如果 {hit.yes} 等于 1
      报错 409 会形成环
    结束
    设 n = 写库 app.db graph_edge_insert src={src} dst={dst}
    返回 {"ok": 1}
  结束

  函数 能到达 start goal
    如果 {start} 等于 {goal}
      返回 {"yes": 1}
    结束
    设 rows = 查询 app.db graph_edges_from src={start}
    遍历 r 于 {rows}
      设 h = 调用 能到达 start={r.dst} goal={goal}
      如果 {h.yes} 等于 1
        返回 {"yes": 1}
      结束
    结束
    返回 {"yes": 0}
  结束
结束
