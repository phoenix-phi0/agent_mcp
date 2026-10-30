模块 subject
依赖 无

## 表
表 subject_info
  code 文本 科目编码，唯一；小写字母数字下划线；日语语法是 jp_grammar
  name 文本 显示名，如 日语语法
  intro 长文本 说明，可空
  kind 文本 类型：language 或 general
  caps 文本 能力开关 JSON，如 {"vocab":1,"dictation":1,"lesson":1,"levels":1,"jp_judge":1,"textbook_import":1}，缺省键视为 0
  levels 文本 自定义等级列表，英文逗号分隔有序（日语 N5,N4,N3,N2,N1），空表示不分级
  qtypes 文本 启用的题型，英文逗号分隔（日语 choice,fill）
  visibility 文本 public 或 private
  owner 文本 创建者教师用户名
  status 文本 active（启用）/ disabled（停用，不删数据）/ draft（未发布，学生看不到）
  created_at 文本 建于时间，格式 YYYY-MM-DD HH:MM:SS
  updated_at 文本 改于时间，格式 YYYY-MM-DD HH:MM:SS
表 subject_teacher
  subject_id 整数 科目编号（subject_info 的 id）
  teacher 文本 教师用户名；subject_id + teacher 唯一
  role 文本 owner（负责）或 editor（协作）
  created_at 文本 建于时间
表 subject_student
  subject_id 整数 科目编号
  learner 文本 学生用户名；subject_id + learner 唯一
  assigned_by 文本 分配的教师用户名，迁移登记的是空串
  status 文本 active 或 revoked（撤销，保留作答数据）
  created_at 文本 建于时间
表 subject_pref
  learner 文本 学习者，唯一
  subject_id 整数 当前科目编号
表 subject_ai
  subject_id 整数 科目编号，唯一
  persona 长文本 老师人设，可空
  tutor_prompt 长文本 问老师提示词，可空
  assist_prompt 长文本 教师助手提示词，可空
  summary_prompt 长文本 学情总结提示词，可空
  import_prompt 长文本 教材导入提示词，可空
  kg_gen_prompt 长文本 图谱生成提示词，可空
  updated_by 文本 最后修改的教师，可空
  updated_at 文本 最后修改时间，可空

## 页面字段
页面 subject_view 科目管理页面
  subj_id 整数 科目表「编号」列，也是编辑/成员浮层地址里带的科目编号
  subj_code 文本 科目编码（新建时填，建后不可改）
  subj_name 文本 科目名称
  subj_intro 长文本 科目说明
  subj_kind 枚举 通用,语言 类型（页面值域中文；通用存 general、语言存 language）
  subj_visibility 文本 科目表「可见性」列（公共/私有）
  subj_status 文本 科目表「状态」列（启用/停用/草稿）
  subj_owner 文本 科目表「创建者」列
  subj_my_role 文本 科目表「我的身份」列（负责/协作/公共只读/单人）
  subj_student_n 整数 科目表「在册学生」列
  subj_teacher_n 整数 科目表「教师数」列
  manage_head 文本 页面抬头

## 函数
公开 函数 科目访问 learner current_role subject_id need auth_mode?
  返回 {ok, reason, via}；ok 为 1 通过 / 0 拒绝；reason 是拒绝原因（通过时空串）；via 是凭什么通过：assigned（学生已分配）/ owner / editor / public / single（单人模式）/ 空串
  报错 400 need 不对
  伪代码 need 不是 read、write、settings、assign 之一，报错 400 need 不对
  伪代码 current_role 不是 student 也不是 teacher（单人模式或不登录）：auth_mode 等于 on（登录模式却没有角色），返回 {"ok": 0, "reason": "没有权限访问该科目", "via": ""}，不查库；auth_mode 不传或不等于 on，返回 {"ok": 1, "reason": "", "via": "single"}，不查库（不传 auth_mode 时行为同旧）
  伪代码 按 subject_id 查 subject_info，查不到返回 {"ok": 0, "reason": "没有这个科目", "via": ""}
  伪代码 current_role 等于 student：只有 need 等于 read 才可能通过；该科目 status 必须是 active，且 subject_student 有 (subject_id, learner) 的行且 status 等于 active，才返回 {"ok": 1, "reason": "", "via": "assigned"}；否则返回 {"ok": 0, "reason": "该科目未分配给你", "via": ""}（need 不是 read 时 reason 为「学生没有这个权限」）
  伪代码 current_role 等于 teacher：先定身份——科目 owner 等于 learner、或 subject_teacher 有 (subject_id, learner) 且 role 等于 owner，则是 owner；有 (subject_id, learner) 且 role 等于 editor，则是 editor；否则看 visibility 等于 public 且 status 不是 draft 则是 public；其余是 none
  伪代码 教师权限矩阵：read——owner、editor、public 通过；write——owner、editor 通过；settings——只有 owner 通过；assign——owner、editor、public 通过；none 一律拒绝，reason 为「没有权限访问该科目」；身份不够时 reason 为「没有这个权限」；通过时 via 是 owner / editor / public
  伪代码 停用的科目教师照样能读（排查用）；draft 的科目只有 owner、editor 能读

公开 函数 列我的科目 learner current_role
  返回 {total, subjects}；subjects 是 [{id, code, name, kind, visibility}]，按 id 升序
  伪代码 current_role 等于 student：subject_student 里该 learner 且 status 等于 active 的科目，且科目 status 等于 active
  伪代码 current_role 等于 teacher：科目 owner 等于 learner、或 subject_teacher 有该 learner 的行的科目（不论 status）；再加上 visibility 等于 public 且 status 不是 draft 的科目；去重
  伪代码 其他 current_role（单人模式或不登录）：visibility 等于 public 且 status 等于 active 的科目
  伪代码 返回 {"total": 数量, "subjects": 列表}

公开 函数 当前科目 learner current_role?
  返回 {subject_id}；当前科目编号，不报错，永远有值
  伪代码 learner 为空，返回 {"subject_id": 1}
  伪代码 按 learner 查 subject_pref；有行且 subject_info 有该科目、status 不是 draft，并且 (a) subject_student 有 (subject_id, learner) 且 status 等于 active 且科目 status 等于 active，或 (b) 科目 owner 等于 learner，或 (c) subject_teacher 有 (subject_id, learner) 的行，或 (d) current_role 等于 teacher 且该科目 visibility 等于 public 且 status 等于 active（教师切到无关系的公共科目也算有效），才返回 {"subject_id": 偏好科目}；current_role 不传或为 student 时没有 (d)，学生仍只认已分配（(a)）
  伪代码 偏好失效或没有偏好：取 subject_student 中该 learner 且 status 等于 active、科目 status 等于 active 的最小 subject_id；有则返回它
  伪代码 都没有（比如单人模式、还没分配科目、教师没有偏好）返回 {"subject_id": 1}，保证日语旧行为不变
  伪代码 只读；不调用别的模块

