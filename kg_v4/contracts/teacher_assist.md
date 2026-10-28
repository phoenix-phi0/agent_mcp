模块 teacher_assist
依赖 account report progress kg lesson subject

## 表
表 teacher_assist_message 学习记录
  teacher 文本 教师用户名（对话归谁）
  role 文本 角色：user（老师）/ assistant（助手）
  content 长文本 内容
  intent 文本 意图：class_overview / student_detail / point_status / teaching_advice / chitchat，老师那条与助手回复那条相同
  student 文本 本轮聚焦的学生用户名（匹配成功才写），可空
  point 文本 本轮聚焦的知识点编号（匹配成功才写），可空
  status 文本 ok（按数据回答）/ ask（没找到或有多个，用模板回复、没调回答模型），老师那条与助手那条相同
  at 文本 时间 YYYY-MM-DD HH:MM:SS
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出）；本模块没有传 need=write 的函数（对话记录是老师自己的流水，按读处理）

函数 学生范围 subject_id
  返回 [{username, display_name, status, last_at}]；本科目的学生范围，按 account.列学生 的顺序（与 report 的学生范围同一规则，report 的该函数是私有的，这里按同样规则做一份）
  伪代码 调用 account.列学生，得全部学生（含停用），带出 username、display_name、status、last_at
  伪代码 所有科目（含 1 号日语）统一：调用 subject.列科目学生 subject_id=subject_id，得 students；只留 username 在 students 各项 learner 里的学生（科目里登记且 active 的学生；没有登记或已撤销的不出现），顺序不变。不再有「1 号=全部学生」的特例，也不按 id=1 判断；学生范围的规则只在 subject.列科目学生 一处（本函数与 report 的同名私有函数都只是它加 account.列学生 的过滤）

函数 取最近对话 current_user limit subject_id
  返回 文本，本科目最近 limit 条对话，按 id 升序，每条一行，老师写「老师：内容」，助手写「助手：内容」；老师那条截取前 100 个字，助手那条截取前 150 个字；没有则空串
  伪代码 查 teacher_assist_message 中该 teacher 且 subject_id 等于 subject_id 的行（别的科目的对话不出现），按 id 降序取前 limit 条，再翻成升序，内容在 SQL 里按上面的字数截取
  伪代码 逐条拼成「老师：…」「助手：…」，用换行连接后返回

函数 取上轮聚焦 current_user subject_id
  返回 {student, student_name, point, point_title}；取该教师在本科目最后一条助手回复里的 student、point（没有为空串），并翻成显示名和知识点名（给判意图和「他/这个语法」用）
  伪代码 查 teacher_assist_message 中该 teacher、subject_id 等于 subject_id 且 role 等于 assistant 的行，取 id 最大一行的 student、point；没有行则四个值都为空串
  伪代码 student 不为空：调用 学生范围 subject_id=subject_id 取该生 display_name（找不到当空串）；point 不为空：调用 kg.取知识点 code=point subject=subject_id 取 title（找不到当空串）
  伪代码 返回 {"student": …, "student_name": …, "point": …, "point_title": …}

公开 函数 匹配学生 name learner? current_role? auth_mode? subject?
  返回 {status, username, display_name, candidates, roster}；status 为 one（唯一）/ many（多个）/ none（零个）；one 时 username、display_name 是那位学生；many 时 candidates 是最多 5 个 [{username, display_name, status}]；none 时 candidates 为空列表；roster 恒为本科目学生范围的前 10 个「显示名（用户名）」用「、」连接（给没找到时提示用）；只在本科目的学生范围里匹配（登记在别的科目的学生匹配不到）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（本函数没有 current_user，故补 learner；路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 学生范围 subject_id=subject_id，得本科目全部学生（含停用），带出 username、display_name、status、last_at
  伪代码 name 去首尾空白，再去掉结尾的「同学」二字；去完为空，返回 {"status": "none", …}（不是报错）
  伪代码 按顺序匹配，前一档有结果就停：①username 与 name 相等（忽略大小写）；②display_name 与 name 相等；③模糊：display_name 包含 name，或 name 包含 display_name（display_name 至少 2 个字才用这个方向），或 username 包含 name（name 至少 2 个字）
  伪代码 命中 1 个返回 one；命中多个返回 many（按学生列表顺序取前 5 个为 candidates）；0 个返回 none
  伪代码 停用的学生也参与匹配（教师可能问已停用的学生），status 原样带出「启用」「停用」

