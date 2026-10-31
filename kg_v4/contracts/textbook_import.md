模块 textbook_import
依赖 kg lesson subject

## 表
表 textbook_import_task
  series_code 文本 目标系列代号
  series_name 文本 系列显示名
  source 文本 来源，可空
  license 文本 授权，可空
  code_prefix 文本 课号前缀，可空
  file_name 文本 原文件名，可空
  raw_text 长文本 从文件取出的纯文本（同一文件重复上传靠它全局判重）
  status 文本 处理中 / 待审阅 / 已导入 / 已撤下 / 失败
  fail_reason 文本 失败原因，可空
  report 长文本 确认导入后的导入报告（JSON 文本），可空
  display_title 文本 页面显示标题（系列显示名-原文件名，没有文件名时只取系列显示名），可空
  created_at 文本 建于时间
  lesson_level 文本 等级范围（全部 或 N5 到 N1；给模型的候选条目按等级预筛），可空，空按全部
  rewrite 整数 是否让模型改写讲解和例句（1/0），可空，空按 1（默认改写）
  overwrite 整数 是否允许覆盖已有系列（1/0），可空，空按 0
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 textbook_import_chunk
  task_id 整数 所属任务 id
  seq 整数 块序号，从 1 起
  title 文本 块标题（块的第一行截前 50 字），可空
  content 长文本 块文本
  status 文本 待处理 / 处理中 / 完成 / 失败
  fail_reason 文本 失败原因，可空
  retry_count 整数 重试次数，默认 0
表 textbook_import_draft
  task_id 整数 所属任务 id
  chunk_id 整数 来源块 id
  code 文本 课号（课号前缀 + 序号）
  level 文本 等级 N5/N4/N3/N2/N1
  title 文本 标题
  summary 长文本 一句话，可空
  explain 长文本 讲解，可空
  connection 长文本 接续，可空
  examples 长文本 例句，可空
  examples_edited 整数 是否改过例句（1/0）
  orig_title 文本 原标题，可空
  seq 整数 课序
  item_codes 文本 映射的条目编号，英文逗号连接，可空
  point_codes 文本 映射的知识点编号，英文逗号连接，可空
  status 文本 待审 / 通过 / 驳回
  display_title 文本 页面显示标题（课号-标题），可空
  confidence 整数 模型自评的映射把握（0 到 100 的百分数），可空（模型没给或看不懂）
  dropped_codes 文本 模型给了但库里没有、被丢掉的编号，写成「条目 x、y；知识点 z」，可空
  reason 文本 模型说的为什么这样映射，可空

## 页面字段
页面 import_view 教材导入页面
  prefix 文本 课号前缀
  rewrite 布尔 改写讲解和例句（开关）
  overwrite 布尔 覆盖已有系列（开关）
  document 文件 教材文件
  job_state 文本 任务表「进度」列
  created 文本 任务表「时间」列
  lesson_n 整数 系列表「课数」列
  series_state 文本 系列表「状态」列
  reason 文本 模型的理由
  draft_level 枚举 N5,N4,N3,N2,N1 草稿课等级
  mapping 文本 草稿课表「映射」列
  issues 文本 问题
  confidence 文本 把握
  review 文本 审阅
  chunk_status 文本 块表「状态」列
  error 文本 块表「说明」列
  tries 整数 块表「次数」列
  formation 文本 接续
  explanation 文本 讲解
  map_kind 文本 映射表「种类」列
  map_code 文本 映射表「编号」列
  map_label 文本 映射表「名称」列
  map_add 文本 从已有的选
  map_typed 文本 或者输入编号

## 函数
公开 函数 新建导入 series_code series_name code_prefix file_path source? license? file_name? file_size? file_ext? lesson_level? rewrite? overwrite? learner? current_role? auth_mode? subject?
  返回 {ok, task_id, duplicate, chunk_count}；duplicate 为 1 表示库里已有内容完全相同的任务（不分系列），直接返回那一个，不再新存
  报错 400 series_code 不能为空
  报错 400 series_name 不能为空
  报错 400 code_prefix 不能为空
  报错 400 系列代号只能用小写字母开头，后面是小写字母、数字、下划线、连字符，不超过 40 个字
  报错 400 hanabira 是主教材，不能用导入覆盖它
  报错 400 课号前缀只能用小写字母开头，后面是小写字母、数字，不超过 20 个字
  报错 400 课号前缀已经被别的系列用了，换一个
  报错 400 编号要以「<编码>.」开头
  报错 400 等级范围只能是全部或 N5 到 N1
  报错 400 系列已经有了，要覆盖就勾上覆盖已有系列，不然换个代号
  报错 400 只收 pdf docx md txt 文件
  报错 400 文件不能超过 20MB
  报错 400 文件没有可读文本
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  报错 403 本科目没开教材导入
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 科目门控（K161 D3：本轮教材导入只给日语科目，仍按 N5–N1 校验等级；非日语科目关掉入口，免得往没有课文等级口径的科目里写进 N5–N1 的课）：解析出 subject_id 之后、其它校验之前判断——subject_id 等于 1 直接放行；否则按 subject_id 查 subject_info 的 caps（查询 textbook_import_subject_caps），解析成 JSON 后 textbook_import 键不等于 1（含查不到行、caps 不是 JSON、没有这个键），报错 403 本科目没开教材导入，不读文件、不建任务
  伪代码 series_code 为空，报错 400 series_code 不能为空；series_name 为空，报错 400 series_name 不能为空；code_prefix 为空，报错 400 code_prefix 不能为空
  伪代码 开关（旧 kg 口径）：series_code 不符合 ^[a-z][a-z0-9_-]{0,39}$ 报错 400 系列代号只能用小写字母开头…；series_code 等于 hanabira 报错 400 hanabira 是主教材，不能用导入覆盖它；lesson_level 不为空且不是 全部 N5 N4 N3 N2 N1 之一，报错 400 等级范围只能是全部或 N5 到 N1
  伪代码 课号前缀（旧 kg：queries/import_series_check.sql 第 12-13、16-18 行，routes/textbook_import.zs 第 81-86 行；建任务时就拦，不等到确认导入）：本科目 subject_id 等于 1（日语）时 code_prefix 不符合 ^[a-z][a-z0-9]{0,19}$（小写字母开头，只有小写字母、数字，不超过 20 个字），报错 400 课号前缀只能用小写字母开头，后面是小写字母、数字，不超过 20 个字（旧 kg 原文）；别的系列已经占着这个前缀，报错 400 课号前缀已经被别的系列用了，换一个（v4 报错行不带变量，不用旧 kg 带系列课数的那句）。「占着」＝ lesson_text 里有一行 series_code 不等于本任务的 series_code，且 code 以「前缀-」开头（旧 kg 的课号形态 前缀-三位序号）或 code 等于「前缀 + 纯数字」（v4 草稿课的课号形态 code_prefix 加序号）；用查询 textbook_import_prefix_taken 直读 lesson_text 数行数。本系列自己的课不算占着（覆盖重导自己的系列不会被拦）；前缀只是另一个前缀的开头（如 mnn 与 mnnx01）不算。这两条在 hanabira 检查之后、等级范围和覆盖开关之前判。非日语科目（subject_id 不等于 1）的 code_prefix 不套上面的旧正则，改为符合口径 2：调用本模块 编号前缀检查 subject_id=subject_id code=code_prefix 加 "1"（用 v4 草稿课号形态「前缀加序号」的样例课号检查），要求 code_prefix 以「<科目编码>.」开头（如 math.，之后可再跟字母数字下划线连字符），不符报错 400 编号要以「<编码>.」开头（草稿课号 code_prefix 加序号因此都带科目前缀，确认导入时 lesson 再按课号逐个复核）；「别的系列占着前缀」的检查对所有科目照旧（课号全局唯一，查询不限科目）
  伪代码 覆盖开关：overwrite 不等于 1 时，lesson_series 里已有 code 等于 series_code 的行（系列编号全局唯一，不限科目；overwrite 等于 1 但该系列属于别的科目，确认导入时 lesson 报 400 系列编号已被其他科目使用）（含已撤下的 sort_order 小于 0 的），或 lesson_text 里已有 series_code 等于它的课，报错 400 系列已经有了，要覆盖就勾上覆盖已有系列，不然换个代号（用查询 textbook_import_series_exists 直读 lesson 的两张表）；overwrite 等于 1 不查
  伪代码 file_ext 不为空时，去掉开头的点并转小写后不是 pdf docx md txt 之一，报错 400 只收 pdf docx md txt 文件
  伪代码 file_size 不为空时，数值大于 20971520（20MB），报错 400 文件不能超过 20MB
  伪代码 用 doc 包「读文档」读 file_path 取纯文本 text；text 去掉空白后为空，报错 400 文件没有可读文本
  伪代码 查 textbook_import_task 中 raw_text 等于 text 且 subject_id 等于本科目的行（不限系列；别的科目的任务不算重复，查不到就新建，也不会把别的科目的任务返回出来），有则返回 {"ok": 1, "task_id": 该行 id, "duplicate": 1, "chunk_count": 该任务块数}（同一文件传两次只存一份）
  伪代码 切块：按行拆开；以 # 开头的行，或以「第」开头且含「课」的行，开始一个新块；第一个标题之前若有非空内容自成一块；全文没有任何标题行时，每 2000 个字符切一块；块标题取块首行前 50 字，块序号从 1 起
  伪代码 在一个事务里：往 textbook_import_task 插入 (series_code, series_name, source, license, code_prefix, file_name, raw_text=text, status=处理中, display_title=series_name 加 "-" 加 file_name（file_name 为空时只取 series_name）, created_at=当前时间, lesson_level=lesson_level 为空取「全部」, rewrite=rewrite 等于 0 取 0 否则取 1, overwrite=overwrite 等于 1 取 1 否则取 0, subject_id=本科目 subject_id)；每块往 textbook_import_chunk 插入 (task_id, seq, title, content, status=待处理, retry_count=0)
  伪代码 事务结束之后：后台执行 scripts/textbook_import_run.zs task_id=<任务id>（脚本只传 task_id，后台处理的科目以任务行 subject_id 为准）on_error=scripts/textbook_import_run_fail.zs
  伪代码 返回 {"ok": 1, "task_id": 任务id, "duplicate": 0, "chunk_count": 块数}

公开 函数 处理任务 task_id learner? current_role? auth_mode? subject?
  返回 {ok, task_id, chunk_total, failed}；failed 是本次处理后失败的块数
  报错 404 没有这个任务
  伪代码 科目：本函数是后台处理（脚本只传 task_id，不经路由），不调用 本科目、不校验权限；learner、current_role、auth_mode、subject 只为签名统一，不参与处理；科目以任务行的 subject_id 为准（按 task_id 查任务，不按入参 subject 过滤，不传 subject 也能处理任何科目的任务），记为 subject_id；任务、块、草稿的读写都以这个 subject_id 为准；本函数在本模块内调用其它函数、调用 kg./lesson. 的函数时一律带 subject=subject_id
  伪代码 按 task_id 查 textbook_import_task（不按科目过滤），查不到报错 404 没有这个任务；取任务行的 subject_id
  伪代码 查该任务 status=待处理 的块，按 seq 升序，逐块调用本模块 处理块 chunk_id=该块 id subject=subject_id（单块失败只记在块上，不中断）
  伪代码 全部块处理完后，把任务 status 改为 待审阅
  伪代码 统计该任务 status=失败 的块数 failed
  伪代码 返回 {"ok": 1, "task_id": task_id, "chunk_total": 块总数, "failed": failed}

