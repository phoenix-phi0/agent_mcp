业务 graph
  用包 db

  # 按编号取知识点；没有这个知识点返回空结构
  公开 函数 取知识点 code
    设 p = 查一行 app.db point_by_code code={code}
    返回 {p}
  结束

  # 没写「公开」：别的模块调不了
  函数 内部统计
    返回 {"n": 0}
  结束
结束