公开 函数 匹配知识点 keyword learner? current_role? auth_mode? subject?
  返回 {status, code, title, candidates, total}；status 为 one / many / none；one 时 code、title 是那个知识点；many 时 candidates 是最多 5 个 [{code, title}]、total 是命中总数；none 时 candidates 为空列表、total 为 0；只在本科目的知识点和条目里匹配
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（本函数没有 current_user，故补 learner；路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 keyword 去首尾空白，去掉开头的「～」「~」「〜」和结尾的「的用法」；去完为空，返回 {"status": "none", …}（不是报错）
  伪代码 调用 kg.列知识点 subject=subject_id，得全部知识点 [{code, title}]
  伪代码 按顺序匹配，前一档有结果就停：①code 与 keyword 相等（忽略大小写）；②title 与 keyword 相等；③title 包含 keyword，或 keyword 包含 title（title 至少 2 个字才用这个方向）
  伪代码 前三档都没有：调用 kg.列条目 subject=subject_id，取 name 包含 keyword（或 keyword 包含 name，name 至少 2 个字）的条目，把它们的 point_code 去重后当命中（条目名如「ばかり」，教师常用条目名问）；再调用 kg.取知识点 code=该编号 subject=subject_id 取 title
  伪代码 命中 1 个返回 one；多个返回 many（按知识点列表顺序取前 5 个）；0 个返回 none

函数 班级上下文 current_user subject_id
  返回 文本：本科目全班概况的数据段（供 class_overview 和 teaching_advice 用）
  伪代码 调用 report.取全班学情 sort_by=avg_score subject=subject_id，得 total、students、weak_points（学生范围是本科目登记的学生，由 report 决定）
  伪代码 第一行「今天：当前日期」（只写日期 YYYY-MM-DD，用于让助手知道今天是哪天；其余日期都是库里原文）
  伪代码 第二行「全班 total 人，有作答的 m 人，还没作答的 k 人」，m、k 由 students 的 answer_total 是否大于 0 数出来
  伪代码 学生表：只列 answer_total 大于 0 的学生，按平均分从低到高；每人一行「显示名（用户名）｜作答 answer_total｜近期正确率 recent_accuracy%｜平均分 avg_score｜已掌握 mastered_count｜低分点 weak_count 个（最低的两个标题）｜最近学习 last_at 的前 10 个字符」；行数上限 30，超过 30 人时只列平均分最低的 20 人，并写「另有 n 人未列出」
  伪代码 没作答的学生一行「还没作答：显示名（用户名）、…」，最多 10 人，超出写「等 n 人」
  伪代码 全班薄弱知识点前 5 个，每个一行「标题（level）｜student_count 人低于 80 分｜这些人平均 avg_score 分」
  伪代码 总长度超过 2500 个字时，从学生表末尾的行砍起，并写「（表已截断）」
  伪代码 total 等于 0 时只返回「今天：…」和「还没有学生账号」

