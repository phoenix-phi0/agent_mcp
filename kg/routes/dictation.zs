# 单词默写：出词、提示、判对、错词本。界面在 ui/quiz_dictation.ui。
#
# 两个方向：看中文写日语（给意思和等级，写汉字或假名都算对）、看汉字写读音
# （给汉字和意思，写假名读音；只出有汉字、汉字跟假名不一样的词）。判对用
# japanese 包的「判默写」，规则写在那个动词里；能出哪些词见
# queries/dictation_pick.sql。
#
# **单独记录**：作答记进 word_attempt，不写 attempt / mastery / score，不影响
# 知识点的掌握和得分。错词本从 word_attempt 现算（queries/dictation_book.sql）：
# 某词在某方向上最近一次答错就进本，之后这个方向上不看提示连续答对 2 次出本。
#
# 当前那个词记在 dictation_state 里，不由前端传：判的永远是库里记的那个，
# 同一个交两次只算一次。学习者不传就是 me，跟做题页同一个默认值。
#
# state 的键都带 d 前缀（dphase、dcard、dstat……），不跟做题页的 phase、card
# 撞：state 合并进全局的 shared，撞了的话这边出词，做题页的卡也跟着变。


# 进页面时：把上次选的方向、等级、题源填回去，显示这一轮的成绩。不推消息，
# 也不把上次没答完的那个词推出来（切一次界面跑一次）；点「开始」接着练。
接口 POST /dictation/state 动作 dictation_state
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}

  设 form_vals.dict_direction = {progress.dict_direction 或 看中文写日语}
  设 form_vals.dict_level = {progress.dict_level 或 全部}
  设 form_vals.dict_source = {progress.dict_source 或 随机}
  响应 form {form_vals}
  设 state.dstat = {progress.stat 或}
  响应 state {state}
结束


# 开始：按顶栏选的方向、等级、题源开一轮（计数清零）。
接口 POST /dictation/start 动作 dictation_start
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 result = 执行 scripts/dictation_pick.zs learner={learner} direction_label={dict_direction 或 看中文写日语} level={dict_level 或 全部} source_label={dict_source 或 随机} new_round=1
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
结束


# 下一个：接着这一轮，方向、等级、题源用库里记的（这一轮开始时选的）——
# 中途改了顶栏不算，点「开始」才按新的来，一轮里不会混着两个方向。
接口 POST /dictation/next 动作 dictation_next
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}
  如果 {progress.current_word 或} 为空
    返回 {"error":"还没出词，先点「开始」"} 400
  结束
  设 result = 执行 scripts/dictation_pick.zs learner={learner} direction_label={progress.dict_direction} level={progress.dict_level} source_label={progress.dict_source} new_round=0
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
结束


# 再来一轮：一轮结束时的按钮。方向、等级、题源照这一轮的，从头一轮。
接口 POST /dictation/again 动作 dictation_again
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}
  设 result = 执行 scripts/dictation_pick.zs learner={learner} direction_label={progress.dict_direction 或 看中文写日语} level={progress.dict_level 或 全部} source_label={progress.dict_source 或 随机} new_round=1
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
结束


# 练错词：一轮结束时的按钮。方向、等级照这一轮的，题源换成错词复习，顶栏
# 也跟着改。错词本空时界面上说一声（dphase=empty）。
接口 POST /dictation/wrong 动作 dictation_wrong
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}
  设 chosen_direction = {progress.dict_direction 或 看中文写日语}
  设 chosen_level = {progress.dict_level 或 全部}
  设 result = 执行 scripts/dictation_pick.zs learner={learner} direction_label={chosen_direction} level={chosen_level} source_label=错词复习 new_round=1
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
  设 form_vals.dict_direction = {chosen_direction}
  设 form_vals.dict_level = {chosen_level}
  设 form_vals.dict_source = 错词复习
  响应 form {form_vals}
结束


# 随机练一轮：错词本空时卡上的按钮。方向、等级照刚才的，题源换成随机。
接口 POST /dictation/random 动作 dictation_random
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}
  设 chosen_direction = {progress.dict_direction 或 看中文写日语}
  设 chosen_level = {progress.dict_level 或 全部}
  设 result = 执行 scripts/dictation_pick.zs learner={learner} direction_label={chosen_direction} level={chosen_level} source_label=随机 new_round=1
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
  设 form_vals.dict_direction = {chosen_direction}
  设 form_vals.dict_level = {chosen_level}
  设 form_vals.dict_source = 随机
  响应 form {form_vals}
结束


# 带地址参数进来（界面上的「载入」）：学习进度页给的是 #默写?source=review，
# 直接开一轮错词复习。还可以带 direction=reading（看汉字写读音）、
# level=N4。参数名特意不叫 dict_*：地址参数会盖掉每次提交的同名键，叫那个
# 名字的话顶栏下拉就改不动了。没给的照库里记的。
接口 POST /dictation/load 动作 dictation_load
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}
  设 chosen_direction = {progress.dict_direction 或 看中文写日语}
  如果 {direction 或 无} 等于 reading
    设 chosen_direction = 看汉字写读音
  结束
  如果 {direction 或 无} 等于 meaning
    设 chosen_direction = 看中文写日语
  结束
  设 chosen_level = {level 或}
  如果 {chosen_level} 为空
    设 chosen_level = {progress.dict_level 或 全部}
  结束
  设 chosen_source = {progress.dict_source 或 随机}
  如果 {source 或 无} 等于 review
    设 chosen_source = 错词复习
  结束
  如果 {source 或 无} 等于 random
    设 chosen_source = 随机
  结束
  设 result = 执行 scripts/dictation_pick.zs learner={learner} direction_label={chosen_direction} level={chosen_level} source_label={chosen_source} new_round=1
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
  设 form_vals.dict_direction = {chosen_direction}
  设 form_vals.dict_level = {chosen_level}
  设 form_vals.dict_source = {chosen_source}
  响应 form {form_vals}
