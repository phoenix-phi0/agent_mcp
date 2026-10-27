模块 lesson
依赖 kg subject

## 表
表 lesson_series
  code 文本 系列编号，唯一（默认系列编号为 hanabira）
  name 文本 系列名称
  intro 长文本 简介，可空
  source 文本 来源，可空
  license 文本 许可，可空
  sort_order 整数 排序，小于 0 表示已撤下，不在下拉里出现
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 lesson_text
  code 文本 课文编号，唯一
  level 文本 等级 N5/N4/N3/N2/N1
  title 文本 标题
  summary 长文本 一句话，可空
  explain 长文本 讲解，可空
  connection 长文本 接续，可空
  examples 长文本 例句（日语+中文，整体存取，不拆行），可空
  examples_edited 整数 是否改过例句（1/0）
  orig_title 文本 原标题，可空
  series_code 文本 所属系列编号
  seq 整数 课序（线性教材显示第 N 课）
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 lesson_item_link
  lesson_code 文本 课文编号
  item_code 文本 表达方式条目编号（来自 kg_item）
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 lesson_point_link
  lesson_code 文本 课文编号
  point_code 文本 知识点编号（来自 kg_point）
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 lesson_pref 学习记录
  learner 文本 学习者；learner + subject_id 唯一
  series_code 文本 所选当前系列编号（偏好，导入和撤下都不清空）
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 页面字段
页面 lesson_view 教材页面
  series 文本 系列下拉所选的系列编号（选项来自接口 series_options，只有可用系列）
  lesson_level 枚举 全部,N5,N4,N3,N2,N1 等级筛选
  keyword 文本 关键字（标题、一句话、条目名）
  qcount 整数 课文表「题数」列（按挂接算出来的，不在真表）
  jp 文本 例句表「日语」列
  zh 文本 例句表「中文」列
  label 文本 条目表「条目」列（条目名或「（整个知识点）」）
  point_label 文本 条目表「所属知识点」列

## 函数
公开 函数 列系列 learner? current_role? auth_mode? subject?
  返回 {total, series}，series 是 [{code, name, intro, source, license, sort_order}]，只含 sort_order 不小于 0 的系列，按 sort_order 升序、id 升序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 查 lesson_series 中 subject_id 等于本科目且 sort_order 不小于 0 的行，按 sort_order 升序、id 升序（别的科目的系列不出现）
  伪代码 返回 {"total": 行数, "series": 列表}

公开 函数 取当前系列 learner current_role? auth_mode? subject?
  返回 {learner, series_code, name, is_default}；is_default 为 1 表示没选或所选系列已不可用，用了默认系列 hanabira
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 lesson_pref 一行
  伪代码 有记录时，按其 series_code 查 lesson_series，存在且属于本科目（subject_id 等于本科目）且 sort_order 不小于 0，则返回 {"learner": learner, "series_code": 该编号, "name": 该系列 name, "is_default": 0}
  伪代码 否则：本科目 subject_id 等于 1 时按 hanabira 查 lesson_series（subject_id 等于 1 的行），name 取其 name，没有这行时 name 取 "hanabira"（日语行为同旧）；本科目不等于 1 时取本科目 sort_order 不小于 0 的第一个系列（sort_order 升序、id 升序），有则按它的 code、name 走下面的默认返回，一个系列也没有则返回 {"learner": learner, "series_code": "", "name": "", "is_default": 1}
  伪代码 返回 {"learner": learner, "series_code": "hanabira", "name": name, "is_default": 1}

公开 函数 选择系列 learner series_code current_role? auth_mode? subject?
  返回 {ok, learner, series_code}
  报错 404 没有这个系列
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 series_code 和本科目 subject_id 查 lesson_series，查不到（包括属于别的科目）或 sort_order 小于 0，报错 404 没有这个系列
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 lesson_pref，没有则插入 (learner, subject_id, series_code)，有则更新 series_code
  伪代码 返回 {"ok": 1, "learner": learner, "series_code": series_code}

公开 函数 列课文 series_code? level? keyword? learner? current_role? auth_mode? subject?
  返回 {total, lessons}，lessons 是 [{code, level, title, summary, series_code, seq}]，按 seq 升序、id 升序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 查 lesson_text 中 subject_id 等于本科目的行
  伪代码 series_code 不为空时只留 series_code 相等的行
  伪代码 level 不为空时只留 level 相等的行
  伪代码 keyword 不为空时只留 code、title、summary 任一包含 keyword，或该课经 lesson_item_link 挂接的条目（kg_item）的名字包含 keyword 的行；同课只出一次（挂接多个命中条目不重复）
  伪代码 条目名匹配：lesson_item_link 按 lesson_code 关联 kg_item（两边 subject_id 都等于本科目），任一挂接条目的 name 包含 keyword 即命中
  伪代码 按 seq 升序、id 升序，返回 {"total": 行数, "lessons": 列表}

公开 函数 取课文 code learner? current_role? auth_mode? subject?
  返回 {code, level, title, summary, explain, connection, examples, examples_edited, orig_title, series_code, seq, point_codes}；point_codes 是该课挂的知识点编号用英文逗号连接（按挂接顺序）；查不到返回空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 code 和本科目 subject_id 查 lesson_text 一行，查不到（包括属于别的科目）则返回空，文案与「不存在」相同
  伪代码 查 lesson_point_link 中 subject_id 等于本科目且 lesson_code=code 的行，按 id 升序，取 point_code 用英文逗号连接成 point_codes
  伪代码 返回该行各字段加 point_codes

公开 函数 按条目列课文 item_code learner? current_role? auth_mode? subject?
  返回 {item_code, total, lessons}，lessons 是 [{code, level, title, summary, series_code, seq}]，按 seq 升序、id 升序
  报错 404 没有这个条目
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 kg.取条目 code=item_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个条目
  伪代码 查 lesson_item_link 中 subject_id 等于本科目且 item_code 相等的行，连 lesson_text（subject_id 也等于本科目）取课文，同一课只算一次，按 seq 升序、id 升序
  伪代码 返回 {"item_code": item_code, "total": 个数, "lessons": 列表}

