# 问老师：学习者发一句话，老师回一句。界面在 ui/teacher.ui。
#
# 每条消息先用「快」档判意图，再分几路：
#
#   出题  想练习、做题、测一下；或者把题目和自己的答案贴过来让老师判对错。
#         老师**不在对话里出题、不判分**（批改和学习记录都在做题页），只按
#         消息找到对应的课文，回一句话加做题页的链接（#做题?lesson=课文编号，
#         跟 kg/__main__.py 的 quiz_link 同一个写法）和这一课的「读课文」。
#         找不到能出题的课文、又提到了具体语法（keywords 不空）就退到按等级、
#         考点（#做题?level=N4&kind=接续），再没有就是不带参数的做题页，并且
#         说明找不到。
#         没指定具体内容（「给我出点题」「考考我」「练练我薄弱的」，keywords
#         空）看学情（review_brief）：
#           没有作答记录  按等级出（提到了就用，没提 N5），说明「还没有记录，
#                         先做几道我才知道你哪里弱」
#           提到了等级或考点  按它出；这一级有得分低于 80 的点就再附「复习
#                         薄弱点」并提一句是哪几个点
#           都没提        「复习薄弱点」（#做题?mode=review），一句话说依据
#                         （得分最低的几个点和分数，没有得分就是最近答错的点），
#                         再附 progress_pick 推荐的那一课「练这一课」
#         这一路都不调回答的模型，回复用模板拼。
#   进度  问自己的情况：学得怎么样、哪里薄弱、接下来学什么、N4 还差什么。
#         「平衡」档，提示词以进度摘要为主，加上按进度推荐的一课
#         （progress_pick：掌握得分低于 80 的点优先，没有得分退回最近答错、
#         现在能学）；回复附「读课文」「练这一课」（这一课没题就是
#         按等级的做题页），有作答记录的再附「复习薄弱点」。
#   教材  问教材整体：教材里有什么、N4 有哪些课、有没有讲〜的课。「平衡」档，
#         提示词里放课文目录（lesson_catalog：提到等级就只列那一级，否则
#         全部，按等级分组只列标题）、标题或条目直接对上的课、按进度推荐
#         的课；回复附这些课的「读课文」和「打开教材」。
#         单独成一路而不并进讲解：讲解的提示词里是一两篇课文的**正文**，
#         这里要的是**目录**，两样都塞进去提示词翻倍、模型也容易拿正文去
#         答「有哪些课」；分开判还能在对话记录里看出哪些问题是问教材的。
#   讲解  讲语法、问用法、问区别、闲聊（判成「其他」的也走这一路）。用「平衡」
#         档回答，提示词里带上库里最相关的一两篇课文正文、进度摘要和最近
#         几轮对话；回答下面附第一篇参考课文的「读课文」，能出题的再附
#         「练一练」。
#
# 除了出题，每一路的提示词里都有这个学习者的进度摘要（progress_brief：
# 已掌握 x/总数、累计答题和正确率、在学的点和它们的掌握得分（低的在前）、
# 最近答错的、现在能学的，
# ≤ 800 字；没答过题写「还没有作答记录」）。系统提示词里交代：结合进度
# 给建议，但不编造进度里没有的数据；网址由网站附在回复下面，模型不写。
#
# 意图判定不用「问JSON」：它解析失败直接报错，接口就是 500。这里先「问」拿
# 原文，再用「解析JSON」——解析不了得到空字典，{intent_json.intent 或 讲解} 取不到就
# 按讲解处理。intent 不是五个值之一的也按讲解。
#
# 链接：消息带 links 列表 [{href, text}]（前端一排画出来），由 chat_links
# 在 SQL 里拼成 JSON（转义交给 json_object），再「解析JSON」成列表。旧的
# link / link_text 照旧给一个（做题的那个优先，没有就是第一个），只认这
# 两个键的地方照样能用。
#
# 对话记录在 chat_message（学习记录，只进不改）。学习者那条和老师那条在
# 模型回来之后一起写，一个事务：模型调用出错时这一轮整个不记，不会留下
# 一句没有回答的问话。老师那条的 links 原文记在 links 列。
#
# 学习者不传就是 me，跟做题、学习记录同一个默认值；达标线（得分 80，
# 回落线 60）跟学习进度页一样。


