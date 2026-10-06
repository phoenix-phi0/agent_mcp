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

  设 series = {series 或 hanabira}
  设 code_args.series = {series}
  设 code_ok = 查一值表 app.db series_code_ok {code_args}
  如果 {code_ok} 不等于 1
    返回 {"error":"系列编号只能是小写字母、数字、下划线、连字符"} 400
  结束

  设 series_rows = 解析JSON []
  设 has_series_file = 存在 content/series.jsonl
  如果 {has_series_file} 等于 是
    读JSONL series_rows = content/series.jsonl
  结束

  # 新约定的文件优先；hanabira 没有新文件时读老的两个文件
  设 lessons_file = content/series/{series}/lessons.jsonl
  设 links_rows = 解析JSON []
  设 legacy = 否
  设 has_lessons_file = 存在 {lessons_file}
  如果 {has_lessons_file} 等于 否
    如果 {series} 不等于 hanabira
      返回 {"error":"没有这个系列的课文文件：{lessons_file}"} 404
    结束
    设 legacy = 是
    设 lessons_file = content/lessons.jsonl
    读JSONL links_rows = content/item_lessons.jsonl
  结束
  读JSONL lessons = {lessons_file}

  设 lesson_n = 0
  设 link_n = 0
  设 point_n = 0
  设 unlinked = 0
  设 rejected_n = 0
  设 rejected_rows = 解析JSON []
  设 note = 

  事务 app.db
    遍历 one_series 于 {series_rows} 序号 row
      设 series_args.code = {one_series.code 或}
      设 series_args.label = {one_series.label 或}
      设 series_args.description = {one_series.description 或}
      设 series_args.source = {one_series.source 或}
      设 series_args.license = {one_series.license 或}
      设 series_args.sort = {one_series.sort 或 0}
      设 affected = 写库表 app.db series_upsert {series_args}
    结束

    设 affected = 写库表 app.db item_lesson_clear {code_args}
    设 affected = 写库表 app.db lesson_point_clear {code_args}
    设 affected = 写库表 app.db lesson_clear {code_args}

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
      设 lessons_found.seq = {item.seq 或}
      设 lessons_found.items = {item.items 或}
      设 lessons_found.points = {item.points 或}
      设 lessons_found.series = {item.series 或}
      如果 {lessons_found.series} 为空
        设 lessons_found.series = {series}
      结束
      设 reason = 
      如果 {lessons_found.series} 不等于 {series}
        设 reason = 这一行的series是{lessons_found.series}，不是正在导入的{series}
      否则
        设 reason = 查一值表 app.db lesson_refs_missing {lessons_found}
      结束
      如果 {reason} 不为空
        # 拒收整行：课不进库，映射也不进
        设 rejected_n = 相加 {rejected_n} 1
        设 bad_row.file = {lessons_file}
        设 bad_row.row = {row}
        设 bad_row.code = {lessons_found.code}
        设 bad_row.reason = {reason}
        设 rejected_rows = 列表加项 {rejected_rows} {bad_row}
        设 note = {note} 课文第{row}行{lessons_found.code}拒收：{reason}；
      否则
        # 缺编号不在这里判：插入语句把空编号变成 NULL，撞非空约束抛错，
        # 整个事务回滚——课文文件坏了就一条都不换，库里保持原样。
        设 affected = 写库表 app.db lesson_insert {lessons_found}
        设 lesson_n = 相加 {lesson_n} 1
        设 affected = 写库表 app.db lesson_items_link {lessons_found}
        设 link_n = 相加 {link_n} {affected}
        设 affected = 写库表 app.db lesson_points_link {lessons_found}
        设 point_n = 相加 {point_n} {affected}
      结束
    结束

    # 老文件（hanabira）的挂接：一行一对，两头有一头不存在就那一行不挂
    遍历 link 于 {links_rows} 序号 row
      设 pair.item = {link.item 或}
      设 pair.lesson = {link.lesson 或}
      设 pair.rank = {link.rank 或 1}
      设 affected = 写库表 app.db item_lesson_add {pair}
      如果 {affected} 等于 1
        设 link_n = 相加 {link_n} 1
      否则
        设 unlinked = 相加 {unlinked} 1
        设 bad_row.file = content/item_lessons.jsonl
        设 bad_row.row = {row}
        设 bad_row.code = {pair.lesson}
        设 bad_row.reason = 挂接{pair.item}→{pair.lesson}没挂上（两头有一头不存在，或者重复）
        设 rejected_rows = 列表加项 {rejected_rows} {bad_row}
        设 note = {note} 挂接第{row}行{pair.item}→{pair.lesson}没挂上；
      结束
    结束
  结束

  # 这个系列里没挂到任何条目、知识点上的课：映射漏了或拼错了
  设 orphan_n = 查一值表 app.db lesson_orphans {code_args}
  设 rejected_n = 相加 {rejected_n} {unlinked}

  设 report.series = {series}
  设 report.lessons = {lesson_n}
  设 report.links = {link_n}
  设 report.points = {point_n}
  设 report.failed = {unlinked}
  设 report.rejected = {rejected_n}
  设 report.rejected_rows = {rejected_rows}
  设 report.orphans = {orphan_n}
  设 report.note = {note}
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