公开 函数 按知识点列课文 point_code learner? current_role? auth_mode? subject?
  返回 {point_code, total, lessons}，lessons 同「按条目列课文」（只含直接挂在该知识点上的课）
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 kg.取知识点 code=point_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个知识点
  伪代码 查 lesson_point_link 中 subject_id 等于本科目且 point_code 相等的行，连 lesson_text（subject_id 也等于本科目）取课文，同一课只算一次，按 seq 升序、id 升序
  伪代码 返回 {"point_code": point_code, "total": 个数, "lessons": 列表}

公开 函数 取课文关联条目 lesson_code learner? current_role? auth_mode? subject?
  返回 {lesson_code, total, items}，items 是 [{code, name, point_code}]，按挂接顺序
  报错 404 没有这课
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 lesson_code 和本科目 subject_id 查 lesson_text，查不到（包括属于别的科目）报错 404 没有这课
  伪代码 查 lesson_item_link 中 subject_id 等于本科目且 lesson_code 相等的行，按 id 升序
  伪代码 逐行调用 kg.取条目 code=该行 item_code subject=subject_id，取到则收 {code, name, point_code}，取不到（条目已被删）跳过
  伪代码 返回 {"lesson_code": lesson_code, "total": 个数, "items": 列表}

公开 函数 取知识点等级 point_code learner? current_role? auth_mode? subject?
  返回 {point_code, level, lesson_count}；level 是与该知识点相关的课文里最基础的等级（N5 最基础、N1 最难），没有相关课文时 level 为空串、lesson_count 为 0
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 kg.取知识点 code=point_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个知识点
  伪代码 课文集合 = lesson_point_link 中 subject_id 等于本科目且 point_code 相等的课文编号，并上「调用 kg.按知识点列条目 point_code=point_code subject=subject_id」得到的每个条目在 lesson_item_link（subject_id 等于本科目）中挂的课文编号，去重
  伪代码 连 lesson_text（subject_id 等于本科目）取每课 level，lesson_count = 集合大小
  伪代码 集合为空返回 {"point_code": point_code, "level": "", "lesson_count": 0}
  伪代码 否则取等级数字最大的 level（N5 > N4 > N3 > N2 > N1），返回 {"point_code": point_code, "level": level, "lesson_count": lesson_count}

公开 函数 导入课文 series_code file_path series_name? intro? source? license? sort_order? learner? current_role? auth_mode? subject?
  返回 {ok, series_code, total, item_links, point_links}
  报错 400 series_code 不能为空
  报错 400 导入文件有错
  报错 400 课号重复
  报错 400 课文映射对不上
  报错 400 编号要以「<编码>.」开头
  报错 400 系列编号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 series_code 为空，报错 400 series_code 不能为空
  伪代码 sort_order 不为空且不是整数，报错 400 导入文件有错
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略；没有有效行报错 400 导入文件有错
  伪代码 每行格式「课号|等级|标题|一句话|讲解|接续|例句|是否改过例句|原标题|课序|条目编号列表|知识点编号列表」，用 | 分隔；例句字段原样整体存入；后面从「是否改过例句」起的字段可省略或为空；条目编号列表、知识点编号列表内用英文逗号隔开
  伪代码 校验：课号、标题不能为空；等级必须是 N5 N4 N3 N2 N1 之一；是否改过例句为空当 0，只能是 0 或 1；课序为空当 0，否则必须是整数；任一不满足报错 400 导入文件有错
  伪代码 同一文件内课号重复，或课号已存在于 series_code 以外的系列的 lesson_text 中，报错 400 课号重复
  伪代码 课号前缀：每行课号调用本模块 编号前缀检查 subject_id=subject_id code=课号（日语 subject_id=1 豁免，其它科目要以「<科目编码>.」开头），不符报错 400 编号要以「<编码>.」开头，整批不写
  伪代码 条目编号列表里每个编号调用 kg.取条目 code=编号 subject=subject_id，取不到（包括属于别的科目）报错 400 课文映射对不上；知识点编号列表里每个编号调用 kg.取知识点 code=编号 subject=subject_id，取不到报错 400 课文映射对不上（映射只引用已有的，不新建）
  伪代码 在一个事务里：
  伪代码 按 series_code 查 lesson_series：已有但 subject_id 不等于本科目，报错 400 系列编号已被其他科目使用（整批不写，系列编号全局唯一）；没有则插入 (code=series_code, name=series_name 不为空取之否则取 series_code, intro, source, license, sort_order=sort_order 不为空取之否则 100, subject_id)；有则对 series_name、intro、source、license、sort_order 中不为空的项更新对应列，为空的项不改
  伪代码 删除 lesson_item_link、lesson_point_link 中属于 series_code 系列各课的行，再删除 lesson_text 中 series_code 相等的行（只动这个系列，其它系列、其它科目和 lesson_pref 不动）
  伪代码 逐行插入 lesson_text（series_code 取入参，带 subject_id），对条目编号列表每个编号插入 lesson_item_link (lesson_code, item_code, subject_id)，对知识点编号列表每个编号插入 lesson_point_link (lesson_code, point_code, subject_id)，同一课内重复编号只插一次，统计 item_links、point_links
  伪代码 返回 {"ok": 1, "series_code": series_code, "total": 有效行数, "item_links": item_links, "point_links": point_links}

