模块 report
依赖 account progress dictation tutor teacher_rules kg lesson subject

## 表
表 report_summary
  student 文本 被总结的学生用户名
  summary 长文本 AI 写的学情总结
  author 文本 写的人（教师用户名）
  created_at 文本 写的时间，格式 YYYY-MM-DD HH:MM:SS
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 页面字段
页面 report_view 学情页面
  report_sort 枚举 最近学习,平均得分 排序
  label 文本 全班表「学生」、知识点表「知识点」等列（显示名）
  last_active 文本 全班表「最近学习」列
  attempt_n 整数 全班表「作答数」列
  recent_rate 文本 全班表「近期正确率」列
  avg_score 文本 全班表「平均得分」列
  mastered_n 整数 全班表「已掌握」列
  weak_points 文本 全班表「薄弱知识点」列
  book_n 整数 全班表「错词本」列
  wrong_n 整数 薄弱点表「答错」列
  answer_n 整数 薄弱点表「作答」列
  learner_n 整数 薄弱点表「答错的人数」列
  point_label 文本 条目表「所属知识点」列
  tally 文本 「答对/答题」列
  score_text 文本 知识点表「得分」列
  mastered_text 文本 知识点表「掌握」列
  last_wrong 文本 「最近答错」列
  at 文本 最近作答表「时间」列
  stem_brief 文本 最近作答表「题干」列
  given_text 文本 最近作答表「作答」列
  result 文本 最近作答表「对错」列
  direction_label 文本 错词表「方向」列
  chat_q 文本 问老师筛选「关键词」
  chat_from 文本 问老师筛选「起始日期」
  chat_to 文本 问老师筛选「结束日期」
  chat_intent 枚举 全部,出题,进度,教材,讲解,本轮总结 问老师筛选「意图」
  chat_id 整数 问老师表一轮的编号
  chat_at 文本 问老师表「时间」列
  chat_intent_label 文本 问老师表「意图」列
  chat_ask 文本 问老师表「学生问」列
  chat_reply 文本 问老师表「AI老师答」列
  chat_notes 文本 问老师表「用了的设定」列
  link_label 文本 问老师全文链接表「名称」列
  link_url 文本 问老师全文链接表「地址」列

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出）；本模块只有 写学情总结、写学情总结页面 传 need=write（往 report_summary 写一行带科目、别的教师会读的总结，属于写科目数据，只有负责/协作教师可写），其余函数按读

函数 学生范围 subject_id
  返回 [{username, display_name, status, last_at}]；本科目的学生范围，按 account.列学生 的顺序；last_at 是该生在本科目的最近学习时间（本科目没有作答为空串）
  伪代码 调用 account.列学生 subject=subject_id（K170：按本科目取 last_at；不传 subject 时 列学生 只算日语科目，学生只在 Python 科目作答时 Python 学情里「最近学习」为空），得全部学生（含停用），带出 username、display_name、status、last_at
  伪代码 所有科目（含 1 号日语）统一：调用 subject.列科目学生 subject_id=subject_id，得 students；只留 username 在 students 各项 learner 里的学生（科目里登记且 active 的学生；没有登记或已撤销的学生不出现），顺序不变。不再有「1 号=全部学生」的特例，也不按 id=1 判断：新建的学生由 account.建学生 自动登记进日语科目（jp_grammar），已有学生由 migrate_subject.py 补登记

函数 取点等级 point_code subject_id
  返回 等级文本（本科目等级之一，即 subject.科目等级 里的一项；日语 N5 到 N1），取不到返回空串
  伪代码 调用 lesson.取知识点等级 point_code=point_code subject=subject_id 出错时 e
  伪代码 出错（如 404）或其 level 为空，返回空串；否则返回其 level

函数 算学生指标 username subject_id
  返回 {answer_total, recent_accuracy, avg_score, mastered_count, wrong_book_count, weak_all}；weak_all 是该学生在本科目的全部低分点 [{point_code, title, score}]，得分低的在前
  伪代码 调用 progress.取概览 learner=username subject=subject_id，取 answer_total、mastered_count
  伪代码 调用 progress.列最近作答 learner=username limit=20 subject=subject_id，得 total 和 answers；recent_accuracy = 四舍五入(其中 correct 等于 1 的个数 * 100 / total)，total 为 0 时为 0（近期正确率按最近 20 条作答算）
  伪代码 调用 progress.列得分 learner=username subject=subject_id，avg_score = 四舍五入(各知识点当前 score 的平均值)，没有得分行为 0
  伪代码 调用 progress.列低分点 learner=username limit=1000 subject=subject_id，得 weak_all（阈值取 progress 默认的 80 分以下）
  伪代码 调用 dictation.统计错词本数 learner=username subject=subject_id，取 total 为 wrong_book_count
  伪代码 返回 {"answer_total": …, "recent_accuracy": …, "avg_score": …, "mastered_count": …, "wrong_book_count": …, "weak_all": …}

