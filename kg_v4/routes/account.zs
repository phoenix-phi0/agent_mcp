认证 可选
认证 核对 account.核对身份
认证 身份 learner 默认 me
认证 角色 student 学生
认证 角色 teacher 教师


接口 POST /account/login 动作 auth_login 公开
  设 r = 调用 account.登录 username={username} password={password}
  设 _msg = 已登录
  消息 系统 {_msg} ok
  响应 go @来处
结束

接口 POST /account/logout 动作 auth_logout 公开
  设 r = 调用 account.退出 learner={learner}
  设 _msg = 已退出
  消息 系统 {_msg} ok
  响应 go 登录
结束

接口 GET /account/me
  设 r = 调用 account.我是谁 learner={learner} auth_mode={auth_mode}
  返回 {r}
结束

接口 POST /account/password 动作 auth_password
  设 r = 调用 account.改密码 learner={learner} auth_mode={auth_mode} old_password={old_password} new_password={new_password} new_password2={new_password2}
  设 _msg = 密码改好了，下次用新密码登录
  消息 系统 {_msg} ok
结束

接口 GET /account/students 角色 teacher
  设 r = 调用 account.列学生
  返回 {r}
结束

接口 POST /account/students 动作 student_home 角色 teacher
  设 r = 调用 account.列学生页面
  表格 students {r}
结束

接口 POST /account/students/create 动作 student_create 角色 teacher
  设 r = 调用 account.建学生 username={username} password={password} display_name={display_name}
  设 _msg = 建好了学生账号：{username}
  表格 students {r}
  消息 系统 {_msg} ok
结束

接口 POST /account/students/reset 动作 student_reset 角色 teacher
  设 r = 调用 account.重置学生密码 username={reset_user} new_password={new_password}
  设 _msg = 已重置{reset_user}的密码
  消息 系统 {_msg} ok
结束

接口 POST /account/students/disable 动作 student_disable 角色 teacher
  设 r = 调用 account.设置学生停用 username={username} disabled=1
  设 _msg = 已停用
  表格 students {r}
  消息 系统 {_msg} ok
结束

接口 POST /account/students/enable 动作 student_enable 角色 teacher
  设 r = 调用 account.设置学生停用 username={username} disabled=0
  设 _msg = 已启用
  表格 students {r}
  消息 系统 {_msg} ok
结束

接口 GET /account/subject/candidates 角色 teacher
  设 r = 调用 account.列可分配学生 subject_id={subject_id}
  返回 {r}
结束

接口 POST /account/subject/members 动作 subject_members 角色 teacher
  设 r = 调用 account.科目成员页面 learner={learner} subj_id={subj_id} current_role={current_role 或} auth_mode={auth_mode 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /account/subject/assign 动作 subject_assign 角色 teacher
  设 r = 调用 account.分配科目学生页面 learner={learner} subj_id={subj_id} assign_learners={assign_learners} current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已分配
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /account/subject/assign-one 动作 subject_assign_one 角色 teacher
  设 r = 调用 account.分配科目学生页面 learner={learner} subj_id={subj_id} assign_learners={cand_learner} current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已分配
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /account/subject/revoke 动作 subject_revoke 角色 teacher
  设 r = 调用 account.撤销科目学生页面 learner={learner} subj_id={subj_id} member_learner={member_learner} current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已撤销
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /account/subject/teacher-add 动作 subject_teacher_add 角色 teacher
  设 r = 调用 account.加科目教师页面 learner={learner} subj_id={subj_id} add_teacher={add_teacher} add_role={add_role 或} current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已加入本科目
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /account/subject/teacher-owner 动作 subject_teacher_owner 角色 teacher
  设 r = 调用 account.改科目教师角色页面 learner={learner} subj_id={subj_id} member_teacher={member_teacher} role=owner current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已设为负责
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /account/subject/teacher-editor 动作 subject_teacher_editor 角色 teacher
  设 r = 调用 account.改科目教师角色页面 learner={learner} subj_id={subj_id} member_teacher={member_teacher} role=editor current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已设为协作
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /account/subject/teacher-remove 动作 subject_teacher_remove 角色 teacher
  设 r = 调用 account.移除科目教师页面 learner={learner} subj_id={subj_id} member_teacher={member_teacher} current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已移出本科目
  消息 系统 {_msg} ok
  响应 state {r}
结束
