# AI 老师设定（教师端）：教师往「问老师」的 AI 老师提示词里加的指示，仿 AI Dungeon
# 的 Memory / Author's Note / World Info。表在 entities/teacher_note.entity，拼法在
# scripts/teacher_notes.zs，问老师那边在 routes/teacher.zs 调它。
#
#   记忆      常驻：每次都接在系统提示词末尾
#   作者注    强引导：紧贴「学生现在说」之前（发给模型的最后一段材料）。可以勾
#             「只用于下一条回复」：这个学生下一条回复成功生成后就不再带（按学生
#             各算一次；生成失败不算用掉）
#   关键词卡  学生最近几句（含这一句）出现任一关键词才带上，放在「最近的对话」之前
#
# 每条是「全班」或「某个学生」的（note_student 空 = 全班）。同类的全班和个人都生效，
# 个人的排在后面。界面两处：
#   ui/teacher_note.ui  「AI老师设定」页：全班的列表、新增 / 编辑（浮层）/ 停用 /
#                       删除，和预览（选学生、输一句，看拼进提示词的部分，不调模型）
#   ui/report.ui        学情里一个学生的页面（#学情?student=xx）：这个学生的和全班的
#                       放在一起（全班的只读），管这个学生个人的
# 两处共用下面的接口：地址里有 student（学生页）就是管这个学生的，没有就是全班的。
# 参数叫 student 不叫 learner（learner 多人模式下被引擎盖成登录的教师自己）。
#
# 全部「只许 教师」：多人模式下学生调了 403「需要教师权限」；单人模式不查角色，
# 教师端（/teacher）照常能用，学生端（/）上没有这些界面。学生的接口（问老师的
# /teacher/state、/teacher/send）也不回这些内容——设定只进发给模型的提示词。
#
# 长度上限在保存时查（queries/teacher_note_check.sql）：每条 400 字、关键词 100 字，
# 启用的同类合计（全班的加上同一个学生个人的）记忆 1200、作者注 600、关键词卡
# 3000 字，超了 400 一句人话，不存。


# 「AI老师设定」页进页面：全班的设定、全班的传达和各学生的传达状态、预览的学生下拉
接口 POST /teacher_note/home 动作 teacher_note_home 只许 教师
  用包 common db http

  设 scope.student =
  设 rows = 查询表 app.db teacher_note_list {scope}
  设 students = 查询 app.db teacher_note_students
  设 group.class_notes = {rows}
  设 group.note_students = {students}
  # 第四种「传达」（routes/teacher_relay.zs）：全班的传达和各学生的状态
  设 relays = 查询 app.db relay_list_class
  设 relay_states = 查询 app.db relay_class_states
  设 group.class_relays = {relays}
  设 group.class_relay_states = {relay_states}
  响应 lists {group}
结束


# 编辑浮层的「载入」：带着地址进来（刷新、别人发来的链接）时把一条拉回表单，只拉
# 这一页能改的。行上点「编辑」时整行已经拷进表单，不调这个。学情的学生页上点
# 「给这个学生加一条」，地址里只有 student：回一张空表单
接口 POST /teacher_note/open 动作 teacher_note_open 只许 教师
  用包 common db http

  设 one.note_id = {note_id 或}
  设 one.student = {student 或}
  如果 {one.note_id} 为空
    设 blank.student = {one.student}
    设 blank.note_kind =
    设 blank.note_keywords =
    设 blank.note_content =
    设 blank.note_once = false
    响应 form {blank}
  否则
    设 record = 查一行表 app.db teacher_note_one {one}
    如果 {record.note_id 或} 为空
      返回 {"error":"没有这条设定（全班的设定要到「AI老师设定」页改）"} 404
    结束
    设 record.student = {one.student}
    响应 form {record}
  结束
结束


# 新增 / 修改：note_id 空是新增（建好就是启用的），不空是修改（启用状态不变）。
# 先查上限，再写；回最新的列表（设定页的 class_notes，学生页的 student_notes）
接口 POST /teacher_note/save 动作 teacher_note_save 只许 教师
  用包 common db http

  设 edit.note_id = {note_id 或}
  设 edit.note_kind = {note_kind 或 记忆}
  设 edit.student = {student 或}
  设 edit.note_keywords = {note_keywords 或}
  设 edit.note_content = {note_content 或}
  设 edit.note_once = {note_once 或 0}
  设 edit.note_by = {current_user 或 老师}
  设 edit.note_enabled = 1

  如果 {edit.student} 不为空
    设 head = 查一行表 app.db report_student {edit}
    如果 {head.found} 等于 0
      返回 {"error":"没有这个学生（{edit.student}），回学情的全班表重新选。"} 400
    结束
  结束
  如果 {edit.note_id} 不为空
    设 current = 查一行表 app.db teacher_note_row {edit}
    如果 {current.note_id 或} 为空
      返回 {"error":"没有这条设定（全班的设定要到「AI老师设定」页改）"} 404
    结束
    设 edit.note_enabled = {current.note_enabled}
  结束

  设 problem = 查一值表 app.db teacher_note_check {edit}
  如果 {problem} 不为空
    返回 {"error":"{problem}"} 400
  结束

  事务 app.db
    如果 {edit.note_id} 为空
      设 affected = 写库表 app.db teacher_note_insert {edit}
    否则
      设 affected = 写库表 app.db teacher_note_update {edit}
    结束
  结束

  设 rows = 查询表 app.db teacher_note_list {edit}
  如果 {edit.student} 为空
    设 group.class_notes = {rows}
  否则
    设 group.student_notes = {rows}
  结束
  响应 lists {group}
  消息 系统 设定已保存 ok
