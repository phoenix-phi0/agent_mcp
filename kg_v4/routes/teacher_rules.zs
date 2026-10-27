接口 GET /teacher_rules/settings 角色 teacher
  设 r = 调用 teacher_rules.列设定 kind={kind 或} student={student 或} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /teacher_rules/setting 角色 teacher
  设 r = 调用 teacher_rules.取设定 setting_id={setting_id} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_rules/setting/save 角色 teacher
  设 r = 调用 teacher_rules.保存设定 kind={kind} content={content} current_user={current_user} setting_id={setting_id 或} student={student 或} keywords={keywords 或} once={once 或} scope={scope 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_rules/setting/enable 角色 teacher
  设 r = 调用 teacher_rules.设置设定启用 setting_id={setting_id} enabled={enabled} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 DELETE /teacher_rules/setting/delete 角色 teacher
  设 r = 调用 teacher_rules.删除设定 setting_id={setting_id} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /teacher_rules/prompt 角色 teacher
  设 r = 调用 teacher_rules.取生效设定 student={student} recent_text={recent_text 或} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /teacher_rules/relays 角色 teacher
  设 r = 调用 teacher_rules.列传达 learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /teacher_rules/relay 角色 teacher
  设 r = 调用 teacher_rules.取传达 relay_id={relay_id} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_rules/relay/save 角色 teacher
  设 r = 调用 teacher_rules.保存传达 urgency={urgency} must_info={must_info} rounds={rounds} current_user={current_user} relay_id={relay_id 或} tone={tone 或} deadline={deadline 或} student={student 或} facts={facts 或} keywords={keywords 或} scope={scope 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_rules/relay/enable 角色 teacher
  设 r = 调用 teacher_rules.设置传达启用 relay_id={relay_id} enabled={enabled} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 DELETE /teacher_rules/relay/delete 角色 teacher
  设 r = 调用 teacher_rules.删除传达 relay_id={relay_id} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_rules/relay/send 角色 teacher
  设 r = 调用 teacher_rules.对学生发传达 relay_id={relay_id} student={student} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /teacher_rules/relay/states 角色 teacher
  设 r = 调用 teacher_rules.列传达状态 student={student 或} learner={current_user 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_rules/note/home 动作 teacher_note_home 角色 teacher
  设 r = 调用 teacher_rules.设定首页页面 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_rules/note/open 动作 teacher_note_open 角色 teacher
  设 r = 调用 teacher_rules.载入设定页面 note_id={note_id 或} student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 form {r}
结束

接口 POST /teacher_rules/note/save 动作 teacher_note_save 角色 teacher
  设 r = 调用 teacher_rules.保存设定页面 note_content={note_content} current_user={current_user} note_kind={note_kind 或} note_id={note_id 或} student={student 或} note_keywords={note_keywords 或} note_once={note_once 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 设定已保存
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/note/disable 动作 teacher_note_disable 角色 teacher
  设 r = 调用 teacher_rules.设置设定启用页面 note_id={note_id} enabled=0 student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 已停用
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/note/enable 动作 teacher_note_enable 角色 teacher
  设 r = 调用 teacher_rules.设置设定启用页面 note_id={note_id} enabled=1 student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 已启用
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/note/delete 动作 teacher_note_delete 角色 teacher
  设 r = 调用 teacher_rules.删除设定页面 note_id={note_id} student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 已删除
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/note/preview 动作 teacher_note_preview 角色 teacher
  设 r = 调用 teacher_rules.设定预览页面 preview_student={preview_student} preview_message={preview_message} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_rules/relay/open 动作 teacher_relay_open 角色 teacher
  设 r = 调用 teacher_rules.载入传达页面 relay_id={relay_id 或} student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 form {r}
结束

接口 POST /teacher_rules/relay/page-save 动作 teacher_relay_save 角色 teacher
  设 r = 调用 teacher_rules.保存传达页面 relay_point={relay_point} current_user={current_user} relay_id={relay_id 或} student={student 或} relay_urgency={relay_urgency 或} relay_voice={relay_voice 或} relay_facts={relay_facts 或} relay_keywords={relay_keywords 或} relay_rounds={relay_rounds 或} relay_due={relay_due 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 传达已保存
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/relay/page-disable 动作 teacher_relay_disable 角色 teacher
  设 r = 调用 teacher_rules.设置传达启用页面 relay_id={relay_id} enabled=0 student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 传达已停用
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/relay/page-enable 动作 teacher_relay_enable 角色 teacher
  设 r = 调用 teacher_rules.设置传达启用页面 relay_id={relay_id} enabled=1 student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 传达已启用
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/relay/page-delete 动作 teacher_relay_delete 角色 teacher
  设 r = 调用 teacher_rules.删除传达页面 relay_id={relay_id} student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 传达已删除
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /teacher_rules/relay/message 动作 teacher_relay_message 角色 teacher
  设 r = 调用 teacher_rules.传达记录页面 message_id={message_id} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 form {r}
结束