公开 函数 处理块 chunk_id learner? current_role? auth_mode? subject?
  返回 {ok, chunk_id, status, draft_count}；status 是处理后块的状态（完成 或 失败）
  报错 404 没有这个块
  伪代码 科目：本函数是后台处理（脚本只传 task_id，不经路由），不调用 本科目、不校验权限；learner、current_role、auth_mode、subject 只为签名统一，不参与处理；科目以任务行的 subject_id 为准（按 task_id 查任务，不按入参 subject 过滤，不传 subject 也能处理任何科目的任务），记为 subject_id；任务、块、草稿的读写都以这个 subject_id 为准；本函数在本模块内调用其它函数、调用 kg./lesson. 的函数时一律带 subject=subject_id
  伪代码 按 chunk_id 查 textbook_import_chunk，查不到报错 404 没有这个块；再取所属任务（取课号前缀 code_prefix 和任务行的 subject_id）
  伪代码 把块 status 改为 处理中
  伪代码 调用本模块 块提示词 chunk_id=chunk_id subject=subject_id，取它的 prompt（候选条目、知识点和「改写」「等级范围」两个开关都在里面，提示词只此一份）
  伪代码 问JSON（调模型）：问题就是 prompt，要求抽出本块里的课，返回 {"lessons": [{"title", "level", "summary", "explain", "connection", "examples", "orig_title", "item_codes": [编号], "point_codes": [编号], "confidence", "reason"}]}，编号只能从候选里选，不许新造；调模型出错或返回里没有 lessons 列表，把块 status 改为 失败、fail_reason 写出错原因，返回 {"ok": 1, "chunk_id": chunk_id, "status": "失败", "draft_count": 0}
  伪代码 对每个模型给的编号核对：item_codes 里每个编号调用 kg.取条目 code=编号 subject=subject_id，point_codes 里每个编号调用 kg.取知识点 code=编号 subject=subject_id，取不到（包括属于别的科目）的编号丢弃（映射只引用已有的，绝不新建），其余保留；level 转大写。丢掉的编号记下来（旧 kg import_lesson_check.sql 第 19-35 行）：条目一段「条目 x、y」，知识点一段「知识点 z」，各段内去重、保持模型给的先后，没丢的那段不写，两段都有用「；」连起来，都没丢为空（dropped_codes）
  伪代码 把握 confidence（旧 kg import_lesson_insert.sql 第 30、46-49 行）：模型给的数 c，大于 0 且不大于 1 的当 0 到 1 的小数，乘 100 四舍五入成整数；大于 1 的当百分数，四舍五入、最大 100；其他（没给、0、负数、不是数字）存空。reason 去首尾空白，空的存空
  伪代码 在一个事务里：先删除该块已有的草稿课（重试时覆盖）；逐课插入 textbook_import_draft (task_id, chunk_id, code=code_prefix + 该任务草稿课总数加 1 的序号, level, title, summary, explain, connection, examples, examples_edited=0, orig_title, seq=该序号, item_codes 逗号连接, point_codes 逗号连接, status=待审, display_title=code 加 "-" 加 title, confidence, dropped_codes, reason)；块 status 改为 完成、fail_reason 置空
  伪代码 返回 {"ok": 1, "chunk_id": chunk_id, "status": "完成", "draft_count": 插入的课数}

公开 函数 标记任务失败 task_id error learner? current_role? auth_mode? subject?
  返回 {ok}
  报错 404 没有这个任务
  伪代码 科目：本函数是后台处理（脚本只传 task_id，不经路由），不调用 本科目、不校验权限；learner、current_role、auth_mode、subject 只为签名统一，不参与处理；科目以任务行的 subject_id 为准（按 task_id 查任务，不按入参 subject 过滤，不传 subject 也能处理任何科目的任务），记为 subject_id；任务、块、草稿的读写都以这个 subject_id 为准；本函数在本模块内调用其它函数、调用 kg./lesson. 的函数时一律带 subject=subject_id
  伪代码 按 task_id 查 textbook_import_task（不按科目过滤），查不到报错 404 没有这个任务
  伪代码 把任务 status 改为 失败，fail_reason 写 error
  伪代码 返回 {"ok": 1}

公开 函数 重试块 chunk_id learner? current_role? auth_mode? subject?
  返回 {ok, chunk_id, task_id, status}；status 是提交后块的状态（待处理，后台处理，前端通过 取任务 轮询进度）
  报错 404 没有这个块
  报错 400 只有失败的块可以重试
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 chunk_id 查 textbook_import_chunk 并连所属任务，查不到或所属任务的 subject_id 不等于本科目（包括属于别的科目），报错 404 没有这个块
  伪代码 块 status 不等于 失败，报错 400 只有失败的块可以重试
  伪代码 在一个事务里：块 status 改为 待处理、fail_reason 置空、retry_count 加 1；所属任务 status 改为 处理中
  伪代码 事务结束之后：后台执行 scripts/textbook_import_run.zs task_id=<所属任务id> on_error=scripts/textbook_import_run_fail.zs（脚本只处理该任务里待处理的块，处理完任务回到待审阅）
  伪代码 返回 {"ok": 1, "chunk_id": chunk_id, "task_id": 所属任务id, "status": "待处理"}

公开 函数 列任务 learner? current_role? auth_mode? subject?
  返回 {total, tasks}，tasks 是 [{task_id, series_code, series_name, display_title, status, chunk_total, pending_count, draft_total, created_at}]，按 id 倒序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 查 textbook_import_task 中 subject_id 等于本科目的行（别的科目的任务不出现），按 id 倒序
  伪代码 每行统计其块数 chunk_total、status 为 待处理 或 处理中 的块数 pending_count、草稿课数 draft_total
  伪代码 返回 {"total": 行数, "tasks": 列表}

公开 函数 取任务 task_id learner? current_role? auth_mode? subject?
  返回 {task_id, series_code, series_name, source, license, code_prefix, file_name, display_title, status, fail_reason, report, created_at, chunk_total, chunk_pending, chunk_done, chunk_failed, chunks, drafts}；chunks 是 [{id, seq, title, status, fail_reason, retry_count}] 按 seq 升序；drafts 是 [{id, code, display_title, title, level, seq, status, item_count, point_count}] 按 seq 升序、id 升序
  报错 404 没有这个任务
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 task_id 和本科目 subject_id 查 textbook_import_task，查不到（包括属于别的科目）报错 404 没有这个任务
  伪代码 查该任务的块和草稿课；chunk_pending 是 status 为 待处理 或 处理中 的块数，chunk_done 是 status=完成 的块数，chunk_failed 是 status=失败 的块数；item_count、point_count 是对应编号列表里的个数
  伪代码 返回上述结构（不返回 raw_text）

公开 函数 取草稿课 draft_id learner? current_role? auth_mode? subject?
  返回 {id, task_id, chunk_id, code, display_title, level, title, summary, explain, connection, examples, examples_edited, orig_title, seq, item_codes, point_codes, status, confidence, dropped_codes, reason}；confidence 是 0 到 100 的整数，没有为空串，dropped_codes、reason 没有为空串
  报错 404 没有这个草稿课
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 draft_id 查 textbook_import_draft 并连所属任务，查不到或所属任务的 subject_id 不等于本科目（包括属于别的科目），报错 404 没有这个草稿课
  伪代码 返回该行各字段

公开 函数 修改草稿课 draft_id title level summary explain connection examples seq learner? current_role? auth_mode? subject?
  返回 {ok, draft_id}
  报错 404 没有这个草稿课
  报错 400 已导入的课不能再改
  报错 400 草稿课字段有错
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 draft_id 查 textbook_import_draft 并连所属任务，查不到或所属任务的 subject_id 不等于本科目（包括属于别的科目），报错 404 没有这个草稿课
  伪代码 所属任务 status 等于 已导入，报错 400 已导入的课不能再改（其它状态都允许修改）
  伪代码 title 为空，或 level 不是 N5 N4 N3 N2 N1 之一，或 seq 不是整数，报错 400 草稿课字段有错
  伪代码 examples 与原 examples 不同时，examples_edited 置 1（已是 1 的保持 1）
  伪代码 更新该行 title、level、summary、explain、connection、examples、seq，display_title 重算为 code 加 "-" 加 title（课号 code 和 status 不改）
  伪代码 返回 {"ok": 1, "draft_id": draft_id}

公开 函数 改映射 draft_id kind action code learner? current_role? auth_mode? subject?
  返回 {ok, item_codes, point_codes}
  报错 404 没有这个草稿课
  报错 400 已导入的课不能再改
  报错 400 kind 只能是 item 或 point
  报错 400 action 只能是 add 或 remove
  报错 404 没有这个条目
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 draft_id 查 textbook_import_draft 并连所属任务，查不到或所属任务的 subject_id 不等于本科目（包括属于别的科目），报错 404 没有这个草稿课
  伪代码 所属任务 status 等于 已导入，报错 400 已导入的课不能再改
  伪代码 kind 不是 item 也不是 point，报错 400 kind 只能是 item 或 point；action 不是 add 也不是 remove，报错 400 action 只能是 add 或 remove
  伪代码 action 为 add：kind 为 item 时调用 kg.取条目 code=code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个条目；kind 为 point 时调用 kg.取知识点 code=code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个知识点（手动加的先查库，绝不新建）；编号不在对应列表时追加到末尾，已在则不重复
  伪代码 action 为 remove：从对应列表里去掉 code，不在列表里也不报错
  伪代码 更新该行 item_codes 或 point_codes（英文逗号连接）
  伪代码 返回 {"ok": 1, "item_codes": 新 item_codes, "point_codes": 新 point_codes}

公开 函数 审核草稿课 draft_id decision learner? current_role? auth_mode? subject?
  返回 {ok, draft_id, status}
  报错 404 没有这个草稿课
  报错 400 已导入的课不能再改
  报错 400 decision 只能是 approve 或 reject
  报错 400 草稿课字段有错
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 draft_id 查 textbook_import_draft 并连所属任务，查不到或所属任务的 subject_id 不等于本科目（包括属于别的科目），报错 404 没有这个草稿课
  伪代码 所属任务 status 等于 已导入，报错 400 已导入的课不能再改
  伪代码 decision 不是 approve 也不是 reject，报错 400 decision 只能是 approve 或 reject
  伪代码 decision 为 approve：title 为空或 level 不是 N5 N4 N3 N2 N1 之一，报错 400 草稿课字段有错；否则 status 改为 通过
  伪代码 decision 为 reject：status 改为 驳回
  伪代码 返回 {"ok": 1, "draft_id": draft_id, "status": 新 status}

公开 函数 一键通过 task_id learner? current_role? auth_mode? subject?
  返回 {ok, approved, skipped}；approved 是本次改为通过的课数，skipped 是仍待审但没通过的课数
  报错 404 没有这个任务
  报错 400 已导入的课不能再改
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 task_id 和本科目 subject_id 查 textbook_import_task，查不到（包括属于别的科目）报错 404 没有这个任务；status 等于 已导入，报错 400 已导入的课不能再改
  伪代码 把该任务 status=待审 且（item_codes 或 point_codes 不为空）且 title 不为空且 level 是 N5 N4 N3 N2 N1 之一的草稿课 status 改为 通过，数出 approved
  伪代码 skipped = 该任务仍为 待审 的草稿课数
  伪代码 返回 {"ok": 1, "approved": approved, "skipped": skipped}

