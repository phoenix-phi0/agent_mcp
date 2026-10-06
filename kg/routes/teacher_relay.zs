# AI 老师设定的第四种「传达」（教师端）：老师要 AI 老师让学生知道的事。表在
# entities/teacher_relay.entity，拼进提示词在 scripts/teacher_notes.zs，判定在
# scripts/relay_judge.zs（问老师回答成功后后台跑）。
#
# 跟记忆 / 作者注 / 关键词卡（routes/teacher_note.zs）的区别：那三种暗中影响 AI 老师、
# 不让学生知道；传达是要学生知道的——学生会在 AI 的回复里看到传达的内容。但设定
# 本身（要点、状态、判定）学生看不到：下面的接口全部「只许 教师」。
#
# 字段：要点（老师的意图，不是台词）、范围（全班 / 某个学生，全班的按学生各自跟踪）、
# 紧急程度（顺便 / 尽快 / 立即）、口吻（以老师名义 / AI自己的口吻）、必须准确的信息、
# 话题关键词（「顺便」时提示什么算沾边）、轮数阈值（默认 3：判了这么多次没传达到
# 就升级为立即）、截止日期（当天升级为立即，过了还没传达到就是已过期、不再带入）。
#
# 界面两处，同 teacher_note：
#   ui/teacher_note.ui  「AI老师设定」页：全班的传达列表（完成情况「已传达 x/总 y」）、
#                       各学生的状态表（点开传达到的那条问老师记录）
#   ui/report.ui        学情里一个学生的页面：这个学生的和全班的放在一起（全班的只读），
#                       状态是这个学生的
# 地址里有 student（学生页）就是管这个学生的，没有就是全班的。参数叫 student 不叫
# learner（learner 多人模式下被引擎盖成登录的教师自己）。
#
# 改了要点或必须准确的信息：这条在各学生上的状态清掉，重新传达（relay_reset）；
# 只改紧急程度、口吻、轮数、截止日不清。


# 编辑传达浮层的「载入」：带着地址进来时把一条拉回表单。行上点「编辑」时整行已经
# 拷进表单，不调这个。点「新增传达」「给这个学生加一条传达」：回一张带默认值的空表单
接口 POST /teacher_relay/open 动作 teacher_relay_open 只许 教师
  用包 common db http

  设 one.relay_id = {relay_id 或}
  设 one.student = {student 或}
  如果 {one.relay_id} 为空
    设 blank.student = {one.student}
    设 blank.relay_point =
    设 blank.relay_urgency = 尽快
    设 blank.relay_voice = 以老师名义
    设 blank.relay_facts =
    设 blank.relay_keywords =
    设 blank.relay_rounds = 3
    设 blank.relay_due =
    响应 form {blank}
  否则
    设 record = 查一行表 app.db relay_one {one}
    如果 {record.relay_id 或} 为空
      返回 {"error":"没有这条传达（全班的传达要到「AI老师设定」页改）"} 404
    结束
    设 record.student = {one.student}
    响应 form {record}
  结束
结束


# 新增 / 修改：relay_id 空是新增（建好就是启用的），不空是修改（启用状态不变）。
# 先查，再写；回最新的列表
接口 POST /teacher_relay/save 动作 teacher_relay_save 只许 教师
  用包 common db http

  设 edit.relay_id = {relay_id 或}
  设 edit.student = {student 或}
  设 edit.relay_point = {relay_point 或}
  设 edit.relay_urgency = {relay_urgency 或 尽快}
  设 edit.relay_voice = {relay_voice 或 以老师名义}
  设 edit.relay_facts = {relay_facts 或}
  设 edit.relay_keywords = {relay_keywords 或}
  设 edit.relay_rounds = {relay_rounds 或 3}
  设 edit.relay_due = {relay_due 或}
  设 edit.relay_by = {current_user 或 老师}

  如果 {edit.student} 不为空
    设 head = 查一行表 app.db report_student {edit}
    如果 {head.found} 等于 0
      返回 {"error":"没有这个学生（{edit.student}），回学情的全班表重新选。"} 400
    结束
  结束
  如果 {edit.relay_id} 不为空
    设 current = 查一行表 app.db relay_row {edit}
    如果 {current.relay_id 或} 为空
      返回 {"error":"没有这条传达（全班的传达要到「AI老师设定」页改）"} 404
    结束
  结束

  设 problem = 查一值表 app.db relay_check {edit}
  如果 {problem} 不为空
    返回 {"error":"{problem}"} 400
  结束

  事务 app.db
    如果 {edit.relay_id} 为空
      设 affected = 写库表 app.db relay_insert {edit}
    否则
      设 affected = 写库表 app.db relay_reset {edit}
      设 affected = 写库表 app.db relay_update {edit}
    结束
  结束

  如果 {edit.student} 为空
    设 rows = 查询 app.db relay_list_class
    设 states = 查询 app.db relay_class_states
    设 group.class_relays = {rows}
    设 group.class_relay_states = {states}
  否则
    设 rows = 查询表 app.db relay_list_student {edit}
    设 group.student_relays = {rows}
  结束
  响应 lists {group}
  消息 系统 传达已保存 ok