公开 函数 解析科目 learner current_role auth_mode subject? need?
  返回 {subject_id}；本次请求用哪个科目
  报错 400 subject 不对
  报错 400 need 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 403 只有科目负责人可以操作
  报错 404 没有这个科目
  伪代码 上面的 403、404（含各模块函数头「报错 404 没有这个科目」「报错 403 …」那几行）只在登录模式（auth_mode 等于 on）下出现；单人/不登录模式不校验权限、不查库，显式 subject 原样返回，所以「学生也能改」的印象只会来自误用单人模式（README 要写明）
  伪代码 need 缺省或 read：以下行为与旧版完全一致；need 为 write：见最后三条；need 为 own：见最后一条
  伪代码 解析顺序：请求里显式 subject（地址参数，路由注入）→ 偏好 → 第一个已分配 → 1；显式 subject 无权报 403
  伪代码 subject 不为空：不是纯数字，报错 400 subject 不对；auth_mode 不等于 on，直接返回 {"subject_id": 该数字}（单人模式不校验，也不查库）
  伪代码 subject 不为空且 auth_mode 等于 on：按「科目访问 need=read auth_mode=on」判断（空角色也被拒），ok 为 0 时——科目不存在报错 404 没有这个科目；current_role 等于 student 报错 403 该科目未分配给你；否则报错 403 没有权限访问该科目；ok 为 1 返回 {"subject_id": 该数字}
  伪代码 subject 为空：直接返回「当前科目 learner=learner current_role=current_role」的结果（偏好 → 第一个已分配 → 1），不校验、不报错
  伪代码 need 校验：need 不为空且不是 read、write、own 之一，报错 400 need 不对（最先检查，不论 auth_mode）
  伪代码 need 等于 write 且 auth_mode 等于 on：先按上面两条解析出 subject_id（显式 subject 的 400/403/404 照旧），再按「科目访问 need=write auth_mode=on」判断，ok 为 0 时——科目不存在报错 404 没有这个科目，否则报错 403 没有权限修改该科目（学生、没有关系的教师、公共科目的非负责/协作教师都是它）；ok 为 1 返回 {"subject_id": 该数字}。即登录模式下只有科目的负责/协作教师能通过写校验
  伪代码 need 等于 write 但 auth_mode 不等于 on（单人/不登录）：不校验，同 need 缺省
  伪代码 need 等于 own（仅负责人通过，给改「全部科目(0)」的内容用）且 auth_mode 等于 on：先按上面两条解析出 subject_id（显式 subject 的 400/403/404 照旧），再按「科目访问 need=settings auth_mode=on」判断，ok 为 0 时——科目不存在报错 404 没有这个科目，否则报错 403 只有科目负责人可以操作（协作教师、公共科目的其他教师、学生都是它）；ok 为 1 返回 {"subject_id": 该数字}；need 等于 own 但 auth_mode 不等于 on：不校验，同 need 缺省

公开 函数 列科目学生 subject_id
  返回 {total, students}；students 是 [{learner}]，subject_student 里该科目 status 等于 active 的学生，按 learner 升序（report、assist_common 用；学生范围的唯一规则，没有「1 号=全部学生」的特例）
  伪代码 查 subject_student 中 subject_id 相等且 status 等于 active 的行，按 learner 升序，去重
  伪代码 不校验权限（调用方已解析科目）、只读、不调用别的模块；科目不存在或没人登记返回 {"total": 0, "students": []}
  伪代码 返回 {"total": 数量, "students": 列表}

公开 函数 登记学生 learner code?
  返回 {registered, subject_id}；把学生登记进一个科目（code 缺省为 jp_grammar，即日语语法），给 account.建学生 用（account 不直接写 subject 的表，依赖方向 account → subject，不成环）
  伪代码 learner 为空返回 {"registered": 0, "subject_id": 0}，不报错
  伪代码 code 为空取 jp_grammar；按 code 查 subject_info（不按 id=1 判断），查不到返回 {"registered": 0, "subject_id": 0}，不报错（库里还没有该科目时建学生照常成功）
  伪代码 subject_student 已有 (subject_id, learner) 的行（不论 active 还是 revoked）就不动，返回 {"registered": 0, "subject_id": 该科目 id}（幂等，不把被撤销的学生重新加回来）
  伪代码 否则插入 subject_student (subject_id, learner, assigned_by=空串, status=active, created_at=当前时间)，返回 {"registered": 1, "subject_id": 该科目 id}
  伪代码 不校验权限、不检查 learner 是否真是学生（调用方负责）、不调用别的模块

公开 函数 切换科目 learner current_role subject
  返回 {ok, subject}；把该用户的当前科目偏好写成 subject
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 learner 为空，报错 400 subject 不对
  伪代码 subject 不是纯数字，报错 400 subject 不对
  伪代码 按「科目访问 need=read」校验（current_role 取入参）：ok 为 0 时——科目不存在报错 404 没有这个科目；current_role 等于 student 报错 403 该科目未分配给你；否则报错 403 没有权限访问该科目；
  伪代码 通过后写 subject_pref：该 learner 没有行则插入 (learner, subject_id)，有则更新 subject_id
  伪代码 返回 {"ok": 1, "subject": 该数字}

函数 管理校验 learner subject_id need current_role? auth_mode?
  返回 {subject_id, code, status, visibility, owner, via}；科目管理类函数的统一入口校验（私有）：科目存在、登录模式下是教师、并且按 need 有权；via 同 科目访问（owner / editor / public / single）
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 403 没有权限给该科目分配学生
  报错 403 没有权限访问该科目
  伪代码 subject_id 为空或不是纯数字，报错 400 subject_id 不对
  伪代码 按 subject_id 查 subject_info，查不到报错 404 没有这个科目（单人模式也查，科目不存在照样 404）
  伪代码 auth_mode 不等于 on（单人/不登录）：不校验角色和权限，返回该科目的 {subject_id, code, status, visibility, owner, "via": "single"}
  伪代码 auth_mode 等于 on：current_role 不等于 teacher（学生、空角色），报错 403 只有教师可以管理科目（先于权限矩阵判断）
  伪代码 need 只会是 read、settings、assign 之一（本模块内部调用，写死）；调用 科目访问 learner=learner current_role=current_role subject_id=subject_id need=need auth_mode=auth_mode，ok 为 0 时：need 等于 settings 报错 403 只有科目负责人可以操作；need 等于 assign 报错 403 没有权限给该科目分配学生；need 等于 read 报错 403 没有权限访问该科目
  伪代码 ok 为 1 返回 {"subject_id": 该数字, "code": 该行 code, "status": 该行 status, "visibility": 该行 visibility, "owner": 该行 owner, "via": 科目访问 的 via}

函数 负责人数 subject_id except?
  返回 {n}；该科目的负责人个数（私有）：subject_info.owner 不为空算 1 个，再加 subject_teacher 中 role 等于 owner 且 teacher 不等于 subject_info.owner 的行数；except 不为空时，把 teacher 等于 except 的那一行（以及 owner 等于 except 时的 subject_info.owner）排除后再数
  伪代码 只读；给 改科目教师角色、移除科目教师 判「不能去掉最后一个负责人」用

公开 函数 建科目 learner code name intro? kind? current_role? auth_mode?
  返回 {id, code}；新建一个科目，建者自动成为负责人；新科目默认 private（私有）、draft（草稿，学生看不到，别的教师也看不到），由负责人「启用」后才对学生生效
  报错 400 learner 不能为空
  报错 403 只有教师可以管理科目
  报错 400 科目编码只能是小写字母开头的小写字母、数字、下划线，最长20
  报错 400 jp_grammar 是日语科目的保留编码
  报错 409 科目编码已存在
  报错 400 科目名称不能为空
  报错 400 科目名称最长40字
  报错 400 类型只能是 language 或 general
  伪代码 learner 为空，报错 400 learner 不能为空
  伪代码 auth_mode 等于 on 且 current_role 不等于 teacher，报错 403 只有教师可以管理科目（任何教师都能建，包括建成公共科目——K71 决定 1 选 A）；auth_mode 不等于 on（单人/不登录）不校验角色
  伪代码 code 去掉首尾空白；不匹配 ^[a-z][a-z0-9_]*$ 或长度超过 20，报错 400 科目编码只能是小写字母开头的小写字母、数字、下划线，最长20
  伪代码 code 等于 jp_grammar（不论库里有没有日语科目），报错 400 jp_grammar 是日语科目的保留编码
  伪代码 subject_info 已有该 code，报错 409 科目编码已存在（code 全局唯一，兼作该科目知识点/条目编号前缀）
  伪代码 name 去掉首尾空白后为空，报错 400 科目名称不能为空；超过 40 个字，报错 400 科目名称最长40字（name 不要求唯一）
  伪代码 kind 为空取 general；不是 language 也不是 general，报错 400 类型只能是 language 或 general
  伪代码 caps 按类型取默认模板：general 为 {"kg":1,"quiz":1,"progress":1,"tutor":1}；language 为 {"kg":1,"quiz":1,"progress":1,"tutor":1,"lesson":1,"textbook_import":1,"vocab":1,"dictation":1,"levels":1}（jp_judge 不开，日语判分只给日语科目）；levels 为空串；qtypes 为 choice,fill
  伪代码 在一个事务里：插入 subject_info (code, name, intro=intro 或空串, kind, caps, levels, qtypes, visibility=private, owner=learner, status=draft, created_at=当前时间, updated_at=当前时间)；再插入 subject_teacher (subject_id=新 id, teacher=learner, role=owner, created_at=当前时间)
  伪代码 不写 subject_pref（建者要用新科目时自己切换；auth_me 的 subjects 由 列我的科目 现算，教师自己负责的科目不论状态都在里面，刷新页面后顶栏下拉即可见）
  伪代码 返回 {"id": 新 id, "code": code}

