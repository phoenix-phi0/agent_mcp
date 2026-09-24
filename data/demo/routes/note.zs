# 笔记的一套增删改查。由实体 note 用「完整」模板生成。
# 生成是一次性的——落盘之后就是普通的 .zs，随便改。
#
# 配套的五条 SQL 在 queries/ 下，文件名 note_*.sql。
# 界面在 ui/note.ui：列表、编辑、新建三个界面，编辑和新建分开，
# 各走各的接口。

接口 POST /note/list 动作 note_refresh
  用包 db http
  设 行表 = 查询 app.db note_list 条数=50
  响应 rows {行表}
结束


接口 POST /note/one 动作 note_open
  用包 db http
  设 一条 = 查一行 app.db note_one id={id}
  如果 {一条.id} 为空
    返回 {"error":"没有这条记录"} 404
  结束
  响应 state {一条}
结束


接口 POST /note/create 动作 note_save
  用包 db http
  事务 app.db
    设 影响 = 写库表 app.db note_insert {请求}
  结束
  设 行表 = 查询 app.db note_list 条数=50
  响应 rows {行表}
  消息 系统 已新建 ok
结束


接口 POST /note/update 动作 note_update
  用包 db http
  事务 app.db
    设 影响 = 写库表 app.db note_update {请求}
  结束
  # 影响 0 行说明那条记录没了——可能别人删了，也可能主键没带过来
  如果 {影响} 等于 0
    返回 {"error":"没有这条记录"} 404
  结束
  设 行表 = 查询 app.db note_list 条数=50
  响应 rows {行表}
  消息 系统 已保存 ok
结束


接口 POST /note/delete 动作 note_remove
  用包 db http
  事务 app.db
    设 影响 = 写库表 app.db note_delete {请求}
  结束
  设 行表 = 查询 app.db note_list 条数=50
  响应 rows {行表}
  消息 系统 已删除 ok
结束
