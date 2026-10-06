# 学情（教师端首页，ui/report.ui）：全班表、全班薄弱点、点进一个学生看细节、
# 请 AI 写学情总结。
#
# 全部「只许 教师」：多人模式下学生 403「需要教师权限」；单人模式不查角色，页面
# 在「管理」那组里照常能开（全班就是库里有学习记录的学习者，比如 me）。
#
# 查询全在 queries/report_*.sql，只读——按学生（参数 student）过滤，不改任何
# 学习数据。参数叫 student 不叫 learner：learner 是引擎注入的「这个请求是谁的
# 数据」（多人模式下就是教师自己），请求体里的 learner 会被盖掉。
#
# AI 学情总结存在 learner_report（entities/report.entity），不进 chat_message：
# 那是学生自己的问老师记录，学生看得到；这份是写给教师的。存下来下次打开这个
# 学生还看得到上一份（带时间），不用每次都调模型。


# 进页面、改排序：全班表 + 全班薄弱点（知识点、条目各前 10）
接口 POST /report/home 动作 report_home 只许 教师
  用包 common db http data

  设 query.sort = {report_sort 或 最近学习}
  设 class_rows = 查询表 app.db report_class {query}
  设 weak_points = 查询 app.db report_weak_points
  设 weak_items = 查询 app.db report_weak_items
  设 group.class_rows = {class_rows}
  设 group.class_weak_points = {weak_points}
  设 group.class_weak_items = {weak_items}
  响应 lists {group}
  设 count = 条数 {class_rows}
  设 state.class_count = 共{count}个学生
  响应 state {state}
  设 form_back.report_sort = {query.sort}
  响应 form {form_back}
结束


# 点进一个学生（#学情?student=s1，界面上的「载入」）：抬头、概况、各知识点、
# 常错条目、最近作答、默写错词本、问老师记录（老师的回答带着当时用了的 AI 老师
# 设定）、上一份 AI 总结、AI 老师设定（这个学生的和全班的）。
#
# 不是学生（教师账号、库里没这个人）：回 state.student.missing 那句，页面上
# 直接显示，不报错。
接口 POST /report/one 动作 report_one 只许 教师
  用包 common db http data

  设 who.student = {student 或}
  如果 {who.student} 为空
    返回 {"error":"缺 student（看哪个学生）"} 400
  结束
  设 head = 查一行表 app.db report_student {who}
  如果 {head.found} 等于 0
    设 missing.username = {who.student}
    设 missing.missing = 没有这个学生（{who.student}），回全班表重新选。
    设 missing.back = {head.back}
    设 state.student = {missing}
    响应 state {state}
  否则
    设 head.missing =
    设 brief.learner = {who.student}
    设 overview = 查一行表 app.db progress_overview {brief}
    设 dictation = 查一行表 app.db dictation_stats {brief}
    设 head.overview = {overview.head}　{overview.answers_text}　{overview.rate_text}　{overview.score_text}
    设 head.dictation = 单词默写：{dictation.text}
    设 last = 查一行表 app.db report_summary_last {who}
    设 summary.text = {last.text 或}
    设 summary.head = {last.head 或}
    设 summary.student = {who.student}
    设 state.student = {head}
    设 state.student_summary = {summary}
    响应 state {state}

    设 points = 查询表 app.db report_points {who}
    设 wrong = 查询表 app.db report_wrong_items {who}
    设 recent = 查询表 app.db report_recent {who}
    设 book = 查询表 app.db report_book {who}
    设 chat_rows = 查询表 app.db report_chat {who}
    # 这个学生的 AI 老师设定，和全班的放在一起（全班的只读），见 routes/teacher_note.zs
    设 note_rows = 查询表 app.db teacher_note_list {who}
    # 传达（routes/teacher_relay.zs）：这个学生的和全班的，状态是这个学生的
    设 relay_rows = 查询表 app.db relay_list_student {who}
    设 group.student_points = {points}
    设 group.student_wrong = {wrong}
    设 group.student_recent = {recent}
    设 group.student_book = {book}
    设 group.student_chat = {chat_rows}
    设 group.student_notes = {note_rows}
    设 group.student_relays = {relay_rows}
    响应 lists {group}
  结束
结束


# 请 AI 写学情总结：平衡档，材料是这个学生的进度摘要（progress_brief，问老师
# 用的同一份）、常错条目、最近作答、默写、问过老师什么（report_ai_extra）。
# 存进 learner_report，回 state.student_summary。十几秒，页面上有等待提示。
#
# 模型没回话：502 一句人话；模型调用本身出错（超时、额度）由引擎翻译成可读的
# 报错（tools/dsl_http.py 的 _model_failure）。都不写库。
接口 POST /report/summary 动作 report_summary 只许 教师
  用包 common db http data

  设 who.student = {student 或}
  如果 {who.student} 为空
    返回 {"error":"缺 student（给哪个学生写总结）"} 400
  结束
  设 head = 查一行表 app.db report_student {who}
  如果 {head.found} 等于 0
    返回 {"error":"没有这个学生"} 404
  结束

  设 brief.learner = {who.student}
  设 brief.line = 80
  设 brief.keep = 60
  设 brief.level =
  设 progress = 查一值表 app.db progress_brief {brief}
  设 extra = 查一行表 app.db report_ai_extra {who}

  系统 你是一位有经验的日语教研老师，帮任课老师看学生的学习数据、写学情总结。读者是老师，不是学生：用第三人称写这个学生，用中文。只依据给你的数据（网站统计的，以它为准），不要编造没给的数字、知识点或经历；数据很少就直说数据不够、只能看出什么。不要客套，不要出题。

  问 summary_text = 学生：{head.label}（{who.student}），用的教材：{head.series_label}，最近学习：{head.last_active}。【学习进度】{progress}【常错的条目】{extra.wrong_text}【最近作答（新的在前）】{extra.recent_text}【单词默写】{extra.dict_text}【最近问老师的问题】{extra.ask_text}请写一段给老师看的学情总结：先一句话总评（学习量、整体掌握情况）；再说薄弱点（得分低的知识点、反复错的条目，结合最近作答说可能错在哪）；再说学习习惯上看得出的情况（有没有在默写、问老师问的是什么）；最后给老师两三条具体建议（先让他复习什么、练什么、课上提醒什么）。全文 400 字以内。 用 平衡
  如果 {summary_text} 为空
    返回 {"error":"AI 这次没有写出总结，过一会儿再试。"} 502
  结束

  设 rec.student = {who.student}
  设 rec.summary_text = {summary_text}
  设 rec.written_by = {current_user}
  设 affected = 写库表 app.db report_summary_add {rec}
  设 last = 查一行表 app.db report_summary_last {who}
  设 summary.text = {last.text 或}
  设 summary.head = {last.head 或}
  设 summary.student = {who.student}
  设 state.student_summary = {summary}
  响应 state {state}
  消息 系统 学情总结写好了 ok
结束
