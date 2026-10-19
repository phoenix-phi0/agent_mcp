业务 progress
  依赖 graph
  用包 db

  公开 函数 记作答 learner point_code correct
    设 p = 调用 graph.取知识点 code={point_code}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    如果 {correct} 不等于 0 且 {correct} 不等于 1
      报错 400 correct 只能是 0 或 1
    结束
    设 day = 当前时间 日期
    设 n = 写库 app.db progress_answer_insert learner={learner} point_code={point_code} correct={correct} at={day}
    设 total = 查一值 app.db progress_answer_total learner={learner} point_code={point_code}
    设 right = 查一值 app.db progress_answer_right learner={learner} point_code={point_code}
    设 score = 计算 四舍五入({right} * 100 / {total})
    返回 {"ok": 1, "total": {total}, "right": {right}, "score": {score}}
  结束
结束