公开 函数 取全班学情 sort_by? student? learner? current_role? auth_mode? subject?
  返回 {total, students, weak_point_count, weak_item_count, weak_points, weak_items}；students 每项 {username, display_name, status, answer_total, recent_accuracy, avg_score, mastered_count, weak_count, weak_points, wrong_book_count, last_at}，weak_points 是该生最低分的前 5 个 [{point_code, title, score}]，weak_count 是该生低分点总数；全班 weak_points 是前 10 个 [{point_code, title, student_count, avg_score, level}]；weak_items 是前 10 个 [{code, name, point_code, student_count}]。只读；student 不为空时只统计该学生；学生范围是当前科目里登记的学生，所有数据都只取本科目
  报错 400 排序方式不对
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 sort_by 为空取 last_at；不是 last_at 也不是 avg_score，报错 400 排序方式不对
  伪代码 调用 学生范围 subject_id=subject_id，得本科目的学生（含停用），带出 username、display_name、status、last_at；student 不为空时只留 username 等于它的学生（不在本科目学生范围里的得空，total 为 0）
  伪代码 对每个学生调用 算学生指标 username=该学生 username subject_id=subject_id，拼出一行；weak_count 为 weak_all 个数，weak_points 取 weak_all 前 5 个
  伪代码 排序：sort_by 为 last_at 时按 last_at 降序（最近学习的在前，没有作答 last_at 为空串的排最后），相同按 username 升序；sort_by 为 avg_score 时按 avg_score 升序（分低的在前），相同按 username 升序
  伪代码 全班薄弱知识点：把所有学生的 weak_all 按 point_code 合并，student_count 是有该低分点的学生数，avg_score 是这些学生该点得分的平均（四舍五入），level 调用 取点等级 point_code=该编号 subject_id=subject_id；按 student_count 降序、avg_score 升序、point_code 升序，取前 10 个
  伪代码 全班薄弱条目：对合并出的每个薄弱知识点（不限于前 10）调用 kg.按知识点列条目 point_code=该编号 subject=subject_id 出错时 e，出错的跳过；其每个条目的 student_count 取该知识点的 student_count；按 student_count 降序、code 升序，取前 10 个
  伪代码 weak_point_count 和 weak_item_count 是全班薄弱知识点、薄弱条目合并后的总数（取前 10 之前的个数）
  伪代码 返回 {"total": 学生数, "students": 列表, "weak_point_count": …, "weak_item_count": …, "weak_points": 前10, "weak_items": 前10}

公开 函数 取学生学情 student learner? current_role? auth_mode? subject?
  返回 {student, display_name, status, answer_total, recent_accuracy, avg_score, mastered_count, wrong_count, wrong_answers, wrong_book_count, wrong_book, weak_count, weak_points, question_count, dialog_last_at, recent_questions, relay_count, relays, has_summary, summary, summary_author, summary_at}；wrong_answers 是最近答错的题 [{point_code, title, question_no, answer, at, score, mastered}]（题干由 quiz 持有，本模块不依赖 quiz，故只给题号与知识点标题）；wrong_book 是错词本 [{word_id, direction, kanji, kana, meaning, last_answer, last_at}]；weak_points 是前 10 个低分点 [{point_code, title, score, level}]；recent_questions 是最近 5 条学生提问 [{content, intent, at}]；relays 是该生的传达状态 [{relay_id, must_info, rounds, rounds_done, finished, confirmed}]；has_summary 为 1 时 summary、summary_author、summary_at 是最近一份学情总结，否则为空串。只读；所有数据只取本科目；学生不在本科目学生范围里（没有登记或已撤销，含只登记在别的科目的学生）与不存在一样
  报错 400 student 不能为空
  报错 404 没有这个学生
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）；这里的 learner 是登录用户，不是被看的 student
  伪代码 student 为空，报错 400 student 不能为空
  伪代码 调用 account.取账号 username=student，取不到或 role 不等于 student，报错 404 没有这个学生
  伪代码 调用 学生范围 subject_id=subject_id，其中没有 username 等于 student 的学生（包括登记在别的科目的学生），报错 404 没有这个学生
  伪代码 调用 算学生指标 username=student subject_id=subject_id，得各指标和 weak_all
  伪代码 调用 progress.列错题 learner=student limit=10 subject=subject_id，得 wrong_answers 和 wrong_count（total）；每行调用 kg.取知识点 code=point_code subject=subject_id 取 title，取不到取空串
  伪代码 调用 dictation.取错词本 learner=student subject=subject_id，得 wrong_book 和 wrong_book_count
  伪代码 weak_count 是 weak_all 个数；weak_points 取 weak_all 前 10 个，每个调用 取点等级 point_code=该编号 subject_id=subject_id 取 level
  伪代码 调用 tutor.取对话摘要 learner=student subject=subject_id，取 question_count、last_at（为 dialog_last_at）、recent（为 recent_questions）
  伪代码 调用 teacher_rules.列传达状态 student=student subject=subject_id，取 items 为 relays、total 为 relay_count
  伪代码 调用 取最近总结 student=student subject=subject_id，得 has_summary、summary、author、created_at
  伪代码 返回上述对象，status 取自账号 disabled（1 为「停用」，否则「启用」）

