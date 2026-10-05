# 学习进度页（ui/progress.ui）：一次把这一页要的都拿齐。
#
# 都是读：attempt / mastery / score 只看不写。进页面时调（「进入时」），
# 所以只回 state 和 lists，不推消息——来回切界面不会在别处叠消息。
#
#   state.prog     概览：已掌握 x / 总知识点 y、累计答题、正确率；empty=1
#                  表示一道都没答过，界面换成「去做题页做几道」
#   lists.doing    在学：答过的知识点，答对/答题、达不达标
#   lists.next     现在能学：learn_next，跟 /learn/next 同一条查询
#   lists.recent   最近作答 20 条
#   lists.levels   N5..N1 每级的知识点掌握了几个
#   lists.scores   掌握得分（progress_scores）：当前分、跟上一次比的变化、
#                  最近打分时间，分低的在前；没有打过分就是空的，界面整块不显示
#                  概览里另有 score_text「平均得分 x」
#
# 学习者不传就是 me，达标线不传就是 80% / 8 题——跟 learn.zs、quiz.zs
# 开头同一段默认值。
接口 POST /progress/page 动作 progress_page
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 正确率 = {rate 或}
  如果 {正确率} 为空
    设 正确率 = 80
  结束
  设 最少题数 = {min_count 或}
  如果 {最少题数} 为空
    设 最少题数 = 8
  结束

  设 谁.learner = {学习者}
  设 概览 = 查一行表 app.db progress_overview {谁}

  设 线.learner = {学习者}
  设 线.rate = {正确率}
  设 线.min_count = {最少题数}
  设 在学 = 查询表 app.db progress_doing {线}

  设 下一步.learner = {学习者}
  设 下一步.条数 = 20
  设 能学 = 查询表 app.db learn_next {下一步}

  设 最近 = 查询表 app.db progress_recent {谁}
  设 分级 = 查询表 app.db progress_levels {谁}

  设 得分 = 查询表 app.db progress_scores {谁}

  设 组.doing = {在学}
  设 组.next = {能学}
  设 组.recent = {最近}
  设 组.levels = {分级}
  设 组.scores = {得分}
  响应 lists {组}
  设 状态.prog = {概览}
  响应 state {状态}
结束
