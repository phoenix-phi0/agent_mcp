模块 kg
依赖 subject

## 表
表 kg_point
  code 文本 知识点编号，在 kg_point 表内全局唯一（跨科目不重号：由「<科目编码>.」前缀口径 2 + 导入时的跨科目同编号拒绝保证；所以别的模块按 point_code 查表不会撞到别科目的点；只要求知识点表内唯一，不要求与 kg_item 的条目编号跨表不重）；非日语科目要以「<科目编码>.」开头
  title 文本 中文名
  subject_id 整数 所属科目，默认 1（1 是日语语法；口径说明，各模块通用：kg/lesson/quiz/textbook_import 的编号前缀豁免和 tutor 的等级文案里写的「日语 subject_id 等于 1」，约定 1 号即 jp_grammar，由迁移脚本保证（migrate_subject.py 建 1 号科目），所以直接按 id=1 判断，不再查 subject_info）
表 kg_edge
  pre_code 文本 前置知识点编号（学后续之前要先会它）
  point_code 文本 后续知识点编号
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 kg_contrast
  a_code 文本 对照一端编号（知识点或表达方式条目，不加外键）；两端按字符串大小规范化，小的放 a_code
  b_code 文本 对照另一端编号
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 kg_item
  code 文本 条目编号，在 kg_item 表内全局唯一（同上：前缀口径 2 + 导入条目的跨科目同编号拒绝；只要求条目表内唯一，不要求与 kg_point 的知识点编号跨表不重）；非日语科目要以「<科目编码>.」开头
  name 文本 条目名称
  point_code 文本 所属知识点（结构点）编号
  after_form 文本 接在哪个形式后，可空
  prev_code 文本 前一个条目编号（只用来排学习顺序），可空
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 页面字段
页面 kg_manage_view 图谱管理页面
  kgp_orig 文本 知识点表行键（原编号）；「编辑知识点」浮层地址带它，新建时为空
  kgp_code 文本 知识点编号（新建时填，建后不可改）
  kgp_title 文本 知识点名称
  kgp_item_n 整数 知识点表「条目数」列
  kgp_pre_n 整数 知识点表「前置数」列
  kgp_next_n 整数 知识点表「后续数」列
  kgp_refs 文本 编辑浮层里的「被引用」说明（只读）
  kgi_orig 文本 条目表行键（原编号）；「编辑条目」浮层地址带它，新建时为空
  kgi_code 文本 条目编号（新建时填，建后不可改）
  kgi_name 文本 条目名称
  kgi_point 文本 所属知识点编号（下拉，选项来自 point_options）
  kgi_point_title 文本 条目表「所属知识点」列（显示名）
  kgi_after 文本 接在哪个形式后，可空
  kgi_prev 文本 前一个条目编号，可空
  edge_key 文本 前置边表行键「前置编号>后续编号」（行动作只能带一个键，两端拼成一个）
  edge_pre 文本 前置知识点编号（下拉）
  edge_point 文本 后续知识点编号（下拉）
  edge_pre_title 文本 前置边表「前置」列（显示名）
  edge_point_title 文本 前置边表「后续」列（显示名）
  ct_key 文本 对照表行键「a_code~b_code」（同上，单键）
  ct_a 文本 对照一端编号
  ct_b 文本 对照另一端编号
  ct_a_label 文本 对照表「一端」列（编号加名称）
  ct_b_label 文本 对照表「另一端」列（编号加名称）
  imp_kind 枚举 知识点,条目,前置边,对照 导入类型
  imp_upload 文件 导入文件（.md/.txt 用 | 分隔，.csv 首行表头，.json 对象列表）
  imp_file 文本 预检时存下的文件路径（确认导入时原样回传；只能是 uploads/ 下的一个文件，即上传时「存文件」给的 uploads/<哈希>.<扩展名>，改成别的路径确认时报 400 导入文件路径不对；引擎没有只读修饰，页面上做成随 imp_ok 显隐的普通字段，提示「预检时存下的文件，不用改」）
  imp_line 整数 预检表「行号」列
  imp_code 文本 预检表「编号」列
  imp_label 文本 预检表「内容」列
  imp_action 文本 预检表「结果」列（新增/更新/报错）
  imp_reason 文本 预检表「说明」列
  imp_head 文本 预检结果抬头
  exp_kind 枚举 全部,知识点,条目,前置边,对照 导出类型
  export_text 长文本 导出文本（与导入同格式，可直接再导入）
  kgm_head 文本 页面抬头
  kgm_role 文本 我的身份（负责/协作/公共只读/单人）

## 函数
公开 函数 取知识点 code learner? current_role? auth_mode? subject?
  返回 {id, code, title}；查不到返回空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 code 和 subject_id 查 kg_point 一行（别的科目的编号当不存在）
  伪代码 查不到则返回空
  伪代码 返回 {"id": id, "code": code, "title": title}

公开 函数 列知识点 learner? current_role? auth_mode? subject?
  返回 {total, points}，points 是 [{code, title}]，按 id 升序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 查 kg_point 中 subject_id 相等的行，按 id 升序
  伪代码 返回 {"total": 行数, "points": 列表}

公开 函数 列前置 code learner? current_role? auth_mode? subject?
  返回 {code, total, points}，points 是该节点直接前置 [{code, title}]
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 code 和 subject_id 查 kg_point，查不到（包括编号属于别的科目）报错 404 没有这个知识点
  伪代码 查 kg_edge 中 subject_id 相等且 point_code=code 的行，取每行 pre_code，连同科目的 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列后续 code learner? current_role? auth_mode? subject?
  返回 {code, total, points}，points 是该节点直接后续 [{code, title}]
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 code 和 subject_id 查 kg_point，查不到（包括编号属于别的科目）报错 404 没有这个知识点
  伪代码 查 kg_edge 中 subject_id 相等且 pre_code=code 的行，取每行 point_code，连同科目的 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列祖先 code learner? current_role? auth_mode? subject?
  返回 {code, total, points}，points 是该节点全部祖先（直接和间接前置，去重，不含自己）[{code, title}]
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 code 和 subject_id 查 kg_point，查不到（包括编号属于别的科目）报错 404 没有这个知识点
  伪代码 从 code 出发，只沿本科目的 kg_edge 的 point_code→pre_code 方向逐层向上取前置，已访问过的不再入队，直到没有新节点
  伪代码 把访问到的节点（不含 code 自己）连同科目的 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列后代 code learner? current_role? auth_mode? subject?
  返回 {code, total, points}，points 是该节点全部后代（直接和间接后续，去重，不含自己）[{code, title}]
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 code 和 subject_id 查 kg_point，查不到（包括编号属于别的科目）报错 404 没有这个知识点
  伪代码 从 code 出发，只沿本科目的 kg_edge 的 pre_code→point_code 方向逐层向下取后续，已访问过的不再入队，直到没有新节点
  伪代码 把访问到的节点（不含 code 自己）连同科目的 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列根节点 learner? current_role? auth_mode? subject?
  返回 {total, points}，points 是没有任何前置的知识点 [{code, title}]
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 取本科目 kg_point 中 code 不出现在本科目 kg_edge.point_code 里的行，按 id 升序
  伪代码 返回 {"total": 个数, "points": 列表}

公开 函数 列分层 learner? current_role? auth_mode? subject?
  返回 {layer_count, layers}，layers 是 [{depth, points}]，points 是 [{code, title}]；节点的 depth = 0（无前置）或 其所有直接前置 depth 的最大值 + 1（按依赖深度分层）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 取本科目的 kg_point 和 kg_edge
  伪代码 无前置的节点 depth=0；其余节点 depth = 其全部前置 depth 最大值 + 1（图无环，按拓扑顺序算）
  伪代码 按 depth 升序分组，组内按 id 升序
  伪代码 返回 {"layer_count": 层数, "layers": 列表}；没有知识点时 layer_count=0，layers 为空列表

公开 函数 加前置边 pre_code point_code learner? current_role? auth_mode? subject?
  返回 {ok, created}，created 为 1 表示新加，0 表示这条边已存在
  报错 400 编号不能为空
  报错 400 不能以自己为前置
  报错 404 没有这个知识点
  报错 400 这条边会形成环
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 pre_code 或 point_code 为空，报错 400 编号不能为空
  伪代码 pre_code 等于 point_code，报错 400 不能以自己为前置
  伪代码 pre_code 或 point_code 不在本科目的 kg_point（包括属于别的科目），报错 404 没有这个知识点
  伪代码 本科目 kg_edge 已有 (pre_code, point_code)，返回 {"ok": 1, "created": 0}
  伪代码 环检查：从 point_code 沿本科目的 kg_edge 向下取全部后代，若包含 pre_code，报错 400 这条边会形成环
  伪代码 往 kg_edge 插入一行 (pre_code, point_code, subject_id)
  伪代码 返回 {"ok": 1, "created": 1}

公开 函数 导出图 learner? current_role? auth_mode? subject?
  返回 {point_count, edge_count, contrast_count, points, edges, contrasts}；points 是 [{code, title}]，edges 是 [{pre_code, point_code}]，contrasts 是 [{a_code, b_code}]
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 分别查 kg_point、kg_edge、kg_contrast 中 subject_id 相等的行，按 id 升序
  伪代码 返回三个列表和各自行数

公开 函数 取条目 code learner? current_role? auth_mode? subject?
  返回 {id, code, name, point_code, after_form, prev_code}；查不到返回空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 code 查 kg_item 一行
  伪代码 查不到则返回空
  伪代码 返回该行各字段

公开 函数 列条目 learner? current_role? auth_mode? subject?
  返回 {total, items}，items 是 [{code, name, point_code, after_form, prev_code}]，按 id 升序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 查 kg_item 中 subject_id 相等的行，按 id 升序
  伪代码 返回 {"total": 行数, "items": 列表}

公开 函数 按知识点列条目 point_code learner? current_role? auth_mode? subject?
  返回 {point_code, total, items}，items 同「列条目」
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 point_code 查 kg_point，查不到报错 404 没有这个知识点
  伪代码 查 kg_item 中 subject_id 相等且 point_code 相等的行，按 id 升序
  伪代码 返回 {"point_code": point_code, "total": 行数, "items": 列表}

公开 函数 列对照 code? learner? current_role? auth_mode? subject?
  返回 {total, contrasts}，contrasts 是 [{a_code, b_code}]
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 code 为空：查 kg_contrast 中 subject_id 相等的行，按 id 升序
  伪代码 code 不为空：只取 subject_id 相等且 a_code=code 或 b_code=code 的行（对照无向，任一端匹配都算）
  伪代码 返回 {"total": 行数, "contrasts": 列表}

公开 函数 核对条目存在 codes learner? current_role? auth_mode? subject?
  返回 {ok, missing_count, missing}；codes 是用英文逗号隔开的编号，每个编号在 kg_item 或 kg_point 里有就算存在；ok 为 1 表示全部存在；missing 是不存在的编号用英文逗号连起来
  报错 400 codes 不能为空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 codes 为空，报错 400 codes 不能为空
  伪代码 按英文逗号拆开，去掉空白项
  伪代码 逐个编号在本科目的 kg_item 和 kg_point 里查，两张表都没有（包括属于别的科目）的记入 missing
  伪代码 返回 {"ok": missing 为空则 1 否则 0, "missing_count": 个数, "missing": 逗号连接}

公开 函数 导入知识点 file_path learner? current_role? auth_mode? subject?
  返回 {ok, total, created, updated}
  报错 400 导入文件有错
  报错 400 编号要以「<编码>.」开头
  报错 400 编号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「编号|中文名」，用 | 分隔；编号或中文名为空、或没有 | 就报错 400 导入文件有错（整批不写）
  伪代码 编号前缀：每行编号都调用本模块 编号前缀检查 subject_id=subject_id code=编号，不符报错 400 编号要以「<编码>.」开头（整批不写）；日语（subject_id 等于 1）豁免
  伪代码 编号全局唯一（知识点表内、跨科目）：编号已在 kg_point 但属于别的科目（subject_id 不相等），报错 400 编号已被其他科目使用（整批不写）；只查 kg_point，不查 kg_item（不要求跨表唯一）
  伪代码 在一个事务里：逐行按 code 查 kg_point，没有则插入 (code, title, subject_id) 并 created+1，有则（必然是本科目的）更新 title 并 updated+1
  伪代码 同一文件里重复的编号后一行覆盖前一行（按已存在算更新）
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