公开 函数 写学情总结 student current_user current_role? auth_mode? subject?
  返回 {ok, id, student, summary, author, created_at}
  报错 400 student 不能为空
  报错 400 current_user 不能为空
  报错 404 没有这个学生
  报错 400 老师暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；current_role、auth_mode、subject 都可选（用户名取 current_user；路由层注入角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；auth_mode 等于 on 时只有该科目的负责/协作教师能写，公共科目的其他教师、学生报 403 没有权限修改该科目（单人模式不校验）；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 student 为空，报错 400 student 不能为空；current_user 为空，报错 400 current_user 不能为空
  伪代码 调用 取学生学情 student=student subject=subject_id（学生不存在、不是学生或不在本科目学生范围里则报 404 没有这个学生）
  伪代码 问（回答档）：把学情（近期正确率、平均得分、已掌握数、最近答错的题、错词本、薄弱点、问老师的提问摘要、传达状态）交给模型，要求写一段给教师看的学情总结；模型出错报错 400 老师暂时无法回答，不写库
  伪代码 回答语言（K181）：lg = 调用 account.取语言 username=current_user 得 lang；lang 等于 ja 时在提示词最末尾追加空格加一句「请用日语回答，专业术语第一次出现时用括号标注中文；与其他提示里的语言要求冲突时，以本句为准。」（学情总结给教师看，跟随教师界面语言；总结提示词是系统拼的、不来自教师设定，无覆盖判断）；lang 为 zh、空或查不到该教师时提示词与旧版逐字一致
  伪代码 往 report_summary 插入一行 (student, summary=总结, author=current_user, created_at=当前时间, subject_id=subject_id)，取其 id（总结只存在本表，不写 tutor 的问老师对话记录）
  伪代码 返回 {"ok": 1, "id": id, "student": student, "summary": 总结, "author": current_user, "created_at": 当前时间}

公开 函数 取最近总结 student learner? current_role? auth_mode? subject?
  返回 {student, has_summary, id, summary, author, created_at}；该学生在本科目没有总结时 has_summary 为 0，id 为 0，其余为空串（下次打开直接看上一份，不调模型）
  报错 400 student 不能为空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id
  伪代码 student 为空，报错 400 student 不能为空
  伪代码 查 report_summary 中 student 相等且 subject_id 等于本科目的行（别的科目的总结不出现），取 id 最大的一行
  伪代码 没有则返回 {"student": student, "has_summary": 0, "id": 0, "summary": "", "author": "", "created_at": ""}
  伪代码 返回 {"student": student, "has_summary": 1, "id": 该行 id, "summary": 该行 summary, "author": 该行 author, "created_at": 该行 created_at}

函数 取题干 question_no lang?
  返回 题干文本，查不到返回空串（学情页给错题回题干，§七-13）；lang 为空视为 zh
  伪代码 K182 内容日语替换：lang 等于 ja 时调 subject.译文 tbl=quiz_question row_key=该题号 field=stem lang=ja，非空返回译文；zh 或无译文返回原题干（与改前逐字一致）
  伪代码 用 app.db 查询 report_quiz_exists（sqlite_master 里有没有 quiz_question 表）：没有（模块用例的库不含下游 quiz 的表）返回空串——report 不声明依赖 quiz，不调 quiz 的函数，只读它的表
  伪代码 有则查 app.db report_quiz_stem（quiz_question 按 question_no 取 stem），查不到返回空串；题号全局唯一，题干查询不按科目限定（调用方的题号来自本科目的作答流水）

函数 缩略 text n
  返回 text 超过 n 个字时取前 n 个字加「…」，否则原文
  伪代码 text 为空返回空串

函数 地址段 text
  返回 {v}；把一段文字放进地址参数用的编码
  伪代码 查一行 app.db report_url_part text=text，只转 % & # + = ? { } 空白 这几种（% 最先转），其余原样（汉字由浏览器和 URLSearchParams 处理）

函数 意图标签 code
  返回 {label}；quiz 出题、progress 进度、textbook 教材、explain 讲解、summary 本轮总结；空串返回空串；别的原样返回

函数 学生对话地址 student chat_page? chat_kw? chat_start? chat_end? chat_kind?
  返回 {href}；形如 #%E5%AD%A6%E6%83%85?student=…&chat_page=…&chat_kw=…&chat_start=…&chat_end=…&chat_kind=…；student 和 chat_kw 经 地址段 编码；后五个参数为空时不出现；chat_page 等于 1 时也不出现。引擎事实：值恰好形如 {name} 时「如果 {x} 不为空」判成空，所以 chat_kw 要先调 地址段 得 v，再判断 v 是否为空（编码后不再是 {name} 的形状）

函数 问老师表单 chat_kw? chat_start? chat_end? chat_kind?
  返回 {chat_q, chat_from, chat_to, chat_intent}；把地址里的筛选条件填回筛选框：chat_q=chat_kw，chat_from=chat_start，chat_to=chat_end，chat_intent=调用 意图标签 code=chat_kind 的 label，为空时写 全部

公开 函数 问老师筛选 student chat_q? chat_from? chat_to? chat_intent? learner? current_role? auth_mode? subject?
  返回 {go}；点「筛选」（动作 report_chat_search）：检查条件，算出带条件的地址，页码回到第 1 页；只读，不写任何表
  报错 400 student 不能为空
  报错 400 日期要写成 YYYY-MM-DD
  报错 400 意图不对
  报错 404 没有这个学生
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id
  伪代码 student 为空，报错 400 student 不能为空；调用 学生范围 subject_id=subject_id 里没有 username 等于 student 的学生，报错 404 没有这个学生
  伪代码 chat_intent 为空或「全部」时 kind 为空串；出题 quiz、进度 progress、教材 textbook、讲解 explain、本轮总结 summary；别的报错 400 意图不对
  伪代码 chat_from、chat_to 不为空且不匹配 ^[0-9]{4}-[0-9]{2}-[0-9]{2}$，报错 400 日期要写成 YYYY-MM-DD
  伪代码 kw = chat_q 去首尾空白；调用 学生对话地址 student=student chat_kw=kw chat_start=chat_from chat_end=chat_to chat_kind=kind，返回 {"go": href}（不带 chat_page，就是第 1 页）