函数 学生上下文 username display_name last_at subject_id
  返回 文本：某个学生在本科目的数据段（供 student_detail 用）
  伪代码 调用 report.取学生学情 student=username subject=subject_id，得各指标
  伪代码 第一行「学生：display_name（username），状态 status，最近学习 last_at 的前 10 个字符（空串写没有作答）」
  伪代码 answer_total 等于 0：第二行「还没有作答」，其余只补「错词本 wrong_book_count 个」和「问老师提问 question_count 次」
  伪代码 否则依次写：「作答 answer_total 题，近期正确率 recent_accuracy%，平均分 avg_score，已掌握 mastered_count 个知识点」；「低分点 weak_count 个，最低的 5 个：标题（等级）得分 …」；「最近答错 wrong_count 题，最近 5 条：知识点标题 日期」；「错词本 wrong_book_count 个，前 5 个：汉字【读音】意思」；「问老师提问 question_count 次，最近 3 条（每条截取前 40 个字）」；relays 里 finished 等于 0 的条数「未传达完的传达 n 条」
  伪代码 has_summary 等于 1 时附「最近的 AI 学情总结（summary_at，summary_author）：」加 summary 前 200 个字
  伪代码 总长度上限 1500 个字，超出从最后一段砍起

函数 知识点上下文 code title subject_id
  返回 文本：某个知识点的本科目全班掌握数据段（供 point_status 用）
  伪代码 调用 lesson.取知识点等级 point_code=code subject=subject_id 取 level；调用 kg.按知识点列条目 point_code=code subject=subject_id 取前 5 个条目名；调用 lesson.按知识点列课文 point_code=code subject=subject_id 取前 3 课的 code、title
  伪代码 调用 学生范围 subject_id=subject_id，对每个学生调用 progress.取状态 learner=该学生 point_code=code subject=subject_id，取 points 的第一项 right、total、mastered、score
  伪代码 第一行「知识点：title（code），等级 level」；第二行「条目：…」（没有写没有条目）；第三行「相关课文：课号 标题 …」（没有写没有课文）
  伪代码 统计行「全班 n 人：已掌握 a 人，作答过但未掌握 b 人，没作答 c 人；有作答的人平均分 s」（没有人作答时平均分写没有）
  伪代码 未掌握且作答过的学生按得分从低到高列，每人一行「显示名（用户名）｜答对 right / 作答 total｜得分 score」，最多 15 人，超出写「等 n 人」
  伪代码 没作答的学生一行「没作答：显示名、…」，最多 10 人，超出写「等 n 人」；已掌握的学生一行「已掌握：显示名、…」，最多 10 人
  伪代码 学生数为 0 时写「还没有学生账号」

函数 建议上下文 current_user subject_id
  返回 文本：教学建议用的数据段
  伪代码 先取 班级上下文 current_user=current_user subject_id=subject_id 的文本
  伪代码 调用 report.取全班学情 subject=subject_id 取 weak_points 前 5 个，对每个调用 lesson.按知识点列课文 point_code=该编号 subject=subject_id 取前 2 课，追加一段「可对应的课文：」每行「知识点标题 → 课号 标题；课号 标题」，没有课文写「该知识点暂无对应课文」
  伪代码 末尾写「建议只能基于上面的数据和课文，课号和标题原样引用」

