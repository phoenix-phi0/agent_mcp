认证 可选
认证 核对 account.核对身份
认证 身份 learner 默认 me
认证 角色 teacher 教师
认证 角色 student 学生

接口 POST /account/login 公开
  设 r = 调用 account.登录 username={username} password={password}
  返回 {r}
结束

接口 GET /account/whoami 角色 teacher
  设 r = 调用 account.我的角色 learner={learner}
  返回 {r}
结束
