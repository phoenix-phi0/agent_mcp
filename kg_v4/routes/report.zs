接口 GET /report/class 角色 teacher
  设 r = 调用 report.取全班学情 sort_by={sort_by 或} student={student 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /report/student 角色 teacher
  设 r = 调用 report.取学生学情 student={student} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /report/summary/write 角色 teacher
  设 r = 调用 report.写学情总结 student={student} current_user={current_user} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /report/summary 角色 teacher
  设 r = 调用 report.取最近总结 student={student} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /report/home 动作 report_home 角色 teacher
  设 r = 调用 report.学情首页页面 report_sort={report_sort 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /report/one 动作 report_one 角色 teacher
  设 r = 调用 report.学生页面 student={student} chat_page={chat_page 或} chat_kw={chat_kw 或} chat_start={chat_start 或} chat_end={chat_end 或} chat_kind={chat_kind 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /report/chat/search 动作 report_chat_search 角色 teacher
  设 r = 调用 report.问老师筛选 student={student} chat_q={chat_q 或} chat_from={chat_from 或} chat_to={chat_to 或} chat_intent={chat_intent 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 已按条件筛选
  消息 系统 {_msg} ok
  响应 go {r.go}
结束

接口 POST /report/chat/one 动作 report_chat_full 角色 teacher
  设 r = 调用 report.问老师全文页面 student={student} chat_id={chat_id} chat_kw={chat_kw 或} chat_start={chat_start 或} chat_end={chat_end 或} chat_kind={chat_kind 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /report/summary 动作 report_summary 角色 teacher
  设 r = 调用 report.写学情总结页面 student={student} current_user={current_user} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  设 _msg = 学情总结写好了
  消息 系统 {_msg} ok
  响应 state {r}
结束