公开 函数 改科目 learner subject_id name? intro? current_role? auth_mode?
  返回 {ok}；改科目的名称和说明（只有负责人）；code 永不可改（任何科目都没有改 code 的入口，1 号日语科目的 jp_grammar 因此受保护）
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 400 科目名称最长40字
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=settings current_role=current_role auth_mode=auth_mode（400/404/403 由它报）
  伪代码 name 去掉首尾空白后为空：不改名；否则超过 40 个字报错 400 科目名称最长40字，不超过则改名
  伪代码 intro：按传入值原样写（不传或空串即清空说明；页面保存时名称和说明总是一起提交）
  伪代码 更新 subject_info 的 name、intro、updated_at=当前时间；返回 {"ok": 1}

公开 函数 设科目可见性 learner subject_id visibility current_role? auth_mode?
  返回 {ok, visibility}；把科目设为公共（public）或私有（private），只有负责人
  报错 400 可见性只能是 public 或 private
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 409 日语科目必须是公共科目
  报错 409 还有其他教师分配的在册学生，不能改成私有
  伪代码 visibility 不是 public 也不是 private，报错 400 可见性只能是 public 或 private（最先检查）
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=settings current_role=current_role auth_mode=auth_mode
  伪代码 科目 code 等于 jp_grammar 且 visibility 等于 private，报错 409 日语科目必须是公共科目（1 号科目保护，单人模式也拦）
  伪代码 visibility 等于 private 且该科目现在是 public：查 subject_student 中该科目 status 等于 active、assigned_by 不为空、且 assigned_by 既不是 subject_info.owner 也不在 subject_teacher（该科目任何角色）里的行；有就报错 409 还有其他教师分配的在册学生，不能改成私有（改私有后那些教师会失去访问，K71 permissions §2；先撤销或把那些教师加为协作再改）
  伪代码 值与现状相同也照常返回（幂等）；否则更新 visibility、updated_at=当前时间
  伪代码 返回 {"ok": 1, "visibility": visibility}

公开 函数 设科目状态 learner subject_id status current_role? auth_mode?
  返回 {ok, status}；启用（active）或停用（disabled）科目，只有负责人；草稿（draft）启用后就是发布，不能改回草稿
  报错 400 状态只能是 active 或 disabled
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 409 日语科目不能停用
  伪代码 status 不是 active 也不是 disabled，报错 400 状态只能是 active 或 disabled（最先检查）
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=settings current_role=current_role auth_mode=auth_mode
  伪代码 科目 code 等于 jp_grammar 且 status 等于 disabled，报错 409 日语科目不能停用（1 号科目保护，单人模式也拦）
  伪代码 草稿（draft）可以直接启用（发布），也可以直接停用；停用后再启用就是 active
  伪代码 值与现状相同也照常返回（幂等）；否则更新 status、updated_at=当前时间；不删任何数据（分配、作答、偏好都保留）
  伪代码 停用后的行为（都由现有函数的既有规则得出，本函数不改别的表）：学生——列我的科目 不再列出、auth_me 的 subjects 里没有、当前科目 的偏好失效回退到下一个已分配科目（都没有回 1）、显式 ?subject= 访问报 403 该科目未分配给你、切换科目 报 403；教师——负责/协作教师照样在 列我的科目、列可管理科目 里看到（状态「停用」），能读、能切过去排查；公共科目的其他教师在 列可管理科目 里看到「停用」只读行，当前科目 偏好它会回退；停用期间不能分配学生（分配学生 报 409），可以撤销；重新启用后原分配全部恢复生效
  伪代码 返回 {"ok": 1, "status": status}

公开 函数 列可管理科目 learner current_role? auth_mode?
  返回 {total, subjects}；subjects 是 [{id, code, name, intro, kind, visibility, status, owner, my_role, student_n, teacher_n}]，按 id 升序；科目管理页的数据源
  报错 403 只有教师可以管理科目
  伪代码 auth_mode 等于 on 且 current_role 不等于 teacher，报错 403 只有教师可以管理科目
  伪代码 auth_mode 等于 on：列出 (a) 科目 owner 等于 learner、或 subject_teacher 有 (subject_id, learner) 的科目（不论 status，含草稿和停用），my_role 为 owner（owner 等于 learner 或 role 等于 owner）或 editor；(b) 其余 visibility 等于 public 且 status 不是 draft 的科目，my_role 为 public（只读，可分配）；他人的私有科目和他人的草稿不列
  伪代码 auth_mode 不等于 on（单人/不登录）：列出全部科目，my_role 为 single
  伪代码 student_n 是 subject_student 中该科目 status 等于 active 的行数；teacher_n 是 调用 列科目教师 subject_id=该科目 id 的 total
  伪代码 返回 {"total": 数量, "subjects": 列表}

公开 函数 科目详情 learner subject_id current_role? auth_mode?
  返回 {id, code, name, intro, kind, visibility, status, owner, my_role, teachers, students}；teachers 同 列科目教师 的 teachers；students 是 [{learner, status, assigned_by, created_at}]（该科目 subject_student 全部行，status 等于 active 的在前，各自按 learner 升序）
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 没有权限访问该科目
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=read current_role=current_role auth_mode=auth_mode，得 via 作为 my_role（owner / editor / public / single）；停用的科目照样能看（排查用）
  伪代码 teachers：调用 列科目教师 subject_id=subject_id 取 teachers
  伪代码 返回 {"id": 科目 id, "code", "name", "intro", "kind", "visibility", "status", "owner"（该行原值）, "my_role": via, "teachers": 列表, "students": 列表}

公开 函数 列科目教师 subject_id
  返回 {total, teachers}；teachers 是 [{teacher, role, creator}]：先放创建者（subject_info.owner，不为空时，role 为 owner，creator 为 1），再放 subject_teacher 中该科目 teacher 不等于创建者的行（creator 为 0），role 为 owner 的在前，各自按 teacher 升序
  伪代码 不校验权限（调用方已校验）、只读、不调用别的模块；科目不存在返回 {"total": 0, "teachers": []}
  伪代码 返回 {"total": 数量, "teachers": 列表}

公开 函数 加科目教师 learner subject_id teacher role? current_role? auth_mode?
  返回 {ok}；把一位教师加进科目（负责 owner 或协作 editor，默认协作），只有负责人；不检查 teacher 是不是真有这个教师账号（subject 是叶子模块，账号校验由 account.加科目教师页面 做）
  报错 400 教师用户名不能为空
  报错 400 角色只能是 owner 或 editor
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 409 该教师已在本科目
  伪代码 teacher 去掉首尾空白后为空，报错 400 教师用户名不能为空
  伪代码 role 为空取 editor；不是 owner 也不是 editor，报错 400 角色只能是 owner 或 editor
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=settings current_role=current_role auth_mode=auth_mode（协作教师不能加人：403 只有科目负责人可以操作）
  伪代码 teacher 等于 subject_info.owner，或 subject_teacher 已有 (subject_id, teacher)，报错 409 该教师已在本科目（改角色走 改科目教师角色）
  伪代码 插入 subject_teacher (subject_id, teacher, role, created_at=当前时间)；返回 {"ok": 1}