公开 函数 取助手上下文 intent student? point? learner? current_role? auth_mode? subject?
  返回 {ok, intent, status, student, student_name, point, point_title, hint, context_text}；status 为 ok（有数据段）/ ask（需要老师补充，hint 是直接回给老师的模板话，context_text 为空串）；student、point 是匹配成功的学生用户名和知识点编号（没有为空串）。只读，不调模型、不写库；学生和知识点都只在本科目里找
  报错 400 intent 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（本函数没有 current_user，故补 learner；路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 intent 不是 class_overview / student_detail / point_status / teaching_advice / chitchat 之一，报错 400 intent 不合法
  伪代码 class_overview：context_text = 班级上下文 current_user=learner subject_id=subject_id（本函数没有 current_user，班级上下文 不用它做查询）；status 为 ok
  伪代码 student_detail：调用 匹配学生 name=student subject=subject_id。none 或 student 为空：status=ask，hint「没有找到叫「student」的学生。现有学生：roster」（student 为空写「你想看哪位学生？现有学生：roster」）；many：status=ask，hint「找到多位：显示名（用户名）、…，你指哪一位？」；one：调用 学生范围 subject_id=subject_id 取该生 last_at，context_text = 学生上下文 username=该生 username display_name=该生 display_name last_at=该生 last_at subject_id=subject_id，student、student_name 填上
  伪代码 point_status：调用 匹配知识点 keyword=point subject=subject_id。none 或 point 为空：status=ask，hint「没有找到「point」这个知识点或条目，换个说法试试（知识点名、条目名或编号都行）」（point 为空写「你想看哪个知识点？」）；many：status=ask，hint「找到多个：标题（编号）、…（共 total 个，最多列 5 个），你指哪一个？」；one：context_text = 知识点上下文 code=该编号 title=该标题 subject_id=subject_id，point、point_title 填上
  伪代码 teaching_advice：context_text = 建议上下文 current_user=learner subject_id=subject_id；student 不为空时再调用 匹配学生 name=student subject=subject_id，one 的话把学生上下文附在后面并填 student（none 或 many 不拦，只是不附，不改 status）；point 不为空时同理用 匹配知识点 keyword=point subject=subject_id，one 的话把知识点上下文附在后面并填 point；整段 context_text 总长度上限 4500 个字，超出从最后附加的段落末尾砍起
  伪代码 chitchat：context_text = 系统功能说明（固定文字：教师端有学情、学生管理、教师助手、AI 老师设定、教材导入五页各管什么；学生端有问老师、做题、默写、教材、学习进度、知识图谱；助手本身只读，不能改设定、不能出题、不能给学生发话）；status 为 ok
  伪代码 返回 {"ok": 1, "intent": intent, "status": status, "student": …, "student_name": …, "point": …, "point_title": …, "hint": …, "context_text": …}

函数 判意图 message recent focus_text
  返回 {intent, student, point}；intent 只会是 class_overview / student_detail / point_status / teaching_advice / chitchat；student、point 是老师话里提到的学生名、知识点名原文（可空串，不是编号）
  伪代码 问JSON（快档）：给模型老师这句话、最近对话 recent、上一轮聚焦 focus_text，让它判意图并抽出学生名和知识点名（「他」「她」「这个学生」指上一轮聚焦的学生、「这个语法」指上一轮聚焦的知识点时，填上一轮的显示名/标题），要求返回 {"intent": …, "student": …, "point": …}
  伪代码 模型出错或返回不合法（intent 不在五个值里）：message 含「全班」「班级」「大家」「整体」「所有学生」任一则 intent 取 class_overview，否则取 chitchat；student、point 取空串（兜底，不报错）
  伪代码 student、point 缺失取空串并去首尾空白
  伪代码 返回 {"intent": intent, "student": student, "point": point}

函数 写一轮 current_user user_text reply intent student point status subject_id
  返回 reply_id（助手回复那一行的 id）
  伪代码 在一个事务里：往 teacher_assist_message 插入老师那条 (teacher=current_user, role=user, content=user_text, intent, student, point, status, at=当前时间, subject_id=subject_id)，再插入助手那条 (role=assistant, content=reply，其余同上)，取其新行 id 为 reply_id
  伪代码 任一步报错，整个事务回滚、整轮不记，错误原样向上抛
  伪代码 返回 reply_id

