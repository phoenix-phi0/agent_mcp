# 文件上传的接口。配 test_upload.py 用。
#
#   cd dsl
#   py serve_http.py            起服务
#   py test_upload.py           另开一个窗口跑
#
# 三个接口对应三种命名方式，外加一个只看不存的。

服务 8091-8099


# 只报告这次请求带了什么，不存盘。先跑这个确认 multipart 收到了。
接口 POST /upload/peek
  用包 http

  设 清单 = 列上传
  返回 {"带了什么":"{清单}"}
结束


# 哈希命名：同样的文件不重复存，天然避开重名和路径注入
接口 POST /upload/hash 动作 save
  用包 http

  设 路径 = 存文件 file uploads 哈希
  如果 {路径} 开头是 [
    返回 {"error":"{路径}"} 400
  结束
  返回 {"ok":true,"path":"{路径}"}
结束


# 时间命名：能看出传的是什么文件，代价是同一秒传两个同名的会撞
接口 POST /upload/time 动作 save
  用包 http

  设 路径 = 存文件 file uploads 时间
  如果 {路径} 开头是 [
    返回 {"error":"{路径}"} 400
  结束
  返回 {"ok":true,"path":"{路径}"}
结束


# 原名：用户能控制文件名，只在确实需要原名时用
接口 POST /upload/raw 动作 save
  用包 http

  设 路径 = 存文件 file uploads 原名
  如果 {路径} 开头是 [
    返回 {"error":"{路径}"} 400
  结束
  返回 {"ok":true,"path":"{路径}"}
结束


# 文本字段跟文件一起发时，两边都要能取到。
# multipart 下文本字段是 request.form，而 .ui 前端把它们包在 form 里
# 发成一个 JSON 字符串——路由器要 parse 那一层。
接口 POST /upload/mixed 动作 save
  用包 http

  设 路径 = 存文件 file uploads 哈希
  返回 {"path":"{路径}","learner":"{learner}","note":"{note}"}
结束


# 同一个字段存两次。第二次多半拿到空文件——read() 之后指针在末尾。
# 这个接口就是用来暴露那个问题的。
接口 POST /upload/twice 动作 save
  用包 http

  设 第一次 = 存文件 file uploads 哈希
  设 第二次 = 存文件 file uploads 时间
  返回 {"first":"{第一次}","second":"{第二次}"}
结束


# 字段名写错时该明确报出来，不该静默成功
接口 POST /upload/wrongname 动作 save
  用包 http

  设 路径 = 存文件 不存在的字段 uploads 哈希
  返回 {"path":"{路径}"}
结束