公开 函数 问老师全文页面 student chat_id chat_kw? chat_start? chat_end? chat_kind? learner? current_role? auth_mode? subject?
  返回 {chat_full, chat_links, form}；「看全文」浮层的「载入」（动作 report_chat_full）。chat_full={id, at, intent_label, ask, reply, notes, lesson_text, lesson_href}；chat_links=[{link_label, link_url}]；form 由 问老师表单 给（筛选框里的值不丢）；只读，不写任何表
  报错 400 student 不能为空
  报错 400 round_id 不合法
  报错 404 没有这个学生
  报错 404 没有这条问老师记录
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id
  伪代码 student 为空，报错 400 student 不能为空；调用 学生范围 subject_id=subject_id 里没有 username 等于 student 的学生，报错 404 没有这个学生
  伪代码 调用 tutor.取问答轮 learner=student round_id=chat_id subject=subject_id 得 t（错误原样向上抛）
  伪代码 notes：t.reply_id 大于 0 时调用 teacher_rules.取回复用到 reply_id=t.reply_id subject=subject_id 取 text，否则空串
  伪代码 lesson_text、lesson_href：t.lesson_code 为空时都是空串；否则调用 lesson.取课文 code=t.lesson_code subject=subject_id 出错时 e，取 title（出错时 title 空串）；lang = 调用 account.取语言 username=learner 取 lang，ja 时调用 subject.译文 tbl=lesson_text row_key=t.lesson_code field=title lang=ja，非空才替换 title；lesson_text=「{课号} {title}」，title 为空时只有课号；lesson_href=#%E8%AF%BE%E6%96%87%E6%9F%A5%E7%9C%8B?code={课号经 地址段 编码}
  伪代码 chat_links：t.links 每项 {link_label: label, link_url: url}；t.links 为空且 t.link 不为空时一行 {link_label: 链接, link_url: t.link}
  伪代码 intent_label：调用 意图标签 code=t.intent 取 label
  伪代码 form：调用 问老师表单 chat_kw=chat_kw chat_start=chat_start chat_end=chat_end chat_kind=chat_kind
  伪代码 返回 {"chat_full": {id, at, intent_label, ask, reply, notes, lesson_text, lesson_href}, "chat_links": 列表, "form": form}；ask、reply 都是全文，不缩略

公开 函数 学情首页页面 report_sort? learner? current_role? auth_mode? subject?
  返回 {class_rows, class_weak_points, class_weak_items, class_count, form}；学情页「进入时/排序」（动作 report_home）的整页状态；report_sort 是页面下拉值「最近学习」「平均得分」（空当最近学习，其它值也当最近学习）；form 回填 {report_sort: 所选}；学生范围是当前科目里登记的学生
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 取全班学情 sort_by=（report_sort 为「平均得分」传 avg_score，否则传 last_at） subject=subject_id，得 students；report_sort 为「平均得分」时再整理一次顺序：answer_total 为 0（没打过分）的学生排到最后，其余保持 取全班学情 给的顺序（旧页行为：没打过分的排最后）
  伪代码 class_rows 每个学生一行 {username, label, href, last_active, attempt_n, recent_rate, avg_score, mastered_n, weak_points, book_n}：label 是 display_name 为空取 username；href=#%E5%AD%A6%E6%83%85?student={username}；last_active=last_at；attempt_n=answer_total；recent_rate 在 answer_total 为 0 时是「—」否则「{recent_accuracy}%」；avg_score 在 answer_total 为 0 时是「—」否则数字；mastered_n=mastered_count；weak_points 取该生 weak_points 前 3 个的 title 用「、」连接，没有为「—」；book_n=wrong_book_count；顺序同 students
  伪代码 class_count=「共{学生数}个学生」；form={"report_sort": 所选，空取「最近学习」}
  伪代码 全班薄弱点聚合：对每个学生调用 progress.取状态 learner=该学生 subject=subject_id，points 每项（code, title, right, total）：wrong=total-right，按 code 累计 wrong_n（wrong 之和）、answer_n（total 之和）、learner_n（wrong 大于 0 的学生数）；只留 wrong_n 大于 0 的点，按 wrong_n 降序、answer_n 降序、code 升序
  伪代码 class_weak_points 取聚合前 10 个，每个 {label: title, wrong_n, answer_n, learner_n}
  伪代码 class_weak_items：对聚合出的每个点（不限前 10）调用 kg.按知识点列条目 point_code=该点 subject=subject_id 出错时 e，出错的跳过；每个条目一行 {label: name, point_label: 该点 title, wrong_n/answer_n/learner_n 取该点的值（v4 按知识点记作答，条目沿用所属知识点的数）, code}，按 wrong_n 降序、answer_n 降序、code 升序，取前 10 个
  伪代码 K182 内容日语替换：lang = 调用 account.取语言 username=learner 取 lang（查不到为空视为 zh）；ja 时 class_weak_points 的 label（知识点 title）与 class_weak_items 的 label/point_label（条目 name、知识点 title）调用 subject.译文（tbl=kg_point field=title / tbl=kg_item field=name，row_key=对应编号），非空才替换；取全班学情 等共享函数不改（还要喂 AI 学情总结）
  伪代码 返回 {"class_rows": …, "class_weak_points": …, "class_weak_items": …, "class_count": …, "form": …}