公开 函数 改科目教师角色 learner subject_id teacher role current_role? auth_mode?
  返回 {ok}；把科目里一位教师改成负责（owner）或协作（editor），只有负责人
  报错 400 角色只能是 owner 或 editor
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 409 科目创建者始终是负责人
  报错 404 该教师不在本科目
  报错 409 不能去掉最后一个负责人
  伪代码 role 不是 owner 也不是 editor，报错 400 角色只能是 owner 或 editor（最先检查）
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=settings current_role=current_role auth_mode=auth_mode
  伪代码 teacher 等于 subject_info.owner（创建者；科目访问 总把创建者当负责人，改了也不生效），报错 409 科目创建者始终是负责人
  伪代码 subject_teacher 没有 (subject_id, teacher) 的行，报错 404 该教师不在本科目
  伪代码 role 等于 editor 且该行 role 等于 owner：调用 负责人数 subject_id=subject_id except=teacher，n 为 0 报错 409 不能去掉最后一个负责人
  伪代码 更新该行 role；返回 {"ok": 1}（负责人可以把自己降为协作，只要还剩别的负责人）

公开 函数 移除科目教师 learner subject_id teacher current_role? auth_mode?
  返回 {ok}；把一位教师移出科目，只有负责人；只删 subject_teacher 这一行，他写过的内容不动
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 409 科目创建者不能移除
  报错 404 该教师不在本科目
  报错 409 不能移除最后一个负责人
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=settings current_role=current_role auth_mode=auth_mode
  伪代码 teacher 等于 subject_info.owner，报错 409 科目创建者不能移除（换创建者属于「转让负责人」，本期不做，见 k94_review 待决定）
  伪代码 subject_teacher 没有 (subject_id, teacher) 的行，报错 404 该教师不在本科目
  伪代码 该行 role 等于 owner：调用 负责人数 subject_id=subject_id except=teacher，n 为 0 报错 409 不能移除最后一个负责人
  伪代码 删除该行；被移除教师的 subject_pref 不动（当前科目 会自动判失效回退）；返回 {"ok": 1}

公开 函数 分配学生 learner subject_id learners current_role? auth_mode?
  返回 {assigned, reactivated, skipped}；把一批学生分配进科目（批量用英文逗号分隔的 learners，一个学生也是一项的列表；不做「多次调用」口径）；负责、协作、公共科目的其他教师都能分配（need=assign，K71 决定 7）；不检查是不是真有这些学生账号（账号校验由 account.分配科目学生页面 做）
  报错 400 请选择要分配的学生
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 没有权限给该科目分配学生
  报错 409 科目已停用，不能分配学生
  伪代码 learners 按英文逗号拆开，每项去掉首尾空白，丢掉空项，去重（保持先后顺序）；一项都没有，报错 400 请选择要分配的学生
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=assign current_role=current_role auth_mode=auth_mode
  伪代码 科目 status 等于 disabled，报错 409 科目已停用，不能分配学生（草稿科目可以先分配，启用后学生才看得到）
  伪代码 在一个事务里逐个处理：subject_student 没有 (subject_id, 该学生) 的行则插入 (subject_id, learner=该学生, assigned_by=learner, status=active, created_at=当前时间)，assigned 加 1；有行且 status 等于 revoked 则把 status 改回 active、assigned_by 改为 learner，reactivated 加 1；已是 active 则不动，skipped 加 1
  伪代码 返回 {"assigned": 数, "reactivated": 数, "skipped": 数}

公开 函数 撤销学生 learner subject_id student current_role? auth_mode?
  返回 {ok}；把一个学生从科目撤销（status 改 revoked，保留行和作答数据，可再分配恢复）
  报错 400 学生用户名不能为空
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 没有权限给该科目分配学生
  报错 404 该学生不在本科目
  报错 403 只能撤销自己分配的学生
  伪代码 student 去掉首尾空白后为空，报错 400 学生用户名不能为空
  伪代码 调用 管理校验 learner=learner subject_id=subject_id need=assign current_role=current_role auth_mode=auth_mode，得 via
  伪代码 subject_student 没有 (subject_id, student) 且 status 等于 active 的行，报错 404 该学生不在本科目
  伪代码 via 等于 public（公共科目的其他教师）且该行 assigned_by 不等于 learner，报错 403 只能撤销自己分配的学生（负责/协作教师、单人模式可以撤销任何人；此条为推荐口径，待用户确认）
  伪代码 停用的科目也可以撤销
  伪代码 更新该行 status=revoked；返回 {"ok": 1}

公开 函数 科目管理页面 learner current_role? auth_mode?
  返回 {subjects, manage_head, can_create}；「科目管理」页「进入时」的整页状态（动作 subject_manage_home）；subjects 是表格行 [{subj_id, subj_code, subj_name, subj_kind, subj_visibility, subj_status, subj_owner, subj_my_role, subj_student_n, subj_teacher_n, can_manage, can_assign}]
  报错 403 只有教师可以管理科目
  伪代码 调用 列可管理科目 learner=learner current_role=current_role auth_mode=auth_mode（学生 403）
  伪代码 每行转页面口径：subj_id=id，subj_code=code，subj_name=name，subj_kind：language 为「语言」否则「通用」，subj_visibility：public 为「公共」否则「私有」，subj_status：active「启用」、disabled「停用」、draft「草稿」，subj_owner=owner，subj_my_role：owner「负责」、editor「协作」、public「公共只读」、single「单人」，subj_student_n=student_n，subj_teacher_n=teacher_n，can_manage：my_role 是 owner 或 single 为 1 否则 0，can_assign：status 不是 disabled 为 1 否则 0
  伪代码 manage_head：「我能管理的科目共{total}个」（不含空格）；can_create：auth_mode 等于 on 时 current_role 等于 teacher 为 1，否则 1（单人模式也能建）
  伪代码 返回 {"subjects": 行表, "manage_head": 文案, "can_create": 1}

公开 函数 载入科目页面 learner subj_id? current_role? auth_mode?
  返回 回填表单 {subj_id, subj_code, subj_name, subj_intro, subj_kind}（动作 subject_open，「编辑科目」浮层的「载入」）
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  伪代码 subj_id 为空（新建）返回空表单 {"subj_id": "", "subj_code": "", "subj_name": "", "subj_intro": "", "subj_kind": "通用"}
  伪代码 否则调用 管理校验 learner=learner subject_id=subj_id need=settings current_role=current_role auth_mode=auth_mode（只有负责人能打开编辑），查 subject_info 返回 {"subj_id": id, "subj_code": code, "subj_name": name, "subj_intro": intro 或空串, "subj_kind": language 为「语言」否则「通用」}

公开 函数 保存科目页面 learner subj_name subj_id? subj_code? subj_intro? subj_kind? current_role? auth_mode?
  返回 刷新后的整页状态，形状同 科目管理页面
  报错 400 learner 不能为空
  报错 400 类型只能是 language 或 general
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 400 科目编码只能是小写字母开头的小写字母、数字、下划线，最长20
  报错 400 jp_grammar 是日语科目的保留编码
  报错 409 科目编码已存在
  报错 400 科目名称不能为空
  报错 400 科目名称最长40字
  伪代码 subj_kind 页面值转换：「通用」或空为 general，「语言」为 language，其他值原样交下去（由 建科目 报 400 类型只能是 language 或 general）
  伪代码 subj_id 为空（新建）：调用 建科目 learner=learner code=subj_code name=subj_name intro=subj_intro kind=转换后 current_role=current_role auth_mode=auth_mode
  伪代码 subj_id 不为空（编辑）：subj_code、subj_kind 忽略（建后不可改）；调用 改科目 learner=learner subject_id=subj_id name=subj_name intro=subj_intro current_role=current_role auth_mode=auth_mode
  伪代码 返回 调用 科目管理页面 learner=learner current_role=current_role auth_mode=auth_mode 的结果

