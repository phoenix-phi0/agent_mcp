模块 account
依赖 progress subject

## 表
表 account_user
  username 文本 用户名，唯一
  password_hash 文本 密码哈希（scrypt），明文不存
  display_name 文本 显示名
  role 文本 角色代号：student 或 teacher
  disabled 整数 是否停用（1/0）
  created_at 文本 建于时间，格式 YYYY-MM-DD HH:MM:SS
表 account_login_fail
  username 文本 登录时填的用户名（不论是否存在），唯一
  fail_count 整数 当前连续失败次数
  locked_until 文本 锁定到何时，格式 YYYY-MM-DD HH:MM:SS，可空

## 页面字段
页面 account_view 账号页面
  account_state 文本 状态
  attempt_n 整数 作答数
  last_active 文本 最近学习
  reset_user 文本 学生用户名
  old_password 文本 旧密码
  new_password 文本 新密码
  new_password2 文本 再输一次新密码

## 函数
公开 函数 核对身份 username
  返回 {username, role}；查不到或账号已停用时返回空
  伪代码 按 username 查 account_user，查不到则返回空
  伪代码 该行 disabled 等于 1，返回空（停用的账号下一个请求就算未登录）
  伪代码 返回 {"username": username, "role": 该行 role}

公开 函数 取账号 username
  返回 {username, display_name, role, disabled, created_at}；查不到返回空；不含密码哈希
  伪代码 按 username 查 account_user，查不到则返回空
  伪代码 返回 {"username": 该行 username, "display_name": 该行 display_name, "role": 该行 role, "disabled": 该行 disabled, "created_at": 该行 created_at}

公开 函数 列学生
  返回 {total, students}；students 是 [{username, display_name, status, answer_count, last_at}]，只含 role 为 student 的账号，按 id 升序；status 为「启用」或「停用」；answer_count 是作答数，没有作答为 0；last_at 是最近学习时间，没有作答为空串
  伪代码 查 account_user 中 role 等于 student 的全部行，按 id 升序
  伪代码 调用 progress.统计作答，得到 learners 列表
  伪代码 对每个学生，在 learners 里按 learner 等于 username 找到则取 answer_count 和 last_at，找不到则 answer_count 为 0、last_at 为空串
  伪代码 disabled 等于 1 则 status 为「停用」，否则为「启用」
  伪代码 返回 {"total": 学生数, "students": 列表}

公开 函数 列学生页面
  返回 [{username, display_name, account_state, attempt_n, last_active}]（数组，不是对象）；学生管理页一列一行，行键与页面列一字不差：account_state 为「正常」或「已停用」，attempt_n 是作答数（做题加默写），没有作答为 0；last_active 是最近学习时间，没有为空串；只含 role 为 student 的账号，按 id 升序
  伪代码 口径与 列学生 相同：查 account_user 中 role 等于 student 的全部行（按 id 升序），调用 progress.统计作答 取每人的 answer_count 和 last_at，找不到则 attempt_n 为 0、last_active 为空串
  伪代码 行键按页面口径输出：disabled 等于 1 则 account_state 为「已停用」，否则为「正常」；answer_count 写成 attempt_n；last_at 写成 last_active
  伪代码 返回数组本身（前端按 lists.students 直接喂列表，不带 total 包装）

公开 函数 登录 username password
  返回 {ok, username, display_name, role}
  报错 401 用户名或密码错误
  报错 429 登录失败次数过多，请稍后再试
  伪代码 username 或 password 为空，报错 401 用户名或密码错误
  伪代码 读 account_login_fail 中该 username 的行；有行且 locked_until 不为空且大于当前时间，报错 429 登录失败次数过多，请稍后再试
  伪代码 按 username 查 account_user；用 auth 包的核对密码 校验 password 与 password_hash
  伪代码 没有这个人、或密码不对、或 disabled 等于 1，一律视为失败（三种情况不区分，错误文字相同）：
  伪代码 失败时在一个事务里：account_login_fail 没有该 username 的行则插入 (username, fail_count=1)，有则 fail_count 加 1；若加完后 fail_count 不小于 5，则把 locked_until 设为当前时间加 5 分钟、fail_count 设为 0；然后报错 401 用户名或密码错误
  伪代码 成功时：把 account_login_fail 该 username 行（若有）的 fail_count 设为 0、locked_until 置空
  伪代码 用 auth 包的签发登录 让路由器发登录 cookie，username=username
  伪代码 返回 {"ok": 1, "username": username, "display_name": 该行 display_name, "role": 该行 role}