公开 函数 写入系列课文并重灌 series_code rows_json series_name? source? license? learner? current_role? auth_mode? subject?
  返回 {ok, series_code, total, imported, item_links, point_links, file_rows, rejected}
  报错 400 series_code 不能为空
  报错 400 课文数据有错
  报错 400 课号重复
  报错 400 编号要以「<编码>.」开头
  报错 400 系列编号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 series_code 为空，报错 400 series_code 不能为空
  伪代码 rows_json 是 JSON 数组，每个元素是一课：{code, level, title, summary, explain, connection, examples, examples_edited, orig_title, seq, item_codes, point_codes}，item_codes、point_codes 是编号数组（可空）；不是数组或没有任何一课，报错 400 课文数据有错
  伪代码 校验每课：code、title 不能为空；level 必须是 N5 N4 N3 N2 N1 之一；examples_edited 为空当 0，只能是 0 或 1；seq 为空当 0，否则必须是整数；任一不满足报错 400 课文数据有错
  伪代码 同一批内 code 重复，或 code 已存在于 series_code 以外的系列的 lesson_text 中（任何科目，课号全局唯一），报错 400 课号重复
  伪代码 课号前缀：每课 code 调用本模块 编号前缀检查 subject_id=subject_id code=code（日语 subject_id=1 豁免，其它科目要以「<科目编码>.」开头），不符报错 400 编号要以「<编码>.」开头，整批不写、不写文件
  伪代码 先写文件：用 写JSONL 把全部课（每课一行 JSON，字段同上）写入 content/lesson/series/{series_code}.jsonl（覆盖旧文件，文件是源数据，库是它的投影），file_rows 为写入的行数
  伪代码 再按文件重灌：读 content/lesson/series/{series_code}.jsonl 逐行处理；每课的 item_codes 每个编号调用 kg.取条目 code=编号 subject=subject_id、point_codes 每个编号调用 kg.取知识点 code=编号 subject=subject_id，任何一个取不到（包括属于别的科目），这一课整行拒收，记入 rejected（元素 {code, reason}，reason 写明哪个条目或知识点编号在库里没有），其余课照常导入；映射只引用已有的，不新建
  伪代码 在一个事务里：按 series_code 查 lesson_series：已有但 subject_id 不等于本科目，报错 400 系列编号已被其他科目使用（整批不写，系列编号全局唯一；这一步放在写文件之前检查）；没有则插入 (code=series_code, name=series_name 不为空取之否则取 series_code, source, license, sort_order=100, subject_id)；有则对 series_name、source、license 中不为空的项更新对应列，并把 sort_order 小于 0 的改回 100（重新上架）
  伪代码 同一事务里删除 lesson_item_link、lesson_point_link 中属于 series_code 系列各课的行，再删除 lesson_text 中 series_code 相等的行（只动这个系列，其它系列、其它科目和 lesson_pref 不动），然后逐课插入通过的课：lesson_text（series_code 取入参，带 subject_id）、lesson_item_link (lesson_code, item_code, subject_id)、lesson_point_link (lesson_code, point_code, subject_id)，同一课内重复编号只插一次，统计 item_links、point_links
  伪代码 total 为 rows_json 的课数，imported 为实际导入的课数（total 减去拒收数）
  伪代码 返回 {"ok": 1, "series_code": series_code, "total": total, "imported": imported, "item_links": item_links, "point_links": point_links, "file_rows": file_rows, "rejected": rejected}

公开 函数 撤下系列 series_code learner? current_role? auth_mode? subject?
  返回 {ok, series_code, removed_lessons, moved}
  报错 404 没有这个系列
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 按 series_code 和本科目 subject_id 查 lesson_series，查不到（包括属于别的科目）报错 404 没有这个系列
  伪代码 先用 移动文件 content/lesson/series/{series_code}.jsonl content/lesson/series/{series_code}.withdrawn.jsonl 挪走内容文件（源不存在返回否，不算错；目标已存在被覆盖），moved 为 1（挪了）或 0（没有文件可挪）
  伪代码 在一个事务里：数出 series_code 系列的课文数 removed_lessons；删除这些课文在 lesson_item_link、lesson_point_link 中的行；删除 lesson_text 中该系列的行；把 lesson_series 该行 sort_order 改为 -1（系列行保留，lesson_pref 不动）
  伪代码 返回 {"ok": 1, "series_code": series_code, "removed_lessons": removed_lessons, "moved": moved}

函数 题数表 subject_id
  返回 [{lesson_code, n}]，只数 subject_id 等于入参科目的课、挂接和题（lesson_text、lesson_item_link、lesson_point_link、kg_item、quiz_question 的 subject_id 都等于入参），n 是该课的题数：该课在 lesson_item_link 挂的条目在 quiz_question 中 item_code 相等的题，并上该课在 lesson_point_link 直接挂的知识点下条目（kg_item 的 point_code 相等）在 quiz_question 中的题，同一题只算一次；一题都没有的课不出现。查 quiz 的表是直读（lesson 不声明依赖 quiz——quiz 已依赖 lesson，声明会成环），题数只数挂接得到的题（模块用例的库没有 quiz 的表，题数按 0；题数大于 0 的路径在整库接口实测核）
  伪代码 先查 app.db lesson_qq_exists（sqlite_master 里有没有 quiz_question 表）得 c——模块用例的库只建本模块和上游模块的表，quiz 的表不一定在；c 为 0 则返回空列表（各课题数按 0，整库和接口实测时表在、题数照实）
  伪代码 c 不为 0 则查 app.db lesson_qcount（带 subject_id），返回列表