公开 函数 导入条目 file_path learner? current_role? auth_mode? subject?
  返回 {ok, total, created, updated}
  报错 400 导入文件有错
  报错 400 条目对不上知识点
  报错 400 编号要以「<编码>.」开头
  报错 400 编号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「编号|名称|知识点编号|接在哪个形式后|前一个条目编号」，用 | 分隔；后三项可以省略或为空（缺的尾部字段当空）；编号、名称、知识点编号任一为空，报错 400 导入文件有错
  伪代码 编号前缀：每行条目编号都调用本模块 编号前缀检查 subject_id=subject_id code=编号，不符报错 400 编号要以「<编码>.」开头（整批不写）；日语（subject_id 等于 1）豁免
  伪代码 编号全局唯一（条目表内、跨科目）：条目编号已在 kg_item 但属于别的科目，报错 400 编号已被其他科目使用（整批不写）；只查 kg_item，不查 kg_point（不要求跨表唯一）
  伪代码 在一个事务里：逐行按 code 查 kg_item，没有则插入（带 subject_id）并 created+1，有则更新 name、point_code、after_form、prev_code 并 updated+1
  伪代码 全部行写完后校验：本科目每个条目的 point_code 必须在本科目的 kg_point，前一个条目编号不为空时必须在本科目的 kg_item（属于别的科目的编号算对不上），否则报错 400 条目对不上知识点，事务回滚整批不写
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

公开 函数 导入对照 file_path learner? current_role? auth_mode? subject?
  返回 {ok, total, created, updated}，重复的对照（不分顺序）算 updated，不新增行
  报错 400 导入文件有错
  报错 400 编号要以「<编码>.」开头
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「编号A|编号B」，用 | 分隔；任一为空、或两端相同，报错 400 导入文件有错（整批不写）；对照两端可以是知识点也可以是条目，不核对是否存在，不加外键，不做环检查
  伪代码 编号前缀：两端编号都调用本模块 编号前缀检查 subject_id=subject_id code=编号，不符报错 400 编号要以「<编码>.」开头（整批不写）；日语（subject_id 等于 1）豁免
  伪代码 在一个事务里：每行把两端按字符串大小规范化（小的为 a_code），按 (subject_id, a_code, b_code) 查 kg_contrast，没有则插入（带 subject_id）并 created+1，有则 updated+1
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（need 不传按 read；need=write 时登录模式下只有负责/协作教师通过，否则 解析科目 报 403 没有权限修改该科目、原样抛出；四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出）

函数 编号前缀检查 subject_id code
  返回 {ok}
  报错 400 编号要以「<编码>.」开头
  伪代码 subject_id 等于 1（日语）：直接返回 {"ok": 1}，旧编号不动
  伪代码 否则按 subject_id 查 subject_info 的 code（科目编码，查询 kg_subject_code）；编码为空、或 code 不匹配 ^[a-z][a-z0-9_]*\.[A-Za-z0-9_-]+$、或 code 不以「<编码>.」开头，报错 400 编号要以「<编码>.」开头（文案里的 <编码> 换成真实编码）
  伪代码 返回 {"ok": 1}

函数 编号格式检查 subject_id code
  返回 {ok}；单个新建、批量预检共用的编号格式校验（私有）：先查字符集，再按口径 2 查前缀
  报错 400 编号只能用字母、数字、点、下划线、短横，最长60
  报错 400 编号要以「<编码>.」开头
  伪代码 code 不匹配 ^[A-Za-z0-9][A-Za-z0-9_.-]{0,59}$（含空白、|、英文逗号、~、>、中文等都不行——| 是导入分隔符，英文逗号是 核对条目存在 的分隔符，> 和 ~ 是页面行键的拼接符），报错 400 编号只能用字母、数字、点、下划线、短横，最长60；日语旧编号（如 te-kudasai）都符合
  伪代码 再调用本模块 编号前缀检查 subject_id=subject_id code=code（日语 subject_id 等于 1 豁免；其它科目要以「<科目编码>.」开头），不符原样抛出
  伪代码 返回 {"ok": 1}

公开 函数 建知识点 code title learner? current_role? auth_mode? subject?
  返回 {ok, code}；单个新建一个知识点
  报错 400 编号不能为空
  报错 400 名称不能为空
  报错 400 名称最长60字
  报错 400 编号只能用字母、数字、点、下划线、短横，最长60
  报错 400 编号要以「<编码>.」开头
  报错 409 编号已存在
  报错 409 编号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 code、title 去掉首尾空白；code 为空报错 400 编号不能为空；title 为空报错 400 名称不能为空；title 超过 60 个字报错 400 名称最长60字
  伪代码 调用本模块 编号格式检查 subject_id=subject_id code=code，报错原样抛出
  伪代码 编号全局唯一（K81 口径：知识点表内、跨科目；只查 kg_point，不查 kg_item）：按 code 查 kg_point（不限科目），有且 subject_id 等于本科目，报错 409 编号已存在；有且属于别的科目，报错 409 编号已被其他科目使用（单个新建用 409；批量导入沿用旧口径 400，不改）
  伪代码 插入 kg_point (code, title, subject_id)
  伪代码 返回 {"ok": 1, "code": code}

公开 函数 改知识点 code title learner? current_role? auth_mode? subject?
  返回 {ok}；只改名称。编号创建后不可改：课文挂接、题目、单词、作答和掌握记录都按编号字符串引用、没有外键，改编号会让它们全部断开
  报错 400 编号不能为空
  报错 400 名称不能为空
  报错 400 名称最长60字
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 code、title 去掉首尾空白；code 为空报错 400 编号不能为空；title 为空报错 400 名称不能为空；title 超过 60 个字报错 400 名称最长60字
  伪代码 按 code 和 subject_id 查 kg_point，查不到（包括编号属于别的科目）报错 404 没有这个知识点
  伪代码 更新该行 title
  伪代码 返回 {"ok": 1}

函数 外部引用 kind code subject_id
  返回 {total, refs}；refs 是 [{source, n, block}]（只列 n 大于 0 的），别的模块对这个编号的引用计数（私有）；直读下游模块的表——kg 不声明依赖它们（lesson、quiz、vocab、progress、dictation 都依赖 kg，声明会成环；先例 lesson.题数表 直读 quiz_question、report.取题干）
  伪代码 每张表先查 app.db kg_table_exists（sqlite_master 里有没有这张表）：模块用例的库只建本模块和上游模块的表，下游表不在就按 0 计；整库和接口实测时表在、照实数
  伪代码 只数本科目：每张表都带 subject_id 等于入参的条件（这些表都有 subject_id 列）
  伪代码 kind 等于 point：lesson_point_link.point_code「课文挂接」、vocab_word.point_code「单词」、progress_answer.point_code「作答记录」、progress_mastery.point_code「掌握记录」、progress_score.point_code「得分记录」、dictation_progress.source「默写进度」，以上 block 为 1（挡删除）；teacher_assist_message.point「教师助手对话」block 为 0（只是对话流水里记过这个点，不挡删除、不改流水）
  伪代码 kind 等于 item：lesson_item_link.item_code「课文挂接」、quiz_question.item_code「题目」，block 为 1
  伪代码 textbook_import 草稿里的 item_codes、point_codes 是逗号文本，展示时已跳过不存在的编号（textbook_import 约定），不算引用
  伪代码 只读；不调用别的模块
  伪代码 返回 {"total": 各项 n 之和, "refs": 列表}

公开 函数 查引用 code kind? learner? current_role? auth_mode? subject?
  返回 {code, kind, total, deletable, refs}；refs 是 [{source, n, block}]（只列 n 大于 0 的），block 为 1 的项会挡删除；deletable 为 1 表示现在可以删
  报错 400 编号不能为空
  报错 400 kind 只能是 point 或 item
  报错 404 没有这个编号
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 code 为空报错 400 编号不能为空；kind 不为空且不是 point、item 之一，报错 400 kind 只能是 point 或 item
  伪代码 kind 为空：本科目 kg_point 有 code 则 kind=point，否则本科目 kg_item 有 code 则 kind=item，都没有报错 404 没有这个编号；kind 给了但本科目对应的表里没有 code（包括属于别的科目），同样报错 404 没有这个编号
  伪代码 kind 等于 point 的本模块内引用：本科目 kg_item 中 point_code 等于 code 的行数「下挂条目」block 1；本科目 kg_edge 中 pre_code 或 point_code 等于 code 的行数「前置边」block 0；本科目 kg_contrast 中 a_code 或 b_code 等于 code 的行数「对照」block 0（边和对照删点时一起删）
  伪代码 kind 等于 item 的本模块内引用：本科目 kg_item 中 prev_code 等于 code 的行数「后一个条目」block 1；本科目 kg_contrast 中 a_code 或 b_code 等于 code 的行数「对照」block 0
  伪代码 调用本模块 外部引用 kind=kind code=code subject_id=subject_id，refs 并进来
  伪代码 deletable：block 为 1 的各项 n 之和为 0 则 1，否则 0
  伪代码 返回 {"code": code, "kind": kind, "total": 全部 n 之和, "deletable": deletable, "refs": 列表}

公开 函数 删知识点 code learner? current_role? auth_mode? subject?
  返回 {ok, edges_removed, contrasts_removed}；删一个知识点，连同它的前置边和对照（同一事务）；被条目或别的模块引用时拒绝（引用保护，见 k98 摘要「删除策略」）
  报错 400 编号不能为空
  报错 404 没有这个知识点
  报错 409 知识点还被引用，不能删除
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 code 去掉首尾空白后为空，报错 400 编号不能为空；按 code 和 subject_id 查 kg_point，查不到（包括属于别的科目）报错 404 没有这个知识点
  伪代码 调用本模块 查引用 code=code kind=point subject=subject_id 得 deletable 和 refs
  伪代码 deletable 为 0：报错 409 知识点还被引用，不能删除（文案后面接 block 为 1 的明细，如「（下挂条目3、作答记录12）」，source 和 n 直接拼、用「、」连、不含空格），库不动
  伪代码 在一个事务里：删除本科目 kg_edge 中 pre_code 或 point_code 等于 code 的行，行数为 edges_removed；删除本科目 kg_contrast 中 a_code 或 b_code 等于 code 的行，行数为 contrasts_removed；删除 kg_point 该行
  伪代码 返回 {"ok": 1, "edges_removed": edges_removed, "contrasts_removed": contrasts_removed}

公开 函数 删前置边 pre_code point_code learner? current_role? auth_mode? subject?
  返回 {ok, removed}；删一条前置边
  报错 400 编号不能为空
  报错 404 没有这条前置边
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 pre_code 或 point_code 为空，报错 400 编号不能为空
  伪代码 本科目 kg_edge 没有 (pre_code, point_code) 的行，报错 404 没有这条前置边（方向反了也算没有）
  伪代码 删除本科目 kg_edge 中 (pre_code, point_code) 的全部行（kg_edge 没有唯一约束，旧数据可能有重复），行数为 removed
  伪代码 不查引用：掌握度不存边，progress 每次读时现算解锁；删边后后续点可能立刻变「可学」、某点可能变成起点，这是预期
  伪代码 返回 {"ok": 1, "removed": removed}

公开 函数 建条目 code name point_code after_form? prev_code? learner? current_role? auth_mode? subject?
  返回 {ok, code}；单个新建一个条目
  报错 400 编号不能为空
  报错 400 名称不能为空
  报错 400 名称最长60字
  报错 400 编号只能用字母、数字、点、下划线、短横，最长60
  报错 400 编号要以「<编码>.」开头
  报错 409 编号已存在
  报错 409 编号已被其他科目使用
  报错 404 没有这个知识点
  报错 404 没有这个前一个条目
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 code、name、point_code、after_form、prev_code 去掉首尾空白；code 为空报错 400 编号不能为空；name 为空报错 400 名称不能为空；name 超过 60 个字报错 400 名称最长60字；point_code 为空报错 404 没有这个知识点
  伪代码 调用本模块 编号格式检查 subject_id=subject_id code=code，报错原样抛出
  伪代码 编号全局唯一（K81 口径：条目表内、跨科目；只查 kg_item，不查 kg_point）：按 code 查 kg_item（不限科目），有且 subject_id 等于本科目，报错 409 编号已存在；有且属于别的科目，报错 409 编号已被其他科目使用
  伪代码 point_code 不在本科目 kg_point（包括属于别的科目），报错 404 没有这个知识点；prev_code 不为空且不在本科目 kg_item，报错 404 没有这个前一个条目（新建的条目还不存在，不会以自己为前一个）
  伪代码 插入 kg_item (code, name, point_code, after_form, prev_code, subject_id)，after_form、prev_code 空串照存
  伪代码 返回 {"ok": 1, "code": code}