公开 函数 设科目可见性页面 learner subj_id visibility current_role? auth_mode?
  返回 刷新后的整页状态，形状同 科目管理页面（行动作「设为公共」「设为私有」，路由用「传」写死 visibility）
  报错 400 可见性只能是 public 或 private
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 409 日语科目必须是公共科目
  报错 409 还有其他教师分配的在册学生，不能改成私有
  伪代码 调用 设科目可见性 learner=learner subject_id=subj_id visibility=visibility current_role=current_role auth_mode=auth_mode
  伪代码 返回 调用 科目管理页面 learner=learner current_role=current_role auth_mode=auth_mode 的结果

公开 函数 设科目状态页面 learner subj_id status current_role? auth_mode?
  返回 刷新后的整页状态，形状同 科目管理页面（行动作「启用」「停用」，路由用「传」写死 status）
  报错 400 状态只能是 active 或 disabled
  报错 400 subject_id 不对
  报错 404 没有这个科目
  报错 403 只有教师可以管理科目
  报错 403 只有科目负责人可以操作
  报错 409 日语科目不能停用
  伪代码 调用 设科目状态 learner=learner subject_id=subj_id status=status current_role=current_role auth_mode=auth_mode
  伪代码 返回 调用 科目管理页面 learner=learner current_role=current_role auth_mode=auth_mode 的结果

## 接口
GET /subject/mine -> 列我的科目
POST /subject/switch -> 切换科目 动作 subject_switch 模板 提交消息 消息=已切换科目
GET /subject/manageable -> 列可管理科目 角色 teacher
GET /subject/detail -> 科目详情 角色 teacher
POST /subject/manage/home -> 科目管理页面 动作 subject_manage_home 模板 页面状态 角色 teacher
POST /subject/manage/open -> 载入科目页面 动作 subject_open 模板 回填 角色 teacher
POST /subject/manage/save -> 保存科目页面 动作 subject_save 模板 页面状态消息 消息=科目已保存 角色 teacher
POST /subject/manage/publish -> 设科目可见性页面 动作 subject_publish 模板 页面状态消息 消息=已设为公共科目 传 visibility=public 角色 teacher
POST /subject/manage/private -> 设科目可见性页面 动作 subject_private 模板 页面状态消息 消息=已设为私有科目 传 visibility=private 角色 teacher
POST /subject/manage/enable -> 设科目状态页面 动作 subject_enable 模板 页面状态消息 消息=科目已启用 传 status=active 角色 teacher
POST /subject/manage/disable -> 设科目状态页面 动作 subject_disable 模板 页面状态消息 消息=科目已停用 传 status=disabled 角色 teacher

## 用例
用例 科目访问_单人模式
  调用 科目访问 learner=me current_role=空 subject_id=1 need=read
  得 ok=1 via=single

用例 科目访问_need不对
  调用 科目访问 learner=s1 current_role=student subject_id=1 need=abc
  报错 400

用例 科目访问_学生已分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 科目访问 learner=s1 current_role=student subject_id=1 need=read
  得 ok=1 via=assigned

用例 科目访问_学生未分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目访问 learner=s1 current_role=student subject_id=1 need=read
  得 ok=0

用例 科目访问_学生已撤销
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=revoked created_at=2026-01-01
  调用 科目访问 learner=s1 current_role=student subject_id=1 need=read
  得 ok=0

用例 科目访问_学生不能写
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 科目访问 learner=s1 current_role=student subject_id=1 need=write
  得 ok=0

用例 科目访问_科目不存在
  调用 科目访问 learner=t1 current_role=teacher subject_id=9 need=read
  得 ok=0

用例 科目访问_教师公共只读
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目访问 learner=t2 current_role=teacher subject_id=1 need=read
  得 ok=1 via=public

用例 科目访问_教师公共不能写
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目访问 learner=t2 current_role=teacher subject_id=1 need=write
  得 ok=0

用例 科目访问_教师公共可分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目访问 learner=t2 current_role=teacher subject_id=1 need=assign
  得 ok=1 via=public

用例 科目访问_他人私有
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目访问 learner=t2 current_role=teacher subject_id=1 need=read
  得 ok=0

用例 科目访问_协作可写不可改设置
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 科目访问 learner=t2 current_role=teacher subject_id=1 need=settings
  得 ok=0

用例 科目访问_协作可写内容
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 科目访问 learner=t2 current_role=teacher subject_id=1 need=write
  得 ok=1 via=editor

用例 科目访问_负责人可改设置
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目访问 learner=t1 current_role=teacher subject_id=1 need=settings
  得 ok=1 via=owner

用例 列我的科目_学生只列已分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 列我的科目 learner=s1 current_role=student
  得 total=1

用例 列我的科目_教师含公共和自己的私有
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t9 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=c name=丙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t9 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 列我的科目 learner=t1 current_role=teacher
  得 total=2

用例 列我的科目_单人模式只列公共启用的
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t9 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 列我的科目 learner=me current_role=空
  得 total=1

用例 当前科目_没有任何数据返回1
  调用 当前科目 learner=me
  得 subject_id=1

用例 当前科目_偏好有效
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_pref learner=s1 subject_id=2
  调用 当前科目 learner=s1
  得 subject_id=2

用例 当前科目_偏好失效回退第一个已分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=revoked created_at=2026-01-01
  先 数据 subject_pref learner=s1 subject_id=2
  调用 当前科目 learner=s1
  得 subject_id=1

用例 解析科目_不传用偏好
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_pref learner=s1 subject_id=2
  调用 解析科目 learner=s1 current_role=student auth_mode=on
  得 subject_id=2

用例 解析科目_请求科目已分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 解析科目 learner=s1 current_role=student auth_mode=on subject=1
  得 subject_id=1

用例 解析科目_请求科目未分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=s1 current_role=student auth_mode=on subject=1
  报错 403

用例 解析科目_请求科目不存在
  调用 解析科目 learner=t1 current_role=teacher auth_mode=on subject=9
  报错 404

用例 解析科目_请求科目不是数字
  调用 解析科目 learner=s1 current_role=student auth_mode=on subject=abc
  报错 400

用例 解析科目_单人模式不校验
  调用 解析科目 learner=me current_role=空 auth_mode=off subject=7
  得 subject_id=7

用例 解析科目_什么都没有默认1
  调用 解析科目 learner=me current_role=空 auth_mode=off
  得 subject_id=1

用例 切换科目_学生已分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 切换科目 learner=s1 current_role=student subject=2
  得 ok=1 subject=2
  库 subject_pref 含 learner=s1 subject_id=2

用例 切换科目_再切一次是更新
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_pref learner=s1 subject_id=5
  调用 切换科目 learner=s1 current_role=student subject=1
  得 ok=1 subject=1
  库 subject_pref 共 1 行
  库 subject_pref 含 learner=s1 subject_id=1

用例 切换科目_学生未分配被拒
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 切换科目 learner=s2 current_role=student subject=1
  报错 403
  库 subject_pref 共 0 行

用例 切换科目_科目不存在
  调用 切换科目 learner=t1 current_role=teacher subject=9
  报错 404

用例 切换科目_不是数字
  调用 切换科目 learner=s1 current_role=student subject=abc
  报错 400

用例 切换科目_教师切公共科目
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 切换科目 learner=t2 current_role=teacher subject=1
  得 ok=1 subject=1

用例 科目访问_空角色登录模式拒绝
  调用 科目访问 learner=me current_role=空 subject_id=1 need=read auth_mode=on
  得 ok=0

用例 科目访问_空角色非登录模式放行
  调用 科目访问 learner=me current_role=空 subject_id=1 need=read auth_mode=off
  得 ok=1 via=single

