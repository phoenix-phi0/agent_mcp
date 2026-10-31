模块 tutor
依赖 kg lesson progress quiz teacher_rules subject

## 表
表 tutor_message 学习记录
  learner 文本 学习者
  role 文本 角色：user（学生）/ teacher（老师）
  content 长文本 内容
  intent 文本 意图：quiz / progress / textbook / explain / summary（本轮总结），学生那条与老师回复那条相同，可空
  lesson_code 文本 关联课文编号，可空
  link 文本 主链接（页面路径），可空
  links 长文本 链接列表，JSON 数组文本 [{label, url}]，没有链接时为空，可空
  summary_round 文本 只有「本轮总结」那条老师消息有值，值为轮次标识（round_key 的十进制文本，如 0、15）；其它消息为空串，可空
  at 文本 时间 YYYY-MM-DD HH:MM:SS
  subject_id 整数 所属科目，默认 1（1 是日语语法）

页面链接约定（只是字符串，不在本模块校验）：读课文 /lesson?code=<课文编号>；按课做题 /quiz?mode=lesson&lesson_code=<课文编号>；按等级做题 /quiz?mode=free&level=<等级>；复习薄弱点 /quiz?mode=review；不带参数的做题页 /quiz。

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400、need 不对报 400，原样抛出；本模块的公开函数都是学习者自己的对话，不传 need，即按 read）

函数 取最近对话 learner limit subject_id
  返回 文本，最近 limit 条对话，按 id 升序，每条一行，学生写「学生：内容」，老师写「老师：内容」；没有则空串
  伪代码 查 tutor_message 中该 learner、subject_id 等于入参 subject_id 且 summary_round 为空串的行（本轮总结不算对话上下文），按 id 降序取前 limit 条，再翻成升序
  伪代码 逐条拼成「学生：…」「老师：…」，用换行连接后返回

函数 判意图 message subject_id
  返回 {intent, keyword, level}；intent 只会是 quiz / progress / textbook / explain；keyword 是学生指名的语法点（非日语科目叫知识点）或课文关键词（可空串）；level 只会是本科目等级之一（subject.科目等级；日语 N5 N4 N3 N2 N1）或空串
  伪代码 先调用 subject.科目等级 subject_id=subject_id 得 levels；再调用 subject.科目老师设定 subject_id=subject_id 得 point_word、explain_word
  伪代码 提示词里的称呼按科目取：「explain 表示问{explain_word}或其他一切」「抽出学生指名的{point_word}或课文关键词 keyword」（日语科目 explain_word=语法讲解、point_word=语法点，提示词与旧版逐字一致；非日语科目是「讲解」「知识点」，不出现「语法」）
  伪代码 问JSON（快档）：让模型判断学生这句话的意图（出题 / 进度 / 教材 / 讲解，其他都算讲解），并抽出指名的内容关键词和指定的等级，要求返回 {"intent": …, "keyword": …, "level": …}；提示词里写明「level（只能是 {本科目等级用空格连接} 或空串）」（按科目换等级清单，不再写死 N5–N1）
  伪代码 intent 不是 quiz、progress、textbook、explain 之一（含模型出错或返回不合法），取 explain
  伪代码 level 去首尾空白后不在本科目等级（levels）里，取空串（不再按 subject_id 特判：科目 1 和其它科目都只认自己的等级，用正则匹配 N5–N1 的写法去掉）；keyword 缺失取空串并去首尾空白
  伪代码 返回 {"intent": intent, "keyword": keyword, "level": level}

函数 取进度摘要 learner subject_id
  返回 文本，学习进度摘要（给模型当上下文和回答进度用）
  伪代码 调用 progress.取概览 learner=learner subject=subject_id，得 point_total、mastered_count、answer_total、accuracy、is_empty
  伪代码 调用 progress.列低分点 learner=learner limit=5 subject=subject_id，得低分点列表
  伪代码 调用 quiz.取当前轮次信息 learner=learner subject=subject_id，has_round 等于 1 时附一行「当前轮次：模式 mode，第 asked_count / round_size 道，答对 right_count 道」
  伪代码 is_empty 等于 1：摘要写「还没有作答记录」；否则写「已掌握 mastered_count / point_total 个知识点，累计答题 answer_total，正确率 accuracy%」，有低分点再附「低分点：编号 标题 得分」逐个列出
  伪代码 返回拼好的文本

函数 推荐一课 learner subject_id
  返回 课文编号，没有可推荐的课返回空串
  伪代码 调用 progress.列低分点 learner=learner limit=5 subject=subject_id，按返回顺序（得分低的在前）对每个 point_code 调用 lesson.按知识点列课文 point_code=该编号 subject=subject_id，取到第一课就返回其 code
  伪代码 低分点都没有课文：调用 progress.算下一步 learner=learner subject=subject_id，next_code 不为空时调用 lesson.按知识点列课文 point_code=next_code subject=subject_id，有课就返回第一课的 code
  伪代码 都没有返回空串