公开 函数 改条目 code name point_code after_form? prev_code? learner? current_role? auth_mode? subject?
  返回 {ok}；改名称、所属知识点、接在、前一个条目；编号不可改（理由同 改知识点：题目和课文挂接按条目编号引用）
  报错 400 编号不能为空
  报错 400 名称不能为空
  报错 400 名称最长60字
  报错 404 没有这个条目
  报错 404 没有这个知识点
  报错 404 没有这个前一个条目
  报错 400 不能以自己为前一个条目
  报错 400 前一个条目会形成环
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 各入参去掉首尾空白；code 为空报错 400 编号不能为空；name 为空报错 400 名称不能为空；name 超过 60 个字报错 400 名称最长60字
  伪代码 按 code 和 subject_id 查 kg_item，查不到（包括属于别的科目）报错 404 没有这个条目
  伪代码 point_code 不在本科目 kg_point，报错 404 没有这个知识点
  伪代码 prev_code 不为空时：等于 code 报错 400 不能以自己为前一个条目；不在本科目 kg_item 报错 404 没有这个前一个条目；从 prev_code 出发沿本科目 kg_item 的 prev_code 链往前走（走过的不再走），遇到 code 报错 400 前一个条目会形成环
  伪代码 after_form、prev_code 按传入值原样写（不传或空串即清空；页面保存时整条提交）
  伪代码 改 point_code 不动别的表：题目、课文挂接按条目编号引用，不受影响；学生端该条目改到新知识点下显示
  伪代码 更新该行 name、point_code、after_form、prev_code
  伪代码 返回 {"ok": 1}

公开 函数 删条目 code learner? current_role? auth_mode? subject?
  返回 {ok, contrasts_removed}；删一个条目，连同它的对照（同一事务）；被后一个条目、题目或课文挂接引用时拒绝
  报错 400 编号不能为空
  报错 404 没有这个条目
  报错 409 条目还被引用，不能删除
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 code 去掉首尾空白后为空，报错 400 编号不能为空；按 code 和 subject_id 查 kg_item，查不到（包括属于别的科目）报错 404 没有这个条目
  伪代码 调用本模块 查引用 code=code kind=item subject=subject_id 得 deletable 和 refs
  伪代码 deletable 为 0：报错 409 条目还被引用，不能删除（文案后面接 block 为 1 的明细，如「（题目5、课文挂接2）」，不含空格），库不动
  伪代码 在一个事务里：删除本科目 kg_contrast 中 a_code 或 b_code 等于 code 的行，行数为 contrasts_removed；删除 kg_item 该行
  伪代码 返回 {"ok": 1, "contrasts_removed": contrasts_removed}

公开 函数 加对照 a_code b_code learner? current_role? auth_mode? subject?
  返回 {ok, created}；created 为 1 表示新加，0 表示这条对照已存在（不分顺序）
  报错 400 编号不能为空
  报错 400 对照两端不能相同
  报错 404 没有这个编号
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 a_code、b_code 去掉首尾空白；任一为空报错 400 编号不能为空；两端相同报错 400 对照两端不能相同
  伪代码 两端各自要在本科目的 kg_point 或 kg_item 里，任一端都不在（包括属于别的科目），报错 404 没有这个编号（单条加比批量导入严；导入对照的旧口径不核对存在，不改）
  伪代码 两端按字符串大小规范化（小的为 a_code），按 (subject_id, a_code, b_code) 查 kg_contrast，有则返回 {"ok": 1, "created": 0}
  伪代码 插入 kg_contrast (a_code, b_code, subject_id)
  伪代码 返回 {"ok": 1, "created": 1}

公开 函数 删对照 a_code b_code learner? current_role? auth_mode? subject?
  返回 {ok}；删一条对照（不分顺序）
  报错 400 编号不能为空
  报错 404 没有这条对照
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 a_code 或 b_code 为空，报错 400 编号不能为空
  伪代码 两端按字符串大小规范化，按 (subject_id, a_code, b_code) 查 kg_contrast，没有报错 404 没有这条对照
  伪代码 删除这些行（旧数据可能有重复，全部删）
  伪代码 返回 {"ok": 1}

公开 函数 导入前置边 file_path learner? current_role? auth_mode? subject?
  返回 {ok, total, created, updated}；批量加前置边（已有的边算 updated，不新增行），整批做环检查
  报错 400 导入文件有错
  报错 400 前置边对不上知识点
  报错 400 这批前置边会形成环
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「前置编号|后续编号」，用 | 分隔；任一为空、没有 |、或两端相同，报错 400 导入文件有错（整批不写）
  伪代码 两端都要在本科目的 kg_point（属于别的科目的编号算对不上），否则报错 400 前置边对不上知识点（整批不写）
  伪代码 环检查：把本科目已有的 kg_edge 和本批的边合在一起按拓扑顺序排，排不完（有环）报错 400 这批前置边会形成环（整批不写）
  伪代码 在一个事务里：每行按 (subject_id, pre_code, point_code) 查 kg_edge，没有则插入并 created+1，有则 updated+1；同一文件里重复的边只插一次，后出现的按已有计 updated
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

函数 拼原因 rs add
  返回 {r}；导入预检逐行攒原因用（私有）：rs 为空时 r 就是 add，否则 r 是「rs；add」（多条原因用「；」连起来）
  伪代码 rs 为空，返回 {"r": add}；否则返回 {"r": "rs；add"}

函数 边可达 edges start target
  返回 {r}；导入预检查环用（私有）：edges 是 [{pre_code, point_code}]，从 start 顺着 pre_code→point_code 走能到 target 时 r 为 1，否则为 0
  伪代码 已到集合先放 start；反复扫一遍 edges，pre_code 已到而 point_code 未到的把 point_code 加进已到集合，直到一轮没有新加入（最多 500 轮）
  伪代码 target 在已到集合里返回 {"r": 1}，否则返回 {"r": 0}

函数 读导入行 kind file_path
  返回 {rows}；导入预检的读文件段（私有）：rows 是 [{line, a, b, c, d, e, extra}]，a..e 按 kind 依次是 point（编号、名称）、item（编号、名称、知识点编号、接在哪个形式后、前一个条目编号）、edge（前置编号、后续编号）、contrast（一端、另一端），没有的项为空串；extra 为 1 表示 md、txt 该行项数超过该类型的项数（见下），csv、json 恒为 0
  报错 400 文件类型只能是 md、txt、csv、json
  报错 400 导入文件读不了
  报错 400 导入文件没有数据行
  报错 400 一次最多导入2000行
  伪代码 file_path 扩展名（不分大小写）是 md、txt：用 doc 包「读文档」取文本，error 不为空报错 400 导入文件读不了；按行拆，每行去首尾空白，空行和以 # 开头的行忽略；其余每行按 | 切成若干项，前 5 项依次放 a..e（不足的补空串）；项数（| 的个数加 1，行尾多余的 | 也算一项）超过该类型的项数——point、edge、contrast 2 项，item 5 项——时 extra 为 1；line 是原文件行号（含被忽略的行）
  伪代码 扩展名是 csv：用 data 包「读CSV」（首行是表头）；是 json：用「读JSON」语句，顶层要是对象列表，解析失败或顶层不是列表报错 400 导入文件读不了；line 是 csv 从 2 起、json 从 1 起
  伪代码 csv、json 的必需列：point 是 code、title；item 是 code、name、point_code（after_form、prev_code 可缺）；edge 是 pre_code、point_code；contrast 是 a_code、b_code。缺列＝csv 表头里没有这个列名（表头各列名去掉 UTF-8 BOM 和首尾空白后比较，同 读CSV 的 utf-8-sig 读法）、json 里没有一个对象带这个键；按上面的顺序找第一个缺的列，报错 400 导入文件读不了（缺<列名>）（整份不认，如「导入文件读不了（缺code）」）。列在、某行的值为空（json 某个对象缺这个键也算这一行为空）不在这里报，照常放进 rows 成空串，由 导入预检 按「缺编号」等记成该行报错。多出的列、键忽略
  伪代码 其他扩展名报错 400 文件类型只能是 md、txt、csv、json
  伪代码 rows 为空报错 400 导入文件没有数据行；超过 2000 行报错 400 一次最多导入2000行
  伪代码 返回 {"rows": rows}

公开 函数 导入预检 kind file_path learner? current_role? auth_mode? subject?
  返回 {kind, total, ok_count, error_count, created, updated, rows}；批量导入的预览，不写库；rows 是 [{line, code, label, action, reason}]，action 是 新增/更新/报错，reason 是逐行说明（报错原因或提示，可空）
  报错 400 导入类型不对
  报错 400 导入文件路径不对
  报错 400 文件类型只能是 md、txt、csv、json
  报错 400 导入文件读不了
  报错 400 导入文件没有数据行
  报错 400 一次最多导入2000行
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 kind 不是 point、item、edge、contrast 之一，报错 400 导入类型不对（预检按写操作校验：没有写权限的人连预览都不给）
  伪代码 文件位置：file_path 必须是 uploads/ 下的一个文件——以 uploads/ 开头，其后只有一段文件名（不再含 /），整个路径不含 ..、不含 \（以 / 开头的绝对路径、Windows 盘符路径自然不以 uploads/ 开头）；不符报错 400 导入文件路径不对（与 确认导入 同一条规则；路由传进来的都是「存文件」给的 uploads/<哈希>.<扩展名>，这条挡的是别的调用方直接传路径读工作目录里别的文件）。在读文件之前判；扩展名不对仍按下一条报 文件类型只能是 md、txt、csv、json
  伪代码 调用本模块 读导入行 kind=kind file_path=file_path 得 rows（读法见 读导入行）：md、txt 用 doc 包「读文档」取文本按行拆，空行和以 # 开头的行忽略，每行按 | 切（格式同 导入知识点 / 导入条目 / 导入对照 / 导入前置边，项数上限也同它们：point、edge、contrast 2 项，item 5 项）；csv 用 data 包「读CSV」（首行是表头）；json 用「读JSON」语句，顶层要是对象列表；其他扩展名报错 400 文件类型只能是 md、txt、csv、json；读文档 返回的 error 不为空、JSON 解析失败或顶层不是列表，报错 400 导入文件读不了
  伪代码 csv 表头和 json 的键：point 是 code,title；item 是 code,name,point_code,after_form,prev_code（后两项可缺）；edge 是 pre_code,point_code；contrast 是 a_code,b_code。两种情况分开：①缺列（csv 表头里没有这个列名；json 里没有一个对象带这个键）整份不认，报错 400 导入文件读不了（缺<列名>），按上面列的顺序报第一个缺的，原文如「导入文件读不了（缺code）」；②列在、但某行的值为空（json 某个对象缺这个键也算该行为空）：不整份拒，该行报错，原因与 md、txt 相同（「缺编号」「缺名称」「缺知识点编号」「缺前置编号」等），确认导入时因此报 400 导入文件有错（第N行：缺编号）。全部行都空也按②逐行报，不再当缺列
  伪代码 有效行为 0 报错 400 导入文件没有数据行；超过 2000 行报错 400 一次最多导入2000行
  伪代码 line 是文件里的行号：md、txt 是原文件行号（含被忽略的行），csv 从 2 起，json 从 1 起；code 是该行编号（edge、contrast 是「A>B」「A~B」），label 是名称或对端
  伪代码 逐行校验，一行有多条原因用「；」连起来（调用本模块 拼原因），有原因的行 action 为「报错」：md、txt 该行 extra 为 1（项数超过该类型的项数，含行尾多余的 |），原因放在第一条：point「项数多了：知识点每行最多2项（编号|名称），行尾多余的|也算一项」、item「项数多了：条目每行最多5项（编号|名称|知识点编号|接在哪个形式后|前一个条目编号），行尾多余的|也算一项」、edge「项数多了：前置边每行最多2项（前置编号|后续编号），行尾多余的|也算一项」、contrast「项数多了：对照每行最多2项（编号A|编号B），行尾多余的|也算一项」（预检与确认同一规则：确认导入先重跑本函数，这类行在预检就是报错行，确认时报 400 导入文件有错（第N行：项数多了…），不会走到旧导入函数的无行号报错；item 比旧 导入条目 严——旧函数忽略第 5 项之后的内容，但经 确认导入 一律先过本函数，所以导入口径以本条为准，直接调旧函数的行为不变）；必填项为空（「缺编号」「缺名称」「缺知识点编号」「缺前置编号」等）；point、item 的编号调用本模块 编号格式检查 subject_id=subject_id code=编号，报错原文作原因；point、item 的名称超过 60 个字；编号已在别的科目（point 只查 kg_point、item 只查 kg_item，K81 口径），原因「编号已被其他科目使用」；item 的所属知识点不在本科目 kg_point「没有这个知识点」；item 的前一个条目不为空且既不在本科目 kg_item、也不是本文件里的条目「没有这个前一个条目」；edge 两端相同「不能以自己为前置」、任一端不在本科目 kg_point「没有这个知识点」；contrast 两端相同「对照两端不能相同」，两端都调用本模块 编号前缀检查 subject_id=subject_id code=编号（只查前缀，不核对存在，同 导入对照 旧口径）
  伪代码 edge 的环检查：各行单行校验都过了以后，把本科目已有的边和本批的边合起来查环，有环时把环上属于本批的行都标为报错，原因「会形成环：A>B>…>A」
  伪代码 没报错的行（计数口径与旧导入函数一致，保证预检的 created/updated 就是确认后的 created/updated）：本科目已有、或本文件前面的行已经出现过（point、item 按编号，edge、contrast 按两端）为「更新」，计入 updated；各列都相同时 reason 写「内容相同」（edge、contrast 写「已存在」）；没有为「新增」，计入 created；同一文件里重复的编号（edge、contrast 按两端；只在没报错的行之间算，报错行不参与）后一行为准、action 照算（与旧导入函数「后一行覆盖前一行」一致）：前面的各行 reason 写「被第N行覆盖」（N 是该编号最后出现的行，即最终生效的那行），最后出现的那行 reason 写「本文件重复，以本行为准」（说明它为什么是「更新」）；该行原来已有「内容相同」「已存在」时用「；」接在后面（如「内容相同；被第5行覆盖」）。理由：保留约定原意（前一行要告诉老师它会被覆盖、不会生效），同时补上后一行的说明——不写的话，库里没有的编号显示成「更新」会让人看不懂；实现上在逐行走完后再回填前面行的 reason
  伪代码 只读：不写库、不删文件
  伪代码 返回 {"kind": kind, "total": 有效行数, "ok_count": 非报错行数, "error_count": 报错行数, "created": 新增行数, "updated": 更新行数, "rows": 按 line 升序}

