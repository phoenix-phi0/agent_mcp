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
#   state.dictation 单词默写（dictation_stats）：练过几个词、正确率、错词本几个，
#                  链接到默写页。读的是 word_attempt，跟上面的学习记录分开
#
# 学习者不传就是 me，达标线不传就是 80% / 8 题——跟 learn.zs、quiz.zs
# 开头同一段默认值。
接口 POST /progress/page 动作 progress_page
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 rate = {rate 或}
  如果 {rate} 为空
    设 rate = 80
  结束
  设 min_count = {min_count 或}
  如果 {min_count} 为空
    设 min_count = 8
  结束

  设 who.learner = {learner}
  设 overview = 查一行表 app.db progress_overview {who}

  设 line_args.learner = {learner}
  设 line_args.rate = {rate}
  设 line_args.min_count = {min_count}
  设 doing = 查询表 app.db progress_doing {line_args}

  设 next_args.learner = {learner}
  设 next_args.limit = 20
  设 next_rows = 查询表 app.db learn_next {next_args}

  设 recent = 查询表 app.db progress_recent {who}
  设 levels = 查询表 app.db progress_levels {who}

  设 score_text = 查询表 app.db progress_scores {who}

  # 单词默写（word_attempt，跟上面的学习记录分开）：练过几个词、正确率、错词本
  设 dictation = 查一行表 app.db dictation_stats {who}

  设 group.doing = {doing}
  设 group.next = {next_rows}
  设 group.recent = {recent}
  设 group.levels = {levels}
  设 group.scores = {score_text}
  响应 lists {group}
  设 state.prog = {overview}
  设 state.dictation = {dictation}
  响应 state {state}
结束