函数 答一轮 current_user user_text intent context_text student point subject_id
  返回 {reply_id, reply}；用模型回答的路径（五种意图共用）
  伪代码 recent = 调用 取最近对话 current_user=current_user limit=6 subject_id=subject_id（此时本句还没写库，所以不含本句）
  伪代码 系统提示 = 助手人设（教师端的教学助手，对老师像同事一样说话，只读）+ 回答规则（写进系统提示里：①数字、人名、名单、知识点名、课号、标题、日期只能原样取自【数据】，不得自己推算新数字、不得「大约」「差不多」估算，唯一允许的是数一数【数据】里列出的行；②【数据】里没有的就直说「这份数据里没有」，不猜、不编，也不要说系统没有的功能；③不要写「昨天」「上周」「几天前」这类相对时间，只能原样引用【数据】里写明的日期；④最近对话里出现过的数字可能已过时，以【数据】为准；⑤你只读：不能改设定、不能给学生发话、不能出题、不能起草传达，老师要这些时告诉老师去哪个页面做；⑥只输出纯文本，不用 Markdown 的标题、加粗、表格、列表符号，不用 emoji；名单每人一行，行首用「・」；⑦一般不超过 300 字，名单最多列 10 人；⑧给教学建议时先说依据（引用【数据】里的哪几项），再给 1 到 3 条具体做法，推荐课文只能用【数据】里的课号和标题；⑨闲聊或问系统用法时简短自然地回应，用法只依据【数据】里的系统功能说明）
  伪代码 用户内容 = 【数据】context_text + 【最近对话】recent + 【老师最新一句】user_text
  伪代码 问（回答档）：系统提示、用户内容，得 reply；模型出错或回复为空，报错 400 助手暂时无法回答，整轮不写任何表
  伪代码 调用 写一轮 current_user=current_user user_text=user_text reply=reply intent=intent student=student point=point status=ok subject_id=subject_id，得 reply_id
  伪代码 返回 {"reply_id": reply_id, "reply": reply}

公开 函数 问助手 current_user message current_role? auth_mode? subject?
  返回 {ok, reply_id, reply, intent, student, point, status}；status 为 ok / ask；对话记录写在当前科目下
  报错 400 current_user 不能为空
  报错 400 消息不能为空
  报错 400 助手暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（用户名取 current_user；路由层注入角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 current_user 为空，报错 400 current_user 不能为空；message 去首尾空白后为空，报错 400 消息不能为空
  伪代码 recent = 调用 取最近对话 current_user=current_user limit=6 subject_id=subject_id；focus = 调用 取上轮聚焦 current_user=current_user subject_id=subject_id，拼成 focus_text（「学生 显示名（用户名）；知识点 标题（编号）」，都没有写「无」）
  伪代码 调用 判意图 message=message recent=recent focus_text=focus_text，得 intent、student、point
  伪代码 intent 等于 student_detail 且 student 为空且上轮聚焦的学生不为空：student 取上轮聚焦学生的显示名；intent 等于 point_status 且 point 为空且上轮聚焦的知识点不为空：point 取上轮的知识点标题（代码层再补一层，不全靠模型）
  伪代码 调用 取助手上下文 intent=intent student=student point=point subject=subject_id，得 status、hint、context_text、匹配到的 student、point
  伪代码 status 等于 ask：不调回答模型，调用 写一轮 current_user=current_user user_text=message reply=hint intent=intent student=空 point=空 status=ask subject_id=subject_id（student=空 point=空，没匹配成功不写聚焦，下一轮「他」不会指向没找到的人），得 reply_id
  伪代码 status 等于 ok：调用 答一轮 current_user=current_user user_text=message intent=intent context_text=context_text student=匹配到的学生 point=匹配到的知识点 subject_id=subject_id，得 reply_id、reply
  伪代码 返回 {"ok": 1, "reply_id": reply_id, "reply": reply, "intent": intent, "student": 匹配到的学生, "point": 匹配到的知识点, "status": status}

公开 函数 列对话 current_user limit? current_role? auth_mode? subject?
  返回 {teacher, total, messages}；messages 是 [{id, role, content, intent, student, point, status, at}]，取该教师在本科目最近 limit 条（默认 50），按 id 升序
  报错 400 current_user 不能为空
  报错 400 limit 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（用户名取 current_user；路由层注入角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id
  伪代码 current_user 为空，报错 400 current_user 不能为空
  伪代码 limit 为空取 50；不是大于等于 1 的整数，报错 400 limit 不合法
  伪代码 查 teacher_assist_message 中该 teacher 且 subject_id 等于本科目的行（别的科目的对话不出现），按 id 降序取前 limit 条，再翻成升序
  伪代码 返回 {"teacher": current_user, "total": 条数, "messages": 列表}

