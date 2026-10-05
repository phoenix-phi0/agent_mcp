# 单词的一套增删改查。由实体 word 用「完整」模板生成。
# 生成是一次性的——落盘之后就是普通的 .zs，随便改。
#
# 配套的五条 SQL 在 queries/ 下，文件名 word_*.sql。
# 界面在 ui/word.ui：列表、编辑、新建三个界面，编辑和新建分开，
# 各走各的接口。

接口 POST /word/list 动作 word_refresh
  用包 db http
  设 rows = 查询 app.db word_list limit=50
  设 group.words = {rows}
  响应 lists {group}
结束


接口 POST /word/one 动作 word_open
  用包 db http
  设 record = 查一行 app.db word_one id={id}
  如果 {record.id} 为空
    返回 {"error":"没有这条记录"} 404
  结束
  # form：前端填进编辑表单（界面上的「载入」）
  响应 form {record}
结束


接口 POST /word/create 动作 word_save
  用包 db http
  事务 app.db
    设 affected = 写库表 app.db word_insert {request}
  结束
  设 rows = 查询 app.db word_list limit=50
  设 group.words = {rows}
  响应 lists {group}
  消息 系统 已新建 ok
结束


接口 POST /word/update 动作 word_update
  用包 db http
  # 没带主键就别进事务：绑定时报「缺少参数」，在事务里会变成 500
  如果 {request.id} 为空
    返回 {"error":"没有指定要改哪一条"} 400
  结束
  事务 app.db
    设 affected = 写库表 app.db word_update {request}
  结束
  # 影响 0 行说明那条记录没了——可能别人删了，也可能主键没带过来
  如果 {affected} 等于 0
    返回 {"error":"没有这条记录"} 404
  结束
  设 rows = 查询 app.db word_list limit=50
  设 group.words = {rows}
  响应 lists {group}
  消息 系统 已保存 ok
结束


接口 POST /word/delete 动作 word_remove
  用包 db http
  如果 {request.id} 为空
    返回 {"error":"没有指定要删哪一条"} 400
  结束
  事务 app.db
    设 affected = 写库表 app.db word_delete {request}
  结束
  设 rows = 查询 app.db word_list limit=50
  设 group.words = {rows}
  响应 lists {group}
  消息 系统 已删除 ok
结束