公开 函数 学生页面 student chat_page? chat_kw? chat_start? chat_end? chat_kind? learner? current_role? auth_mode? subject?
  返回 学情页「载入」（地址 #学情?student=… 进来，动作 report_one）的页面状态：学生存在 {student, student_summary, student_points, student_wrong, student_recent, student_book, student_chat, student_chat_page, student_notes, student_relays, form}；没有这个学生（含不在本科目学生范围里）不报错，只回 {student:{username, missing, back}, form}
  报错 400 student 不能为空
  报错 400 日期要写成 YYYY-MM-DD
  报错 400 意图不对
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 student 为空，报错 400 student 不能为空
  伪代码 form = 调用 问老师表单 chat_kw=chat_kw chat_start=chat_start chat_end=chat_end chat_kind=chat_kind（下面没有这个学生的分支也一起返回）
  伪代码 调用 account.取账号 username=student，取不到或 role 不等于 student；或调用 学生范围 subject_id=subject_id 里没有 username 等于 student 的学生（包括登记在别的科目的学生）：返回 {"student": {"username": student, "missing": "没有这个学生（{student}），回全班表重新选。", "back": "#%E5%AD%A6%E6%83%85"}, "form": form}，不报错
  伪代码 调用 取学生学情 student=student subject=subject_id 得 g；调用 lesson.取当前系列 learner=student subject=subject_id 取 name；调用 progress.列最近作答 learner=student limit=20 subject=subject_id 得 recent；调用 dictation.取默写概况 learner=student subject=subject_id 得 dict
  伪代码 K182 内容日语替换：lang = 调用 account.取语言 username=learner 取 lang（查不到为空视为 zh）；ja 时 student_points/student_wrong/student_recent 各行的知识点 title、条目 name 调用 subject.译文（tbl=kg_point field=title / tbl=kg_item field=name，row_key=对应编号）、错题题干调 取题干 时带 lang={lang}，均非空才替换；取学生学情 本身不改（还要喂 AI 学情总结）
  伪代码 last：g.dialog_last_at、recent 第一条的 at、dict.last_at 三者里最晚的（空串不算），都没有写「还没有」
  伪代码 student 对象 = {username, head, overview, dictation, missing: "", back: "#%E5%AD%A6%E6%83%85"}：head=「{display_name}（{student}）　教材：{系列 name}　最近学习：{last}」（全角空格分隔）；overview 在 answer_total 为 0 时是「还没有作答」，否则「已掌握 {mastered_count} 个知识点　作答 {answer_total} 题　近期正确率 {recent_accuracy}%　平均得分 {avg_score}」；dictation 在 dict.total 为 0 时是「单词默写：还没有作答」，否则「单词默写：作答 {total} 次，正确率 {accuracy}%，错词本 {wrong_book_count} 个」
  伪代码 student_summary={"student": student, "head": has_summary 为 1 时「AI 学情总结（{summary_at}，{summary_author} 请的）」否则空串, "text": summary 或空串}
  伪代码 student_points：调用 progress.取状态 learner=student subject=subject_id，points 里 total 大于 0 或有得分的点（调用 progress.列得分 learner=student subject=subject_id 找得分）；每点 {label: title, tally: 「{right}/{total}」, score_text: 有得分行为得分数字，否则「—」, mastered_text: mastered 为 1 是「已掌握」否则空串}；分低的在前，没有得分的排最后，再按 code
  伪代码 student_wrong：调用 progress.取区间作答 learner=student start_id=0 subject=subject_id 得全部作答，按 question_no 分组，只留至少答错一次的；每题一行 {label: 取题干 的缩略（30 字），题干取不到用题号, point_label: 该题知识点 title（kg.取知识点 subject=subject_id，取不到用编号）, wrong_n: 答错次数, tally: 「{答对数}/{作答数}」, last_wrong: 最近一次答错的 at}；按 wrong_n 降序、last_wrong 降序，取前 10（口径微差：旧页按条目，v4 按题）
  伪代码 student_recent：recent 的 answers 每条 {at, point_label: 知识点 title（kg.取知识点 subject=subject_id，取不到用编号）, stem_brief: 取题干 的缩略（40 字），取不到空串, given_text: answer, result: correct 为 1 是「对」否则「错」}，顺序同 recent（新的在前）
  伪代码 student_book：g.wrong_book 每项 {label: kanji 与 kana 不同时「{kanji}【{kana}】{meaning}」，否则「{kana} {meaning}」, direction_label: direction 为 zh2jp 是「看中文写日语」否则「看汉字写读音」, last_wrong: last_at}
  伪代码 student_chat：调用 tutor.列问答轮 learner=student page=chat_page page_size=20 keyword=chat_kw date_from=chat_start date_to=chat_end intent=chat_kind subject=subject_id 得 ch；rounds 每轮 {chat_id: id, chat_at: at, chat_intent_label: 见下一行, chat_ask: ask 的缩略（120 字）, chat_reply: reply 的缩略（120 字）, chat_notes: reply_id 大于 0 时调用 teacher_rules.取回复用到 reply_id=reply_id subject=subject_id 取 text，否则空串}，顺序同 rounds（新的在前）（取回复用到 按 reply_id 和本科目关联：回复用到记录也带本科目 subject_id，不传 subject 会落到 1 号科目、非日语科目取不到）
  伪代码 每轮的 chat_intent_label：调用 意图标签 code=intent 取 label
  伪代码 student_chat_page={info, total, page, page_count, filtered, older, newer, clear}：info 按 lang 写，zh「共 {total} 条，第 {page}/{page_count} 页」，ja「全 {total} 件、{page}/{page_count} ページ」；filtered：chat_kw（先调 地址段 取 v 再判断，原因见 学生对话地址）、chat_start、chat_end、chat_kind 有一个不为空时 1，否则 0；older：page 小于 page_count 时调用 学生对话地址 student=student chat_page=page+1 chat_kw=chat_kw chat_start=chat_start chat_end=chat_end chat_kind=chat_kind，否则空串；newer：page 大于 1 时调用 学生对话地址 student=student chat_page=page-1 chat_kw=chat_kw chat_start=chat_start chat_end=chat_end chat_kind=chat_kind，否则空串；clear：filtered 为 1 时调用 学生对话地址 student=student，否则空串
  伪代码 student_notes=调用 teacher_rules.设定列表 student=student learner=learner current_role=current_role auth_mode=auth_mode subject=subject_id；student_relays=调用 teacher_rules.传达列表 student=student learner=learner current_role=current_role auth_mode=auth_mode subject=subject_id（带上登录信息，行上 note_subject_label/relay_subject_label 与 can_edit 才按当前登录的人算；学生页两张表的行原样透传）
  伪代码 返回上述十一个键

