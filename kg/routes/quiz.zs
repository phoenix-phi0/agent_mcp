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
# 学习者不传就是 me，跟 learn.zs 同一个默认值。掌握看得分（达标线 80、
# 回落线 60），判定在 scripts/mastery_update.zs，跟 /learn/answer 同一份。


# 整批导入。整表清空重灌，在一个事务里：有坏题（缺题号、缺答案、题号重复）
# 就全部回滚，库里保持原样。条目对不上的题不进库、只计数，报告里说是哪道。
接口 POST /quiz/import
  用包 common db http

  设 rows = {rows 或}
  如果 {rows} 为空
    返回 {"error":"没有题（rows 是空的）"} 400
  结束

  设 imported = 0
  设 skipped = 0
  设 note = 

  事务 app.db
    设 affected = 写库 app.db question_clear
    遍历 item 于 {rows} 序号 row
      设 question.code = {item.id 或}
      设 question.course = {item.课程 或}
      设 question.kind = {item.考点 或}
      设 question.difficulty = {item.难度 或}
      设 question.qtype = {item.题型 或}
      设 question.stem = {item.题干 或}
      设 question.answer = {item.答案 或}
      设 question.accept = {item.可接受 或}
      设 question.explain = {item.解析 或}
      设 question.item = {item.条目 或}
      设 question.lesson = {item.课文 或}
      设 affected = 写库表 app.db question_insert {question}
      如果 {affected} 等于 1
        设 imported = 相加 {imported} 1
      否则
        设 skipped = 相加 {skipped} 1
        设 note = {note}{question.code}的条目「{question.item}」不在库里；
      结束
    结束
  结束

  返回 {"questions":"{imported}","skipped":"{skipped}","note":"{note}"}
结束


# 进页面时：把上次选的等级、考点填回去，显示这一轮的成绩。
#
# 不把上次没答完的那道题重新推出来：进页面这个动作切一次界面就跑一次，
# 推出来的话来回切几次，消息流里就叠几份同一道题。上次那道就放着，
# 点「开始」或「下一题」接着做。
接口 POST /quiz/state 动作 quiz_state
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db quiz_state_one {query}

  设 form_vals.pick_level = {progress.pick_level 或 全部}
  设 form_vals.pick_kind = {progress.pick_kind 或 全部}
  响应 form {form_vals}
  设 state.stat = {progress.stat 或}
  设 state.round_total = {progress.total 或 0}
  设 state.round_lesson = {progress.lesson 或}
  设 state.round_mode = {progress.mode 或}
  响应 state {state}
结束


# 下面三个接口都是出一道题，差别只在清不清零、从哪儿拿范围。出题本身在
# scripts/quiz_pick.zs，三处共用。
#
# 范围：按课练还是按等级考点，记在 quiz_state.lesson 里，不看每次提交带的
# 地址参数。
#   按课进来（#做题?lesson=hb-n4-118，老师、教材给的链接）  记下这一课
#   下一题、再来一轮                                    用库里记的那一课
#   开始（顶栏选等级考点）                              清掉，退出按课模式
#
# 复习薄弱点（#做题?mode=review，问老师、学习进度页给的链接）同样记在库里
# （quiz_state.mode）：载入时记下，下一题、再来一轮看库里的，「开始」清掉。
# 早先「下一题」靠前端把地址参数并进提交来留在这一课：哪次提交没带上
# lesson（地址变了、直接调接口），下一道就悄悄换成了别的课的题。


# 开始：按顶栏的等级、考点出第一道，这一轮的计数清零。按课练着的话就此
# 退出按课模式——地址里的 lesson 不管（前端会把它并进提交），而且让前端
# 回到不带参数的 #做题：不然一刷新「载入」又按那一课出了。
接口 POST /quiz/start 动作 quiz_start
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 chosen_level = {pick_level 或 全部}
  设 chosen_kind = {pick_kind 或 全部}
  # lesson 给空（不能写成「lesson= 」：参数按空格切，空值会吞掉后面那个）
  设 lesson = 
  设 result = 执行 scripts/quiz_pick.zs learner={learner} level={chosen_level} kind={chosen_kind} lesson={lesson} new_round=1
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
  响应 go 做题