公开 函数 确认导入 task_id learner? current_role? auth_mode? subject?
  返回 {ok, series_code, total, imported, rejected_count, rejected, item_links, point_links, file_rows}；total、imported、item_links、point_links、file_rows、rejected 取自 lesson.写入系列课文并重灌 的返回，rejected 是 [{code, reason}]，rejected_count 是 rejected 的个数
  报错 404 没有这个任务
  报错 400 已导入的课不能再改
  报错 400 没有通过的课
  报错 400 hanabira 是主教材，不能用导入覆盖它
  报错 400 系列已经有了，这个任务没勾覆盖已有系列
  报错 400 编号要以「<编码>.」开头
  报错 400 系列编号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 task_id 和本科目 subject_id 查 textbook_import_task，查不到（包括属于别的科目）报错 404 没有这个任务；status 等于 已导入，报错 400 已导入的课不能再改
  伪代码 任务 series_code 等于 hanabira，报错 400 hanabira 是主教材，不能用导入覆盖它；任务 overwrite 不等于 1（空按 0）且 lesson_series 或 lesson_text 里已有这个系列（查询 textbook_import_series_exists），报错 400 系列已经有了，这个任务没勾覆盖已有系列（旧 kg：覆盖要明确勾选）
  伪代码 取该任务 status=通过 的草稿课，按 seq 升序、id 升序；没有则报错 400 没有通过的课（课文和映射都写到当前科目：下面调 lesson 传 subject=subject_id，不会落到别的科目）
  伪代码 组成 rows_json（JSON 数组），每课 {code, level, title, summary, explain, connection, examples, examples_edited, orig_title, seq, item_codes: 编号数组, point_codes: 编号数组}（编号列表按英文逗号拆开，空则空数组）；examples 不直接用草稿里的 JSON 数组文本，调用 例句转教材格式 examples=草稿 examples，把结果写进去（lesson_text.examples 存的是教材页拆句用的「日语^^中文@@日语^^中文」格式）
  伪代码 调用 lesson.写入系列课文并重灌 series_code=任务 series_code rows_json=rows_json series_name=任务 series_name source=任务 source license=任务 license subject=subject_id 得 r（写内容文件、按系列清空重灌、拒收映射对不上的课都由 lesson 完成；每课课号 lesson 按口径 2 复核前缀——非日语科目要以「<科目编码>.」开头，日语 subject_id=1 豁免，不符 lesson 报 400 编号要以「<编码>.」开头，系列已属于别的科目报 400 系列编号已被其他科目使用；lesson 报的错原样向上抛，任务状态不变）
  伪代码 把任务 status 改为 已导入，report 写 r 的 JSON 文本
  伪代码 返回 {"ok": 1, "series_code": 任务 series_code, "total": r.total, "imported": r.imported, "rejected_count": r.rejected 的个数, "rejected": r.rejected, "item_links": r.item_links, "point_links": r.point_links, "file_rows": r.file_rows}

公开 函数 删除任务 task_id learner? current_role? auth_mode? subject?
  返回 {ok, task_id}
  报错 404 没有这个任务
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 task_id 和本科目 subject_id 查 textbook_import_task，查不到（包括属于别的科目）报错 404 没有这个任务
  伪代码 在一个事务里：删除该任务的 textbook_import_draft、textbook_import_chunk，再删除任务行（只删草稿，不调用 lesson，已导入的课不动）
  伪代码 返回 {"ok": 1, "task_id": task_id}

公开 函数 列已导入系列 series_code? learner? current_role? auth_mode? subject?
  返回 {total, series, lesson_total, lessons}；series 是 [{code, name, sort_order, lesson_count}]；series_code 不为空时 lessons 是该系列的课文 [{code, level, title, summary, series_code, seq}]，lesson_total 是其个数；为空时 lessons 为空列表、lesson_total 为 0
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 lesson.列系列 subject=subject_id 得系列列表（只含未撤下的系列）
  伪代码 每个系列调用 lesson.列课文 series_code=该系列编号 subject=subject_id，lesson_count 取返回的 total
  伪代码 series_code 不为空时，调用 lesson.列课文 series_code=series_code subject=subject_id，取其 lessons 和 total
  伪代码 返回 {"total": 系列数, "series": 列表, "lesson_total": 课数, "lessons": 课文列表}

公开 函数 撤下已导入系列 series_code learner? current_role? auth_mode? subject?
  返回 {ok, series_code, removed_lessons, moved}，removed_lessons、moved 取自 lesson.撤下系列 的返回
  报错 400 hanabira 是主教材，不能撤下
  报错 404 没有这个系列
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 series_code 等于 hanabira，报错 400 hanabira 是主教材，不能撤下
  伪代码 调用 lesson.撤下系列 series_code=series_code subject=subject_id 得 r（挪走内容文件、清课文及挂接、排序改 -1 都由 lesson 完成；没有这个系列、系列属于别的科目时 lesson 报 404 原样向上抛）
  伪代码 把 textbook_import_task 中 series_code 相等、subject_id 等于本科目且 status=已导入 的行 status 改为 已撤下
  伪代码 返回 {"ok": 1, "series_code": series_code, "removed_lessons": r.removed_lessons, "moved": r.moved}

公开 函数 块提示词 chunk_id learner? current_role? auth_mode? subject?
  返回 {chunk_id, rewrite, lesson_level, item_count, point_count, prompt}；prompt 是发给模型的完整提示词（处理块 用的就是这一份）；rewrite 是 1/0（任务里空按 1），lesson_level 空按「全部」，item_count、point_count 是给模型的候选条目、知识点个数
  报错 404 没有这个块
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 chunk_id 查 textbook_import_chunk 并连所属任务，查不到或所属任务的 subject_id 不等于本科目（包括属于别的科目），报错 404 没有这个块；再取所属任务（code_prefix、rewrite、lesson_level）
  伪代码 候选知识点：调用 kg.列知识点 subject=subject_id，总是全给（只含本科目）；候选条目：调用 kg.列条目 subject=subject_id 取本科目全部条目，lesson_level 是 N5 N4 N3 N2 N1 之一时只留这两类（旧 kg 口径：按等级预筛，不知道等级的不能漏）：lesson_item_link 里没有任何行挂着它的条目，或挂着它的课文里有 level 等于 lesson_level 的条目（用查询 textbook_import_item_linked 取有挂接的全部条目编号、textbook_import_item_linked_level 取挂在该等级课上的条目编号，直读 lesson_item_link 与 lesson_text，两个查询都限 subject_id 等于本科目）；lesson_level 为「全部」不筛
  伪代码 风格要求：rewrite 为 1 时写版权要求（这是商业教材，原文不能入库：title 只写语法点的名称，summary、explain、connection、examples 一律用自己的话重新写，不要照抄原文的句子，例句自己造，每课 2 到 4 句，日语加中文翻译；只有语法点名称、课序、等级这类事实可以照原文）；rewrite 为 0 时写「讲解、例句可以参照原文来写，例句可以沿用原文的」
  伪代码 prompt = 现有的抽课提示词（抽出每一课，返回 lessons 列表，每项含 title level summary explain connection examples orig_title item_codes point_codes confidence reason，编号只能从候选里选；examples 是数组、每项是有 jp 和 zh 两个键的对象；confidence 是你对映射的把握，0 到 1 的小数；reason 是一句话说为什么这样映射（旧 kg import_chunk.zs 第 37 行的要求））加上风格要求；返回 {"chunk_id": chunk_id, "rewrite": rewrite, "lesson_level": lesson_level, "item_count": 候选条目数, "point_count": 候选知识点数, "prompt": prompt}

公开 函数 创建导入任务 series_code series_name document_path code_prefix? source? license? lesson_level? rewrite? overwrite? file_name? file_size? file_ext? learner? current_role? auth_mode? subject?
  返回 同 新建导入：{ok, task_id, duplicate, chunk_count}（教材导入页「开始解析」，前端按任务 id 跳到审阅页）
  报错 400 同 新建导入
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  报错 403 本科目没开教材导入
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 页面口径转换后调用 新建导入：code_prefix 为空取 series_code 去掉连字符和下划线（旧 kg 口径：前缀不填就用系列代号）；lesson_level 为空取「全部」；rewrite 为空取 1，值为 false 0 否 off（不分大小写）取 0，其他取 1；overwrite 值为 true 1 是 on（不分大小写）取 1，其他（含空）取 0（页面开关提交上来可能是布尔、数字、文字）；file_path 取 document_path，其余入参原样传，并传 learner=learner current_role=current_role auth_mode=auth_mode subject=subject（新建导入 自己做 need=write 的科目校验）
  伪代码 返回 新建导入 的结果

公开 函数 导入首页 learner? current_role? auth_mode? subject?
  返回 教材导入页「进入时」的整页状态：{import_jobs, import_series, form}；import_jobs 是 [{job, series, label, file_name, created, job_state, href}] 按任务 id 倒序（job 是任务 id，series 是系列代号，label 是系列显示名，created 是建于时间，href 是 #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?job={job}）；import_series 是 [{code, label, lesson_n, series_state, href}]（不含 hanabira；series_state 恒为「在用」，列已导入系列 只含未撤下的；href 是 #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?manage={code}）；form 是新建表单的初值 {lesson_level: 全部, rewrite: true, overwrite: false}（开关值是文本 true/false：DSL 的布尔值输出成 JSON 会变成空对象，前端开关认 true/false 文本）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 列任务 subject=subject_id 得 tasks，逐个任务 job_state 用 任务进度文本 task_id subject_id=subject_id 取；调用 列已导入系列 subject=subject_id 得 series，去掉 code 等于 hanabira 的，lesson_n 取 lesson_count
  伪代码 返回 {"import_jobs": 行列表, "import_series": 行列表, "form": {"lesson_level": "全部", "rewrite": "true", "overwrite": "false"}}

