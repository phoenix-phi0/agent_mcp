# 做题：导入题目、出题、判题、记进学习记录。界面在 ui/quiz.ui。
#
# 题目的源文件在 workspace/japanese/content/bunpou/题库/（沿用旧题库格式，
# quiz 包的「挑题」「判题」也读它）。那个目录在本项目之外，读JSONL 碰不到，
# 所以由 py -m kg 读出来、把整批题放在请求里交给 /quiz/import——怎么进库
# 还是写在这里。
#
# 当前那道题记在 quiz_state 里，不由前端传：判的永远是库里记的那道，
# 同一道交两次只算一次（见 queries/quiz_state_answer.sql）。
#
# 判题用 quiz 包的「判对错」，跟「判题」同一套规则：选择题抓选项字母，
# 接续题整段比对（只认标准答案和「可接受」里列的写法）。
#
# 学习者不传就是 me，跟 learn.zs 同一个默认值。达标线也一样：80%、至少 8 题。


# 整批导入。整表清空重灌，在一个事务里：有坏题（缺题号、缺答案、题号重复）
# 就全部回滚，库里保持原样。条目对不上的题不进库、只计数，报告里说是哪道。
接口 POST /quiz/import
  用包 common db http

  设 题表 = {rows 或}
  如果 {题表} 为空
    返回 {"error":"没有题（rows 是空的）"} 400
  结束

  设 进库 = 0
  设 没进 = 0
  设 说明 = 

  事务 app.db
    设 影响 = 写库 app.db question_clear
    遍历 项 于 {题表} 序号 行
      设 题.code = {项.id 或}
      设 题.course = {项.课程 或}
      设 题.kind = {项.考点 或}
      设 题.difficulty = {项.难度 或}
      设 题.qtype = {项.题型 或}
      设 题.stem = {项.题干 或}
      设 题.answer = {项.答案 或}
      设 题.accept = {项.可接受 或}
      设 题.explain = {项.解析 或}
      设 题.item = {项.条目 或}
      设 题.lesson = {项.课文 或}
      设 影响 = 写库表 app.db question_insert {题}
      如果 {影响} 等于 1
        设 进库 = 相加 {进库} 1
      否则
        设 没进 = 相加 {没进} 1
        设 说明 = {说明}{题.code}的条目「{题.item}」不在库里；
      结束
    结束
  结束

  返回 {"questions":"{进库}","skipped":"{没进}","note":"{说明}"}
结束


# 进页面时：把上次选的等级、考点填回去，显示这一轮的成绩。
#
# 不把上次没答完的那道题重新推出来：进页面这个动作切一次界面就跑一次，
# 推出来的话来回切几次，消息流里就叠几份同一道题。上次那道就放着，
# 点「开始」或「下一题」接着做。
接口 POST /quiz/state 动作 quiz_state
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}

  设 表.pick_level = {进度.pick_level 或 全部}
  设 表.pick_kind = {进度.pick_kind 或 全部}
  响应 form {表}
  设 状态.stat = {进度.stat 或}
  设 状态.round_total = {进度.total 或 0}
  设 状态.round_lesson = {进度.lesson 或}
  响应 state {状态}
结束


# 下面三个接口都是出一道题，差别只在清不清零、从哪儿拿范围。出题本身在
# scripts/quiz_pick.zs，三处共用。
#
# 范围：按课练还是按等级考点，记在 quiz_state.lesson 里，不看每次提交带的
# 地址参数。
#   按课进来（#做题?lesson=hb-n4-118，老师、教材给的链接）  记下这一课
#   下一题、再来一轮                                    用库里记的那一课
#   开始（顶栏选等级考点）                              清掉，退出按课模式
# 早先「下一题」靠前端把地址参数并进提交来留在这一课：哪次提交没带上
# lesson（地址变了、直接调接口），下一道就悄悄换成了别的课的题。


# 开始：按顶栏的等级、考点出第一道，这一轮的计数清零。按课练着的话就此
# 退出按课模式——地址里的 lesson 不管（前端会把它并进提交），而且让前端
# 回到不带参数的 #做题：不然一刷新「载入」又按那一课出了。
接口 POST /quiz/start 动作 quiz_start
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 等级 = {pick_level 或 全部}
  设 考点 = {pick_kind 或 全部}
  # 课文给空（不能写成「课文= 」：参数按空格切，空值会吞掉后面那个）
  设 课文 = 
  设 结果 = 执行 scripts/quiz_pick.zs 学习者={学习者} 等级={等级} 考点={考点} 课文={课文} 清零=1
  如果 {结果.error 或} 不为空
    返回 {"error":"{结果.error}"} 404
  结束
  响应 go 做题
结束