用例 科目访问_带auth_mode的学生照常
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 科目访问 learner=s1 current_role=student subject_id=1 need=read auth_mode=on
  得 ok=1 via=assigned

用例 当前科目_教师偏好无关系的公共科目不回退
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=t2 subject_id=2
  调用 当前科目 learner=t2 current_role=teacher
  得 subject_id=2

用例 当前科目_不传角色时教师偏好公共科目同旧回退1
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=t2 subject_id=2
  调用 当前科目 learner=t2
  得 subject_id=1

用例 当前科目_教师偏好他人私有科目回退1
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=t2 subject_id=2
  调用 当前科目 learner=t2 current_role=teacher
  得 subject_id=1

用例 当前科目_教师偏好停用的公共科目回退1
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=disabled created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=t2 subject_id=2
  调用 当前科目 learner=t2 current_role=teacher
  得 subject_id=1

用例 当前科目_学生传角色仍只认已分配
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=s1 subject_id=2
  调用 当前科目 learner=s1 current_role=student
  得 subject_id=1

用例 解析科目_教师不传subject用偏好的公共科目
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=t2 subject_id=2
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on
  得 subject_id=2

用例 解析科目_显式科目优先于偏好
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=t2 subject_id=2
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on subject=1
  得 subject_id=1

用例 解析科目_教师显式他人私有科目403
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on subject=1
  报错 403

用例 解析科目_登录模式空角色显式科目403
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=me current_role=空 auth_mode=on subject=1
  报错 403

用例 解析科目_need不对
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=t1 current_role=teacher auth_mode=on subject=1 need=abc
  报错 400

用例 解析科目_need不对单人模式也报
  调用 解析科目 learner=me current_role=空 auth_mode=off need=abc
  报错 400

用例 解析科目_need_write公共科目非负责教师403
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on subject=1 need=write
  报错 403

用例 解析科目_need_write协作教师通过
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on subject=1 need=write
  得 subject_id=1

用例 解析科目_need_write负责教师通过
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=t1 current_role=teacher auth_mode=on subject=1 need=write
  得 subject_id=1

用例 解析科目_need_write学生403
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 解析科目 learner=s1 current_role=student auth_mode=on subject=1 need=write
  报错 403

用例 解析科目_need_write科目不存在404
  调用 解析科目 learner=t1 current_role=teacher auth_mode=on subject=9 need=write
  报错 404

用例 解析科目_need_write不传subject按偏好解析再校验
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_pref learner=t2 subject_id=2
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on need=write
  报错 403

用例 解析科目_need_write单人模式不校验
  调用 解析科目 learner=me current_role=空 auth_mode=off subject=7 need=write
  得 subject_id=7

用例 解析科目_need_read公共科目教师照常
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on subject=1 need=read
  得 subject_id=1

用例 列科目学生_只列在册的并升序
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s3 assigned_by=t1 status=revoked created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s4 assigned_by=t1 status=active created_at=2026-01-01
  调用 列科目学生 subject_id=2
  得 total=2

用例 列科目学生_没人登记
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 列科目学生 subject_id=1
  得 total=0

用例 登记学生_默认登记进日语科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 登记学生 learner=s1
  得 registered=1 subject_id=1
  库 subject_student 含 subject_id=1 learner=s1 status=active

用例 登记学生_按code登记不按id
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 登记学生 learner=s1
  得 registered=1 subject_id=2
  库 subject_student 含 subject_id=2 learner=s1 status=active
  库 subject_student 无 subject_id=1 learner=s1

用例 登记学生_指定code
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 登记学生 learner=s1 code=math
  得 registered=1 subject_id=2

用例 登记学生_重复登记不新增
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 登记学生 learner=s1
  得 registered=0 subject_id=1
  库 subject_student 共 1 行

用例 登记学生_已撤销的不加回
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=revoked created_at=2026-01-01
  调用 登记学生 learner=s1
  得 registered=0
  库 subject_student 含 subject_id=1 learner=s1 status=revoked

用例 登记学生_科目不存在不报错
  调用 登记学生 learner=s1
  得 registered=0 subject_id=0
  库 subject_student 共 0 行

用例 登记学生_learner为空
  调用 登记学生 learner=空
  得 registered=0
  库 subject_student 共 0 行

用例 解析科目_need_own负责人通过
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=t1 current_role=teacher auth_mode=on subject=1 need=own
  得 subject_id=1

用例 解析科目_need_own协作教师被拒
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on subject=1 need=own
  报错 403

用例 解析科目_need_own协作教师仍可write
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 解析科目 learner=t2 current_role=teacher auth_mode=on subject=1 need=write
  得 subject_id=1

用例 解析科目_need_own公共科目其他教师被拒
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 解析科目 learner=t9 current_role=teacher auth_mode=on subject=1 need=own
  报错 403

用例 解析科目_need_own学生被拒
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 解析科目 learner=s1 current_role=student auth_mode=on subject=1 need=own
  报错 403

用例 解析科目_need_own科目不存在
  调用 解析科目 learner=t1 current_role=teacher auth_mode=on subject=9 need=own
  报错 404

用例 解析科目_need_own单人模式不校验
  调用 解析科目 learner=me current_role=空 auth_mode=off subject=7 need=own
  得 subject_id=7

用例 建科目_教师建私有草稿
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=math name=数学
  得 id=1 code=math
  库 subject_info 含 code=math name=数学 kind=general visibility=private status=draft owner=t1
  库 subject_teacher 含 subject_id=1 teacher=t1 role=owner

用例 建科目_带说明和类型
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=en_1 name=英语 intro=高一 kind=language
  得 code=en_1
  库 subject_info 含 code=en_1 intro=高一 kind=language

用例 建科目_学生403
  调用 建科目 learner=s1 current_role=student auth_mode=on code=math name=数学
  报错 403
  库 subject_info 共 0 行

用例 建科目_编码大写400
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=Math name=数学
  报错 400
  库 subject_info 共 0 行

用例 建科目_编码数字开头400
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=1math name=数学
  报错 400

用例 建科目_编码超长400
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=abcdefghijklmnopqrstu name=数学
  报错 400

用例 建科目_编码重名409
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 建科目 learner=t2 current_role=teacher auth_mode=on code=math name=数学二
  报错 409
  库 subject_info 共 1 行

用例 建科目_保留编码400
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=jp_grammar name=日语
  报错 400
  库 subject_info 共 0 行

用例 建科目_名称为空400
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=math name=空
  报错 400

用例 建科目_类型不对400
  调用 建科目 learner=t1 current_role=teacher auth_mode=on code=math name=数学 kind=abc
  报错 400

用例 建科目_单人模式
  调用 建科目 learner=me current_role=空 auth_mode=off code=math name=数学
  得 code=math
  库 subject_info 含 code=math owner=me status=draft

用例 改科目_负责人改名和说明
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 改科目 learner=t1 current_role=teacher auth_mode=on subject_id=1 name=乙 intro=说明
  得 ok=1
  库 subject_info 含 code=a name=乙 intro=说明

用例 改科目_名称为空不改名
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 改科目 learner=t1 current_role=teacher auth_mode=on subject_id=1 name=空 intro=说明
  得 ok=1
  库 subject_info 含 name=甲 intro=说明

用例 改科目_协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 改科目 learner=t2 current_role=teacher auth_mode=on subject_id=1 name=乙
  报错 403
  库 subject_info 含 name=甲

用例 改科目_公共科目其他教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 改科目 learner=t9 current_role=teacher auth_mode=on subject_id=1 name=乙
  报错 403

用例 改科目_学生403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 改科目 learner=s1 current_role=student auth_mode=on subject_id=1 name=乙
  报错 403

用例 改科目_科目不存在404
  调用 改科目 learner=t1 current_role=teacher auth_mode=on subject_id=9 name=乙
  报错 404

用例 改科目_编号不是数字400
  调用 改科目 learner=t1 current_role=teacher auth_mode=on subject_id=abc name=乙
  报错 400