结束


# 下一题：不清零这一轮的计数。按课练着就还在库里记的那一课（一轮做完时
# 出提示，不换课）；否则等级、考点用页面上现在选的——中途换了考点，
# 下一道就按新的出（这一轮出过的条目照样不再出）。
接口 POST /quiz/next 动作 quiz_next
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db quiz_state_one {query}
  设 chosen_level = {pick_level 或 全部}
  设 chosen_kind = {pick_kind 或 全部}
  设 lesson = {progress.lesson 或}
  设 result = 执行 scripts/quiz_pick.zs learner={learner} level={chosen_level} kind={chosen_kind} lesson={lesson} new_round=0 mode={progress.mode 或}
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
结束


# 再来一轮：一轮做完时卡上的按钮，三种模式都有。按课练还是库里记的那一课，
# 从头一轮、计数清零（本课换一道没出过的题）；复习薄弱点重新挑一轮；自由练
# 按库里记的等级考点重新出一轮（优先换没出过、出得少的条目）。还没出过题
# （库里没有当前题）回 400。
接口 POST /quiz/again 动作 quiz_again
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 progress = 查一行表 app.db quiz_state_one {query}
  设 lesson = {progress.lesson 或}
  设 mode = {progress.mode 或}
  如果 {progress.current 或} 为空
    返回 {"error":"还没出过题，点「开始」出题"} 400
  结束
  设 result = 执行 scripts/quiz_pick.zs learner={learner} level={progress.pick_level} kind={progress.pick_kind} lesson={lesson} new_round=1 mode={mode}
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
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
#
# 地址带 mode=review（复习薄弱点，问老师、学习进度页给的）：进复习模式出题。
# 库里已经在复习、这一轮还没出够（刷新、来回切）就接着这一轮，不清零；
# 不然开新的一轮。一道都没答过的人不报错，界面上说先按等级做几道
# （phase=noreview），顶栏等级没选过的填成 N5。
接口 POST /quiz/lesson 动作 quiz_lesson
  用包 db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 lesson = {lesson 或}
  设 query.learner = {learner}
  设 progress = 查一行表 app.db quiz_state_one {query}
  设 chosen_level = {progress.pick_level 或 全部}
  设 chosen_kind = {progress.pick_kind 或 全部}
  设 mode = {mode 或}
  设 new_round = 1
  如果 {lesson} 为空
    如果 {mode 或 无} 等于 review
      # 已经在复习、这一轮没出够：接着这一轮
      如果 {progress.mode 或 无} 等于 review
        如果 {progress.round_n 或 0} 小于 10
          设 new_round = 0
        结束
      结束
    否则
      设 mode = 
      如果 {level 或} 为空
        如果 {kind 或} 为空
          返回 {"error":"缺 lesson（哪一课），或者 level / kind（按等级、考点），或者 mode=review"} 400
        结束
      结束
      设 chosen_level = {level 或 全部}
      设 chosen_kind = {kind 或 全部}
    结束
  否则
    设 mode = 
  结束
  设 result = 执行 scripts/quiz_pick.zs learner={learner} level={chosen_level} kind={chosen_kind} lesson={lesson} new_round={new_round} mode={mode}
  如果 {result.error 或} 不为空
    返回 {"error":"{result.error}"} 404
  结束
  设 form_vals.pick_level = {chosen_level}
  # 复习但一道没答过：界面让先按等级做几道，等级没选过就填 N5
  如果 {result.empty 或 0} 等于 1
    如果 {chosen_level} 等于 全部
      设 form_vals.pick_level = N5
      # 记进库：之后「进入时」的 /quiz/state 按库里的填顶栏，不记会变回「全部」
      设 level_args.learner = {learner}
      设 level_args.level = N5
      设 affected = 写库表 app.db quiz_state_level {level_args}
    结束
  结束
  设 form_vals.pick_kind = {chosen_kind}
  响应 form {form_vals}