# 下一题：不清零这一轮的计数。按课练着就还在库里记的那一课（这一课一轮
# 做完时出提示，不换课）；否则等级、考点用页面上现在选的——中途换了考点，
# 下一道就按新的出。
接口 POST /quiz/next 动作 quiz_next
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 等级 = {pick_level 或 全部}
  设 考点 = {pick_kind 或 全部}
  设 课文 = {进度.lesson 或}
  设 结果 = 执行 scripts/quiz_pick.zs 学习者={学习者} 等级={等级} 考点={考点} 课文={课文} 清零=0
  如果 {结果.error 或} 不为空
    返回 {"error":"{结果.error}"} 404
  结束
结束


# 再来一轮：按课练、这一课一轮做完时卡上的按钮。还是库里记的那一课，从头
# 一轮，计数清零。
接口 POST /quiz/again 动作 quiz_again
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 课文 = {进度.lesson 或}
  如果 {课文} 为空
    返回 {"error":"现在不是按课练，点「开始」出题"} 400
  结束
  设 结果 = 执行 scripts/quiz_pick.zs 学习者={学习者} 等级={进度.pick_level} 考点={进度.pick_kind} 课文={课文} 清零=1
  如果 {结果.error 或} 不为空
    返回 {"error":"{结果.error}"} 404
  结束
结束


# 按课文进来：界面上的「载入」。地址带着 lesson 打开做题页时前端调它，直接
# 出这一课的第一道，这一轮清零，库里记下在练这一课（之后「下一题」看它）。
#
# **lesson 不填回表单。** 填回去的话，之后点导航回到不带参数的 #做题，表单里
# 还留着 lesson，「开始」「下一题」照样只出那一课——人已经离开那一课了。
# 课文只认地址：地址里有，前端每次提交都会并进来；地址里没有就是没有。
#
# 没有课文、地址带的是等级或考点（#做题?level=N4&kind=接续，问老师找不到
# 具体课文时给的）：按它出第一道，顶栏填成这个等级考点。参数名特意不叫
# pick_level / pick_kind——地址参数会盖掉每次提交的同名键，叫那个名字的话
# 顶栏下拉就改不动了；叫 level / kind，之后「开始」「下一题」照旧看顶栏。
接口 POST /quiz/lesson 动作 quiz_lesson
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 课文 = {lesson 或}
  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 等级 = {进度.pick_level 或 全部}
  设 考点 = {进度.pick_kind 或 全部}
  如果 {课文} 为空
    如果 {level 或} 为空
      如果 {kind 或} 为空
        返回 {"error":"缺 lesson（哪一课），或者 level / kind（按等级、考点）"} 400
      结束
    结束
    设 等级 = {level 或 全部}
    设 考点 = {kind 或 全部}
  结束
  设 结果 = 执行 scripts/quiz_pick.zs 学习者={学习者} 等级={等级} 考点={考点} 课文={课文} 清零=1
  如果 {结果.error 或} 不为空
    返回 {"error":"{结果.error}"} 404
  结束
  设 表.pick_level = {等级}
  设 表.pick_kind = {考点}
  响应 form {表}
结束