结束


# 行上的停用 / 启用 / 删除（带 relay_id）
接口 POST /teacher_relay/disable 动作 teacher_relay_disable 只许 教师
  用包 common db http

  设 change.relay_id = {relay_id 或 0}
  设 change.student = {student 或}
  设 change.enabled = 0
  设 change.relay_by = {current_user 或 老师}
  设 affected = 写库表 app.db relay_toggle {change}
  如果 {affected} 等于 0
    返回 {"error":"没有这条传达（全班的传达要到「AI老师设定」页改）"} 404
  结束
  如果 {change.student} 为空
    设 rows = 查询 app.db relay_list_class
    设 states = 查询 app.db relay_class_states
    设 group.class_relays = {rows}
    设 group.class_relay_states = {states}
  否则
    设 rows = 查询表 app.db relay_list_student {change}
    设 group.student_relays = {rows}
  结束
  响应 lists {group}
  消息 系统 传达已停用 ok
结束


接口 POST /teacher_relay/enable 动作 teacher_relay_enable 只许 教师
  用包 common db http

  设 change.relay_id = {relay_id 或 0}
  设 change.student = {student 或}
  设 change.enabled = 1
  设 change.relay_by = {current_user 或 老师}
  设 affected = 写库表 app.db relay_toggle {change}
  如果 {affected} 等于 0
    返回 {"error":"没有这条传达（全班的传达要到「AI老师设定」页改）"} 404
  结束
  如果 {change.student} 为空
    设 rows = 查询 app.db relay_list_class
    设 states = 查询 app.db relay_class_states
    设 group.class_relays = {rows}
    设 group.class_relay_states = {states}
  否则
    设 rows = 查询表 app.db relay_list_student {change}
    设 group.student_relays = {rows}
  结束
  响应 lists {group}
  消息 系统 传达已启用 ok
结束


接口 POST /teacher_relay/delete 动作 teacher_relay_delete 只许 教师
  用包 common db http

  设 change.relay_id = {relay_id 或 0}
  设 change.student = {student 或}
  事务 app.db
    设 affected = 写库表 app.db relay_delete {change}
    设 cleared = 写库表 app.db relay_state_clear {change}
  结束
  如果 {affected} 等于 0
    返回 {"error":"没有这条传达（全班的传达要到「AI老师设定」页改）"} 404
  结束
  如果 {change.student} 为空
    设 rows = 查询 app.db relay_list_class
    设 states = 查询 app.db relay_class_states
    设 group.class_relays = {rows}
    设 group.class_relay_states = {states}
  否则
    设 rows = 查询表 app.db relay_list_student {change}
    设 group.student_relays = {rows}
  结束
  响应 lists {group}
  消息 系统 传达已删除 ok
结束


# 「打开」传达到的那条问老师记录（浮层的「载入」）：学生那句、老师回复全文、摘录。
# 从列表上点时整行已经拷进表单、不调这个；带着地址进来（刷新、转发的链接）时调
接口 POST /teacher_relay/message 动作 teacher_relay_message 只许 教师
  用包 common db http

  设 one.message_id = {message_id 或 0}
  设 record = 查一行表 app.db relay_message {one}
  如果 {record.message_id 或} 为空
    返回 {"error":"没有这条问老师记录"} 404
  结束
  响应 form {record}
结束