公开 函数 列对话页面 current_user current_role? auth_mode? subject?
  返回 {talk}；助手页消息流的消息列表（本科目最近 40 条，按时间正序），每条 {who, text, kind}：who 为「助手」或「你」，text 为内容，kind 老师那条为 user、助手那条为空串
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（用户名取 current_user；路由层注入角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；本函数在本模块内调用其它函数（含公开函数）时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 列对话 current_user=current_user limit=40 subject=subject_id，得 messages
  伪代码 逐条转换：role 等于 assistant 则 who=助手、kind=空串，否则 who=你、kind=user；text=content
  伪代码 返回 {"talk": 列表}

公开 函数 问助手页面 current_user message current_role? auth_mode? subject?
  返回 与 问助手 相同：{ok, reply_id, reply, intent, student, point, status}；前端「发送」按输入框一句话走问助手
  报错 400 消息不能为空
  报错 400 助手暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（用户名取 current_user；路由层注入角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；本函数在本模块内调用其它函数（含公开函数）时一律带 subject=subject_id（已解析，不再校验）
  伪代码 message 是前端输入框的 content（接口行 参数 content=message）
  伪代码 调用 问助手 current_user=current_user message=message subject=subject_id 并原样返回其结果（错误原样向上抛）

## 接口
POST /teacher_assist/ask -> 问助手页面 动作 assist_send 模板 回复消息 谁=助手 取=reply 参数 content=message 角色 teacher
POST /teacher_assist/history -> 列对话页面 动作 assist_state 模板 状态 键=talk 取=talk 角色 teacher
GET /teacher_assist/messages -> 列对话 角色 teacher

## 用例
用例 匹配学生_显示名唯一
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明
  得 status=one username=s1 display_name=小明

用例 匹配学生_带同学二字
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明同学
  得 status=one username=s1

用例 匹配学生_用户名忽略大小写
  先 数据 account_user username=ab12 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=ab12 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=AB12
  得 status=one username=ab12

用例 匹配学生_模糊匹配到多个
  先 数据 account_user username=s1 password_hash=x display_name=王小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=李小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明
  得 status=many

用例 匹配学生_没有这个人
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=张三
  得 status=none

用例 匹配学生_教师账号不参与
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2025-12-01
  调用 匹配学生 name=王老师
  得 status=none

用例 匹配学生_名字为空
  调用 匹配学生 name=空
  得 status=none

用例 匹配知识点_标题唯一
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=P2 title=助词が
  调用 匹配知识点 keyword=助词は
  得 status=one code=P1 title=助词は

用例 匹配知识点_按条目名找到所属知识点
  先 数据 kg_point code=P1 title=时间表达
  先 数据 kg_item code=I1 name=ばかり point_code=P1
  调用 匹配知识点 keyword=～ばかり
  得 status=one code=P1

用例 匹配知识点_多个
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=P2 title=助词が
  调用 匹配知识点 keyword=助词
  得 status=many total=2

用例 匹配知识点_没有
  先 数据 kg_point code=P1 title=助词は
  调用 匹配知识点 keyword=被动态
  得 status=none total=0

用例 取助手上下文_全班概况
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=40 at=2026-01-01
  调用 取助手上下文 intent=class_overview
  得 ok=1 intent=class_overview status=ok
  库 teacher_assist_message 共 0 行

用例 取助手上下文_学生详情
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=40 at=2026-01-01
  调用 取助手上下文 intent=student_detail student=小一
  得 status=ok student=s1 student_name=小一

用例 取助手上下文_学生没找到要追问
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 取助手上下文 intent=student_detail student=张三
  得 status=ask student=空