结束


# 作答：判当前那道，记进学习记录（跟 /learn/answer 同一套：流水、汇总、
# 掌握标记，一个事务），回对错和解析。
#
# 选择题看 choice（单选），接续题看 given（输入框）。
#
# 同一个事务里给这道题所属的知识点重算掌握得分、再按得分改掌握标记
# （scripts/mastery_update.zs，/learn/answer 和 /score/rebuild 共用；得分算法在
# queries/score_calc.sql，判定规则在 queries/mastery_one.sql）。分跟当前分不同
# 才记一行。变化放在 state.score_change
# （「推量判断 得分 42 → 51」），批改下面显示；不走 messages。
接口 POST /quiz/answer 动作 quiz_answer
  用包 common db http quiz

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束

  设 query.learner = {learner}
  设 progress = 查一行表 app.db quiz_state_one {query}
  设 current = {progress.current 或}
  如果 {current} 为空
    返回 {"error":"还没出题，先点「开始」"} 400
  结束
  如果 {progress.answered} 等于 1
    返回 {"error":"这道已经答过了，点「下一题」"} 400
  结束

  设 key_args.code = {current}
  设 key = 查一行表 app.db question_key {key_args}
  设 answer = {given 或}
  如果 {key.qtype} 等于 选择
    设 answer = {choice 或}
  结束
  如果 {answer 或} 为空
    返回 {"error":"还没作答"} 400
  结束

  # 选择题的选项出题时打乱过：用出题时同一个种子再拆一次，把界面上的字母
  # 换回题库里的原字母再判（picked），批改时标的位置也跟界面上一致
  设 split_args.题干 = {key.stem}
  设 split_args.题型 = {key.qtype}
  设 split_args.答案 = {key.answer}
  设 split_args.选了 = {answer}
  设 split_args.种子 = {learner}|{current}|{progress.seq}
  设 split = 拆选项 {split_args}
  设 orig_answer = {answer}
  如果 {key.qtype} 等于 选择
    设 orig_answer = {split.picked}
  结束

  设 judge_args.题型 = {key.qtype}
  设 judge_args.答案 = {key.answer}
  设 judge_args.可接受 = {key.accept}
  设 judge_args.作答 = {orig_answer}
  设 correct = 判对错 {judge_args}

  设 just_passed = 否
  设 score_text = 
  事务 app.db
    设 submit.learner = {learner}
    设 submit.code = {current}
    设 submit.choice = {orig_answer}
    如果 {key.qtype} 不等于 选择
      设 submit.choice = 
    结束
    设 submit.given = {given 或}
    设 submit.correct = {correct}
    设 affected = 写库表 app.db quiz_state_answer {submit}

    # 影响 0：同一道刚被交过（两个请求挤在一起）。不再记学习记录
    如果 {affected} 等于 1
      设 rec.learner = {learner}
      设 rec.point = {key.point}
      设 rec.item = {current}
      设 rec.correct = {correct}
      # 交的是什么也记下（请老师总结时引用）：选择题是题库里的原字母
      设 rec.answer = {orig_answer}
      设 affected = 写库表 app.db attempt_insert {rec}
      设 affected = 写库表 app.db mastery_bump {rec}

      # 重算得分、按得分改掌握标记，见 scripts/mastery_update.zs（跟
      # /learn/answer 同一份）
      设 scoring = 执行 scripts/mastery_update.zs learner={learner} point={key.point} line={line 或} keep={keep 或}
      设 score_text = {scoring.text 或}
      设 just_passed = {scoring.just}
    结束
  结束

  # 「正确答案是 X」的 X 是界面上的字母（打乱后的），不是题库里的原字母
  设 verdict_args.code = {current}
  设 verdict_args.correct = {correct}
  设 verdict_args.shown = {split.answer_key 或}
  设 result = 查一行表 app.db question_verdict {verdict_args}

  # 判完把题卡重画一遍：选项标出对错（答案那项 right、选错的 wrong、其余
  # dim，有了 state 的按钮界面上就锁住了），下面是批改（verdict，一行对错）
  # 和解析（explain）。题卡的 code 不变，界面不会当成新的一张去翻页。
  # 上面拆的那次已经带着答案和作答，标好了
  设 card.code = {current}
  设 card.head = {key.head}
  设 card.stem = {split.stem}
  设 card.options = {split.options}
  设 card.verdict = {result.text}
  设 card.explain = {result.explain}
  设 card.mine = {answer}
  设 card.ok = {correct}

  # 达标的喜报放在 state.cheer，题卡上批改下面显示，下一道出题时清掉。
  # 不走 messages：做题页没有消息流，早先前端把它塞进了全局第一条流——
  # 喜报跑到问老师的对话里去了，做题页上什么都看不见
  设 state.cheer = 
  如果 {just_passed} 等于 是
    设 state.cheer = 「{key.point_label}」达标了，图上它后面的知识点可能解锁了。
  结束

  设 state.score_change = {score_text}

  设 progress = 查一行表 app.db quiz_state_one {query}
  设 state.card = {card}
  设 state.phase = done
  设 state.stat = {progress.stat}
  设 state.round_total = {progress.total}
  设 state.round_lesson = {progress.lesson}
  设 state.round_mode = {progress.mode}
  响应 state {state}
