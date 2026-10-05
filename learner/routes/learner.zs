# 学习者的一套增删改查。由实体 learner 生成。
# 生成是一次性的——落盘之后就是普通的 .zs，随便改。
#
# 配套的五条 SQL 在 queries/ 下，文件名 learner_*.sql。

接口 POST /learner/list 动作 refresh
  用包 db http
  设 rows = 查询 app.db learner_list limit=50
  设 group.learners = {rows}
  响应 lists {group}
结束


接口 POST /learner/one 动作 open
  用包 db http
  设 record = 查一行 app.db learner_one code={code}
  如果 {record.code} 为空
    返回 {"error":"没有这条记录"} 404
  结束
  # 存进 state：界面的「显示」节点读它，更新接口也从这儿取主键
  响应 state {record}
结束


接口 POST /learner/create 动作 save
  用包 db http
  事务 app.db
    设 affected = 写库 app.db learner_insert code={code} name={name} level={level} note={note}
  结束
  消息 系统 已新建 ok
结束


接口 POST /learner/update 动作 update
  用包 db http
  事务 app.db
    设 affected = 写库 app.db learner_update name={name} level={level} note={note} code={code}
  结束
  # 影响 0 行说明那条记录没了——可能别人删了，也可能主键传错
  如果 {affected} 等于 0
    返回 {"error":"没有这条记录"} 404
  结束
  消息 系统 已保存 ok
结束


接口 POST /learner/delete 动作 remove
  用包 db http
  事务 app.db
    设 affected = 写库 app.db learner_delete code={code}
  结束
  消息 系统 已删除 ok
结束