结束


# 行上的停用 / 启用（带 note_id）。启用前按上限再查一遍
接口 POST /teacher_note/disable 动作 teacher_note_disable 只许 教师
  用包 common db http

  设 change.note_id = {note_id 或 0}
  设 change.student = {student 或}
  设 change.enabled = 0
  设 change.note_by = {current_user 或 老师}
  设 affected = 写库表 app.db teacher_note_toggle {change}
  如果 {affected} 等于 0
    返回 {"error":"没有这条设定（全班的设定要到「AI老师设定」页改）"} 404
  结束
  设 rows = 查询表 app.db teacher_note_list {change}
  如果 {change.student} 为空
    设 group.class_notes = {rows}
  否则
    设 group.student_notes = {rows}
  结束
  响应 lists {group}
  消息 系统 已停用 ok
结束


接口 POST /teacher_note/enable 动作 teacher_note_enable 只许 教师
  用包 common db http

  设 change.note_id = {note_id 或 0}
  设 change.student = {student 或}
  设 change.enabled = 1
  设 change.note_by = {current_user 或 老师}
  设 current = 查一行表 app.db teacher_note_row {change}
  如果 {current.note_id 或} 为空
    返回 {"error":"没有这条设定（全班的设定要到「AI老师设定」页改）"} 404
  结束
  设 check.note_id = {current.note_id}
  设 check.note_kind = {current.note_kind}
  设 check.student = {change.student}
  设 check.note_keywords = {current.note_keywords}
  设 check.note_content = {current.note_content}
  设 check.note_enabled = 1
  设 problem = 查一值表 app.db teacher_note_check {check}
  如果 {problem} 不为空
    返回 {"error":"{problem}"} 400
  结束
  设 affected = 写库表 app.db teacher_note_toggle {change}
  设 rows = 查询表 app.db teacher_note_list {change}
  如果 {change.student} 为空
    设 group.class_notes = {rows}
  否则
    设 group.student_notes = {rows}
  结束
  响应 lists {group}
  消息 系统 已启用 ok
结束


接口 POST /teacher_note/delete 动作 teacher_note_delete 只许 教师
  用包 common db http

  设 change.note_id = {note_id 或 0}
  设 change.student = {student 或}
  设 affected = 写库表 app.db teacher_note_delete {change}
  如果 {affected} 等于 0
    返回 {"error":"没有这条设定（全班的设定要到「AI老师设定」页改）"} 404
  结束
  设 rows = 查询表 app.db teacher_note_list {change}
  如果 {change.student} 为空
    设 group.class_notes = {rows}
  否则
    设 group.student_notes = {rows}
  结束
  响应 lists {group}
  消息 系统 已删除 ok
结束


# 预览：选一个学生、输一句示例提问，看这句会命中哪些关键词卡、拼进提示词的教师
# 设定是什么样。跟问老师调的是同一个 scripts/teacher_notes.zs（用这个学生真实的
# 最近几句判关键词），不调模型、不写库，「只用于下一条」也不会被用掉。
#
# state.preview：system / cards / relay / tail 四段原文，ids，relay_pick（这次带哪条
# 传达、用的紧急程度、后面还排着几条），layout（各段放在提示词里的位置，其余材料
# 用「……」代替）；lists.preview_hits：命中的关键词卡。传达的预览同样不写库：不算
# 带入、不判定
接口 POST /teacher_note/preview 动作 teacher_note_preview 只许 教师
  用包 common db http

  设 pick = {preview_student 或}
  设 sample = {preview_message 或}
  如果 {pick} 为空
    返回 {"error":"先选一个学生"} 400
  结束
  如果 {sample} 为空
    返回 {"error":"输一句示例提问"} 400
  结束

  设 notes = 执行 scripts/teacher_notes.zs learner={pick} message={sample}
  设 nl = 查一值 app.db text_newline
  设 preview.student = {pick}
  设 preview.system = {notes.system 或 （没有生效的设定，系统提示词不加东西）}
  设 preview.cards = {notes.cards 或 （没有命中的关键词卡）}
  设 preview.tail = {notes.tail 或 （没有生效的作者注）}
  设 preview.ids = {notes.ids 或 （无）}
  设 preview.relay = {notes.relay 或 （没有待传达的要点）}
  设 preview.relay_pick = （没有待传达的要点）
  如果 {notes.relay_id} 不为空
    设 preview.relay_pick = 传达#{notes.relay_id}「{notes.relay_brief}」，这次按「{notes.relay_urgency}」带；后面还排着{notes.relay_queue}条（一条回复只带一条）
  结束
  设 preview.layout = 【系统提示词】你是一位耐心的日语老师……你不要自己写网址。{notes.system}{nl}{nl}【发给模型的提示词】学生现在用的教材：【……】课文、进度等材料：【……】{notes.cards}最近的对话（旧的在前）：【……】{notes.relay}{notes.tail}学生现在说：【{sample}】请直接回答学生现在这句话。
  设 state.preview = {preview}
  响应 state {state}
  设 group.preview_hits = {notes.hits}
  响应 lists {group}
结束