# 作答：判当前那道，记进学习记录（跟 /learn/answer 同一套：流水、汇总、
# 掌握标记，一个事务），回对错和解析。
#
# 选择题看 choice（单选），接续题看 given（输入框）。
#
# 同一个事务里给这道题所属的知识点重算掌握得分（scripts/score_update.zs，
# 算法在 queries/score_calc.sql，打分参数的默认值也在那个脚本里——/learn/answer
# 和 /score/rebuild 共用）。跟当前分不同才记一行。变化放在 state.score_change
# （「推量判断 得分 42 → 51」），批改下面显示；不走 messages。
接口 POST /quiz/answer 动作 quiz_answer
  用包 common db http quiz

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

  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 当前 = {进度.current 或}
  如果 {当前} 为空
    返回 {"error":"还没出题，先点「开始」"} 400
  结束
  如果 {进度.answered} 等于 1
    返回 {"error":"这道已经答过了，点「下一题」"} 400
  结束

  设 键查.code = {当前}
  设 键 = 查一行表 app.db question_key {键查}
  设 作答 = {given 或}
  如果 {键.qtype} 等于 选择
    设 作答 = {choice 或}
  结束
  如果 {作答 或} 为空
    返回 {"error":"还没作答"} 400
  结束

  # 选择题的选项出题时打乱过：用出题时同一个种子再拆一次，把界面上的字母
  # 换回题库里的原字母再判（picked），批改时标的位置也跟界面上一致
  设 拆.题干 = {键.stem}
  设 拆.题型 = {键.qtype}
  设 拆.答案 = {键.answer}
  设 拆.选了 = {作答}
  设 拆.种子 = {学习者}|{当前}|{进度.seq}
  设 卡 = 拆选项 {拆}
  设 原作答 = {作答}
  如果 {键.qtype} 等于 选择
    设 原作答 = {卡.picked}
  结束

  设 判.题型 = {键.qtype}
  设 判.答案 = {键.answer}
  设 判.可接受 = {键.accept}
  设 判.作答 = {原作答}
  设 对错 = 判对错 {判}

  设 刚达标 = 否
  设 得分 = 
  事务 app.db
    设 交.learner = {学习者}
    设 交.code = {当前}
    设 交.choice = {原作答}
    如果 {键.qtype} 不等于 选择
      设 交.choice = 
    结束
    设 交.given = {given 或}
    设 交.correct = {对错}
    设 影响 = 写库表 app.db quiz_state_answer {交}

    # 影响 0：同一道刚被交过（两个请求挤在一起）。不再记学习记录
    如果 {影响} 等于 1
      设 记.learner = {学习者}
      设 记.point = {键.point}
      设 记.item = {当前}
      设 记.correct = {对错}
      # 交的是什么也记下（请老师总结时引用）：选择题是题库里的原字母
      设 记.answer = {原作答}
      设 影响 = 写库表 app.db attempt_insert {记}
      设 影响 = 写库表 app.db mastery_bump {记}

      设 条件.learner = {学习者}
      设 条件.point = {键.point}
      设 条件.rate = {正确率}
      设 条件.min_count = {最少题数}
      设 现状 = 查一行表 app.db mastery_one {条件}
      如果 {现状.ok} 等于 1
        如果 {现状.mastered} 等于 0
          设 刚达标 = 是
        结束
      结束
      设 标记.learner = {学习者}
      设 标记.point = {键.point}
      设 标记.mastered = {现状.ok}
      设 影响 = 写库表 app.db mastery_set {标记}

      设 打分 = 执行 scripts/score_update.zs 学习者={学习者} 知识点={键.point}
      设 得分 = {打分.text 或}
    结束
  结束

  # 「正确答案是 X」的 X 是界面上的字母（打乱后的），不是题库里的原字母
  设 判后.code = {当前}
  设 判后.correct = {对错}
  设 判后.shown = {卡.answer_key 或}
  设 结果 = 查一行表 app.db question_verdict {判后}

  # 判完把题卡重画一遍：选项标出对错（答案那项 right、选错的 wrong、其余
  # dim，有了 state 的按钮界面上就锁住了），下面是批改和解析。题卡的 code
  # 不变，界面不会当成新的一张去翻页。上面拆的那次已经带着答案和作答，
  # 标好了
  设 卡片.code = {当前}
  设 卡片.head = {键.head}
  设 卡片.stem = {卡.stem}
  设 卡片.options = {卡.options}
  设 卡片.verdict = {结果.text}
  设 卡片.mine = {作答}
  设 卡片.ok = {对错}

  # 达标的喜报放在 state.cheer，题卡上批改下面显示，下一道出题时清掉。
  # 不走 messages：做题页没有消息流，早先前端把它塞进了全局第一条流——
  # 喜报跑到问老师的对话里去了，做题页上什么都看不见
  设 状态.cheer = 
  如果 {刚达标} 等于 是
    设 状态.cheer = 「{键.point_label}」达标了，图上它后面的知识点可能解锁了。
  结束

  设 状态.score_change = {得分}

  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 状态.card = {卡片}
  设 状态.phase = done
  设 状态.stat = {进度.stat}
  设 状态.round_total = {进度.total}
  设 状态.round_lesson = {进度.lesson}
  响应 state {状态}
结束


