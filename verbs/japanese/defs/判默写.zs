# 判默写：判一道单词默写，返回 {correct, note, mine}
# 参数：默写
#
# 默写是一个结构 {方向, 作答, 词, 候选}（或者它的 JSON 文本）：
#   方向  meaning = 看中文写日语，reading = 看汉字写读音
#   作答  学习者写的
#   词    这道考的词 {kanji, kana, meaning}
#   候选  库里跟它沾边的别的词（同意思、同汉字、同读音的），{kanji, kana, meaning}
#         的列表，由调用方查好给（kg 的 queries/dictation_near.sql）
#
# correct 是 "1" / "0"；note 是给人看的一句补充（同义词也算对、写的是同读音的
# 另一个词、这是另一个读法……），没有就空；mine 是归一以后的作答。
#
# 比较前两边都归一：NFKC（全角字母数字、半角片假名统一）、去掉空白和句号逗号、
# 片假名换成平假名——「アウ」「あう」「ｱｳ」是同一个答案。不认罗马字。
#
# 看中文写日语：写这个词的汉字或假名都对；意思（去掉开头的 [N4] 等级）完全相同
# 的别的词，写它的汉字或假名也对（同义词，题面只给了意思，人没法知道要的是
# 哪一个）。写成同读音不同意思的词（会う 写成 合う）判错，note 里说写的是哪个词。
#
# 看汉字写读音：等于这个词的假名才对；同一个汉字的别的读音，意思也一样的也对，
# 意思不一样的判错，note 里说「这是另一个读法」。
#
# 候选由调用方给、不在这里查库：规则跟库无关，这里只管「怎么算一样」，测试直接
# 喂结构就能测全。参数坏了直接报错，不判 0：调用方拿 0 当「答错」记进作答记录，
# 一个格式问题会变成一条假的错词。

用包 common text

设 args = 解析JSON {默写}
设 bad = 相等 {args} {}
如果 {bad} 等于 是
  报错 判默写的参数要是一个结构：{方向,作答,词,候选}
结束
设 direction = {args.方向 或}
设 is_meaning = 相等 {direction} meaning
设 is_reading = 相等 {direction} reading
如果 {is_meaning} 等于 否
  如果 {is_reading} 等于 否
    报错 判默写：方向要是meaning或reading，给的是「{direction}」
  结束
结束
设 word_raw = {args.词 或}
设 word = 解析JSON {word_raw}
设 kana = {word.kana 或}
如果 {kana} 为空
  报错 判默写：没有考的词（词.kana是空的）
结束
设 kanji = {word.kanji 或}
设 near_raw = {args.候选 或 []}
设 near = 解析JSON {near_raw}

# 归一：NFKC、去空白和句号逗号、片假名换平假名
设 answer = {args.作答 或}
设 mine = 归一化 {answer} 是
设 mine = 转平假名 {mine}
设 out.correct = 0
设 out.note =
设 out.mine = {mine}
如果 {mine} 为空
  设 out.note = 没有写答案
  返回 {out}
结束

# 意思去掉开头的等级「[N4] 」
设 meaning = {word.meaning 或}
设 meaning = 替换 {meaning} ^\s*\[N[1-5]\]\s*
设 meaning = 替换 {meaning} ^\s+|\s+$
设 kana_n = 归一化 {kana} 是
设 kana_n = 转平假名 {kana_n}

如果 {is_meaning} 等于 是
  设 kanji_n = 归一化 {kanji} 是
  设 kanji_n = 转平假名 {kanji_n}
  设 hit_kanji = 相等 {mine} {kanji_n}
  设 hit_kana = 相等 {mine} {kana_n}
  如果 {hit_kanji} 等于 是
    设 out.correct = 1
    返回 {out}
  结束
  如果 {hit_kana} 等于 是
    设 out.correct = 1
    返回 {out}
  结束
  # 写的是候选里的哪个词：意思一样就算对（同义词）；第一个意思不一样的记下来，
  # 都不算对时说「你写的是另一个词」
  设 other =
  遍历 c 于 {near}
    设 c_kanji = {c.kanji 或}
    设 c_kana = {c.kana 或}
    设 c_kanji_n = 归一化 {c_kanji} 是
    设 c_kanji_n = 转平假名 {c_kanji_n}
    设 c_kana_n = 归一化 {c_kana} 是
    设 c_kana_n = 转平假名 {c_kana_n}
    设 c_hit = 相等 {mine} {c_kanji_n}
    设 c_hit_kana = 相等 {mine} {c_kana_n}
    如果 {c_hit_kana} 等于 是
      设 c_hit = 是
    结束
    如果 {c_hit} 等于 是
      设 c_meaning = {c.meaning 或}
      设 c_meaning = 替换 {c_meaning} ^\s*\[N[1-5]\]\s*
      设 c_meaning = 替换 {c_meaning} ^\s+|\s+$
      # 候选怎么念给人听：「汉字【假名】意思」，没汉字或汉字就是假名时「假名 意思」
      设 c_shown = {c_kana} {c_meaning}
      如果 {c_kanji} 不为空
        设 c_same_kana = 相等 {c_kanji} {c_kana}
        如果 {c_same_kana} 等于 否
          设 c_shown = {c_kanji}【{c_kana}】{c_meaning}
        结束
      结束
      设 same = 相等 {c_meaning} {meaning}
      如果 {meaning} 为空
        设 same = 否
      结束
      如果 {same} 等于 是
        设 out.correct = 1
        设 out.note = 「{c_shown}」意思一样，也算对
        返回 {out}
      结束
      如果 {other} 为空
        设 other = {c_shown}
      结束
    结束
  结束
  如果 {other} 不为空
    设 out.note = 你写的是另一个词：{other}
  结束
  返回 {out}
结束

# 看汉字写读音：只认读音
设 hit_kana = 相等 {mine} {kana_n}
如果 {hit_kana} 等于 是
  设 out.correct = 1
  返回 {out}
结束
如果 {kanji} 为空
  返回 {out}
结束
遍历 c 于 {near}
  设 c_kanji = {c.kanji 或}
  设 c_kana = {c.kana 或}
  设 c_kana_n = 归一化 {c_kana} 是
  设 c_kana_n = 转平假名 {c_kana_n}
  设 same_kanji = 相等 {c_kanji} {kanji}
  设 same_kana = 相等 {mine} {c_kana_n}
  如果 {same_kanji} 等于 是
    如果 {same_kana} 等于 是
      # 同一个汉字的另一个读音：意思一样也算对，不一样提示「另一个读法」
      设 c_meaning = {c.meaning 或}
      设 c_meaning = 替换 {c_meaning} ^\s*\[N[1-5]\]\s*
      设 c_meaning = 替换 {c_meaning} ^\s+|\s+$
      设 same = 相等 {c_meaning} {meaning}
      如果 {meaning} 为空
        设 same = 否
      结束
      如果 {same} 等于 是
        设 out.correct = 1
        设 out.note = 「{kanji}」读【{c_kana}】也对
      否则
        设 c_shown = {c_kana} {c_meaning}
        设 c_same_kana = 相等 {c_kanji} {c_kana}
        如果 {c_same_kana} 等于 否
          设 c_shown = {c_kanji}【{c_kana}】{c_meaning}
        结束
        设 out.note = 这是另一个读法：{c_shown}。这里要的是「{meaning}」的读法
      结束
      返回 {out}
    结束
  结束
结束
返回 {out}
