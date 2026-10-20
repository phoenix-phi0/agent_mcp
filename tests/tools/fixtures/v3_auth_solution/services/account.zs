业务 account
  用包 db auth

  公开 函数 登录 username password
    设 row = 查一行 app.db account_user_by_username username={username}
    如果 {row} 为空
      返回 {"ok": 0}
    结束
    设 核对 = 核对密码 {password} {row.password_hash}
    如果 {核对} 等于 否
      返回 {"ok": 0}
    结束
    签发登录 {username}
    返回 {"ok": 1}
  结束

  公开 函数 我的角色 who
    设 row = 查一行 app.db account_user_by_username username={who}
    如果 {row} 为空
      报错 404 没有这个用户
    结束
    返回 {"role": "{row.role}"}
  结束
结束