公开 函数 确认导入 kind file_path learner? current_role? auth_mode? subject?
  返回 {ok, kind, total, created, updated}；按预检通过的文件真正写库（整批：有一行报错就一行都不写）
  报错 400 导入类型不对
  报错 400 导入文件路径不对
  报错 400 导入文件有错
  报错 400 文件类型只能是 md、txt、csv、json
  报错 400 导入文件读不了
  报错 400 导入文件没有数据行
  报错 400 一次最多导入2000行
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 file_path 不符合 导入预检 的文件位置规则（必须以 uploads/ 开头、其后只有一段文件名不再含 /、整个路径不含 .. 和 \；以 / 开头的绝对路径、Windows 盘符路径都不以 uploads/ 开头），或扩展名不是 md、txt、csv、json 之一（不分大小写），报错 400 导入文件路径不对（页面回传的是预检时存下的路径 uploads/<哈希>.<扩展名>；限定在 uploads/ 内，防路径穿越、防拿工作目录里别的同扩展名文件来导入或借报错行号探测内容）
  伪代码 调用本模块 导入预检 kind=kind file_path=file_path subject=subject_id 得 error_count 和 rows（预检的报错原样抛出）；error_count 大于 0，报错 400 导入文件有错（文案后接第一条报错行「第N行：原因」）
  伪代码 扩展名是 md、txt：复用旧导入函数——kind 等于 point 调用本模块 导入知识点 file_path=file_path subject=subject_id；item 调用本模块 导入条目 file_path=file_path subject=subject_id；contrast 调用本模块 导入对照 file_path=file_path subject=subject_id；edge 调用本模块 导入前置边 file_path=file_path subject=subject_id；得 total、created、updated
  伪代码 扩展名是 csv、json：调用本模块 写入导入行 kind=kind rows=预检的全部行 subject_id=subject_id 得 total、created、updated
  伪代码 预检和写库之间别人改了库、导致旧函数报 400：原样抛出（旧函数自己整批回滚）
  伪代码 返回 {"ok": 1, "kind": kind, "total": total, "created": created, "updated": updated}

函数 写入导入行 kind rows subject_id
  返回 {ok, total, created, updated}；csv、json 导入的写库段（私有）
  报错 400 导入文件有错
  伪代码 在一个事务里按 kind 逐行写，口径与 导入知识点 / 导入条目 / 导入对照 / 导入前置边 的事务段完全相同：point 有则改 title、没有则插；item 有则改 name、point_code、after_form、prev_code，没有则插；contrast 两端规范化后有则 updated+1、没有则插；edge 有则 updated+1、没有则插
  伪代码 写完做与旧函数相同的收尾校验（item：每个条目的 point_code 在本科目 kg_point、prev_code 在本科目 kg_item；edge：本科目全图无环），失败报错 400 导入文件有错，事务回滚整批不写
  伪代码 实现时四个旧导入函数的事务段和本函数共用同一组查询（旧函数行为不变，旧用例不改）
  伪代码 返回 {"ok": 1, "total": 行数, "created": created, "updated": updated}

公开 函数 导出文本 kind? learner? current_role? auth_mode? subject?
  返回 {kind, count, text}；text 是与导入同格式（| 分隔）的多行文本，按类型存成 .txt 可直接再导入
  报错 400 导出类型不对
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 kind 为空取 all；不是 all、point、item、edge、contrast 之一，报错 400 导出类型不对
  伪代码 调用本模块 导出图 subject=subject_id 得 points、edges、contrasts；调用本模块 列条目 subject=subject_id 得 items
  伪代码 每行：point「code|title」；item「code|name|point_code|after_form|prev_code」（空项留空）；edge「pre_code|point_code」；contrast「a_code|b_code」；各段按 id 升序，用换行连
  伪代码 kind 等于 all：四段依次用「# 知识点」「# 条目」「# 前置边」「# 对照」打头（# 开头的行导入时被忽略；但四段混在一个文件里不能直接导入，要按段拆开存，页面上写明）
  伪代码 count 是导出的数据行数（不含 # 行）
  伪代码 返回 {"kind": kind, "count": count, "text": text}

函数 页面身份 learner current_role auth_mode subject_id
  返回 {can_write, kgm_role}；图谱管理页按身份显隐编辑按钮用（私有；真正的拦截在各写函数的 need=write）
  伪代码 auth_mode 不等于 on（单人/不登录），返回 {"can_write": 1, "kgm_role": "单人"}
  伪代码 调用 subject.科目访问 learner=learner current_role=current_role subject_id=subject_id need=write auth_mode=auth_mode：ok 为 1 时 can_write=1，kgm_role 按 via：owner「负责」、editor「协作」
  伪代码 ok 为 0 时 can_write=0，再调用 subject.科目访问 learner=learner current_role=current_role subject_id=subject_id need=read auth_mode=auth_mode：via 等于 public 时 kgm_role 为「公共只读」，否则为「无权」（正常到不了这里：读校验已经先拦了）
  伪代码 返回 {"can_write": can_write, "kgm_role": kgm_role}

公开 函数 图谱管理页面 learner current_role? auth_mode? subject?
  返回 {graph, kgm_points, kgm_items, kgm_edges, kgm_contrasts, point_options, kgm_head, kgm_role, can_write}；「图谱管理」页「进入时」（动作 kgm_home）的整页状态，也是各写操作页面函数的返回
  报错 403 只有教师可以管理图谱
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 调用本模块 页面身份 learner=learner current_role=current_role auth_mode=auth_mode subject_id=subject_id 得 can_write、kgm_role
  伪代码 调用本模块 导出图 subject=subject_id 和 调用本模块 列条目 subject=subject_id 取本科目全部点、边、对照、条目，下面都在内存里拼，不逐点再查库
  伪代码 graph 形状同 progress.图谱页面 的 graph（前端同一个「节点图」控件）：nodes 每点 {id: code, code, label: title, state, badge, desc}；管理页不看掌握度——有任何前置边或后续边的点 state 为 open，孤点（一条前置边都没连）为 locked（灰显，提醒还没连边）；badge 为该点下挂条目数；desc 为直接前置的 title 用「、」连，没有前置为「（起点）」；edges：前置边 {from: pre_code, to: point_code, kind: 空串}，对照两端都是本科目知识点时 {from: a_code, to: b_code, kind: 对照}（条目端的对照不画，表里照列）
  伪代码 kgm_points：每点 {kgp_orig: code, kgp_code: code, kgp_title: title, kgp_item_n: 下挂条目数, kgp_pre_n: 直接前置数, kgp_next_n: 直接后续数}，按 id 升序
  伪代码 kgm_items：每条 {kgi_orig: code, kgi_code: code, kgi_name: name, kgi_point: point_code, kgi_point_title: 所属知识点 title（取不到空串）, kgi_after: after_form 或空串, kgi_prev: prev_code 或空串}，按 id 升序
  伪代码 kgm_edges：每条 {edge_key: 「pre_code>point_code」, edge_pre: pre_code, edge_point: point_code, edge_pre_title, edge_point_title}，按 id 升序
  伪代码 kgm_contrasts：每条 {ct_key: 「a_code~b_code」, ct_a, ct_b, ct_a_label, ct_b_label}，label 为「编号（名称）」，名称取本科目知识点 title 或条目 name，都没有只给编号；按 id 升序
  伪代码 point_options：[{value: code, label: 「code（title）」}]，按 id 升序（条目的所属知识点、前置边两端的下拉用）
  伪代码 kgm_head：「共{n}个知识点、{m}条前置边、{k}个条目、{l}条对照」（不含空格）
  伪代码 返回 {"graph": …, "kgm_points": …, "kgm_items": …, "kgm_edges": …, "kgm_contrasts": …, "point_options": …, "kgm_head": …, "kgm_role": kgm_role, "can_write": can_write}

公开 函数 载入知识点页面 learner kgp_orig? code? current_role? auth_mode? subject?
  返回 回填表单 {kgp_orig, kgp_code, kgp_title, kgp_refs}（动作 kgm_point_open，「编辑知识点」浮层的「载入」）
  报错 403 只有教师可以管理图谱
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 编号取 kgp_orig，为空再取 code（节点图点开带的是 code，知识点表行上带的是 kgp_orig）；两个都为空（新建）返回 {"kgp_orig": "", "kgp_code": "", "kgp_title": "", "kgp_refs": ""}
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 调用本模块 取知识点 code=编号 subject=subject_id，为空报错 404 没有这个知识点
  伪代码 调用本模块 查引用 code=编号 kind=point subject=subject_id 得 refs、deletable：refs 为空时 kgp_refs 为「没有被引用，可以删除」；否则「被引用：」接各项「{source}{n}」用「、」连，deletable 为 0 时再接「。删除会被拒绝，可以改名」
  伪代码 返回 {"kgp_orig": 编号, "kgp_code": 编号, "kgp_title": title, "kgp_refs": kgp_refs}