用例 改科目_单人模式不校验权限
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 改科目 learner=me current_role=空 auth_mode=off subject_id=1 name=乙
  得 ok=1
  库 subject_info 含 name=乙

用例 设科目可见性_负责人设公共
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目可见性 learner=t1 current_role=teacher auth_mode=on subject_id=1 visibility=public
  得 ok=1 visibility=public
  库 subject_info 含 code=a visibility=public

用例 设科目可见性_值不对400
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目可见性 learner=t1 current_role=teacher auth_mode=on subject_id=1 visibility=abc
  报错 400

用例 设科目可见性_协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 设科目可见性 learner=t2 current_role=teacher auth_mode=on subject_id=1 visibility=public
  报错 403
  库 subject_info 含 visibility=private

用例 设科目可见性_日语科目不能私有409
  先 数据 subject_info code=jp_grammar name=日语语法 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目可见性 learner=t1 current_role=teacher auth_mode=on subject_id=1 visibility=private
  报错 409
  库 subject_info 含 visibility=public

用例 设科目可见性_有他人分配的学生不能私有409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t9 status=active created_at=2026-01-01
  调用 设科目可见性 learner=t1 current_role=teacher auth_mode=on subject_id=1 visibility=private
  报错 409
  库 subject_info 含 visibility=public

用例 设科目可见性_只有自己和协作分配的可以私有
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t2 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s3 assigned_by=t9 status=revoked created_at=2026-01-01
  调用 设科目可见性 learner=t1 current_role=teacher auth_mode=on subject_id=1 visibility=private
  得 ok=1 visibility=private
  库 subject_info 含 visibility=private

用例 设科目状态_负责人停用
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目状态 learner=t1 current_role=teacher auth_mode=on subject_id=1 status=disabled
  得 ok=1 status=disabled
  库 subject_info 含 status=disabled

用例 设科目状态_停用后再启用
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=disabled created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 设科目状态 learner=t1 current_role=teacher auth_mode=on subject_id=1 status=active
  得 ok=1 status=active
  库 subject_info 含 status=active
  库 subject_student 含 learner=s1 status=active

用例 设科目状态_草稿发布
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=draft created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目状态 learner=t1 current_role=teacher auth_mode=on subject_id=1 status=active
  得 status=active
  库 subject_info 含 status=active

用例 设科目状态_不能改回草稿400
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目状态 learner=t1 current_role=teacher auth_mode=on subject_id=1 status=draft
  报错 400
  库 subject_info 含 status=active

用例 设科目状态_日语科目不能停用409
  先 数据 subject_info code=jp_grammar name=日语语法 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目状态 learner=t1 current_role=teacher auth_mode=on subject_id=1 status=disabled
  报错 409
  库 subject_info 含 status=active

用例 设科目状态_日语科目单人模式也不能停用
  先 数据 subject_info code=jp_grammar name=日语语法 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目状态 learner=me current_role=空 auth_mode=off subject_id=1 status=disabled
  报错 409

用例 设科目状态_协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 设科目状态 learner=t2 current_role=teacher auth_mode=on subject_id=1 status=disabled
  报错 403
  库 subject_info 含 status=active

用例 设科目状态_停用不删分配
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 设科目状态 learner=t1 current_role=teacher auth_mode=on subject_id=1 status=disabled
  得 ok=1
  库 subject_student 含 subject_id=1 learner=s1 status=active

用例 列可管理科目_自己的含草稿停用加公共
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=draft created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t9 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=c name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t9 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=d name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t9 status=draft created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=e name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t9 status=disabled created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=5 teacher=t1 role=editor created_at=2026-01-01
  调用 列可管理科目 learner=t1 current_role=teacher auth_mode=on
  得 total=3

用例 列可管理科目_公共停用的也列
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t9 status=disabled created_at=2026-01-01 updated_at=2026-01-01
  调用 列可管理科目 learner=t1 current_role=teacher auth_mode=on
  得 total=1

用例 列可管理科目_学生403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 列可管理科目 learner=s1 current_role=student auth_mode=on
  报错 403

用例 列可管理科目_单人模式列全部
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t9 status=draft created_at=2026-01-01 updated_at=2026-01-01
  调用 列可管理科目 learner=me current_role=空 auth_mode=off
  得 total=2

用例 科目详情_负责人
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=revoked created_at=2026-01-01
  调用 科目详情 learner=t1 current_role=teacher auth_mode=on subject_id=1
  得 id=1 code=a my_role=owner status=active

用例 科目详情_协作教师
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 科目详情 learner=t2 current_role=teacher auth_mode=on subject_id=1
  得 my_role=editor

用例 科目详情_公共科目其他教师只读
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目详情 learner=t9 current_role=teacher auth_mode=on subject_id=1
  得 my_role=public

用例 科目详情_停用科目负责人照样能看
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=disabled created_at=2026-01-01 updated_at=2026-01-01
  调用 科目详情 learner=t1 current_role=teacher auth_mode=on subject_id=1
  得 status=disabled

用例 科目详情_他人私有403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目详情 learner=t9 current_role=teacher auth_mode=on subject_id=1
  报错 403

用例 科目详情_学生403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 科目详情 learner=s1 current_role=student auth_mode=on subject_id=1
  报错 403

用例 科目详情_不存在404
  调用 科目详情 learner=t1 current_role=teacher auth_mode=on subject_id=9
  报错 404

用例 列科目教师_含创建者和协作
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t3 role=owner created_at=2026-01-01
  调用 列科目教师 subject_id=1
  得 total=3

用例 列科目教师_创建者有行不重复
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t1 role=owner created_at=2026-01-01
  调用 列科目教师 subject_id=1
  得 total=1

用例 列科目教师_科目不存在
  调用 列科目教师 subject_id=9
  得 total=0

用例 加科目教师_负责人加协作
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 加科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2
  得 ok=1
  库 subject_teacher 含 subject_id=1 teacher=t2 role=editor

用例 加科目教师_加负责人
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 加科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2 role=owner
  得 ok=1
  库 subject_teacher 含 teacher=t2 role=owner

用例 加科目教师_协作教师不能加人403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 加科目教师 learner=t2 current_role=teacher auth_mode=on subject_id=1 teacher=t3
  报错 403
  库 subject_teacher 共 1 行

用例 加科目教师_已在本科目409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 加科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2 role=owner
  报错 409
  库 subject_teacher 含 teacher=t2 role=editor

用例 加科目教师_创建者409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 加科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t1
  报错 409
  库 subject_teacher 共 0 行

用例 加科目教师_角色不对400
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 加科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2 role=boss
  报错 400

用例 加科目教师_教师为空400
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 加科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=空
  报错 400

用例 加科目教师_公共科目其他教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 加科目教师 learner=t9 current_role=teacher auth_mode=on subject_id=1 teacher=t9
  报错 403

用例 改科目教师角色_协作升负责
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 改科目教师角色 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2 role=owner
  得 ok=1
  库 subject_teacher 含 teacher=t2 role=owner

用例 改科目教师角色_负责降协作
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=owner created_at=2026-01-01
  调用 改科目教师角色 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2 role=editor
  得 ok=1
  库 subject_teacher 含 teacher=t2 role=editor

用例 改科目教师角色_最后一个负责人409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=空 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t1 role=owner created_at=2026-01-01
  调用 改科目教师角色 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t1 role=editor
  报错 409
  库 subject_teacher 含 teacher=t1 role=owner

用例 改科目教师角色_还有别的负责人可降自己
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=空 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t1 role=owner created_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=owner created_at=2026-01-01
  调用 改科目教师角色 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t1 role=editor
  得 ok=1
  库 subject_teacher 含 teacher=t1 role=editor

用例 改科目教师角色_创建者409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t1 role=owner created_at=2026-01-01
  调用 改科目教师角色 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t1 role=editor
  报错 409

用例 改科目教师角色_不在本科目404
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 改科目教师角色 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2 role=owner
  报错 404

