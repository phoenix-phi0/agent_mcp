# 课文：导入、按条目取。
#
# 课文是内容不是学习记录（见 entities/lesson.entity），导入是整表清空重灌：
# 映射文件里删掉一行，库里那条挂接也跟着没有，不需要另写对账。整个导入在
# 一个事务里，课文文件有坏行（缺编号、编号重复）就全部回滚，库里保持原样。
#
# 挂接（item_lessons.jsonl）两头不存在时不报错、只计数：拼错一个条目编号
# 不该让整批都进不去，但报告里要看得见是哪一行。
#
# 条目要先导进来（kg/import2），所以 run_import 里这个排在它后面。

接口 POST /lesson/import 动作 lesson_import
  用包 common db http

  读JSONL 课表 = content/lessons.jsonl
  读JSONL 挂表 = content/item_lessons.jsonl

  设 课数 = 0
  设 挂数 = 0
  设 没挂上 = 0
  设 说明 = 

  事务 app.db
    设 影响 = 写库 app.db item_lesson_clear
    设 影响 = 写库 app.db lesson_clear

    遍历 项 于 {课表} 序号 行
      设 课.code = {项.code 或}
      设 课.level = {项.level 或}
      设 课.title = {项.title 或}
      设 课.summary = {项.summary 或}
      设 课.explanation = {项.explanation 或}
      设 课.formation = {项.formation 或}
      设 课.examples = {项.examples 或}
      设 课.changed = {项.changed 或 0}
      设 课.source_title = {项.source_title 或}
      # 缺编号不在这里判：插入语句把空编号变成 NULL，撞非空约束抛错，
      # 整个事务回滚——课文文件坏了就一条都不换，库里保持原样。
      设 影响 = 写库表 app.db lesson_insert {课}
      设 课数 = 相加 {课数} 1
    结束

    遍历 挂 于 {挂表} 序号 行
      设 对.item = {挂.item 或}
      设 对.lesson = {挂.lesson 或}
      设 对.rank = {挂.rank 或 1}
      设 影响 = 写库表 app.db item_lesson_add {对}
      如果 {影响} 等于 1
        设 挂数 = 相加 {挂数} 1
      否则
        设 没挂上 = 相加 {没挂上} 1
        设 说明 = {说明} 挂接第{行}行{对.item}→{对.lesson}没挂上；
      结束
    结束
  结束

  # 没挂到任何条目上的课：映射文件漏了或拼错了
  设 孤数 = 查一值 app.db lesson_orphans

  返回 {"lessons":"{课数}","links":"{挂数}","failed":"{没挂上}","orphans":"{孤数}","note":"{说明}"}
结束


# 一个条目挂着的课文，按 rank 排。examples 是 JSON 文本，页面自己解析。
接口 POST /item/lessons 动作 item_lessons
  用包 db http

  设 条目 = {item 或}
  如果 {条目} 为空
    返回 {"error":"缺 item（哪个条目）"} 400
  结束
  设 查.item = {条目}
  设 有 = 查一值表 app.db item_exists {查}
  如果 {有} 为空
    返回 {"error":"没有这个条目"} 404
  结束

  设 课 = 查询表 app.db item_lessons {查}
  设 组.lessons = {课}
  响应 lists {组}
结束


# 教材页（ui/textbook.ui）的课文表：按等级筛、按关键字搜。进页面时也调它
# （「进入时」），所以只回 lists 和 state，不推消息。
#
# 等级、关键字是用户填的，关键字里可能有空格、日语，所以拼一个字典交给
# 查询表，不用按位置传的写法（那种按空格切参数，值一有空格就错位）。
接口 POST /lesson/list 动作 lesson_list
  用包 db http data

  设 查.lesson_level = {lesson_level 或 全部}
  设 查.keyword = {keyword 或}
  设 课表 = 查询表 app.db lesson_list {查}
  设 组.lessons = {课表}
  响应 lists {组}
  设 数 = 条数 {课表}
  设 状态.lesson_count = 共{数}课
  响应 state {状态}
  # 把用的条件填回表单：表单的初值是空串（实体的「默认 全部」管不到前端），
  # 不填回去的话进页面时等级下拉是空的，表里却是全部
  响应 form {查}
结束


# 读一课：教材页的阅读视图，界面上的「载入」。地址带着 lesson 打开教材页
# （#教材?lesson=hb-n4-118，表里点标题、刷新、别处给的链接都是这样）时
# 前端调它。
#
# 回什么：
#   state.reading       抬头、一句话、接续、讲解，「练这一课」「问老师」的地址
#   lists.examples      例句，一句一行（SQL 里把 JSON 拆开）
#   lists.lesson_items  挂着的条目
#   lists.lessons       全部课文——「载入」之前前端把表单清回了默认（等级
#                       全部、关键字空），课文表也得跟着回到全部，不然退回
#                       课文表时下拉框写着「全部」、表里却还是上次筛过的
#
# 没有这一课：不用「返回」报 404，回 state.reading.missing 那句说明，页面
# 上直接显示。也不推消息——这个页面没有消息流，消息会落到别的界面的流里。
#
# 表单也填回默认（等级全部、关键字空）：理由同上，「载入」前表单被清成了
# 空串，等级下拉会是空的。
接口 POST /lesson/one 动作 lesson_one
  用包 db http data

  设 课文 = {lesson 或}
  如果 {课文} 为空
    返回 {"error":"缺 lesson（哪一课）"} 400
  结束
  设 查.lesson = {课文}
  设 课 = 查一行表 app.db lesson_one {查}
  如果 {课.code 或} 为空
    设 没有.code = {课文}
    设 没有.missing = 没有这一课（{课文}），回课文表重新选。
    设 没有.back = #%E6%95%99%E6%9D%90
    设 状态.reading = {没有}
    响应 state {状态}
  否则
    设 课.missing = 
    设 例句 = 查询表 app.db lesson_examples {查}
    设 条目 = 查询表 app.db lesson_items {查}
    设 全部.lesson_level = 全部
    设 全部.keyword = 
    设 课表 = 查询表 app.db lesson_list {全部}
    设 组.examples = {例句}
    设 组.lesson_items = {条目}
    设 组.lessons = {课表}
    响应 lists {组}
    设 数 = 条数 {课表}
    设 状态.lesson_count = 共{数}课
    设 状态.reading = {课}
    响应 state {状态}
  结束
  设 默认.lesson_level = 全部
  设 默认.keyword = 
  响应 form {默认}
结束
