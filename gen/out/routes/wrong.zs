# 错题本的一套增删改查。由实体 wrong 生成。
# 生成是一次性的——落盘之后就是普通的 .zs，随便改。
#
# 配套的五条 SQL 在 queries/ 下，文件名 wrong_*.sql。

接口 POST /wrong/list 动作 refresh
  用包 db http
  设 行表 = 查询 app.db wrong_list 条数=50
  响应 rows {行表}
结束


接口 POST /wrong/one 动作 open
  用包 db http
  设 一条 = 查一行 app.db wrong_one learner={learner}
  如果 {一条.learner} 为空
    返回 {"error":"没有这条记录"} 404
  结束
  # 存进 state：界面的「显示」节点读它，更新接口也从这儿取主键
  响应 state {一条}
结束


接口 POST /wrong/create 动作 save
  用包 db http
  事务 app.db
    设 影响 = 写库 app.db wrong_insert learner={learner} question={question} course={course} point={point} times={times}
  结束
  消息 系统 已新建 ok
结束


接口 POST /wrong/update 动作 update
  用包 db http
  事务 app.db
    设 影响 = 写库 app.db wrong_update question={question} course={course} point={point} times={times} learner={learner}
  结束
  # 影响 0 行说明那条记录没了——可能别人删了，也可能主键传错
  如果 {影响} 等于 0
    返回 {"error":"没有这条记录"} 404
  结束
  消息 系统 已保存 ok
结束


接口 POST /wrong/delete 动作 remove
  用包 db http
  事务 app.db
    设 影响 = 写库 app.db wrong_delete learner={learner}
  结束
  消息 系统 已删除 ok
结束
