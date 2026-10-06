# 登录、退出、现在是谁、改自己的密码。由 py -m gen auth 生成的 auth.zs 改出来：
# 没有注册——学生账号由教师在「学生管理」页建（routes/student.zs），教师账号用
# 命令行建（py -m kg 建教师 <用户名>）。
#
# 两种模式，同一份路由（tools/dsl_http.py 文件开头「认证」一节）：
#
#   单人模式（默认：app.pyw、py -m kg、gen run kg）  不用登录，下面这些声明都不
#       起作用；learner 照旧是请求里的 learner，没给就是 me
#   多人模式（py -m kg --登录、KG_LOGIN=1）  除了标「公开」的，所有接口都要
#       登录；learner 就是登录的用户名，请求体里的 learner 一律不算；标了
#       「角色 teacher」的接口（管理侧）只许教师，学生 403「需要教师权限」
#
# 「认证 核对」：每个请求按 cookie 里的用户名查一次 user_auth，停用的账号下一个
# 请求就当没登录（令牌本身是无状态的签名串，没法吊销，靠这一步）。
#
# 登录限流在 auth 包的「登录」里：同一用户名或同一来源连续失败 5 次锁 5 分钟。

认证 可选
认证 核对 app.db user_auth
认证 身份 learner 默认 me
认证 角色 teacher 教师


# 登录失败不区分「没这个人」「密码错」「停用了」（user_by_name 查不到停用的）
接口 POST /auth/login 动作 auth_login 公开
  用包 auth http
  设 user = 登录 app.db user_by_name {request}
  如果 {user} 为空
    返回 {"error":"用户名或密码不对"} 400
  结束
  返回 {"go":"@来处","messages":[{"who":"系统","text":"已登录","kind":"ok"}]}
结束


接口 POST /auth/logout 动作 auth_logout 公开
  用包 auth http
  设 result = 退出登录
  返回 {"go":"登录","messages":[{"who":"系统","text":"已退出","kind":"ok"}]}
结束


# 现在是谁。前端打开页面、登录、退出时问一次（templates/frontend/app.js.j2 的
# refreshMe）：顶栏显示 label，hide 里的「侧」不进导航——学生看不到「管理」。
# 只是界面上藏起来，真正把关的是接口上的「角色 teacher」。
# 单人模式 user 是空串，顶栏什么都不多、管理侧照常可用。
接口 POST /auth/me 动作 auth_me 公开
  用包 common db http
  设 out.user = {current_user}
  设 out.mode = {auth_mode}
  设 out.label =
  设 out.role =
  设 out.hide = 解析JSON []
  如果 {current_user} 不为空
    设 who.username = {current_user}
    设 me = 查一行表 app.db auth_me {who}
    设 out.label = {me.label}
    设 out.role = {me.role}
    设 out.hide = 解析JSON {me.hide}
  结束
  返回 {out}
结束


# 改自己的密码：要旧密码。用户名只认登录的人（{current_user}），请求体里的
# username 不算。单人模式没有账号，这一步不可用
接口 POST /auth/password 动作 auth_password
  用包 auth http
  如果 {current_user} 为空
    返回 {"error":"单人模式没有账号，不用改密码"} 400
  结束
  设 result = 改密码 app.db user_by_name user_set_password {request}
  如果 {result} 开头是 [
    返回 {"error":"{result}"} 400
  结束
  返回 {"messages":[{"who":"系统","text":"密码改好了，下次用新密码登录","kind":"ok"}]}
结束
