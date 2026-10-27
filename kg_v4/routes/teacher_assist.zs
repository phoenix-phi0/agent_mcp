接口 POST /teacher_assist/ask 动作 assist_send 角色 teacher
  设 r = 调用 teacher_assist.问助手页面 current_user={current_user} message={content}
  消息 助手 {r.reply} ok
结束

接口 POST /teacher_assist/history 动作 assist_state 角色 teacher
  设 r = 调用 teacher_assist.列对话页面 current_user={current_user}
  响应 state {"talk":{r.talk}}
结束

接口 GET /teacher_assist/messages 角色 teacher
  设 r = 调用 teacher_assist.列对话 current_user={current_user} limit={limit 或}
  返回 {r}
结束
