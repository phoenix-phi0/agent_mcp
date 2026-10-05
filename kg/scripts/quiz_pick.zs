# 出一道题。routes/quiz.zs 里「开始」「下一题」「按课文进来」三个接口共用，
# 用「执行 scripts/quiz_pick.zs 键=值 …」调。不放在 routes/ 下：那里的 .zs
# 是按「接口」块扫的，放一个没有接口的脚本进去看着像写漏了。
#
# 参数：
#   学习者
#   等级、考点   页面顶栏选的，「全部」表示不限
#   课文         给了就只在这一课的题里出，等级考点不管（见 question_pick.sql）
#   清零         1 = 这一轮的计数清零（开始），0 = 接着算（下一题）
#
# 成功：往响应的 state 里放一张新题卡（card），返回 {"ok":"1"}。
# 题卡：{code, head, stem, options:[{key,text,state}], verdict, mine}，界面上
# 「卡片 翻页 card.code」——code 一变就是新的一张。
# 失败：返回 {"error":…}，由调用的接口决定怎么回——子脚本的「返回」只结束
# 子脚本，结束不了接口。

用包 db http quiz

设 查.learner = {学习者}
设 进度 = 查一行表 app.db quiz_state_one {查}

设 范围 = 
如果 {课文 或} 不为空
  设 课查.lesson = {课文}
  设 课 = 查一行表 app.db lesson_scope {课查}
  如果 {课.code 或} 为空
    返回 {"error":"没有这一课：{课文}"}
  结束
  设 范围 = {课.scope}
结束

设 抽.learner = {学习者}
设 抽.level = {等级}
设 抽.kind = {考点}
设 抽.lesson = {课文 或}
设 抽.last = {进度.current 或}
设 题号 = 查一值表 app.db question_pick {抽}
如果 {题号} 为空
  如果 {课文 或} 不为空
    返回 {"error":"这一课还没有题"}
  结束
  返回 {"error":"这个等级和考点下没有题"}
结束

设 记.learner = {学习者}
设 记.level = {等级}
设 记.kind = {考点}
设 记.code = {题号}
设 记.reset = {清零}
设 影响 = 写库表 app.db quiz_state_pick {记}

设 取.code = {题号}
设 题 = 查一行表 app.db question_show {取}
设 拆.题干 = {题.stem}
设 拆.题型 = {题.qtype}
设 卡 = 拆选项 {拆}
设 卡片.code = {题号}
设 卡片.head = {题.head}
设 卡片.stem = {卡.stem}
设 卡片.options = {卡.options}
设 卡片.verdict = 
设 卡片.mine = 

设 进度 = 查一行表 app.db quiz_state_one {查}
设 状态.card = {卡片}
设 状态.qtype = {题.qtype}
设 状态.phase = ask
设 状态.stat = {进度.stat}
设 状态.scope = {范围}
响应 state {状态}

返回 {"ok":"1"}
