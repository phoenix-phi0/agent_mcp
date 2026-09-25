# 学习记录：记作答、看进度、算下一步学什么。
#
# 达标线从请求来，不给就用默认（80% 正确率、至少 8 题）。那是教学策略，
# 不是语言结构，所以既不在图里也不写死在这儿——严格模式、考前冲刺都可以
# 传不同的线。

# 记一次作答：写流水、更新汇总、重算掌握标记。三件事一个事务——中途断了
# 就全不算，不能出现「流水记了但汇总没加」。
接口 POST /learn/answer 动作 learn_answer
  用包 common db http

  设 正确率 = {rate}
  如果 {正确率} 为空
    设 正确率 = 80
  结束
  设 最少题数 = {min_count}
  如果 {最少题数} 为空
    设 最少题数 = 8
  结束

  事务 app.db
    设 影响 = 写库表 app.db attempt_insert {请求}
    设 影响 = 写库表 app.db mastery_bump {请求}

    设 条件.learner = {learner}
    设 条件.point = {point}
    设 条件.rate = {正确率}
    设 条件.min_count = {最少题数}
    设 现状 = 查一行表 app.db mastery_one {条件}

    # 刚达标：这次答完才够线，之前不够。用来提示「解锁了新知识点」
    设 刚达标 = 否
    如果 {现状.ok} 等于 1
      如果 {现状.mastered} 等于 0
        设 刚达标 = 是
      结束
    结束

    设 标记.learner = {learner}
    设 标记.point = {point}
    设 标记.mastered = {现状.ok}
    设 影响 = 写库表 app.db mastery_set {标记}
  结束

  返回 {"right":"{现状.right}","total":"{现状.total}","rate":"{现状.rate}","mastered":"{现状.ok}","just":"{刚达标}"}
结束


# 现在能学什么：自己没掌握、前置都掌握了的知识点，按依赖深度排。
接口 POST /learn/next 动作 learn_next
  用包 db http
  设 行表 = 查询 app.db learn_next learner={learner} 条数=20
  设 组.next = {行表}
  响应 lists {组}
结束


# 进度：掌握了多少，以及在学的那些还差什么。
接口 POST /learn/status 动作 learn_status
  用包 db http

  设 正确率 = {rate}
  如果 {正确率} 为空
    设 正确率 = 80
  结束
  设 最少题数 = {min_count}
  如果 {最少题数} 为空
    设 最少题数 = 8
  结束

  设 总览 = 查一行 app.db learn_progress learner={learner}
  设 条件.learner = {learner}
  设 条件.rate = {正确率}
  设 条件.min_count = {最少题数}
  设 条件.条数 = 10
  设 在学 = 查询表 app.db learn_doing {条件}

  # 不能用「返回」：它一出现脚本就结束，上面「响应」攒的 lists 全作废。
  # 进度用 state 给（它本来就是跨界面的状态），表格用 lists。
  设 组.doing = {在学}
  响应 lists {组}
  设 状态.progress = {总览}
  响应 state {状态}
结束
