# 普通 DSL 中复用审查步骤；需要支持派任务的模型客户端。
用包 workflow
设 material = 接口返回用户姓名和邮箱。
设 criteria = 接口必须返回姓名、邮箱和用户编号。
设 review = 审查任务 {material} {criteria}
如果 {review.status} 等于 成功
  打印 审查结论：{review.result.decision}
  打印 问题：{review.result.issues}
否则
  打印 审查任务失败：{review.reason}
结束