函数 写一轮 learner user_text intent lesson_code reply link links_json setting_ids setting_versions relay_ids subject_id
  返回 reply_id（老师回复那一行的 id）
  伪代码 在一个事务里：
  伪代码 往 tutor_message 插入学生那条 (learner, role=user, content=user_text, intent, lesson_code, link 空, links 空, summary_round 空串, at=当前时间, subject_id=入参 subject_id)
  伪代码 往 tutor_message 插入老师那条 (learner, role=teacher, content=reply, intent, lesson_code, link, links=links_json, summary_round 空串, at=当前时间, subject_id=入参 subject_id)，取其新行 id 为 reply_id
  伪代码 调用 teacher_rules.记回复用到设定 reply_id=reply_id student=learner setting_ids=setting_ids setting_versions=setting_versions subject=subject_id（setting_ids 为空时它不写库；use 记录带科目，once 设定按科目判定）
  伪代码 调用 teacher_rules.记回复传达 reply_id=reply_id student=learner relay_ids=relay_ids subject=subject_id（relay_ids 为空时它不写库；传达必须属于当前科目或全部科目(0)）
  伪代码 上面任一步报错，整个事务回滚、整轮不记，错误原样向上抛
  伪代码 返回 reply_id

函数 判传达 learner reply relay_ids subject_id
  返回 无；这是回复写完之后的收尾，任何失败都不影响回复
  伪代码 relay_ids 为空直接返回
  伪代码 按英文逗号拆开，逐个编号：调用 teacher_rules.取传达 relay_id=编号 subject=subject_id 取 must_info，出错（如 404）跳过这个编号
  伪代码 问JSON（快档）：给模型这条回复 reply 和 must_info，问回复是否已把必须准确的信息传达到，要求返回 {"delivered": 1 或 0}
  伪代码 delivered 等于 1 时调用 teacher_rules.记传达判定 student=learner relay_id=编号 delivered=1 subject=subject_id，出错忽略
  伪代码 模型出错或返回不合法时按 delivered=0 处理（兜底，不调用记传达判定，不报错）

