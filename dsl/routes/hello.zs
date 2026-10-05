# 干净环境的示例接口。不依赖题库，起服务器就能试。
#
#   py serve_http.py
#   curl -X POST localhost:8091/hello -H "Content-Type: application/json" -d "{\"name\":\"世界\"}"
#
# 端口写成范围：8091 被占了就往上找，找到哪个会打印出来。
# 命令行 --port 优先，而且给了就不找。

服务 8091-8099


# ---- 两种返回方式 ----

# 一、「返回」：像 Flask 的 return。给 JSON 就返回 JSON，给文本就返回
# 文本，末尾三位数是状态码。立即结束，后面的行不跑。

接口 POST /api/user
  如果 {id} 为空
    返回 {"code":400,"msg":"缺少 id"} 400
  结束

  返回 {"code":0,"data":{"id":"{id}","name":"张三"}}
结束


接口 GET /health
  返回 ok
结束


# 二、「消息 / 状态」：往固定的五个字段里塞，塞完接着跑。
# 配套 .ui 生成的前端用。

接口 POST /hello
  用包 http

  消息 服务器 你好，{name}
  状态 last {name}
结束


# ---- 会话 ----

# 连发几次能看到计数在涨——验证会话真的存住了。
# 会话按 learner 分文件，换个 learner 计数从头开始。

接口 POST /count
  用包 common http

  如果 {session.次数} 为空
    设 session.次数 = 0
  结束

  设 session.次数 = 相加 {session.次数} 1
  消息 服务器 这是第 {session.次数} 次
  状态 count {session.次数}
结束


# ---- 数据库 ----

# 先建库：py gendb.py --create --demo
接口 POST /authors
  用包 db

  设 authors = 查询 试验.db 作者统计
  返回 {"authors":{authors}}
结束


# 事务：两条写入要么全成要么全败
接口 POST /authors/add
  用包 db

  如果 {code} 为空
    返回 {"error":"缺少工号"} 400
  结束

  事务 试验.db
    设 result = 写库 试验.db 加作者 code={code} name={name} level=新手
  结束

  返回 {"added":{code}}
结束


# ---- 排查 ----

接口 POST /echo
  返回 {"收到":{"name":"{name}","id":"{id}"},"会话":{session}}
结束


# 真调一次模型。默认假客户端返回固定内容，加 --real 才走真的。
接口 POST /ask
  问 answer = 用一句话回答：{question}
  返回 {"answer":"{answer}"}
结束
