业务 account
  依赖 progress subject
  用包 common db text auth

  公开 函数 核对身份 username
    # 返回 {username, role}；查不到或账号已停用时返回空
    # 按 username 查 account_user，查不到则返回空
    # 该行 disabled 等于 1，返回空（停用的账号下一个请求就算未登录）
    设 u = 查一行 app.db account_user_by_name username={username}
    如果 {u.username 或} 为空
      返回 {nothing 或}
    结束
    如果 {u.disabled} 等于 1
      返回 {nothing 或}
    结束
    返回 {"username": "{u.username}", "role": "{u.role}"}
  结束

  公开 函数 取账号 username
    # 返回 {username, display_name, role, disabled, created_at}；查不到返回空；不含密码哈希
    # 按 username 查 account_user，查不到则返回空
    设 u = 查一行 app.db account_user_by_name username={username}
    如果 {u.username 或} 为空
      返回 {nothing 或}
    结束
    返回 {"username": "{u.username}", "display_name": "{u.display_name}", "role": "{u.role}", "disabled": {u.disabled}, "created_at": "{u.created_at}"}
  结束

  公开 函数 列学生 learner? current_role? auth_mode? subject?
    设 sj = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    # 返回 {total, students}；students 是 [{username, display_name, status, answer_count, last_at}]，只含 role 为 student 的账号，按 id 升序；status 为「启用」或「停用」；answer_count 是作答数，没有作答为 0；last_at 是最近学习时间，没有作答为空串
    # 查 account_user 中 role 等于 student 的全部行，按 id 升序
    # 调用 progress.统计作答，得到 learners 列表
    # 对每个学生，在 learners 里按 learner 等于 username 找到则取 answer_count 和 last_at，找不到则 answer_count 为 0、last_at 为空串
    # disabled 等于 1 则 status 为「停用」，否则为「启用」
    设 rows = 查询 app.db account_students
    设 pr = 调用 progress.统计作答 subject={sj.subject_id}
    设 list = 解析JSON []
    遍历 s 于 {rows}
      设 cnt = 0
      设 last = 
      遍历 l 于 {pr.learners}
        如果 {l.learner} 等于 {s.username}
          设 cnt = {l.answer_count}
          设 last = {l.last_at}
        结束
      结束
      设 st = 启用
      如果 {s.disabled} 等于 1
        设 st = 停用
      结束
      设 it.username = {s.username}
      设 it.display_name = {s.display_name}
      设 it.status = {st}
      设 it.answer_count = {cnt}
      设 it.last_at = {last}
      设 list = 列表加项 {list} {it}
    结束
    设 total = 列表长度 {rows}
    返回 {"total": {total}, "students": {list}}
  结束

  公开 函数 列学生页面 learner? current_role? auth_mode? subject?
    设 sj = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    # 返回 [{username, display_name, account_state, attempt_n, last_active}]（数组）
    # 口径与 列学生 相同，行键按页面口径输出
    设 rows = 查询 app.db account_students
    设 pr = 调用 progress.统计作答 subject={sj.subject_id}
    设 list = 解析JSON []
    遍历 s 于 {rows}
      设 cnt = 0
      设 last = 
      遍历 l 于 {pr.learners}
        如果 {l.learner} 等于 {s.username}
          设 cnt = {l.answer_count}
          设 last = {l.last_at}
        结束
      结束
      设 st = 正常
      如果 {s.disabled} 等于 1
        设 st = 已停用
      结束
      设 it.username = {s.username}
      设 it.display_name = {s.display_name}
      设 it.account_state = {st}
      设 it.attempt_n = {cnt}
      设 it.last_active = {last}
      设 list = 列表加项 {list} {it}
    结束
    返回 {list}
  结束

  公开 函数 登录 username password
    # 返回 {ok, username, display_name, role}
    # 报错 401 用户名或密码错误
    # 报错 429 登录失败次数过多，请稍后再试
    # username 或 password 为空，报错 401 用户名或密码错误
    # 读 account_login_fail 中该 username 的行；有行且 locked_until 不为空且大于当前时间 2026-01-01 09:00:00，报错 429 登录失败次数过多，请稍后再试
    # 按 username 查 account_user；用 auth 包的核对密码 校验 password 与 password_hash
    # 没有这个人、或密码不对、或 disabled 等于 1，一律视为失败（三种情况不区分，错误文字相同）：
    # 失败时在一个事务里：account_login_fail 没有该 username 的行则插入 (username, fail_count=1)，有则 fail_count 加 1；若加完后 fail_count 不小于 5，则把 locked_until 设为当前时间加 5 分钟、fail_count 设为 0；然后报错 401 用户名或密码错误
    # 成功时：把 account_login_fail 该 username 行（若有）的 fail_count 设为 0、locked_until 置空
    # 用 auth 包的签发登录 让路由器发登录 cookie，username=username
    如果 {username} 为空 或 {password} 为空
      报错 401 用户名或密码错误
    结束
    设 f = 查一行 app.db account_fail_get username={username}
    设 now = 当前时间
    设 lu0 = {f.locked_until 或}
    设 lu = 替换 {lu0} \s _
    设 nw = 替换 {now} \s _
    如果 {lu} 不为空 且 {lu} 大于 {nw}
      报错 429 登录失败次数过多，请稍后再试
    结束
    设 u = 查一行 app.db account_user_by_name username={username}
    设 good = 否
    如果 {u.username 或} 不为空
      如果 {u.disabled} 不等于 1
        设 good = 核对密码 {password} {u.password_hash}
      结束
    结束
    如果 {good} 不等于 是
      事务 app.db
        如果 {f.username 或} 为空
          设 n1 = 写库 app.db account_fail_insert username={username}
        否则
          设 n2 = 写库 app.db account_fail_bump username={username}
        结束
        设 g = 查一行 app.db account_fail_get username={username}
        如果 {g.fail_count} 不小于 5
          设 n3 = 写库 app.db account_fail_lock username={username} now={nw}
        结束
      结束
      报错 401 用户名或密码错误
    结束
    设 n4 = 写库 app.db account_fail_clear username={username}
    设 sg = 签发登录 {username}
    返回 {"ok": 1, "username": "{username}", "display_name": "{u.display_name}", "role": "{u.role}"}
  结束

  函数 取我是谁 learner
    # 返回 {username, display_name, role}
    # 报错 404 没有这个账号
    # 按 learner 查 account_user，查不到报错 404 没有这个账号
    设 u = 查一行 app.db account_user_by_name username={learner}
    如果 {u.username 或} 为空
      报错 404 没有这个账号
    结束
    返回 {"username": "{learner}", "display_name": "{u.display_name}", "role": "{u.role}"}
  结束

  公开 函数 我是谁 learner auth_mode
    # 返回 {auth_mode, username, display_name, role}；auth_mode 为 off（单人模式）时固定返回 {"auth_mode": "off", "username": learner, "display_name": learner, "role": "student"}
    # 报错 404 没有这个账号
    # auth_mode 等于 off，返回 {"auth_mode": "off", "username": learner, "display_name": learner, "role": "student"}
    # 否则调用 取我是谁 learner=learner（查不到报 404 没有这个账号）
    如果 {auth_mode} 等于 off
      返回 {"auth_mode": "off", "username": "{learner}", "display_name": "{learner}", "role": "student"}
    结束
    设 w = 调用 取我是谁 learner={learner}
    返回 {"auth_mode": "{auth_mode}", "username": "{w.username}", "display_name": "{w.display_name}", "role": "{w.role}"}
  结束

  公开 函数 认证信息 current_user current_role auth_mode
    # 返回 {user, label, role, role_label, badge, hide, mode, subjects, subject}
    # auth_mode 不等于 on 或 current_user 为空，返回空用户对象
    # 按 current_user 查 account_user；查不到或 disabled 等于 1，同样返回空用户对象
    # 调用 subject.列我的科目 取 subjects 只保留 id name；调用 subject.当前科目 取 subject_id
    设 okf = 0
    设 u = 解析JSON {}
    如果 {auth_mode} 等于 on 且 {current_user} 不为空
      设 u = 查一行 app.db account_user_by_name username={current_user}
      如果 {u.username 或} 不为空
        如果 {u.disabled} 不等于 1
          设 okf = 1
        结束
      结束
    结束
    如果 {okf} 不等于 1
      返回 {"user": "", "label": "", "role": "", "role_label": "", "badge": "", "hide": [], "mode": "{auth_mode}", "subjects": [], "subject": 1}
    结束
    设 sl = 调用 subject.列我的科目 learner={current_user} current_role={u.role}
    设 list = 解析JSON []
    遍历 s 于 {sl.subjects}
      设 it.id = {s.id}
      设 it.name = {s.name}
      设 list = 列表加项 {list} {it}
    结束
    设 sc = 调用 subject.当前科目 learner={current_user} current_role={u.role}
    设 rl = 
    如果 {u.role} 等于 teacher
      设 rl = 教师
    结束
    如果 {u.role} 等于 student
      设 rl = 学生
    结束
    返回 {"user": "{current_user}", "label": "{u.display_name}", "role": "{u.role}", "role_label": "{rl}", "badge": "", "hide": [], "mode": "on", "subjects": {list}, "subject": {sc.subject_id}}
  结束

  公开 函数 退出 learner
    # 返回 {ok}
    # 报错 400 learner 不能为空
    # learner 为空，报错 400 learner 不能为空
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    设 lo = 退出登录
    返回 {"ok": 1}
  结束

  公开 函数 改密码 learner auth_mode old_password new_password new_password2
    # 返回 {ok}
    # 报错 404 单人模式没有账号
    # 报错 400 新密码不能为空
    # 报错 400 两次新密码不一致
    # 报错 400 旧密码不对
    # 报错 404 没有这个账号
    # auth_mode 等于 off，报错 404 单人模式没有账号
    # new_password 为空，报错 400 新密码不能为空
    # new_password 不等于 new_password2，报错 400 两次新密码不一致
    # 按 learner 查 account_user，查不到报错 404 没有这个账号
    # 用 auth 包的核对密码 校验 old_password 与 password_hash，不对报错 400 旧密码不对
    如果 {auth_mode} 等于 off
      报错 404 单人模式没有账号
    结束
    如果 {new_password} 为空
      报错 400 新密码不能为空
    结束
    如果 {new_password} 不等于 {new_password2}
      报错 400 两次新密码不一致
    结束
    设 u = 查一行 app.db account_user_by_name username={learner}
    如果 {u.username 或} 为空
      报错 404 没有这个账号
    结束
    设 ok = 核对密码 {old_password} {u.password_hash}
    如果 {ok} 不等于 是
      报错 400 旧密码不对
    结束
    设 h = 哈希密码 {new_password}
    设 n = 写库 app.db account_user_set_hash username={learner} password_hash={h}
    返回 {"ok": 1}
  结束

  公开 函数 建学生 username password display_name learner? current_role? auth_mode? subject?
    设 sj = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    # 返回 {ok, username, display_name, role}；role 固定为 student
    # 报错 400 用户名和密码不能为空
    # 报错 409 用户名已存在
    # username 或 password 为空，报错 400 用户名和密码不能为空
    # display_name 为空则取 username
    # account_user 已有该 username，报错 409 用户名已存在
    # 用 auth 包的哈希密码 算 password 的哈希
    # 往 account_user 插入 (username, password_hash, display_name, role=student, disabled=0, created_at=当前时间)
    如果 {username} 为空 或 {password} 为空
      报错 400 用户名和密码不能为空
    结束
    设 um = 匹配 {username} ^[A-Za-z0-9_.@\-\u4e00-\u9fff]+$
    设 ul = 截取 {username} 41
    如果 {um.matched} 不等于 是 或 {ul} 不为空
      报错 400 用户名只能用字母、数字、汉字和 _ . @ -，不能有空格，最长 40
    结束
    设 ex = 查一行 app.db account_user_by_name username={username}
    如果 {ex.username 或} 不为空
      报错 409 用户名已存在
    结束
    设 pl = 截取 {password} 6
    如果 {pl} 为空
      报错 400 密码至少 6 位
    结束
    设 dn = {display_name}
    如果 {dn} 为空
      设 dn = {username}
    结束
    设 h = 哈希密码 {password}
    设 now = 当前时间
    设 ca = 替换 {now} \s _
    设 f.username = {username}
    设 f.password_hash = {h}
    设 f.display_name = {dn}
    设 f.created_at = {ca}
    设 n = 写库表 app.db account_user_insert {f}
    设 rg = 调用 subject.登记学生 learner={username} code=jp_grammar
    设 out = 调用 列学生页面 subject={sj.subject_id}
    返回 {out}
  结束

  公开 函数 重置学生密码 username new_password
    # 返回 {ok}
    # 报错 400 新密码不能为空
    # 报错 404 没有这个账号
    # 报错 403 只能操作学生账号
    # new_password 为空，报错 400 新密码不能为空
    # 按 username 查 account_user，查不到报错 404 没有这个账号
    # 该行 role 不等于 student，报错 403 只能操作学生账号
    # 用 auth 包的哈希密码 算 new_password 的哈希，更新该行 password_hash
    如果 {new_password} 为空
      报错 400 新密码不能为空
    结束
    设 u = 查一行 app.db account_user_by_name username={username}
    如果 {u.username 或} 为空
      报错 404 没有这个账号
    结束
    如果 {u.role} 不等于 student
      报错 403 只能操作学生账号
    结束
    设 h = 哈希密码 {new_password}
    设 n = 写库 app.db account_user_set_hash username={username} password_hash={h}
    设 n2 = 写库 app.db account_fail_clear username={username}
    返回 {"ok": 1}
  结束

  公开 函数 设置学生停用 username disabled learner? current_role? auth_mode? subject?
    设 sj = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    # 返回 {ok, username, disabled}
    # 报错 400 disabled 只能是 0 或 1
    # 报错 404 没有这个账号
    # 报错 403 只能操作学生账号
    # disabled 不是 0 也不是 1，报错 400 disabled 只能是 0 或 1
    # 按 username 查 account_user，查不到报错 404 没有这个账号
    # 该行 role 不等于 student，报错 403 只能操作学生账号
    # 更新该行 disabled=disabled
    如果 {disabled} 不等于 0 且 {disabled} 不等于 1
      报错 400 disabled 只能是 0 或 1
    结束
    设 u = 查一行 app.db account_user_by_name username={username}
    如果 {u.username 或} 为空
      报错 404 没有这个账号
    结束
    如果 {u.role} 不等于 student
      报错 403 只能操作学生账号
    结束
    设 n = 写库 app.db account_user_set_disabled username={username} disabled={disabled}
    设 out = 调用 列学生页面 subject={sj.subject_id}
    返回 {out}
  结束

  公开 函数 列可分配学生 subject_id
    设 sl = 调用 subject.列科目学生 subject_id={subject_id}
    设 rows = 查询 app.db account_students_enabled
    设 list = 解析JSON []
    遍历 s 于 {rows}
      设 found = 0
      遍历 l 于 {sl.students}
        如果 {l.learner} 等于 {s.username}
          设 found = 1
        结束
      结束
      如果 {found} 等于 0
        设 it.username = {s.username}
        设 it.display_name = {s.display_name}
        设 list = 列表加项 {list} {it}
      结束
    结束
    设 total = 列表长度 {list}
    返回 {"total": {total}, "students": {list}}
  结束

  公开 函数 科目成员页面 learner subj_id current_role? auth_mode?
    设 d = 调用 subject.科目详情 learner={learner} subject_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    设 cm = 0
    如果 {d.my_role} 等于 owner 或 {d.my_role} 等于 single
      设 cm = 1
    结束
    设 ca = 0
    如果 {d.status} 不等于 disabled
      设 ca = 1
    结束
    设 rl = 单人
    如果 {d.my_role} 等于 owner
      设 rl = 负责
    结束
    如果 {d.my_role} 等于 editor
      设 rl = 协作
    结束
    如果 {d.my_role} 等于 public
      设 rl = 公共只读
    结束
    设 stz = 草稿
    如果 {d.status} 等于 active
      设 stz = 启用
    结束
    如果 {d.status} 等于 disabled
      设 stz = 停用
    结束
    设 head = {d.name}（{d.code}）·{stz}·我是{rl}
    设 tl = 解析JSON []
    遍历 t 于 {d.teachers}
      设 tu = 查一行 app.db account_user_by_name username={t.teacher}
      设 tn = {tu.display_name 或}
      如果 {tu.username 或} 为空
        设 tn = {t.teacher}（无账号）
      结束
      设 mr = 协作
      如果 {t.role} 等于 owner
        设 mr = 负责
      结束
      设 mc = 
      如果 {t.creator} 等于 1
        设 mc = 是
      结束
      设 ce = 0
      如果 {cm} 等于 1 且 {t.creator} 等于 0
        设 ce = 1
      结束
      设 tr.member_teacher = {t.teacher}
      设 tr.member_teacher_label = {tn}
      设 tr.member_role = {mr}
      设 tr.member_creator = {mc}
      设 tr.can_edit = {ce}
      设 tl = 列表加项 {tl} {tr}
    结束
    设 sl2 = 解析JSON []
    遍历 s 于 {d.students}
      设 su = 查一行 app.db account_user_by_name username={s.learner}
      设 sn = {su.display_name 或}
      如果 {su.username 或} 为空
        设 sn = {s.learner}（无账号）
      结束
      设 ms = 已撤销
      如果 {s.status} 等于 active
        设 ms = 在册
      结束
      设 ab = {s.assigned_by 或迁移登记}
      设 cr = 0
      如果 {s.status} 等于 active 且 ({d.my_role} 不等于 public 或 {s.assigned_by} 等于 {learner})
        设 cr = 1
      结束
      设 sr.member_learner = {s.learner}
      设 sr.member_learner_label = {sn}
      设 sr.member_state = {ms}
      设 sr.member_assigned_by = {ab}
      设 sr.can_revoke = {cr}
      设 sl2 = 列表加项 {sl2} {sr}
    结束
    设 cl = 解析JSON []
    如果 {ca} 等于 1
      设 cd = 调用 列可分配学生 subject_id={subj_id}
      遍历 c 于 {cd.students}
        设 cx.cand_learner = {c.username}
        设 cx.cand_label = {c.display_name}
        设 cl = 列表加项 {cl} {cx}
      结束
    结束
    设 ol = 解析JSON []
    如果 {cm} 等于 1
      设 trows = 查询 app.db account_teachers_enabled
      遍历 o 于 {trows}
        设 inn = 0
        遍历 t2 于 {d.teachers}
          如果 {t2.teacher} 等于 {o.username}
            设 inn = 1
          结束
        结束
        如果 {inn} 等于 0
          设 lb = {o.display_name}（{o.username}）
          设 ox.value = {o.username}
          设 ox.label = {lb}
          设 ol = 列表加项 {ol} {ox}
        结束
      结束
    结束
    设 form.subj_id = {d.id}
    设 form.assign_learners = 
    设 form.add_teacher = 
    设 form.add_role = 协作
    返回 {"form": {form}, "member_head": "{head}", "member_my_role": "{rl}", "can_manage": {cm}, "can_assign": {ca}, "member_teachers": {tl}, "member_students": {sl2}, "assign_candidates": {cl}, "teacher_options": {ol}}
  结束

  公开 函数 分配科目学生页面 learner subj_id assign_learners current_role? auth_mode?
    设 d = 调用 subject.科目详情 learner={learner} subject_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    设 s1 = 替换 {assign_learners} [，、\s,]+ ,
    设 parts = 按正则切分 {s1} ,
    设 joined = 
    设 seen = ,
    设 cnt = 0
    遍历 x 于 {parts}
      如果 {x} 为空
        继续
      结束
      设 key = ,{x},
      如果 {seen} 包含 {key}
        继续
      结束
      设 seen = {seen}{x},
      如果 {cnt} 等于 0
        设 joined = {x}
      否则
        设 joined = {joined},{x}
      结束
      设 cnt = 计算 {cnt} + 1
    结束
    如果 {cnt} 等于 0
      报错 400 请选择要分配的学生
    结束
    遍历 y 于 {parts}
      如果 {y} 不为空
        设 u = 查一行 app.db account_user_by_name username={y}
        如果 {u.username 或} 为空
          报错 400 有的用户名不是可用的学生账号
        结束
        如果 {u.role} 不等于 student 或 {u.disabled} 等于 1
          报错 400 有的用户名不是可用的学生账号
        结束
      结束
    结束
    设 ar = 调用 subject.分配学生 learner={learner} subject_id={subj_id} learners={joined} current_role={current_role} auth_mode={auth_mode}
    设 out = 调用 科目成员页面 learner={learner} subj_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    返回 {out}
  结束

  公开 函数 撤销科目学生页面 learner subj_id member_learner current_role? auth_mode?
    设 rv = 调用 subject.撤销学生 learner={learner} subject_id={subj_id} student={member_learner} current_role={current_role} auth_mode={auth_mode}
    设 out = 调用 科目成员页面 learner={learner} subj_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    返回 {out}
  结束

  公开 函数 加科目教师页面 learner subj_id add_teacher add_role? current_role? auth_mode?
    设 d = 调用 subject.科目详情 learner={learner} subject_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    如果 {d.my_role} 不等于 owner 且 {d.my_role} 不等于 single
      报错 403 只有科目负责人可以操作
    结束
    设 rr = editor
    如果 {add_role} 等于 负责
      设 rr = owner
    否则如果 {add_role} 不为空 且 {add_role} 不等于 协作
      报错 400 角色只能是 owner 或 editor
    结束
    设 at = 替换 {add_teacher} ^\s+|\s+$
    如果 {at} 为空
      报错 400 请选择要加入的教师
    结束
    设 u = 查一行 app.db account_user_by_name username={at}
    如果 {u.username 或} 为空
      报错 400 不是可用的教师账号
    结束
    如果 {u.role} 不等于 teacher 或 {u.disabled} 等于 1
      报错 400 不是可用的教师账号
    结束
    设 ad = 调用 subject.加科目教师 learner={learner} subject_id={subj_id} teacher={at} role={rr} current_role={current_role} auth_mode={auth_mode}
    设 out = 调用 科目成员页面 learner={learner} subj_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    返回 {out}
  结束

  公开 函数 改科目教师角色页面 learner subj_id member_teacher role current_role? auth_mode?
    设 rv = 调用 subject.改科目教师角色 learner={learner} subject_id={subj_id} teacher={member_teacher} role={role} current_role={current_role} auth_mode={auth_mode}
    设 out = 调用 科目成员页面 learner={learner} subj_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    返回 {out}
  结束

  公开 函数 移除科目教师页面 learner subj_id member_teacher current_role? auth_mode?
    设 rv = 调用 subject.移除科目教师 learner={learner} subject_id={subj_id} teacher={member_teacher} current_role={current_role} auth_mode={auth_mode}
    设 out = 调用 科目成员页面 learner={learner} subj_id={subj_id} current_role={current_role} auth_mode={auth_mode}
    返回 {out}
  结束

结束
