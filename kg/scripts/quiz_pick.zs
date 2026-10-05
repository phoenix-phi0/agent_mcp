# 出一道题。routes/quiz.zs 里「开始」「下一题」「按课文进来」「再来一轮」
# 几个接口共用，用「执行 scripts/quiz_pick.zs 键=值 …」调。不放在 routes/
# 下：那里的 .zs 是按「接口」块扫的，放一个没有接口的脚本进去看着像写漏了。
#
# 参数：
#   学习者
#   等级、考点   页面顶栏选的，「全部」表示不限
#   课文         给了就是按课练（见 question_pick_lesson.sql：本课的题为主，
#                每第三道混一道易混对比题），等级考点不管；空就是按等级考点，
#                这时库里记的「在练的课」也清掉——点「开始」就退出按课模式
#   清零         1 = 这一轮的计数清零、按课练从头一轮（开始、按课进来、再来
#                一轮），0 = 接着算（下一题）
#   模式         review = 复习薄弱点（#做题?mode=review）：课文空、等级考点不管，
#                题从这个人的低分点、错题、久没做的已掌握点里挑（见
#                question_pick_review.sql）；一轮出够「轮题数」道（默认 10）
#                就 phase=end，卡上「请老师总结这一轮」「再来一轮」。
#                一道都没答过：不出题、不报错，phase=noreview，界面上一句
#                「先按等级做几道」和「开始」，返回里多一个 empty=1。不给（空）
#                就是按课或按等级考点，
#                库里记的模式清掉
#   轮题数       复习一轮几道，不给是 10
#
# 成功：往响应的 state 里放一张新题卡（card），返回 {"ok":"1"}。
# 题卡：{code, head, stem, options:[{key,text,state}], verdict, mine}，界面上
# 「卡片 翻页 card.code」——code 一变就是新的一张。选项是打乱过的（种子
# 「学习者|题号|seq」，判题时 routes/quiz.zs 用同一个种子再拆一次）。
# 按课练这一课的题都出过一轮了：不出题，state 里 phase=end、round 是那句
# 提示和「回教材」「换一课」的地址，同样返回 {"ok":"1"}。
# state 里还有 round_total（这一轮答了几道）、round_lesson（按课练的课，自由练
# 是空）、round_mode（review 或空），界面按它们出「请老师总结」的按钮；出新题时
# summary 清空（总结卡片收起）。
# 失败：返回 {"error":…}，由调用的接口决定怎么回——子脚本的「返回」只结束
# 子脚本，结束不了接口。

用包 db http quiz

设 查.learner = {学习者}
设 进度 = 查一行表 app.db quiz_state_one {查}

设 范围 = 
设 已出 = 
设 已出几道 = 0
# 条件左边展开成空串时认不出来，空的先当「无」
设 模式值 = {模式 或 无}
如果 {课文 或} 不为空
  设 模式值 = 无
结束
如果 {模式值} 不等于 review
  设 模式值 = 
结束
如果 {课文 或} 不为空
  设 课查.lesson = {课文}
  设 课 = 查一行表 app.db lesson_scope {课查}
  如果 {课.code 或} 为空
    返回 {"error":"没有这一课：{课文}"}
  结束
  设 范围 = {课.scope}
  # 「下一题」接着这一轮；新一轮（按课进来、再来一轮）从头算
  如果 {清零} 等于 0
    设 已出 = {进度.round_seen 或}
    设 已出几道 = {进度.round_n 或 0}
  结束

  设 抽.learner = {学习者}
  设 抽.lesson = {课文}
  设 抽.seen = {已出}
  设 抽.n = {已出几道}
  设 抽.last = {进度.current 或}
  设 抽中 = 查一行表 app.db question_pick_lesson {抽}
  设 题号 = {抽中.code 或}
  如果 {题号} 为空
    如果 {清零} 等于 1
      返回 {"error":"这一课还没有题"}
    结束
    # 这一课的题这一轮都出过了：说一声，不悄悄换到别的课
    设 一轮.text = 这一课的{课.n}道题都做过一轮了（{进度.stat}）。可以再来一轮、换一课，或者回教材再看看这一课。
    设 一轮.back = {课.back}
    设 一轮.more = {课.more}
    设 状态.phase = end
    设 状态.round = {一轮}
    设 状态.stat = {进度.stat}
    设 状态.scope = {范围}
    设 状态.cheer = 
    设 状态.round_total = {进度.total}
    设 状态.round_lesson = {课文}
    设 状态.round_mode = 
    响应 state {状态}
    返回 {"ok":"1"}
  结束
