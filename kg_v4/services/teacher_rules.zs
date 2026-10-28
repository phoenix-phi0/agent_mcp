业务 teacher_rules
  依赖 account subject
  用包 common db text

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {"subject_id": {r.subject_id}}
  结束

  公开 函数 列设定 kind? student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 rows = 查询 app.db teacher_rules_setting_list kind={kind} student={student} subj={sid}
    设 n = 查一值 app.db teacher_rules_setting_count kind={kind} student={student} subj={sid}
    设 out.items = {rows}
    设 out.total = {n}
    返回 {out}
  结束

  公开 函数 取设定 setting_id learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 p = 查一行 app.db teacher_rules_setting_get id={setting_id} subj={sid}
    如果 {p.id 或} 为空
      报错 404 没有这条设定
    结束
    返回 {p}
  结束

  公开 函数 保存设定 kind content current_user setting_id? student? keywords? once? scope? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    如果 {scope} 不为空 且 {scope} 不等于 current 且 {scope} 不等于 all
      报错 400 范围不对
    结束
    设 need_own = 0
    如果 {scope} 等于 all
      设 need_own = 1
    结束
    如果 {setting_id} 不为空
      设 old = 查一行 app.db teacher_rules_setting_get id={setting_id} subj={sid}
      如果 {old.id 或} 为空
        报错 404 没有这条设定
      结束
      如果 {old.subject_id} 等于 0
        设 need_own = 1
      结束
    结束
    如果 {need_own} 等于 1
      设 ow = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={sid} need=own
    结束
    如果 {kind 或 none} 不等于 memory 且 {kind 或 none} 不等于 note 且 {kind 或 none} 不等于 card
      报错 400 种类只能是 memory、note、card
    结束
    设 has = 匹配 文本={content} 正则=\S
    如果 {has.matched} 不等于 是
      报错 400 内容必填
    结束
    设 kw = 替换 文本={keywords} 正则=[，、,\s]+ 替换为=,
    设 kw = 替换 文本={kw} 正则=^,|,$
    设 once_val = 0
    如果 {kind} 等于 note 且 {once 或 0} 等于 1
      设 once_val = 1
    结束
    如果 {setting_id} 为空
      设 ins_sid = {sid}
      如果 {scope} 等于 all
        设 ins_sid = 0
      结束
      设 args.kind = {kind}
      设 args.student = {student}
      设 args.keywords = {kw}
      设 args.content = {content}
      设 args.once = {once_val}
      设 args.author = {current_user}
      设 args.subj = {ins_sid}
      设 n = 写库表 app.db teacher_rules_setting_insert {args}
      设 sid2 = 查一值 app.db teacher_rules_setting_last_id
    否则
      设 ns = {blank 或}
      如果 {scope} 等于 all
        设 ns = 0
      否则如果 {scope} 等于 current
        设 ns = {sid}
      结束
      设 args.id = {setting_id}
      设 args.kind = {kind}
      设 args.student = {student}
      设 args.keywords = {kw}
      设 args.content = {content}
      设 args.once = {once_val}
      设 args.author = {current_user}
      设 args.subj = {sid}
      设 args.new_sid = {ns}
      设 n = 写库表 app.db teacher_rules_setting_update {args}
      设 sid2 = {setting_id}
    结束
    设 p = 查一行 app.db teacher_rules_setting_get id={sid2} subj={sid}
    返回 {p}
  结束

  公开 函数 设置设定启用 setting_id enabled learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    如果 {enabled 或 none} 不等于 0 且 {enabled 或 none} 不等于 1
      报错 400 enabled 只能是 0 或 1
    结束
    设 old = 查一行 app.db teacher_rules_setting_get id={setting_id} subj={sid}
    如果 {old.id 或} 为空
      报错 404 没有这条设定
    结束
    如果 {old.subject_id} 等于 0
      设 ow = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid} need=own
    结束
    设 n = 写库 app.db teacher_rules_setting_set_enabled id={setting_id} enabled={enabled}
    设 p = 查一行 app.db teacher_rules_setting_enabled_view id={setting_id}
    返回 {p}
  结束

  公开 函数 删除设定 setting_id learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 old = 查一行 app.db teacher_rules_setting_get id={setting_id} subj={sid}
    如果 {old.id 或} 为空
      报错 404 没有这条设定
    结束
    如果 {old.subject_id} 等于 0
      设 ow = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid} need=own
    结束
    设 n = 写库 app.db teacher_rules_setting_delete id={setting_id}
    返回 {"ok": 1}
  结束

  公开 函数 取生效设定 student recent_text? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 args.student = {student}
    设 args.recent = {recent_text}
    设 args.subj = {sid}
    设 p = 查一行表 app.db teacher_rules_setting_effective {args}
    返回 {p}
  结束

  公开 函数 记回复用到设定 reply_id student setting_ids setting_versions learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    如果 {setting_ids} 为空
      返回 {"ok": 1, "recorded": 0}
    结束
    设 bad = 查一值 app.db teacher_rules_pair_mismatch a={setting_ids} b={setting_versions}
    如果 {bad} 等于 1
      报错 400 设定编号与版本号个数不一致
    结束
    设 foreign = 查一值 app.db teacher_rules_setting_foreign_count ids={setting_ids} subj={sid}
    如果 {foreign} 大于 0
      报错 404 没有这条设定
    结束
    设 n = 写库 app.db teacher_rules_setting_use_insert reply_id={reply_id} student={student} setting_ids={setting_ids} setting_versions={setting_versions} subj={sid}
    返回 {"ok": 1, "recorded": 1}
  结束

  公开 函数 列传达 learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 rows = 查询 app.db teacher_rules_relay_list subj={sid}
    设 n = 查一值 app.db teacher_rules_relay_count subj={sid}
    设 out.items = {rows}
    设 out.total = {n}
    返回 {out}
  结束

  公开 函数 取传达 relay_id learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 p = 查一行 app.db teacher_rules_relay_get id={relay_id} subj={sid}
    如果 {p.id 或} 为空
      报错 404 没有这条传达
    结束
    返回 {p}
  结束

  公开 函数 保存传达 urgency must_info rounds current_user relay_id? tone? deadline? student? facts? keywords? scope? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    如果 {scope} 不为空 且 {scope} 不等于 current 且 {scope} 不等于 all
      报错 400 范围不对
    结束
    设 need_own = 0
    如果 {scope} 等于 all
      设 need_own = 1
    结束
    如果 {relay_id} 不为空
      设 old = 查一行 app.db teacher_rules_relay_get id={relay_id} subj={sid}
      如果 {old.id 或} 为空
        报错 404 没有这条传达
      结束
      如果 {old.subject_id} 等于 0
        设 need_own = 1
      结束
    结束
    如果 {need_own} 等于 1
      设 ow = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={sid} need=own
    结束
    如果 {urgency 或 none} 不等于 low 且 {urgency 或 none} 不等于 normal 且 {urgency 或 none} 不等于 urgent
      报错 400 紧急程度只能是 low、normal 或 urgent
    结束
    设 has = 匹配 文本={must_info} 正则=\S
    如果 {has.matched} 不等于 是
      报错 400 必须准确的信息必填
    结束
    设 rm = 匹配 文本={rounds} 正则=^[0-9]+$
    如果 {rm.matched} 不等于 是
      报错 400 轮数必须是不小于 1 的整数
    结束
    如果 {rounds} 小于 1
      报错 400 轮数必须是不小于 1 的整数
    结束
    如果 {deadline} 不为空
      设 dm = 匹配 文本={deadline} 正则=^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$
      如果 {dm.matched} 不等于 是
        报错 400 截止日格式应为 YYYY-MM-DD
      结束
    结束
    如果 {relay_id} 为空
      设 ins_sid = {sid}
      如果 {scope} 等于 all
        设 ins_sid = 0
      结束
      设 args.urgency = {urgency}
      设 args.tone = {tone}
      设 args.must_info = {must_info}
      设 args.rounds = {rounds}
      设 args.deadline = {deadline}
      设 args.student = {student}
      设 args.facts = {facts}
      设 args.keywords = {keywords}
      设 args.author = {current_user}
      设 args.subj = {ins_sid}
      设 n = 写库表 app.db teacher_rules_relay_insert {args}
      设 rid = 查一值 app.db teacher_rules_relay_last_id
    否则
      设 ns = {blank 或}
      如果 {scope} 等于 all
        设 ns = 0
      否则如果 {scope} 等于 current
        设 ns = {sid}
      结束
      设 args.id = {relay_id}
      设 args.urgency = {urgency}
      设 args.tone = {tone}
      设 args.must_info = {must_info}
      设 args.rounds = {rounds}
      设 args.deadline = {deadline}
      设 args.student = {student}
      设 args.facts = {facts}
      设 args.keywords = {keywords}
      设 args.author = {current_user}
      设 args.subj = {sid}
      设 args.new_sid = {ns}
      设 n = 写库表 app.db teacher_rules_relay_update {args}
      设 rid = {relay_id}
    结束
    设 p = 查一行 app.db teacher_rules_relay_get id={rid} subj={sid}
    返回 {p}
  结束

  公开 函数 设置传达启用 relay_id enabled learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    如果 {enabled 或 none} 不等于 0 且 {enabled 或 none} 不等于 1
      报错 400 enabled 只能是 0 或 1
    结束
    设 old = 查一行 app.db teacher_rules_relay_get id={relay_id} subj={sid}
    如果 {old.id 或} 为空
      报错 404 没有这条传达
    结束
    如果 {old.subject_id} 等于 0
      设 ow = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid} need=own
    结束
    设 n = 写库 app.db teacher_rules_relay_set_enabled id={relay_id} enabled={enabled}
    设 p = 查一行 app.db teacher_rules_relay_enabled_view id={relay_id}
    返回 {p}
  结束

  公开 函数 删除传达 relay_id learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 old = 查一行 app.db teacher_rules_relay_get id={relay_id} subj={sid}
    如果 {old.id 或} 为空
      报错 404 没有这条传达
    结束
    如果 {old.subject_id} 等于 0
      设 ow = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid} need=own
    结束
    事务 app.db
      设 n1 = 写库 app.db teacher_rules_relay_delete id={relay_id}
      设 n2 = 写库 app.db teacher_rules_relay_state_delete_by_relay relay_id={relay_id}
    结束
    返回 {"ok": 1}
  结束

  公开 函数 对学生发传达 relay_id student learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 r = 查一行 app.db teacher_rules_relay_get id={relay_id} subj={sid}
    如果 {r.id 或} 为空
      报错 404 没有这条传达
    结束
    如果 {r.enabled} 等于 0
      报错 400 传达已停用
    结束
    如果 {r.student 或} 不为空 且 {r.student 或} 不等于 {student 或 none}
      报错 400 这条传达不是发给该学生的
    结束
    事务 app.db
      设 n1 = 写库 app.db teacher_rules_relay_state_reset relay_id={r.id} student={student}
      设 n2 = 写库 app.db teacher_rules_relay_state_insert_new relay_id={r.id} student={student}
    结束
    返回 {"ok": 1, "relay_id": {r.id}, "student": "{student}"}
  结束

  公开 函数 列传达状态 student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 rows = 查询 app.db teacher_rules_relay_state_list student={student} subj={sid}
    设 n = 查一值 app.db teacher_rules_relay_state_count student={student} subj={sid}
    设 out.items = {rows}
    设 out.total = {n}
    返回 {out}
  结束

  公开 函数 取待传达 student learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 today = 当前时间 日期
    设 p = 查一行 app.db teacher_rules_relay_pending student={student} today={today} subj={sid}
    返回 {p}
  结束

  公开 函数 记回复传达 reply_id student relay_ids learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    如果 {relay_ids} 为空
      返回 {"ok": 1, "recorded": 0}
    结束
    设 miss = 查一值 app.db teacher_rules_relay_missing_count ids={relay_ids} subj={sid}
    如果 {miss} 大于 0
      报错 404 没有这条传达
    结束
    设 other = 查一值 app.db teacher_rules_relay_other_student_count ids={relay_ids} student={student}
    如果 {other} 大于 0
      报错 400 这条传达不是发给该学生的
    结束
    事务 app.db
      设 n1 = 写库 app.db teacher_rules_relay_use_insert reply_id={reply_id} student={student} relay_ids={relay_ids} subj={sid}
      设 n2 = 写库 app.db teacher_rules_relay_state_bump ids={relay_ids} student={student}
      设 n3 = 写库 app.db teacher_rules_relay_state_insert_first ids={relay_ids} student={student}
    结束
    返回 {"ok": 1, "recorded": 1}
  结束

  公开 函数 记传达判定 student relay_id delivered learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    如果 {delivered 或 none} 不等于 0 且 {delivered 或 none} 不等于 1
      报错 400 delivered 只能是 0 或 1
    结束
    设 r = 查一行 app.db teacher_rules_relay_get id={relay_id} subj={sid}
    如果 {r.id 或} 为空
      报错 404 没有这条传达
    结束
    如果 {r.student 或} 不为空 且 {r.student 或} 不等于 {student 或 none}
      报错 404 没有传达状态
    结束
    设 st = 查一行 app.db teacher_rules_relay_state_get relay_id={relay_id} student={student}
    如果 {st.relay_id 或} 为空
      报错 404 没有传达状态
    结束
    如果 {delivered} 等于 1
      设 n = 写库 app.db teacher_rules_relay_state_confirm relay_id={relay_id} student={student}
    结束
    设 st2 = 查一行 app.db teacher_rules_relay_state_get relay_id={relay_id} student={student}
    返回 {st2}
  结束

  公开 函数 设定列表 student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 own = 1
    设 wr = 1
    如果 {auth_mode} 等于 on
      设 a1 = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=settings auth_mode={auth_mode}
      设 own = {a1.ok}
      设 a2 = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=write auth_mode={auth_mode}
      设 wr = {a2.ok}
    结束
    设 sname = 查一值 app.db teacher_rules_subject_name id={sid}
    如果 {sname 或} 为空
      设 sname = 科目{sid}
    结束
    设 rows = 查询 app.db teacher_rules_note_rows student={student} subj={sid} sname={sname} own={own} wr={wr}
    设 tv = 替换 文本=xtruex 正则=x
    设 fv = 替换 文本=xfalsex 正则=x
    设 items = 解析JSON []
    遍历 row 于 {rows}
      如果 {row.note_once} 等于 1
        设 row.note_once = {tv}
      否则
        设 row.note_once = {fv}
      结束
      设 items = 列表加项 {items} {row}
    结束
    返回 {items}
  结束

  公开 函数 传达列表 student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 today = 当前时间 日期
    设 studs = ,
    设 total = 0
    如果 {student} 为空
      设 st = 调用 account.列学生
      设 total = {st.total 或 0}
      遍历 u 于 {st.students}
        设 studs = {studs},{u.username}
      结束
    结束
    设 own = 1
    设 wr = 1
    如果 {auth_mode} 等于 on
      设 a1 = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=settings auth_mode={auth_mode}
      设 own = {a1.ok}
      设 a2 = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=write auth_mode={auth_mode}
      设 wr = {a2.ok}
    结束
    设 sname = 查一值 app.db teacher_rules_subject_name id={sid}
    如果 {sname 或} 为空
      设 sname = 科目{sid}
    结束
    设 rows = 查询 app.db teacher_rules_relay_rows student={student} today={today} studs={studs} total={total} subj={sid} sname={sname} own={own} wr={wr}
    返回 {rows}
  结束

  公开 函数 传达状态列表 learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 today = 当前时间 日期
    设 studs = ,
    设 st = 调用 account.列学生
    遍历 u 于 {st.students}
      设 studs = {studs},{u.username}
    结束
    设 names = 查询 app.db teacher_rules_sorted_names studs={studs}
    设 rels = 查询 app.db teacher_rules_relay_list subj={sid}
    设 out = 解析JSON []
    遍历 rel 于 {rels}
      如果 {rel.student 或} 为空
        遍历 nm 于 {names}
          设 a = 调用 account.取账号 username={nm.username}
          设 label = {nm.username}
          如果 {a.display_name 或} 不为空
            设 label = {a.display_name}（{nm.username}）
          结束
          设 p = 查一行 app.db teacher_rules_relay_pair relay_id={rel.id} student={nm.username} today={today} label={label}
          设 out = 列表加项 {out} {p}
        结束
      结束
    结束
    返回 {out}
  结束

  公开 函数 取回复用到 reply_id learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 a = 查一值 app.db teacher_rules_reply_setting_text reply_id={reply_id} subj={sid}
    设 b = 查一值 app.db teacher_rules_reply_relay_text reply_id={reply_id} subj={sid}
    设 text = {a 或}
    如果 {a 或} 不为空 且 {b 或} 不为空
      设 text = {a}、{b}
    否则如果 {b 或} 不为空
      设 text = {b}
    结束
    设 out.text = {text}
    返回 {out}
  结束

  公开 函数 设定首页页面 learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 notes_r = 调用 设定列表 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 notes = {notes_r}
    设 relays = 调用 传达列表 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 states = 调用 传达状态列表 subject={sid}
    设 st = 调用 account.列学生
    设 studs = ,
    遍历 u 于 {st.students}
      设 studs = {studs},{u.username}
    结束
    设 names = 查询 app.db teacher_rules_sorted_names studs={studs}
    设 opts = 解析JSON []
    遍历 nm 于 {names}
      设 a = 调用 account.取账号 username={nm.username}
      设 label = {nm.username}
      如果 {a.display_name 或} 不为空
        设 label = {a.display_name}（{nm.username}）
      结束
      设 o = 查一行 app.db teacher_rules_student_option username={nm.username} label={label}
      设 opts = 列表加项 {opts} {o}
    结束
    设 out.class_notes = {notes}
    设 out.note_students = {opts}
    设 out.class_relays = {relays}
    设 out.class_relay_states = {states}
    设 own = 1
    如果 {auth_mode} 等于 on
      设 a1 = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=settings auth_mode={auth_mode}
      设 own = {a1.ok}
    结束
    设 sname = 查一值 app.db teacher_rules_subject_name id={sid}
    如果 {sname 或} 为空
      设 sname = 科目{sid}
    结束
    设 out.note_is_owner = {own}
    设 out.subject_head = {sname}的AI老师设定（含全部科目的）
    返回 {out}
  结束

  公开 函数 载入设定页面 note_id? student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    如果 {note_id} 为空
      返回 {"student": "{student}", "note_kind": "记忆", "note_keywords": "", "note_content": "", "note_once": "false", "note_subject_scope": "当前科目"}
    结束
    设 p = 调用 取设定 setting_id={note_id} subject={sid}
    如果 {p.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条设定
    结束
    设 kindcn = 关键词卡
    如果 {p.kind} 等于 memory
      设 kindcn = 记忆
    否则如果 {p.kind} 等于 note
      设 kindcn = 作者注
    结束
    设 tv = 替换 文本=xtruex 正则=x
    设 fv = 替换 文本=xfalsex 正则=x
    设 scope_cn = 当前科目
    如果 {p.subject_id} 等于 0
      设 scope_cn = 全部科目
    结束
    设 out.note_subject_scope = {scope_cn}
    设 out.student = {student}
    设 out.note_kind = {kindcn}
    设 out.note_keywords = {p.keywords}
    设 out.note_content = {p.content}
    如果 {p.once} 等于 1
      设 out.note_once = {tv}
    否则
      设 out.note_once = {fv}
    结束
    返回 {out}
  结束

  公开 函数 保存设定页面 note_content current_user note_kind? note_id? student? note_keywords? note_once? note_subject_scope? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 scope_v = {blank 或}
    如果 {note_subject_scope 或} 等于 当前科目 或 {note_subject_scope 或} 等于 current
      设 scope_v = current
    否则如果 {note_subject_scope 或} 等于 全部科目 或 {note_subject_scope 或} 等于 all
      设 scope_v = all
    否则如果 {note_subject_scope 或} 不为空
      报错 400 范围不对
    结束
    设 kind_v = {note_kind}
    如果 {note_kind 或 _} 等于 记忆 或 {note_kind 或 _} 等于 _
      设 kind_v = memory
    否则如果 {note_kind 或 _} 等于 作者注
      设 kind_v = note
    否则如果 {note_kind 或 _} 等于 关键词卡
      设 kind_v = card
    结束
    如果 {student} 不为空
      设 acc = 调用 account.取账号 username={student}
      如果 {acc.username 或} 为空 或 {acc.role 或 _} 不等于 student
        报错 404 没有这个学生
      结束
    结束
    如果 {note_id} 不为空
      设 old = 调用 取设定 setting_id={note_id} subject={sid}
      如果 {old.student 或 _} 不等于 {student 或 _}
        报错 404 没有这条设定
      结束
    结束
    设 once_v = 0
    设 raw_once = {note_once 或 0}
    如果 {raw_once} 等于 是 或 {raw_once} 等于 True 或 {raw_once} 等于 true 或 {raw_once} 等于 TRUE 或 {raw_once} 等于 1
      设 once_v = 1
    结束
    设 saved = 调用 保存设定 kind={kind_v} content={note_content} current_user={current_user} setting_id={note_id} student={student} keywords={note_keywords} once={once_v} scope={scope_v} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 notes_r = 调用 设定列表 student={student} learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 notes = {notes_r}
    如果 {student} 为空
      设 out.class_notes = {notes}
    否则
      设 out.student_notes = {notes}
    结束
    返回 {out}
  结束

  公开 函数 设置设定启用页面 note_id enabled student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 old = 调用 取设定 setting_id={note_id} subject={sid}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条设定
    结束
    设 u = 调用 设置设定启用 setting_id={note_id} enabled={enabled} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 notes_r = 调用 设定列表 student={student} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 notes = {notes_r}
    如果 {student} 为空
      设 out.class_notes = {notes}
    否则
      设 out.student_notes = {notes}
    结束
    返回 {out}
  结束

  公开 函数 删除设定页面 note_id student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 old = 调用 取设定 setting_id={note_id} subject={sid}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条设定
    结束
    设 u = 调用 删除设定 setting_id={note_id} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 notes_r = 调用 设定列表 student={student} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    设 notes = {notes_r}
    如果 {student} 为空
      设 out.class_notes = {notes}
    否则
      设 out.student_notes = {notes}
    结束
    返回 {out}
  结束

  公开 函数 设定预览页面 preview_student preview_message learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    如果 {preview_student} 为空
      报错 400 先选一个学生
    结束
    如果 {preview_message} 为空
      报错 400 输一句示例提问
    结束
    设 ra = {blank 或}
    设 ex = 查一值 app.db teacher_rules_tutor_exists
    如果 {ex} 大于 0
      设 ra = 查一值 app.db teacher_rules_recent_asks learner={preview_student} subj={sid}
    结束
    设 recent_text = 查一值 app.db teacher_rules_text_join a={ra} b={preview_message}
    设 eff = 调用 取生效设定 student={preview_student} recent_text={recent_text} subject={sid}
    设 pend = 调用 取待传达 student={preview_student} subject={sid}
    设 ids = {eff.setting_ids}
    如果 {eff.setting_ids 或} 为空
      设 ids = （无）
    结束
    设 relay_pick = （没有待传达的要点）
    如果 {pend.relay_ids 或} 不为空
      设 first = 替换 文本={pend.relay_ids} 正则=,.*$
      设 rest_n = 计算 {pend.count} - 1
      设 relay_pick = 查一值 app.db teacher_rules_relay_pick id={first} rest={rest_n}
    结束
    设 layout = 查一值 app.db teacher_rules_preview_layout memory={eff.memory_text} card={eff.card_text} relay={pend.prompt_text} note={eff.note_text} message={preview_message}
    设 hits = 查询 app.db teacher_rules_hit_cards student={preview_student} recent={recent_text} subj={sid}
    设 pv.ids = {ids}
    设 pv.relay_pick = {relay_pick}
    设 pv.layout = {layout}
    设 out.preview = {pv}
    设 out.preview_hits = {hits}
    返回 {out}
  结束

  公开 函数 载入传达页面 relay_id? student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    如果 {relay_id} 为空
      返回 {"student": "{student}", "relay_point": "", "relay_urgency": "尽快", "relay_voice": "以老师名义", "relay_facts": "", "relay_keywords": "", "relay_rounds": 3, "relay_due": "", "relay_subject_scope": "当前科目"}
    结束
    设 p = 调用 取传达 relay_id={relay_id} subject={sid}
    如果 {p.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条传达
    结束
    设 urg = 尽快
    如果 {p.urgency} 等于 urgent
      设 urg = 立即
    否则如果 {p.urgency} 等于 low
      设 urg = 顺便
    结束
    设 out.student = {student}
    设 out.relay_point = {p.must_info}
    设 out.relay_urgency = {urg}
    设 out.relay_voice = {p.tone 或 以老师名义}
    设 out.relay_facts = {p.facts 或}
    设 out.relay_keywords = {p.keywords 或}
    设 out.relay_rounds = {p.rounds}
    设 scope_cn = 当前科目
    如果 {p.subject_id} 等于 0
      设 scope_cn = 全部科目
    结束
    设 out.relay_subject_scope = {scope_cn}
    设 out.relay_due = {p.deadline 或}
    返回 {out}
  结束

  公开 函数 保存传达页面 relay_point current_user relay_id? student? relay_urgency? relay_voice? relay_facts? relay_keywords? relay_rounds? relay_due? relay_subject_scope? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    如果 {student} 不为空
      设 acc = 调用 account.取账号 username={student}
      如果 {acc.username 或} 为空 或 {acc.role 或 _} 不等于 student
        报错 404 没有这个学生
      结束
    结束
    如果 {relay_id} 不为空
      设 old = 调用 取传达 relay_id={relay_id} subject={sid}
      如果 {old.student 或 _} 不等于 {student 或 _}
        报错 404 没有这条传达
      结束
    结束
    设 scope_v = {blank 或}
    如果 {relay_subject_scope 或} 等于 当前科目 或 {relay_subject_scope 或} 等于 current
      设 scope_v = current
    否则如果 {relay_subject_scope 或} 等于 全部科目 或 {relay_subject_scope 或} 等于 all
      设 scope_v = all
    否则如果 {relay_subject_scope 或} 不为空
      报错 400 范围不对
    结束
    设 urg = normal
    如果 {relay_urgency 或 _} 等于 立即
      设 urg = urgent
    否则如果 {relay_urgency 或 _} 等于 顺便
      设 urg = low
    结束
    设 rounds_v = {relay_rounds 或 3}
    如果 {rounds_v} 等于 0
      设 rounds_v = 3
    结束
    设 saved = 调用 保存传达 urgency={urg} must_info={relay_point} rounds={rounds_v} current_user={current_user} relay_id={relay_id} tone={relay_voice} deadline={relay_due} student={student} facts={relay_facts} keywords={relay_keywords} scope={scope_v} current_role={current_role} auth_mode={auth_mode} subject={sid}
    如果 {student} 为空
      设 rl = 调用 传达列表 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={sid}
      设 rs = 调用 传达状态列表 subject={sid}
      设 out.class_relays = {rl}
      设 out.class_relay_states = {rs}
    否则
      设 rl = 调用 传达列表 student={student} learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={sid}
      设 out.student_relays = {rl}
    结束
    返回 {out}
  结束

  公开 函数 设置传达启用页面 relay_id enabled student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 old = 调用 取传达 relay_id={relay_id} subject={sid}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条传达
    结束
    设 u = 调用 设置传达启用 relay_id={relay_id} enabled={enabled} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    如果 {student} 为空
      设 rl = 调用 传达列表 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
      设 rs = 调用 传达状态列表 subject={sid}
      设 out.class_relays = {rl}
      设 out.class_relay_states = {rs}
    否则
      设 rl = 调用 传达列表 student={student} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
      设 out.student_relays = {rl}
    结束
    返回 {out}
  结束

  公开 函数 删除传达页面 relay_id student? learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 sid = {sr.subject_id}
    设 old = 调用 取传达 relay_id={relay_id} subject={sid}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条传达
    结束
    设 u = 调用 删除传达 relay_id={relay_id} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
    如果 {student} 为空
      设 rl = 调用 传达列表 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
      设 rs = 调用 传达状态列表 subject={sid}
      设 out.class_relays = {rl}
      设 out.class_relay_states = {rs}
    否则
      设 rl = 调用 传达列表 student={student} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={sid}
      设 out.student_relays = {rl}
    结束
    返回 {out}
  结束

  公开 函数 传达记录页面 message_id learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 mid = 查一值 app.db teacher_rules_relay_state_by_id id={message_id} subj={sid}
    如果 {mid 或} 为空
      报错 404 没有这条问老师记录
    结束
    返回 {"relay_msg_ask": "（暂不记录原话）", "relay_msg_reply": "（暂不记录原话）", "relay_excerpt": "（暂不记录原话）"}
  结束

结束
