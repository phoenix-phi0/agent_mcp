# 作答的一套增删改查。由实体 answer 生成。
# 生成是一次性的——落盘之后就是普通的 .zs，随便改。
#
# 配套的五条 SQL 在 queries/ 下，文件名 answer_*.sql。
#
# id 是自增主键，表单里没有这一列。约定：列表接口返回的每行
# 带 id，界面点「编辑」时存进 state，更新和删除从
# {session.id} 取。

接口 POST /answer/list 动作 refresh
  用包 db http
  设 rows = 查询 app.db answer_list limit=50
  响应 rows {rows}
结束


接口 POST /answer/one 动作 open
  用包 db http
  设 record = 查一行 app.db answer_one id={id}
  如果 {record.id} 为空
    返回 {"error":"没有这条记录"} 404
  结束
  # 存进 state：界面的「显示」节点读它，更新接口也从这儿取主键
  响应 state {record}
结束


接口 POST /answer/create 动作 save
  用包 db http
  事务 app.db
    设 affected = 写库 app.db answer_insert learner={learner} question={question} course={course} point={point} given={given} correct={correct} seconds={seconds}
  结束
  消息 系统 已新建 ok
结束


接口 POST /answer/update 动作 update
  用包 db http
  事务 app.db
    设 affected = 写库 app.db answer_update learner={learner} question={question} course={course} point={point} given={given} correct={correct} seconds={seconds} id={session.id}
  结束
  # 影响 0 行说明那条记录没了——可能别人删了，也可能主键传错
  如果 {affected} 等于 0
    返回 {"error":"没有这条记录"} 404
  结束
  消息 系统 已保存 ok
结束


接口 POST /answer/delete 动作 remove
  用包 db http
  事务 app.db
    设 affected = 写库 app.db answer_delete id={session.id}
  结束
  消息 系统 已删除 ok
结束
