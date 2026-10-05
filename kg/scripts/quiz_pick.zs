# 出一道题。routes/quiz.zs 里「开始」「下一题」「按课文进来」「再来一轮」
# 几个接口共用，用「执行 scripts/quiz_pick.zs 键=值 …」调。不放在 routes/
# 下：那里的 .zs 是按「接口」块扫的，放一个没有接口的脚本进去看着像写漏了。
#
# 三种模式都是一轮一轮来，**一轮里每个知识点只出一题**——这里的知识点是语法
# 条目（question.item，如 ようだ、ために），不是图上的大节点。这一轮出过的
# 题号记在 quiz_state.round_seen，抽题的查询据此跳过出过的条目。一轮出够数、
# 或者挑不出没出过的条目了，就不出题，state 里 phase=end、round 是一句
# 「这一轮做完了」和地址，卡上「再来一轮」「请老师总结这一轮」。
#
# 参数：
#   learner      学习者
#   level、kind  等级、考点，页面顶栏选的，「全部」表示不限
#   lesson       课文。给了就是按课练（见 question_pick_lesson.sql）：一轮 = 本课
#                1 道 + 易混对比（没有就同级同考点）的别的条目各 1 道，一共
#                round_size 道（默认 5），等级考点不管；空就是按等级考点，
#                这时库里记的「在练的课」也清掉——点「开始」就退出按课模式
#   new_round    1 = 这一轮的计数清零、从头一轮（开始、按课进来、再来
#                一轮），0 = 接着算（下一题）
#   mode         review = 复习薄弱点（#做题?mode=review）：lesson 空、等级考点不管，
#                题从这个人的低分点、错题、久没做的已掌握点里挑（见
#                question_pick_review.sql），一轮 round_size 道（默认 10）。
#                一道都没答过：不出题、不报错，phase=noreview，界面上一句
#                「先按等级做几道」和「开始」，返回里多一个 empty=1。不给（空）
#                就是按课或按等级考点，库里记的模式清掉
#   round_size   一轮几道。自由练、复习默认 10，按课练默认 5。候选条目不够时
#                一轮就是候选条目数
#
# 成功：往响应的 state 里放一张新题卡（card），返回 {"ok":"1"}。
# 题卡：{code, head, stem, options:[{key,text,state}], verdict, explain, mine}，界面上
# 「卡片 翻页 card.code」——code 一变就是新的一张。选项是打乱过的（种子
# 「learner|题号|seq」，判题时 routes/quiz.zs 用同一个种子再拆一次）。
# 一轮做完：不出题，state 里 phase=end、round 是那句提示和地址（按课练给
# 「回教材」「换一课」，别的模式空），同样返回 {"ok":"1"}。
# state 里还有 round_total（这一轮答了几道）、round_lesson（按课练的课，自由练
# 是空）、round_mode（review 或空）；出新题时 summary 清空（总结卡片收起）。
# 失败：返回 {"error":…}，由调用的接口决定怎么回——子脚本的「返回」只结束
# 子脚本，结束不了接口。

用包 db http quiz

设 query.learner = {learner}
设 progress = 查一行表 app.db quiz_state_one {query}

设 scope =
设 seen =
设 seen_n = 0
# 「下一题」接着这一轮；新一轮（开始、按课进来、再来一轮）从头算
如果 {new_round} 等于 0
  设 seen = {progress.round_seen 或}
  设 seen_n = {progress.round_n 或 0}
结束
# 一轮做完时填这几样，最后统一回 phase=end
设 round_done = 0
设 round_end.text =
设 round_end.back =
设 round_end.more =
设 code =
# 条件左边展开成空串时认不出来，空的先当「无」
设 mode_val = {mode 或 无}
如果 {lesson 或} 不为空
  设 mode_val = 无
结束
如果 {mode_val} 不等于 review
  设 mode_val =
结束
如果 {lesson 或} 不为空
  设 lesson_args.lesson = {lesson}
  设 lesson_row = 查一行表 app.db lesson_scope {lesson_args}
  如果 {lesson_row.code 或} 为空
    返回 {"error":"没有这一课：{lesson}"}
  结束
  设 scope = {lesson_row.scope}
  设 pick_args.learner = {learner}
  设 pick_args.lesson = {lesson}
  设 pick_args.seen = {seen}
  设 pick_args.n = {seen_n}
  设 pick_args.size = {round_size 或 5}
  设 pick_args.last = {progress.current 或}
  设 picked = 查一行表 app.db question_pick_lesson {pick_args}
  设 code = {picked.code 或}
  如果 {code} 为空
    如果 {seen_n} 等于 0
      返回 {"error":"这一课还没有题"}
    结束
    # 这一轮出够了：说一声，不悄悄换到别的课。本课的题都轮到过了另外提一句
    设 cycle_args.learner = {learner}
    设 cycle_args.lesson = {lesson}
    设 cycle_args.seen = {seen}
    设 cycle = 查一行表 app.db lesson_cycle {cycle_args}
    设 round_done = 1
    设 round_end.text = 这一轮做完了（{progress.stat}）。再来一轮会换一道本课的题，对比题也换；也可以换一课，或者回教材再看看这一课。
    如果 {cycle.done 或 0} 等于 1
      设 round_end.text = 这一轮做完了（{progress.stat}）。这一课的{cycle.n}道题都出过了，再来一轮从头再轮一遍；也可以换一课，或者回教材再看看这一课。
    结束
    设 round_end.back = {lesson_row.back}
    设 round_end.more = {lesson_row.more}
  结束
