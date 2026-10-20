模块 account
依赖 无
认证 可选
认证 核对 app.db account_by_name
认证 身份 who 默认 me
认证 角色 teacher 教师
认证 角色 student 学生

## 表
表 account_user
  id 整数 主键
  username 文本 唯一 用户名
  password_hash 文本 密码哈希
  role 文本 角色

## 函数
公开 函数 登录 username password
  返回 {ok}
  伪代码 核对用户名密码，对了 签发登录，返回 {"ok": 1}；不对返回 {"ok": 0}
公开 函数 我的角色 who
  返回 {role}
  报错 404 没有这个用户
  伪代码 按 username=who 查 account_user，查不到 报错 404；查到返回 {"role": role}

## 接口
POST /account/login -> 登录 公开
GET /account/whoami -> 我的角色 角色 teacher

## 用例
用例 登录_账号不存在
  调用 登录 username=nope password=x
  得 ok=0
用例 我的角色_有
  先 数据 account_user username=t1 role=teacher password_hash=x
  调用 我的角色 who=t1
  得 role=teacher
用例 我的角色_没有
  调用 我的角色 who=nope
  报错 404