公开 函数 写学情总结页面 student current_user current_role? auth_mode? subject?
  返回 {student_summary}，形状同 学生页面 的 student_summary（刚写好的最新一份）
  报错 400 student 不能为空
  报错 400 current_user 不能为空
  报错 404 没有这个学生
  报错 400 老师暂时无法回答
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；current_role、auth_mode、subject 都可选（用户名取 current_user；路由层注入角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；auth_mode 等于 on 时只有该科目的负责/协作教师能写（否则 403 没有权限修改该科目）；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 写学情总结 student=student current_user=current_user subject=subject_id（权限已在上一步校验，这里只传已解析的科目；错误原样向上抛，不写库）
  伪代码 调用 取最近总结 student=student subject=subject_id，返回 {"student_summary": {"student": student, "head": 「AI 学情总结（{created_at}，{author} 请的）」, "text": summary}}

## 接口
GET /report/class -> 取全班学情 角色 teacher
GET /report/student -> 取学生学情 角色 teacher
POST /report/summary/write -> 写学情总结 角色 teacher
GET /report/summary -> 取最近总结 角色 teacher
POST /report/home -> 学情首页页面 动作 report_home 模板 页面状态 表单=form 角色 teacher
POST /report/one -> 学生页面 动作 report_one 模板 页面状态 表单=form 角色 teacher
POST /report/chat/search -> 问老师筛选 动作 report_chat_search 模板 提交跳转动态 消息=已按条件筛选 跳转={r.go} 角色 teacher
POST /report/chat/one -> 问老师全文页面 动作 report_chat_full 模板 页面状态 表单=form 角色 teacher
POST /report/summary -> 写学情总结页面 动作 report_summary 模板 页面状态消息 消息=学情总结写好了 角色 teacher

## 用例
用例 全班学情_正常
  先 数据 account_user username=t1 password_hash=x display_name=老师 role=teacher disabled=0 created_at=2025-12-01
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P2
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q2 correct=0 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P2 question_no=q3 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=50 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P2 score=0 at=2026-01-01
  先 数据 progress_answer learner=s2 point_code=P1 question_no=q1 correct=1 at=2026-01-01
  先 数据 progress_score learner=s2 point_code=P1 score=100 at=2026-01-01
  先 数据 progress_mastery learner=s2 point_code=P1 right_count=1 total_count=1 mastered=1 updated_at=2026-01-01
  调用 取全班学情
  得 total=2 weak_point_count=2 weak_item_count=2
  库 report_summary 共 0 行

用例 全班学情_按学生过滤
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=40 at=2026-01-01
  先 数据 progress_answer learner=s2 point_code=P1 question_no=q1 correct=1 at=2026-01-01
  先 数据 progress_score learner=s2 point_code=P1 score=100 at=2026-01-01
  调用 取全班学情 sort_by=avg_score student=s2
  得 total=1 weak_point_count=0 weak_item_count=0

用例 全班学情_没有学生
  调用 取全班学情
  得 total=0 weak_point_count=0 weak_item_count=0

用例 全班学情_排序方式不对
  调用 取全班学情 sort_by=bad
  报错 400

用例 学生学情_正常
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q2 correct=0 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P2 question_no=q3 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=50 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P2 score=0 at=2026-01-01
  先 数据 tutor_message learner=s1 role=user content=什么是敬语 intent=explain at=2026-01-01
  先 数据 teacher_rules_relay urgency=normal must_info=下周三小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=0 updated_at=2026-01-01
  调用 取学生学情 student=s1
  得 student=s1 display_name=小一 status=启用 answer_total=3 recent_accuracy=33 avg_score=25 mastered_count=0 wrong_count=2 wrong_book_count=0 weak_count=2 question_count=1 relay_count=1 has_summary=0