公开 函数 教材页面 learner series? lesson_level? keyword? current_role? auth_mode? subject?
  返回 教材页「进入时/搜索/改系列」（动作 lesson_list）的整页状态：{lessons, series_options, series_head, lesson_count, form}；lessons 是 [{code, level, title, summary, qcount, href}]（qcount 为该课题数、没有为 0，href=#%E6%95%99%E6%9D%90?lesson={code}）；series_options 是可用系列的 [{value, label}]（label 用系列名）；series_head 是当前系列名；lesson_count 是「共{N}课」；form 回填 {series: 当前系列编号, lesson_level: 所选（空填「全部」）, keyword: 所选（可空）}
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 列系列 得可用系列列表（本科目的）；调用 题数表 subject_id=subject_id 得题数表（qcount 只数本科目的题）
  伪代码 series 不为空且在可用系列里：调用 选择系列 learner=learner series_code=series subject=subject_id，当前系列=该系列（编号、name）；否则（series 为空或不在可用系列里，不改偏好）调用 取当前系列 learner=learner subject=subject_id，当前系列取其 series_code、name
  伪代码 调用 列课文 series_code=当前系列编号 level=（lesson_level 为空或「全部」传空串，否则原值） keyword=keyword 或空串，得 {total, lessons}
  伪代码 lessons 逐行补 qcount（题数表中 lesson_code 相等的 n，没有为 0）和 href=#%E6%95%99%E6%9D%90?lesson={code}
  伪代码 series_options 为可用系列逐行转 {value: code, label: name}；返回 {"lessons": 行列表, "series_options": 选项列表, "series_head": 当前系列 name, "lesson_count": "共{total}课", "form": {"series": 当前系列编号, "lesson_level": lesson_level 为空取「全部」否则原值, "keyword": keyword 或空串}}

