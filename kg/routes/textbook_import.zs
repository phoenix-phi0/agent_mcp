# 教材导入：管理侧「教材导入」页（ui/textbook_import.ui）的接口。
#
# 一本教材从上传到出现在教材页的下拉里：
#
#   新建导入  import_create   填系列代号、显示名、来源、授权、课号前缀，选文件，
#                             「开始解析」：存文件（只收 pdf/docx/md/txt，20MB 以内）、
#                             取文本（doc 包「读文档」，扫描版 PDF 报要 OCR）、按课
#                             切块（text 包「切章节」），建任务和块，每块「后台执行」
#                             scripts/import_chunk.zs（请模型抽课、映射到已有条目 /
#                             知识点），马上回到审阅页，页面轮询进度
#   审阅      import_load / import_poll   任务的进度、块表（出错的能重试）、草稿课表
#             import_draft_pass / reject / save、import_map_add / remove、
#             import_pass_mapped          逐课改字段、增删映射、通过驳回，或一键通过
#                                         有映射的课
#   确认导入  import_confirm  通过的课写成 content/series/<code>/lessons.jsonl、系列
#                             写进 content/series.jsonl，再按系列导入
#                             （scripts/lesson_import.zs，跟 /lesson/import 同一段），
#                             显示导入报告
#   删除任务  import_job_delete       只删草稿（三张 import_ 表的行），已导入的课不动
#   撤下系列  import_series_withdraw  清掉这个系列的 lesson / item_lesson / lesson_point，
#                                     series 里 sort 改成 -1（下拉里不再有它）
#
# 草稿表见 entities/textbook_import.entity。映射只引用已有的 item / node，绝不
# 新建：模型给的编号用 SQL 过一遍（import_lesson_check），手动加的先查
# （import_code_kind）。
#
# 地址（同一个界面按参数切换，跟教材页一样）：
#   #教材导入               新建导入、任务表、系列表
#   #教材导入?job=3         审阅一个任务
#   #教材导入?draft=12      编辑一课草稿
#   #教材导入?manage=mnn    管理一个已导入的系列（撤下）。参数不叫 series：新建
#                           表单里有个 series 字段，「载入」看到地址参数跟表单
#                           里的值一样就不拉了
#
# 这是管理功能。kg 现在单人用、没开认证（没有「认证」那一行），页面只是在导航
# 上跟学习者的页面分开（.ui 的「侧 管理」）。以后要加口令：py -m gen auth kg/
# 开认证，再给这几个接口加角色检查（{current_user} 对一张管理员表）。

# 上传的文件：存到项目的 uploads/（.gitignore 里有，不进 git），按内容哈希命名
# 同一个文件传两次只存一份。


# 进页面：任务表、系列表；新建表单的初值（等级范围全部、改写默认勾上）。
接口 POST /import/home 动作 import_home
  用包 db http

  执行 scripts/import_home_view.zs
  设 defaults.lesson_level = 全部
  设 defaults.rewrite = true
  设 defaults.overwrite = false
  响应 form {defaults}
结束