用例 学生学情_教师账号不算学生
  先 数据 account_user username=t1 password_hash=x display_name=老师 role=teacher disabled=0 created_at=2025-12-01
  调用 取学生学情 student=t1
  报错 404

用例 学生学情_没有这个人
  调用 取学生学情 student=nobody
  报错 404

用例 写学情总结_正常
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=0 at=2026-01-01
  调用 写学情总结 student=s1 current_user=t1
  得 ok=1 student=s1 author=t1
  库 report_summary 共 1 行
  库 report_summary 含 student=s1 author=t1
  库 tutor_message 共 0 行

用例 写学情总结_不是学生
  先 数据 account_user username=t1 password_hash=x display_name=老师 role=teacher disabled=0 created_at=2025-12-01
  调用 写学情总结 student=t1 current_user=t1
  报错 404
  库 report_summary 共 0 行

用例 取最近总结_取最新一份
  先 数据 report_summary student=s1 summary=第一份 author=t1 created_at=2026-01-01
  先 数据 report_summary student=s1 summary=第二份 author=t1 created_at=2026-01-01
  调用 取最近总结 student=s1
  得 has_summary=1 summary=第二份 author=t1

用例 取最近总结_还没有
  调用 取最近总结 student=s1
  得 has_summary=0 id=0

用例 学情首页页面_正常
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q2 correct=1 at=2026-01-01
  先 数据 progress_mastery learner=s1 point_code=P1 right_count=1 total_count=2 mastered=0 updated_at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=50 at=2026-01-01
  调用 学情首页页面 report_sort=平均得分
  得 class_count=共2个学生

用例 学情首页页面_平均得分没打过分的排最后
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s2 point_code=P1 question_no=q1 correct=1 at=2026-01-01
  先 数据 progress_score learner=s2 point_code=P1 score=90 at=2026-01-01
  调用 学情首页页面 report_sort=平均得分
  得 class_count=共2个学生

用例 学情首页页面_没有学生
  调用 学情首页页面
  得 class_count=共0个学生

用例 学生页面_正常
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q2 correct=1 at=2026-01-01
  先 数据 progress_mastery learner=s1 point_code=P1 right_count=1 total_count=2 mastered=0 updated_at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=50 at=2026-01-01
  先 数据 tutor_message learner=s1 role=user content=什么是敬语 intent=explain at=2026-01-01
  先 数据 teacher_rules_setting kind=memory content=多用中文 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay urgency=normal must_info=下周三小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 学生页面 student=s1
  得 有返回

用例 学生页面_没有这个学生不报错
  调用 学生页面 student=nobody
  得 有返回

用例 学生页面_教师账号不算学生
  先 数据 account_user username=t1 password_hash=x display_name=老师 role=teacher disabled=0 created_at=2025-12-01
  调用 学生页面 student=t1
  得 有返回

用例 学生页面_问老师分页
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 tutor_message learner=s1 role=user content=什么是敬语 intent=explain at=2026-01-01
  调用 学生页面 student=s1 chat_page=9 chat_kw=敬语
  得 有返回

用例 学生页面_问老师日期不对
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 学生页面 student=s1 chat_start=20260101
  报错 400

用例 问老师筛选_回到第一页
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 问老师筛选 student=s1 chat_q=敬语 chat_intent=讲解
  得 有返回

用例 问老师筛选_没有这个学生
  调用 问老师筛选 student=nobody
  报错 404

用例 问老师筛选_意图不对
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 问老师筛选 student=s1 chat_intent=乱写
  报错 400

用例 问老师筛选_日期不对
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 问老师筛选 student=s1 chat_from=2026/01/01
  报错 400

用例 问老师全文页面_正常
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 tutor_message learner=s1 role=user content=什么是敬语 intent=explain at=2026-01-01
  先 数据 tutor_message learner=s1 role=teacher content=敬语是表示尊敬的说法 intent=explain at=2026-01-01
  调用 问老师全文页面 student=s1 chat_id=1
  得 有返回
  库 tutor_message 共 2 行

用例 问老师全文页面_没有这条
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 问老师全文页面 student=s1 chat_id=99
  报错 404

用例 问老师全文页面_学生不在本科目
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 tutor_message learner=s1 role=user content=日语问题 intent=explain at=2026-01-01
  调用 问老师全文页面 student=s1 chat_id=1 subject=2
  报错 404

用例 写学情总结页面_正常
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  先 数据 progress_score learner=s1 point_code=P1 score=0 at=2026-01-01
  调用 写学情总结页面 student=s1 current_user=t1
  得 有返回
  库 report_summary 共 1 行
  库 report_summary 含 student=s1 author=t1

用例 写学情总结页面_不是学生
  先 数据 account_user username=t1 password_hash=x display_name=老师 role=teacher disabled=0 created_at=2025-12-01
  调用 写学情总结页面 student=t1 current_user=t1
  报错 404
  库 report_summary 共 0 行

用例 跨科目_全班学情只看登记的学生
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目甲 point_code=math.a subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=30 at=2026-01-01 subject_id=2
  调用 取全班学情 subject=2
  得 total=1 weak_point_count=1 weak_item_count=1

用例 跨科目_2号科目数据对1号不可见
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=30 at=2026-01-01 subject_id=2
  调用 取全班学情
  得 total=2 weak_point_count=0 weak_item_count=0

用例 跨科目_全班学情没有登记学生
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  调用 取全班学情 subject=2
  得 total=0

