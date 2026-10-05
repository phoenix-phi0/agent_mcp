# 掌握得分：记一次打分、看当前分、看一个点的历史、回填。
#
# 得分来自做题：每答一题（/quiz/answer、/learn/answer），同一个事务里按
# 最近的作答重算这个点的分，变了才记一行（scripts/score_update.zs，算法在
# queries/score_calc.sql）。/score/add 是手工记一次，留着给调试和以后别的
# 来源用。
#
# 不影响「掌握」和解锁：那两样仍只看 mastery 的计数达标线。
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


# 回填：自动打分上线之前就有的作答，那些点没有得分。给每个「有作答、没有
# 得分」的（学习者, 知识点）按现在的作答算一次、记一行。已经有得分的点
# 一律不碰——不改旧行，也不因为算法变了重打。再调一次什么都不做。
#
# 给 learner 只补这个人，不给是所有人（这里不补 me：回填是维护动作，补的
# 是库里所有人的缺口）。返回补了几行。
接口 POST /score/rebuild 动作 score_rebuild
  用包 common db http

  设 查.learner = {learner 或}
  设 缺 = 查询表 app.db score_missing {查}
  设 补了 = 0
  事务 app.db
    遍历 项 于 {缺}
      设 打分 = 执行 scripts/score_update.zs 学习者={项.learner} 知识点={项.point}
      如果 {打分.changed} 等于 1
        设 补了 = 相加 {补了} 1
      结束
    结束
  结束
  返回 {"added":"{补了}"}
结束