公开 函数 任务视图 task_id learner? current_role? auth_mode? subject?
  返回 教材导入页审阅块的整页状态（「载入」和「每隔 2」轮询都用它；数字字段 running、passed 以及 import_chunks 的 tries、seq 必须是 JSON 数字不是文本——前端用 !job.running 判断，文本「0」会被当成真）：{job, job_note, import_chunks, import_drafts, import_rejected}；没有这个任务不报错，返回 {"job": {"id": task_id, "missing": "没有这个导入任务（{task_id}），可能已经删了。", "running": 0, "back": "#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5"}}（旧行为）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 task_id 用查询 textbook_import_task_by_id 先查（查不到、或任务的 subject_id 不等于本科目即属于别的科目，都走 missing，不调 取任务，免得报 404；文案与不存在相同）；查到调用 取任务 task_id=task_id subject=subject_id 得 t
  伪代码 job = {id: t.task_id, series: t.series_code, label: t.series_name, running, passed, head, progress, report_note, textbook, missing: 空串, back: #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5}；running 在 t.status 等于 处理中 时为 1 否则 0（页面据此每隔 2 秒轮询）；passed 是 status 为 通过 的草稿课数
  伪代码 head = 「系列 {series_code}（{series_name}）· 课号前缀 {code_prefix} · 文件 {file_name} · 」加「讲解和例句由模型改写」（任务 rewrite 不等于 0）或「保留原文讲解（没勾改写）」；progress：处理中为「正在解析：{完成加失败的块数}/{块总数} 块做完」加（失败块数大于 0 时）「，出错 {n} 块」加「。这页会自己刷新，可以先去别的页面。」；失败为「解析失败：{fail_reason}」；其他为「解析完了：{块总数} 块，抽出 {草稿课数} 课」加（失败块数大于 0 时）「，出错 {n} 块（在块表里重试）」加「。通过 {x} 课、驳回 {y} 课。」，已导入再加「已导入。」
  伪代码 report 不为空（确认导入后的 JSON）：解析出 imported、item_links、point_links、rejected；report_note = 「导入报告：导入 {imported} 课，映射到条目 {item_links} 条、知识点 {point_links} 条，拒收 {rejected 个数} 行。」，textbook = #%E6%95%99%E6%9D%90，import_rejected 取 rejected（[{code, reason}]）；report 为空这三项为空串/空列表
  伪代码 import_chunks 是 [{chunk_id, seq, title, chunk_status, error, tries}]：chunk_status 把块 status 换成旧名（待处理→待解析、处理中→解析中、完成→完成、失败→出错），error 取 fail_reason（空串），tries = retry_count 加 1（块还是待处理时不加）
  伪代码 import_drafts 是 [{draft, seq, title, draft_level, mapping, issues, confidence, review, href}]，按 seq、id 升序：draft 是草稿课 id，draft_level 取 level（空填「?」），mapping 用 映射文本 item_codes point_codes subject_id=subject_id，issues 用 问题文本，confidence 用 取草稿课 draft_id=draft subject=subject_id 的 confidence（有值写成「{n}%」，没有为空串），review 取 status（待审/通过/驳回），href 是 #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?draft={draft}
  伪代码 返回 {"job": job, "job_note": "", "import_chunks": 块行, "import_drafts": 草稿行, "import_rejected": 拒收行}（job_note 清空，一次操作的提示由调用方另放）

公开 函数 草稿视图 draft_id with_form? learner? current_role? auth_mode? subject?
  返回 教材导入页编辑块的整页状态：{draft, draft_note, draft_maps, map_options, form}；with_form 为「是」时 form 回填全部字段，否则（默认）form 只清空加映射的两个框；没有这一课不报错，只返回 {"draft": {"draft": draft_id, "missing": "没有这一课草稿（{draft_id}），可能任务已经删了。", "back": "#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5"}, "form": {}}（旧行为）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 draft_id 用查询 textbook_import_draft_by_id 先查（查不到、或所属任务的 subject_id 不等于本科目即属于别的科目，都走 missing，不调 取草稿课；文案与不存在相同）；查到调用 取草稿课 draft_id=draft_id subject=subject_id 得 d，再取所属任务（series_code）和来源块（seq、title）
  伪代码 draft = {draft: d.id, job: d.task_id, seq, title, draft_level: d.level, summary, explanation: d.explain, formation: d.connection, examples（空填 [] ，页面仍按 JSON 数组编辑，库里存的是什么就给什么）, dropped: d.dropped_codes（没有为空串）, issues: 问题文本, reason: d.reason（没有为空串）, confidence: 有值写成「{n}%」否则空串, review: d.status, series: series_code, head: 「系列 {series_code} · 第 {seq} 课 · {status}」, from_chunk: 「第 {块序} 块「{块标题}」」（来源块已不在填「?」）, back: #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?job={d.task_id}, missing: 空串}
  伪代码 draft_maps 是现在的映射 [{map_kind, map_code, map_label}]：item_codes 每个编号调用 kg.取条目 code=编号 subject=subject_id（取不到、包括属于别的科目，跳过）得 {map_kind: 条目, map_code: 编号, map_label: 「{name}（属于 {所属知识点 title}）」，所属知识点取不到只写 name}，point_codes 每个编号调用 kg.取知识点 code=编号 subject=subject_id 得 {map_kind: 知识点, map_code: 编号, map_label: title}；条目在前
  伪代码 map_options 是 [{value, label}]：调用 kg.列条目 subject=subject_id 每项 {value: code, label: 「{name}（条目，{code}）」}（按所属知识点、编号排），再 kg.列知识点 subject=subject_id 每项 {value: code, label: 「〔{title}〕（知识点，{code}）」}
  伪代码 form：with_form 为「是」 {title, draft_level, seq, summary, formation: connection, explanation: explain, examples（空填 []）, map_add: 空串, map_typed: 空串}；否则只 {map_add: 空串, map_typed: 空串}
  伪代码 返回 {"draft": draft, "draft_note": "", "draft_maps": 映射行, "map_options": 选项, "form": form}（draft_note 清空，「保存了。」由调用方另放）

函数 系列视图 series_code subject_id
  返回 教材导入页系列块的状态 {series_view}；series_view = {code, head, note, can_withdraw, back}；没有这个系列（或已撤下）为 {code, head: 「没有这个系列（{series_code}），可能已经撤下了。」, note, can_withdraw: 0, back}，note 在本科目存在 series_code 相等且 status=已撤下 的 textbook_import_task 时为「撤下了：这个系列已经撤下，教材页的下拉里不再有它。」（撤下后重新载入页面，不能把撤下的提示丢掉），否则（从没导入过、没有这个系列）为空串
  伪代码 找不到系列时：在 textbook_import_task 里查 series_code 相等、subject_id 等于 subject_id 且 status 等于 已撤下 的行，有则 note 为上面那句「撤下了：…」，没有则 note 为空串；找到系列（在用）时 note 为空串，不查任务表
  伪代码 调用 列已导入系列 series_code=series_code subject=subject_id 得 s，在 series 里找 code 相等的；找到 head = 「系列 {code}（{name}）：{lesson_count} 课。在用，教材页的下拉里能选到。」，note 空串，can_withdraw 在 code 不等于 hanabira 时为 1 否则 0，back = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5

公开 函数 导入视图 task_id? draft_id? series_code? learner? current_role? auth_mode? subject?
  返回 教材导入页「载入」（地址 #教材导入?job=3 / ?draft=12 / ?manage=mnn 进来时前端调它）的整页状态，加 form：task_id 不为空取 任务视图 task_id=task_id subject=subject_id 的结果；否则 draft_id 不为空取 草稿视图 draft_id=draft_id with_form=是 subject=subject_id 的结果；否则 series_code 不为空取 系列视图 series_code=series_code subject_id=subject_id 的结果；三个都空只返回 {form: {}}；非草稿的两种情况 form 为空对象 {}（不回填，也不动输入框）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 只取第一个不为空的；返回里 form 总是有这个键
  伪代码 task_id 非空时：返回 任务视图 加上 form 键等于 {}

公开 函数 一键通过页面 task_id learner? current_role? auth_mode? subject?
  返回 同 任务视图，job_note 为「通过了：{approved} 课（有映射、还待审的）。」
  报错 404 没有这个任务
  报错 400 已导入的课不能再改
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 一键通过 task_id=task_id subject=subject_id 得 r（报错原样向上抛）；调用 任务视图 task_id=task_id subject=subject_id 得 v；v 的 job_note 换成上面那句

公开 函数 确认导入页面 task_id learner? current_role? auth_mode? subject?
  返回 同 任务视图（已导入的任务带 job.report_note、import_rejected）
  报错 404 没有这个任务
  报错 400 已导入的课不能再改
  报错 400 没有通过的课
  报错 400 hanabira 是主教材，不能用导入覆盖它
  报错 400 系列已经有了，这个任务没勾覆盖已有系列
  报错 400 编号要以「<编码>.」开头
  报错 400 系列编号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 确认导入 task_id=task_id subject=subject_id（报错原样向上抛）；返回 任务视图 task_id=task_id subject=subject_id 的结果

公开 函数 审核草稿页面 draft_id decision job? learner? current_role? auth_mode? subject?
  返回 job 不为空（审阅页行上的通过/驳回）时同 任务视图 task_id=job，另加 form 键等于空对象 {}（接口用 表单=form 回填，视图里没有 form 会漏出字面量）；job 为空（编辑页）时同 草稿视图 draft_id=draft_id（with_form 否，不冲掉正在改的字段）
  报错 404 没有这个草稿课
  报错 400 已导入的课不能再改
  报错 400 decision 只能是 approve 或 reject
  报错 400 草稿课字段有错
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 审核草稿课 draft_id=draft_id decision=decision subject=subject_id（报错原样向上抛）；再按 job 是否为空返回对应视图（任务视图 task_id=job subject=subject_id，或 草稿视图 draft_id=draft_id with_form=否 subject=subject_id）

公开 函数 保存草稿页面 draft_id title draft_level seq summary? formation? explanation? examples? learner? current_role? auth_mode? subject?
  返回 同 草稿视图（with_form=是，把保存后的字段填回表单），draft_note 为「保存了。」
  报错 404 没有这个草稿课
  报错 400 已导入的课不能再改
  报错 400 草稿课字段有错
  报错 400 例句要写成 JSON 数组
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 examples 不为空且与库里原 examples 不同时，必须是 JSON 数组文本，否则报错 400 例句要写成 JSON 数组，每句一个对象（jp 日语、zh 中文）（判断用 SQL json_valid 加 json_type 等于 array 或 DSL 的解析JSON，两种都行）
  伪代码 调用 修改草稿课 draft_id=draft_id title=title level=draft_level summary=summary 或空串 explain=explanation 或空串 connection=formation 或空串 examples=examples 或空串 seq=seq subject=subject_id（报错原样向上抛）；调用 草稿视图 draft_id=draft_id with_form=是 subject=subject_id 得 v；v 的 draft_note 换成「保存了。」

公开 函数 加映射页面 draft_id map_typed? map_add? learner? current_role? auth_mode? subject?
  返回 同 草稿视图（with_form=否：只清空两个加映射的框，不冲掉正在改的字段）
  报错 404 没有这个草稿课
  报错 400 已导入的课不能再改
  报错 400 从下拉里选一个条目或知识点，或者输入编号
  报错 400 库里没有这个编号，只能挑已有的条目、知识点（不新建）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 code 取 map_typed（优先），为空取 map_add；code 为空报错 400 从下拉里选一个条目或知识点，或者输入编号
  伪代码 kind 推断：调用 kg.取条目 code=code subject=subject_id 有则 item；否则调用 kg.取知识点 code=code subject=subject_id 有则 point；都没有报错 400 库里没有编号「{code}」，只能挑已有的条目、知识点（不新建）
  伪代码 调用 改映射 draft_id=draft_id kind=kind action=add code=code subject=subject_id（报错原样向上抛）；返回 草稿视图 draft_id=draft_id with_form=否 subject=subject_id 的结果

公开 函数 去掉映射页面 draft_id map_code learner? current_role? auth_mode? subject?
  返回 同 草稿视图（with_form=否）
  报错 404 没有这个草稿课
  报错 400 已导入的课不能再改
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 取草稿课 draft_id=draft_id subject=subject_id（取不到、包括属于别的科目，404 向上抛）；map_code 在该草稿课 item_codes（逗号拆开）里 kind=item，否则 kind=point
  伪代码 调用 改映射 draft_id=draft_id kind=kind action=remove code=map_code subject=subject_id；返回 草稿视图 draft_id=draft_id with_form=否 subject=subject_id 的结果

公开 函数 重试块页面 chunk_id learner? current_role? auth_mode? subject?
  返回 同 任务视图 task_id=该块所属任务（重试后块回到待解析，任务回到处理中，页面开始轮询）
  报错 404 没有这个块
  报错 400 只有失败的块可以重试
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 重试块 chunk_id=chunk_id subject=subject_id 得 r（报错原样向上抛）；返回 任务视图 task_id=r.task_id subject=subject_id 的结果

公开 函数 撤下系列页面 series_code learner? current_role? auth_mode? subject?
  返回 教材导入页「撤下这个系列」的整页状态：{series_view, import_jobs, import_series}；series_view = {code, head, note, can_withdraw: 0, back}，head =「系列 {code}（{name}）：0 课。已撤下，教材页的下拉里没有它。」，note =「撤下了：库里删掉 {removed_lessons} 课（连同映射），教材页的下拉里不再有它。课文文件留在 content/lesson/series/{code}.withdrawn.jsonl。」（moved 为 0 时没有后半句）；import_jobs、import_series 同 导入首页（刷新首页两张表）
  报错 400 hanabira 是主教材，不能撤下
  报错 404 没有这个系列
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；任务、块、草稿都属于所属任务的 subject_id（块、草稿经所属任务判断），下面所有查询和写入都只限这个 subject_id；按 id 取到别的科目的任务、块、草稿，一律当不存在（包括属于别的科目），报错或返回与「不存在」完全相同；本函数是写内容操作，auth_mode 等于 on 时只有负责/协作教师可写（公开科目的其他教师只读）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 先调用 列已导入系列 subject=subject_id 取这个系列的 name（撤下后就查不到了；找不到则交给 撤下已导入系列 报 404）；调用 撤下已导入系列 series_code=series_code subject=subject_id 得 r（报错原样向上抛）；再按 导入首页 的口径取两张表

函数 例句转教材格式 examples
  返回 文本，教材页（lesson 的 取课文）拆句用的「日语^^中文@@日语^^中文」格式；没有可用的例句为空串
  伪代码 草稿里的例句是模型给的 JSON 数组文本 [{"jp":"日语","zh":"中文"},…]（草稿编辑页仍按 JSON 编辑，不变）；旧 kg 的课文例句本来就存 JSON、读的地方自己拆（queries/lesson_examples.sql 第 20-27 行），没有现成的转换代码，这里的口径由教材页的拆法反推：教材页按 @@ 拆句、每句按 ^^ 拆成恰好两段（lesson 约定的 取课文 例句那条）
  伪代码 examples 去首尾空白后为空，返回空串；解析不成功，或解析出来不是数组（已经是教材页格式的老数据、手写的文本），原样返回，不报错
  伪代码 数组逐项处理，坏项跳过不报错：不是对象；jp 或 zh 缺了、不是文本、去首尾空白后为空；jp 或 zh 里含「^^」或「@@」（这两个是分隔符，留在文本里会让教材页拆错句，宁可整句不要，不改写原文）。其余项取 jp、zh 去首尾空白，拼成 jp 加 ^^ 加 zh，各项按原顺序用 @@ 连接
  伪代码 空数组、或每一项都是坏项，返回空串
  伪代码 例：[{"jp":"A","zh":"甲"},{"jp":"B","zh":"乙"}] 返回 A^^甲@@B^^乙

函数 任务进度文本 task_id subject_id
  返回 任务表「进度」列的一句话：处理中为「解析中 {完成加失败的块数}/{块总数} 块」；失败为「失败：{fail_reason}」；已导入为「已导入」；已撤下为「已撤下」；其他（待审阅）为「待审 {草稿课数} 课（通过 {x}、驳回 {y}）」；块里有失败的再加「，出错 {n} 块」
  伪代码 调用 取任务 task_id=task_id subject=subject_id，从 chunks、drafts 的 status 数出各数

函数 映射文本 item_codes point_codes subject_id
  返回 草稿课表「映射」列：条目名用「、」连起来；条目和知识点都有时中间加「 / 」；知识点写成「〔title〕」用「、」连起来；一个都没有（或编号库里已不存在）为「（没有）」
  伪代码 编号都是英文逗号连接的文本；条目调用 kg.取条目 code=编号 subject=subject_id 取 name，知识点调用 kg.取知识点 code=编号 subject=subject_id 取 title，取不到（包括属于别的科目）的跳过

函数 问题文本 draft task_drafts
  返回 审阅要看的问题，用「；」连接（末尾不带），没有为空串；draft 是 取草稿课 的结果，task_drafts 是同任务全部草稿课
  伪代码 依次判：level 不是 N5 N4 N3 N2 N1 之一 →「等级没认出」；item_codes 和 point_codes 都为空 →「没映射到已有条目或知识点」；explain 去空白后为空 →「讲解是空的」；summary 去空白后为空 →「一句话是空的」；draft.status 不是 驳回 且同任务有别的草稿课 seq 相同且 status 不是 驳回 →「课序跟别的课重复」

函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，need=write 无权报 403 没有权限修改该科目，原样抛出）

函数 编号前缀检查 subject_id code
  返回 {ok}
  报错 400 编号要以「<编码>.」开头
  伪代码 subject_id 等于 1（日语）：直接返回 {"ok": 1}，旧编号不动
  伪代码 否则按 subject_id 查 subject_info 的 code（科目编码，查询 textbook_import_subject_code）；编码为空、或 code 不匹配 ^[a-z][a-z0-9_]*\.[A-Za-z0-9_-]+$、或 code 不以「<编码>.」开头，报错 400 编号要以「<编码>.」开头（文案里的 <编码> 换成真实编码）
  伪代码 返回 {"ok": 1}

## 接口
POST /textbook_import/home -> 导入首页 动作 import_home 模板 页面状态 表单=form 角色 teacher
POST /textbook_import/poll -> 任务视图 动作 import_poll 模板 页面状态 参数 job=task_id 角色 teacher
POST /textbook_import/load -> 导入视图 动作 import_load 模板 页面状态 表单=form 参数 job=task_id draft=draft_id manage=series_code 角色 teacher
POST /textbook_import/task/create -> 创建导入任务 上传 document 类型 pdf,docx,md,txt 上限 20MB 动作 import_create 模板 提交跳转动态 消息=已建任务 跳转=#教材导入?job={r.task_id} 参数 series=series_code label=series_name prefix=code_prefix 角色 teacher
POST /textbook_import/task/approve-mapped -> 一键通过页面 动作 import_pass_mapped 模板 页面状态 参数 job=task_id 角色 teacher
POST /textbook_import/task/confirm -> 确认导入页面 动作 import_confirm 模板 页面状态 参数 job=task_id 角色 teacher
POST /textbook_import/task/delete -> 删除任务 动作 import_job_delete 模板 提交跳转 消息=已删除这个导入任务 跳转=#教材导入 参数 job=task_id 角色 teacher
POST /textbook_import/chunk/retry -> 重试块页面 动作 import_chunk_retry 模板 页面状态 角色 teacher
POST /textbook_import/draft/pass -> 审核草稿页面 动作 import_draft_pass 模板 页面状态 表单=form 传 decision=approve 参数 draft=draft_id 角色 teacher
POST /textbook_import/draft/reject -> 审核草稿页面 动作 import_draft_reject 模板 页面状态 表单=form 传 decision=reject 参数 draft=draft_id 角色 teacher
POST /textbook_import/draft/save -> 保存草稿页面 动作 import_draft_save 模板 页面状态 表单=form 参数 draft=draft_id 角色 teacher
POST /textbook_import/draft/map-add -> 加映射页面 动作 import_map_add 模板 页面状态 表单=form 参数 draft=draft_id 角色 teacher
POST /textbook_import/draft/map-remove -> 去掉映射页面 动作 import_map_remove 模板 页面状态 表单=form 参数 draft=draft_id 角色 teacher
POST /textbook_import/series/withdraw -> 撤下系列页面 动作 import_series_withdraw 模板 页面状态 参数 manage=series_code 角色 teacher
GET /textbook_import/tasks -> 列任务 角色 teacher
GET /textbook_import/task -> 取任务 角色 teacher
GET /textbook_import/draft -> 取草稿课 角色 teacher
POST /textbook_import/draft/update -> 修改草稿课 角色 teacher
POST /textbook_import/draft/mapping -> 改映射 角色 teacher
POST /textbook_import/draft/review -> 审核草稿课 角色 teacher
GET /textbook_import/series -> 列已导入系列 角色 teacher
GET /textbook_import/chunk/prompt -> 块提示词 角色 teacher

## 用例
用例 新建导入_正常
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md file_name=a.md file_size=100 file_ext=md
  得 ok=1 duplicate=0 chunk_count=1
  库 textbook_import_task 共 1 行
  库 textbook_import_task 含 series_code=s1 series_name=系列一 display_title=系列一-a.md status=待审阅
  库 textbook_import_chunk 共 1 行

用例 新建导入_同文件只存一份
  先 文件 imports/a.md 内容=第1课は的用法
  先 调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md
  得 ok=1 duplicate=1 chunk_count=1
  库 textbook_import_task 共 1 行

用例 新建导入_不同系列同文件也只存一份
  先 文件 imports/a.md 内容=第1课は的用法
  先 调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md
  调用 新建导入 series_code=s2 series_name=系列二 code_prefix=s2 file_path=imports/a.md
  得 ok=1 duplicate=1
  库 textbook_import_task 共 1 行

用例 新建导入_系列代号为空
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=空 series_name=系列一 code_prefix=s1 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_显示名为空
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=空 code_prefix=s1 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_课号前缀为空
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=空 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_文件类型不收
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md file_ext=exe
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_文件超过20MB
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md file_size=20971521 file_ext=md
  报错 400
  库 textbook_import_task 共 0 行

用例 处理任务_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=处理中 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 处理任务 task_id=1
  得 ok=1 task_id=1 chunk_total=1
  库 textbook_import_task 含 status=待审阅
  库 textbook_import_chunk 无 status=待处理

用例 处理任务_没有任务
  调用 处理任务 task_id=999
  报错 404

用例 处理块_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1_ file_name=a.md raw_text=x status=处理中 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 处理块 chunk_id=1
  得 ok=1 chunk_id=1
  库 textbook_import_chunk 无 status=待处理
  库 textbook_import_chunk 无 status=处理中

用例 处理块_没有块
  调用 处理块 chunk_id=999
  报错 404

用例 标记任务失败_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=处理中 created_at=2026-01-01
  调用 标记任务失败 task_id=1 error=boom
  得 ok=1
  库 textbook_import_task 含 id=1 status=失败 fail_reason=boom

用例 标记任务失败_没有任务
  调用 标记任务失败 task_id=999 error=boom
  报错 404

用例 重试块_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1_ file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=失败 fail_reason=oops retry_count=0
  调用 重试块 chunk_id=1
  得 ok=1 chunk_id=1 task_id=1 status=待处理
  库 textbook_import_chunk 含 id=1 retry_count=1
  库 textbook_import_chunk 无 status=待处理
  库 textbook_import_task 含 id=1 status=待审阅

用例 重试块_非失败块
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=完成 retry_count=0
  调用 重试块 chunk_id=1
  报错 400
  库 textbook_import_chunk 含 id=1 retry_count=0

用例 重试块_没有块
  调用 重试块 chunk_id=999
  报错 404

用例 列任务_两个任务
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_task series_code=s2 series_name=系列二 file_name=b.md raw_text=y status=待审阅 created_at=2026-01-01
  调用 列任务
  得 total=2

用例 列任务_没有任务
  调用 列任务
  得 total=0

用例 取任务_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 display_title=系列一-a.md created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=完成 retry_count=0
  先 数据 textbook_import_chunk task_id=1 seq=2 content=y status=失败 retry_count=0
  先 数据 textbook_import_chunk task_id=1 seq=3 content=z status=待处理 retry_count=0
  调用 取任务 task_id=1
  得 task_id=1 series_code=s1 display_title=系列一-a.md status=待审阅 chunk_total=3 chunk_pending=1 chunk_done=1 chunk_failed=1

用例 取任务_没有任务
  调用 取任务 task_id=999
  报错 404

用例 取草稿课_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1 point_codes=P1 status=待审 display_title=s1_01-は的用法
  调用 取草稿课 draft_id=1
  得 id=1 code=s1_01 display_title=s1_01-は的用法 level=N5 title=は的用法 seq=1 item_codes=I1 point_codes=P1 status=待审

用例 取草稿课_没有
  调用 取草稿课 draft_id=999
  报错 404

用例 取草稿课_文本带引号
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 explain=讲解"带引号" examples=[{"jp":"a","zh":"b"}] examples_edited=0 seq=1 status=待审
  调用 取草稿课 draft_id=1
  得 id=1 code=s1_01 level=N5

用例 取任务_报告带引号
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 report={"imported":1,"rejected":[]} created_at=2026-01-01
  调用 取任务 task_id=1
  得 task_id=1 status=已导入

用例 草稿视图_例句带引号
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 explain=讲解"带引号" examples=[{"jp":"a","zh":"b"}] examples_edited=0 seq=1 status=待审
  调用 草稿视图 draft_id=1 with_form=是
  得 draft_note=空

用例 任务视图_已导入带报告
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 report={"imported":1,"item_links":1,"point_links":0,"rejected":[{"code":"s1_02","reason":"没有这个条目"}]} created_at=2026-01-01
  调用 任务视图 task_id=1
  得 job_note=空

用例 修改草稿课_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=旧标题 examples_edited=0 seq=1 status=待审
  调用 修改草稿课 draft_id=1 title=新标题 level=N4 summary=空 explain=空 connection=空 examples=新例句 seq=2
  得 ok=1 draft_id=1
  库 textbook_import_draft 含 id=1 title=新标题 level=N4 seq=2 examples_edited=1 code=s1_01 display_title=s1_01-新标题

用例 修改草稿课_处理中的任务也能改
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=处理中 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=旧标题 examples_edited=0 seq=1 status=待审
  调用 修改草稿课 draft_id=1 title=新标题 level=N5 summary=空 explain=空 connection=空 examples=空 seq=1
  得 ok=1
  库 textbook_import_draft 含 id=1 title=新标题

用例 修改草稿课_等级非法
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=旧标题 examples_edited=0 seq=1 status=待审
  调用 修改草稿课 draft_id=1 title=新标题 level=N9 summary=空 explain=空 connection=空 examples=空 seq=1
  报错 400
  库 textbook_import_draft 含 id=1 title=旧标题 level=N5

用例 修改草稿课_任务已导入
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=旧标题 examples_edited=0 seq=1 status=通过
  调用 修改草稿课 draft_id=1 title=新标题 level=N5 summary=空 explain=空 connection=空 examples=空 seq=1
  报错 400
  库 textbook_import_draft 含 id=1 title=旧标题

用例 改映射_加条目
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 改映射 draft_id=1 kind=item action=add code=I1
  得 ok=1 item_codes=I1
  库 textbook_import_draft 含 id=1 item_codes=I1

用例 改映射_删知识点
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1 point_codes=P1 status=待审
  调用 改映射 draft_id=1 kind=point action=remove code=P1
  得 ok=1 item_codes=I1
  库 textbook_import_draft 含 id=1 item_codes=I1

用例 改映射_条目不存在
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 改映射 draft_id=1 kind=item action=add code=NOPE
  报错 404
  库 textbook_import_draft 无 item_codes=NOPE

用例 改映射_知识点不存在
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 改映射 draft_id=1 kind=point action=add code=NOPE
  报错 404

用例 改映射_kind非法
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 改映射 draft_id=1 kind=word action=add code=I1
  报错 400

用例 改映射_任务已导入
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  调用 改映射 draft_id=1 kind=item action=remove code=I1
  报错 400

用例 审核草稿课_通过
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 审核草稿课 draft_id=1 decision=approve
  得 ok=1 draft_id=1 status=通过
  库 textbook_import_draft 含 id=1 status=通过

用例 审核草稿课_驳回
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 审核草稿课 draft_id=1 decision=reject
  得 ok=1 status=驳回
  库 textbook_import_draft 含 id=1 status=驳回

用例 审核草稿课_等级非法不能通过
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=X title=は的用法 examples_edited=0 seq=1 status=待审
  调用 审核草稿课 draft_id=1 decision=approve
  报错 400
  库 textbook_import_draft 含 id=1 status=待审

用例 审核草稿课_decision非法
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 审核草稿课 draft_id=1 decision=maybe
  报错 400

用例 审核草稿课_任务已导入
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  调用 审核草稿课 draft_id=1 decision=reject
  报错 400
  库 textbook_import_draft 含 id=1 status=通过

用例 一键通过_只通过有映射的
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=有映射 examples_edited=0 seq=1 item_codes=I1 status=待审
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_02 level=N5 title=无映射 examples_edited=0 seq=2 status=待审
  调用 一键通过 task_id=1
  得 ok=1 approved=1 skipped=1
  库 textbook_import_draft 含 code=s1_01 status=通过
  库 textbook_import_draft 含 code=s1_02 status=待审

用例 一键通过_任务已导入
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  调用 一键通过 task_id=1
  报错 400

用例 确认导入_正常
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1 point_codes=P1 status=通过
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_02 level=N5 title=被驳回 examples_edited=0 seq=2 status=驳回
  调用 确认导入 task_id=1
  得 ok=1 series_code=s1 total=1 imported=1 rejected_count=0 item_links=1 point_links=1 file_rows=1
  库 lesson_text 共 1 行
  库 lesson_text 含 code=s1_01 series_code=s1 level=N5
  库 lesson_item_link 含 lesson_code=s1_01 item_code=I1
  库 textbook_import_task 含 id=1 status=已导入

用例 确认导入_没有通过的课
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=待审的课 examples_edited=0 seq=1 status=待审
  调用 确认导入 task_id=1
  报错 400
  库 lesson_text 共 0 行
  库 textbook_import_task 含 id=1 status=待审阅

用例 确认导入_任务已导入
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  调用 确认导入 task_id=1
  报错 400

用例 确认导入_没有任务
  调用 确认导入 task_id=999
  报错 404

用例 删除任务_只删草稿
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=完成 retry_count=0
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  先 数据 lesson_text code=s1_01 level=N5 title=已导入的课 examples_edited=0 series_code=s1 seq=1
  调用 删除任务 task_id=1
  得 ok=1 task_id=1
  库 textbook_import_task 共 0 行
  库 textbook_import_chunk 共 0 行
  库 textbook_import_draft 共 0 行
  库 lesson_text 共 1 行

用例 删除任务_没有任务
  调用 删除任务 task_id=999
  报错 404

用例 列已导入系列_正常
  先 数据 lesson_series code=s1 name=系列一 sort_order=100
  先 数据 lesson_text code=s1_01 level=N5 title=第一课 examples_edited=0 series_code=s1 seq=1
  调用 列已导入系列
  得 total=1 lesson_total=0

用例 列已导入系列_带课文列表
  先 数据 lesson_series code=s1 name=系列一 sort_order=100
  先 数据 lesson_text code=s1_01 level=N5 title=第一课 examples_edited=0 series_code=s1 seq=1
  先 数据 lesson_text code=s1_02 level=N5 title=第二课 examples_edited=0 series_code=s1 seq=2
  调用 列已导入系列 series_code=s1
  得 total=1 lesson_total=2

用例 列已导入系列_没有系列
  调用 列已导入系列
  得 total=0

用例 撤下已导入系列_正常
  先 数据 lesson_series code=s1 name=系列一 sort_order=100
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  调用 撤下已导入系列 series_code=s1
  得 ok=1 series_code=s1 removed_lessons=0 moved=0
  库 lesson_series 含 code=s1 sort_order=-1
  库 textbook_import_task 含 id=1 status=已撤下

用例 撤下已导入系列_没有系列
  调用 撤下已导入系列 series_code=NOPE
  报错 404

用例 新建导入_默认开关
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md file_name=a.md
  得 ok=1 duplicate=0
  库 textbook_import_task 含 series_code=s1 lesson_level=全部 rewrite=1 overwrite=0

用例 新建导入_存开关
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md lesson_level=N4 rewrite=0 overwrite=1
  得 ok=1
  库 textbook_import_task 含 series_code=s1 lesson_level=N4 rewrite=0 overwrite=1

用例 新建导入_等级范围非法
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md lesson_level=N9
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_系列代号格式不对
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=BadCode series_name=系列一 code_prefix=s1 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_hanabira不能导入
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=hanabira series_name=主教材 code_prefix=h file_path=imports/a.md overwrite=1
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_系列已有没勾覆盖
  先 数据 lesson_series code=s1 name=旧系列 sort_order=100
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_系列已有勾了覆盖
  先 数据 lesson_series code=s1 name=旧系列 sort_order=100
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md overwrite=1
  得 ok=1 duplicate=0
  库 textbook_import_task 含 series_code=s1 overwrite=1

用例 新建导入_撤下过的系列也要勾覆盖
  先 数据 lesson_series code=s1 name=旧系列 sort_order=-1
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 块提示词_默认改写不筛等级
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 kg_item code=I2 name=が point_code=P1
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1_ file_name=a.md raw_text=x status=处理中 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 块提示词 chunk_id=1
  得 chunk_id=1 rewrite=1 lesson_level=全部 item_count=2 point_count=1

用例 块提示词_不改写
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1_ file_name=a.md raw_text=x status=处理中 created_at=2026-01-01 rewrite=0
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 块提示词 chunk_id=1
  得 rewrite=0

用例 块提示词_按等级预筛条目
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 kg_item code=I2 name=が point_code=P1
  先 数据 kg_item code=I3 name=を point_code=P1
  先 数据 lesson_text code=h_01 level=N4 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_text code=h_02 level=N5 title=第二课 examples_edited=0 series_code=hanabira seq=2
  先 数据 lesson_item_link lesson_code=h_01 item_code=I1
  先 数据 lesson_item_link lesson_code=h_02 item_code=I2
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1_ file_name=a.md raw_text=x status=处理中 created_at=2026-01-01 lesson_level=N5
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 块提示词 chunk_id=1
  得 lesson_level=N5 item_count=2 point_count=1

用例 块提示词_没有块
  调用 块提示词 chunk_id=999
  报错 404

用例 取草稿课_带模型自评
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审 confidence=85 dropped_codes=条目NOPE reason=助词は
  调用 取草稿课 draft_id=1
  得 id=1 confidence=85 dropped_codes=条目NOPE reason=助词は

用例 取草稿课_旧行没有模型自评
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 取草稿课 draft_id=1
  得 id=1 confidence=空 dropped_codes=空 reason=空

用例 草稿视图_带模型自评
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 title=第1课 content=x status=完成 retry_count=0
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审 confidence=85 dropped_codes=条目NOPE reason=助词は
  调用 草稿视图 draft_id=1 with_form=是
  得 draft_note=空

用例 任务视图_带模型自评
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=完成 retry_count=0
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审 confidence=85 reason=助词は
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_02 level=N5 title=旧行 examples_edited=0 seq=2 status=待审
  调用 任务视图 task_id=1
  得 job_note=空

用例 确认导入_例句转成教材页格式
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples=[{"jp":"私は学生です","zh":"我是学生"},{"jp":"これはペンです","zh":"这是笔"}] examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  得 ok=1 imported=1
  库 lesson_text 含 code=s1_01 series_code=s1 examples=私は学生です^^我是学生@@これはペンです^^这是笔

用例 确认导入_例句含分隔符的项跳过
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples=[{"jp":"甲^^乙","zh":"丙"},{"jp":"好句","zh":"好译"},{"jp":"丁","zh":"戊@@己"}] examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  得 ok=1 imported=1
  库 lesson_text 含 code=s1_01 examples=好句^^好译

用例 确认导入_例句坏项跳过不报错
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples=["字符串",5,{"jp":"只有日语"},{"jp":"","zh":"空日语"},{"jp":"句一","zh":"译一"},{"zh":"只有中文"},{"jp":"句二","zh":"译二"}] examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  得 ok=1 imported=1
  库 lesson_text 含 code=s1_01 examples=句一^^译一@@句二^^译二

用例 确认导入_例句空数组
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples=[] examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  得 ok=1 imported=1
  库 lesson_text 含 code=s1_01 series_code=s1
  库 lesson_text 无 examples=[]

用例 确认导入_例句全是坏项
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples=[{"jp":"甲^^乙","zh":"丙"},7] examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  得 ok=1 imported=1
  库 lesson_text 含 code=s1_01 series_code=s1
  库 lesson_text 无 examples=[{"jp":"甲^^乙","zh":"丙"},7]

用例 确认导入_例句不是JSON数组原样
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples=句子^^译文 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  得 ok=1 imported=1
  库 lesson_text 含 code=s1_01 examples=句子^^译文

用例 确认导入_系列已有没勾覆盖
  先 数据 lesson_series code=s1 name=旧系列 sort_order=100
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  报错 400
  库 lesson_text 共 0 行
  库 textbook_import_task 含 id=1 status=待审阅

用例 确认导入_系列已有勾了覆盖
  先 数据 lesson_series code=s1 name=旧系列 sort_order=100
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01 overwrite=1
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  得 ok=1 series_code=s1 total=1 imported=1
  库 lesson_text 含 code=s1_01 series_code=s1
  库 textbook_import_task 含 id=1 status=已导入

用例 确认导入_hanabira不能覆盖
  先 数据 textbook_import_task series_code=hanabira series_name=主教材 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01 overwrite=1
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=h_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  报错 400
  库 lesson_text 共 0 行

用例 撤下已导入系列_hanabira不能撤
  先 数据 lesson_series code=hanabira name=主教材 sort_order=1
  调用 撤下已导入系列 series_code=hanabira
  报错 400
  库 lesson_series 含 code=hanabira sort_order=1

用例 新建导入_前缀有大写
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=S1 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_前缀不是字母开头
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=1a file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_前缀带下划线
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s_1 file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_前缀超过20个字
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=abcdefghijklmnopqrstu file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_前缀刚好20个字
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=abcdefghijklmnopqrst file_path=imports/a.md
  得 ok=1 duplicate=0
  库 textbook_import_task 含 code_prefix=abcdefghijklmnopqrst

用例 新建导入_前缀被别的系列的旧式课号占了
  先 数据 lesson_text code=mnn-001 level=N5 title=别系列的课 examples_edited=0 series_code=mnn seq=1
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=mnn file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_前缀被别的系列的草稿式课号占了
  先 数据 lesson_text code=mnn12 level=N5 title=别系列的课 examples_edited=0 series_code=mnn seq=1
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=mnn file_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 新建导入_前缀只是别人课号的开头不算占
  先 数据 lesson_text code=mnnx01 level=N5 title=别系列的课 examples_edited=0 series_code=mnnx seq=1
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=mnn file_path=imports/a.md
  得 ok=1 duplicate=0
  库 textbook_import_task 含 series_code=s1 code_prefix=mnn

用例 新建导入_自己系列的课号不算占
  先 数据 lesson_text code=s101 level=N5 title=自己系列的课 examples_edited=0 series_code=s1 seq=1
  先 文件 imports/a.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/a.md overwrite=1
  得 ok=1 duplicate=0
  库 textbook_import_task 含 series_code=s1 code_prefix=s1 overwrite=1

用例 创建导入任务_前缀有大写
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=s1 series_name=系列一 document_path=imports/a.md code_prefix=Bad file_name=a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 创建导入任务_前缀被别的系列用了
  先 数据 lesson_text code=mnn-001 level=N5 title=别系列的课 examples_edited=0 series_code=mnn seq=1
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=s1 series_name=系列一 document_path=imports/a.md code_prefix=mnn file_name=a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 创建导入任务_留空前缀取系列代号但超过20个字
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=abcdefghij-klmnopqrstuv series_name=系列一 document_path=imports/a.md file_name=a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 创建导入任务_正常
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=s1 series_name=系列一 document_path=imports/a.md file_name=a.md
  得 ok=1 duplicate=0 chunk_count=1
  库 textbook_import_task 含 series_code=s1 code_prefix=s1 lesson_level=全部 rewrite=1 overwrite=0

用例 创建导入任务_前缀默认去连字符下划线
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=my-s_1 series_name=系列一 document_path=imports/a.md
  得 ok=1
  库 textbook_import_task 含 series_code=my-s_1 code_prefix=mys1

用例 创建导入任务_页面开关文本
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=s1 series_name=系列一 document_path=imports/a.md code_prefix=p1 lesson_level=N4 rewrite=false overwrite=true
  得 ok=1
  库 textbook_import_task 含 series_code=s1 code_prefix=p1 lesson_level=N4 rewrite=0 overwrite=1

用例 创建导入任务_开关勾上
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=s1 series_name=系列一 document_path=imports/a.md rewrite=true overwrite=false
  得 ok=1
  库 textbook_import_task 含 series_code=s1 rewrite=1 overwrite=0

用例 创建导入任务_系列已有没勾覆盖
  先 数据 lesson_series code=s1 name=旧系列 sort_order=100
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=s1 series_name=系列一 document_path=imports/a.md rewrite=true overwrite=false
  报错 400
  库 textbook_import_task 共 0 行

用例 创建导入任务_系列代号为空
  先 文件 imports/a.md 内容=第1课は的用法
  调用 创建导入任务 series_code=空 series_name=系列一 document_path=imports/a.md
  报错 400
  库 textbook_import_task 共 0 行

用例 导入首页_没有任务
  调用 导入首页
  得 有返回

用例 导入首页_有任务有系列
  先 数据 lesson_series code=hanabira name=主教材 sort_order=1
  先 数据 lesson_series code=s1 name=系列一 sort_order=100
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 display_title=系列一-a.md created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=完成 retry_count=0
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  调用 导入首页
  得 有返回

用例 任务视图_有任务
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1_ file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=完成 retry_count=0
  先 数据 textbook_import_chunk task_id=1 seq=2 content=y status=失败 fail_reason=oops retry_count=0
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1 status=待审
  调用 任务视图 task_id=1
  得 job_note=空

用例 任务视图_没有任务
  调用 任务视图 task_id=999
  得 有返回

用例 草稿视图_有这一课
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 title=第1课 content=x status=完成 retry_count=0
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1 point_codes=P1 status=待审
  调用 草稿视图 draft_id=1 with_form=是
  得 draft_note=空

用例 草稿视图_没有这一课
  调用 草稿视图 draft_id=999
  得 有返回

用例 导入视图_带任务
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  调用 导入视图 task_id=1
  得 job_note=空

用例 导入视图_带草稿
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 导入视图 draft_id=1
  得 draft_note=空

用例 导入视图_带系列
  先 数据 lesson_series code=s1 name=系列一 sort_order=100
  调用 导入视图 series_code=s1
  得 有返回

用例 导入视图_撤下后载入该系列
  先 数据 lesson_series code=s1 name=系列一 sort_order=-1
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已撤下 created_at=2026-01-01
  调用 导入视图 series_code=s1
  得 有返回

用例 导入视图_没导入过的系列载入
  调用 导入视图 series_code=NOPE
  得 有返回

用例 导入视图_什么都没带
  调用 导入视图
  得 有返回

用例 一键通过页面_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=有映射 examples_edited=0 seq=1 item_codes=I1 status=待审
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_02 level=N5 title=无映射 examples_edited=0 seq=2 status=待审
  调用 一键通过页面 task_id=1
  得 有返回
  库 textbook_import_draft 含 code=s1_01 status=通过
  库 textbook_import_draft 含 code=s1_02 status=待审

用例 一键通过页面_任务已导入
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  调用 一键通过页面 task_id=1
  报错 400

用例 确认导入页面_正常
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1 point_codes=P1 status=通过
  调用 确认导入页面 task_id=1
  得 job_note=空
  库 lesson_text 含 code=s1_01 series_code=s1 level=N5
  库 textbook_import_task 含 id=1 status=已导入

用例 确认导入页面_没有通过的课
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=待审的课 examples_edited=0 seq=1 status=待审
  调用 确认导入页面 task_id=1
  报错 400
  库 lesson_text 共 0 行

用例 审核草稿页面_审阅页通过
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 审核草稿页面 draft_id=1 decision=approve job=1
  得 job_note=空
  库 textbook_import_draft 含 id=1 status=通过

用例 审核草稿页面_编辑页驳回
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 审核草稿页面 draft_id=1 decision=reject
  得 draft_note=空
  库 textbook_import_draft 含 id=1 status=驳回

用例 审核草稿页面_任务已导入
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=通过
  调用 审核草稿页面 draft_id=1 decision=reject job=1
  报错 400
  库 textbook_import_draft 含 id=1 status=通过

用例 保存草稿页面_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=旧标题 examples_edited=0 seq=1 status=待审
  调用 保存草稿页面 draft_id=1 title=新标题 draft_level=N4 seq=2 summary=新一句话 formation=新接续 explanation=新讲解 examples=[]
  得 draft_note=保存了。
  库 textbook_import_draft 含 id=1 title=新标题 level=N4 seq=2 summary=新一句话 connection=新接续 explain=新讲解 code=s1_01

用例 保存草稿页面_例句不是JSON
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=旧标题 examples_edited=0 seq=1 status=待审
  调用 保存草稿页面 draft_id=1 title=新标题 draft_level=N4 seq=2 examples=不是JSON
  报错 400
  库 textbook_import_draft 含 id=1 title=旧标题 level=N5

用例 保存草稿页面_等级非法
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=旧标题 examples_edited=0 seq=1 status=待审
  调用 保存草稿页面 draft_id=1 title=新标题 draft_level=N9 seq=2
  报错 400
  库 textbook_import_draft 含 id=1 title=旧标题

用例 加映射页面_输入条目编号
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 加映射页面 draft_id=1 map_typed=I1
  得 有返回
  库 textbook_import_draft 含 id=1 item_codes=I1

用例 加映射页面_下拉选知识点
  先 数据 kg_point code=P1 title=助词
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 加映射页面 draft_id=1 map_add=P1
  得 有返回
  库 textbook_import_draft 含 id=1 point_codes=P1

用例 加映射页面_编号不存在
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 加映射页面 draft_id=1 map_typed=NOPE
  报错 400
  库 textbook_import_draft 无 item_codes=NOPE

用例 加映射页面_什么都没填
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 status=待审
  调用 加映射页面 draft_id=1
  报错 400

用例 去掉映射页面_去条目
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1,I2 point_codes=P1 status=待审
  调用 去掉映射页面 draft_id=1 map_code=I1
  得 有返回
  库 textbook_import_draft 含 id=1 item_codes=I2 point_codes=P1

用例 去掉映射页面_去知识点
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=s1_01 level=N5 title=は的用法 examples_edited=0 seq=1 item_codes=I1 point_codes=P1 status=待审
  调用 去掉映射页面 draft_id=1 map_code=P1
  得 有返回
  库 textbook_import_draft 含 id=1 item_codes=I1

用例 去掉映射页面_没有草稿
  调用 去掉映射页面 draft_id=999 map_code=I1
  报错 404

用例 重试块页面_正常
  先 数据 textbook_import_task series_code=s1 series_name=系列一 code_prefix=s1_ file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=失败 fail_reason=oops retry_count=0
  调用 重试块页面 chunk_id=1
  得 job_note=空
  库 textbook_import_chunk 含 id=1 retry_count=1

用例 重试块页面_非失败块
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=完成 retry_count=0
  调用 重试块页面 chunk_id=1
  报错 400
  库 textbook_import_chunk 含 id=1 retry_count=0

用例 撤下系列页面_正常
  先 数据 lesson_series code=s1 name=系列一 sort_order=100
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=已导入 created_at=2026-01-01
  调用 撤下系列页面 series_code=s1
  得 有返回
  库 lesson_series 含 code=s1 sort_order=-1
  库 textbook_import_task 含 id=1 status=已撤下

用例 撤下系列页面_没有系列
  调用 撤下系列页面 series_code=NOPE
  报错 404

用例 撤下系列页面_hanabira
  先 数据 lesson_series code=hanabira name=主教材 sort_order=1
  调用 撤下系列页面 series_code=hanabira
  报错 400
  库 lesson_series 含 code=hanabira sort_order=1

用例 跨科目_列任务只看本科目
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 列任务 subject=2
  得 total=1

用例 跨科目_列任务不传科目是日语
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 列任务
  得 total=1

用例 跨科目_取任务别的科目当不存在
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 取任务 task_id=1
  报错 404

用例 跨科目_取任务本科目
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 取任务 task_id=1 subject=2
  得 task_id=1 series_code=math.s

用例 跨科目_取草稿课别的科目当不存在
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数 examples_edited=0 seq=1 status=待审
  调用 取草稿课 draft_id=1
  报错 404

用例 跨科目_取草稿课本科目
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数 examples_edited=0 seq=1 status=待审
  调用 取草稿课 draft_id=1 subject=2
  得 id=1 code=math.1

用例 跨科目_任务视图别的科目当不存在
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 任务视图 task_id=1
  得 有返回
  得 import_chunks=空 import_drafts=空

用例 跨科目_修改草稿课别的科目404
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=旧标题 examples_edited=0 seq=1 status=待审
  调用 修改草稿课 draft_id=1 title=新标题 level=N5 summary=空 explain=空 connection=空 examples=空 seq=1
  报错 404
  库 textbook_import_draft 含 id=1 title=旧标题

用例 跨科目_审核草稿课别的科目404
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数 examples_edited=0 seq=1 status=待审
  调用 审核草稿课 draft_id=1 decision=approve
  报错 404
  库 textbook_import_draft 含 id=1 status=待审

用例 跨科目_改映射别的科目的条目404
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数 examples_edited=0 seq=1 status=待审
  调用 改映射 draft_id=1 kind=item action=add code=I1 subject=2
  报错 404
  库 textbook_import_draft 无 item_codes=I1

用例 跨科目_改映射本科目的条目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数 examples_edited=0 seq=1 status=待审
  调用 改映射 draft_id=1 kind=item action=add code=math.i1 subject=2
  得 ok=1 item_codes=math.i1

用例 跨科目_一键通过别的科目的任务404
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 一键通过 task_id=1
  报错 404

用例 跨科目_删除任务别的科目404
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 删除任务 task_id=1
  报错 404
  库 textbook_import_task 共 1 行

用例 跨科目_重试块别的科目404
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=失败 fail_reason=oops retry_count=0
  调用 重试块 chunk_id=1
  报错 404
  库 textbook_import_chunk 含 id=1 retry_count=0

用例 跨科目_块提示词别的科目404
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 块提示词 chunk_id=1
  报错 404

用例 跨科目_块提示词候选只含本科目
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 kg_item code=math.i2 name=条目二 point_code=math.a subject_id=2
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 块提示词 chunk_id=1 subject=2
  得 chunk_id=1 item_count=2 point_count=1

用例 跨科目_处理块后台以任务科目为准
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 处理块 chunk_id=1
  得 ok=1 chunk_id=1
  库 textbook_import_chunk 无 status=待处理
  库 textbook_import_chunk 无 status=处理中

用例 跨科目_处理任务后台以任务科目为准
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_chunk task_id=1 seq=1 content=x status=待处理 retry_count=0
  调用 处理任务 task_id=1
  得 ok=1 task_id=1 chunk_total=1
  库 textbook_import_task 含 id=1 status=待审阅 subject_id=2

用例 跨科目_新建导入落当前科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 新建导入 series_code=math_s series_name=数学教材 code_prefix=math. file_path=imports/m.md file_name=m.md subject=2
  得 ok=1 duplicate=0 chunk_count=1
  库 textbook_import_task 含 series_code=math_s code_prefix=math. subject_id=2

用例 跨科目_新建导入前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 新建导入 series_code=math_s series_name=数学教材 code_prefix=m file_path=imports/m.md subject=2
  报错 400
  库 textbook_import_task 共 0 行

用例 跨科目_新建导入别的科目的前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 新建导入 series_code=math_s series_name=数学教材 code_prefix=jp. file_path=imports/m.md subject=2
  报错 400
  库 textbook_import_task 共 0 行

用例 跨科目_新建导入同文件别的科目不算重复
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  先 调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/m.md
  调用 新建导入 series_code=math_s series_name=数学教材 code_prefix=math. file_path=imports/m.md subject=2
  得 ok=1 duplicate=0
  库 textbook_import_task 共 2 行
  库 textbook_import_task 含 series_code=math_s subject_id=2

用例 跨科目_确认导入落当前科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数入门 examples_edited=0 seq=1 item_codes=math.i1 point_codes=math.a status=通过
  调用 确认导入 task_id=1 subject=2
  得 ok=1 series_code=math.s total=1 imported=1 item_links=1 point_links=1
  库 lesson_series 含 code=math.s subject_id=2
  库 lesson_text 含 code=math.1 series_code=math.s subject_id=2
  库 lesson_item_link 含 lesson_code=math.1 item_code=math.i1 subject_id=2
  库 lesson_point_link 含 lesson_code=math.1 point_code=math.a subject_id=2
  库 textbook_import_task 含 id=1 status=已导入

用例 跨科目_确认导入别的科目的任务404
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数入门 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1
  报错 404
  库 lesson_text 共 0 行
  库 textbook_import_task 含 id=1 status=待审阅

用例 跨科目_确认导入课号前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=m file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=m1 level=N5 title=代数入门 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1 subject=2
  报错 400
  库 lesson_text 共 0 行
  库 textbook_import_task 含 id=1 status=待审阅

用例 跨科目_列已导入系列只看本科目
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  先 数据 lesson_text code=math.1 level=N5 title=代数 examples_edited=0 series_code=math.s seq=1 subject_id=2
  调用 列已导入系列 series_code=math.s subject=2
  得 total=1 lesson_total=1

用例 跨科目_撤下已导入系列别的科目的系列404
  先 数据 lesson_series code=s1 name=系列一 sort_order=100
  先 数据 textbook_import_task series_code=s1 series_name=系列一 file_name=a.md raw_text=x status=待审阅 created_at=2026-01-01
  调用 撤下已导入系列 series_code=s1 subject=2
  报错 404
  库 lesson_series 含 code=s1 sort_order=100
  库 textbook_import_task 含 id=1 status=待审阅

用例 跨科目_撤下已导入系列落当前科目
  先 数据 lesson_series code=math.s name=数学教材 sort_order=100 subject_id=2
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 file_name=m.md raw_text=y status=已导入 created_at=2026-01-01 subject_id=2
  调用 撤下已导入系列 series_code=math.s subject=2
  得 ok=1 series_code=math.s
  库 lesson_series 含 code=math.s sort_order=-1
  库 textbook_import_task 含 id=1 status=已撤下

用例 跨科目_need_新建导入公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 新建导入 series_code=math_s series_name=数学教材 code_prefix=math. file_path=imports/m.md learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 textbook_import_task 共 0 行

用例 跨科目_need_新建导入协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 新建导入 series_code=math_s series_name=数学教材 code_prefix=math. file_path=imports/m.md learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 duplicate=0
  库 textbook_import_task 含 series_code=math_s subject_id=2

用例 跨科目_need_确认导入公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数入门 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 lesson_text 共 0 行
  库 textbook_import_task 含 id=1 status=待审阅

用例 跨科目_need_确认导入协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  先 数据 textbook_import_draft task_id=1 chunk_id=1 code=math.1 level=N5 title=代数入门 examples_edited=0 seq=1 status=通过
  调用 确认导入 task_id=1 learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 series_code=math.s imported=1
  库 lesson_text 含 code=math.1 subject_id=2

用例 跨科目_need_读取公共科目非负责教师可读
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 列任务 learner=t2 current_role=teacher auth_mode=on subject=2
  得 total=1

用例 跨科目_need_删除任务公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps={"textbook_import":1} levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 textbook_import_task series_code=math.s series_name=数学教材 code_prefix=math. file_name=m.md raw_text=y status=待审阅 created_at=2026-01-01 subject_id=2
  调用 删除任务 task_id=1 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 textbook_import_task 共 1 行

用例 门控_非日语科目没开教材导入403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=py name=编程 kind=general caps={"kg":1,"quiz":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 新建导入 series_code=py_s series_name=编程教材 code_prefix=py. file_path=imports/m.md file_name=m.md subject=2
  报错 403
  库 textbook_import_task 共 0 行

用例 门控_非日语科目caps不是JSON也403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=py name=编程 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 创建导入任务 series_code=py_s series_name=编程教材 document_path=imports/m.md code_prefix=py. subject=2
  报错 403
  库 textbook_import_task 共 0 行

用例 门控_日语科目照常
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/m.md 内容=第1课は的用法
  调用 新建导入 series_code=s1 series_name=系列一 code_prefix=s1 file_path=imports/m.md file_name=m.md
  得 ok=1 duplicate=0

## 脚本
scripts/textbook_import_run.zs 入参 task_id；出错 scripts/textbook_import_run_fail.zs；后台逐块处理一个导入任务里待处理的块（调 处理任务；新建导入和重试块都走它），完成后任务进入待审阅；出错时调 标记任务失败，把任务状态写成失败并记原因
