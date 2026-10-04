# 掌握得分：记一次打分、看当前分、看一个点的历史。
#
# 只是数据这一层：还没接界面，也不影响「掌握」和解锁（那两样只看
# mastery）。得分怎么折算成掌握、要不要跟答题合起来算，以后再定——
# 先把数据攒起来。
#
# 学习者不传就是 me，跟 learn.zs、node.zs 同一个默认值（这个项目没开
# 认证，是一个人自己用的）。每个接口开头都是同一段：先取 {learner 或}
# （缺了不会留成 {learner} 字面量），再判空补 me——空串和没传一样处理。


# 记一次打分。分值 0–100 的整数。返回这个点打完之后的当前分。
接口 POST /score/add 动作 score_add
  用包 common db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束

  设 分 = {value 或}
  如果 {分} 为空
    返回 {"error":"缺分数（0–100 的整数）"} 400
  结束

  设 查点.point = {point 或}
  设 有 = 查一值表 app.db node_exists {查点}
  如果 {有} 为空
    返回 {"error":"没有这个知识点"} 404
  结束

  设 记.learner = {学习者}
  设 记.point = {point}
  设 记.value = {分}
  设 影响 = 写库表 app.db score_add {记}
  # 写入那条 SQL 自己查范围，不合格就影响 0 行
  如果 {影响} 等于 0
    返回 {"error":"分数要是 0–100 的整数"} 400
  结束

  设 条件.learner = {学习者}
  设 条件.point = {point}
  设 当前 = 查询表 app.db score_now {条件}
  设 组.scores = {当前}
  响应 lists {组}
  # 消息按空格切参数，提示里不能有空格
  消息 系统 记下了：{分}分 ok
结束


# 当前得分：每个知识点取最新的一次。给 point 就只看那一个，不给是全部。
# 没打过分的点不出现。
接口 POST /score/now 动作 score_now
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束

  设 条件.learner = {学习者}
  设 条件.point = {point 或}
  设 当前 = 查询表 app.db score_now {条件}
  设 组.scores = {当前}
  响应 lists {组}
结束


# 一个知识点的全部打分，从早到晚。
接口 POST /score/history 动作 score_history
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束

  设 点 = {point 或}
  如果 {点} 为空
    返回 {"error":"缺 point（看哪个知识点的历史）"} 400
  结束

  设 条件.learner = {学习者}
  设 条件.point = {点}
  设 历史 = 查询表 app.db score_history {条件}
  设 组.history = {历史}
  响应 lists {组}
结束