公开 函数 保存知识点页面 learner kgp_title kgp_orig? kgp_code? current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面
  报错 403 只有教师可以管理图谱
  报错 400 编号不能为空
  报错 400 名称不能为空
  报错 400 名称最长60字
  报错 400 编号只能用字母、数字、点、下划线、短横，最长60
  报错 400 编号要以「<编码>.」开头
  报错 409 编号已存在
  报错 409 编号已被其他科目使用
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 kgp_orig 为空（新建）：调用本模块 建知识点 code=kgp_code title=kgp_title learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 kgp_orig 不为空（编辑）：kgp_code 忽略（建后不可改）；调用本模块 改知识点 code=kgp_orig title=kgp_title learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 删知识点页面 learner kgp_orig current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面（知识点表行上「删除」，带 kgp_orig）
  报错 403 只有教师可以管理图谱
  报错 400 编号不能为空
  报错 404 没有这个知识点
  报错 409 知识点还被引用，不能删除
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 调用本模块 删知识点 code=kgp_orig learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 加前置边页面 learner edge_pre edge_point current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面（「加前置边」两个下拉加按钮）
  报错 403 只有教师可以管理图谱
  报错 400 编号不能为空
  报错 400 不能以自己为前置
  报错 404 没有这个知识点
  报错 400 这条边会形成环
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 调用本模块 加前置边 pre_code=edge_pre point_code=edge_point learner=learner current_role=current_role auth_mode=auth_mode subject=subject（已有的边 created 为 0，不报错）
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 删前置边页面 learner edge_key current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面（前置边表行上「删除」，带 edge_key）
  报错 403 只有教师可以管理图谱
  报错 400 前置边参数不对
  报错 400 编号不能为空
  报错 404 没有这条前置边
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 edge_key 按第一个「>」拆成前后两段（编号本身不含 >，见 编号格式检查）；没有「>」或任一段为空，报错 400 前置边参数不对
  伪代码 调用本模块 删前置边 pre_code=前段 point_code=后段 learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 载入条目页面 learner kgi_orig? current_role? auth_mode? subject?
  返回 回填表单 {kgi_orig, kgi_code, kgi_name, kgi_point, kgi_after, kgi_prev}（动作 kgm_item_open，「编辑条目」浮层的「载入」）
  报错 403 只有教师可以管理图谱
  报错 404 没有这个条目
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 kgi_orig 为空（新建）返回 {"kgi_orig": "", "kgi_code": "", "kgi_name": "", "kgi_point": "", "kgi_after": "", "kgi_prev": ""}
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 调用本模块 取条目 code=kgi_orig subject=subject_id，为空报错 404 没有这个条目
  伪代码 返回 {"kgi_orig": code, "kgi_code": code, "kgi_name": name, "kgi_point": point_code, "kgi_after": after_form 或空串, "kgi_prev": prev_code 或空串}

公开 函数 保存条目页面 learner kgi_name kgi_point kgi_orig? kgi_code? kgi_after? kgi_prev? current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面
  报错 403 只有教师可以管理图谱
  报错 400 编号不能为空
  报错 400 名称不能为空
  报错 400 名称最长60字
  报错 400 编号只能用字母、数字、点、下划线、短横，最长60
  报错 400 编号要以「<编码>.」开头
  报错 409 编号已存在
  报错 409 编号已被其他科目使用
  报错 404 没有这个条目
  报错 404 没有这个知识点
  报错 404 没有这个前一个条目
  报错 400 不能以自己为前一个条目
  报错 400 前一个条目会形成环
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 kgi_orig 为空（新建）：调用本模块 建条目 code=kgi_code name=kgi_name point_code=kgi_point after_form=kgi_after prev_code=kgi_prev learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 kgi_orig 不为空（编辑）：kgi_code 忽略（建后不可改）；调用本模块 改条目 code=kgi_orig name=kgi_name point_code=kgi_point after_form=kgi_after prev_code=kgi_prev learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 删条目页面 learner kgi_orig current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面（条目表行上「删除」，带 kgi_orig）
  报错 403 只有教师可以管理图谱
  报错 400 编号不能为空
  报错 404 没有这个条目
  报错 409 条目还被引用，不能删除
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 调用本模块 删条目 code=kgi_orig learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 加对照页面 learner ct_a ct_b current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面
  报错 403 只有教师可以管理图谱
  报错 400 编号不能为空
  报错 400 对照两端不能相同
  报错 404 没有这个编号
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 调用本模块 加对照 a_code=ct_a b_code=ct_b learner=learner current_role=current_role auth_mode=auth_mode subject=subject（已有 created 为 0，不报错）
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 删对照页面 learner ct_key current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面（对照表行上「删除」，带 ct_key）
  报错 403 只有教师可以管理图谱
  报错 400 对照参数不对
  报错 400 编号不能为空
  报错 404 没有这条对照
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 ct_key 按第一个「~」拆成两段；没有「~」或任一段为空，报错 400 对照参数不对
  伪代码 调用本模块 删对照 a_code=前段 b_code=后段 learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 返回 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 的结果

公开 函数 导入预检页面 learner imp_kind imp_upload_path current_role? auth_mode? subject?
  返回 {imp_rows, imp_head, imp_ok, form}（动作 kgm_import_preview，「批量导入」浮层上传后的预览）；imp_rows 是 [{imp_line, imp_code, imp_label, imp_action, imp_reason}]；imp_ok 为 1 表示没有报错行、可以确认；form 是 {imp_kind, imp_file}，把存盘路径填回表单给「确认导入」用
  报错 403 只有教师可以管理图谱
  报错 400 导入类型不对
  报错 400 导入文件路径不对
  报错 400 文件类型只能是 md、txt、csv、json
  报错 400 导入文件读不了
  报错 400 导入文件没有数据行
  报错 400 一次最多导入2000行
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 imp_kind 页面值转换：「知识点」point、「条目」item、「前置边」edge、「对照」contrast；其他（含空）报错 400 导入类型不对
  伪代码 调用本模块 导入预检 kind=转换后 file_path=imp_upload_path learner=learner current_role=current_role auth_mode=auth_mode subject=subject
  伪代码 imp_rows：每行 {imp_line: line, imp_code: code, imp_label: label, imp_action: action, imp_reason: reason}
  伪代码 imp_head：「共{total}行：新增{created}、更新{updated}、报错{error_count}」，error_count 大于 0 时再接「。改好文件重新上传，一行都不会写入」（不含空格）
  伪代码 返回 {"imp_rows": …, "imp_head": …, "imp_ok": error_count 为 0 则 1 否则 0, "form": {"imp_kind": imp_kind, "imp_file": imp_upload_path}}

公开 函数 确认导入页面 learner imp_kind imp_file current_role? auth_mode? subject?
  返回 刷新后的整页状态，形状同 图谱管理页面，另加 {"imp_rows": [], "imp_ok": 0, "imp_head": 「已导入：新增{created}、更新{updated}」}（动作 kgm_import_confirm）
  报错 403 只有教师可以管理图谱
  报错 400 导入类型不对
  报错 400 导入文件路径不对
  报错 400 导入文件有错
  报错 400 文件类型只能是 md、txt、csv、json
  报错 400 导入文件读不了
  报错 400 导入文件没有数据行
  报错 400 一次最多导入2000行
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 imp_kind 页面值转换同 导入预检页面；其他（含空）报错 400 导入类型不对
  伪代码 调用本模块 确认导入 kind=转换后 file_path=imp_file learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 created、updated
  伪代码 调用本模块 图谱管理页面 learner=learner current_role=current_role auth_mode=auth_mode subject=subject，并上 imp_rows、imp_ok、imp_head 返回

公开 函数 导出页面 learner exp_kind? current_role? auth_mode? subject?
  返回 {export_text, export_head}（动作 kgm_export，「导出」浮层；文本框里全选复制，或按类型存成 .txt 再导入）
  报错 403 只有教师可以管理图谱
  报错 400 导出类型不对
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 教师校验：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理图谱（先于科目解析；单人模式不校验）
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 exp_kind 页面值转换：「全部」或空 all、「知识点」point、「条目」item、「前置边」edge、「对照」contrast；其他报错 400 导出类型不对
  伪代码 调用本模块 导出文本 kind=转换后 subject=subject_id 得 count、text
  伪代码 export_head：「共{count}行」，kind 等于 all 时再接「。四段要按段拆开分别导入」
  伪代码 返回 {"export_text": text, "export_head": export_head}

## 接口
GET /kg/point -> 取知识点
GET /kg/points -> 列知识点
GET /kg/prerequisites -> 列前置
GET /kg/successors -> 列后续
GET /kg/ancestors -> 列祖先
GET /kg/descendants -> 列后代
GET /kg/roots -> 列根节点
GET /kg/layers -> 列分层
POST /kg/edge/add -> 加前置边 角色 teacher
GET /kg/export -> 导出图
GET /kg/item -> 取条目
GET /kg/items -> 列条目
GET /kg/items/by-point -> 按知识点列条目
GET /kg/contrasts -> 列对照
POST /kg/import/points -> 导入知识点 上传 file 类型 md,txt 上限 20MB 角色 teacher
POST /kg/import/items -> 导入条目 上传 file 类型 md,txt 上限 20MB 角色 teacher
POST /kg/import/contrasts -> 导入对照 上传 file 类型 md,txt 上限 20MB 角色 teacher
POST /kg/point/create -> 建知识点 角色 teacher
POST /kg/point/update -> 改知识点 角色 teacher
POST /kg/point/delete -> 删知识点 角色 teacher
POST /kg/edge/delete -> 删前置边 角色 teacher
POST /kg/item/create -> 建条目 角色 teacher
POST /kg/item/update -> 改条目 角色 teacher
POST /kg/item/delete -> 删条目 角色 teacher
POST /kg/contrast/add -> 加对照 角色 teacher
POST /kg/contrast/delete -> 删对照 角色 teacher
GET /kg/refs -> 查引用 角色 teacher
POST /kg/import/edges -> 导入前置边 上传 file 类型 md,txt 上限 20MB 角色 teacher
POST /kg/import/preview -> 导入预检 上传 file 类型 md,txt,csv,json 上限 20MB 角色 teacher
POST /kg/import/confirm -> 确认导入 角色 teacher
GET /kg/export/text -> 导出文本 角色 teacher
POST /kg/manage/home -> 图谱管理页面 动作 kgm_home 模板 页面状态 角色 teacher
POST /kg/manage/point/open -> 载入知识点页面 动作 kgm_point_open 模板 回填 角色 teacher
POST /kg/manage/point/save -> 保存知识点页面 动作 kgm_point_save 模板 页面状态消息 消息=知识点已保存 角色 teacher
POST /kg/manage/point/delete -> 删知识点页面 动作 kgm_point_delete 模板 页面状态消息 消息=知识点已删除 角色 teacher
POST /kg/manage/edge/add -> 加前置边页面 动作 kgm_edge_add 模板 页面状态消息 消息=前置边已加上 角色 teacher
POST /kg/manage/edge/delete -> 删前置边页面 动作 kgm_edge_delete 模板 页面状态消息 消息=前置边已删除 角色 teacher
POST /kg/manage/item/open -> 载入条目页面 动作 kgm_item_open 模板 回填 角色 teacher
POST /kg/manage/item/save -> 保存条目页面 动作 kgm_item_save 模板 页面状态消息 消息=条目已保存 角色 teacher
POST /kg/manage/item/delete -> 删条目页面 动作 kgm_item_delete 模板 页面状态消息 消息=条目已删除 角色 teacher
POST /kg/manage/contrast/add -> 加对照页面 动作 kgm_contrast_add 模板 页面状态消息 消息=对照已加上 角色 teacher
POST /kg/manage/contrast/delete -> 删对照页面 动作 kgm_contrast_delete 模板 页面状态消息 消息=对照已删除 角色 teacher
POST /kg/manage/import/preview -> 导入预检页面 上传 imp_upload 类型 md,txt,csv,json 上限 20MB 动作 kgm_import_preview 模板 页面状态 表单=form 角色 teacher
POST /kg/manage/import/confirm -> 确认导入页面 动作 kgm_import_confirm 模板 页面状态消息 消息=导入完成 角色 teacher
POST /kg/manage/export -> 导出页面 动作 kgm_export 模板 页面状态 角色 teacher

## 用例
用例 取知识点_存在
  先 数据 kg_point code=P1 title=一次函数
  调用 取知识点 code=P1
  得 code=P1 title=一次函数

用例 取知识点_不存在
  调用 取知识点 code=NOPE
  得 为空

用例 列知识点_两个
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=P2 title=乙
  调用 列知识点
  得 total=2

用例 列知识点_空库
  调用 列知识点
  得 total=0

用例 列前置_直接前置
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 列前置 code=C
  得 code=C total=1

用例 列前置_没有这个点
  调用 列前置 code=NOPE
  报错 404

用例 列后续_直接后续
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=A point_code=C
  调用 列后续 code=A
  得 code=A total=2

用例 列后续_没有这个点
  调用 列后续 code=NOPE
  报错 404

用例 列祖先_间接也算
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 列祖先 code=C
  得 code=C total=2

用例 列祖先_根节点没有祖先
  先 数据 kg_point code=A title=甲
  调用 列祖先 code=A
  得 total=0

用例 列祖先_没有这个点
  调用 列祖先 code=NOPE
  报错 404