用例 取助手上下文_学生有多个要追问
  先 数据 account_user username=s1 password_hash=x display_name=王小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=李小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  调用 取助手上下文 intent=student_detail student=小明
  得 status=ask

用例 取助手上下文_没说是哪个学生
  调用 取助手上下文 intent=student_detail
  得 status=ask

用例 取助手上下文_知识点掌握
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_mastery learner=s1 point_code=P1 right_count=0 total_count=1 mastered=0 updated_at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=40 at=2026-01-01
  调用 取助手上下文 intent=point_status point=一次函数
  得 status=ok point=P1 point_title=一次函数

用例 取助手上下文_知识点没找到要追问
  先 数据 kg_point code=P1 title=一次函数
  调用 取助手上下文 intent=point_status point=被动态
  得 status=ask point=空

用例 取助手上下文_教学建议
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 lesson_text code=L1 level=N5 title=はとが summary=主题助词 explain=x connection=x examples=x examples_edited=0 orig_title=x series_code=hanabira seq=1
  先 数据 lesson_point_link lesson_code=L1 point_code=P1
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=20 at=2026-01-01
  调用 取助手上下文 intent=teaching_advice
  得 ok=1 status=ok

用例 取助手上下文_闲聊给系统功能说明
  调用 取助手上下文 intent=chitchat
  得 status=ok intent=chitchat

用例 取助手上下文_意图不合法
  调用 取助手上下文 intent=bad
  报错 400

用例 问助手_正常
  调用 问助手 current_user=t1 message=你好
  得 ok=1 status=ok
  库 teacher_assist_message 共 2 行
  库 teacher_assist_message 含 teacher=t1 role=user content=你好
  库 teacher_assist_message 含 teacher=t1 role=assistant status=ok

用例 问助手_消息为空
  调用 问助手 current_user=t1 message=空
  报错 400
  库 teacher_assist_message 共 0 行

用例 问助手_教师为空
  调用 问助手 current_user=空 message=你好
  报错 400
  库 teacher_assist_message 共 0 行

用例 列对话_正常
  先 数据 teacher_assist_message teacher=t1 role=user content=问题一 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t1 role=assistant content=回答一 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t2 role=user content=别人的 status=ok at=2026-01-01
  调用 列对话 current_user=t1
  得 teacher=t1 total=2

用例 列对话_limit截取最近
  先 数据 teacher_assist_message teacher=t1 role=user content=一 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t1 role=assistant content=二 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t1 role=user content=三 status=ok at=2026-01-01
  调用 列对话 current_user=t1 limit=2
  得 total=2

用例 列对话_没有记录
  调用 列对话 current_user=t1
  得 total=0

用例 列对话_limit非法
  调用 列对话 current_user=t1 limit=0
  报错 400

用例 列对话_教师为空
  调用 列对话 current_user=空
  报错 400

用例 列对话页面_转换消息字段
  先 数据 teacher_assist_message teacher=t1 role=user content=问题一 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t1 role=assistant content=回答一 intent=class_overview status=ok at=2026-01-01
  调用 列对话页面 current_user=t1
  得 有返回

用例 问助手页面_正常
  调用 问助手页面 current_user=t1 message=全班怎么样
  得 ok=1
  库 teacher_assist_message 共 2 行

用例 问助手页面_消息为空
  调用 问助手页面 current_user=t1 message=空
  报错 400
  库 teacher_assist_message 共 0 行

用例 跨科目_列对话只看本科目
  先 数据 teacher_assist_message teacher=t1 role=user content=日语问题 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t1 role=user content=数学问题一 status=ok at=2026-01-01 subject_id=2
  先 数据 teacher_assist_message teacher=t1 role=assistant content=数学回答一 status=ok at=2026-01-01 subject_id=2
  调用 列对话 current_user=t1 subject=2
  得 teacher=t1 total=2

用例 跨科目_列对话不传科目是日语
  先 数据 teacher_assist_message teacher=t1 role=user content=日语问题 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t1 role=user content=数学问题一 status=ok at=2026-01-01 subject_id=2
  调用 列对话 current_user=t1
  得 teacher=t1 total=1

