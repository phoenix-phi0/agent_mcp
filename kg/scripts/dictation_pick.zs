# 单词默写出一个词。routes/dictation.zs 里「开始」「下一个」「再来一轮」
# 「练错词」「载入」共用，用「执行 scripts/dictation_pick.zs 键=值 …」调。
#
# 一轮 10 个词，一轮里不重复（dictation_state.round_seen 记着出过的）。
# 出够 10 个、或者挑不出没出过的了，就不出：state 里 dphase=end，dround 是
# 一句「这一轮做完了」，lists.round_wrong 是这一轮答错的词。
#
# 参数：
#   learner          学习者
#   direction_label  方向，界面上的中文：看中文写日语 / 看汉字写读音
#   level            全部 / N5..N1（意思开头的等级前缀）
#   source_label     题源：随机 / 错词复习
#   new_round        1 = 从头一轮（开始、再来一轮、练错词、载入），0 = 接着（下一个）
#
# 错词复习但错词本是空的：不出、不报错，dphase=empty，dempty 是一句话，
# 界面上给「随机练一轮」。返回里多一个 empty=1。
#
# 成功返回 {"ok":"1"}。词卡放在 state.dcard：{code, head, stem, sub, hint,
# verdict, right, mine, note}。state 的键都带 d 前缀（dphase、dcard……）：
# state 合并进全局的 shared，做题页用的是 phase、card，撞名的话一边出题
# 另一边的卡也跟着变。
# 失败返回 {"error":…}，由调用的接口决定怎么回。

用包 db http

设 query.learner = {learner}
设 progress = 查一行表 app.db dictation_state_one {query}

设 direction = meaning
如果 {direction_label} 等于 看汉字写读音
  设 direction = reading
结束
设 source = random
如果 {source_label} 等于 错词复习
  设 source = review
结束

设 seen =
设 seen_n = 0
如果 {new_round} 等于 0
  设 seen = {progress.round_seen 或}
  设 seen_n = {progress.round_n 或 0}
结束

设 rec.learner = {learner}
设 rec.direction_label = {direction_label}
设 rec.level = {level}
设 rec.source_label = {source_label}

设 word_id =
如果 {seen_n} 小于 10
  设 pick_args.learner = {learner}
  设 pick_args.direction = {direction}
  设 pick_args.level = {level}
  设 pick_args.source = {source}
  设 pick_args.seen = {seen}
  设 word_id = 查一值表 app.db dictation_pick {pick_args}
结束

如果 {word_id} 为空
  如果 {seen_n} 等于 0
    # 一个都挑不出来：记下这次的选择（下次进页面顶栏还是它），不出题
    设 affected = 写库表 app.db dictation_state_settings {rec}
    如果 {source} 等于 review
      设 state.dphase = empty
      设 state.dempty = 「{direction_label}」这个方向（等级：{level}）的错词本是空的——没有答错过的词，或者都已经连续答对两次了。先随机练一轮吧。
      设 state.dcard =
      设 state.dstat =
      响应 state {state}
      返回 {"ok":"1","empty":"1"}
    结束
    返回 {"error":"这个等级下没有能默写的词"}
  结束
  # 出够一轮，或者范围里的词都出过了
  设 wrong = 查询表 app.db dictation_round_wrong {query}
  设 group.round_wrong = {wrong}
  响应 lists {group}
  设 round_end.text = 这一轮做完了：答对 {progress.round_right} 个，共 {progress.round_total} 个。
  如果 {progress.round_right} 等于 {progress.round_total}
    设 round_end.text = 这一轮做完了：{progress.round_total} 个全对。
  结束
  设 state.dphase = end
  设 state.dround = {round_end}
  设 state.dstat = {progress.stat}
  响应 state {state}
  返回 {"ok":"1"}
结束

设 rec.word = {word_id}
设 rec.reset = {new_round}
设 rec.seen = {seen}
设 rec.n = {seen_n}
设 affected = 写库表 app.db dictation_state_pick {rec}
设 progress = 查一行表 app.db dictation_state_one {query}

设 word_args.word = {word_id}
设 word_args.direction = {direction}
设 word = 查一行表 app.db dictation_word {word_args}

设 card.code = {progress.round_from}-{progress.round_n}
设 card.head = {word.head}
设 card.stem = {word.bare}
设 card.sub =
如果 {direction} 等于 reading
  设 card.stem = {word.kanji}
  设 card.sub = 意思：{word.bare}
结束
设 card.hint =
设 card.verdict =
设 card.right =
设 card.mine =
设 card.note =

设 state.dcard = {card}
设 state.dphase = ask
设 state.dstat = {progress.stat}
响应 state {state}

返回 {"ok":"1"}
