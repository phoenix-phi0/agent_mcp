# 文件名 graph_api → 属于 graph 模块：可调 graph 的公开函数；调 progress 要 graph 的业务文件依赖它
接口 POST /graph/point
  设 p = 调用 graph.取知识点 code={code}
  返回 {p}
结束


接口 POST /graph/internal
  设 r = 调用 graph.内部统计
  返回 {r}
结束


接口 POST /graph/undeclared
  设 r = 调用 progress.记作答 learner=u point_code=P1 question_no=1 correct=1
  返回 {r}
结束
