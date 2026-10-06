# 学习记录：记作答、看进度、算下一步学什么。
#
# 掌握看掌握得分（不看累计正确率，理由见 queries/mastery_one.sql）：得分
# ≥ 达标线 line 算掌握，掌握之后 ≥ 回落线 keep 就继续算。两条线从请求来，
# 不给就用默认（80 / 60，在 scripts/mastery_update.zs）。那是教学策略，
# 不是语言结构，所以既不在图里也不写死在这儿——严格模式、考前冲刺都可以
# 传不同的线。
#
# **学习者不传就是 me。** 这个项目没开认证（没跑过 gen auth），是一个人
# 自己用的。但每个接口都得用同一个默认值（score.zs、node.zs 也是）：
# 早先 /node/list 的默认是空串，那样记在 me 名下的东西图上看不到——
# 写的按 me、读的按「没有人」，而且两边都不报错。所以每个接口开头都是
# 同一段：先取 {learner 或}（缺了不会留成 {learner} 字面量），再判空补
# me——空串和没传一样处理。


# 记一次作答：写流水、更新汇总、重算掌握标记、重算掌握得分。一个事务——
# 中途断了就全不算，不能出现「流水记了但汇总没加」。
接口 POST /learn/answer 动作 learn_answer
  用包 common db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束

  # 对错必须给：缺了的话 CAST 成 0，记成一道错题，不报错
  设 correct = {correct 或}
  如果 {correct} 为空
    返回 {"error":"缺 correct（1 对 0 错）"} 400
  结束

  # 不直接把 {request} 交给写库：里面的 learner 可能是空的，要用上面补过默认值的
  设 rec.learner = {learner}
  设 rec.point = {point}
  设 rec.item = {item 或}
  设 rec.correct = {correct}
  # 作答内容这里没有（只报对错），记空
  设 rec.answer =

  事务 app.db
    设 affected = 写库表 app.db attempt_insert {rec}
    设 affected = 写库表 app.db mastery_bump {rec}

    # 重算得分、按得分改掌握标记（达标线 line / 回落线 keep 不传就用
    # 脚本里的默认值），见 scripts/mastery_update.zs
    设 scoring = 执行 scripts/mastery_update.zs learner={learner} point={point} line={line 或} keep={keep 或}
  结束

  返回 {"right":"{scoring.right}","total":"{scoring.total}","rate":"{scoring.rate}","mastered":"{scoring.mastered}","just":"{scoring.just}","score":"{scoring.after}"}
结束


# 现在能学什么：自己没掌握、前置都掌握了的知识点，按依赖深度排。
接口 POST /learn/next 动作 learn_next
  用包 db http
  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 rows = 查询 app.db learn_next learner={learner} limit=20
  设 group.next = {rows}
  响应 lists {group}
结束


# 进度：掌握了多少，以及在学的那些还差什么。
接口 POST /learn/status 动作 learn_status
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 line = {line 或}
  如果 {line} 为空
    设 line = 80
  结束
  设 keep = {keep 或}
  如果 {keep} 为空
    设 keep = 60
  结束

  设 overview = 查一行 app.db learn_progress learner={learner}
  设 cond.learner = {learner}
  设 cond.line = {line}
  设 cond.keep = {keep}
  设 cond.limit = 10
  设 doing = 查询表 app.db learn_doing {cond}

  # 不能用「返回」：它一出现脚本就结束，上面「响应」攒的 lists 全作废。
  # 进度用 state 给（它本来就是跨界面的状态），表格用 lists。
  设 group.doing = {doing}
  响应 lists {group}
  设 state.progress = {overview}
  响应 state {state}
结束