# 请老师总结这一轮：按课练一轮做完时卡上的「请老师总结这一轮」，自由练答满
# 5 道后顶栏的「结束并请老师总结」。学习者点了才调模型（「平衡」档，十几秒、
# 占额度），不自动调。
#
# 「这一轮」见 queries/round_attempts.sql：quiz_state.round_from 之后的作答。
# 开始、按课进来、再来一轮时重记起点；自由练总结完也重记（「结束」就是这一轮
# 到此为止，接着做是新的一轮）。按课练总结完不动，「再来一轮」才开新的。
#
# 提示词：本轮每道题（知识点·条目、课文、对错、题干、选项内容、正确答案、
# 学习者的作答、解析）+ 进度摘要（progress_brief，跟问老师同一段）。系统
# 提示词沿用问老师的人设，加上：不出新题、不重新判分、不编造数据。
#
# 结果写进对话记录（chat_message，intent=总结）：学习者一条简短的「（做完
# 一轮：范围，x/y）请老师总结」、老师一条总结全文带链接（读课文、再练这一课
# ——错得最多的那课，去问老师接着聊）。到问老师页历史里看得到，chat_recent
# 也带着它，接着问「刚才那轮怎么样」接得上。
#
# 做题页上：总结放在 state.summary（{text, read, practice, chat}），界面画成
# 一张总结卡片。做题页没有消息流，不走 messages。本轮 0 题时回 400 和一句话，
# 不调模型。模型出错时路由器回 502 和一句人话（error），页面弹提示条；对话
# 记录在模型回来之后才写，出错时不留半截。
接口 POST /quiz/summary 动作 quiz_summary
  用包 common db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 查.learner = {学习者}
  设 本轮 = 查一行表 app.db round_attempts {查}
  设 题数 = {本轮.n 或 0}
  如果 {题数} 等于 0
    返回 {"error":"这一轮还没有做题，做几道再请老师总结。"} 400
  结束

  设 谁.learner = {学习者}
  设 谁.rate = 80
  设 谁.min_count = 8
  设 谁.level = {本轮.level 或}
  设 进度 = 查一值表 app.db progress_brief {谁}

  系统 你是一位耐心的日语老师，学生是中国人。用中文讲解，日语例句给出原文和中文意思。回答简洁、讲清重点，不要客套。学生刚在网站的做题页做完一轮题，请你总结这一轮。题目网站已经判过分，对错以网站给的为准：你不出新题、不重新判分。提示词里会给你这一轮的每道题和这个学生的学习进度（网站统计的），不要编造里面没有的数据（没给的数字、没列出的知识点不要说）。课文和做题页的链接由网站附在你的回复下面，你不要自己写网址。

  问 答 = 下面是学生这一轮做的题（{本轮.label}，答对 {本轮.ok_n} 道，共 {题数} 道；对错是网站判的）。选择题的选项在学生的界面上打乱过顺序，所以只给了选项的内容、没给字母，提到学生选了什么时请说内容。【{本轮.text}】这个学生整体的学习进度：【{进度}】请这样写：第一句是总评，写明本轮 {本轮.ok_n}/{题数}；然后按知识点说哪里错了、为什么错（结合解析，引用学生选的或写的内容）；有容易混的说法就说怎么区分；最后给下一步建议（先复习哪一课、练哪些点；进度里有掌握得分的话，得分低的点优先）。全对的话简短肯定，说说接下来可以往哪儿走。不要出新题。全文控制在 600 字以内。 用 平衡
  如果 {答} 为空
    返回 {"error":"老师这次没有给出总结，过一会儿再试。"} 502
  结束

  # 链接：错得最多的那课「读课文」「再练这一课」，和「去问老师接着聊」
  设 链.href1 = {本轮.read 或}
  设 链.text1 = 读课文：《{本轮.worst_title}》
  设 链.href2 = {本轮.practice 或}
  设 链.text2 = 再练这一课：《{本轮.worst_title}》
  设 链.href3 = #%E9%97%AE%E8%80%81%E5%B8%88
  设 链.text3 = 去问老师接着聊
  设 链文 = 查一值表 app.db chat_links {链}

  事务 app.db
    设 问话.learner = {学习者}
    设 问话.role = learner
    设 问话.content = （做完一轮：{本轮.label}，{本轮.ok_n}/{题数}）请老师总结
    设 问话.intent = 总结
    设 问话.lesson = {本轮.worst 或}
    设 问话.link =
    设 问话.link_text =
    设 问话.links =
    设 影响 = 写库表 app.db chat_add {问话}
    设 答话.learner = {学习者}
    设 答话.role = teacher
    设 答话.content = {答}
    设 答话.intent = 总结
    设 答话.lesson = {本轮.worst 或}
    设 答话.link = {链.href1}
    设 答话.link_text = {链.text1}
    设 答话.links = {链文}
    设 影响 = 写库表 app.db chat_add {答话}
    # 自由练：这一轮到此结束
    如果 {本轮.lesson 或} 为空
      设 影响 = 写库表 app.db quiz_state_round_end {查}
    结束
  结束

  设 总结.text = {答}
  设 总结.read = {链.href1}
  设 总结.practice = {链.href2}
  设 总结.chat = {链.href3}
  # 按课练、错得最多的就是在练的这一课：做题页上不给「再练这一课」——地址
  # 就是现在这个，点了不会重新载入；卡上本来就有「再来一轮」
  设 最差 = {本轮.worst 或 -}
  设 在练 = {本轮.lesson 或 无}
  如果 {最差} 等于 {在练}
    设 总结.practice =
  结束
  设 状态.summary = {总结}
  如果 {本轮.lesson 或} 为空
    # 自由练结束了：题卡收起，计数清零，等着点「开始」
    设 进度 = 查一行表 app.db quiz_state_one {查}
    设 状态.phase =
    设 状态.stat = {进度.stat}
    设 状态.round_total = {进度.total}
  结束
  响应 state {状态}
结束
