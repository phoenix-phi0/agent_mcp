# 课文：导入、按条目取、教材页。
#
# 课文是内容不是学习记录（见 entities/lesson.entity），导入是**按系列**清空
# 重灌：只删这个系列的课、item_lesson、lesson_point，别的系列和学习记录一行
# 不动。映射文件里删掉一行，库里那条挂接也跟着没有，不需要另写对账。整个导入
# 在一个事务里，课文文件有坏行（缺编号、编号重复、跟别的系列撞编号）就全部
# 回滚，库里保持原样。
#
# 系列（series）：参数 series，不给是 hanabira。读哪个文件：
#   content/series/<code>/lessons.jsonl   新约定，一行一课，映射写在行里
#                                          （items：已有条目，points：已有
#                                          知识点），格式见 content/series/README.md
#   content/lessons.jsonl + item_lessons.jsonl   hanabira 的老文件，新约定的
#                                          文件不在时用，保持兼容
# content/series.jsonl（系列的名称、来源、许可）每次导入都按编号 upsert。
#
# 映射只引用已有的 item / node，**绝不新建**。引用了不存在的：
#   新约定的一行课（items / points 里有一个不存在）整行拒收——课不进库，
#     它的映射也不进；
#   老文件的一行挂接两头有一头不存在，那一行不挂。
# 都不报错、照常导入别的行，拒收的写进报告的 rejected_rows：[{file, row,
# code, reason}]——拼错一个编号不该让整批都进不去，但报告里要看得见是哪一行。
#
# 条目、知识点要先导进来（kg/import2），所以 run_import 里这个排在它后面。

接口 POST /lesson/import 动作 lesson_import
  用包 common db http data text

  # 导入本身在 scripts/lesson_import.zs（教材导入页的「确认导入」也调它）
  设 series = {series 或 hanabira}
  设 report = 执行 scripts/lesson_import.zs series={series}
  设 status = {report.status 或 200}
  如果 {status} 等于 400
    返回 {"error":"{report.error}"} 400
  结束
  如果 {status} 等于 404
    返回 {"error":"{report.error}"} 404
  结束
  返回 {report}
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


# 教材页（ui/textbook.ui）的课文表：按系列、等级筛，按关键字搜。进页面时也
# 调它（「进入时」），所以只回 lists、state、form，不推消息。
#
# 系列：表单里的 series 是顶栏「系列」下拉选的（「改时」直接提交到这里）。
# 给了就记进这个学习者的偏好（learner_pref_set：只认下拉里有的系列，跟原来
# 一样不写），然后按偏好取当前系列（series_current，没记过是 hanabira）——
# 列表、抬头、填回表单的都是它。下拉的选项（lists.series_options）每次都回：
# 进页面时前端先清空 lists，不回的话下拉就空了。
#
# 等级、关键字是用户填的，关键字里可能有空格、日语，所以拼一个字典交给
# 查询表，不用按位置传的写法（那种按空格切参数，值一有空格就错位）。
接口 POST /lesson/list 动作 lesson_list
  用包 db http data

  设 pref.learner = {learner 或 me}
  设 pref.series = {series 或}
  如果 {pref.series} 不为空
    设 affected = 写库表 app.db learner_pref_set {pref}
  结束
  设 current = 查一行表 app.db series_current {pref}

  设 query.series = {current.code}
  设 query.lesson_level = {lesson_level 或 全部}
  设 query.keyword = {keyword 或}
  设 lessons = 查询表 app.db lesson_list {query}
  设 options = 查询 app.db series_options
  设 group.lessons = {lessons}
  设 group.series_options = {options}
  响应 lists {group}
  设 count = 条数 {lessons}
  设 state.lesson_count = 共{count}课
  设 state.series_head = {current.label}
  响应 state {state}
  # 把用的条件填回表单：表单的初值是空串（实体的「默认 全部」管不到前端），
  # 不填回去的话进页面时等级下拉是空的，表里却是全部；系列也是
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
#   lists.lessons       当前系列的全部课文——「载入」之前前端把表单清回了默认
#                       （等级全部、关键字空），课文表也得跟着回到全部，不然
#                       退回课文表时下拉框写着「全部」、表里却还是上次筛过的
#   lists.series_options  系列下拉的选项（同 lesson_list）
#
# 读的这一课不一定在当前系列里（老师兜底给的别的系列的课、别人发来的链接）：
# 照样读，阅读顶栏上写着它自己的系列名（reading.series_label）。
#
# 没有这一课：不用「返回」报 404，回 state.reading.missing 那句说明，页面
# 上直接显示。也不推消息——这个页面没有消息流，消息会落到别的界面的流里。
#
# 表单也填回默认（等级全部、关键字空、当前系列）：理由同上，「载入」前表单
# 被清成了空串，等级下拉会是空的。
接口 POST /lesson/one 动作 lesson_one
  用包 db http data

  设 pref.learner = {learner 或 me}
  设 current = 查一行表 app.db series_current {pref}
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
    设 all_args.series = {current.code}
    设 all_args.lesson_level = 全部
    设 all_args.keyword = 
    设 lessons = 查询表 app.db lesson_list {all_args}
    设 options = 查询 app.db series_options
    设 group.examples = {examples}
    设 group.lesson_items = {item}
    设 group.lessons = {lessons}
    设 group.series_options = {options}
    响应 lists {group}
    设 count = 条数 {lessons}
    设 state.lesson_count = 共{count}课
    设 state.series_head = {current.label}
    设 state.reading = {lessons_found}
    响应 state {state}
  结束
  设 defaults.series = {current.code}
  设 defaults.lesson_level = 全部
  设 defaults.keyword = 
  响应 form {defaults}
结束