函数 取我是谁 learner
  返回 {username, display_name, role}
  报错 404 没有这个账号
  伪代码 按 learner 查 account_user，查不到报错 404 没有这个账号
  伪代码 返回 {"username": learner, "display_name": 该行 display_name, "role": 该行 role}

公开 函数 我是谁 learner auth_mode
  返回 {auth_mode, username, display_name, role}；auth_mode 为 off（单人模式）时固定返回 {"auth_mode": "off", "username": learner, "display_name": learner, "role": "student"}
  报错 404 没有这个账号
  伪代码 auth_mode 等于 off，返回 {"auth_mode": "off", "username": learner, "display_name": learner, "role": "student"}
  伪代码 否则调用 取我是谁 learner=learner（查不到报 404 没有这个账号）
  伪代码 返回 {"auth_mode": auth_mode, "username": 其 username, "display_name": 其 display_name, "role": 其 role}

公开 函数 认证信息 current_user current_role auth_mode
  返回 {user, label, role, role_label, badge, hide, mode, subjects, subject}；给前端顶栏用（auth_me）：user 是登录的用户名（单人模式或没登录是空串），label 是显示名，role 是角色代号，role_label 是「学生」或「教师」，badge 与 hide 恒为空串与空数组，mode 是 auth_mode 原值，subjects 是当前用户可见的科目 [{id, name}]，subject 是当前科目编号（没登录是 1，subjects 为空数组）
  伪代码 auth_mode 不等于 on 或 current_user 为空，返回 {"user": "", "label": "", "role": "", "role_label": "", "badge": "", "hide": [], "mode": auth_mode, "subjects": [], "subject": 1}
  伪代码 按 current_user 查 account_user；查不到或 disabled 等于 1，同样返回上面那个没登录的空对象
  伪代码 调用 subject.列我的科目 learner=current_user current_role=该行 role，取返回的 subjects，只保留 id 和 name 两个键，得到 subjects 数组
  伪代码 调用 subject.当前科目 learner=current_user，取 subject_id 作为 subject
  伪代码 role_label：role 等于 teacher 取「教师」，等于 student 取「学生」，其他取空串
  伪代码 返回 {"user": current_user, "label": 该行 display_name, "role": 该行 role, "role_label": role_label, "badge": "", "hide": [], "mode": "on", "subjects": subjects, "subject": subject}
  伪代码 依赖方向：account 依赖 subject（subject 是叶子，不依赖 account；角色由 account 查出后以 current_role 传给 subject）

公开 函数 退出 learner
  返回 {ok}
  报错 400 learner 不能为空
  伪代码 learner 为空，报错 400 learner 不能为空
  伪代码 用 auth 包的退出登录 让路由器清掉登录 cookie
  伪代码 返回 {"ok": 1}

公开 函数 改密码 learner auth_mode old_password new_password new_password2
  返回 {ok}
  报错 404 单人模式没有账号
  报错 400 新密码不能为空
  报错 400 两次新密码不一致
  报错 400 旧密码不对
  报错 404 没有这个账号
  伪代码 auth_mode 等于 off，报错 404 单人模式没有账号
  伪代码 new_password 为空，报错 400 新密码不能为空
  伪代码 new_password 不等于 new_password2，报错 400 两次新密码不一致
  伪代码 按 learner 查 account_user，查不到报错 404 没有这个账号
  伪代码 用 auth 包的核对密码 校验 old_password 与 password_hash，不对报错 400 旧密码不对
  伪代码 用 auth 包的哈希密码 算 new_password 的哈希，更新该行 password_hash
  伪代码 返回 {"ok": 1}

公开 函数 建学生 username password display_name
  返回 刷新后的学生列表（「列学生页面」的口径，数组），建完号页面直接用它刷新表格
  报错 400 用户名和密码不能为空
  报错 400 用户名只能用字母、数字、汉字和 _ . @ -，不能有空格，最长 40
  报错 400 密码至少 6 位
  报错 409 用户名已存在
  伪代码 username 或 password 为空，报错 400 用户名和密码不能为空
  伪代码 username 不符合用户名字符集（字母、数字、汉字和 _ . @ -，不能有空格，最长 40；口径同原 kg tools/auth.py 的 USERNAME_RE），报错 400 用户名只能用字母、数字、汉字和 _ . @ -，不能有空格，最长 40
  伪代码 password 不足 6 位，报错 400 密码至少 6 位（口径同原 kg tools/auth.py 的 MIN_PASSWORD）
  伪代码 display_name 为空则取 username
  伪代码 account_user 已有该 username，报错 409 用户名已存在
  伪代码 用 auth 包的哈希密码 算 password 的哈希
  伪代码 往 account_user 插入 (username, password_hash, display_name, role=student, disabled=0, created_at=当前时间)
  伪代码 调用 列学生页面，返回刷新后的学生列表（数组）