否则
  如果 {mode_val 或 无} 等于 review
    # ---- 复习薄弱点 ----
    设 brief_args.learner = {learner}
    设 brief_args.score_line = 80
    设 brief_args.level =
    设 brief_args.top = 3
    设 basis = 查一行表 app.db review_brief {brief_args}
    如果 {basis.answers 或 0} 等于 0
      # 没有作答记录：不出题、不报错，库里不记复习模式
      设 state.phase = noreview
      设 state.card =
      设 state.scope =
      设 state.cheer =
      设 state.summary =
      设 state.round_mode = review
      设 state.round_lesson =
      设 state.round_total = 0
      响应 state {state}
      返回 {"ok":"1","empty":"1"}
    结束
    设 scope = 复习薄弱点：{basis.names}
    如果 {basis.names} 为空
      设 scope = 复习薄弱点
    结束
    设 round_len = {round_size 或 10}
    如果 {seen_n} 小于 {round_len}
      设 pick_args.learner = {learner}
      设 pick_args.seen = {seen}
      设 pick_args.n = {seen_n}
      设 pick_args.score_line = 80
      设 pick_args.stale_days = 7
      设 pick_args.spread = 20
      设 picked = 查一行表 app.db question_pick_review {pick_args}
      设 code = {picked.code 或}
      如果 {code} 为空
        如果 {seen_n} 等于 0
          返回 {"error":"作答过的知识点下没有题可以复习"}
        结束
      结束
    结束
    如果 {code} 为空
      # 这一轮出够了（或者作答过的条目都出过了）：等着「请老师总结」或「再来一轮」
      设 round_done = 1
      设 round_end.text = 这一轮复习做完了（{progress.stat}）。可以请老师总结这一轮，或者再来一轮。
    结束
  否则
    # ---- 自由练（按等级、考点）----
    设 round_len = {round_size 或 10}
    如果 {seen_n} 小于 {round_len}
      设 pick_args.learner = {learner}
      设 pick_args.level = {level}
      设 pick_args.kind = {kind}
      设 pick_args.seen = {seen}
      设 pick_args.last = {progress.current 或}
      设 code = 查一值表 app.db question_pick {pick_args}
      如果 {code} 为空
        如果 {seen_n} 等于 0
          返回 {"error":"这个等级和考点下没有题"}
        结束
      结束
    结束
    如果 {code} 为空
      # 出够一轮，或者这个范围的条目都出过了（候选不够一轮的题数）
      设 round_done = 1
      设 round_end.text = 这一轮做完了（{progress.stat}），{seen_n}道题各考一个不同的知识点。可以请老师总结这一轮，或者再来一轮。
    结束
  结束
结束

如果 {round_done} 等于 1
  设 state.phase = end
  设 state.round = {round_end}
  设 state.stat = {progress.stat}
  设 state.scope = {scope}
  设 state.cheer =
  设 state.round_total = {progress.total}
  设 state.round_lesson = {lesson 或}
  设 state.round_mode = {mode_val}
  响应 state {state}
  返回 {"ok":"1"}
结束

设 rec.learner = {learner}
设 rec.level = {level}
设 rec.kind = {kind}
设 rec.code = {code}
设 rec.reset = {new_round}
设 rec.lesson = {lesson 或}
设 rec.seen = {seen}
设 rec.n = {seen_n}
设 rec.mode = {mode_val}
设 affected = 写库表 app.db quiz_state_pick {rec}
设 progress = 查一行表 app.db quiz_state_one {query}

设 fetch_args.code = {code}
设 question = 查一行表 app.db question_show {fetch_args}
设 split_args.题干 = {question.stem}
设 split_args.题型 = {question.qtype}
设 split_args.种子 = {learner}|{code}|{progress.seq}
设 split = 拆选项 {split_args}
设 card.code = {code}
设 card.head = {question.head}
设 card.stem = {split.stem}
设 card.options = {split.options}
设 card.verdict =
设 card.explain =
设 card.mine =

设 state.card = {card}
设 state.qtype = {question.qtype}
设 state.phase = ask
设 state.stat = {progress.stat}
设 state.scope = {scope}
设 state.cheer =
# 这一轮答了几道、是不是按课练、是不是复习。出了新题，上一轮的总结卡片收起来
设 state.round_total = {progress.total}
设 state.round_lesson = {lesson 或}
设 state.round_mode = {mode_val}
设 state.summary =
响应 state {state}

返回 {"ok":"1"}
