业务 subject
  用包 db text common

  公开 函数 科目访问 learner current_role subject_id need
    如果 {need} 不等于 read 且 {need} 不等于 write 且 {need} 不等于 settings 且 {need} 不等于 assign
      报错 400 need 不对
    结束
    如果 {current_role} 不等于 student 且 {current_role} 不等于 teacher
      返回 {"ok": 1, "reason": "", "via": "single"}
    结束
    设 si = 查一行 app.db subject_info_by_id id={subject_id}
    如果 {si} 为空
      返回 {"ok": 0, "reason": "没有这个科目", "via": ""}
    结束
    如果 {current_role} 等于 student
      如果 {need} 不等于 read
        返回 {"ok": 0, "reason": "学生没有这个权限", "via": ""}
      结束
      如果 {si.status} 等于 active
        设 stv = 查一值 app.db subject_student_status subject_id={subject_id} learner={learner}
        如果 {stv} 等于 active
          返回 {"ok": 1, "reason": "", "via": "assigned"}
        结束
      结束
      返回 {"ok": 0, "reason": "该科目未分配给你", "via": ""}
    结束
    设 tr = 查一值 app.db subject_teacher_role subject_id={subject_id} learner={learner}
    设 ident = none
    如果 {si.owner} 等于 {learner} 或 {tr} 等于 owner
      设 ident = owner
    否则如果 {tr} 等于 editor
      设 ident = editor
    否则如果 {si.visibility} 等于 public 且 {si.status} 不等于 draft
      设 ident = public
    结束
    如果 {ident} 等于 none
      返回 {"ok": 0, "reason": "没有权限访问该科目", "via": ""}
    结束
    设 allow = 0
    如果 {need} 等于 read 或 {need} 等于 assign
      设 allow = 1
    否则如果 {need} 等于 write
      如果 {ident} 等于 owner 或 {ident} 等于 editor
        设 allow = 1
      结束
    否则
      如果 {ident} 等于 owner
        设 allow = 1
      结束
    结束
    如果 {allow} 等于 1
      返回 {"ok": 1, "reason": "", "via": "{ident}"}
    结束
    返回 {"ok": 0, "reason": "没有这个权限", "via": ""}
  结束

  公开 函数 列我的科目 learner current_role
    如果 {current_role} 等于 student
      设 rows = 查询 app.db subject_list_student learner={learner}
    否则如果 {current_role} 等于 teacher
      设 rows = 查询 app.db subject_list_teacher learner={learner}
    否则
      设 rows = 查询 app.db subject_list_public
    结束
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "subjects": {rows}}
  结束

  公开 函数 当前科目 learner
    如果 {learner} 为空
      返回 {"subject_id": 1}
    结束
    设 pv = 查一值 app.db subject_pref_val learner={learner}
    如果 {pv} 不为空
      设 pi = 查一行 app.db subject_info_by_id id={pv}
      如果 {pi} 不为空
        如果 {pi.status} 不等于 draft
          设 okv = 0
          设 stv = 查一值 app.db subject_student_status subject_id={pv} learner={learner}
          如果 {stv} 等于 active 且 {pi.status} 等于 active
            设 okv = 1
          结束
          如果 {pi.owner} 等于 {learner}
            设 okv = 1
          结束
          设 tr = 查一值 app.db subject_teacher_role subject_id={pv} learner={learner}
          如果 {tr} 不为空
            设 okv = 1
          结束
          如果 {okv} 等于 1
            返回 {"subject_id": {pv}}
          结束
        结束
      结束
    结束
    设 fm = 查一值 app.db subject_first_assigned learner={learner}
    如果 {fm} 不为空
      返回 {"subject_id": {fm}}
    结束
    返回 {"subject_id": 1}
  结束

  公开 函数 解析科目 learner current_role auth_mode subject?
    如果 {subject} 为空
      设 c = 调用 subject.当前科目 learner={learner}
      返回 {"subject_id": {c.subject_id}}
    结束
    设 mm = 匹配 {subject} ^[0-9]+$
    如果 {mm.matched} 不等于 是
      报错 400 subject 不对
    结束
    如果 {auth_mode} 不等于 on
      返回 {"subject_id": {subject}}
    结束
    设 a = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={subject} need=read
    如果 {a.ok} 等于 0
      设 si = 查一行 app.db subject_info_by_id id={subject}
      如果 {si} 为空
        报错 404 没有这个科目
      结束
      如果 {current_role} 等于 student
        报错 403 该科目未分配给你
      结束
      报错 403 没有权限访问该科目
    结束
    返回 {"subject_id": {subject}}
  结束

  公开 函数 切换科目 learner current_role subject
    如果 {learner} 为空
      报错 400 subject 不对
    结束
    设 mm = 匹配 {subject} ^[0-9]+$
    如果 {mm.matched} 不等于 是
      报错 400 subject 不对
    结束
    设 a = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={subject} need=read
    如果 {a.ok} 等于 0
      设 si = 查一行 app.db subject_info_by_id id={subject}
      如果 {si} 为空
        报错 404 没有这个科目
      结束
      如果 {current_role} 等于 student
        报错 403 该科目未分配给你
      结束
      报错 403 没有权限访问该科目
    结束
    设 pv = 查一值 app.db subject_pref_val learner={learner}
    如果 {pv} 为空
      设 n = 写库 app.db subject_pref_insert learner={learner} subject_id={subject}
    否则
      设 n = 写库 app.db subject_pref_update learner={learner} subject_id={subject}
    结束
    返回 {"ok": 1, "subject": {subject}}
  结束
结束