公开 函数 重置学生密码 username new_password
  返回 {ok}
  报错 400 新密码不能为空
  报错 404 没有这个账号
  报错 403 只能操作学生账号
  伪代码 new_password 为空，报错 400 新密码不能为空
  伪代码 按 username 查 account_user，查不到报错 404 没有这个账号
  伪代码 该行 role 不等于 student，报错 403 只能操作学生账号
  伪代码 用 auth 包的哈希密码 算 new_password 的哈希，更新该行 password_hash
  伪代码 把 account_login_fail 该 username 行（若有）的 fail_count 设为 0、locked_until 置空
  伪代码 返回 {"ok": 1}

公开 函数 设置学生停用 username disabled
  返回 刷新后的学生列表（「列学生页面」的口径，数组），停用/启用后页面直接用它刷新表格
  报错 400 disabled 只能是 0 或 1
  报错 404 没有这个账号
  报错 403 只能操作学生账号
  伪代码 disabled 不是 0 也不是 1，报错 400 disabled 只能是 0 或 1
  伪代码 按 username 查 account_user，查不到报错 404 没有这个账号
  伪代码 该行 role 不等于 student，报错 403 只能操作学生账号
  伪代码 更新该行 disabled=disabled
  伪代码 调用 列学生页面，返回刷新后的学生列表（数组）

## 接口
POST /account/login -> 登录 动作 auth_login 模板 提交跳转 消息=已登录 跳转=@来处 公开
POST /account/logout -> 退出
GET /account/me -> 我是谁
POST /account/password -> 改密码 动作 auth_password 模板 提交消息 消息=密码改好了，下次用新密码登录
GET /account/students -> 列学生 角色 teacher
POST /account/students -> 列学生页面 动作 student_home 模板 列表 键=students 行=username,display_name,account_state,attempt_n,last_active 角色 teacher
POST /account/students/create -> 建学生 动作 student_create 模板 提交消息 消息=建好了学生账号：{username} 键=students 角色 teacher
POST /account/students/reset -> 重置学生密码 动作 student_reset 模板 提交消息 消息=已重置{reset_user}的密码 参数 reset_user=username 角色 teacher
POST /account/students/disable -> 设置学生停用 动作 student_disable 模板 提交消息 消息=已停用 键=students 传 disabled=1 角色 teacher
POST /account/students/enable -> 设置学生停用 动作 student_enable 模板 提交消息 消息=已启用 键=students 传 disabled=0 角色 teacher

## 用例
用例 核对身份_存在
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2026-01-01
  调用 核对身份 username=s1
  得 username=s1 role=student

用例 核对身份_不存在
  调用 核对身份 username=nobody
  得 为空

用例 核对身份_已停用
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=1 created_at=2026-01-01
  调用 核对身份 username=s1
  得 为空

用例 取账号_存在
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2026-01-01
  调用 取账号 username=t1
  得 username=t1 display_name=王老师 role=teacher disabled=0

用例 取账号_不存在
  调用 取账号 username=nobody
  得 为空

用例 列学生_含作答统计
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=1 created_at=2026-01-01
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01_08:00:00
  调用 列学生
  得 total=2

用例 列学生_没有学生
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2026-01-01
  调用 列学生
  得 total=0

用例 登录_成功
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 登录 username=s1 password=pw123456
  得 ok=1 username=s1 display_name=小明 role=student

用例 登录_密码错记失败
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 登录 username=s1 password=wrong
  报错 401
  库 account_login_fail 含 username=s1 fail_count=1

用例 登录_没这个人
  调用 登录 username=nobody password=pw123456
  报错 401

用例 登录_已停用
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  先 调用 设置学生停用 username=s1 disabled=1
  调用 登录 username=s1 password=pw123456
  报错 401

