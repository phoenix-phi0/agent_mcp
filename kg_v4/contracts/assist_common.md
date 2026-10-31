模块 assist_common
依赖 account subject kg

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，need=write 且没有写权限报 403 没有权限修改该科目，原样抛出）。本模块只读，不传 need

公开 函数 学生范围 learner? current_role? auth_mode? subject?
  返回 {total, students}；students 是 [{username, display_name, status, last_at}]：本科目的学生范围，按 account.列学生 的顺序（与 report 的学生范围同一规则，report 的该函数是私有的，这里按同样规则做一份）；M4 拆模块后由 teacher_assist（取上轮聚焦、知识点上下文、取助手上下文）调用，原是 teacher_assist 的私有函数
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；别的模块调用时传 subject=已解析的科目编号
  伪代码 调用 account.列学生，得全部学生（含停用），带出 username、display_name、status、last_at
  伪代码 所有科目（含 1 号日语）统一：调用 subject.列科目学生 subject_id=subject_id，得 enrolled；只留 username 在 enrolled 各项 learner 里的学生（科目里登记且 active 的学生；没有登记或已撤销的不出现），顺序不变。不再有「1 号=全部学生」的特例，也不按 id=1 判断；学生范围的规则只在 subject.列科目学生 一处（本函数与 report 的同名私有函数都只是它加 account.列学生 的过滤）
  伪代码 返回 {"total": 人数, "students": 列表}

公开 函数 匹配学生 name learner? current_role? auth_mode? subject?
  返回 {status, username, display_name, candidates, roster}；status 为 one（唯一）/ many（多个）/ none（零个）；one 时 username、display_name 是那位学生；many 时 candidates 是最多 5 个 [{username, display_name, status}]；none 时 candidates 为空列表；roster 恒为本科目学生范围的前 10 个「显示名（用户名）」用「、」连接（给没找到时提示用）；只在本科目的学生范围里匹配（登记在别的科目的学生匹配不到）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（本函数没有 current_user，故补 learner；路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用本模块 学生范围 subject=subject_id，得 students：本科目全部学生（含停用），带出 username、display_name、status、last_at
  伪代码 name 去首尾空白，再去掉结尾的「同学」二字，再去一次首尾空白（「小明 同学」得「小明」）；去完为空，返回 {"status": "none", …}（不是报错）
  伪代码 传参（K166）：转小写、数长度用的 assist_common_lower、assist_common_len，参数（name、显示名）一律装进对象用 查一值表 传，不得按位置 s={…}、t={…} 传（显示名是库里的自由文本，可能首尾有空白，按位置传引擎报错）
  伪代码 按顺序匹配，前一档有结果就停：①username 与 name 相等（忽略大小写）；②display_name 与 name 相等；③模糊：display_name 包含 name，或 name 包含 display_name（display_name 至少 2 个字才用这个方向），或 username 包含 name（name 至少 2 个字）
  伪代码 命中 1 个返回 one；命中多个返回 many（按学生列表顺序取前 5 个为 candidates）；0 个返回 none
  伪代码 停用的学生也参与匹配（教师可能问已停用的学生），status 原样带出「启用」「停用」

公开 函数 匹配知识点 keyword learner? current_role? auth_mode? subject?
  返回 {status, code, title, candidates, total}；status 为 one / many / none；one 时 code、title 是那个知识点；many 时 candidates 是最多 5 个 [{code, title}]、total 是命中总数；none 时 candidates 为空列表、total 为 0；只在本科目的知识点和条目里匹配
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（本函数没有 current_user，故补 learner；路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用其它模块的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 keyword 去首尾空白，去掉开头的「～」「~」「〜」和结尾的「的用法」，再去一次首尾空白（「ばかり 的用法」得「ばかり」）；去完为空，返回 {"status": "none", …}（不是报错）
  伪代码 传参（K166）：转小写、数长度用的 assist_common_lower、assist_common_len，参数（keyword、知识点标题、条目名）一律装进对象用 查一值表 传，不得按位置传（标题、条目名是库里的自由文本）
  伪代码 调用 kg.列知识点 subject=subject_id，得全部知识点 [{code, title}]
  伪代码 按顺序匹配，前一档有结果就停：①code 与 keyword 相等（忽略大小写）；②title 与 keyword 相等；③title 包含 keyword，或 keyword 包含 title（title 至少 2 个字才用这个方向）
  伪代码 前三档都没有：调用 kg.列条目 subject=subject_id，取 name 包含 keyword（或 keyword 包含 name，name 至少 2 个字）的条目，把它们的 point_code 去重后当命中（条目名如「ばかり」，教师常用条目名问）；再调用 kg.取知识点 code=该编号 subject=subject_id 取 title
  伪代码 命中 1 个返回 one；多个返回 many（按知识点列表顺序取前 5 个）；0 个返回 none

## 用例
用例 匹配学生_显示名唯一
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明
  得 status=one username=s1 display_name=小明

用例 匹配学生_带同学二字
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明同学
  得 status=one username=s1

用例 匹配学生_用户名忽略大小写
  先 数据 account_user username=ab12 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=ab12 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=AB12
  得 status=one username=ab12

用例 匹配学生_模糊匹配到多个
  先 数据 account_user username=s1 password_hash=x display_name=王小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=李小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明
  得 status=many

用例 匹配学生_没有这个人
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=张三
  得 status=none

用例 匹配学生_教师账号不参与
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2025-12-01
  调用 匹配学生 name=王老师
  得 status=none

用例 匹配学生_名字为空
  调用 匹配学生 name=空
  得 status=none

用例 匹配知识点_标题唯一
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=P2 title=助词が
  调用 匹配知识点 keyword=助词は
  得 status=one code=P1 title=助词は

用例 匹配知识点_按条目名找到所属知识点
  先 数据 kg_point code=P1 title=时间表达
  先 数据 kg_item code=I1 name=ばかり point_code=P1
  调用 匹配知识点 keyword=～ばかり
  得 status=one code=P1

用例 匹配知识点_多个
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=P2 title=助词が
  调用 匹配知识点 keyword=助词
  得 status=many total=2

用例 匹配知识点_没有
  先 数据 kg_point code=P1 title=助词は
  调用 匹配知识点 keyword=被动态
  得 status=none total=0

用例 跨科目_匹配学生只在登记的学生里
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小红 subject=2
  得 status=none

用例 跨科目_匹配学生本科目登记的
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明 subject=2
  得 status=one username=s1 display_name=小明

用例 跨科目_匹配学生不传科目是日语登记的学生
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小红
  得 status=one username=s2

用例 跨科目_匹配学生日语没登记的匹配不到
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 匹配学生 name=小明
  得 status=none

用例 跨科目_匹配知识点只看本科目
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 匹配知识点 keyword=代数
  得 status=none total=0

用例 跨科目_匹配知识点本科目
  先 数据 kg_point code=P1 title=助词は
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 匹配知识点 keyword=代数 subject=2
  得 status=one code=math.a title=代数

用例 跨科目_匹配知识点按条目名只看本科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=因式分解 point_code=math.a subject_id=2
  调用 匹配知识点 keyword=因式分解
  得 status=none

用例 学生范围_只列本科目登记的学生
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  调用 学生范围
  得 total=1

用例 跨科目_学生范围只看本科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=2 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  调用 学生范围 subject=2
  得 total=1