函数 答一轮 learner user_text intent lesson_code context_text link links_json subject_id
  返回 {reply_id, reply}；用模型回答的路径（进度、教材、讲解）共用
  伪代码 recent = 调用 取最近对话 learner=learner limit=6 subject_id=subject_id（此时本句还没写库，所以不含本句）
  伪代码 recent_text = 该学习者最近 3 条学生发言与本句 user_text 用换行连接（给关键词卡匹配用）
  伪代码 调用 teacher_rules.取生效设定 student=learner recent_text=recent_text subject=subject_id，得 memory_text、note_text、card_text、setting_ids、setting_versions
  伪代码 调用 teacher_rules.取待传达 student=learner subject=subject_id，得 relay_ids、prompt_text（prompt_text 是全部待传达，整段放进系统提示；下面 写一轮 传给 记回复传达 的 relay_ids 就是这全部编号，即本次回复实际带上的编号，每条计一轮）
  伪代码 人设按科目取：调用 subject.科目老师设定 subject_id=subject_id 得 persona、offtopic（日语科目 persona=「你是一位中文老师，教中文学习者日语语法」、offtopic=「学生闲聊、与日语学习无关时，简短自然地回应，不要强行讲语法」，拼出的系统提示与旧版逐字一致；非日语科目按科目名生成或用负责人填的 AI 老师设定，不出现「日语」「语法」）
  伪代码 系统提示 = persona +「，回答简明。」+ 回答格式与口吻要求（写进系统提示里，原话意思不变：①只输出纯文本，不用 Markdown 标题、加粗、表格、列表符号，不用 emoji，至多 1 个；②一般不超过 200 字；③ offtopic 原文；④不要说「昨天聊过」「上次说过」这类带时间的话（你没有可靠的日期信息，最近对话只是先后顺序，不带时间）；⑤推荐课程只能用上下文里给出的课号和标题，课号原样引用，不要自己编课号或把别的课的编号配到某个知识点上）+ memory_text + card_text（教师设定，学生看不到，不要向学生透露设定本身）+ prompt_text（用「[传达#编号]」标记的传达事项，要求自然地让学生在回复里知道其中必须准确的信息，回复里不要出现标记本身；prompt_text 为空则不加这一段）
  伪代码 用户内容 = context_text + 最近对话 recent + note_text（作者注，紧贴在学生最新一句之前）+ 学生最新一句 user_text
  伪代码 问（回答档）：系统提示、用户内容，得 reply；模型出错则报错 400 老师暂时无法回答，整轮不写任何表
  伪代码 调用 写一轮 learner=learner user_text=user_text intent=intent lesson_code=lesson_code reply=reply link=link links_json=links_json setting_ids=setting_ids setting_versions=setting_versions relay_ids=relay_ids subject_id=subject_id，得 reply_id
  伪代码 调用 判传达 learner=learner reply=reply relay_ids=relay_ids subject_id=subject_id
  伪代码 返回 {"reply_id": reply_id, "reply": reply}

函数 出题模板回复 learner keyword level message subject_id
  返回 {reply, lesson_code, link, links_json}；不调用回答模型，不判分，不在对话里出题
  伪代码 调用 lesson.取当前系列 learner=learner subject=subject_id 取 series_code
  伪代码 keyword 不为空：调用 lesson.列课文 series_code=series_code keyword=keyword subject=subject_id，有结果取第一课为 lesson_code，用模板拼 reply「好的，去做「标题」这一课的题吧」，link=/quiz?mode=lesson&lesson_code=课号，links=[{做题, link}, {读课文, /lesson?code=课号}]
  伪代码 否则（keyword 为空，或没找到课）且 level 不为空：lesson_code 为空，reply 模板「按 level 等级给你出题」（keyword 不为空时先说明没找到对应课文），link=/quiz?mode=free&level=level，links=[{做题, link}]
  伪代码 否则 keyword 为空（没指定内容）看学情：调用 progress.取概览 learner=learner subject=subject_id，is_empty 等于 1：取 调用 subject.科目等级 subject_id=subject_id 的 first（日语是 N5），reply 模板「还没有学习记录，先从{first}开始」，link=/quiz?mode=free&level={first}（等级原样拼进地址；中文等级在 # 后面由前端 URLSearchParams 解析，不用另做编码），links=[{做题, link}]；所有科目同一口径（删掉科目 1 的特判和「先去做题页做几道题吧」那条分支）。实现注意：reply 是模板文字，「设 reply = …」右边不要以「词+空格」开头（会被当成动词调用），整句不带空格
  伪代码 有记录时调用 progress.列低分点 learner=learner limit=1 subject=subject_id，有低分点则 link=/quiz，links=[{做题, /quiz}, {复习薄弱点, /quiz?mode=review}]，reply 模板提到可以复习薄弱点；没有低分点则 link=/quiz，links=[{做题, /quiz}]
  伪代码 否则（指了 keyword 但没找到课也没有等级）：link=/quiz，links=[{做题, /quiz}]，reply 模板说明没找到对应内容，请在做题页自己选等级和考点
  伪代码 links_json 为 links 的 JSON 文本；返回 {"reply": reply, "lesson_code": lesson_code, "link": link, "links_json": links_json}

公开 函数 问老师 learner message current_role? auth_mode? subject?
  返回 {ok, reply_id, reply, intent, lesson_code, link, links}；links 是 [{label, url}]，没有链接为空列表
  报错 400 learner 不能为空
  报错 400 消息不能为空
  报错 400 老师暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 learner 为空，报错 400 learner 不能为空；message 去首尾空白后为空，报错 400 消息不能为空
  伪代码 调用 判意图 message=message subject_id=subject_id，得 intent、keyword、level
  伪代码 intent 等于 quiz：调用 出题模板回复 learner=learner keyword=keyword level=level message=message subject_id=subject_id，调用 写一轮 learner=learner user_text=message intent=quiz lesson_code=其 lesson_code reply=其 reply link=其 link links_json=其 links_json setting_ids=空 setting_versions=空 relay_ids=空 subject_id=subject_id（这一路不调回答模型，也不拼教师设定与传达，不记用到设定）
  伪代码 intent 等于 progress：summary = 调用 取进度摘要 learner=learner subject_id=subject_id；lesson_code = 调用 推荐一课 learner=learner subject_id=subject_id；lesson_code 不为空时 link=/lesson?code=课号，links=[{读课文, /lesson?code=课号}, {练这一课, /quiz?mode=lesson&lesson_code=课号}]，否则 link 空、links 空；lesson_code 不为空时再调用 lesson.取课文 code=lesson_code subject=subject_id 取 title（取不到当空串）；调用 答一轮 learner=learner user_text=message intent=progress lesson_code=lesson_code context_text=（进度摘要 summary，要求按它回答，并说明推荐的那一课；lesson_code 不为空时写明「推荐课：课号 lesson_code，标题 title，只能推荐这一课，课号原样引用」，为空时写明「没有可推荐的课，不要推荐课号」）link=link links_json=links_json subject_id=subject_id
  伪代码 intent 等于 textbook：调用 lesson.取当前系列 learner=learner subject=subject_id 取 series_code；调用 lesson.列课文 series_code=series_code subject=subject_id，取前 30 课拼成课文目录（课号 等级 标题 一句话；非日语科目不带等级，只写 课号 标题 一句话）；调用 答一轮 learner=learner user_text=message intent=textbook lesson_code=空 context_text=（课文目录，要求用目录回答）link=空 links_json=空 subject_id=subject_id
  伪代码 intent 等于 explain：调用 lesson.取当前系列 learner=learner subject=subject_id 取 series_code；keyword 不为空时调用 lesson.列课文 series_code=series_code keyword=keyword subject=subject_id，取前 2 课（没有则 0 课）；对每课调用 lesson.取课文 code=课号 subject=subject_id，取标题、讲解、接续、例句作为课文正文（非日语科目不塞日语专用数据：不带等级，接续、例句有内容才附）；再附 调用 取进度摘要 learner=learner subject_id=subject_id 的摘要
  伪代码 有课文时 lesson_code=第一课课号，link=/lesson?code=课号，links=[{读课文, /lesson?code=课号}, {练一练, /quiz?mode=lesson&lesson_code=课号}]；没有课文时 lesson_code、link、links 为空；调用 答一轮 learner=learner user_text=message intent=explain lesson_code=lesson_code context_text=（课文正文 + 进度摘要）link=link links_json=links_json subject_id=subject_id
  伪代码 把 links_json 解析成列表；返回 {"ok": 1, "reply_id": reply_id, "reply": reply, "intent": intent, "lesson_code": lesson_code, "link": link, "links": 列表}

公开 函数 讲解一课 learner lesson_code current_role? auth_mode? subject?
  返回 {ok, reply_id, reply, intent, lesson_code, link, links}；intent 恒为 explain；不判意图，直接讲这一课
  报错 400 learner 不能为空
  报错 400 lesson_code 不能为空
  报错 404 没有这课
  报错 400 老师暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 learner 为空报错 400 learner 不能为空；lesson_code 为空报错 400 lesson_code 不能为空
  伪代码 调用 lesson.取课文 code=lesson_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这课
  伪代码 调用 lesson.取课文关联条目 lesson_code=lesson_code subject=subject_id，得关联条目名称，和课文标题、讲解、接续、例句一起作为课文正文
  伪代码 summary = 调用 取进度摘要 learner=learner subject_id=subject_id
  伪代码 link=/lesson?code=lesson_code，links=[{读课文, /lesson?code=课号}, {练这一课, /quiz?mode=lesson&lesson_code=课号}]
  伪代码 调用 答一轮 learner=learner user_text=「请老师讲解：」加课文标题 intent=explain lesson_code=lesson_code context_text=（课文正文 + 进度摘要）link=link links_json=links 的 JSON 文本 subject_id=subject_id
  伪代码 返回 {"ok": 1, "reply_id": reply_id, "reply": reply, "intent": "explain", "lesson_code": lesson_code, "link": link, "links": links}

公开 函数 列对话 learner limit? current_role? auth_mode? subject?
  返回 {learner, total, messages}；messages 是 [{id, role, content, intent, lesson_code, link, links, summary_round, at}]，取该学习者最近 limit 条（默认 50），按 id 升序；links 是解析后的列表（没有为空列表）
  报错 400 limit 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 limit 为空取 50；不是大于等于 1 的整数，报错 400 limit 不合法
  伪代码 查 tutor_message 中该 learner 且 subject_id 等于本科目的行（别的科目的对话不出现），按 id 降序取前 limit 条，再翻成升序
  伪代码 返回 {"learner": learner, "total": 条数, "messages": 列表}

公开 函数 取对话摘要 learner current_role? auth_mode? subject?
  返回 {learner, question_count, last_at, recent}；question_count 是该学习者 role=user 的消息数；last_at 是该学习者最后一条消息的 at（没有为空串）；recent 是最近 5 条学生提问 [{content, intent, at}]，按 id 降序；本表只有问老师对话，不含教师写的学情总结
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 统计 tutor_message 中该 learner、subject_id 等于本科目且 role=user 的行数为 question_count
  伪代码 取该 learner 且 subject_id 等于本科目的行中 id 最大一行的 at 为 last_at，没有为空串
  伪代码 查该 learner、subject_id 等于本科目且 role=user 的行，按 id 降序取前 5 条，取 content、intent、at
  伪代码 返回 {"learner": learner, "question_count": question_count, "last_at": last_at, "recent": 列表}

公开 函数 总结本轮 learner current_role? auth_mode? subject?
  返回 {ok, reused, round_key, summary, total, right, reply_id}；reused 为 1 表示这一轮已经总结过，原样给回、没有调模型；total、right 是这一轮作答数和答对数；reply_id 是存下的总结那一行的 id
  报错 400 learner 不能为空
  报错 400 本轮还没有作答
  报错 400 老师暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 learner 为空，报错 400 learner 不能为空
  伪代码 调用 quiz.取本轮作答 learner=learner subject=subject_id，得 round_key、mode、lesson_code、total、answers；right = answers 中 correct 等于 1 的个数
  伪代码 查 tutor_message 中该 learner、subject_id 等于本科目、role=teacher、summary_round 等于 round_key 的十进制文本的行（按 id 降序第一条）；有则返回 {"ok": 1, "reused": 1, "round_key": round_key, "summary": 该行 content, "total": total, "right": right, "reply_id": 该行 id}，不调模型、不写库
  伪代码 total 等于 0（含没有进度行），报错 400 本轮还没有作答
  伪代码 对 answers 中每个不同的 point_code 调用 kg.取知识点 code=该编号 subject=subject_id 取 title，取不到用编号当标题
  伪代码 问（回答档）：提示词以 调用 subject.科目老师设定 subject_id=subject_id 的 persona 加「。」开头（日语科目即「你是一位中文老师，教中文学习者日语语法。」，与旧版逐字一致），再把模式 mode、课 lesson_code、每题（知识点标题、题号、对错、作答）、total、right 交给模型，要求写一段给学生的本轮总结（做得好的、该复习的）；模型出错报错 400 老师暂时无法回答，不写库
  伪代码 往 tutor_message 插入一行 (learner, role=teacher, content=总结, intent=summary, lesson_code=lesson_code, link 空, links 空, summary_round=round_key 的十进制文本, at=当前时间, subject_id=本科目 subject_id)，取其 id 为 reply_id（只写这一行；不记学生那条）
  伪代码 返回 {"ok": 1, "reused": 0, "round_key": round_key, "summary": 总结, "total": total, "right": right, "reply_id": reply_id}

公开 函数 列对话页面 learner current_role? auth_mode? subject?
  返回 {talk}；问老师页消息流的消息列表（最近 40 条，按时间正序），每条 {who, text, kind, link, link_text, links}：who 为「老师」或「你」，text 为内容，kind 学生那条为 user、老师那条为空串，links 是 [{href, text}]（前端消息流只认 # 或 http(s) 开头的地址，地址空不画）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 调用 列对话 learner=learner limit=40 subject=subject_id，得 messages
  伪代码 逐条转换：role 等于 teacher 则 who=老师、kind=空串，否则 who=你、kind=user；text=content；link 取该行 link；link_text 为空串（v4 不存单链接文字，老前端键，留空保持行形状一致）
  伪代码 links 由该行 links 列表逐项转成 {href: url, text: label}；转完为空且 link 不为空时 links=[{href: link, text: link}]（前端退回旧写法时链接文字显示地址）
  伪代码 地址是 v4 页面路径的转成界面链接（前端消息流只认 # 或 http(s) 开头的地址）：/lesson?code=X→#%E6%95%99%E6%9D%90?lesson=X、/quiz?mode=lesson&lesson_code=X→#%E5%81%9A%E9%A2%98?lesson=X、/quiz?mode=free&level=L→#%E5%81%9A%E9%A2%98?level=L、/quiz?mode=review→#%E5%81%9A%E9%A2%98?mode=review、/quiz→#%E5%81%9A%E9%A2%98，http(s) 原样
  伪代码 返回 {"talk": 列表}

公开 函数 总结页面 learner current_role? auth_mode? subject?
  返回 {summary}；做题页「请老师总结这一轮」（动作 quiz_summary 的接口声明在本模块：路径归做题页，但总结要调 总结本轮 和 quiz.取本轮作答，放本模块避免 quiz↔tutor 依赖成环）：summary 是 {text, chat, read, practice, explain}，text 为总结全文，其余四个是链接地址（空串前端不画）
  报错 400 本轮还没有作答
  报错 400 老师暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 调用 总结本轮 learner=learner subject=subject_id，得 summary（400 原样向上抛；同一轮重复点它给回存好的那条，不再调模型）
  伪代码 调用 quiz.取本轮作答 learner=learner subject=subject_id 得 answers：统计 correct=0 的 point_code 出现次数，取最多的为 worst_point（并列取先出现的），全对则 worst_point 为空
  伪代码 worst_point 不为空：调用 lesson.按知识点列课文 point_code=worst_point subject=subject_id 取第一课 code、title（取不到课则四个链接全空）；read=#%E6%95%99%E6%9D%90?lesson={code}、practice=#%E5%81%9A%E9%A2%98?lesson={code}、explain=#%E9%97%AE%E8%80%81%E5%B8%88?lesson={code}（旧页同款地址）
  伪代码 调用 quiz.取当前轮次信息 learner=learner subject=subject_id，lesson_code 等于 worst 课号（在练的就是这门课）则 practice 为空串（地址就是当前页，点了不会重新载入）
  伪代码 chat=#%E9%97%AE%E8%80%81%E5%B8%88；返回 {"summary": {"text": summary, "chat": chat, "read": read, "practice": practice, "explain": explain}}

公开 函数 问老师页面 learner message? lesson? current_role? auth_mode? subject?
  返回 与 问老师/讲解一课 相同：{ok, reply_id, reply, intent, lesson_code, link, links}；前端「发送」按输入框一句话走问老师，「触发」带地址参数 lesson 进来直接讲那一课
  报错 400 消息不能为空
  报错 404 没有这课
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（tutor_message 带 subject_id 条件，对话记录按科目分开存取）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress./quiz./teacher_rules. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（取最近对话、判意图、取进度摘要、推荐一课、写一轮、判传达、答一轮、出题模板回复）带 subject_id=subject_id；非日语科目（subject_id 不等于 1）不塞日语专用数据（假名、N 级等）；提示词里的老师人设和措辞按科目取（subject.科目老师设定，见 判意图、答一轮、总结本轮；日语科目与旧提示词逐字一致）
  伪代码 message 是前端输入框的 content（接口行 参数 content=message：前端键 content 传给函数入参 message）；lesson 是地址参数（教材页「请老师讲解」、做题页「请老师讲这课」跳 #问老师?lesson=… 时前端并进提交），两者都可选
  伪代码 lesson 不为空：调用 讲解一课 learner=learner lesson_code=lesson subject=subject_id 并原样返回其结果（404 没有这课原样向上抛）
  伪代码 否则调用 问老师 learner=learner message=message subject=subject_id 并原样返回其结果（message 去首尾空白后为空，问老师 报 400 消息不能为空，原样向上抛）

## 接口
POST /tutor/ask -> 问老师页面 动作 teacher_send 模板 回复消息 谁=老师 取=reply 参数 content=message 角色 student
POST /tutor/history -> 列对话页面 动作 teacher_state 模板 状态 键=talk 取=talk 角色 student
POST /quiz/summary -> 总结页面 动作 quiz_summary 模板 页面状态 角色 student
POST /tutor/explain -> 讲解一课 角色 student
GET /tutor/messages -> 列对话 角色 student
POST /tutor/summarize-round -> 总结本轮 角色 student

## 用例
用例 问老师_正常
  调用 问老师 learner=u1 message=你好
  得 ok=1
  库 tutor_message 共 2 行
  库 tutor_message 含 learner=u1 role=user content=你好
  库 tutor_message 含 learner=u1 role=teacher

用例 问老师_消息为空
  调用 问老师 learner=u1 message=空
  报错 400
  库 tutor_message 共 0 行

用例 问老师_learner为空
  调用 问老师 learner=空 message=你好
  报错 400
  库 tutor_message 共 0 行

用例 讲解一课_正常
  先 数据 lesson_text code=L1 level=N5 title=はとが summary=主题助词 explain=はは提示主题 connection=名词 examples=私は学生です examples_edited=0 orig_title=はとが series_code=hanabira seq=1
  调用 讲解一课 learner=u1 lesson_code=L1
  得 ok=1 intent=explain lesson_code=L1
  库 tutor_message 共 2 行
  库 tutor_message 含 learner=u1 role=user intent=explain lesson_code=L1
  库 tutor_message 含 learner=u1 role=teacher intent=explain lesson_code=L1

用例 讲解一课_带设定和传达
  先 数据 lesson_text code=L1 level=N5 title=はとが summary=主题助词 explain=はは提示主题 connection=名词 examples=私は学生です examples_edited=0 orig_title=はとが series_code=hanabira seq=1
  先 数据 teacher_rules_setting kind=memory student=u1 keywords=k content=多用例句 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01
  先 数据 teacher_rules_relay urgency=normal tone=温和 must_info=下周三小测 rounds=2 deadline=2099-12-31 student=u1 enabled=1 author=t1 updated_at=2026-01-01
  调用 讲解一课 learner=u1 lesson_code=L1
  得 ok=1
  库 tutor_message 共 2 行
  库 teacher_rules_setting_use 共 1 行
  库 teacher_rules_setting_use 含 student=u1
  库 teacher_rules_relay_use 共 1 行
  库 teacher_rules_relay_state 含 relay_id=1 student=u1 rounds_done=1 finished=0

用例 讲解一课_没有这课
  调用 讲解一课 learner=u1 lesson_code=NOPE
  报错 404
  库 tutor_message 共 0 行

用例 讲解一课_课号为空
  调用 讲解一课 learner=u1 lesson_code=空
  报错 400
  库 tutor_message 共 0 行

用例 列对话_正常
  先 数据 tutor_message learner=u1 role=user content=问题一 at=2026-01-01
  先 数据 tutor_message learner=u1 role=teacher content=回答一 at=2026-01-01
  先 数据 tutor_message learner=u2 role=user content=别人的 at=2026-01-01
  调用 列对话 learner=u1
  得 learner=u1 total=2

用例 列对话_limit截取最近
  先 数据 tutor_message learner=u1 role=user content=一 at=2026-01-01
  先 数据 tutor_message learner=u1 role=teacher content=二 at=2026-01-01
  先 数据 tutor_message learner=u1 role=user content=三 at=2026-01-01
  调用 列对话 learner=u1 limit=2
  得 total=2

用例 列对话_没有记录
  调用 列对话 learner=u1
  得 total=0

用例 列对话_limit非法
  调用 列对话 learner=u1 limit=0
  报错 400

用例 取对话摘要_正常
  先 数据 tutor_message learner=u1 role=user content=问题一 intent=explain at=2026-01-01
  先 数据 tutor_message learner=u1 role=teacher content=回答一 intent=explain at=2026-01-01
  先 数据 tutor_message learner=u1 role=user content=问题二 intent=progress at=2026-01-01
  调用 取对话摘要 learner=u1
  得 learner=u1 question_count=2 last_at=2026-01-01

用例 取对话摘要_没有记录
  先 数据 tutor_message learner=u2 role=user content=别人的 at=2026-01-01
  调用 取对话摘要 learner=u1
  得 learner=u1 question_count=0

用例 总结本轮_正常
  先 数据 kg_point code=P1 title=一次函数
  先 数据 quiz_progress learner=u1 level=N5 category=接续题 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=1
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01
  调用 总结本轮 learner=u1
  得 ok=1 reused=0 round_key=0 total=1 right=1
  库 tutor_message 共 1 行
  库 tutor_message 含 learner=u1 role=teacher intent=summary summary_round=0

用例 总结本轮_同一轮不再调模型
  先 数据 kg_point code=P1 title=一次函数
  先 数据 quiz_progress learner=u1 level=N5 category=接续题 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=1
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01
  先 调用 总结本轮 learner=u1
  调用 总结本轮 learner=u1
  得 ok=1 reused=1 round_key=0 total=1 right=1
  库 tutor_message 共 1 行

用例 总结本轮_新一轮重新总结
  先 数据 kg_point code=P1 title=一次函数
  先 数据 quiz_progress learner=u1 level=N5 category=接续题 current_no=Q2 answered=1 right_count=0 asked_nos=Q2 asked_count=1 mode=lesson lesson_code=L1 round_start_id=1 seq=2 last_correct=0
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q2 correct=0 answer=B at=2026-01-01
  先 数据 tutor_message learner=u1 role=teacher content=上一轮总结 intent=summary summary_round=0 at=2026-01-01
  调用 总结本轮 learner=u1
  得 ok=1 reused=0 round_key=1 total=1 right=0
  库 tutor_message 共 2 行
  库 tutor_message 含 learner=u1 role=teacher summary_round=1

用例 总结本轮_没有进度行
  调用 总结本轮 learner=u1
  报错 400
  库 tutor_message 共 0 行

用例 总结本轮_本轮没有作答
  先 数据 quiz_progress learner=u1 level=N5 category=接续题 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=0
  调用 总结本轮 learner=u1
  报错 400
  库 tutor_message 共 0 行

用例 列对话页面_转换消息字段
  先 数据 tutor_message learner=u1 role=user content=问题一 at=2026-01-01
  先 数据 tutor_message learner=u1 role=teacher content=回答一 intent=quiz link=/quiz links=[{"label":"做题","url":"/quiz"}] at=2026-01-01
  调用 列对话页面 learner=u1
  得 有返回

用例 问老师页面_讲解直达
  先 数据 lesson_text code=L1 level=N5 title=はとが summary=主题助词 explain=はは提示主题 connection=名词 examples=私は学生です examples_edited=0 orig_title=はとが series_code=hanabira seq=1
  调用 问老师页面 learner=u1 lesson=L1
  得 ok=1 intent=explain lesson_code=L1
  库 tutor_message 共 2 行

用例 问老师页面_消息为空
  调用 问老师页面 learner=u1
  报错 400
  库 tutor_message 共 0 行

用例 总结页面_正常
  先 数据 kg_point code=P1 title=点一
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=1
  先 数据 progress_answer learner=me point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01
  调用 总结页面 learner=me
  得 有返回
  库 tutor_message 共 1 行

用例 总结页面_没作答
  调用 总结页面 learner=me
  报错 400

用例 跨科目_问老师落当前科目
  调用 问老师 learner=u1 message=你好 subject=2
  得 ok=1
  库 tutor_message 共 2 行
  库 tutor_message 含 learner=u1 role=user content=你好 subject_id=2
  库 tutor_message 含 learner=u1 role=teacher subject_id=2

用例 跨科目_问老师不传科目是日语
  调用 问老师 learner=u1 message=你好
  得 ok=1
  库 tutor_message 含 learner=u1 role=user content=你好 subject_id=1
  库 tutor_message 含 learner=u1 role=teacher subject_id=1

用例 跨科目_问老师消息为空
  调用 问老师 learner=u1 message=空 subject=2
  报错 400
  库 tutor_message 共 0 行

用例 跨科目_列对话只看本科目
  先 数据 tutor_message learner=u1 role=user content=日语问题 at=2026-01-01 subject_id=1
  先 数据 tutor_message learner=u1 role=user content=数学问题 at=2026-01-01 subject_id=2
  先 数据 tutor_message learner=u1 role=teacher content=数学回答 at=2026-01-01 subject_id=2
  调用 列对话 learner=u1 subject=2
  得 learner=u1 total=2

用例 跨科目_列对话不传科目是日语
  先 数据 tutor_message learner=u1 role=user content=日语问题 at=2026-01-01 subject_id=1
  先 数据 tutor_message learner=u1 role=user content=数学问题 at=2026-01-01 subject_id=2
  先 数据 tutor_message learner=u1 role=teacher content=数学回答 at=2026-01-01 subject_id=2
  调用 列对话 learner=u1
  得 learner=u1 total=1

用例 跨科目_取对话摘要只算本科目
  先 数据 tutor_message learner=u1 role=user content=日语问题 at=2026-01-01 subject_id=1 intent=explain
  先 数据 tutor_message learner=u1 role=user content=数学问题一 at=2026-01-01 subject_id=2 intent=explain
  先 数据 tutor_message learner=u1 role=user content=数学问题二 at=2026-01-01 subject_id=2 intent=progress
  调用 取对话摘要 learner=u1 subject=2
  得 learner=u1 question_count=2

用例 跨科目_取对话摘要别的科目没有记录
  先 数据 tutor_message learner=u1 role=user content=日语问题 at=2026-01-01 subject_id=1
  调用 取对话摘要 learner=u1 subject=2
  得 learner=u1 question_count=0 last_at=空

用例 跨科目_列对话页面只见本科目
  先 数据 tutor_message learner=u1 role=user content=日语问题 at=2026-01-01 subject_id=1
  先 数据 tutor_message learner=u1 role=user content=数学问题 at=2026-01-01 subject_id=2
  调用 列对话页面 learner=u1 subject=2
  得 有返回

用例 跨科目_列对话页面别的科目没有对话
  先 数据 tutor_message learner=u1 role=user content=日语问题 at=2026-01-01 subject_id=1
  先 数据 tutor_message learner=u1 role=user content=数学问题 at=2026-01-01 subject_id=2
  调用 列对话页面 learner=u1 subject=3
  得 talk=[]

用例 跨科目_讲解一课别的科目的课当不存在
  先 数据 lesson_text code=L1 level=N5 title=はとが summary=主题助词 explain=はは提示主题 connection=名词 examples=私は学生です examples_edited=0 orig_title=はとが series_code=hanabira seq=1
  调用 讲解一课 learner=u1 lesson_code=L1 subject=2
  报错 404
  库 tutor_message 共 0 行

用例 跨科目_讲解一课落当前科目
  先 数据 lesson_text code=math.L1 level=N5 title=一次函数 summary=图像是直线 explain=y=kx+b examples_edited=0 orig_title=一次函数 series_code=math.s seq=1 subject_id=2
  调用 讲解一课 learner=u1 lesson_code=math.L1 subject=2
  得 ok=1 intent=explain lesson_code=math.L1
  库 tutor_message 共 2 行
  库 tutor_message 含 learner=u1 role=user intent=explain lesson_code=math.L1 subject_id=2
  库 tutor_message 含 learner=u1 role=teacher intent=explain lesson_code=math.L1 subject_id=2

用例 跨科目_问老师页面讲解直达别的科目的课404
  先 数据 lesson_text code=L1 level=N5 title=はとが summary=主题助词 explain=はは提示主题 connection=名词 examples=私は学生です examples_edited=0 orig_title=はとが series_code=hanabira seq=1
  调用 问老师页面 learner=u1 lesson=L1 subject=2
  报错 404
  库 tutor_message 共 0 行

用例 跨科目_问老师页面讲解直达落当前科目
  先 数据 lesson_text code=math.L1 level=N5 title=一次函数 summary=图像是直线 explain=y=kx+b examples_edited=0 orig_title=一次函数 series_code=math.s seq=1 subject_id=2
  调用 问老师页面 learner=u1 lesson=math.L1 subject=2
  得 ok=1 intent=explain lesson_code=math.L1
  库 tutor_message 含 learner=u1 role=teacher subject_id=2

用例 跨科目_讲解一课只带本科目和全部科目的设定与传达
  先 数据 lesson_text code=math.L1 level=N5 title=一次函数 summary=图像是直线 explain=y=kx+b examples_edited=0 orig_title=一次函数 series_code=math.s seq=1 subject_id=2
  先 数据 teacher_rules_setting kind=memory content=日语设定 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01 subject_id=1
  先 数据 teacher_rules_setting kind=memory content=数学设定 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01 subject_id=2
  先 数据 teacher_rules_setting kind=memory content=通用设定 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01
  先 数据 teacher_rules_relay urgency=normal must_info=日语小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01 subject_id=1
  先 数据 teacher_rules_relay urgency=normal must_info=数学小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01 subject_id=2
  调用 讲解一课 learner=u1 lesson_code=math.L1 subject=2
  得 ok=1
  库 teacher_rules_setting_use 共 1 行
  库 teacher_rules_setting_use 含 student=u1 setting_ids=2,3
  库 teacher_rules_relay_use 共 1 行
  库 teacher_rules_relay_state 共 1 行
  库 teacher_rules_relay_state 含 relay_id=2 student=u1 rounds_done=1

用例 跨科目_总结本轮只算本科目的作答
  先 数据 kg_point code=math.P1 title=一次函数 subject_id=2
  先 数据 quiz_progress learner=u1 level=N5 category=接续题 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=1 subject_id=2
  先 数据 progress_answer learner=u1 point_code=math.P1 question_no=math.Q1 correct=1 answer=A at=2026-01-01 subject_id=2
  调用 总结本轮 learner=u1 subject=2
  得 ok=1 reused=0 round_key=0 total=1 right=1
  库 tutor_message 共 1 行
  库 tutor_message 含 learner=u1 role=teacher intent=summary summary_round=0 subject_id=2

用例 跨科目_总结本轮别的科目的作答当没有作答
  先 数据 kg_point code=P1 title=一次函数
  先 数据 quiz_progress learner=u1 level=N5 category=接续题 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=1
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01
  调用 总结本轮 learner=u1 subject=2
  报错 400
  库 tutor_message 共 0 行

用例 跨科目_总结本轮别的科目的总结不算已总结
  先 数据 kg_point code=math.P1 title=一次函数 subject_id=2
  先 数据 quiz_progress learner=u1 level=N5 category=接续题 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=1 subject_id=2
  先 数据 progress_answer learner=u1 point_code=math.P1 question_no=math.Q1 correct=1 answer=A at=2026-01-01 subject_id=2
  先 数据 tutor_message learner=u1 role=teacher content=日语的总结 intent=summary summary_round=0 at=2026-01-01 subject_id=1
  调用 总结本轮 learner=u1 subject=2
  得 ok=1 reused=0 round_key=0 total=1 right=1
  库 tutor_message 共 2 行
  库 tutor_message 含 learner=u1 role=teacher summary_round=0 subject_id=2

用例 跨科目_总结页面落当前科目
  先 数据 kg_point code=math.P1 title=一次函数 subject_id=2
  先 数据 quiz_progress learner=me level=N5 category=接续题 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=math.L1 round_start_id=0 seq=1 last_correct=1 subject_id=2
  先 数据 progress_answer learner=me point_code=math.P1 question_no=math.Q1 correct=1 answer=A at=2026-01-01 subject_id=2
  调用 总结页面 learner=me subject=2
  得 有返回
  库 tutor_message 共 1 行
  库 tutor_message 含 learner=me role=teacher intent=summary subject_id=2

用例 跨科目_总结页面别的科目的作答400
  先 数据 kg_point code=P1 title=点一
  先 数据 quiz_progress learner=me level=N5 category=接续题 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=lesson lesson_code=L1 round_start_id=0 seq=1 last_correct=1
  先 数据 progress_answer learner=me point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01
  调用 总结页面 learner=me subject=2
  报错 400

用例 跨科目_need_学生访问未分配科目403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 问老师 learner=u1 message=你好 current_role=student auth_mode=on subject=2
  报错 403
  库 tutor_message 共 0 行

用例 跨科目_need_学生访问已分配科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=u1 assigned_by=t1 status=active created_at=2026-01-01
  调用 问老师 learner=u1 message=你好 current_role=student auth_mode=on subject=2
  得 ok=1
  库 tutor_message 含 learner=u1 role=user subject_id=2

用例 问老师_自定义等级科目正常
  先 数据 subject_info code=jp_grammar name=日语 levels=空 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 问老师 learner=u1 message=出几道题 subject=2
  得 ok=1
  库 tutor_message 含 learner=u1 role=user content=出几道题 subject_id=2
  库 tutor_message 含 learner=u1 role=teacher subject_id=2

用例 问老师_日语科目空等级照旧
  先 数据 subject_info code=jp_grammar name=日语 levels=空 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 问老师 learner=u1 message=出几道题
  得 ok=1
  库 tutor_message 含 learner=u1 role=user content=出几道题 subject_id=1

用例 问老师_通用科目按科目人设正常
  先 数据 subject_info code=jp_grammar name=日语语法 levels=空 kind=language caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 问老师 learner=u1 message=什么是列表 subject=2
  得 ok=1
  库 tutor_message 共 2 行
  库 tutor_message 含 learner=u1 role=teacher subject_id=2

用例 问老师_自定义AI老师设定正常
  先 数据 subject_info code=jp_grammar name=日语语法 levels=空 kind=language caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_ai subject_id=2 persona=你是严格的编程教练。
  调用 问老师 learner=u1 message=什么是列表 subject=2
  得 ok=1
  库 tutor_message 含 learner=u1 role=teacher subject_id=2

用例 总结本轮_通用科目按科目人设正常
  先 数据 subject_info code=jp_grammar name=日语语法 levels=空 kind=language caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=py.P1 title=列表 subject_id=2
  先 数据 quiz_progress learner=u1 level=入门 category=选择 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 mode=free lesson_code=空 round_start_id=0 seq=1 last_correct=1 subject_id=2
  先 数据 progress_answer learner=u1 point_code=py.P1 question_no=py.Q1 correct=1 answer=A at=2026-01-01 subject_id=2
  调用 总结本轮 learner=u1 subject=2
  得 ok=1 reused=0 total=1 right=1
  库 tutor_message 含 learner=u1 role=teacher intent=summary subject_id=2