否则
  如果 {模式值 或 无} 等于 review
    # ---- 复习薄弱点 ----
    设 依查.learner = {学习者}
    设 依查.score_line = 80
    设 依查.level = 
    设 依查.top = 3
    设 依据 = 查一行表 app.db review_brief {依查}
    如果 {依据.answers 或 0} 等于 0
      # 没有作答记录：不出题、不报错，库里不记复习模式
      设 状态.phase = noreview
      设 状态.card = 
      设 状态.scope = 
      设 状态.cheer = 
      设 状态.summary = 
      设 状态.round_mode = review
      设 状态.round_lesson = 
      设 状态.round_total = 0
      响应 state {状态}
      返回 {"ok":"1","empty":"1"}
    结束
    设 范围 = 复习薄弱点：{依据.names}
    如果 {依据.names} 为空
      设 范围 = 复习薄弱点
    结束
    设 一轮几道 = {轮题数 或 10}
    如果 {清零} 等于 0
      设 已出 = {进度.round_seen 或}
      设 已出几道 = {进度.round_n 或 0}
    结束
    如果 {已出几道} 不小于 {一轮几道}
      # 这一轮出够了：说一声，等着「请老师总结」或「再来一轮」
      设 一轮.text = 这一轮复习做完了（{进度.stat}）。可以请老师总结这一轮，或者再来一轮。
      设 一轮.back = 
      设 一轮.more = 
      设 状态.phase = end
      设 状态.round = {一轮}
      设 状态.stat = {进度.stat}
      设 状态.scope = {范围}
      设 状态.cheer = 
      设 状态.round_total = {进度.total}
      设 状态.round_lesson = 
      设 状态.round_mode = review
      响应 state {状态}
      返回 {"ok":"1"}
    结束
    设 抽.learner = {学习者}
    设 抽.seen = {已出}
    设 抽.n = {已出几道}
    设 抽.last = {进度.current 或}
    设 抽.score_line = 80
    设 抽.stale_days = 7
    设 抽.gap = 3
    设 抽.spread = 20
    设 抽中 = 查一行表 app.db question_pick_review {抽}
    设 题号 = {抽中.code 或}
    如果 {题号} 为空
      返回 {"error":"作答过的知识点下没有题可以复习"}
    结束
  否则
    设 抽.learner = {学习者}
    设 抽.level = {等级}
    设 抽.kind = {考点}
    设 抽.last = {进度.current 或}
    设 题号 = 查一值表 app.db question_pick {抽}
    如果 {题号} 为空
      返回 {"error":"这个等级和考点下没有题"}
    结束
  结束
结束

设 记.learner = {学习者}
设 记.level = {等级}
设 记.kind = {考点}
设 记.code = {题号}
设 记.reset = {清零}
设 记.lesson = {课文 或}
设 记.seen = {已出}
设 记.n = {已出几道}
设 记.mode = {模式值}
设 影响 = 写库表 app.db quiz_state_pick {记}
设 进度 = 查一行表 app.db quiz_state_one {查}

设 取.code = {题号}
设 题 = 查一行表 app.db question_show {取}
设 拆.题干 = {题.stem}
设 拆.题型 = {题.qtype}
设 拆.种子 = {学习者}|{题号}|{进度.seq}
设 卡 = 拆选项 {拆}
设 卡片.code = {题号}
设 卡片.head = {题.head}
设 卡片.stem = {卡.stem}
设 卡片.options = {卡.options}
设 卡片.verdict = 
设 卡片.mine = 

设 状态.card = {卡片}
设 状态.qtype = {题.qtype}
设 状态.phase = ask
设 状态.stat = {进度.stat}
设 状态.scope = {范围}
设 状态.cheer = 
# 这一轮答了几道、是不是按课练：界面据此决定出不出「结束并请老师总结」。
# 出了新题，上一轮的总结卡片收起来
设 状态.round_total = {进度.total}
设 状态.round_lesson = {课文 或}
设 状态.round_mode = {模式值}
设 状态.summary = 
响应 state {状态}

返回 {"ok":"1"}