结束


# 提示：首个假名和读音的字数，卡上显示。记下看过提示，交的时候
# word_attempt.hinted = 1——答对照样算对，但不算进「连续答对两次出错词本」。
# 已经交了的不给（没意义，也不改记录）。
接口 POST /dictation/hint 动作 dictation_hint
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}
  如果 {progress.current_word 或} 为空
    返回 {"error":"还没出词，先点「开始」"} 400
  结束
  如果 {progress.answered} 等于 1
    返回 {"error":"这个已经交过了，点「下一个」"} 400
  结束
  设 hint_args.learner = {learner}
  设 hint_args.word = {progress.current_word}
  设 hint_args.direction = {progress.direction}
  设 affected = 写库表 app.db dictation_state_hint {hint_args}
  设 word = 查一行表 app.db dictation_word {hint_args}

  设 card.code = {progress.round_from}-{progress.round_n}
  设 card.head = {word.head}
  设 card.stem = {word.bare}
  设 card.sub =
  如果 {progress.direction} 等于 reading
    设 card.stem = {word.kanji}
    设 card.sub = 意思：{word.bare}
  结束
  设 card.hint = {word.hint}
  设 card.verdict =
  设 card.right =
  设 card.mine =
  设 card.note =
  设 state.dcard = {card}
  设 state.dphase = ask
  设 state.dstat = {progress.stat}
  响应 state {state}
结束


# 交答案：判当前那个词，记进 word_attempt（一个事务），卡上原地出批改：
# 对错、正确的「汉字【读音】意思」、你写的、补充的一句（同义词也算对、
# 写成了同读音的另一个词、这是另一个读法……）。空答案回 400，不记。
接口 POST /dictation/answer 动作 dictation_answer
  用包 db http japanese

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db dictation_state_one {query}
  设 current = {progress.current_word 或}
  如果 {current} 为空
    返回 {"error":"还没出词，先点「开始」"} 400
  结束
  如果 {progress.answered} 等于 1
    返回 {"error":"这个已经交过了，点「下一个」"} 400
  结束
  设 answer = {dict_answer 或}
  如果 {answer} 为空
    返回 {"error":"还没写答案"} 400
  结束

  设 word_args.word = {current}
  设 word_args.direction = {progress.direction}
  设 word = 查一行表 app.db dictation_word {word_args}
  设 near = 查询表 app.db dictation_near {word_args}

  设 judge_args.方向 = {progress.direction}
  设 judge_args.作答 = {answer}
  设 judge_args.词 = {word}
  设 judge_args.候选 = {near}
  设 judged = 判默写 {judge_args}
  设 correct = {judged.correct}

  事务 app.db
    设 submit.learner = {learner}
    设 submit.word = {current}
    设 submit.answer = {answer}
    设 submit.correct = {correct}
    设 affected = 写库表 app.db dictation_state_answer {submit}
    # 影响 0：同一个刚被交过（两个请求挤在一起），不再记
    如果 {affected} 等于 1
      设 rec.learner = {learner}
      设 rec.word = {current}
      设 rec.direction = {progress.direction}
      设 rec.answer = {answer}
      设 rec.correct = {correct}
      设 rec.hinted = {progress.hinted}
      设 affected = 写库表 app.db dictation_attempt_insert {rec}
    结束
  结束

  设 progress = 查一行表 app.db dictation_state_one {query}
  设 card.code = {progress.round_from}-{progress.round_n}
  设 card.head = {word.head}
  设 card.stem = {word.bare}
  设 card.sub =
  如果 {progress.direction} 等于 reading
    设 card.stem = {word.kanji}
    设 card.sub = 意思：{word.bare}
  结束
  设 card.hint =
  如果 {progress.hinted} 等于 1
    设 card.hint = {word.hint}
  结束
  设 card.verdict = ✗不对
  如果 {correct} 等于 1
    设 card.verdict = ○对了
    如果 {progress.hinted} 等于 1
      设 card.verdict = ○对了（看了提示，不算进错词本的「连续答对」）
    结束
  结束
  设 card.right = 正确：{word.label}
  设 card.mine = 你写的：{answer}
  设 card.note = {judged.note 或}
  设 state.dcard = {card}
  设 state.dphase = done
  设 state.dstat = {progress.stat}
  响应 state {state}
结束


# 错词本：按学习者、方向（meaning / reading）、等级（全部 / N5..N1）列出来。
# 界面上没直接用（练错词走出词的查询），给别的地方和测试查。
接口 POST /dictation/book 动作 dictation_book
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 book_args.learner = {learner}
  设 book_args.direction = {direction 或 meaning}
  设 book_args.level = {level 或 全部}
  设 rows = 查询表 app.db dictation_book {book_args}
  设 group.book = {rows}
  响应 lists {group}
结束
