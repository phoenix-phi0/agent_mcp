# 学生管理（管理侧，ui/student.ui）：教师建学生账号、重置密码、停用 / 启用、看列表。
#
# 全部「角色 teacher」：多人模式下只有教师能调，学生 403。单人模式（默认）不查
# 角色、也没人登录——页面照样能打开，只是账号要到多人模式（py -m kg --登录）
# 才用得上。
#
# 学生不能自己注册（没有 /auth/register）。建号、重置的密码在 auth 包的 Python
# 里哈希（建用户 / 重置密码），不经过 SQL 的明文参数。页面上只能建学生
# （user_create 写死 role = student），停用也只停得了学生（student_set_disabled）。


# 进页面：学生表
接口 POST /student/home 动作 student_home 角色 teacher
  用包 common db http
  设 rows = 查询 app.db student_list
  设 group.students = {rows}
  响应 lists {group}
结束


接口 POST /student/create 动作 student_create 角色 teacher
  用包 auth common db http
  设 result = 建用户 app.db user_create {request}
  如果 {result} 开头是 [
    返回 {"error":"{result}"} 400
  结束
  设 rows = 查询 app.db student_list
  设 group.students = {rows}
  响应 lists {group}
  消息 系统 建好了学生账号：{result} ok
结束


# 重置密码：输学生用户名和新密码（new_password）。只重置学生的——
# 先查这个名字是不是学生，教师的密码只能用命令行改（py -m kg 改密）
接口 POST /student/reset 动作 student_reset 角色 teacher
  用包 auth common db http
  设 target.username = {reset_user 或}
  设 found = 查一值表 app.db student_exists {target}
  如果 {found} 等于 0
    返回 {"error":"没有这个学生"} 400
  结束
  设 reset_args = {request}
  设 reset_args.username = {reset_user}
  设 result = 重置密码 app.db user_set_password {reset_args}
  如果 {result} 开头是 [
    返回 {"error":"{result}"} 400
  结束
  消息 系统 已重置{result}的密码 ok
结束


# 行上的停用 / 启用（带 username）
接口 POST /student/disable 动作 student_disable 角色 teacher
  用包 common db http
  设 change.username = {username 或}
  设 change.disabled = 1
  设 affected = 写库表 app.db student_set_disabled {change}
  设 rows = 查询 app.db student_list
  设 group.students = {rows}
  响应 lists {group}
  消息 系统 已停用 ok
结束


接口 POST /student/enable 动作 student_enable 角色 teacher
  用包 common db http
  设 change.username = {username 或}
  设 change.disabled = 0
  设 affected = 写库表 app.db student_set_disabled {change}
  设 rows = 查询 app.db student_list
  设 group.students = {rows}
  响应 lists {group}
  消息 系统 已启用 ok
结束