用例 登录_第5次失败触发锁定
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  先 数据 account_login_fail username=s1 fail_count=4 locked_until=2026-01-01_08:00:00
  调用 登录 username=s1 password=wrong
  报错 401
  库 account_login_fail 含 username=s1 fail_count=0

用例 登录_锁定期内被拒
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  先 数据 account_login_fail username=s1 fail_count=0 locked_until=2026-01-01_09:03:00
  调用 登录 username=s1 password=pw123456
  报错 429

用例 我是谁_单人模式
  调用 我是谁 learner=me auth_mode=off
  得 auth_mode=off username=me display_name=me role=student

用例 我是谁_多人模式
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 我是谁 learner=s1 auth_mode=on
  得 auth_mode=on username=s1 display_name=小明 role=student

用例 我是谁_账号不存在
  调用 我是谁 learner=ghost auth_mode=on
  报错 404

用例 认证信息_单人模式
  调用 认证信息 current_user=空 current_role=空 auth_mode=off
  得 user=空 subject=1

用例 认证信息_学生一个科目
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2026-01-01
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 认证信息 current_user=s1 current_role=student auth_mode=on
  得 user=s1 label=小明 role=student role_label=学生 subject=1

用例 认证信息_学生两个科目偏好2
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2026-01-01
  先 数据 subject_info code=a name=甲 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=b name=乙 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 subject_pref learner=s1 subject_id=2
  调用 认证信息 current_user=s1 current_role=student auth_mode=on
  得 user=s1 subject=2

用例 认证信息_教师
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2026-01-01
  调用 认证信息 current_user=t1 current_role=teacher auth_mode=on
  得 user=t1 label=王老师 role=teacher role_label=教师 subject=1

用例 退出_正常
  调用 退出 learner=s1
  得 ok=1

用例 退出_learner为空
  调用 退出 learner=空
  报错 400

用例 改密码_成功
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 改密码 learner=s1 auth_mode=on old_password=pw123456 new_password=newpw789 new_password2=newpw789
  得 ok=1

用例 改密码_旧密码不对
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 改密码 learner=s1 auth_mode=on old_password=wrong new_password=newpw789 new_password2=newpw789
  报错 400

用例 改密码_两次不一致
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 改密码 learner=s1 auth_mode=on old_password=pw123456 new_password=newpw789 new_password2=other
  报错 400

用例 改密码_单人模式
  调用 改密码 learner=me auth_mode=off old_password=a new_password=b new_password2=b
  报错 404

用例 建学生_成功
  调用 建学生 username=s1 password=pw123456 display_name=小明
  得 有返回
  库 account_user 共 1 行
  库 account_user 含 username=s1 role=student disabled=0 created_at=2026-01-01_09:00:00

用例 建学生_用户名带非法字符
  调用 建学生 username=s1! password=pw123456 display_name=小明
  报错 400
  库 account_user 共 0 行

用例 建学生_密码过短
  调用 建学生 username=s1 password=abc12 display_name=小明
  报错 400
  库 account_user 共 0 行

用例 建学生_用户名重复
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 建学生 username=s1 password=other display_name=小红
  报错 409
  库 account_user 共 1 行

用例 建学生_密码为空
  调用 建学生 username=s1 password=空 display_name=小明
  报错 400
  库 account_user 共 0 行

用例 列学生页面_含停用学生
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小红 role=student disabled=1 created_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=Q1 correct=1 answer=A at=2026-01-01_08:00:00
  调用 列学生页面
  得 有返回

用例 重置学生密码_成功
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 重置学生密码 username=s1 new_password=newpw789
  得 ok=1

用例 重置学生密码_教师账号被拒
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2026-01-01
  调用 重置学生密码 username=t1 new_password=newpw789
  报错 403

用例 重置学生密码_没有这个账号
  调用 重置学生密码 username=nobody new_password=newpw789
  报错 404

用例 设置学生停用_停用
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 设置学生停用 username=s1 disabled=1
  得 有返回
  库 account_user 含 username=s1 disabled=1

用例 设置学生停用_教师账号被拒
  先 数据 account_user username=t1 password_hash=x display_name=王老师 role=teacher disabled=0 created_at=2026-01-01
  调用 设置学生停用 username=t1 disabled=1
  报错 403
  库 account_user 含 username=t1 disabled=0

用例 设置学生停用_值非法
  先 调用 建学生 username=s1 password=pw123456 display_name=小明
  调用 设置学生停用 username=s1 disabled=2
  报错 400