用例 跨科目_列对话页面只看本科目
  先 数据 teacher_assist_message teacher=t1 role=user content=日语问题 status=ok at=2026-01-01
  先 数据 teacher_assist_message teacher=t1 role=user content=数学问题一 status=ok at=2026-01-01 subject_id=2
  调用 列对话页面 current_user=t1 subject=3
  得 talk=[]

用例 跨科目_问助手对话落当前科目
  调用 问助手 current_user=t1 message=你好 subject=2
  得 ok=1 status=ok
  库 teacher_assist_message 共 2 行
  库 teacher_assist_message 含 teacher=t1 role=user content=你好 subject_id=2
  库 teacher_assist_message 含 teacher=t1 role=assistant status=ok subject_id=2

用例 跨科目_问助手页面对话落当前科目
  调用 问助手页面 current_user=t1 message=全班怎么样 subject=2
  得 ok=1
  库 teacher_assist_message 共 2 行
  库 teacher_assist_message 含 teacher=t1 role=user subject_id=2

用例 跨科目_匹配学生只在登记的学生里
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小红 subject=2
  得 status=none

用例 跨科目_匹配学生本科目登记的
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明 subject=2
  得 status=one username=s1 display_name=小明

用例 跨科目_匹配学生不传科目是日语登记的学生
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小红
  得 status=one username=s2

用例 跨科目_匹配学生日语没登记的匹配不到
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明
  得 status=none

用例 跨科目_匹配知识点只看本科目
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 匹配知识点 keyword=代数
  得 status=none total=0

用例 跨科目_匹配知识点本科目
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 匹配知识点 keyword=代数 subject=2
  得 status=one code=math.a title=代数

用例 跨科目_匹配知识点按条目名只看本科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=因式分解 point_code=math.a subject_id=2
  调用 匹配知识点 keyword=因式分解
  得 status=none

用例 跨科目_取助手上下文学生详情本科目
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=40 at=2026-01-01 subject_id=2
  调用 取助手上下文 intent=student_detail student=小一 subject=2
  得 status=ok student=s1 student_name=小一

用例 跨科目_取助手上下文学生没登记要追问
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  调用 取助手上下文 intent=student_detail student=小一 subject=2
  得 status=ask student=空

用例 跨科目_取助手上下文全班概况本科目
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 取助手上下文 intent=class_overview subject=2
  得 ok=1 intent=class_overview status=ok
  库 teacher_assist_message 共 0 行

用例 跨科目_取助手上下文知识点掌握本科目
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_mastery learner=s1 point_code=math.a right_count=0 total_count=1 mastered=0 updated_at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=40 at=2026-01-01 subject_id=2
  调用 取助手上下文 intent=point_status point=代数 subject=2
  得 status=ok point=math.a point_title=代数

用例 跨科目_取助手上下文知识点别的科目要追问
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 取助手上下文 intent=point_status point=代数
  得 status=ask point=空

用例 跨科目_登录模式私有科目非负责教师被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 问助手 current_user=t9 message=你好 current_role=teacher auth_mode=on subject=2
  报错 403
  库 teacher_assist_message 共 0 行

用例 跨科目_登录模式列对话私有科目非负责教师被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 列对话 current_user=t9 current_role=teacher auth_mode=on subject=2
  报错 403

用例 跨科目_登录模式负责教师可问助手
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 问助手 current_user=t1 message=你好 current_role=teacher auth_mode=on subject=2
  得 ok=1 status=ok
  库 teacher_assist_message 含 teacher=t1 role=user subject_id=2

用例 跨科目_科目不存在
  调用 列对话 current_user=t1 current_role=teacher auth_mode=on subject=9
  报错 404

用例 跨科目_科目不是数字
  调用 列对话 current_user=t1 subject=abc
  报错 400