用例 列后代_间接也算
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 列后代 code=A
  得 code=A total=2

用例 列后代_没有这个点
  调用 列后代 code=NOPE
  报错 404

用例 列根节点_只有无前置的
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=D title=丁
  先 数据 kg_edge pre_code=A point_code=B
  调用 列根节点
  得 total=2

用例 列根节点_空库
  调用 列根节点
  得 total=0

用例 列分层_最长路径定深度
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  先 数据 kg_edge pre_code=A point_code=C
  调用 列分层
  得 layer_count=3

用例 列分层_空库
  调用 列分层
  得 layer_count=0

用例 加前置边_正常
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  调用 加前置边 pre_code=A point_code=B
  得 ok=1 created=1
  库 kg_edge 共 1 行
  库 kg_edge 含 pre_code=A point_code=B

用例 加前置边_重复不新增
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  调用 加前置边 pre_code=A point_code=B
  得 ok=1 created=0
  库 kg_edge 共 1 行

用例 加前置边_成环被拒
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 加前置边 pre_code=C point_code=A
  报错 400
  库 kg_edge 共 2 行

用例 加前置边_自环被拒
  先 数据 kg_point code=A title=甲
  调用 加前置边 pre_code=A point_code=A
  报错 400
  库 kg_edge 共 0 行

用例 加前置边_没有这个点
  先 数据 kg_point code=A title=甲
  调用 加前置边 pre_code=A point_code=NOPE
  报错 404
  库 kg_edge 共 0 行

用例 导出图_全部
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_contrast a_code=A b_code=B
  调用 导出图
  得 point_count=2 edge_count=1 contrast_count=1

用例 导出图_空库
  调用 导出图
  得 point_count=0 edge_count=0 contrast_count=0

用例 取条目_存在
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 取条目 code=I1
  得 code=I1 name=条目一 point_code=P1

用例 取条目_不存在
  调用 取条目 code=NOPE
  得 为空

用例 列条目_两个
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P1 prev_code=I1
  调用 列条目
  得 total=2

用例 列条目_空库
  调用 列条目
  得 total=0

用例 按知识点列条目_正常
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=P2 title=乙
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P2
  调用 按知识点列条目 point_code=P1
  得 point_code=P1 total=1

用例 按知识点列条目_没有这个点
  调用 按知识点列条目 point_code=NOPE
  报错 404

用例 列对照_全部
  先 数据 kg_contrast a_code=A b_code=B
  先 数据 kg_contrast a_code=C b_code=D
  调用 列对照
  得 total=2

用例 列对照_按一端筛选
  先 数据 kg_contrast a_code=A b_code=B
  先 数据 kg_contrast a_code=C b_code=D
  调用 列对照 code=B
  得 total=1

用例 核对条目存在_都在
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 核对条目存在 codes=I1,P1
  得 ok=1 missing_count=0

用例 核对条目存在_有缺
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 核对条目存在 codes=I1,ZZ
  得 ok=0 missing_count=1 missing=ZZ

用例 核对条目存在_空
  调用 核对条目存在 codes=空
  报错 400

用例 导入知识点_新建
  先 文件 kg_in/p.txt 内容=P1|一次函数
  调用 导入知识点 file_path=kg_in/p.txt
  得 ok=1 total=1 created=1 updated=0
  库 kg_point 含 code=P1 title=一次函数

用例 导入知识点_重复是更新
  先 数据 kg_point code=P1 title=旧名
  先 文件 kg_in/p.txt 内容=P1|新名
  调用 导入知识点 file_path=kg_in/p.txt
  得 ok=1 total=1 created=0 updated=1
  库 kg_point 共 1 行
  库 kg_point 含 code=P1 title=新名

用例 导入知识点_坏行回滚
  先 文件 kg_in/p.txt 内容=只有一项没有分隔符
  调用 导入知识点 file_path=kg_in/p.txt
  报错 400
  库 kg_point 共 0 行

用例 导入条目_新建
  先 数据 kg_point code=P1 title=甲
  先 文件 kg_in/i.txt 内容=I1|条目一|P1
  调用 导入条目 file_path=kg_in/i.txt
  得 ok=1 total=1 created=1 updated=0
  库 kg_item 含 code=I1 name=条目一 point_code=P1

用例 导入条目_重复是更新
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=旧名 point_code=P1
  先 文件 kg_in/i.txt 内容=I1|新名|P1
  调用 导入条目 file_path=kg_in/i.txt
  得 ok=1 created=0 updated=1
  库 kg_item 共 1 行
  库 kg_item 含 code=I1 name=新名

用例 导入条目_知识点对不上
  先 文件 kg_in/i.txt 内容=I1|条目一|NOPE
  调用 导入条目 file_path=kg_in/i.txt
  报错 400
  库 kg_item 共 0 行

用例 导入条目_缺字段
  先 文件 kg_in/i.txt 内容=I1
  调用 导入条目 file_path=kg_in/i.txt
  报错 400
  库 kg_item 共 0 行

用例 导入对照_新建
  先 文件 kg_in/c.txt 内容=B|A
  调用 导入对照 file_path=kg_in/c.txt
  得 ok=1 total=1 created=1 updated=0
  库 kg_contrast 共 1 行
  库 kg_contrast 含 a_code=A b_code=B

用例 导入对照_反向重复不新增
  先 数据 kg_contrast a_code=A b_code=B
  先 文件 kg_in/c.txt 内容=B|A
  调用 导入对照 file_path=kg_in/c.txt
  得 ok=1 created=0 updated=1
  库 kg_contrast 共 1 行

用例 导入对照_两端相同
  先 文件 kg_in/c.txt 内容=A|A
  调用 导入对照 file_path=kg_in/c.txt
  报错 400
  库 kg_contrast 共 0 行

用例 跨科目_列知识点只看本科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  调用 列知识点 subject=2
  得 total=2

用例 跨科目_不传科目是日语
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 列知识点
  得 total=1

用例 跨科目_取知识点别的科目当不存在
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 取知识点 code=math.a
  得 为空

用例 跨科目_取知识点本科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 取知识点 code=math.a subject=2
  得 code=math.a title=代数

用例 跨科目_列前置别的科目404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 列前置 code=math.a
  报错 404

用例 跨科目_列后代只走本科目的边
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_point code=math.c title=概率 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  先 数据 kg_edge pre_code=math.b point_code=math.c subject_id=2
  调用 列后代 code=math.a subject=2
  得 code=math.a total=2

用例 跨科目_列根节点和分层只看本科目
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  调用 列分层 subject=2
  得 layer_count=2

用例 跨科目_列根节点日语看不到2号
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 列根节点
  得 total=1

用例 跨科目_加前置边落当前科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  调用 加前置边 pre_code=math.a point_code=math.b subject=2
  得 ok=1 created=1
  库 kg_edge 含 pre_code=math.a point_code=math.b subject_id=2

用例 跨科目_加前置边不能连别的科目的点
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 加前置边 pre_code=P1 point_code=math.a subject=2
  报错 404
  库 kg_edge 共 0 行

用例 跨科目_导出图只看本科目
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  先 数据 kg_contrast a_code=math.a b_code=math.b subject_id=2
  调用 导出图 subject=2
  得 point_count=2 edge_count=1 contrast_count=1

用例 跨科目_取条目别的科目当不存在
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 取条目 code=math.i1
  得 为空

用例 跨科目_列条目只看本科目
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 列条目 subject=2
  得 total=1

用例 跨科目_按知识点列条目别的科目404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 按知识点列条目 point_code=math.a
  报错 404

用例 跨科目_列对照只看本科目
  先 数据 kg_contrast a_code=A b_code=B
  先 数据 kg_contrast a_code=math.a b_code=math.b subject_id=2
  调用 列对照 subject=2
  得 total=1

用例 跨科目_核对条目存在别的科目算缺
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 核对条目存在 codes=math.a
  得 ok=0 missing_count=1 missing=math.a

用例 跨科目_导入知识点带前缀落2号
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/p.txt 内容=math.a|代数
  调用 导入知识点 file_path=kg_in/p.txt subject=2
  得 ok=1 total=1 created=1 updated=0
  库 kg_point 含 code=math.a title=代数 subject_id=2

用例 跨科目_导入知识点前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/p.txt 内容=a|代数
  调用 导入知识点 file_path=kg_in/p.txt subject=2
  报错 400
  库 kg_point 共 0 行

用例 跨科目_导入知识点别的科目的前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/p.txt 内容=jp.a|代数
  调用 导入知识点 file_path=kg_in/p.txt subject=2
  报错 400
  库 kg_point 共 0 行

用例 跨科目_导入知识点同编号跨科目被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 文件 kg_in/p.txt 内容=math.a|甲
  调用 导入知识点 file_path=kg_in/p.txt
  报错 400
  库 kg_point 共 1 行
  库 kg_point 含 code=math.a title=代数 subject_id=2

用例 跨科目_导入条目带前缀落2号
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 文件 kg_in/i.txt 内容=math.i1|条目|math.a
  调用 导入条目 file_path=kg_in/i.txt subject=2
  得 ok=1 total=1 created=1 updated=0
  库 kg_item 含 code=math.i1 name=条目 point_code=math.a subject_id=2

用例 跨科目_导入条目前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 文件 kg_in/i.txt 内容=i1|条目|math.a
  调用 导入条目 file_path=kg_in/i.txt subject=2
  报错 400
  库 kg_item 共 0 行

用例 跨科目_导入条目挂到别的科目的点被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=甲
  先 文件 kg_in/i.txt 内容=math.i1|条目|P1
  调用 导入条目 file_path=kg_in/i.txt subject=2
  报错 400
  库 kg_item 共 0 行

用例 跨科目_导入条目同编号跨科目被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 文件 kg_in/i.txt 内容=math.i1|条目|P1
  调用 导入条目 file_path=kg_in/i.txt
  报错 400
  库 kg_item 共 1 行

用例 跨科目_导入对照带前缀落2号
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/c.txt 内容=math.b|math.a
  调用 导入对照 file_path=kg_in/c.txt subject=2
  得 ok=1 total=1 created=1 updated=0
  库 kg_contrast 含 a_code=math.a b_code=math.b subject_id=2

用例 跨科目_导入对照前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/c.txt 内容=b|a
  调用 导入对照 file_path=kg_in/c.txt subject=2
  报错 400
  库 kg_contrast 共 0 行

用例 跨科目_显式科目不是数字
  调用 列知识点 subject=abc
  报错 400

用例 跨科目_need_加前置边公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  调用 加前置边 pre_code=math.a point_code=math.b learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_edge 共 0 行

用例 跨科目_need_加前置边协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  调用 加前置边 pre_code=math.a point_code=math.b learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 created=1
  库 kg_edge 含 pre_code=math.a point_code=math.b subject_id=2

用例 跨科目_need_导入知识点公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/n1.txt 内容=math.a|代数
  调用 导入知识点 file_path=kg_in/n1.txt learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_point 共 0 行

用例 跨科目_need_导入知识点协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 文件 kg_in/n2.txt 内容=math.a|代数
  调用 导入知识点 file_path=kg_in/n2.txt learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 total=1 created=1 updated=0
  库 kg_point 含 code=math.a subject_id=2

用例 跨科目_need_导入条目公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 文件 kg_in/n3.txt 内容=math.i1|条目|math.a
  调用 导入条目 file_path=kg_in/n3.txt learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_item 共 0 行

用例 跨科目_need_导入对照公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/n4.txt 内容=math.b|math.a
  调用 导入对照 file_path=kg_in/n4.txt learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_contrast 共 0 行

用例 跨科目_need_负责教师导入对照可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 kg_in/n5.txt 内容=math.b|math.a
  调用 导入对照 file_path=kg_in/n5.txt learner=t1 current_role=teacher auth_mode=on subject=2
  得 ok=1 total=1 created=1 updated=0

用例 跨科目_need_读不受影响公共科目非负责教师可读
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 列知识点 learner=t2 current_role=teacher auth_mode=on subject=2
  得 total=1

用例 建知识点_正常
  调用 建知识点 code=P9 title=新点
  得 ok=1 code=P9
  库 kg_point 含 code=P9 title=新点 subject_id=1

用例 建知识点_本科目重号409
  先 数据 kg_point code=P1 title=甲
  调用 建知识点 code=P1 title=乙
  报错 409
  库 kg_point 共 1 行
  库 kg_point 含 code=P1 title=甲

