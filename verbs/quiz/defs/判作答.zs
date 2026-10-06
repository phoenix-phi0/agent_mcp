# 判作答：判一道题，返回 {correct, mine}。题目由调用方给，不读题库文件
# 参数：题
#
# 题是一个结构 {题型, 答案, 可接受, 作答}（或者它的 JSON 文本）。correct 是
# 1 / 0；mine 是从作答里认出来的：选择题是选的字母（没认出来是空），别的题型
# 是归一化以后的作答（批改时说「你写的是…」用）。「判对错」和 quiz 包的
# 「判题」「批量判题」「错题号」都用它——判对规则只写这一份。
#
# 规则（不调模型）：
#   比较前两边都归一化：NFKC（全角转半角）、去掉空白。
#   选择题  从作答里抓第一个选项字母（「C」「c」「选C」「答案是 C」都认），
#           跟答案（转大写）比。抓不到字母就是错。
#   接续题  整段比对，末尾的句号不计：只认标准答案和「可接受」里列的写法。
#           不能走填空题那套去掉词尾假名再比——接续题考的恰恰是词尾：答案
#           「書かせられる」，写「書かれる」，去掉假名都是「書」，会被判对。
#   填空题  （别的题型都算）比汉字，允许多写送假名：答案「憎」，写「憎」
#           「憎む」「憎い」都对，写「恨」才错。不允许的话，按自然语感写完整
#           词形会被判错——那是题目的问题，不是学生的。
#
# 可接受在库里存的是 JSON 文本（["…","…"]），也可能直接是列表；不是 JSON 的
# 一段文字当成一个写法。
#
# 参数坏了直接报错，不判 0：调用方拿 0 当「答错」记进学习记录，一个格式问题
# 会变成一条假的错题。

用包 common text

# 不写「如果 {q} 为空」：结构展开成 {…} 的样子，会被当成没展开的变量、算作空
设 q = 解析JSON {题}
设 bad = 相等 {q} {}
如果 {bad} 等于 是
  报错 判对错的参数要是一个结构：{题型,答案,可接受,作答}
结束
设 kind = {q.题型 或}
设 key = {q.答案 或}
如果 {key} 为空
  报错 判对错：没有标准答案
结束
设 given = {q.作答 或}
设 out.correct = 0

设 is_choice = 相等 {kind} 选择
如果 {is_choice} 等于 是
  设 out.mine = 取字母 {given}
  设 key = 归一化 {key}
  设 key = 转大写 {key}
  设 same = 相等 {out.mine} {key}
  如果 {same} 等于 是
    如果 {out.mine} 不为空
      设 out.correct = 1
    结束
  结束
  返回 {out}
结束

设 is_cont = 相等 {kind} 接续
如果 {is_cont} 等于 是
  设 mine = 归一化 {given}
  设 mine = 替换 {mine} 。+$
  设 out.mine = {mine}
  如果 {mine} 为空
    返回 {out}
  结束
  设 accept_raw = {q.可接受 或}
  设 accepted = 解析JSON {accept_raw}
  如果 {accepted} 为空
    设 accepted = 解析JSON []
    如果 {accept_raw} 不为空
      设 accepted = 列表加项 [] {accept_raw}
    结束
  结束
  设 accepted = 列表加项 {accepted} {key}
  遍历 alt 于 {accepted}
    设 alt_n = 归一化 {alt}
    设 alt_n = 替换 {alt_n} 。+$
    设 same = 相等 {alt_n} {mine}
    如果 {same} 等于 是
      设 out.correct = 1
      返回 {out}
    结束
  结束
  返回 {out}
结束

# 填空：整段一样；或者去掉作答末尾的送假名等于答案；或者两边去掉送假名一样
设 want = 归一化 {key}
设 mine = 归一化 {given}
设 out.mine = {mine}
设 same = 相等 {want} {mine}
如果 {same} 等于 是
  设 out.correct = 1
  返回 {out}
结束
设 mine_stem = 替换 {mine} [぀-ゟ]+$
设 same = 相等 {mine_stem} {want}
如果 {same} 等于 是
  设 out.correct = 1
  返回 {out}
结束
设 want_stem = 替换 {want} [぀-ゟ]+$
如果 {want_stem} 不为空
  设 same = 相等 {want_stem} {mine_stem}
  如果 {same} 等于 是
    设 out.correct = 1
  结束
结束
返回 {out}