# 新建导入、开始解析。
接口 POST /import/create 动作 import_create
  用包 common db http data doc text

  设 series = {series 或}
  设 label = {label 或}
  设 prefix = {prefix 或}
  如果 {series} 为空
    返回 {"error":"填一下系列代号：英文小写字母开头，比如 mnn"} 400
  结束
  如果 {label} 为空
    返回 {"error":"填一下显示名：教材页的下拉里显示它，比如「大家的日语」"} 400
  结束
  # 课号前缀不填就用系列代号（去掉连字符、下划线）
  如果 {prefix} 为空
    设 prefix = 替换 {series} [-_]
  结束
  设 check_args.series = {series}
  设 check_args.prefix = {prefix}
  设 check = 查一行表 app.db import_series_check {check_args}
  如果 {check.code_ok} 不等于 1
    返回 {"error":"系列代号只能用小写字母开头，后面是小写字母、数字、下划线、连字符，不超过 40 个字"} 400
  结束
  如果 {series} 等于 hanabira
    返回 {"error":"hanabira 是主教材，不能用导入覆盖它"} 400
  结束
  如果 {check.prefix_ok} 不等于 1
    返回 {"error":"课号前缀只能用小写字母开头，后面是小写字母、数字，不超过 20 个字"} 400
  结束
  如果 {check.prefix_taken} 大于 0
    设 out.error = 课号前缀「{prefix}」已经被别的系列用了（那边有 {check.prefix_taken} 课的课号以「{prefix}-」开头），换一个
    返回 {out} 400
  结束
  设 flag_args.overwrite = {overwrite 或}
  设 overwrite_on = 查一值表 app.db import_flag {flag_args}
  设 has_dir = 存在 content/series/{series}/lessons.jsonl
  如果 {overwrite_on} 不等于 1
    如果 {check.series_exists} 等于 1
      设 out.error = 系列「{series}」已经有了。要换掉它就勾上「覆盖已有系列」，不然换个代号
      返回 {out} 400
    结束
    如果 {has_dir} 等于 是
      设 out.error = content/series/{series}/ 已经有课文文件了。要换掉它就勾上「覆盖已有系列」，不然换个代号
      返回 {out} 400
    结束
  结束

  # 存文件：类型白名单（扩展名 + 文件头）、20MB 上限。不合格回「[…]」开头的一句
  设 info = 上传信息 document
  设 saved = 存文件 document uploads 哈希 pdf,docx,md,txt 20MB
  设 saved_head = 截取 {saved} 1 1
  如果 {saved_head} 等于 [
    设 out.error = 文件没收下：{saved}
    返回 {out} 400
  结束

  设 doc = 读文档 {saved}
  设 doc_error = {doc.error 或}
  设 error_head = 截取 {doc_error} 1 1
  # 读不了、切不出、块太多：不建任务，刚存的文件也删掉（不留没人认领的文件）
  如果 {error_head} 不为空
    设 removed = 删文件 {saved}
    设 out.error = {doc_error}
    返回 {out} 400
  结束
  设 chunks = 切章节 {doc.text} 6000
  设 chunk_n = 条数 {chunks}
  如果 {chunk_n} 等于 0
    设 removed = 删文件 {saved}
    返回 {"error":"文件里没取出文字，换一个文件试试"} 400
  结束
  # 一块一次模型调用（平衡档），太多了先拦下，别一下子把额度用光
  如果 {chunk_n} 大于 80
    设 removed = 删文件 {saved}
    设 out.error = 切出的块太多：{chunk_n} 块，一次最多 80 块。把教材拆成几个文件分别导入
    返回 {out} 400
  结束

  设 job_row.series = {series}
  设 job_row.label = {label}
  设 job_row.source = {source 或}
  设 job_row.license = {license 或}
  设 job_row.prefix = {prefix}
  设 job_row.level_hint = {lesson_level 或 全部}
  设 job_row.rewrite = {rewrite 或 0}
  设 job_row.overwrite = {overwrite_on}
  设 job_row.document = {saved}
  设 job_row.file_name = {info.name 或}
  设 job_row.doc_kind = {doc.kind}
  设 job_row.pages = {doc.pages}
  设 job_row.paragraphs = {doc.paragraphs}
  设 job_row.chars = {doc.chars}
  事务 app.db
    设 affected = 写库表 app.db import_job_insert {job_row}
    设 job_id = 查一值 app.db import_last_id
    遍历 chunk 于 {chunks}
      设 chunk_row.job = {job_id}
      设 chunk_row.seq = {chunk.seq}
      设 chunk_row.title = {chunk.title}
      设 chunk_row.body = {chunk.text}
      设 affected = 写库表 app.db import_chunk_insert {chunk_row}
    结束
  结束

  # 每块交给后台：同时跑几块由引擎的后台线程池管（默认 2），出错的块由
  # import_chunk_fail.zs 记下原因
  设 id_args.job = {job_id}
  设 chunk_ids = 查询表 app.db import_chunk_ids {id_args}
  遍历 one_chunk 于 {chunk_ids}
    后台执行 scripts/import_chunk.zs chunk={one_chunk.chunk} on_error=scripts/import_chunk_fail.zs
  结束

  设 out.go = #教材导入?job={job_id}
  设 out.job = {job_id}
  返回 {out}
结束


# 「载入」：按地址参数拉回审阅页 / 编辑页 / 系列页。
接口 POST /import/load 动作 import_load
  用包 db http common data

  设 job = {job 或}
  设 draft = {draft 或}
  设 manage = {manage 或}
  如果 {job} 不为空
    执行 scripts/import_job_view.zs job={job}
  结束
  如果 {draft} 不为空
    执行 scripts/import_draft_view.zs draft={draft} with_form=是
  结束
  如果 {manage} 不为空
    设 one_args.series = {manage}
    设 series_row = 查一行表 app.db import_series_one {one_args}
    如果 {series_row.code 或} 为空
      设 missing.code = {manage}
      设 missing.head = 没有这个系列（{manage}）。
      设 missing.can_withdraw = 0
      设 missing.back = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5
      设 state.series_view = {missing}
    否则
      设 state.series_view = {series_row}
    结束
    响应 state {state}
  结束
结束


# 审阅页轮询（「每隔 2」，还有块在解析时）：进度、块表、草稿课表。
接口 POST /import/poll 动作 import_poll
  用包 db http common data

  设 job = {job 或}
  如果 {job} 不为空
    执行 scripts/import_job_view.zs job={job}
  结束
结束


# 重试一块（块表行上的「重试」，带 chunk_id）：回到待解析，再交给后台。
接口 POST /import/chunk_retry 动作 import_chunk_retry
  用包 db http common data

  设 chunk_id = {chunk_id 或}
  如果 {chunk_id} 为空
    返回 {"error":"缺 chunk_id（重试哪一块）"} 400
  结束
  设 args.chunk_id = {chunk_id}
  设 job = 查一值表 app.db import_chunk_job {args}
  如果 {job} 为空
    返回 {"error":"没有这一块"} 404
  结束
  设 affected = 写库表 app.db import_chunk_retry {args}
  如果 {affected} 等于 1
    后台执行 scripts/import_chunk.zs chunk={chunk_id} on_error=scripts/import_chunk_fail.zs
  结束
  执行 scripts/import_job_view.zs job={job}
结束


# 一课草稿通过 / 驳回 / 回到待审。审阅页的行上带 draft（地址里有 job，回刷审阅
# 页）；编辑页地址里是 draft（回刷编辑页）。
接口 POST /import/draft_pass 动作 import_draft_pass
  用包 db http common data
  设 draft = {draft 或}
  # 空值不能当脚本参数传（「job= review=…」会把后面整段吞进 job），没有就传 -
  设 job = {job 或 -}
  执行 scripts/import_draft_review.zs draft={draft} job={job} review=通过
结束

接口 POST /import/draft_reject 动作 import_draft_reject
  用包 db http common data
  设 draft = {draft 或}
  # 空值不能当脚本参数传（「job= review=…」会把后面整段吞进 job），没有就传 -
  设 job = {job 或 -}
  执行 scripts/import_draft_review.zs draft={draft} job={job} review=驳回
结束


# 「全部通过有映射的课」：还待审、映射到了至少一个条目或知识点的课一律通过。
# 孤课、驳回过的不动。
接口 POST /import/pass_mapped 动作 import_pass_mapped
  用包 db http common data

  设 job = {job 或}
  如果 {job} 为空
    返回 {"error":"缺 job（哪个导入任务）"} 400
  结束
  设 args.job = {job}
  设 passed_n = 写库表 app.db import_pass_mapped {args}
  设 affected = 写库表 app.db import_issues {args}
  执行 scripts/import_job_view.zs job={job}
  设 note.job_note = 通过了：{passed_n} 课（有映射、还待审的）。
  响应 state {note}
结束


# 编辑页「保存」：改字段。例句要是 JSON 数组（[{"jp":…,"zh":…}]）。
接口 POST /import/draft_save 动作 import_draft_save
  用包 db http common data

  设 draft = {draft 或}
  如果 {draft} 为空
    返回 {"error":"缺 draft（改哪一课）"} 400
  结束
  设 ex_args.examples = {examples 或}
  设 examples_ok = 查一值表 app.db import_examples_ok {ex_args}
  如果 {examples_ok} 不等于 1
    返回 {"error":"例句要写成 JSON 数组，每句一个对象：[{\"jp\": \"日语\", \"zh\": \"中文\"}]"} 400
  结束
  设 affected = 写库表 app.db import_draft_save {request}
  设 job_args.draft = {draft}
  设 job = 查一值表 app.db import_draft_job {job_args}
  如果 {job} 为空
    返回 {"error":"没有这一课草稿"} 404
  结束
  设 issue_args.job = {job}
  设 affected = 写库表 app.db import_issues {issue_args}
  执行 scripts/import_draft_view.zs draft={draft} with_form=是
  设 note.draft_note = 保存了。
  响应 state {note}
结束


# 编辑页「加映射」：从下拉里选（map_add），或者直接输入编号（map_typed，优先）。
# 只能挑库里已有的条目、知识点。
接口 POST /import/map_add 动作 import_map_add
  用包 db http common data

  设 draft = {draft 或}
  设 code = {map_typed 或}
  如果 {code} 为空
    设 code = {map_add 或}
  结束
  如果 {draft} 为空
    返回 {"error":"缺 draft（给哪一课加）"} 400
  结束
  如果 {code} 为空
    返回 {"error":"从下拉里选一个条目或知识点，或者输入编号"} 400
  结束
  设 kind_args.code = {code}
  设 kind = 查一值表 app.db import_code_kind {kind_args}
  如果 {kind} 为空
    设 out.error = 库里没有编号「{code}」。只能挑已有的条目、知识点（不新建）
    返回 {out} 400
  结束
  设 add.draft = {draft}
  设 add.code = {code}
  设 add.kind = {kind}
  设 affected = 写库表 app.db import_map_add {add}
  设 job = 查一值表 app.db import_draft_job {add}
  设 issue_args.job = {job}
  设 affected = 写库表 app.db import_issues {issue_args}
  执行 scripts/import_draft_view.zs draft={draft} with_form=否
结束


# 编辑页映射表行上的「去掉」（带 map_code）。
接口 POST /import/map_remove 动作 import_map_remove
  用包 db http common data

  设 draft = {draft 或}
  设 map_code = {map_code 或}
  如果 {draft} 为空
    返回 {"error":"缺 draft"} 400
  结束
  设 rm.draft = {draft}
  设 rm.map_code = {map_code}
  设 affected = 写库表 app.db import_map_remove {rm}
  设 job = 查一值表 app.db import_draft_job {rm}
  设 issue_args.job = {job}
  设 affected = 写库表 app.db import_issues {issue_args}
  执行 scripts/import_draft_view.zs draft={draft} with_form=否
结束


# 确认导入：通过的课 → content/series/<code>/lessons.jsonl（格式见
# content/series/README.md），系列 → content/series.jsonl（按编号 upsert），然后
# 按系列导入（scripts/lesson_import.zs：只清空重灌这个系列，别的系列、学习记录
# 一行不动；引用了库里没有的编号整行拒收，进报告）。
#
# 系列已经有了、又没勾「覆盖已有系列」的拦下——除非就是这个任务上次导进去的
# （审阅后再导一次是常事）。hanabira 永远不让覆盖。
接口 POST /import/confirm 动作 import_confirm
  用包 common db http data text

  设 job = {job 或}
  如果 {job} 为空
    返回 {"error":"缺 job（导入哪个任务）"} 400
  结束
  设 args.job = {job}
  设 job_row = 查一行表 app.db import_job_one {args}
  如果 {job_row.id 或} 为空
    返回 {"error":"没有这个导入任务"} 404
  结束
  如果 {job_row.running} 等于 1
    返回 {"error":"还有块在解析，等解析完再导入"} 400
  结束
  设 series = {job_row.series}
  如果 {series} 等于 hanabira
    返回 {"error":"hanabira 是主教材，不能用导入覆盖它"} 400
  结束
  设 check_args.series = {series}
  设 check_args.prefix = {job_row.prefix}
  设 check = 查一行表 app.db import_series_check {check_args}
  如果 {check.code_ok} 不等于 1
    返回 {"error":"系列代号不合格"} 400
  结束
  设 has_dir = 存在 content/series/{series}/lessons.jsonl
  如果 {job_row.overwrite} 不等于 1
    如果 {job_row.imported} 为空
      如果 {check.series_exists} 等于 1
        设 out.error = 系列「{series}」已经有了，这个任务没勾「覆盖已有系列」。删掉任务重新导入时勾上它
        返回 {out} 400
      结束
      如果 {has_dir} 等于 是
        设 out.error = content/series/{series}/ 已经有课文文件了，这个任务没勾「覆盖已有系列」
        返回 {out} 400
      结束
    结束
  结束
  如果 {check.prefix_taken} 大于 0
    设 out.error = 课号前缀「{job_row.prefix}」已经被别的系列用了，导入会撞编号
    返回 {out} 400
  结束

  设 rows = 查询表 app.db import_lesson_export {args}
  设 row_n = 条数 {rows}
  如果 {row_n} 等于 0
    返回 {"error":"还没有通过的课。先在草稿课表里通过几课（或者「全部通过有映射的课」）"} 400
  结束

  # 课文文件：items / points 在库里是 JSON 文本，解析回数组再写
  设 lesson_rows = 解析JSON []
  遍历 row 于 {rows}
    设 out_row.code = {row.code}
    设 out_row.series = {row.series}
    设 out_row.level = {row.level}
    设 out_row.seq = {row.seq}
    设 out_row.title = {row.title}
    设 out_row.summary = {row.summary}
    设 out_row.explanation = {row.explanation}
    设 out_row.formation = {row.formation}
    设 out_row.examples = {row.examples}
    设 out_row.items = 解析JSON {row.items}
    设 out_row.points = 解析JSON {row.points}
    设 lesson_rows = 列表加项 {lesson_rows} {out_row}
  结束
  设 written = 写JSONL content/series/{series}/lessons.jsonl {lesson_rows}

  # 系列种子：按编号 upsert。原来就有、没撤下的保留它的排序，新的（或撤下过的）排 1
  设 series_rows = 解析JSON []
  设 has_series_file = 存在 content/series.jsonl
  如果 {has_series_file} 等于 是
    读JSONL series_rows = content/series.jsonl
  结束
  设 kept = 解析JSON []
  设 sort = 1
  遍历 one_series 于 {series_rows}
    设 same = 相等 {one_series.code} {series}
    如果 {same} 等于 是
      设 old_sort = {one_series.sort 或 0}
      如果 {old_sort} 不小于 0
        设 sort = {old_sort}
      结束
    否则
      设 kept = 列表加项 {kept} {one_series}
    结束
  结束
  设 seed.code = {series}
  设 seed.label = {job_row.label}
  设 seed.description = 从「教材导入」上传的教材解析而来（{job_row.file_name}），讲解和例句已改写。
  如果 {job_row.rewrite} 不等于 1
    设 seed.description = 从「教材导入」上传的教材解析而来（{job_row.file_name}）。
  结束
  设 seed.source = {job_row.source}
  设 seed.license = {job_row.license}
  # 文件里 sort 要是数字，不是 "1"
  设 seed.sort = 转数字 {sort}
  设 kept = 列表加项 {kept} {seed}
  设 written = 写JSONL content/series.jsonl {kept}

  设 report = 执行 scripts/lesson_import.zs series={series}
  设 status = {report.status 或 200}
  如果 {status} 不等于 200
    设 out.error = 导入失败：{report.error}
    返回 {out} 400
  结束
  设 mark.job = {job}
  设 mark.report = {report}
  设 affected = 写库表 app.db import_job_imported {mark}
  执行 scripts/import_job_view.zs job={job}
结束


# 删除一个导入任务（审阅页「删除这个任务」，浮层里再确认一次）：只删草稿。
接口 POST /import/job_delete 动作 import_job_delete
  用包 db http

  设 job = {job 或}
  如果 {job} 为空
    返回 {"error":"缺 job（删哪个任务）"} 400
  结束
  设 args.job = {job}
  事务 app.db
    设 affected = 写库表 app.db import_job_delete {args}
    设 affected = 写库表 app.db import_job_delete_chunks {args}
    设 affected = 写库表 app.db import_job_delete_job {args}
  结束
  返回 {"go":"#教材导入"}
结束


# 撤下一个已导入的系列（系列页「撤下这个系列」，浮层里再确认一次）：
#   库里：这个系列的 item_lesson、lesson_point、lesson 清空，series.sort = -1
#   文件：content/series.jsonl 里这一行 sort 改成 -1；lessons.jsonl 挪成
#         lessons.withdrawn.jsonl（留着，重新上架时不用再解析），原处写空——
#         否则下次 py -m kg 启动导入时课又回来了
# 学习记录、学习者的偏好一行不动：选过这个系列的学习者回到 hanabira
# （series_current 只认 sort ≥ 0 的）。hanabira 不能撤。
接口 POST /import/series_withdraw 动作 import_series_withdraw
  用包 common db http data text

  设 series = {manage 或}
  如果 {series} 为空
    返回 {"error":"缺 manage（撤下哪个系列）"} 400
  结束
  如果 {series} 等于 hanabira
    返回 {"error":"hanabira 是主教材，不能撤下"} 400
  结束
  设 code_args.series = {series}
  设 code_ok = 查一值表 app.db series_code_ok {code_args}
  如果 {code_ok} 不等于 1
    返回 {"error":"系列编号不对"} 400
  结束
  设 series_row = 查一行表 app.db import_series_one {code_args}
  如果 {series_row.code 或} 为空
    返回 {"error":"没有这个系列"} 404
  结束

  事务 app.db
    设 affected = 写库表 app.db item_lesson_clear {code_args}
    设 affected = 写库表 app.db lesson_point_clear {code_args}
    设 removed = 写库表 app.db lesson_clear {code_args}
    设 affected = 写库表 app.db import_series_hide {code_args}
  结束

  设 series_rows = 解析JSON []
  设 has_series_file = 存在 content/series.jsonl
  如果 {has_series_file} 等于 是
    读JSONL series_rows = content/series.jsonl
  结束
  设 kept = 解析JSON []
  设 found = 否
  遍历 one_series 于 {series_rows}
    设 same = 相等 {one_series.code} {series}
    如果 {same} 等于 是
      设 one_series.sort = 转数字 -1
      设 found = 是
    结束
    设 kept = 列表加项 {kept} {one_series}
  结束
  如果 {found} 等于 否
    设 seed.code = {series}
    设 seed.label = {series_row.label}
    设 seed.sort = 转数字 -1
    设 kept = 列表加项 {kept} {seed}
  结束
  设 written = 写JSONL content/series.jsonl {kept}

  设 lessons_file = content/series/{series}/lessons.jsonl
  设 has_lessons = 存在 {lessons_file}
  如果 {has_lessons} 等于 是
    读JSONL old_lessons = {lessons_file}
    设 old_n = 条数 {old_lessons}
    如果 {old_n} 大于 0
      设 written = 写JSONL content/series/{series}/lessons.withdrawn.jsonl {old_lessons}
    结束
    设 empty = 解析JSON []
    设 written = 写JSONL {lessons_file} {empty}
  结束

  设 one_args.series = {series}
  设 after = 查一行表 app.db import_series_one {one_args}
  设 after.note = 撤下了：库里删掉 {removed} 课（连同映射），教材页的下拉里不再有它。课文文件留在 content/series/{series}/lessons.withdrawn.jsonl。
  设 state.series_view = {after}
  响应 state {state}
  执行 scripts/import_home_view.zs
结束