公开 函数 课文页面 learner lesson? current_role? auth_mode? subject?
  返回 教材页「载入」（地址 #教材?lesson=… 进来时前端调它，动作 lesson_one）的整页状态：正常 {reading, examples, lesson_items, lessons, series_options, series_head, lesson_count, form}（lessons/series_options/series_head/lesson_count/form 同 教材页面 的默认形态：当前系列全部课文、等级全部、关键字空，form 回填 {series: 当前系列编号, lesson_level: 「全部」, keyword: 空串}）；没有这一课不报错，只回 {reading, form}（旧行为）
  报错 400 lesson 不能为空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 lesson 为空，报错 400 lesson 不能为空
  伪代码 调用 取当前系列 learner=learner subject=subject_id 得当前系列；调用 取课文 code=lesson subject=subject_id，查不到（返回空，包括属于别的科目的课，文案与不存在相同）则返回 {"reading": {"code": lesson, "missing": "没有这一课（{lesson}），回课文表重新选。", "back": "#%E6%95%99%E6%9D%90"}, "form": {"series": 当前系列编号, "lesson_level": "全部", "keyword": ""}}，不报错
  伪代码 有这一课：题数 n 取题数表（题数表 subject_id=subject_id）中 lesson_code 相等的 n（没有为 0）；reading={"code": code, "level": level, "title": title, "summary": summary 或空串, "formation": connection 或空串, "explanation": explain 或空串, "qcount": n, "head": "《{title}》　{level}　第{N}课（{code}）", "series": series_code, "series_label": 系列名（调 列系列 找 series_code 的 name，找不到用 series_code）, "practice": n 大于 0 则 #%E5%81%9A%E9%A2%98?lesson={code} 否则空串, "quiz_note": n 大于 0 则「这一课有 {n} 道题」否则「这一课还没有题，可以先问老师」, "ask": "#%E9%97%AE%E8%80%81%E5%B8%88", "explain": "#%E9%97%AE%E8%80%81%E5%B8%88?lesson={code}", "back": "#%E6%95%99%E6%9D%90", "missing": 空串}；N 为 seq 不为 0 时取 seq，否则取课号末三位转成整数（不足三位按整体数字）
  伪代码 examples：该课 examples 字段（日语^^中文@@日语^^中文）按 @@ 拆句、每句按 ^^ 拆，恰好两段收 {jp, zh}，拆不出两段的跳过（坏了当没有例句，不报错）
  伪代码 lesson_items：调用 取课文关联条目 lesson_code=lesson 得 items，逐条转 {code, label: name, point_label: 调用 kg.取知识点 code=point_code 取 title（取不到用 point_code）}；再把 point_codes 按英文逗号拆开的每个直接挂知识点追加 {code: 点编号, label: （整个知识点）, point_label: 该点 title（取不到用编号）}（旧口径：排在条目后面）
  伪代码 lessons/series_options/series_head/lesson_count/form 按 教材页面 的默认形态拼（series 入参为空、lesson_level=「全部」、keyword 空串）；返回 {"reading": reading, "examples": 例句列表, "lesson_items": 条目列表, "lessons": 行列表, "series_options": 选项列表, "series_head": 当前系列 name, "lesson_count": "共{total}课", "form": {"series": 当前系列编号, "lesson_level": "全部", "keyword": ""}}

函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（need 不传按 read；need=write 时登录模式下只有负责/协作教师通过，否则 解析科目 报 403 没有权限修改该科目、原样抛出；四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出）

函数 编号前缀检查 subject_id code
  返回 {ok}
  报错 400 编号要以「<编码>.」开头
  伪代码 subject_id 等于 1（日语）：直接返回 {"ok": 1}，旧编号不动
  伪代码 否则按 subject_id 查 subject_info 的 code（科目编码，查询 lesson_subject_code）；编码为空、或 code 不匹配 ^[a-z][a-z0-9_]*\.[A-Za-z0-9_-]+$、或 code 不以「<编码>.」开头，报错 400 编号要以「<编码>.」开头（文案里的 <编码> 换成真实编码）
  伪代码 返回 {"ok": 1}

## 接口
GET /lesson/series -> 列系列
GET /lesson/series/current -> 取当前系列
POST /lesson/series/select -> 选择系列
GET /lesson/list -> 列课文
POST /lesson/list -> 教材页面 动作 lesson_list 模板 页面状态 表单=form 角色 student
GET /lesson/detail -> 取课文
POST /lesson/one -> 课文页面 动作 lesson_one 模板 页面状态 表单=form 角色 student
GET /lesson/by-item -> 按条目列课文
GET /lesson/by-point -> 按知识点列课文
GET /lesson/items -> 取课文关联条目
GET /lesson/point-level -> 取知识点等级
POST /lesson/import -> 导入课文 上传 file 类型 md,txt 上限 20MB 角色 teacher
POST /lesson/series/withdraw -> 撤下系列 角色 teacher

## 内容文件
content/lesson/series/{series_code}.jsonl 字段 code,level,title,summary,explain,connection,examples,examples_edited,orig_title,seq,item_codes,point_codes；写：本模块函数 写入系列课文并重灌；读：本模块函数 写入系列课文并重灌；系列课文的源数据，库按它重灌
content/lesson/series/{series_code}.withdrawn.jsonl 字段 code,level,title,summary,explain,connection,examples,examples_edited,orig_title,seq,item_codes,point_codes；写：本模块函数 撤下系列；读：无；撤下后留着的系列课文

## 用例
用例 列系列_只含可用
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=old name=旧教材 sort_order=-1
  先 数据 lesson_series code=b name=乙教材 sort_order=0
  调用 列系列
  得 total=2

用例 列系列_空库
  调用 列系列
  得 total=0

用例 取当前系列_默认
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  调用 取当前系列 learner=me
  得 series_code=hanabira name=Hanabira is_default=1

用例 取当前系列_选过
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=b name=乙教材 sort_order=2
  先 调用 选择系列 learner=me series_code=b
  调用 取当前系列 learner=me
  得 series_code=b name=乙教材 is_default=0

用例 取当前系列_所选已撤下回默认
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=b name=乙教材 sort_order=-1
  先 数据 lesson_pref learner=me series_code=b
  调用 取当前系列 learner=me
  得 series_code=hanabira is_default=1

用例 选择系列_正常覆盖
  先 数据 lesson_series code=a name=甲 sort_order=1
  先 数据 lesson_series code=b name=乙 sort_order=2
  先 调用 选择系列 learner=me series_code=a
  调用 选择系列 learner=me series_code=b
  得 ok=1 series_code=b
  库 lesson_pref 共 1 行
  库 lesson_pref 含 learner=me series_code=b

用例 选择系列_已撤下
  先 数据 lesson_series code=b name=乙 sort_order=-1
  调用 选择系列 learner=me series_code=b
  报错 404
  库 lesson_pref 共 0 行

用例 列课文_按系列和等级
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=L2 level=N4 title=第二课 examples_edited=0 series_code=a seq=2
  先 数据 lesson_text code=L3 level=N5 title=第三课 examples_edited=0 series_code=b seq=1
  调用 列课文 series_code=a level=N5
  得 total=1

用例 列课文_关键字
  先 数据 lesson_text code=L1 level=N5 title=は和が examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=L2 level=N5 title=に和で examples_edited=0 series_code=a seq=2
  调用 列课文 keyword=に和
  得 total=1

用例 列课文_关键字搜条目名
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=L2 level=N5 title=に和で examples_edited=0 series_code=a seq=2
  先 数据 kg_item code=I1 name=は～です point_code=P1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  调用 列课文 keyword=は～です
  得 total=1

用例 列课文_无匹配
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=a seq=1
  调用 列课文 series_code=zzz
  得 total=0

用例 取课文_正常
  先 数据 lesson_text code=L1 level=N5 title=第一课 explain=讲解内容 examples_edited=0 series_code=a seq=3
  先 数据 lesson_point_link lesson_code=L1 point_code=P1
  先 数据 lesson_point_link lesson_code=L1 point_code=P2
  调用 取课文 code=L1
  得 code=L1 level=N5 title=第一课 explain=讲解内容 series_code=a seq=3 point_codes=P1,P2

用例 取课文_不存在
  调用 取课文 code=NOPE
  得 为空

用例 按条目列课文_正常
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=a seq=2
  先 数据 lesson_text code=L2 level=N5 title=第二课 examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=L3 level=N5 title=第三课 examples_edited=0 series_code=a seq=3
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  先 数据 lesson_item_link lesson_code=L2 item_code=I1
  调用 按条目列课文 item_code=I1
  得 item_code=I1 total=2

用例 按条目列课文_没有条目
  调用 按条目列课文 item_code=NOPE
  报错 404

用例 按知识点列课文_正常
  先 数据 kg_point code=P1 title=助词
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=a seq=1
  先 数据 lesson_point_link lesson_code=L1 point_code=P1
  调用 按知识点列课文 point_code=P1
  得 point_code=P1 total=1

用例 按知识点列课文_没有知识点
  调用 按知识点列课文 point_code=NOPE
  报错 404

用例 取课文关联条目_正常
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 kg_item code=I2 name=が point_code=P1
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=a seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  先 数据 lesson_item_link lesson_code=L1 item_code=I2
  调用 取课文关联条目 lesson_code=L1
  得 lesson_code=L1 total=2

用例 取课文关联条目_没有这课
  调用 取课文关联条目 lesson_code=NOPE
  报错 404

用例 取知识点等级_取最基础
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 lesson_text code=L1 level=N4 title=第一课 examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=L2 level=N5 title=第二课 examples_edited=0 series_code=a seq=2
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  先 数据 lesson_point_link lesson_code=L2 point_code=P1
  调用 取知识点等级 point_code=P1
  得 point_code=P1 level=N5 lesson_count=2

用例 取知识点等级_无课文
  先 数据 kg_point code=P1 title=助词
  调用 取知识点等级 point_code=P1
  得 lesson_count=0

用例 取知识点等级_没有知识点
  调用 取知识点等级 point_code=NOPE
  报错 404

用例 导入课文_正常新建系列
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 文件 imports/a.md 内容=L1|N5|标题一|一句话|讲解|接续|例句A^^中文A@@例句B^^中文B|0|原标题|1|I1|P1
  调用 导入课文 series_code=a file_path=imports/a.md series_name=甲教材
  得 ok=1 series_code=a total=1 item_links=1 point_links=1
  库 lesson_series 含 code=a name=甲教材 sort_order=100
  库 lesson_text 共 1 行
  库 lesson_text 含 code=L1 level=N5 title=标题一 series_code=a seq=1 examples_edited=0
  库 lesson_item_link 含 lesson_code=L1 item_code=I1
  库 lesson_point_link 含 lesson_code=L1 point_code=P1

用例 导入课文_只清空本系列且偏好保留
  先 数据 lesson_series code=a name=甲 sort_order=1
  先 数据 lesson_series code=b name=乙 sort_order=2
  先 数据 lesson_text code=OLD1 level=N5 title=旧一 examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=B1 level=N5 title=乙一 examples_edited=0 series_code=b seq=1
  先 数据 lesson_point_link lesson_code=OLD1 point_code=P1
  先 数据 lesson_point_link lesson_code=B1 point_code=P1
  先 数据 lesson_pref learner=me series_code=a
  先 文件 imports/a.md 内容=L1|N5|新一
  调用 导入课文 series_code=a file_path=imports/a.md
  得 ok=1 total=1 item_links=0 point_links=0
  库 lesson_text 共 2 行
  库 lesson_text 无 code=OLD1
  库 lesson_text 含 code=B1 series_code=b
  库 lesson_text 含 code=L1 series_code=a seq=0 examples_edited=0
  库 lesson_point_link 共 1 行
  库 lesson_point_link 含 lesson_code=B1 point_code=P1
  库 lesson_pref 含 learner=me series_code=a
  库 lesson_series 含 code=a name=甲 sort_order=1

用例 导入课文_映射对不上整批不写
  先 数据 lesson_series code=a name=甲 sort_order=1
  先 数据 lesson_text code=OLD1 level=N5 title=旧一 examples_edited=0 series_code=a seq=1
  先 文件 imports/a.md 内容=L1|N5|新一|||||||||NOPE
  调用 导入课文 series_code=a file_path=imports/a.md
  报错 400
  库 lesson_text 共 1 行
  库 lesson_text 含 code=OLD1

用例 导入课文_课号与其他系列重复
  先 数据 lesson_series code=b name=乙 sort_order=2
  先 数据 lesson_text code=L1 level=N5 title=乙一 examples_edited=0 series_code=b seq=1
  先 文件 imports/a.md 内容=L1|N5|新一
  调用 导入课文 series_code=a file_path=imports/a.md
  报错 400
  库 lesson_text 共 1 行
  库 lesson_text 含 code=L1 series_code=b

用例 导入课文_等级非法
  先 文件 imports/a.md 内容=L1|N9|新一
  调用 导入课文 series_code=a file_path=imports/a.md
  报错 400
  库 lesson_text 共 0 行
  库 lesson_series 共 0 行

用例 导入课文_空文件
  先 文件 imports/a.md 内容=#只有注释
  调用 导入课文 series_code=a file_path=imports/a.md
  报错 400

用例 导入课文_series_code为空
  先 文件 imports/a.md 内容=L1|N5|新一
  调用 导入课文 series_code=空 file_path=imports/a.md
  报错 400

用例 写入系列课文并重灌_正常新建系列
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  调用 写入系列课文并重灌 series_code=a rows_json=[{"code":"L1","level":"N5","title":"标题一","summary":"一句话","explain":"讲解","connection":"接续","examples":"例句A^^中文A","examples_edited":0,"orig_title":"原标题","seq":1,"item_codes":["I1"],"point_codes":["P1"]}] series_name=甲教材
  得 ok=1 series_code=a total=1 imported=1 item_links=1 point_links=1 file_rows=1
  库 lesson_series 含 code=a name=甲教材 sort_order=100
  库 lesson_text 共 1 行
  库 lesson_text 含 code=L1 level=N5 title=标题一 series_code=a seq=1 examples_edited=0
  库 lesson_item_link 含 lesson_code=L1 item_code=I1
  库 lesson_point_link 含 lesson_code=L1 point_code=P1

用例 写入系列课文并重灌_再写一遍覆盖且只动本系列
  先 数据 lesson_series code=a name=甲 sort_order=1
  先 数据 lesson_series code=b name=乙 sort_order=2
  先 数据 lesson_text code=OLD1 level=N5 title=旧一 examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=B1 level=N5 title=乙一 examples_edited=0 series_code=b seq=1
  先 数据 lesson_point_link lesson_code=B1 point_code=P1
  先 数据 lesson_pref learner=me series_code=a
  调用 写入系列课文并重灌 series_code=a rows_json=[{"code":"L1","level":"N5","title":"新一","seq":1}]
  得 ok=1 total=1 imported=1 item_links=0 point_links=0 file_rows=1
  库 lesson_text 共 2 行
  库 lesson_text 无 code=OLD1
  库 lesson_text 含 code=B1 series_code=b
  库 lesson_text 含 code=L1 series_code=a
  库 lesson_point_link 含 lesson_code=B1 point_code=P1
  库 lesson_pref 含 learner=me series_code=a
  库 lesson_series 含 code=a name=甲 sort_order=1

用例 写入系列课文并重灌_引用不存在的条目整行拒收
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  调用 写入系列课文并重灌 series_code=a rows_json=[{"code":"L1","level":"N5","title":"好","seq":1,"item_codes":["I1"],"point_codes":["P1"]},{"code":"L2","level":"N5","title":"坏","seq":2,"item_codes":["NOPE"],"point_codes":[]},{"code":"L3","level":"N4","title":"坏二","seq":3,"item_codes":[],"point_codes":["NOP"]}]
  得 ok=1 total=3 imported=1 item_links=1 point_links=1 file_rows=3
  库 lesson_text 共 1 行
  库 lesson_text 含 code=L1 series_code=a
  库 lesson_text 无 code=L2
  库 lesson_item_link 共 1 行

用例 写入系列课文并重灌_等级非法
  调用 写入系列课文并重灌 series_code=a rows_json=[{"code":"L1","level":"N9","title":"新一"}]
  报错 400
  库 lesson_text 共 0 行
  库 lesson_series 共 0 行

用例 写入系列课文并重灌_课号与其他系列重复
  先 数据 lesson_series code=b name=乙 sort_order=2
  先 数据 lesson_text code=L1 level=N5 title=乙一 examples_edited=0 series_code=b seq=1
  调用 写入系列课文并重灌 series_code=a rows_json=[{"code":"L1","level":"N5","title":"新一"}]
  报错 400
  库 lesson_text 共 1 行
  库 lesson_text 含 code=L1 series_code=b

用例 写入系列课文并重灌_series_code为空
  调用 写入系列课文并重灌 series_code=空 rows_json=[{"code":"L1","level":"N5","title":"新一"}]
  报错 400

用例 撤下系列_写入后挪文件并清库
  先 调用 写入系列课文并重灌 series_code=a rows_json=[{"code":"L1","level":"N5","title":"甲一","seq":1}]
  调用 撤下系列 series_code=a
  得 ok=1 series_code=a removed_lessons=1 moved=1
  库 lesson_text 共 0 行
  库 lesson_series 含 code=a sort_order=-1

用例 撤下系列_第二次没有文件可挪
  先 调用 写入系列课文并重灌 series_code=a rows_json=[{"code":"L1","level":"N5","title":"甲一","seq":1}]
  先 调用 撤下系列 series_code=a
  调用 撤下系列 series_code=a
  得 ok=1 removed_lessons=0 moved=0

用例 撤下系列_正常
  先 数据 lesson_series code=a name=甲 sort_order=1
  先 数据 lesson_series code=b name=乙 sort_order=2
  先 数据 lesson_text code=L1 level=N5 title=甲一 examples_edited=0 series_code=a seq=1
  先 数据 lesson_text code=L2 level=N5 title=甲二 examples_edited=0 series_code=a seq=2
  先 数据 lesson_text code=B1 level=N5 title=乙一 examples_edited=0 series_code=b seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  先 数据 lesson_point_link lesson_code=B1 point_code=P1
  先 数据 lesson_pref learner=me series_code=a
  调用 撤下系列 series_code=a
  得 ok=1 series_code=a removed_lessons=2
  库 lesson_text 共 1 行
  库 lesson_item_link 共 0 行
  库 lesson_point_link 共 1 行
  库 lesson_series 含 code=a sort_order=-1
  库 lesson_pref 含 learner=me series_code=a

用例 撤下系列_没有这个系列
  调用 撤下系列 series_code=NOPE
  报错 404

用例 教材页面_默认系列
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 lesson_text code=L1 level=N5 title=第一课 summary=一句话 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  调用 教材页面 learner=me
  得 series_head=Hanabira lesson_count=共1课
  库 lesson_pref 共 0 行

用例 教材页面_选系列记偏好
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=b name=乙教材 sort_order=2
  先 数据 lesson_text code=B1 level=N4 title=乙一 examples_edited=0 series_code=b seq=1
  调用 教材页面 learner=me series=b
  得 series_head=乙教材 lesson_count=共1课
  库 lesson_pref 含 learner=me series_code=b

用例 教材页面_系列不在下拉不改偏好
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=b name=乙教材 sort_order=-1
  先 数据 lesson_pref learner=me series_code=hanabira
  调用 教材页面 learner=me series=b
  得 series_head=Hanabira
  库 lesson_pref 含 learner=me series_code=hanabira

用例 课文页面_正常
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 kg_point code=P1 title=助词
  先 数据 kg_item code=I1 name=は point_code=P1
  先 数据 lesson_text code=L1 level=N5 title=第一课 summary=一句话 explain=讲解内容 examples_edited=0 series_code=hanabira seq=46
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  调用 课文页面 learner=me lesson=L1
  得 series_head=Hanabira lesson_count=共1课

用例 课文页面_没有这一课不报错
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  调用 课文页面 learner=me lesson=NOPE
  得 有返回

用例 课文页面_lesson为空
  调用 课文页面 learner=me
  报错 400

用例 跨科目_列系列只看本科目
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  调用 列系列 subject=2
  得 total=1

用例 跨科目_不传科目是日语
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  调用 列系列
  得 total=1

用例 跨科目_取当前系列非日语没有系列
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  调用 取当前系列 learner=me subject=2
  得 series_code=空 is_default=1

用例 跨科目_取当前系列非日语取本科目第一个
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  调用 取当前系列 learner=me subject=2
  得 series_code=math.s name=数学教材 is_default=1

用例 跨科目_选择系列别的科目的系列404
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  调用 选择系列 learner=me series_code=hanabira subject=2
  报错 404

用例 跨科目_选择系列偏好落当前科目
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  调用 选择系列 learner=me series_code=math.s subject=2
  得 ok=1
  库 lesson_pref 含 learner=me series_code=math.s subject_id=2

用例 跨科目_列课文只看本科目
  先 数据 lesson_text code=L1 level=N5 title=甲 series_code=hanabira seq=1
  先 数据 lesson_text code=math.L1 level=N5 title=乙 series_code=math.s seq=1 subject_id=2
  调用 列课文 subject=2
  得 total=1

用例 跨科目_取课文别的科目当不存在
  先 数据 lesson_text code=math.L1 level=N5 title=乙 series_code=math.s seq=1 subject_id=2
  调用 取课文 code=math.L1
  得 为空

用例 跨科目_取课文本科目
  先 数据 lesson_text code=math.L1 level=N5 title=乙 series_code=math.s seq=1 subject_id=2
  调用 取课文 code=math.L1 subject=2
  得 code=math.L1 title=乙

用例 跨科目_取课文关联条目别的科目404
  先 数据 lesson_text code=math.L1 level=N5 title=乙 series_code=math.s seq=1 subject_id=2
  调用 取课文关联条目 lesson_code=math.L1
  报错 404

用例 跨科目_按条目列课文别的科目的条目404
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 按条目列课文 item_code=math.i1
  报错 404

用例 跨科目_取知识点等级别的科目的点404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 取知识点等级 point_code=math.a
  报错 404

用例 跨科目_导入课文落当前科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 文件 imports/m.md 内容=math.L1|N5|标题一|一句话|讲解|接续|例句A^^中文A|0|原标题|1|math.i1|math.a
  调用 导入课文 series_code=math.s file_path=imports/m.md series_name=数学教材 subject=2
  得 ok=1 total=1 item_links=1 point_links=1
  库 lesson_series 含 code=math.s subject_id=2
  库 lesson_text 含 code=math.L1 series_code=math.s subject_id=2
  库 lesson_item_link 含 lesson_code=math.L1 item_code=math.i1 subject_id=2
  库 lesson_point_link 含 lesson_code=math.L1 point_code=math.a subject_id=2

用例 跨科目_导入课文前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 文件 imports/m2.md 内容=L1|N5|标题一|一句话|讲解|接续|例句A^^中文A|0|原标题|1||math.a
  调用 导入课文 series_code=math.s file_path=imports/m2.md subject=2
  报错 400
  库 lesson_text 共 0 行
  库 lesson_series 共 0 行

用例 跨科目_导入课文映射在别的科目对不上
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=甲
  先 文件 imports/m3.md 内容=math.L1|N5|标题一|一句话|讲解|接续|例句A^^中文A|0|原标题|1||P1
  调用 导入课文 series_code=math.s file_path=imports/m3.md subject=2
  报错 400
  库 lesson_text 共 0 行

用例 跨科目_导入课文课号被别的科目占用
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 lesson_text code=math.L1 level=N5 title=旧 series_code=other seq=1 subject_id=1
  先 文件 imports/m4.md 内容=math.L1|N5|标题一|一句话|讲解|接续|例句A^^中文A|0|原标题|1||
  调用 导入课文 series_code=math.s file_path=imports/m4.md subject=2
  报错 400
  库 lesson_text 共 1 行

用例 跨科目_导入课文系列编号被别的科目占用
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 lesson_series code=math.s name=占用 sort_order=1 subject_id=1
  先 文件 imports/m5.md 内容=math.L1|N5|标题一|一句话|讲解|接续|例句A^^中文A|0|原标题|1||
  调用 导入课文 series_code=math.s file_path=imports/m5.md subject=2
  报错 400
  库 lesson_text 共 0 行

用例 跨科目_写入系列课文并重灌落当前科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 写入系列课文并重灌 series_code=math.s rows_json=[{"code":"math.L1","level":"N5","title":"标题一","summary":"一句话","explain":"讲解","connection":"接续","examples":"例句A^^中文A","examples_edited":0,"orig_title":"原标题","seq":1,"item_codes":["math.i1"],"point_codes":["math.a"]}] series_name=数学教材 subject=2
  得 ok=1 total=1 imported=1 item_links=1 point_links=1
  库 lesson_series 含 code=math.s subject_id=2
  库 lesson_text 含 code=math.L1 subject_id=2
  库 lesson_item_link 含 lesson_code=math.L1 item_code=math.i1 subject_id=2

用例 跨科目_写入系列课文并重灌前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 写入系列课文并重灌 series_code=math.s rows_json=[{"code":"L1","level":"N5","title":"标题一","summary":"","explain":"","connection":"","examples":"","examples_edited":0,"orig_title":"","seq":1,"item_codes":[],"point_codes":[]}] subject=2
  报错 400
  库 lesson_text 共 0 行

用例 跨科目_撤下系列别的科目404
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  调用 撤下系列 series_code=hanabira subject=2
  报错 404
  库 lesson_series 含 code=hanabira sort_order=1

用例 跨科目_教材页面只见本科目的系列和课文
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_text code=L1 level=N5 title=甲 series_code=hanabira seq=1
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  先 数据 lesson_text code=math.L1 level=N5 title=乙 series_code=math.s seq=1 subject_id=2
  调用 教材页面 learner=me subject=2
  得 series_head=数学教材 lesson_count=共1课

用例 跨科目_课文页面别的科目的课不报错
  先 数据 lesson_series code=hanabira name=Hanabira sort_order=1
  先 数据 lesson_text code=L1 level=N5 title=甲 series_code=hanabira seq=1
  调用 课文页面 learner=me lesson=L1 subject=2
  得 有返回

用例 跨科目_need_导入课文公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 imports/n1.md 内容=math.L1|N5|标题一|一句话|讲解|接续|例句A^^中文A|0|原标题|1||
  调用 导入课文 series_code=math.s file_path=imports/n1.md learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 lesson_text 共 0 行
  库 lesson_series 共 0 行

用例 跨科目_need_导入课文协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 文件 imports/n2.md 内容=math.L1|N5|标题一|一句话|讲解|接续|例句A^^中文A|0|原标题|1||
  调用 导入课文 series_code=math.s file_path=imports/n2.md series_name=数学教材 learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 total=1
  库 lesson_text 含 code=math.L1 subject_id=2

用例 跨科目_need_写入系列课文并重灌公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 写入系列课文并重灌 series_code=math.s rows_json=[{"code":"math.L1","level":"N5","title":"标题一","summary":"","explain":"","connection":"","examples":"","examples_edited":0,"orig_title":"","seq":1,"item_codes":[],"point_codes":[]}] learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 lesson_text 共 0 行

用例 跨科目_need_撤下系列公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  调用 撤下系列 series_code=math.s learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 lesson_series 含 code=math.s sort_order=1

用例 跨科目_need_撤下系列协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  调用 撤下系列 series_code=math.s learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 series_code=math.s
  库 lesson_series 含 code=math.s sort_order=-1

用例 跨科目_need_选择系列仍是读_公共科目教师照常
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 lesson_series code=math.s name=数学教材 sort_order=1 subject_id=2
  调用 选择系列 learner=t2 series_code=math.s current_role=teacher auth_mode=on subject=2
  得 ok=1