# 进页面：把最近的对话放回消息流。只回 state，不推 messages——切一次界面
# 跑一次，推消息的话来回切几次就叠几份。state 里的 talk 是整条流，直接替换。
# 库里的 links 是 JSON 文本，逐条解析回列表（老数据只有 link 的，查询里已经
# 拼成一个元素的数组）。
接口 POST /teacher/state 动作 teacher_state
  用包 common db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 query.learner = {learner}
  设 history_rows = 查询表 app.db chat_history {query}
  遍历 row 于 {history_rows}
    设 row.links = 解析JSON {row.links}
  结束
  设 state.talk = {history_rows}
  设 state.mode = {run_mode}
  响应 state {state}
结束


接口 POST /teacher/send 动作 teacher_send
  用包 common db http

  设 learner = {learner 或}
  如果 {learner} 为空
    设 learner = me
  结束
  设 message = {content 或}
  如果 {message} 为空
    返回 {"error":"先写点什么再发"} 400
  结束

  # 最近几轮，不含这一句（这一句还没写进库）
  设 query.learner = {learner}
  设 recent_talk = 查一值表 app.db chat_recent {query}
  如果 {recent_talk} 为空
    设 recent_talk = （这是第一句，之前没有对话）
  结束

  # ---- 判意图（快档）----
  系统 你是日语学习网站的意图分类器。你只输出一个 JSON 对象，不回答学习者的问题，不加任何解释。
  问 intent_raw = 判断学习者发给日语老师的这条消息想干什么。intent 只能是五个值之一：「出题」= 想练习、做题、测一下、考考自己，或者把题目和自己的答案贴过来让老师判对错；「进度」= 问自己的学习情况，比如学得怎么样、哪里薄弱、错得多的是哪些、接下来学什么、某个等级还差什么；「教材」= 问网站教材或课文的整体情况，比如教材里有什么、某个等级有哪些课、有没有讲某个语法的课；「讲解」= 问语法、用法、意思、接续、几个说法的区别，请老师解释；「其他」= 打招呼、闲聊、和日语学习无关。输出一个 JSON 对象，键是：intent（出题 / 进度 / 教材 / 讲解 / 其他）；keywords（字符串数组，消息里提到的日语语法点或说法的原文，如 ために、ように、てから，没有就空数组）；level（提到的 JLPT 等级，N5 到 N1，没提就空串）；kind（想练的考点，只能是 挖空、意思、接续、找错句 之一，没提就空串）；grade（是不是贴了题目和答案让老师判对错，是 或 否）。学习者的消息：{message} 用 快
  设 intent_json = 解析JSON {intent_raw}
  设 intent = {intent_json.intent 或 讲解}
  设 known = 否
  如果 {intent} 等于 出题
    设 known = 是
  结束
  如果 {intent} 等于 进度
    设 known = 是
  结束
  如果 {intent} 等于 教材
    设 known = 是
  结束
  如果 {intent} 等于 讲解
    设 known = 是
  结束
  如果 {intent} 等于 其他
    设 known = 是
  结束
  如果 {known} 等于 否
    设 intent = 讲解
  结束

  设 search.keywords = {intent_json.keywords 或}
  设 search.message = {message}
  设 search.level = {intent_json.level 或}

  设 reply.who = 老师
  设 reply.link =
  设 reply.link_text =
  设 lesson_code =
  # 回复下面的链接，按顺序最多三个，href 空的不画
  设 links.href1 =
  设 links.text1 =
  设 links.href2 =
  设 links.text2 =
  设 links.href3 =
  设 links.text3 =

  如果 {intent} 等于 出题
    # ---- 出题：不出题、不判分，指去做题页 ----
    设 search.quiz = 1
    设 lesson_row = 查一行表 app.db lesson_find {search}
    设 opening = 想练习的话去做题页：
    # 先落到变量里再比：条件左边展开成空串时「如果  等于 是」认不出来
    设 wants_grading = {intent_json.grade 或 否}
    如果 {wants_grading} 等于 是
      设 opening = 对答案、判对错我在这里不做，去做题页做：那边判完给解析，还记进你的学习记录。
    结束
    设 word = {intent_json.keywords 或}
    设 scope_args.level = {intent_json.level 或}
    设 scope_args.kind = {intent_json.kind 或}
    设 scope = 查一行表 app.db quiz_link {scope_args}
    如果 {lesson_row.code 或} 不为空
      设 lesson_code = {lesson_row.code}
      设 reply.text = {opening}《{lesson_row.title}》（{lesson_row.level}）这一课有 {lesson_row.n} 道题，点下面的链接直接开始。题目、批改和解析都在做题页，我这边不出题也不判分；做完有不明白的再回来问我。
      设 reply.link = {lesson_row.link}
      设 reply.link_text = 去做题：《{lesson_row.title}》
      设 links.href2 = {lesson_row.read}
      设 links.text2 = 读课文：《{lesson_row.title}》
    否则
      如果 {word} 为空
        # ---- 没指定具体内容：看学情 ----
        设 brief_args.learner = {learner}
        设 brief_args.score_line = 80
        设 brief_args.level = {scope.level 或}
        设 brief_args.top = 3
        设 brief = 查一行表 app.db review_brief {brief_args}
        如果 {brief.answers} 等于 0
          # 没有作答记录：按等级出，没提等级就 N5
          如果 {scope.level 或} 为空
            设 scope_args.level = N5
            设 scope = 查一行表 app.db quiz_link {scope_args}
          结束
          设 reply.text = {opening}还没有你的作答记录，先做几道我才知道你哪里弱。先按 {scope.label} 出题，点下面的链接直接开始。我这边不出题也不判分；做完再来找我，就能按你的情况挑薄弱的练了。
          设 reply.link = {scope.link}
          设 reply.link_text = 去做题：{scope.label}
        否则
          如果 {scope.label 或} 不为空
            # 提到了等级或考点：按它出，这一级有低分点再提一句复习
            设 reply.text = {opening}按你说的出 {scope.label} 的题，点下面的链接直接开始。我这边不出题也不判分；做完有不明白的再回来问我。
            设 reply.link = {scope.link}
            设 reply.link_text = 去做题：{scope.label}
            如果 {brief.weak_n} 不等于 0
              设 reply.text = {opening}按你说的出 {scope.label} 的题，点下面的链接直接开始。这一范围里你还有几个点得分偏低（{brief.scores}），想专门练它们就点「复习薄弱点」。我这边不出题也不判分；做完有不明白的再回来问我。
              设 links.href2 = {brief.link}
              设 links.text2 = 复习薄弱点
            结束
          否则
            # 都没提：复习薄弱点，说依据，再附按进度推荐的那一课
            # 依据：有低分点说分数，没有就说最近答错的点。文本不能以「词+空格」
            # 开头（会被当成动词调用），所以低分点那句整句写在回复里
            设 basis = {brief.names}是你最近答错过的点
            如果 {brief.names} 为空
              设 basis = 目前没有得分偏低的点，复习时从你做过的点里挑久没做的、做错过的
            结束
            设 reply.text = {opening}按你的做题记录挑薄弱的练：{basis}。点「复习薄弱点」，题从这些点和你最近答错的题里出，一轮 10 道。我这边不出题也不判分；做完可以在做题页请我总结这一轮。
            如果 {brief.scores} 不为空
              设 reply.text = {opening}按你的做题记录挑薄弱的练，你现在得分最低的是 {brief.scores}。点「复习薄弱点」，题从这些点和你最近答错的题里出，一轮 10 道。我这边不出题也不判分；做完可以在做题页请我总结这一轮。
            结束
            设 reply.link = {brief.link}
            设 reply.link_text = 复习薄弱点
            设 pick_args.learner = {learner}
            设 pick_args.level = 
            设 pick_args.score_line = 80
            设 pick = 查一行表 app.db progress_pick {pick_args}
            如果 {pick.practice 或} 不为空
              设 lesson_code = {pick.code}
              设 links.href2 = {pick.practice}
              设 links.text2 = 练这一课：《{pick.title}》
            结束
          结束
        结束
      否则
        设 reply.link = {scope.link}
        如果 {scope.label 或} 不为空
          设 reply.text = {opening}没找到专门讲这个的课文，先按 {scope.label} 出题，点下面的链接直接开始。我这边不出题也不判分；做完有不明白的再回来问我。
          设 reply.link_text = 去做题：{scope.label}
        否则
          设 reply.text = {opening}没找到对应的课文，也没看出你想练哪个等级。点下面的链接打开做题页，在顶栏选好等级和考点再点「开始」。我这边不出题也不判分。
          设 reply.link_text = 打开做题页
        结束
      结束
    结束
    设 links.href1 = {reply.link}
    设 links.text1 = {reply.link_text}
  否则
    # ---- 要模型回答的几路：先取进度摘要 ----
    设 who.learner = {learner}
    设 who.line = 80
    设 who.keep = 60
    设 who.level = {intent_json.level 或}
    设 progress = 查一值表 app.db progress_brief {who}

    系统 你是一位耐心的日语老师，学生是中国人。用中文讲解，日语例句给出原文和中文意思。回答简洁、讲清重点，不要客套。你只讲解，不在对话里出题、不给学生判分；学生想练习时请他去做题页。提示词里会给你这个学生的学习进度（网站统计的），可以结合进度给建议，但不要编造进度里没有的数据（没给的数字、没列出的知识点不要说）。课文和做题页的链接由网站附在你的回复下面，你不要自己写网址。

    如果 {intent} 等于 进度
      # ---- 进度：以进度摘要为主，推荐一课 ----
      设 pick_args.learner = {learner}
      设 pick_args.level = {intent_json.level 或}
      # 掌握得分低于这条线的点优先推（没有得分退回原来的顺序）
      设 pick_args.score_line = 80
      设 pick = 查一行表 app.db progress_pick {pick_args}
      设 suggestion = （教材里没有能推荐的课文）
      如果 {pick.code 或} 不为空
        设 lesson_code = {pick.code}
        设 suggestion = 《{pick.title}》（{pick.level}，课文 {pick.code}）：{pick.summary} 推荐理由：{pick.reason}。这一课有 {pick.qcount} 道题。
        设 links.href1 = {pick.read}
        设 links.text1 = 读课文：《{pick.title}》
        如果 {pick.practice 或} 不为空
          设 links.href2 = {pick.practice}
          设 links.text2 = 练这一课：《{pick.title}》
        结束
      结束
      # 推荐的课没有题（或者一课都推不出来）：按等级的做题页
      如果 {links.href2} 为空
        设 scope_args.level = {intent_json.level 或}
        设 scope_args.kind = {intent_json.kind 或}
        设 scope = 查一行表 app.db quiz_link {scope_args}
        设 links.href2 = {scope.link}
        设 links.text2 = 打开做题页
        如果 {scope.label 或} 不为空
          设 links.text2 = 去做题：{scope.label}
        结束
      结束
      # 有作答记录：再附「复习薄弱点」
      设 brief_args.learner = {learner}
      设 brief_args.score_line = 80
      设 brief_args.level = 
      设 brief_args.top = 3
      设 brief = 查一行表 app.db review_brief {brief_args}
      如果 {brief.answers} 不等于 0
        设 links.href3 = {brief.link}
        设 links.text3 = 复习薄弱点
      结束
      问 answer_text = 下面是这个学生在网站上的学习进度（网站统计的，以它为准）：【{progress}】按进度推荐的下一课：【{suggestion}】最近的对话（旧的在前）：【{recent_talk}】学生现在说：【{message}】请以学习进度为主回答：说清他现在的情况（只用上面给的数字和知识点），指出薄弱的地方（有掌握得分的话，得分低的点先说），给出具体的下一步建议（先读或复习哪一课、练哪些点）。还没有作答记录的话，就建议从推荐的课开始、去做题页做几道。 用 平衡
      设 reply.text = {answer_text}
      设 reply.link = {links.href2}
      设 reply.link_text = {links.text2}
    否则
      如果 {intent} 等于 教材
        # ---- 教材：课文目录 + 直接对上的课 + 按进度推荐的课 ----
        设 catalog_args.level = {intent_json.level 或}
        设 catalog = 查一值表 app.db lesson_catalog {catalog_args}
        设 search.quiz = 0
        设 lessons = 查询表 app.db lesson_find {search}
        设 related =
        遍历 lesson_row 于 {lessons}
          如果 {lesson_row.strong} 等于 1
            设 related = {related}《{lesson_row.title}》（{lesson_row.level}，课文 {lesson_row.code}）：{lesson_row.summary}；
            如果 {links.href1} 为空
              设 lesson_code = {lesson_row.code}
              设 links.href1 = {lesson_row.read}
              设 links.text1 = 读课文：《{lesson_row.title}》
            否则
              设 links.href2 = {lesson_row.read}
              设 links.text2 = 读课文：《{lesson_row.title}》
            结束
          结束
        结束
        如果 {related} 为空
          设 related = （没有标题或条目直接对上的课）
        结束
        设 pick_args.learner = {learner}
        设 pick_args.level = {intent_json.level 或}
        设 pick_args.score_line = 80
        设 pick = 查一行表 app.db progress_pick {pick_args}
        设 suggestion = （没有）
        如果 {pick.code 或} 不为空
          设 suggestion = 《{pick.title}》（{pick.level}，课文 {pick.code}），推荐理由：{pick.reason}
          如果 {links.href2} 为空
            # 右边展开成空串时条件认不出来，空的换成「无」再比
            如果 {pick.read} 不等于 {links.href1 或 无}
              如果 {links.href1} 为空
                设 lesson_code = {pick.code}
              结束
              设 links.href2 = {pick.read}
              设 links.text2 = 读课文：《{pick.title}》（按进度推荐）
            结束
          结束
        结束
        设 links.href3 = #%E6%95%99%E6%9D%90
        设 links.text3 = 打开教材
        问 answer_text = 下面是网站教材的课文目录（按等级分组，只有标题）：【{catalog}】标题或条目跟学生的问题直接对上的课：【{related}】按学生进度推荐的课：【{suggestion}】这个学生的学习进度：【{progress}】最近的对话（旧的在前）：【{recent_talk}】学生现在说：【{message}】请根据目录回答学生关于教材的问题，推荐具体的课时写出课文标题；目录里没有的课不要编。 用 平衡
        设 reply.text = {answer_text}
        设 reply.link = {links.href1}
        设 reply.link_text = {links.text1}
        如果 {reply.link} 为空
          设 reply.link = {links.href3}
          设 reply.link_text = {links.text3}
        结束
      否则
        # ---- 讲解：平衡档，带课文正文、进度和最近几轮 ----
        设 search.quiz = 0
        设 lessons = 查询表 app.db lesson_find {search}
        设 reference =
        遍历 lesson_row 于 {lessons}
          设 reference = {reference}{lesson_row.body}
          如果 {lesson_code} 为空
            设 lesson_code = {lesson_row.code}
            设 links.href1 = {lesson_row.read}
            设 links.text1 = 读课文：《{lesson_row.title}》
          结束
          如果 {reply.link} 为空
            如果 {lesson_row.strong} 等于 1
              如果 {lesson_row.n} 不等于 0
                设 reply.link = {lesson_row.link}
                设 reply.link_text = 练一练：《{lesson_row.title}》（{lesson_row.n} 道题）
              结束
            结束
          结束
        结束
        如果 {reference} 为空
          设 reference = （库里没找到相关课文，按你自己的知识回答，拿不准的地方直说。）
        结束
        设 links.href2 = {reply.link}
        设 links.text2 = {reply.link_text}
        如果 {reply.link} 为空
          设 reply.link = {links.href1}
          设 reply.link_text = {links.text1}
        结束

        问 answer_text = 下面是网站课文库里和这个问题最相关的课文，讲解时以它为准（跟问题无关就忽略）：【{reference}】这个学生的学习进度（网站统计的，跟问题有关时可以结合着给建议）：【{progress}】最近的对话（旧的在前，接着这些往下聊）：【{recent_talk}】学生现在说：【{message}】请直接回答学生现在这句话。 用 平衡
        设 reply.text = {answer_text}
      结束
    结束
  结束

  设 links_json = 查一值表 app.db chat_links {links}
  设 reply.links = 解析JSON {links_json}

  事务 app.db
    设 ask_row.learner = {learner}
    设 ask_row.role = learner
    设 ask_row.content = {message}
    设 ask_row.intent = {intent}
    设 ask_row.lesson = {lesson_code}
    设 ask_row.link =
    设 ask_row.link_text =
    设 ask_row.links =
    设 ask_row.round_key =
    设 affected = 写库表 app.db chat_add {ask_row}
    设 reply_row.learner = {learner}
    设 reply_row.role = teacher
    设 reply_row.content = {reply.text}
    设 reply_row.intent = {intent}
    设 reply_row.lesson = {lesson_code}
    设 reply_row.link = {reply.link}
    设 reply_row.link_text = {reply.link_text}
    设 reply_row.links = {links_json}
    设 reply_row.round_key =
    设 affected = 写库表 app.db chat_add {reply_row}
  结束

  响应 messages {reply}
  设 state.intent = {intent}
  响应 state {state}
结束
