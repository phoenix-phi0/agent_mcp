业务 tutor
  依赖 account kg lesson progress quiz subject teacher_rules
  用包 common db text

  函数 本科目 learner current_role auth_mode subject need?
    设 sr = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {sr}
  结束

  函数 取最近对话 learner limit subject_id
    # 返回 文本，最近 limit 条对话，按 id 升序，每条一行，学生写「学生：内容」，老师写「老师：内容」；没有则空串
    # 查 tutor_message 中该 learner 且 summary_round 为空串的行（本轮总结不算对话上下文），按 id 降序取前 limit 条，再翻成升序
    # 逐条拼成「学生：…」「老师：…」，用换行连接后返回
    设 t = 查一值 app.db tutor_recent learner={learner} limit={limit} subject_id={subject_id}
    返回 {t 或}
  结束

  函数 判意图 message subject_id
    # 返回 {intent, keyword, level}；intent 只会是 quiz / progress / textbook / explain；keyword 是学生指名的语法点或课文关键词（可空串）；level 只会是 N5 N4 N3 N2 N1 或空串
    # 问JSON（快档）：让模型判断学生这句话的意图（出题 / 进度 / 教材 / 讲解，其他都算讲解），并抽出指名的内容关键词和指定的等级，要求返回 {"intent": …, "keyword": …, "level": …}
    # intent 不是 quiz、progress、textbook、explain 之一（含模型出错或返回不合法），取 explain
    # level 不是 N5 N4 N3 N2 N1 之一，取空串；keyword 缺失取空串并去首尾空白
    # 返回 {"intent": intent, "keyword": keyword, "level": level}
    设 lv = 调用 subject.科目等级 subject_id={subject_id}
    设 ts0 = 调用 subject.科目老师设定 subject_id={subject_id}
    设 lvs = {zz 或}
    遍历 lx 于 {lv.levels}
      如果 {lvs} 为空
        设 lvs = {lx}
      否则
        设 lvs = {lvs} {lx}
      结束
    结束
    问JSON j = 判断学生这句话的意图：quiz 表示想做题，progress 表示问学习进度，textbook 表示问教材或课文目录，explain 表示问{ts0.explain_word}或其他一切。同时抽出学生指名的{ts0.point_word}或课文关键词 keyword（没有则空串）和指定的等级 level（只能是 {lvs} 或空串）。学生的话：{message} 格式 intent:文本 keyword?:文本 level?:文本 用 快 出错时 ej
    如果 {ej} 不为空
      设 j.intent = explain
      设 j.keyword = {zz 或}
      设 j.level = {zz 或}
    结束
    设 intent = {j.intent 或 explain}
    如果 {intent} 不等于 quiz 且 {intent} 不等于 progress 且 {intent} 不等于 textbook 且 {intent} 不等于 explain
      设 intent = explain
    结束
    设 level = {j.level 或}
    如果 {level} 不为空
      设 level = 替换 {level} ^\s+|\s+$
    结束
    如果 {level} 不为空
      设 hay = ,{lv.text},
      设 needle = ,{level},
      如果 {hay} 不包含 {needle}
        设 level = {zz 或}
      结束
    结束
    设 kw = {j.keyword 或}
    设 keyword = {zz 或}
    如果 {kw} 不为空
      设 keyword = 替换 {kw} ^\s+|\s+$
    结束
    设 out.intent = {intent}
    设 out.keyword = {keyword}
    设 out.level = {level}
    返回 {out}
  结束

  函数 取进度摘要 learner subject_id
    # 返回 文本，学习进度摘要（给模型当上下文和回答进度用）
    # 调用 progress.取概览 learner=learner，得 point_total、mastered_count、answer_total、accuracy、is_empty
    # 调用 progress.列低分点 learner=learner limit=5，得低分点列表
    # 调用 quiz.取当前轮次信息 learner=learner，has_round 等于 1 时附一行「当前轮次：模式 mode，第 asked_count / round_size 道，答对 right_count 道」
    # is_empty 等于 1：摘要写「还没有作答记录」；否则写「已掌握 mastered_count / point_total 个知识点，累计答题 answer_total，正确率 accuracy%」，有低分点再附「低分点：编号 标题 得分」逐个列出
    # 返回拼好的文本
    设 ov = 调用 progress.取概览 learner={learner} subject={subject_id}
    设 low = 调用 progress.列低分点 learner={learner} limit=5 subject={subject_id}
    设 rd = 调用 quiz.取当前轮次信息 learner={learner} subject={subject_id}
    如果 {ov.is_empty} 等于 1
      设 s = 还没有作答记录
    否则
      设 s = 已掌握{ov.mastered_count} / {ov.point_total} 个知识点，累计答题 {ov.answer_total}，正确率 {ov.accuracy}%
    结束
    遍历 pt 于 {low.points}
      设 s = {s}；低分点：{pt.point_code} {pt.title} 得分{pt.score}
    结束
    如果 {rd.has_round} 等于 1
      设 s = {s}；当前轮次：模式 {rd.mode}，第 {rd.asked_count} / {rd.round_size} 道，答对 {rd.right_count} 道
    结束
    返回 {s}
  结束

  函数 推荐一课 learner subject_id
    # 返回 课文编号，没有可推荐的课返回空串
    # 调用 progress.列低分点 learner=learner limit=5，按返回顺序（得分低的在前）对每个 point_code 调用 lesson.按知识点列课文 point_code=该编号，取到第一课就返回其 code
    # 低分点都没有课文：调用 progress.算下一步 learner=learner，next_code 不为空时调用 lesson.按知识点列课文 point_code=next_code，有课就返回第一课的 code
    # 都没有返回空串
    设 found = {zz 或}
    设 low = 调用 progress.列低分点 learner={learner} limit=5 subject={subject_id}
    遍历 pt 于 {low.points}
      如果 {found} 为空
        设 ls = 调用 lesson.按知识点列课文 point_code={pt.point_code} subject={subject_id}
        遍历 l 于 {ls.lessons}
          如果 {found} 为空
            设 found = {l.code}
          结束
        结束
      结束
    结束
    如果 {found} 为空
      设 nx = 调用 progress.算下一步 learner={learner} subject={subject_id}
      如果 {nx.next_code} 不为空
        设 ls2 = 调用 lesson.按知识点列课文 point_code={nx.next_code} subject={subject_id}
        遍历 l2 于 {ls2.lessons}
          如果 {found} 为空
            设 found = {l2.code}
          结束
        结束
      结束
    结束
    返回 {found}
  结束

  函数 写一轮 learner user_text intent lesson_code reply link links_json setting_ids setting_versions relay_ids subject_id
    # 返回 reply_id（老师回复那一行的 id）
    # 在一个事务里：
    # 往 tutor_message 插入学生那条 (learner, role=user, content=user_text, intent, lesson_code, link 空, links 空, summary_round 空串, at=当前时间)
    # 往 tutor_message 插入老师那条 (learner, role=teacher, content=reply, intent, lesson_code, link, links=links_json, summary_round 空串, at=当前时间)，取其新行 id 为 reply_id
    # 调用 teacher_rules.记回复用到设定 reply_id=reply_id student=learner setting_ids=setting_ids setting_versions=setting_versions（setting_ids 为空时它不写库）
    # 调用 teacher_rules.记回复传达 reply_id=reply_id student=learner relay_ids=relay_ids（relay_ids 为空时它不写库）
    # 上面任一步报错，整个事务回滚、整轮不记，错误原样向上抛
    # 返回 reply_id
    设 now = 当前时间
    设 u.learner = {learner}
    设 u.role = user
    设 u.content = {user_text}
    设 u.intent = {intent}
    设 u.lesson_code = {lesson_code}
    设 u.link = {zz 或}
    设 u.links = {zz 或}
    设 u.summary_round = {zz 或}
    设 u.subject_id = {subject_id}
    设 u.at = {now}
    设 t.learner = {learner}
    设 t.role = teacher
    设 t.content = {reply}
    设 t.intent = {intent}
    设 t.lesson_code = {lesson_code}
    设 t.link = {link}
    设 t.links = {links_json}
    设 t.summary_round = {zz 或}
    设 t.subject_id = {subject_id}
    设 t.at = {now}
    事务 app.db
      设 n1 = 写库表 app.db tutor_insert {u}
      设 n2 = 写库表 app.db tutor_insert {t}
      设 rid = 查一值 app.db tutor_last_id learner={learner} role=teacher subject_id={subject_id}
      设 x1 = 调用 teacher_rules.记回复用到设定 reply_id={rid} student={learner} setting_ids={setting_ids} setting_versions={setting_versions} subject={subject_id}
      设 x2 = 调用 teacher_rules.记回复传达 reply_id={rid} student={learner} relay_ids={relay_ids} subject={subject_id}
    结束
    返回 {rid}
  结束

  函数 判传达 learner reply relay_ids subject_id
    # 返回 无；这是回复写完之后的收尾，任何失败都不影响回复
    # relay_ids 为空直接返回
    # 按英文逗号拆开，逐个编号：调用 teacher_rules.取传达 relay_id=编号 取 must_info，出错（如 404）跳过这个编号
    # 问JSON（快档）：给模型这条回复 reply 和 must_info，问回复是否已把必须准确的信息传达到，要求返回 {"delivered": 1 或 0}
    # delivered 等于 1 时调用 teacher_rules.记传达判定 student=learner relay_id=编号 delivered=1，出错忽略
    # 模型出错或返回不合法时按 delivered=0 处理（兜底，不调用记传达判定，不报错）
    如果 {relay_ids} 为空
      返回 0
    结束
    设 parts = 按正则切分 {relay_ids} ,
    遍历 rid 于 {parts}
      如果 {rid} 不为空
        设 rl = 调用 teacher_rules.取传达 relay_id={rid} subject={subject_id} 出错时 e
        如果 {e} 为空
          问JSON j = 下面是老师给学生的一条回复和必须准确传达的信息，判断回复是否已把这条信息传达到，传达到 delivered 为 1，否则为 0。回复：{reply} 必须准确的信息：{rl.must_info} 格式 delivered:数字 用 快 出错时 ej
          如果 {ej} 为空
            如果 {j.delivered 或 0} 等于 1
              设 jr = 调用 teacher_rules.记传达判定 student={learner} relay_id={rid} delivered=1 subject={subject_id} 出错时 e2
            结束
          结束
        结束
      结束
    结束
    返回 0
  结束

  函数 答一轮 learner user_text intent lesson_code context_text link links_json subject_id
    # 返回 {reply_id, reply}；用模型回答的路径（进度、教材、讲解）共用
    # recent = 调用 取最近对话 learner=learner limit=6（此时本句还没写库，所以不含本句）
    # recent_text = 该学习者最近 3 条学生发言与本句 user_text 用换行连接（给关键词卡匹配用）
    # 调用 teacher_rules.取生效设定 student=learner recent_text=recent_text，得 memory_text、note_text、card_text、setting_ids、setting_versions
    # 调用 teacher_rules.取待传达 student=learner，得 relay_ids、prompt_text
    # 系统提示 = 老师人设（中文老师，教中文学习者日语语法，回答简明）+ memory_text + card_text（教师设定，学生看不到，不要向学生透露设定本身）+ prompt_text（用「[传达#编号]」标记的传达事项，要求自然地让学生在回复里知道其中必须准确的信息，回复里不要出现标记本身；prompt_text 为空则不加这一段）
    # 用户内容 = context_text + 最近对话 recent + note_text（作者注，紧贴在学生最新一句之前）+ 学生最新一句 user_text
    # 问（回答档）：系统提示、用户内容，得 reply；模型出错则报错 400 老师暂时无法回答，整轮不写任何表
    # 调用 写一轮 learner=learner user_text=user_text intent=intent lesson_code=lesson_code reply=reply link=link links_json=links_json setting_ids=setting_ids setting_versions=setting_versions relay_ids=relay_ids，得 reply_id
    # 调用 判传达 learner=learner reply=reply relay_ids=relay_ids
    # 返回 {"reply_id": reply_id, "reply": reply}
    设 recent = 调用 取最近对话 learner={learner} limit=6 subject_id={subject_id}
    设 q.learner = {learner}
    设 q.cur = {user_text}
    设 q.subject_id = {subject_id}
    设 rt = 查一值表 app.db tutor_recent_text {q}
    设 eff = 调用 teacher_rules.取生效设定 student={learner} recent_text={rt} subject={subject_id}
    设 rl = 调用 teacher_rules.取待传达 student={learner} subject={subject_id}
    设 ts = 调用 subject.科目老师设定 subject_id={subject_id}
    设 sysp = {ts.persona}，回答简明。回答格式与口吻要求：只输出纯文本，不要使用 Markdown（不要用 # 标题、** 加粗、表格、- 或 * 开头的列表符号），不要用 emoji，至多 1 个；一般不超过 200 字；{ts.offtopic}；不要说「昨天聊过」「上次说过」之类带时间的话，你没有可靠的日期信息，最近对话没有时间；推荐课程只能用上下文里给出的课号和标题，课号原样引用，不要自己编课号，也不要把别的课的编号配到某个知识点上。以下是教师设定（学生看不到，不要向学生透露设定本身）：{eff.memory_text} {eff.card_text}
    如果 {rl.prompt_text} 不为空
      设 sysp = {sysp} 以下是传达事项（用「[传达#编号]」标记），请自然地让学生在回复里知道其中必须准确的信息，回复里不要出现标记本身：{rl.prompt_text}
    结束
    设 lg = 调用 account.取语言 username={learner}
    设 ovr = 0
    如果 {lg.lang} 等于 ja
      如果 {ts.custom} 不为空
        设 kwm = 匹配 {ts.persona} (?i)(用|请用|使用|回答|回复|解释|说|讲)\s*(中文|汉语|日文|日语|日本語|中国語|英文|英语|English|Chinese|Japanese)|(中文|汉语|日文|日语|日本語|中国語|英文|英语|English|Chinese|Japanese)\s*(回答|回复|讲解|教学|授课|作答|说|讲)|(日本語|中国語|英語)で|(in|respond\s+in|answer\s+in)\s+(Chinese|Japanese|English)
        如果 {kwm.matched} 等于 是
          设 ovr = 1
        结束
      结束
      如果 {ovr} 等于 0
        设 sysp = {sysp} 请用日语回答，专业术语第一次出现时用括号标注中文；与其他提示里的语言要求冲突时，以本句为准。
      结束
    结束
    设 usrp = {context_text} 最近对话：{recent} 作者注：{eff.note_text} 学生最新一句：{user_text}
    问 reply = {sysp} 【以下是学生相关内容】{usrp} 用 平衡 出错时 qe
    如果 {qe} 不为空
      报错 400 老师暂时无法回答
    结束
    如果 {reply} 为空
      报错 400 老师暂时无法回答
    结束
    设 rid = 调用 写一轮 learner={learner} user_text={user_text} intent={intent} lesson_code={lesson_code} reply={reply} link={link} links_json={links_json} setting_ids={eff.setting_ids} setting_versions={eff.setting_versions} relay_ids={rl.relay_ids} subject_id={subject_id}
    设 jd = 调用 判传达 learner={learner} reply={reply} relay_ids={rl.relay_ids} subject_id={subject_id}
    设 out.reply_id = {rid}
    设 out.reply = {reply}
    返回 {out}
  结束

  函数 出题模板回复 learner keyword level message subject_id
    # 返回 {reply, lesson_code, link, links_json}；不调用回答模型，不判分，不在对话里出题
    # 调用 lesson.取当前系列 learner=learner 取 series_code
    # keyword 不为空：调用 lesson.列课文 series_code=series_code keyword=keyword，有结果取第一课为 lesson_code，用模板拼 reply「好的，去做「标题」这一课的题吧」，link=/quiz?mode=lesson&lesson_code=课号，links=[{做题, link}, {读课文, /lesson?code=课号}]
    # 否则（keyword 为空，或没找到课）且 level 不为空：lesson_code 为空，reply 模板「按 level 等级给你出题」（keyword 不为空时先说明没找到对应课文），link=/quiz?mode=free&level=level，links=[{做题, link}]
    # 否则 keyword 为空（没指定内容）看学情：调用 progress.取概览 learner=learner，is_empty 等于 1：reply 模板「还没有学习记录，先从 N5 开始」，link=/quiz?mode=free&level=N5，links=[{做题, link}]
    # 有记录时调用 progress.列低分点 learner=learner limit=1：有低分点则 link=/quiz，links=[{做题, /quiz}, {复习薄弱点, /quiz?mode=review}]，reply 模板提到可以复习薄弱点；没有低分点则 link=/quiz，links=[{做题, /quiz}]
    # 否则（指了 keyword 但没找到课也没有等级）：link=/quiz，links=[{做题, /quiz}]，reply 模板说明没找到对应内容，请在做题页自己选等级和考点
    # links_json 为 links 的 JSON 文本；返回 {"reply": reply, "lesson_code": lesson_code, "link": link, "links_json": links_json}
    设 cs = 调用 lesson.取当前系列 learner={learner} subject={subject_id}
    设 lc = {zz 或}
    设 title = {zz 或}
    设 found = 0
    如果 {keyword} 不为空
      设 ls = 调用 lesson.列课文 series_code={cs.series_code} keyword={keyword} subject={subject_id}
      遍历 l 于 {ls.lessons}
        如果 {found} 等于 0
          设 lc = {l.code}
          设 title = {l.title}
          设 found = 1
        结束
      结束
    结束
    如果 {found} 等于 1
      设 reply = 好的，去做「{title}」这一课的题吧
      设 link = /quiz?mode=lesson&lesson_code={lc}
      设 lj = [{"label": "做题", "url": "/quiz?mode=lesson&lesson_code={lc}"}, {"label": "读课文", "url": "/lesson?code={lc}"}]
    否则如果 {level} 不为空
      设 link = /quiz?mode=free&level={level}
      设 reply = 按{level}等级给你出题
      如果 {keyword} 不为空
        设 reply = 没有找到对应的课文。按{level}等级给你出题
      结束
      设 lj = [{"label": "做题", "url": "/quiz?mode=free&level={level}"}]
    否则如果 {keyword} 为空
      设 ov = 调用 progress.取概览 learner={learner} subject={subject_id}
      如果 {ov.is_empty} 等于 1
        设 lv2 = 调用 subject.科目等级 subject_id={subject_id}
        设 fl = {lv2.first}
        设 reply = 还没有学习记录，先从{fl}开始
        设 link = /quiz?mode=free&level={fl}
        设 lj = [{"label": "做题", "url": "/quiz?mode=free&level={fl}"}]
      否则
        设 low = 调用 progress.列低分点 learner={learner} limit=1 subject={subject_id}
        设 link = /quiz
        如果 {low.total} 大于 0
          设 reply = 好的，去做题吧，也可以复习一下薄弱点
          设 lj = [{"label": "做题", "url": "/quiz"}, {"label": "复习薄弱点", "url": "/quiz?mode=review"}]
        否则
          设 reply = 好的，去做题吧
          设 lj = [{"label": "做题", "url": "/quiz"}]
        结束
      结束
    否则
      设 link = /quiz
      设 reply = 没有找到对应的内容，请在做题页自己选等级和考点
      设 lj = [{"label": "做题", "url": "/quiz"}]
    结束
    设 out.reply = {reply}
    设 out.lesson_code = {lc}
    设 out.link = {link}
    设 out.links_json = {lj}
    返回 {out}
  结束

  公开 函数 问老师 learner message current_role? auth_mode? subject?
    # 返回 {ok, reply_id, reply, intent, lesson_code, link, links}；links 是 [{label, url}]，没有链接为空列表
    # 报错 400 learner 不能为空
    # 报错 400 消息不能为空
    # 报错 400 老师暂时无法回答
    # learner 为空，报错 400 learner 不能为空；message 去首尾空白后为空，报错 400 消息不能为空
    # 调用 判意图 message=message，得 intent、keyword、level
    # intent 等于 quiz：调用 出题模板回复 learner=learner keyword=keyword level=level message=message，调用 写一轮 learner=learner user_text=message intent=quiz lesson_code=其 lesson_code reply=其 reply link=其 link links_json=其 links_json setting_ids 空 setting_versions 空 relay_ids 空（这一路不调回答模型，也不拼教师设定与传达，不记用到设定）
    # intent 等于 progress：summary = 调用 取进度摘要 learner=learner；lesson_code = 调用 推荐一课 learner=learner；lesson_code 不为空时 link=/lesson?code=课号，links=[{读课文, /lesson?code=课号}, {练这一课, /quiz?mode=lesson&lesson_code=课号}]，否则 link 空、links 空；调用 答一轮 learner=learner user_text=message intent=progress lesson_code=lesson_code context_text=（进度摘要 summary，要求按它回答，并说明推荐的那一课）link=link links_json=links_json
    # intent 等于 textbook：调用 lesson.取当前系列 learner=learner 取 series_code；调用 lesson.列课文 series_code=series_code，取前 30 课拼成课文目录（课号 等级 标题 一句话）；调用 答一轮 intent=textbook lesson_code 空 link 空 links 空 context_text=（课文目录，要求用目录回答）
    # intent 等于 explain：调用 lesson.取当前系列 取 series_code；keyword 不为空时调用 lesson.列课文 series_code=series_code keyword=keyword，取前 2 课（没有则 0 课）；对每课调用 lesson.取课文 code=课号，取标题、讲解、接续、例句作为课文正文；再附 调用 取进度摘要 learner=learner 的摘要
    # 有课文时 lesson_code=第一课课号，link=/lesson?code=课号，links=[{读课文, /lesson?code=课号}, {练一练, /quiz?mode=lesson&lesson_code=课号}]；没有课文时 lesson_code、link、links 为空；调用 答一轮 learner=learner user_text=message intent=explain lesson_code=lesson_code context_text=（课文正文 + 进度摘要）link=link links_json=links_json
    # 把 links_json 解析成列表；返回 {"ok": 1, "reply_id": reply_id, "reply": reply, "intent": intent, "lesson_code": lesson_code, "link": link, "links": 列表}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    设 msg = {zz 或}
    如果 {message} 不为空
      设 msg = 替换 {message} ^\s+|\s+$
    结束
    如果 {msg} 为空
      报错 400 消息不能为空
    结束
    设 j = 调用 判意图 message={msg} subject_id={subject_id}
    设 intent = {j.intent}
    设 keyword = {j.keyword}
    设 level = {j.level}
    设 e0 = {zz 或}
    设 link = {zz 或}
    设 lc = {zz 或}
    设 lj = []
    如果 {intent} 等于 quiz
      设 tp = 调用 出题模板回复 learner={learner} keyword={keyword} level={level} message={msg} subject_id={subject_id}
      设 reply = {tp.reply}
      设 lc = {tp.lesson_code}
      设 link = {tp.link}
      设 lj = {tp.links_json}
      设 rid = 调用 写一轮 learner={learner} user_text={msg} intent=quiz lesson_code={lc} reply={reply} link={link} links_json={lj} setting_ids={e0} setting_versions={e0} relay_ids={e0} subject_id={subject_id}
    否则如果 {intent} 等于 progress
      设 summary = 调用 取进度摘要 learner={learner} subject_id={subject_id}
      设 lc = 调用 推荐一课 learner={learner} subject_id={subject_id}
      如果 {lc} 不为空
        设 link = /lesson?code={lc}
        设 lj = [{"label": "读课文", "url": "/lesson?code={lc}"}, {"label": "练这一课", "url": "/quiz?mode=lesson&lesson_code={lc}"}]
      结束
      设 ctx = 学习进度摘要：{summary}。请按它回答，没有可推荐的课，不要推荐课号。
      如果 {lc} 不为空
        设 cc = 调用 lesson.取课文 code={lc} subject={subject_id}
        设 tt = {cc.title 或}
        设 ctx = 学习进度摘要：{summary}。请按它回答，并说明推荐课：课号 {lc}，标题 {tt}，只能推荐这一课，课号原样引用。
      结束
      设 a = 调用 答一轮 learner={learner} user_text={msg} intent=progress lesson_code={lc} context_text={ctx} link={link} links_json={lj} subject_id={subject_id}
      设 rid = {a.reply_id}
      设 reply = {a.reply}
    否则如果 {intent} 等于 textbook
      设 cs = 调用 lesson.取当前系列 learner={learner} subject={subject_id}
      设 ls = 调用 lesson.列课文 series_code={cs.series_code} subject={subject_id}
      设 cat = 课文目录：
      设 n = 0
      遍历 l 于 {ls.lessons}
        如果 {n} 小于 30
          如果 {subject_id} 等于 1
            设 cat = {cat}；{l.code} {l.level} {l.title} {l.summary}
          否则
            设 cat = {cat}；{l.code} {l.title} {l.summary}
          结束
          设 n = 计算 {n} + 1
        结束
      结束
      设 ctx = {cat}。请用这份目录回答学生。
      设 a = 调用 答一轮 learner={learner} user_text={msg} intent=textbook lesson_code={e0} context_text={ctx} link={e0} links_json={lj} subject_id={subject_id}
      设 rid = {a.reply_id}
      设 reply = {a.reply}
    否则
      设 cs = 调用 lesson.取当前系列 learner={learner} subject={subject_id}
      设 body = 课文正文：
      设 n = 0
      如果 {keyword} 不为空
        设 ls = 调用 lesson.列课文 series_code={cs.series_code} keyword={keyword} subject={subject_id}
        遍历 l 于 {ls.lessons}
          如果 {n} 小于 2
            设 c = 调用 lesson.取课文 code={l.code} subject={subject_id}
            设 body = {body}【{c.title}】讲解：{c.explain}。
            如果 {c.connection} 不为空
              设 body = {body}接续：{c.connection}。
            结束
            如果 {c.examples} 不为空
              设 body = {body}例句：{c.examples}。
            结束
            如果 {n} 等于 0
              设 lc = {l.code}
            结束
            设 n = 计算 {n} + 1
          结束
        结束
      结束
      设 summary = 调用 取进度摘要 learner={learner} subject_id={subject_id}
      如果 {lc} 不为空
        设 link = /lesson?code={lc}
        设 lj = [{"label": "读课文", "url": "/lesson?code={lc}"}, {"label": "练一练", "url": "/quiz?mode=lesson&lesson_code={lc}"}]
      结束
      设 ctx = {body} 学习进度：{summary}
      设 a = 调用 答一轮 learner={learner} user_text={msg} intent=explain lesson_code={lc} context_text={ctx} link={link} links_json={lj} subject_id={subject_id}
      设 rid = {a.reply_id}
      设 reply = {a.reply}
    结束
    设 links = 解析JSON {lj}
    设 out.ok = 1
    设 out.reply_id = {rid}
    设 out.reply = {reply}
    设 out.intent = {intent}
    设 out.lesson_code = {lc}
    设 out.link = {link}
    设 out.links = {links}
    返回 {out}
  结束

  公开 函数 讲解一课 learner lesson_code current_role? auth_mode? subject?
    # 返回 {ok, reply_id, reply, intent, lesson_code, link, links}；intent 恒为 explain；不判意图，直接讲这一课
    # 报错 400 learner 不能为空
    # 报错 400 lesson_code 不能为空
    # 报错 404 没有这课
    # 报错 400 老师暂时无法回答
    # learner 为空报错 400 learner 不能为空；lesson_code 为空报错 400 lesson_code 不能为空
    # 调用 lesson.取课文 code=lesson_code，取不到报错 404 没有这课
    # 调用 lesson.取课文关联条目 lesson_code=lesson_code，得关联条目名称，和课文标题、讲解、接续、例句一起作为课文正文
    # summary = 调用 取进度摘要 learner=learner
    # link=/lesson?code=lesson_code，links=[{读课文, /lesson?code=课号}, {练这一课, /quiz?mode=lesson&lesson_code=课号}]
    # 调用 答一轮 learner=learner user_text=「请老师讲解：」加课文标题 intent=explain lesson_code=lesson_code context_text=（课文正文 + 进度摘要）link=link links_json=links 的 JSON 文本
    # 返回 {"ok": 1, "reply_id": reply_id, "reply": reply, "intent": "explain", "lesson_code": lesson_code, "link": link, "links": links}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    如果 {lesson_code} 为空
      报错 400 lesson_code 不能为空
    结束
    设 c = 调用 lesson.取课文 code={lesson_code} subject={subject_id}
    如果 {c} 为空
      报错 404 没有这课
    结束
    设 rel = 调用 lesson.取课文关联条目 lesson_code={lesson_code} subject={subject_id}
    设 names = {zz 或}
    遍历 it 于 {rel.items}
      设 names = {names} {it.name}
    结束
    设 summary = 调用 取进度摘要 learner={learner} subject_id={subject_id}
    设 link = /lesson?code={lesson_code}
    设 lj = [{"label": "读课文", "url": "/lesson?code={lesson_code}"}, {"label": "练这一课", "url": "/quiz?mode=lesson&lesson_code={lesson_code}"}]
    设 ctx = 课文正文：【{c.title}】讲解：{c.explain}；接续：{c.connection}；例句：{c.examples}；关联条目：{names}。学习进度：{summary}
    设 ut = 请老师讲解：{c.title}
    设 a = 调用 答一轮 learner={learner} user_text={ut} intent=explain lesson_code={lesson_code} context_text={ctx} link={link} links_json={lj} subject_id={subject_id}
    设 links = 解析JSON {lj}
    设 out.ok = 1
    设 out.reply_id = {a.reply_id}
    设 out.reply = {a.reply}
    设 out.intent = explain
    设 out.lesson_code = {lesson_code}
    设 out.link = {link}
    设 out.links = {links}
    返回 {out}
  结束

  公开 函数 列对话 learner limit? current_role? auth_mode? subject?
    # 返回 {learner, total, messages}；messages 是 [{id, role, content, intent, lesson_code, link, links, summary_round, at}]，取该学习者最近 limit 条（默认 50），按 id 升序；links 是解析后的列表（没有为空列表）
    # 报错 400 limit 不合法
    # limit 为空取 50；不是大于等于 1 的整数，报错 400 limit 不合法
    # 查 tutor_message 中该 learner 的行，按 id 降序取前 limit 条，再翻成升序
    # 返回 {"learner": learner, "total": 条数, "messages": 列表}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 lim = 50
    如果 {limit} 不为空
      设 lm = 匹配 {limit} ^[0-9]+$
      如果 {lm.matched} 不等于 是
        报错 400 limit 不合法
      结束
      设 lim = {limit}
      如果 {lim} 小于 1
        报错 400 limit 不合法
      结束
    结束
    设 rows = 查询 app.db tutor_list learner={learner} limit={lim} subject_id={subject_id}
    设 msgs = 解析JSON []
    遍历 r 于 {rows}
      设 it = {r}
      设 lj = {r.links 或}
      如果 {lj} 为空
        设 lj = []
      结束
      设 it.links = 解析JSON {lj}
      设 msgs = 列表加项 {msgs} {it}
    结束
    设 total = 列表长度 {msgs}
    设 out.learner = {learner}
    设 out.total = {total}
    设 out.messages = {msgs}
    返回 {out}
  结束

  公开 函数 取对话摘要 learner current_role? auth_mode? subject?
    # 返回 {learner, question_count, last_at, recent}；question_count 是该学习者 role=user 的消息数；last_at 是该学习者最后一条消息的 at（没有为空串）；recent 是最近 5 条学生提问 [{content, intent, at}]，按 id 降序；本表只有问老师对话，不含教师写的学情总结
    # 统计 tutor_message 中该 learner 且 role=user 的行数为 question_count
    # 取该 learner 中 id 最大一行的 at 为 last_at，没有为空串
    # 查该 learner 且 role=user 的行，按 id 降序取前 5 条，取 content、intent、at
    # 返回 {"learner": learner, "question_count": question_count, "last_at": last_at, "recent": 列表}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 cnt = 查一值 app.db tutor_count_user learner={learner} subject_id={subject_id}
    设 last_at = 查一值 app.db tutor_last_at learner={learner} subject_id={subject_id}
    设 recent = 查询 app.db tutor_recent_questions learner={learner} subject_id={subject_id}
    设 out.learner = {learner}
    设 out.question_count = {cnt}
    设 out.last_at = {last_at 或}
    设 out.recent = {recent}
    返回 {out}
  结束

  公开 函数 总结本轮 learner current_role? auth_mode? subject?
    # 返回 {ok, reused, round_key, summary, total, right, reply_id}；reused 为 1 表示这一轮已经总结过，原样给回、没有调模型；total、right 是这一轮作答数和答对数；reply_id 是存下的总结那一行的 id
    # 报错 400 learner 不能为空
    # 报错 400 本轮还没有作答
    # 报错 400 老师暂时无法回答
    # learner 为空，报错 400 learner 不能为空
    # 调用 quiz.取本轮作答 learner=learner，得 round_key、mode、lesson_code、total、answers；right = answers 中 correct 等于 1 的个数
    # 查 tutor_message 中该 learner、role=teacher、summary_round 等于 round_key 的十进制文本的行（按 id 降序第一条）；有则返回 {"ok": 1, "reused": 1, "round_key": round_key, "summary": 该行 content, "total": total, "right": right, "reply_id": 该行 id}，不调模型、不写库
    # total 等于 0（含没有进度行），报错 400 本轮还没有作答
    # 对 answers 中每个不同的 point_code 调用 kg.取知识点 code=该编号 取 title，取不到用编号当标题
    # 问（回答档）：把模式 mode、课 lesson_code、每题（知识点标题、题号、对错、作答）、total、right 交给模型，要求写一段给学生的本轮总结（做得好的、该复习的）；模型出错报错 400 老师暂时无法回答，不写库
    # 往 tutor_message 插入一行 (learner, role=teacher, content=总结, intent=summary, lesson_code=lesson_code, link 空, links 空, summary_round=round_key 的十进制文本, at=当前时间)，取其 id 为 reply_id（只写这一行；不记学生那条）
    # 返回 {"ok": 1, "reused": 0, "round_key": round_key, "summary": 总结, "total": total, "right": right, "reply_id": reply_id}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    设 r = 调用 quiz.取本轮作答 learner={learner} subject={subject_id}
    设 rk = {r.round_key}
    设 total = {r.total}
    设 right = 0
    遍历 a 于 {r.answers}
      如果 {a.correct} 等于 1
        设 right = 计算 {right} + 1
      结束
    结束
    设 f = 查一行 app.db tutor_summary_find learner={learner} round_key={rk} subject_id={subject_id}
    如果 {f} 不为空
      设 o.ok = 1
      设 o.reused = 1
      设 o.round_key = {rk}
      设 o.summary = {f.content}
      设 o.total = {total}
      设 o.right = {right}
      设 o.reply_id = {f.id}
      返回 {o}
    结束
    如果 {total} 等于 0
      报错 400 本轮还没有作答
    结束
    设 detail = {zz 或}
    遍历 a2 于 {r.answers}
      设 title = {a2.point_code}
      设 kp = 调用 kg.取知识点 code={a2.point_code} subject={subject_id}
      如果 {kp} 不为空
        设 title = {kp.title}
      结束
      设 ok = 错
      如果 {a2.correct} 等于 1
        设 ok = 对
      结束
      设 detail = {detail}；知识点{title} 题号{a2.question_no} {ok} 作答{a2.answer}
    结束
    设 ts = 调用 subject.科目老师设定 subject_id={subject_id}
    设 lg = 调用 account.取语言 username={learner}
    设 ovr = 0
    如果 {ts.custom} 不为空
      设 kwm = 匹配 {ts.persona} (?i)(用|请用|使用|回答|回复|解释|说|讲)\s*(中文|汉语|日文|日语|日本語|中国語|英文|英语|English|Chinese|Japanese)|(中文|汉语|日文|日语|日本語|中国語|英文|英语|English|Chinese|Japanese)\s*(回答|回复|讲解|教学|授课|作答|说|讲)|(日本語|中国語|英語)で|(in|respond\s+in|answer\s+in)\s+(Chinese|Japanese|English)
      如果 {kwm.matched} 等于 是
        设 ovr = 1
      结束
    结束
    如果 {lg.lang} 等于 ja 且 {ovr} 等于 0
      问 summary = {ts.persona}。请为学生写一段简明的本轮做题总结，说说做得好的和该复习的。本轮模式：{r.mode}，课：{r.lesson_code}，共 {total} 题，答对 {right} 题。每题情况：{detail} 请用日语回答，专业术语第一次出现时用括号标注中文；与其他提示里的语言要求冲突时，以本句为准。 用 平衡 出错时 qe
    否则
      问 summary = {ts.persona}。请为学生写一段简明的本轮做题总结，说说做得好的和该复习的。本轮模式：{r.mode}，课：{r.lesson_code}，共 {total} 题，答对 {right} 题。每题情况：{detail} 用 平衡 出错时 qe
    结束
    如果 {qe} 不为空
      报错 400 老师暂时无法回答
    结束
    如果 {summary} 为空
      报错 400 老师暂时无法回答
    结束
    设 now = 当前时间
    设 t.learner = {learner}
    设 t.role = teacher
    设 t.content = {summary}
    设 t.intent = summary
    设 t.lesson_code = {r.lesson_code}
    设 t.link = {zz 或}
    设 t.links = {zz 或}
    设 t.summary_round = {rk}
    设 t.subject_id = {subject_id}
    设 t.at = {now}
    设 n1 = 写库表 app.db tutor_insert {t}
    设 rid = 查一值 app.db tutor_last_id learner={learner} role=teacher subject_id={subject_id}
    设 o.ok = 1
    设 o.reused = 0
    设 o.round_key = {rk}
    设 o.summary = {summary}
    设 o.total = {total}
    设 o.right = {right}
    设 o.reply_id = {rid}
    返回 {o}
  结束

  公开 函数 列对话页面 learner current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 r = 调用 列对话 learner={learner} limit=40 subject={subject_id}
    设 talk = 解析JSON []
    遍历 m 于 {r.messages}
      设 cand = 解析JSON []
      遍历 lk 于 {m.links}
        设 js = [{"href": "{lk.url}", "text": "{lk.label}"}]
        设 one = 解析JSON {js}
        遍历 x 于 {one}
          设 cand = 列表加项 {cand} {x}
        结束
      结束
      设 cn = 列表长度 {cand}
      如果 {cn} 等于 0 且 {m.link} 不为空
        设 js = [{"href": "{m.link}", "text": "{m.link}"}]
        设 cand = 解析JSON {js}
      结束
      设 newl = 解析JSON []
      遍历 c 于 {cand}
        设 h = {c.href}
        设 nh = {h}
        如果 {h} 开头是 /quiz?mode=lesson&lesson_code=
          设 rest = 截取 {h} 31
          设 nh = #%E5%81%9A%E9%A2%98?lesson={rest}
        否则如果 {h} 开头是 /quiz?mode=free&level=
          设 rest = 截取 {h} 23
          设 nh = #%E5%81%9A%E9%A2%98?level={rest}
        否则如果 {h} 等于 /quiz?mode=review
          设 nh = #%E5%81%9A%E9%A2%98?mode=review
        否则如果 {h} 等于 /quiz
          设 nh = #%E5%81%9A%E9%A2%98
        否则如果 {h} 开头是 /lesson?code=
          设 rest = 截取 {h} 14
          设 nh = #%E6%95%99%E6%9D%90?lesson={rest}
        结束
        设 js2 = [{"href": "{nh}", "text": "{c.text}"}]
        设 one2 = 解析JSON {js2}
        遍历 y 于 {one2}
          设 newl = 列表加项 {newl} {y}
        结束
      结束
      设 it = {m}
      设 it.who = 你
      设 it.kind = user
      如果 {m.role} 等于 teacher
        设 it.who = 老师
        设 it.kind = {zz 或}
      结束
      设 it.text = {m.content}
      设 it.link = {m.link 或}
      设 it.link_text = {zz 或}
      设 it.links = {newl}
      设 talk = 列表加项 {talk} {it}
    结束
    设 out.talk = {talk}
    返回 {out}
  结束

  公开 函数 总结页面 learner current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 s = 调用 总结本轮 learner={learner} subject={subject_id}
    设 qa = 调用 quiz.取本轮作答 learner={learner} subject={subject_id}
    设 pts = 解析JSON []
    设 seen = ,
    遍历 a 于 {qa.answers}
      如果 {a.correct} 等于 0
        如果 {seen} 不包含 ,{a.point_code},
          设 seen = {seen}{a.point_code},
          设 pts = 列表加项 {pts} {a.point_code}
        结束
      结束
    结束
    设 worst = {zz 或}
    设 best = 0
    遍历 p 于 {pts}
      设 cnt = 0
      遍历 a2 于 {qa.answers}
        如果 {a2.correct} 等于 0 且 {a2.point_code} 等于 {p}
          设 cnt = 计算 {cnt} + 1
        结束
      结束
      如果 {cnt} 大于 {best}
        设 best = {cnt}
        设 worst = {p}
      结束
    结束
    设 rd = {zz 或}
    设 pr = {zz 或}
    设 ex = {zz 或}
    设 wl = {zz 或}
    如果 {worst} 不为空
      设 ls = 调用 lesson.按知识点列课文 point_code={worst} subject={subject_id} 出错时 le
      如果 {le} 为空
        遍历 l 于 {ls.lessons}
          如果 {wl} 为空
            设 wl = {l.code}
          结束
        结束
      结束
    结束
    如果 {wl} 不为空
      设 rd = #%E6%95%99%E6%9D%90?lesson={wl}
      设 pr = #%E5%81%9A%E9%A2%98?lesson={wl}
      设 ex = #%E9%97%AE%E8%80%81%E5%B8%88?lesson={wl}
      设 ri = 调用 quiz.取当前轮次信息 learner={learner} subject={subject_id}
      如果 {ri.lesson_code} 等于 {wl}
        设 pr = {zz 或}
      结束
    结束
    设 sm.text = {s.summary}
    设 sm.chat = #%E9%97%AE%E8%80%81%E5%B8%88
    设 sm.read = {rd}
    设 sm.practice = {pr}
    设 sm.explain = {ex}
    设 out.summary = {sm}
    返回 {out}
  结束

  公开 函数 问老师页面 learner message? lesson? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    如果 {lesson} 不为空
      设 r = 调用 讲解一课 learner={learner} lesson_code={lesson} subject={subject_id}
    否则
      设 r = 调用 问老师 learner={learner} message={message} subject={subject_id}
    结束
    返回 {r}
  结束

结束