结束


# 请老师总结这一轮：一轮做完时卡上的「请老师总结这一轮」（三种模式一样）。
# 学习者点了才调模型（「平衡」档，十几秒、占额度），不自动调。
#
# 「这一轮」见 queries/round_attempts.sql：quiz_state.round_from 之后的作答。
# 开始、按课进来、再来一轮时重记起点；总结完不动，那张一轮做完的卡还在，
# 「再来一轮」或「开始」才开新的。
#
# 早先自由练没有「一轮」，答满 5 道顶栏出「结束并请老师总结」，总结完这一轮
# 就此结束。现在自由练也是一轮 10 道（每道一个不同的条目）、做完出同一张卡，
# 那个中途结束的按钮去掉了：一轮本来就不长，两种「总结」一个结束一轮、一个
# 不结束，反而让人糊涂。
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
#
# 一轮只总结一次：两条记录带着 round_key（这一轮的起点和最后一道作答）。同
# 一轮再点「请老师总结」、刷新后再点，查到总结过就原样给回，不调模型、不再
# 写；两个请求前后脚都调了模型的，写库前在事务里再查一次，只留先写的那对。
#
# 模型慢的时候：平衡档是 cli:claude/sonnet，实测一次十秒上下；claude 卡住
# 90 秒算超时，排队等不到也一样，改用档位的 fallback（智谱），见
# tools/llm_router.py。前端只锁做题页自己的按钮，等的时候可以去别的页面。
接口 POST /quiz/summary 动作 quiz_summary
  用包 common db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 round_info = 查一行表 app.db round_attempts {query}
  设 question_n = {round_info.n 或 0}
  如果 {question_n} 等于 0
    返回 {"error":"这一轮还没有做题，做几道再请老师总结。"} 400
  结束

  # 链接：错得最多的那课「读课文」「再练这一课」，和「去问老师接着聊」
  设 links.href1 = {round_info.read 或}
  设 links.text1 = 读课文：《{round_info.worst_title}》
  设 links.href2 = {round_info.practice 或}
  设 links.text2 = 再练这一课：《{round_info.worst_title}》
  设 links.href3 = #%E9%97%AE%E8%80%81%E5%B8%88
  设 links.text3 = 去问老师接着聊
  设 links_json = 查一值表 app.db chat_links {links}

  # 这一轮总结过了（同一轮再点一次、刷新后再点）：原样给回那条，不再调模型、
  # 不再写一对。round_key 是这一轮的起点和最后一道作答，见 round_attempts.sql
  设 key.learner = {learner}
  设 key.round_key = {round_info.round_key 或}
  设 answer_text = 查一值表 app.db chat_summary_of {key}
  如果 {answer_text} 为空
    设 who.learner = {learner}
    设 who.line = 80
    设 who.keep = 60
    设 who.level = {round_info.level 或}
    设 progress = 查一值表 app.db progress_brief {who}

    系统 你是一位耐心的日语老师，学生是中国人。用中文讲解，日语例句给出原文和中文意思。回答简洁、讲清重点，不要客套。学生刚在网站的做题页做完一轮题，请你总结这一轮。题目网站已经判过分，对错以网站给的为准：你不出新题、不重新判分。提示词里会给你这一轮的每道题和这个学生的学习进度（网站统计的），不要编造里面没有的数据（没给的数字、没列出的知识点不要说）。课文和做题页的链接由网站附在你的回复下面，你不要自己写网址。

    问 answer_text = 下面是学生这一轮做的题（{round_info.label}，答对 {round_info.ok_n} 道，共 {question_n} 道；对错是网站判的）。选择题的选项在学生的界面上打乱过顺序，所以只给了选项的内容、没给字母，提到学生选了什么时请说内容。【{round_info.text}】这个学生整体的学习进度：【{progress}】请这样写：第一句是总评，写明本轮 {round_info.ok_n}/{question_n}；然后按知识点说哪里错了、为什么错（结合解析，引用学生选的或写的内容）；有容易混的说法就说怎么区分；最后给下一步建议（先复习哪一课、练哪些点；进度里有掌握得分的话，得分低的点优先）。全对的话简短肯定，说说接下来可以往哪儿走。不要出新题。全文控制在 600 字以内。 用 平衡
    如果 {answer_text} 为空
      返回 {"error":"老师这次没有给出总结，过一会儿再试。"} 502
    结束

    事务 app.db
      # 前后脚的另一个请求先写了：不再写一对（这次模型的回答丢掉，给回先写的那条）
      设 done_text = 查一值表 app.db chat_summary_of {key}
      如果 {done_text} 为空
        设 ask_row.learner = {learner}
        设 ask_row.role = learner
        设 ask_row.content = （做完一轮：{round_info.label}，{round_info.ok_n}/{question_n}）请老师总结
        设 ask_row.intent = 总结
        设 ask_row.lesson = {round_info.worst 或}
        设 ask_row.link =
        设 ask_row.link_text =
        设 ask_row.links =
        设 ask_row.round_key = {key.round_key}
        设 affected = 写库表 app.db chat_add {ask_row}
        设 reply_row.learner = {learner}
        设 reply_row.role = teacher
        设 reply_row.content = {answer_text}
        设 reply_row.intent = 总结
        设 reply_row.lesson = {round_info.worst 或}
        设 reply_row.link = {links.href1}
        设 reply_row.link_text = {links.text1}
        设 reply_row.links = {links_json}
        设 reply_row.round_key = {key.round_key}
        设 affected = 写库表 app.db chat_add {reply_row}
      否则
        设 answer_text = {done_text}
      结束
    结束
  结束

  设 summary.text = {answer_text}
  设 summary.read = {links.href1}
  设 summary.practice = {links.href2}
  设 summary.chat = {links.href3}
  # 按课练、错得最多的就是在练的这一课：做题页上不给「再练这一课」——地址
  # 就是现在这个，点了不会重新载入；卡上本来就有「再来一轮」
  设 worst = {round_info.worst 或 -}
  设 practicing = {round_info.lesson 或 无}
  如果 {worst} 等于 {practicing}
    设 summary.practice =
  结束
  设 state.summary = {summary}
  响应 state {state}
结束
