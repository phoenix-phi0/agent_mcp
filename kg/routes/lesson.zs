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

  读JSONL lessons = content/lessons.jsonl
  读JSONL links_rows = content/item_lessons.jsonl

  设 lesson_n = 0
  设 link_n = 0
  设 unlinked = 0
  设 note = 

  事务 app.db
    设 affected = 写库 app.db item_lesson_clear
    设 affected = 写库 app.db lesson_clear

    遍历 item 于 {lessons} 序号 row
      设 lessons_found.code = {item.code 或}
      设 lessons_found.level = {item.level 或}
      设 lessons_found.title = {item.title 或}
      设 lessons_found.summary = {item.summary 或}
      设 lessons_found.explanation = {item.explanation 或}
      设 lessons_found.formation = {item.formation 或}
      设 lessons_found.examples = {item.examples 或}
      设 lessons_found.changed = {item.changed 或 0}
      设 lessons_found.source_title = {item.source_title 或}
      # 缺编号不在这里判：插入语句把空编号变成 NULL，撞非空约束抛错，
      # 整个事务回滚——课文文件坏了就一条都不换，库里保持原样。
      设 affected = 写库表 app.db lesson_insert {lessons_found}
      设 lesson_n = 相加 {lesson_n} 1
    结束

    遍历 link 于 {links_rows} 序号 row
      设 pair.item = {link.item 或}
      设 pair.lesson = {link.lesson 或}
      设 pair.rank = {link.rank 或 1}
      设 affected = 写库表 app.db item_lesson_add {pair}
      如果 {affected} 等于 1
        设 link_n = 相加 {link_n} 1
      否则
        设 unlinked = 相加 {unlinked} 1
        设 note = {note} 挂接第{row}行{pair.item}→{pair.lesson}没挂上；
      结束
    结束
  结束

  # 没挂到任何条目上的课：映射文件漏了或拼错了
  设 orphan_n = 查一值 app.db lesson_orphans

  返回 {"lessons":"{lesson_n}","links":"{link_n}","failed":"{unlinked}","orphans":"{orphan_n}","note":"{note}"}
结束


# 一个条目挂着的课文，按 rank 排。examples 是 JSON 文本，页面自己解析。
接口 POST /item/lessons 动作 item_lessons
  用包 db http

  设 item = {item 或}
  如果 {item} 为空
    返回 {"error":"缺 item（哪个条目）"} 400
  结束
  设 query.item = {item}
  设 exists = 查一值表 app.db item_exists {query}
  如果 {exists} 为空
    返回 {"error":"没有这个条目"} 404
  结束

  设 lessons_found = 查询表 app.db item_lessons {query}
  设 group.lessons = {lessons_found}
  响应 lists {group}
结束


# 教材页（ui/textbook.ui）的课文表：按等级筛、按关键字搜。进页面时也调它
# （「进入时」），所以只回 lists 和 state，不推消息。
#
# 等级、关键字是用户填的，关键字里可能有空格、日语，所以拼一个字典交给
# 查询表，不用按位置传的写法（那种按空格切参数，值一有空格就错位）。
接口 POST /lesson/list 动作 lesson_list
  用包 db http data

  设 query.lesson_level = {lesson_level 或 全部}
  设 query.keyword = {keyword 或}
  设 lessons = 查询表 app.db lesson_list {query}
  设 group.lessons = {lessons}
  响应 lists {group}
  设 count = 条数 {lessons}
  设 state.lesson_count = 共{count}课
  响应 state {state}
  # 把用的条件填回表单：表单的初值是空串（实体的「默认 全部」管不到前端），
  # 不填回去的话进页面时等级下拉是空的，表里却是全部
  响应 form {query}
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

  设 lesson = {lesson 或}
  如果 {lesson} 为空
    返回 {"error":"缺 lesson（哪一课）"} 400
  结束
  设 query.lesson = {lesson}
  设 lessons_found = 查一行表 app.db lesson_one {query}
  如果 {lessons_found.code 或} 为空
    设 missing.code = {lesson}
    设 missing.missing = 没有这一课（{lesson}），回课文表重新选。
    设 missing.back = #%E6%95%99%E6%9D%90
    设 state.reading = {missing}
    响应 state {state}
  否则
    设 lessons_found.missing = 
    设 examples = 查询表 app.db lesson_examples {query}
    设 item = 查询表 app.db lesson_items {query}
    设 all_args.lesson_level = 全部
    设 all_args.keyword = 
    设 lessons = 查询表 app.db lesson_list {all_args}
    设 group.examples = {examples}
    设 group.lesson_items = {item}
    设 group.lessons = {lessons}
    响应 lists {group}
    设 count = 条数 {lessons}
    设 state.lesson_count = 共{count}课
    设 state.reading = {lessons_found}
    响应 state {state}
  结束
  设 defaults.lesson_level = 全部
  设 defaults.keyword = 
  响应 form {defaults}
结束