用例 改科目教师角色_协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t3 role=editor created_at=2026-01-01
  调用 改科目教师角色 learner=t2 current_role=teacher auth_mode=on subject_id=1 teacher=t3 role=owner
  报错 403
  库 subject_teacher 含 teacher=t3 role=editor

用例 改科目教师角色_角色不对400
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 改科目教师角色 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2 role=boss
  报错 400

用例 移除科目教师_负责人移除协作
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 移除科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2
  得 ok=1
  库 subject_teacher 无 teacher=t2

用例 移除科目教师_最后一个负责人409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=空 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t1 role=owner created_at=2026-01-01
  调用 移除科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t1
  报错 409
  库 subject_teacher 共 1 行

用例 移除科目教师_还有别的负责人可移除自己
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=空 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t1 role=owner created_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=owner created_at=2026-01-01
  调用 移除科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t1
  得 ok=1
  库 subject_teacher 无 teacher=t1
  库 subject_teacher 共 1 行

用例 移除科目教师_创建者409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t1 role=owner created_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=owner created_at=2026-01-01
  调用 移除科目教师 learner=t2 current_role=teacher auth_mode=on subject_id=1 teacher=t1
  报错 409
  库 subject_teacher 共 2 行

用例 移除科目教师_不在本科目404
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 移除科目教师 learner=t1 current_role=teacher auth_mode=on subject_id=1 teacher=t2
  报错 404

用例 移除科目教师_协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t3 role=editor created_at=2026-01-01
  调用 移除科目教师 learner=t2 current_role=teacher auth_mode=on subject_id=1 teacher=t3
  报错 403
  库 subject_teacher 共 2 行

用例 分配学生_负责人批量分配
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 learners=s1,s2
  得 assigned=2 reactivated=0 skipped=0
  库 subject_student 共 2 行
  库 subject_student 含 subject_id=1 learner=s1 status=active assigned_by=t1

用例 分配学生_已撤销的恢复
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t9 status=revoked created_at=2026-01-01
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 learners=s1
  得 assigned=0 reactivated=1
  库 subject_student 共 1 行
  库 subject_student 含 learner=s1 status=active assigned_by=t1

用例 分配学生_已在册跳过
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 learners=s1,s2
  得 assigned=1 skipped=1
  库 subject_student 共 2 行

用例 分配学生_去重和空项
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 learners=s1,,s1
  得 assigned=1
  库 subject_student 共 1 行

用例 分配学生_列表为空400
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 learners=空
  报错 400
  库 subject_student 共 0 行

用例 分配学生_协作教师可分配
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 分配学生 learner=t2 current_role=teacher auth_mode=on subject_id=1 learners=s1
  得 assigned=1
  库 subject_student 含 learner=s1 assigned_by=t2

用例 分配学生_公共科目其他教师可分配
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=t9 current_role=teacher auth_mode=on subject_id=1 learners=s1
  得 assigned=1
  库 subject_student 含 learner=s1 assigned_by=t9

用例 分配学生_他人私有403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=t9 current_role=teacher auth_mode=on subject_id=1 learners=s1
  报错 403
  库 subject_student 共 0 行

用例 分配学生_学生403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=s1 current_role=student auth_mode=on subject_id=1 learners=s2
  报错 403
  库 subject_student 共 0 行

用例 分配学生_停用科目409
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=disabled created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 learners=s1
  报错 409
  库 subject_student 共 0 行

用例 分配学生_草稿科目可分配
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=draft created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 learners=s1
  得 assigned=1

用例 分配学生_科目不存在404
  调用 分配学生 learner=t1 current_role=teacher auth_mode=on subject_id=9 learners=s1
  报错 404

用例 分配学生_单人模式
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 分配学生 learner=me current_role=空 auth_mode=off subject_id=1 learners=s1
  得 assigned=1
  库 subject_student 含 learner=s1 assigned_by=me

用例 撤销学生_负责人撤销
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t9 status=active created_at=2026-01-01
  调用 撤销学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 student=s1
  得 ok=1
  库 subject_student 共 1 行
  库 subject_student 含 learner=s1 status=revoked

用例 撤销学生_协作教师撤销别人分配的
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 撤销学生 learner=t2 current_role=teacher auth_mode=on subject_id=1 student=s1
  得 ok=1
  库 subject_student 含 learner=s1 status=revoked

用例 撤销学生_公共科目其他教师撤销别人分配的403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 撤销学生 learner=t9 current_role=teacher auth_mode=on subject_id=1 student=s1
  报错 403
  库 subject_student 含 learner=s1 status=active

用例 撤销学生_公共科目其他教师撤销自己分配的
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t9 status=active created_at=2026-01-01
  调用 撤销学生 learner=t9 current_role=teacher auth_mode=on subject_id=1 student=s1
  得 ok=1
  库 subject_student 含 learner=s1 status=revoked

用例 撤销学生_不在册404
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=revoked created_at=2026-01-01
  调用 撤销学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 student=s1
  报错 404

用例 撤销学生_停用科目也能撤销
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=disabled created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 撤销学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 student=s1
  得 ok=1

用例 撤销学生_学生403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 撤销学生 learner=s1 current_role=student auth_mode=on subject_id=1 student=s1
  报错 403
  库 subject_student 含 learner=s1 status=active

用例 撤销学生_学生为空400
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 撤销学生 learner=t1 current_role=teacher auth_mode=on subject_id=1 student=空
  报错 400

用例 科目管理页面_教师
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 科目管理页面 learner=t1 current_role=teacher auth_mode=on
  得 can_create=1

用例 科目管理页面_学生403
  调用 科目管理页面 learner=s1 current_role=student auth_mode=on
  报错 403

用例 载入科目页面_编辑回填
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 载入科目页面 learner=t1 current_role=teacher auth_mode=on subj_id=1
  得 subj_code=a subj_name=甲 subj_kind=通用

用例 载入科目页面_新建空表单
  调用 载入科目页面 learner=t1 current_role=teacher auth_mode=on
  得 subj_code=空 subj_kind=通用

用例 载入科目页面_协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 载入科目页面 learner=t2 current_role=teacher auth_mode=on subj_id=1
  报错 403

用例 保存科目页面_新建
  调用 保存科目页面 learner=t1 current_role=teacher auth_mode=on subj_code=math subj_name=数学 subj_kind=语言
  得 有返回
  库 subject_info 含 code=math kind=language status=draft owner=t1

用例 保存科目页面_编辑不改编码
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 保存科目页面 learner=t1 current_role=teacher auth_mode=on subj_id=1 subj_code=zz subj_name=乙
  得 有返回
  库 subject_info 含 code=a name=乙

用例 保存科目页面_新建编码重名409
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 保存科目页面 learner=t1 current_role=teacher auth_mode=on subj_code=math subj_name=数学
  报错 409
  库 subject_info 共 1 行

用例 保存科目页面_编辑协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 保存科目页面 learner=t2 current_role=teacher auth_mode=on subj_id=1 subj_name=乙
  报错 403

用例 设科目可见性页面_设公共
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目可见性页面 learner=t1 current_role=teacher auth_mode=on subj_id=1 visibility=public
  得 有返回
  库 subject_info 含 visibility=public

用例 设科目可见性页面_协作教师403
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=1 teacher=t2 role=editor created_at=2026-01-01
  调用 设科目可见性页面 learner=t2 current_role=teacher auth_mode=on subj_id=1 visibility=public
  报错 403

用例 设科目状态页面_停用
  先 数据 subject_info code=a name=甲 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目状态页面 learner=t1 current_role=teacher auth_mode=on subj_id=1 status=disabled
  得 有返回
  库 subject_info 含 status=disabled

用例 设科目状态页面_日语科目409
  先 数据 subject_info code=jp_grammar name=日语语法 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 设科目状态页面 learner=t1 current_role=teacher auth_mode=on subj_id=1 status=disabled
  报错 409