用例 建知识点_别的科目已用409
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 建知识点 code=math.a title=甲
  报错 409
  库 kg_point 共 1 行

用例 建知识点_编号含分隔符400
  调用 建知识点 code=a>b title=甲
  报错 400
  库 kg_point 共 0 行

用例 建知识点_名称为空400
  调用 建知识点 code=P9 title=空
  报错 400
  库 kg_point 共 0 行

用例 建知识点_前缀不符400
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 建知识点 code=a title=代数 subject=2
  报错 400
  库 kg_point 共 0 行

用例 建知识点_带前缀落2号
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 建知识点 code=math.x title=代数 subject=2
  得 ok=1 code=math.x
  库 kg_point 含 code=math.x title=代数 subject_id=2

用例 建知识点_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 建知识点 code=math.x title=代数 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_point 共 0 行

用例 建知识点_已分配学生403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 建知识点 code=math.x title=代数 learner=s1 current_role=student auth_mode=on subject=2
  报错 403
  库 kg_point 共 0 行

用例 建知识点_协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  调用 建知识点 code=math.x title=代数 learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1
  库 kg_point 含 code=math.x subject_id=2

用例 建知识点_单人模式不校验身份
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 建知识点 code=math.x title=代数 learner=s1 current_role=student subject=2
  得 ok=1
  库 kg_point 含 code=math.x subject_id=2

用例 改知识点_正常
  先 数据 kg_point code=P1 title=旧名
  调用 改知识点 code=P1 title=新名
  得 ok=1
  库 kg_point 共 1 行
  库 kg_point 含 code=P1 title=新名

用例 改知识点_没有404
  调用 改知识点 code=NOPE title=甲
  报错 404

用例 改知识点_别的科目当不存在404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 改知识点 code=math.a title=甲
  报错 404
  库 kg_point 含 code=math.a title=代数

用例 改知识点_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 改知识点 code=math.a title=甲 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_point 含 code=math.a title=代数

用例 删知识点_连边一起删
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 删知识点 code=B
  得 ok=1 edges_removed=2 contrasts_removed=0
  库 kg_point 共 2 行
  库 kg_edge 共 0 行

用例 删知识点_连对照一起删
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_contrast a_code=A b_code=B
  调用 删知识点 code=A
  得 ok=1 contrasts_removed=1
  库 kg_contrast 共 0 行
  库 kg_point 共 1 行

用例 删知识点_有下挂条目409
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 删知识点 code=P1
  报错 409
  库 kg_point 共 1 行
  库 kg_item 共 1 行

用例 删知识点_没有404
  调用 删知识点 code=NOPE
  报错 404

用例 删知识点_别的科目当不存在404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 删知识点 code=math.a
  报错 404
  库 kg_point 共 1 行

用例 删知识点_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 删知识点 code=math.a learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_point 共 1 行

用例 删知识点_负责教师可删
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 删知识点 code=math.a learner=t1 current_role=teacher auth_mode=on subject=2
  得 ok=1
  库 kg_point 共 0 行

用例 删前置边_正常
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  调用 删前置边 pre_code=A point_code=B
  得 ok=1 removed=1
  库 kg_edge 共 0 行
  库 kg_point 共 2 行

用例 删前置边_方向反了404
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  调用 删前置边 pre_code=B point_code=A
  报错 404
  库 kg_edge 共 1 行

用例 删前置边_别的科目当不存在404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  调用 删前置边 pre_code=math.a point_code=math.b
  报错 404
  库 kg_edge 共 1 行

用例 删前置边_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  调用 删前置边 pre_code=math.a point_code=math.b learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_edge 共 1 行

用例 建条目_正常
  先 数据 kg_point code=P1 title=甲
  调用 建条目 code=I9 name=新条目 point_code=P1
  得 ok=1 code=I9
  库 kg_item 含 code=I9 name=新条目 point_code=P1 subject_id=1

用例 建条目_知识点不存在404
  调用 建条目 code=I9 name=新条目 point_code=NOPE
  报错 404
  库 kg_item 共 0 行

用例 建条目_前一个条目不存在404
  先 数据 kg_point code=P1 title=甲
  调用 建条目 code=I9 name=新条目 point_code=P1 prev_code=NOPE
  报错 404
  库 kg_item 共 0 行

用例 建条目_重号409
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 建条目 code=I1 name=别的 point_code=P1
  报错 409
  库 kg_item 共 1 行

用例 建条目_挂别的科目的点404
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=甲
  调用 建条目 code=math.i1 name=条目 point_code=P1 subject=2
  报错 404
  库 kg_item 共 0 行

用例 建条目_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 建条目 code=math.i1 name=条目 point_code=math.a learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_item 共 0 行

用例 改条目_正常
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=P2 title=乙
  先 数据 kg_item code=I1 name=旧名 point_code=P1
  调用 改条目 code=I1 name=新名 point_code=P2
  得 ok=1
  库 kg_item 共 1 行
  库 kg_item 含 code=I1 name=新名 point_code=P2

用例 改条目_以自己为前一个400
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 改条目 code=I1 name=条目一 point_code=P1 prev_code=I1
  报错 400

用例 改条目_前一个条目成环400
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P1 prev_code=I1
  调用 改条目 code=I1 name=条目一 point_code=P1 prev_code=I2
  报错 400
  库 kg_item 共 2 行
  库 kg_item 含 code=I2 prev_code=I1

用例 改条目_没有404
  先 数据 kg_point code=P1 title=甲
  调用 改条目 code=NOPE name=甲 point_code=P1
  报错 404

用例 改条目_别的科目当不存在404
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 改条目 code=math.i1 name=新名 point_code=P1
  报错 404
  库 kg_item 含 code=math.i1 name=条目

用例 删条目_正常
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 删条目 code=I1
  得 ok=1 contrasts_removed=0
  库 kg_item 共 0 行
  库 kg_point 共 1 行

用例 删条目_连对照一起删
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_contrast a_code=I1 b_code=P1
  调用 删条目 code=I1
  得 ok=1 contrasts_removed=1
  库 kg_contrast 共 0 行

用例 删条目_被后一个条目引用409
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P1 prev_code=I1
  调用 删条目 code=I1
  报错 409
  库 kg_item 共 2 行

用例 删条目_没有404
  调用 删条目 code=NOPE
  报错 404

用例 删条目_别的科目当不存在404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 删条目 code=math.i1
  报错 404
  库 kg_item 共 1 行

用例 加对照_正常
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 加对照 a_code=P1 b_code=I1
  得 ok=1 created=1
  库 kg_contrast 共 1 行
  库 kg_contrast 含 a_code=I1 b_code=P1 subject_id=1

用例 加对照_反向重复不新增
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_contrast a_code=A b_code=B
  调用 加对照 a_code=B b_code=A
  得 ok=1 created=0
  库 kg_contrast 共 1 行

用例 加对照_两端相同400
  先 数据 kg_point code=A title=甲
  调用 加对照 a_code=A b_code=A
  报错 400
  库 kg_contrast 共 0 行

用例 加对照_编号不存在404
  先 数据 kg_point code=A title=甲
  调用 加对照 a_code=A b_code=NOPE
  报错 404
  库 kg_contrast 共 0 行

用例 加对照_别的科目的编号404
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 加对照 a_code=A b_code=math.a
  报错 404
  库 kg_contrast 共 0 行

用例 删对照_反向也能删
  先 数据 kg_contrast a_code=A b_code=B
  调用 删对照 a_code=B b_code=A
  得 ok=1
  库 kg_contrast 共 0 行

用例 删对照_没有404
  调用 删对照 a_code=A b_code=B
  报错 404

用例 删对照_别的科目当不存在404
  先 数据 kg_contrast a_code=math.a b_code=math.b subject_id=2
  调用 删对照 a_code=math.a b_code=math.b
  报错 404
  库 kg_contrast 共 1 行

用例 查引用_知识点有下挂条目不可删
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=P2 title=乙
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_edge pre_code=P1 point_code=P2
  调用 查引用 code=P1
  得 code=P1 kind=point total=2 deletable=0

用例 查引用_只有边和对照可删
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=P2 title=乙
  先 数据 kg_edge pre_code=P1 point_code=P2
  先 数据 kg_contrast a_code=P1 b_code=P2
  调用 查引用 code=P1 kind=point
  得 kind=point total=2 deletable=1

用例 查引用_条目无引用可删
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 查引用 code=I1
  得 code=I1 kind=item total=0 deletable=1

用例 查引用_没有404
  调用 查引用 code=NOPE
  报错 404

用例 查引用_kind不对400
  先 数据 kg_point code=P1 title=甲
  调用 查引用 code=P1 kind=abc
  报错 400

用例 查引用_别的科目当不存在404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 查引用 code=math.a
  报错 404

用例 导入前置边_新建
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 文件 kg_in/e.txt 内容=A|B
  调用 导入前置边 file_path=kg_in/e.txt
  得 ok=1 total=1 created=1 updated=0
  库 kg_edge 含 pre_code=A point_code=B subject_id=1

用例 导入前置边_重复是更新
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  先 文件 kg_in/e.txt 内容=A|B
  调用 导入前置边 file_path=kg_in/e.txt
  得 ok=1 created=0 updated=1
  库 kg_edge 共 1 行

用例 导入前置边_成环整批不写
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 文件 kg_in/e.txt 内容=B|C\nC|A
  调用 导入前置边 file_path=kg_in/e.txt
  报错 400
  库 kg_edge 共 1 行

用例 导入前置边_对不上知识点
  先 数据 kg_point code=A title=甲
  先 文件 kg_in/e.txt 内容=A|NOPE
  调用 导入前置边 file_path=kg_in/e.txt
  报错 400
  库 kg_edge 共 0 行

用例 导入前置边_别的科目的点对不上
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 文件 kg_in/e.txt 内容=A|math.a
  调用 导入前置边 file_path=kg_in/e.txt
  报错 400
  库 kg_edge 共 0 行

用例 导入前置边_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 文件 kg_in/e2.txt 内容=math.a|math.b
  调用 导入前置边 file_path=kg_in/e2.txt learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_edge 共 0 行

用例 导入预检_新增和更新不写库
  先 数据 kg_point code=P1 title=旧名
  先 文件 uploads/p.txt 内容=P1|新名\nP2|乙
  调用 导入预检 kind=point file_path=uploads/p.txt
  得 kind=point total=2 ok_count=2 error_count=0 created=1 updated=1
  库 kg_point 共 1 行
  库 kg_point 含 code=P1 title=旧名

用例 导入预检_逐行报错
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 uploads/p.txt 内容=math.a|代数\nbad|乙\nmath.b|
  调用 导入预检 kind=point file_path=uploads/p.txt subject=2
  得 total=3 ok_count=1 error_count=2 created=1
  库 kg_point 共 0 行

用例 导入预检_条目可引用本文件里的前一个
  先 数据 kg_point code=P1 title=甲
  先 文件 uploads/i.txt 内容=I1|条目一|P1\nI2|条目二|P1||I1
  调用 导入预检 kind=item file_path=uploads/i.txt
  得 total=2 error_count=0 created=2
  库 kg_item 共 0 行

用例 导入预检_前置边成环标报错
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  先 文件 uploads/e.txt 内容=B|A
  调用 导入预检 kind=edge file_path=uploads/e.txt
  得 total=1 error_count=1
  库 kg_edge 共 1 行

用例 导入预检_csv
  先 文件 uploads/p.csv 内容=code,title\nP1,甲\nP2,乙
  调用 导入预检 kind=point file_path=uploads/p.csv
  得 total=2 error_count=0 created=2

用例 导入预检_json
  先 文件 uploads/p.json 内容=[{"code":"P1","title":"甲"}]
  调用 导入预检 kind=point file_path=uploads/p.json
  得 total=1 error_count=0 created=1

用例 导入预检_csv缺列400
  先 文件 uploads/p.csv 内容=code,name\nP1,甲
  调用 导入预检 kind=point file_path=uploads/p.csv
  报错 400

用例 导入预检_类型不对400
  先 文件 uploads/p.txt 内容=P1|甲
  调用 导入预检 kind=abc file_path=uploads/p.txt
  报错 400

用例 导入预检_文件类型不对400
  先 文件 uploads/p.xml 内容=P1|甲
  调用 导入预检 kind=point file_path=uploads/p.xml
  报错 400

用例 导入预检_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 uploads/p2.txt 内容=math.a|代数
  调用 导入预检 kind=point file_path=uploads/p2.txt learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403

