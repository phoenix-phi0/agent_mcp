# 按系列导入课文：/lesson/import（routes/lesson.zs）和教材导入页的「确认导入」
# （routes/textbook_import.zs）共用这一段，规则见 routes/lesson.zs 开头的说明和
# content/series/README.md。
#
# 参数 series：系列编号，不给是 hanabira。
# 返回导入报告 {series, lessons, links, points, failed, rejected, rejected_rows,
# orphans, note}；参数不对时返回 {error, status}（status 是 400 / 404），由调用
# 的接口按它回状态码——子脚本的「返回」只结束子脚本，带不出状态码。

用包 common db data text

设 series = {series 或 hanabira}
设 code_args.series = {series}
设 code_ok = 查一值表 app.db series_code_ok {code_args}
如果 {code_ok} 不等于 1
  返回 {"error":"系列编号只能是小写字母、数字、下划线、连字符","status":"400"}
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
    返回 {"error":"没有这个系列的课文文件：{lessons_file}","status":"404"}
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
