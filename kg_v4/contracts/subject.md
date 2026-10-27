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
  返回 {total, students}；students 是 [{learner}]，subject_student 里该科目 status 等于 active 的学生，按 learner 升序（report、teacher_assist 用；学生范围的唯一规则，没有「1 号=全部学生」的特例）
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

## 接口
GET /subject/mine -> 列我的科目
POST /subject/switch -> 切换科目 动作 subject_switch 模板 提交消息 消息=已切换科目

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
