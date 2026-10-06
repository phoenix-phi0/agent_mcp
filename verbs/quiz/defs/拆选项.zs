# 拆选项：把选择题的题干拆成「题面」和「选项列表」，给界面画成一个个按钮用
# 参数：题
#
# 题是一个结构 {题干, 题型, 答案, 选了, 种子}。返回 {stem, options, picked,
# answer_key}，options 每项 {key, text, state}。不是选择题时只有 {stem, options}，
# stem 原样、options 是空列表。
#
# 选项写在题干里，一行一个：「A. …」（字母可以是全角，点可以是 ．、:：）。
# 不改题库格式去存结构化选项：quiz 包的「挑题」「判题」、老师的流程都按现在的
# 格式读，改了要动一串东西。在要画按钮的地方拆一下就够。
#
# 给了答案和选了：答案那项 right、选错的那项 wrong、其余 dim；没给就都是空
# （还没答）。
#
# 给了种子就按种子打乱选项顺序、按新位置重新标 A–D：题库里正确答案的位置是出题
# 人定的，按课练时同一课几道题的答案字母可能全一样（hb-n4-012 三道都是 A），点
# 同一个位置就全对。种子由调用方给（学习者|题号|第几次出题），出题和判题用同一个，
# 顺序对得上（稳定打乱用 sha256，不用 hash()——每个进程的盐不一样）。这时「选了」
# 是界面上的字母，picked 是它对应的原字母（拿去判对错），answer_key 是正确答案在
# 界面上的字母。没给种子，字母不变，picked 就是选了、answer_key 就是答案。

用包 common text

# 不写「如果 {q} 为空」：结构展开成 {…} 的样子，会被当成没展开的变量、算作空
设 q = 解析JSON {题}
设 bad = 相等 {q} {}
如果 {bad} 等于 是
  报错 拆选项的参数要是一个结构：{题干,题型,答案,选了}
结束
设 stem_all = {q.题干 或}
设 kind = {q.题型 或}
设 is_choice = 相等 {kind} 选择
如果 {is_choice} 等于 否
  设 out.stem = {stem_all}
  设 out.options = 解析JSON []
  返回 {out}
结束

设 key = {q.答案 或}
设 key = 归一化 {key}
设 key = 转大写 {key}
设 chosen = {q.选了 或}
设 chosen = 归一化 {chosen}
设 chosen = 转大写 {chosen}
设 seed = {q.种子 或}
设 marking = 否
如果 {key} 不为空
  如果 {chosen} 不为空
    设 marking = 是
  结束
结束

设 parts = 挑行 {stem_all} ^\s*([A-DＡ-Ｄ])\s*[.．、:：]\s*(.*)$
设 lines = 稳定打乱 {parts.hits} {seed}
设 options = 解析JSON []
设 picked = {chosen}
设 answer_key = {key}
设 answer_seen = 否
遍历 line 于 {lines} 序号 i
  # orig 是题库里的原字母，shown 是界面上的字母：打乱了就按新位置标
  设 orig = 归一化 {line.1}
  设 shown = {orig}
  如果 {seed} 不为空
    设 shown = 截取 ABCDEFGH {i} 1
    如果 {shown} 为空
      设 shown = {orig}
    结束
  结束
  设 is_answer = 相等 {orig} {key}
  设 is_chosen = 相等 {shown} {chosen}
  如果 {is_chosen} 等于 是
    设 picked = {orig}
  结束
  如果 {is_answer} 等于 是
    如果 {answer_seen} 等于 否
      设 answer_key = {shown}
      设 answer_seen = 是
    结束
  结束
  设 opt.key = {shown}
  设 opt.text = 替换 {line.2} \s+$
  设 opt.state =
  如果 {marking} 等于 是
    设 opt.state = dim
    如果 {is_chosen} 等于 是
      设 opt.state = wrong
    结束
    如果 {is_answer} 等于 是
      设 opt.state = right
    结束
  结束
  设 options = 列表加项 {options} {opt}
结束

设 out.stem = 替换 {parts.rest} ^\s+|\s+$
设 out.options = {options}
设 out.picked = {picked}
设 out.answer_key = {answer_key}
返回 {out}