用例 导入预检_不在uploads下400
  先 文件 kg_in/p.txt 内容=P1|甲
  调用 导入预检 kind=point file_path=kg_in/p.txt
  报错 400

用例 导入预检_行尾多余竖线按错行报
  先 文件 uploads/p.txt 内容=P1|甲|\nP2|乙
  调用 导入预检 kind=point file_path=uploads/p.txt
  得 total=2 ok_count=1 error_count=1 created=1
  库 kg_point 共 0 行

用例 导入预检_条目项数多了按错行报
  先 数据 kg_point code=P1 title=甲
  先 文件 uploads/i.txt 内容=I1|条目一|P1|||
  调用 导入预检 kind=item file_path=uploads/i.txt
  得 total=1 error_count=1

用例 导入预检_csv某行空值按错行报
  先 文件 uploads/p.csv 内容=code,title\nP1,甲\n,乙
  调用 导入预检 kind=point file_path=uploads/p.csv
  得 total=2 ok_count=1 error_count=1 created=1

用例 导入预检_csv整列值为空按错行报
  先 文件 uploads/p.csv 内容=code,title\n,甲\n,乙
  调用 导入预检 kind=point file_path=uploads/p.csv
  得 total=2 ok_count=0 error_count=2

用例 导入预检_json缺键整份不认400
  先 文件 uploads/p.json 内容=[{"title":"甲"}]
  调用 导入预检 kind=point file_path=uploads/p.json
  报错 400

用例 导入预检_同文件重复编号
  先 文件 uploads/p.txt 内容=P1|甲\nP1|乙
  调用 导入预检 kind=point file_path=uploads/p.txt
  得 total=2 error_count=0 created=1 updated=1
  库 kg_point 共 0 行

用例 确认导入_txt复用旧导入
  先 文件 uploads/p.txt 内容=P1|甲\nP2|乙
  调用 确认导入 kind=point file_path=uploads/p.txt
  得 ok=1 kind=point total=2 created=2 updated=0
  库 kg_point 共 2 行

用例 确认导入_csv条目
  先 数据 kg_point code=P1 title=甲
  先 文件 uploads/i.csv 内容=code,name,point_code\nI1,条目一,P1
  调用 确认导入 kind=item file_path=uploads/i.csv
  得 ok=1 total=1 created=1
  库 kg_item 含 code=I1 name=条目一 point_code=P1 subject_id=1

用例 确认导入_前置边
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 文件 uploads/e.txt 内容=A|B
  调用 确认导入 kind=edge file_path=uploads/e.txt
  得 ok=1 created=1
  库 kg_edge 含 pre_code=A point_code=B

用例 确认导入_有一行报错整批不写
  先 文件 uploads/p.txt 内容=P1|甲\n只有一项
  调用 确认导入 kind=point file_path=uploads/p.txt
  报错 400
  库 kg_point 共 0 行

用例 确认导入_路径不对400
  调用 确认导入 kind=point file_path=../x.txt
  报错 400

用例 确认导入_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 uploads/p3.txt 内容=math.a|代数
  调用 确认导入 kind=point file_path=uploads/p3.txt learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 kg_point 共 0 行

用例 确认导入_不在uploads下400
  先 文件 kg_in/p.txt 内容=P1|甲
  调用 确认导入 kind=point file_path=kg_in/p.txt
  报错 400
  库 kg_point 共 0 行

用例 确认导入_uploads子目录400
  先 文件 uploads/sub/p.txt 内容=P1|甲
  调用 确认导入 kind=point file_path=uploads/sub/p.txt
  报错 400
  库 kg_point 共 0 行

用例 确认导入_绝对路径400
  调用 确认导入 kind=point file_path=/tmp/p.txt
  报错 400

用例 确认导入_行尾多余竖线400
  先 文件 uploads/p.txt 内容=P1|甲|\nP2|乙
  调用 确认导入 kind=point file_path=uploads/p.txt
  报错 400
  库 kg_point 共 0 行

用例 确认导入_csv某行空值400
  先 文件 uploads/p.csv 内容=code,title\nP1,甲\n,乙
  调用 确认导入 kind=point file_path=uploads/p.csv
  报错 400
  库 kg_point 共 0 行

用例 导出文本_全部
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_item code=I1 name=条目一 point_code=A
  调用 导出文本
  得 kind=all count=4

用例 导出文本_只要条目
  先 数据 kg_point code=A title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=A
  调用 导出文本 kind=item
  得 kind=item count=1 text=I1|条目一|A||

用例 导出文本_类型不对400
  调用 导出文本 kind=abc
  报错 400

用例 导出文本_只看本科目
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 导出文本 kind=point subject=2
  得 count=1 text=math.a|代数

用例 导出文本_公共科目非负责教师可导出
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 导出文本 kind=point learner=t2 current_role=teacher auth_mode=on subject=2
  得 count=1

用例 图谱管理页面_单人模式
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  调用 图谱管理页面 learner=me
  得 can_write=1 kgm_role=单人 kgm_head=共2个知识点、1条前置边、0个条目、0条对照

用例 图谱管理页面_负责教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 图谱管理页面 learner=t1 current_role=teacher auth_mode=on subject=2
  得 can_write=1 kgm_role=负责

用例 图谱管理页面_协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  调用 图谱管理页面 learner=t2 current_role=teacher auth_mode=on subject=2
  得 can_write=1 kgm_role=协作

用例 图谱管理页面_公共科目其他教师只读
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 图谱管理页面 learner=t2 current_role=teacher auth_mode=on subject=2
  得 can_write=0 kgm_role=公共只读

用例 图谱管理页面_私有科目无关教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 图谱管理页面 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403

用例 图谱管理页面_学生403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 图谱管理页面 learner=s1 current_role=student auth_mode=on subject=2
  报错 403

用例 图谱管理页面_只看本科目
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  调用 图谱管理页面 learner=me subject=2
  得 kgm_head=共2个知识点、0条前置边、0个条目、0条对照

用例 载入知识点页面_新建空表单
  调用 载入知识点页面 learner=me
  得 kgp_orig=空 kgp_code=空

用例 载入知识点页面_编辑回填带引用
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 载入知识点页面 learner=me kgp_orig=P1
  得 kgp_orig=P1 kgp_code=P1 kgp_title=甲 kgp_refs=被引用：下挂条目1。删除会被拒绝，可以改名

用例 载入知识点页面_节点图带code
  先 数据 kg_point code=P1 title=甲
  调用 载入知识点页面 learner=me code=P1
  得 kgp_orig=P1 kgp_refs=没有被引用，可以删除

用例 载入知识点页面_没有404
  调用 载入知识点页面 learner=me kgp_orig=NOPE
  报错 404

用例 载入知识点页面_学生403
  调用 载入知识点页面 learner=s1 current_role=student auth_mode=on kgp_orig=P1
  报错 403

用例 保存知识点页面_新建
  调用 保存知识点页面 learner=me kgp_code=P9 kgp_title=新点
  得 kgm_head=共1个知识点、0条前置边、0个条目、0条对照
  库 kg_point 含 code=P9 title=新点

用例 保存知识点页面_编辑不改编号
  先 数据 kg_point code=P1 title=旧名
  调用 保存知识点页面 learner=me kgp_orig=P1 kgp_code=ZZ kgp_title=新名
  得 有返回
  库 kg_point 共 1 行
  库 kg_point 含 code=P1 title=新名

用例 保存知识点页面_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 保存知识点页面 learner=t2 current_role=teacher auth_mode=on subject=2 kgp_code=math.x kgp_title=代数
  报错 403
  库 kg_point 共 0 行

用例 删知识点页面_正常
  先 数据 kg_point code=A title=甲
  调用 删知识点页面 learner=me kgp_orig=A
  得 kgm_head=共0个知识点、0条前置边、0个条目、0条对照
  库 kg_point 共 0 行

用例 删知识点页面_引用保护409
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 删知识点页面 learner=me kgp_orig=P1
  报错 409
  库 kg_point 共 1 行

用例 加前置边页面_正常
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  调用 加前置边页面 learner=me edge_pre=A edge_point=B
  得 kgm_head=共2个知识点、1条前置边、0个条目、0条对照
  库 kg_edge 含 pre_code=A point_code=B

用例 加前置边页面_成环400
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  调用 加前置边页面 learner=me edge_pre=B edge_point=A
  报错 400
  库 kg_edge 共 1 行

用例 删前置边页面_正常
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  调用 删前置边页面 learner=me edge_key=A>B
  得 有返回
  库 kg_edge 共 0 行

用例 删前置边页面_参数不对400
  调用 删前置边页面 learner=me edge_key=AB
  报错 400

用例 载入条目页面_编辑回填
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 载入条目页面 learner=me kgi_orig=I1
  得 kgi_orig=I1 kgi_name=条目一 kgi_point=P1 kgi_prev=空

用例 载入条目页面_新建空表单
  调用 载入条目页面 learner=me
  得 kgi_orig=空 kgi_code=空

用例 载入条目页面_没有404
  调用 载入条目页面 learner=me kgi_orig=NOPE
  报错 404

用例 保存条目页面_新建
  先 数据 kg_point code=P1 title=甲
  调用 保存条目页面 learner=me kgi_code=I9 kgi_name=新条目 kgi_point=P1
  得 有返回
  库 kg_item 含 code=I9 name=新条目 point_code=P1

用例 保存条目页面_编辑不改编号
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=旧名 point_code=P1
  调用 保存条目页面 learner=me kgi_orig=I1 kgi_code=ZZ kgi_name=新名 kgi_point=P1
  得 有返回
  库 kg_item 共 1 行
  库 kg_item 含 code=I1 name=新名

用例 删条目页面_引用保护409
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P1 prev_code=I1
  调用 删条目页面 learner=me kgi_orig=I1
  报错 409
  库 kg_item 共 2 行

用例 删条目页面_正常
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 删条目页面 learner=me kgi_orig=I1
  得 有返回
  库 kg_item 共 0 行

用例 加对照页面_正常
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  调用 加对照页面 learner=me ct_a=B ct_b=A
  得 kgm_head=共2个知识点、0条前置边、0个条目、1条对照
  库 kg_contrast 含 a_code=A b_code=B

用例 删对照页面_正常
  先 数据 kg_contrast a_code=A b_code=B
  调用 删对照页面 learner=me ct_key=A~B
  得 有返回
  库 kg_contrast 共 0 行

用例 删对照页面_参数不对400
  调用 删对照页面 learner=me ct_key=AB
  报错 400

用例 导入预检页面_预览
  先 文件 uploads/p.txt 内容=P1|甲
  调用 导入预检页面 learner=me imp_kind=知识点 imp_upload_path=uploads/p.txt
  得 imp_ok=1 imp_head=共1行：新增1、更新0、报错0
  库 kg_point 共 0 行

用例 导入预检页面_有报错不能确认
  先 文件 uploads/p.txt 内容=P1|甲\n只有一项
  调用 导入预检页面 learner=me imp_kind=知识点 imp_upload_path=uploads/p.txt
  得 imp_ok=0
  库 kg_point 共 0 行

用例 导入预检页面_类型不对400
  先 文件 uploads/p.txt 内容=P1|甲
  调用 导入预检页面 learner=me imp_kind=别的 imp_upload_path=uploads/p.txt
  报错 400

用例 确认导入页面_导入
  先 文件 uploads/p.txt 内容=P1|甲
  调用 确认导入页面 learner=me imp_kind=知识点 imp_file=uploads/p.txt
  得 imp_ok=0 imp_head=已导入：新增1、更新0
  库 kg_point 含 code=P1 title=甲

用例 确认导入页面_公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 uploads/p4.txt 内容=math.a|代数
  调用 确认导入页面 learner=t2 current_role=teacher auth_mode=on subject=2 imp_kind=知识点 imp_file=uploads/p4.txt
  报错 403
  库 kg_point 共 0 行

用例 确认导入页面_不在uploads下400
  先 文件 kg_in/p.txt 内容=P1|甲
  调用 确认导入页面 learner=me imp_kind=知识点 imp_file=kg_in/p.txt
  报错 400
  库 kg_point 共 0 行

用例 导出页面_全部
  先 数据 kg_point code=A title=甲
  调用 导出页面 learner=me
  得 export_head=共1行。四段要按段拆开分别导入

用例 导出页面_类型不对400
  调用 导出页面 learner=me exp_kind=别的
  报错 400
