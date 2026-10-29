接口 POST /teacher_assist/ask 动作 assist_send 角色 teacher
  设 r = 调用 teacher_assist.问助手页面 current_user={current_user} message={content} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r.page}
结束

接口 POST /teacher_assist/history 动作 assist_state 角色 teacher
  设 r = 调用 teacher_assist.列对话页面 current_user={current_user} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 GET /teacher_assist/messages 角色 teacher
  设 r = 调用 teacher_assist.列对话 current_user={current_user} limit={limit 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /teacher_assist/draft/open 动作 assist_draft_open 角色 teacher
  设 r = 调用 teacher_assist.取草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/draft/confirm 动作 assist_draft_confirm 角色 teacher
  设 r = 调用 teacher_assist.确认草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/draft/discard 动作 assist_draft_discard 角色 teacher
  设 r = 调用 teacher_assist.放弃草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /teacher_assist/draft/undo 动作 assist_draft_undo 角色 teacher
  设 r = 调用 teacher_assist.撤销草稿页面 current_user={current_user} draft_id={draft_id} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束