用例 跨科目_取学生学情本科目数据
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=30 at=2026-01-01 subject_id=2
  先 数据 tutor_message learner=s1 role=user content=日语问题 intent=explain at=2026-01-01
  先 数据 tutor_message learner=s1 role=user content=数学问题 intent=explain at=2026-01-01 subject_id=2
  调用 取学生学情 student=s1 subject=2
  得 student=s1 answer_total=1 wrong_count=1 weak_count=1 question_count=1

用例 跨科目_取学生学情没登记当不存在
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=3 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 取学生学情 student=s1 subject=2
  报错 404

用例 跨科目_取学生学情日语不受影响
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  调用 取学生学情 student=s1
  得 student=s1 answer_total=1 wrong_count=0

用例 跨科目_写学情总结落当前科目
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=0 at=2026-01-01 subject_id=2
  调用 写学情总结 student=s1 current_user=t1 subject=2
  得 ok=1 student=s1 author=t1
  库 report_summary 共 1 行
  库 report_summary 含 student=s1 author=t1 subject_id=2

用例 跨科目_写学情总结没登记的学生404
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  调用 写学情总结 student=s1 current_user=t1 subject=2
  报错 404
  库 report_summary 共 0 行

用例 跨科目_取最近总结只看本科目
  先 数据 report_summary student=s1 summary=日语的 author=t1 created_at=2026-01-01
  先 数据 report_summary student=s1 summary=数学的 author=t1 created_at=2026-01-02 subject_id=2
  调用 取最近总结 student=s1 subject=2
  得 has_summary=1 summary=数学的

用例 跨科目_取最近总结别的科目当没有
  先 数据 report_summary student=s1 summary=日语的 author=t1 created_at=2026-01-01
  调用 取最近总结 student=s1 subject=2
  得 has_summary=0 id=0

用例 跨科目_取最近总结不传科目是日语
  先 数据 report_summary student=s1 summary=日语的 author=t1 created_at=2026-01-01
  先 数据 report_summary student=s1 summary=数学的 author=t1 created_at=2026-01-02 subject_id=2
  调用 取最近总结 student=s1
  得 has_summary=1 summary=日语的

用例 跨科目_学情首页页面只看登记的学生
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=30 at=2026-01-01 subject_id=2
  调用 学情首页页面 subject=2
  得 class_count=共1个学生

用例 跨科目_学生页面没登记的学生不报错
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  调用 学生页面 student=s1 subject=2
  得 有返回
  得 student_points=空 student_wrong=空

用例 跨科目_学生页面本科目
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  先 数据 progress_score learner=s1 point_code=math.a score=30 at=2026-01-01 subject_id=2
  调用 学生页面 student=s1 subject=2
  得 有返回

用例 跨科目_写学情总结页面落当前科目
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  调用 写学情总结页面 student=s1 current_user=t1 subject=2
  得 有返回
  库 report_summary 共 1 行
  库 report_summary 含 student=s1 author=t1 subject_id=2

用例 跨科目_登录模式私有科目非负责教师被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 取全班学情 learner=t9 current_role=teacher auth_mode=on subject=2
  报错 403

用例 跨科目_登录模式负责教师可看
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 取全班学情 learner=t1 current_role=teacher auth_mode=on subject=2
  得 total=0

用例 跨科目_登录模式学生未分配被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 取学生学情 student=s1 learner=s1 current_role=student auth_mode=on subject=2
  报错 403

用例 跨科目_科目不存在
  调用 取全班学情 learner=t1 current_role=teacher auth_mode=on subject=9
  报错 404

用例 跨科目_科目不是数字
  调用 取全班学情 subject=abc
  报错 400

用例 日语科目_学生范围只看登记的学生
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 取全班学情
  得 total=1

用例 日语科目_撤销的学生不显示
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=revoked created_at=2026-01-01
  调用 取全班学情
  得 total=1

用例 日语科目_没登记的学生取学情当不存在
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  调用 取学生学情 student=s1
  报错 404

用例 日语科目_学生页面没登记不报错
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  调用 学生页面 student=s1
  得 有返回
  得 student_points=空 student_wrong=空

用例 跨科目_2号科目撤销的学生不显示
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s2 assigned_by=t1 status=revoked created_at=2026-01-01
  调用 取全班学情 subject=2
  得 total=1

用例 写学情总结_登录模式公共科目非负责教师被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 写学情总结 student=s1 current_user=t9 current_role=teacher auth_mode=on subject=2
  报错 403
  库 report_summary 共 0 行

用例 写学情总结_登录模式学生被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 写学情总结 student=s1 current_user=s1 current_role=student auth_mode=on subject=1
  报错 403
  库 report_summary 共 0 行

用例 写学情总结_登录模式协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=s1 point_code=math.a question_no=math.q1 correct=0 at=2026-01-01 subject_id=2
  调用 写学情总结 student=s1 current_user=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 author=t2
  库 report_summary 含 student=s1 author=t2 subject_id=2

用例 写学情总结页面_登录模式公共科目非负责教师被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 写学情总结页面 student=s1 current_user=t9 current_role=teacher auth_mode=on subject=2
  报错 403
  库 report_summary 共 0 行

用例 写学情总结_单人模式不校验写权限
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=0 at=2026-01-01
  调用 写学情总结 student=s1 current_user=t1 subject=1
  得 ok=1
  库 report_summary 共 1 行
