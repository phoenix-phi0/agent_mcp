业务 subject
  用包 db text common

  公开 函数 科目访问 learner current_role subject_id need auth_mode?
    如果 {need} 不等于 read 且 {need} 不等于 write 且 {need} 不等于 settings 且 {need} 不等于 assign
      报错 400 need 不对
    结束
    如果 {current_role} 不等于 student 且 {current_role} 不等于 teacher
      如果 {auth_mode} 等于 on
        返回 {"ok": 0, "reason": "没有权限访问该科目", "via": ""}
      结束
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
    设 lang = zh
    设 ev = 查一值 app.db subject_table_exists name=account_user
    如果 {ev} 大于 0
      设 lg = 查一值 app.db subject_user_lang username={learner}
      设 lang = {lg 或 zh}
    结束
    如果 {lang} 等于 ja
      设 out = 解析JSON []
      遍历 s 于 {rows}
        设 nm = {s.name}
        设 tx = 调用 subject.译文 tbl=subject_info row_key={s.code} field=name lang=ja
        如果 {tx.text} 不为空
          设 nm = {tx.text}
        结束
        设 o = {"id": {s.id}, "code": "{s.code}", "name": "{nm}", "kind": "{s.kind}", "visibility": "{s.visibility}"}
        设 out = 列表加项 {out} {o}
      结束
      设 rows = {out}
    结束
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "subjects": {rows}}
  结束

  公开 函数 当前科目 learner current_role?
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
          如果 {current_role} 等于 teacher 且 {pi.visibility} 等于 public 且 {pi.status} 等于 active
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

  公开 函数 解析科目 learner current_role auth_mode subject? need?
    如果 {need} 不为空 且 {need} 不等于 read 且 {need} 不等于 write 且 {need} 不等于 own
      报错 400 need 不对
    结束
    如果 {subject} 为空
      设 c = 调用 subject.当前科目 learner={learner} current_role={current_role}
      设 sid = {c.subject_id}
    否则
      设 mm = 匹配 {subject} ^[0-9]+$
      如果 {mm.matched} 不等于 是
        报错 400 subject 不对
      结束
      设 sid = {subject}
      如果 {auth_mode} 等于 on
        设 a = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=read auth_mode=on
        如果 {a.ok} 等于 0
          设 si = 查一行 app.db subject_info_by_id id={sid}
          如果 {si} 为空
            报错 404 没有这个科目
          结束
          如果 {current_role} 等于 student
            报错 403 该科目未分配给你
          结束
          报错 403 没有权限访问该科目
        结束
      结束
    结束
    如果 {auth_mode} 等于 on 且 {need} 等于 write
      设 w = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=write auth_mode=on
      如果 {w.ok} 等于 0
        设 si = 查一行 app.db subject_info_by_id id={sid}
        如果 {si} 为空
          报错 404 没有这个科目
        结束
        报错 403 没有权限修改该科目
      结束
    结束
    如果 {auth_mode} 等于 on 且 {need} 等于 own
      设 w = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={sid} need=settings auth_mode=on
      如果 {w.ok} 等于 0
        设 si = 查一行 app.db subject_info_by_id id={sid}
        如果 {si} 为空
          报错 404 没有这个科目
        结束
        报错 403 只有科目负责人可以操作
      结束
    结束
    返回 {"subject_id": {sid}}
  结束

  公开 函数 列科目学生 subject_id
    设 rows = 查询 app.db subject_student_list subject_id={subject_id}
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "students": {rows}}
  结束

  公开 函数 登记学生 learner code?
    如果 {learner} 为空
      返回 {"registered": 0, "subject_id": 0}
    结束
    设 cd = {code 或 jp_grammar}
    设 si = 查一行 app.db subject_info_by_code code={cd}
    如果 {si} 为空
      返回 {"registered": 0, "subject_id": 0}
    结束
    设 stv = 查一值 app.db subject_student_status subject_id={si.id} learner={learner}
    如果 {stv} 不为空
      返回 {"registered": 0, "subject_id": {si.id}}
    结束
    设 now = 当前时间
    设 n = 写库 app.db subject_student_insert subject_id={si.id} learner={learner} created_at={now}
    返回 {"registered": 1, "subject_id": {si.id}}
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

  函数 管理校验 learner subject_id need current_role? auth_mode?
    如果 {subject_id} 为空
      报错 400 subject_id 不对
    结束
    设 mm = 匹配 {subject_id} ^[0-9]+$
    如果 {mm.matched} 不等于 是
      报错 400 subject_id 不对
    结束
    设 si = 查一行 app.db subject_info_full id={subject_id}
    如果 {si} 为空
      报错 404 没有这个科目
    结束
    如果 {auth_mode} 不等于 on
      返回 {"subject_id": {si.id}, "code": "{si.code}", "status": "{si.status}", "visibility": "{si.visibility}", "owner": "{si.owner}", "via": "single"}
    结束
    如果 {current_role} 不等于 teacher
      报错 403 只有教师可以管理科目
    结束
    设 a = 调用 科目访问 learner={learner} current_role={current_role} subject_id={subject_id} need={need} auth_mode=on
    如果 {a.ok} 等于 0
      如果 {need} 等于 settings
        报错 403 只有科目负责人可以操作
      结束
      如果 {need} 等于 assign
        报错 403 没有权限给该科目分配学生
      结束
      报错 403 没有权限访问该科目
    结束
    返回 {"subject_id": {si.id}, "code": "{si.code}", "status": "{si.status}", "visibility": "{si.visibility}", "owner": "{si.owner}", "via": "{a.via}"}
  结束

  函数 负责人数 subject_id except?
    设 q = {"subject_id": "{subject_id}", "ex": "{except}"}
    设 n = 查一值表 app.db subject_owner_count {q}
    返回 {"n": {n}}
  结束

  公开 函数 科目等级 subject_id
    设 sid = {subject_id 或}
    设 mm = 匹配 {sid} ^[0-9]+$
    如果 {mm.matched} 不等于 是
      设 sid = 1
    结束
    设 si = 查一行 app.db subject_levels_by_id id={sid}
    设 raw = {si.levels 或}
    设 parts = 按正则切分 {raw} ,
    设 items = 解析JSON []
    设 txt = {zz 或}
    设 first = {zz 或}
    遍历 x 于 {parts}
      如果 {x} 为空
        继续
      结束
      设 s = 替换 {x} ^\s+|\s+$
      如果 {s} 为空
        继续
      结束
      设 items = 列表加项 {items} {s}
      如果 {txt} 为空
        设 txt = {s}
        设 first = {s}
      否则
        设 txt = {txt},{s}
      结束
    结束
    设 n = 列表长度 {items}
    如果 {n} 等于 0
      设 items = 解析JSON ["N5","N4","N3","N2","N1"]
      设 txt = N5,N4,N3,N2,N1
      设 first = N5
      设 n = 5
    结束
    设 opts = 解析JSON [{"value":"全部","label":"全部"}]
    遍历 y 于 {items}
      设 o = {"value": "{y}", "label": "{y}"}
      设 opts = 列表加项 {opts} {o}
    结束
    返回 {"levels": {items}, "first": "{first}", "text": "{txt}", "count": {n}, "options": {opts}}
  结束

  函数 校验等级 levels
    设 parts = 按正则切分 {levels 或} ,
    设 seen = ,
    设 cnt = 0
    设 txt = {zz 或}
    遍历 x 于 {parts}
      如果 {x} 为空
        继续
      结束
      设 s = 替换 {x} ^\s+|\s+$
      如果 {s} 为空
        继续
      结束
      设 tl = 截取 {s} 13
      如果 {tl} 不为空
        报错 400 等级格式不对
      结束
      设 bad = 匹配 {s} [|^\s]
      如果 {bad.matched} 等于 是
        报错 400 等级格式不对
      结束
      设 key = ,{s},
      如果 {seen} 包含 {key}
        报错 400 等级格式不对
      结束
      设 seen = {seen}{s},
      设 cnt = 计算 {cnt} + 1
      如果 {cnt} 大于 10
        报错 400 等级格式不对
      结束
      如果 {txt} 为空
        设 txt = {s}
      否则
        设 txt = {txt},{s}
      结束
    结束
    如果 {cnt} 等于 0
      报错 400 等级格式不对
    结束
    返回 {"text": "{txt}", "count": {cnt}}
  结束

  函数 等级在用数 subject_id level
    设 total = 0
    设 q = {"subject_id": "{subject_id}", "level": "{level}"}
    设 e1 = 查一值 app.db subject_table_exists name=quiz_question
    如果 {e1} 大于 0
      设 c1 = 查一值表 app.db subject_use_quiz_question {q}
      设 total = 计算 {total} + {c1}
    结束
    设 e2 = 查一值 app.db subject_table_exists name=lesson_text
    如果 {e2} 大于 0
      设 c2 = 查一值表 app.db subject_use_lesson_text {q}
      设 total = 计算 {total} + {c2}
    结束
    设 e3 = 查一值 app.db subject_table_exists name=quiz_progress
    如果 {e3} 大于 0
      设 c3 = 查一值表 app.db subject_use_quiz_progress {q}
      设 total = 计算 {total} + {c3}
    结束
    设 e4 = 查一值 app.db subject_table_exists name=textbook_import_draft
    设 e5 = 查一值 app.db subject_table_exists name=textbook_import_task
    如果 {e4} 大于 0 且 {e5} 大于 0
      设 c4 = 查一值表 app.db subject_use_textbook_import_draft {q}
      设 total = 计算 {total} + {c4}
    结束
    返回 {"n": {total}}
  结束

  公开 函数 建科目 learner code name intro? kind? levels? current_role? auth_mode?
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理科目
    结束
    设 cd = {code 或}
    如果 {cd} 不为空
      设 cd = 替换 {cd} ^\s+|\s+$
    结束
    设 cm = 匹配 {cd} ^[a-z][a-z0-9_]*$
    设 ctail = 截取 {cd} 21
    如果 {cm.matched} 不等于 是 或 {ctail} 不为空
      报错 400 科目编码只能是小写字母开头的小写字母、数字、下划线，最长20
    结束
    如果 {cd} 等于 jp_grammar
      报错 400 jp_grammar 是日语科目的保留编码
    结束
    设 ex = 查一值 app.db subject_info_by_code code={cd}
    如果 {ex} 不为空
      报错 409 科目编码已存在
    结束
    设 nm = {name 或}
    如果 {nm} 不为空
      设 nm = 替换 {nm} ^\s+|\s+$
    结束
    如果 {nm} 为空
      报错 400 科目名称不能为空
    结束
    设 ntail = 截取 {nm} 41
    如果 {ntail} 不为空
      报错 400 科目名称最长40字
    结束
    设 kd = {kind 或 general}
    如果 {kd} 不等于 language 且 {kd} 不等于 general
      报错 400 类型只能是 language 或 general
    结束
    设 lv = {levels 或}
    如果 {lv} 不为空
      设 lv = 替换 {lv} ^\s+|\s+$
    结束
    如果 {lv} 为空
      如果 {kd} 等于 language
        设 lv = N5,N4,N3,N2,N1
      否则
        设 lv = 入门,基础,进阶
      结束
    否则
      设 lc = 调用 校验等级 levels={lv}
      设 lv = {lc.text}
    结束
    设 now = 当前时间
    设 row = {"code": "{cd}", "name": "{nm}", "intro": "{intro 或}", "kind": "{kd}", "levels": "{lv}", "owner": "{learner}", "now": "{now}"}
    事务 app.db
      如果 {kd} 等于 language
        设 n1 = 写库表 app.db subject_info_insert_language {row}
      否则
        设 n1 = 写库表 app.db subject_info_insert_general {row}
      结束
      设 sid = 查一值 app.db subject_info_by_code code={cd}
      设 n2 = 写库 app.db subject_teacher_insert subject_id={sid} teacher={learner} role=owner now={now}
    结束
    返回 {"id": {sid}, "code": "{cd}"}
  结束

  公开 函数 改科目 learner subject_id name? intro? levels? current_role? auth_mode?
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=settings current_role={current_role} auth_mode={auth_mode}
    设 si = 查一行 app.db subject_info_full id={subject_id}
    设 nm = {name 或}
    如果 {nm} 不为空
      设 nm = 替换 {nm} ^\s+|\s+$
    结束
    设 newname = {si.name}
    如果 {nm} 不为空
      设 ntail = 截取 {nm} 41
      如果 {ntail} 不为空
        报错 400 科目名称最长40字
      结束
      设 newname = {nm}
    结束
    设 newlv = {si.levels 或}
    设 lv = {levels 或}
    如果 {lv} 不为空
      设 lv = 替换 {lv} ^\s+|\s+$
    结束
    如果 {lv} 不为空
      设 lc = 调用 校验等级 levels={lv}
      设 newlv = {lc.text}
      设 oldlv = 调用 科目等级 subject_id={subject_id}
      设 nk = ,{newlv},
      遍历 x 于 {oldlv.levels}
        设 key = ,{x},
        如果 {nk} 不包含 {key}
          设 u = 调用 等级在用数 subject_id={subject_id} level={x}
          如果 {u.n} 大于 0
            报错 400 等级「{x}」还有{u.n}条记录在用，先改掉题目和课文的等级再删
          结束
        结束
      结束
    结束
    设 now = 当前时间
    设 row = {"id": "{subject_id}", "name": "{newname}", "intro": "{intro 或}", "levels": "{newlv}", "now": "{now}"}
    设 n = 写库表 app.db subject_info_update {row}
    返回 {"ok": 1}
  结束

  公开 函数 设科目可见性 learner subject_id visibility current_role? auth_mode?
    如果 {visibility} 不等于 public 且 {visibility} 不等于 private
      报错 400 可见性只能是 public 或 private
    结束
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=settings current_role={current_role} auth_mode={auth_mode}
    如果 {v.code} 等于 jp_grammar 且 {visibility} 等于 private
      报错 409 日语科目必须是公共科目
    结束
    如果 {visibility} 等于 private 且 {v.visibility} 等于 public
      设 fc = 查一值 app.db subject_student_foreign subject_id={subject_id}
      如果 {fc} 大于 0
        报错 409 还有其他教师分配的在册学生，不能改成私有
      结束
    结束
    设 now = 当前时间
    设 n = 写库 app.db subject_info_set_visibility visibility={visibility} now={now} id={subject_id}
    返回 {"ok": 1, "visibility": "{visibility}"}
  结束

  公开 函数 设科目状态 learner subject_id status current_role? auth_mode?
    如果 {status} 不等于 active 且 {status} 不等于 disabled
      报错 400 状态只能是 active 或 disabled
    结束
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=settings current_role={current_role} auth_mode={auth_mode}
    如果 {v.code} 等于 jp_grammar 且 {status} 等于 disabled
      报错 409 日语科目不能停用
    结束
    设 now = 当前时间
    设 n = 写库 app.db subject_info_set_status status={status} now={now} id={subject_id}
    返回 {"ok": 1, "status": "{status}"}
  结束

  公开 函数 列可管理科目 learner current_role? auth_mode?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理科目
    结束
    如果 {auth_mode} 等于 on
      设 rows = 查询 app.db subject_manage_list learner={learner}
    否则
      设 rows = 查询 app.db subject_manage_list_all
    结束
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "subjects": {rows}}
  结束

  公开 函数 列科目教师 subject_id
    设 si = 查一行 app.db subject_info_full id={subject_id}
    如果 {si} 为空
      返回 {"total": 0, "teachers": []}
    结束
    设 rows = 查询 app.db subject_teacher_list subject_id={subject_id}
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "teachers": {rows}}
  结束

  公开 函数 科目详情 learner subject_id current_role? auth_mode?
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=read current_role={current_role} auth_mode={auth_mode}
    设 si = 查一行 app.db subject_info_full id={subject_id}
    设 tl = 调用 列科目教师 subject_id={subject_id}
    设 st = 查询 app.db subject_student_all subject_id={subject_id}
    返回 {"id": {si.id}, "code": "{si.code}", "name": "{si.name}", "intro": "{si.intro 或}", "kind": "{si.kind}", "visibility": "{si.visibility}", "status": "{si.status}", "owner": "{si.owner}", "my_role": "{v.via}", "teachers": {tl.teachers}, "students": {st}}
  结束

  公开 函数 加科目教师 learner subject_id teacher role? current_role? auth_mode?
    设 tc = {teacher 或}
    如果 {tc} 不为空
      设 tc = 替换 {tc} ^\s+|\s+$
    结束
    如果 {tc} 为空
      报错 400 教师用户名不能为空
    结束
    设 rl = {role 或 editor}
    如果 {rl} 不等于 owner 且 {rl} 不等于 editor
      报错 400 角色只能是 owner 或 editor
    结束
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=settings current_role={current_role} auth_mode={auth_mode}
    设 tr = 查一值 app.db subject_teacher_role subject_id={subject_id} learner={tc}
    如果 {v.owner} 等于 {tc} 或 {tr} 不为空
      报错 409 该教师已在本科目
    结束
    设 now = 当前时间
    设 n = 写库 app.db subject_teacher_insert subject_id={subject_id} teacher={tc} role={rl} now={now}
    返回 {"ok": 1}
  结束

  公开 函数 改科目教师角色 learner subject_id teacher role current_role? auth_mode?
    如果 {role} 不等于 owner 且 {role} 不等于 editor
      报错 400 角色只能是 owner 或 editor
    结束
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=settings current_role={current_role} auth_mode={auth_mode}
    如果 {teacher} 不为空 且 {v.owner} 等于 {teacher}
      报错 409 科目创建者始终是负责人
    结束
    设 tr = 查一值 app.db subject_teacher_role subject_id={subject_id} learner={teacher}
    如果 {tr} 为空
      报错 404 该教师不在本科目
    结束
    如果 {role} 等于 editor 且 {tr} 等于 owner
      设 c = 调用 负责人数 subject_id={subject_id} except={teacher}
      如果 {c.n} 等于 0
        报错 409 不能去掉最后一个负责人
      结束
    结束
    设 n = 写库 app.db subject_teacher_update_role subject_id={subject_id} teacher={teacher} role={role}
    返回 {"ok": 1}
  结束

  公开 函数 移除科目教师 learner subject_id teacher current_role? auth_mode?
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=settings current_role={current_role} auth_mode={auth_mode}
    如果 {teacher} 不为空 且 {v.owner} 等于 {teacher}
      报错 409 科目创建者不能移除
    结束
    设 tr = 查一值 app.db subject_teacher_role subject_id={subject_id} learner={teacher}
    如果 {tr} 为空
      报错 404 该教师不在本科目
    结束
    如果 {tr} 等于 owner
      设 c = 调用 负责人数 subject_id={subject_id} except={teacher}
      如果 {c.n} 等于 0
        报错 409 不能移除最后一个负责人
      结束
    结束
    设 n = 写库 app.db subject_teacher_delete subject_id={subject_id} teacher={teacher}
    返回 {"ok": 1}
  结束

  公开 函数 分配学生 learner subject_id learners current_role? auth_mode?
    设 ls = {learners 或}
    如果 {ls} 为空
      报错 400 请选择要分配的学生
    结束
    设 hm = 匹配 {ls} [^,\s]
    如果 {hm.matched} 不等于 是
      报错 400 请选择要分配的学生
    结束
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=assign current_role={current_role} auth_mode={auth_mode}
    如果 {v.status} 等于 disabled
      报错 409 科目已停用，不能分配学生
    结束
    设 parts = 按正则切分 {ls} ,
    设 now = 当前时间
    设 assigned = 0
    设 reactivated = 0
    设 skipped = 0
    设 seen = ,
    事务 app.db
      遍历 x 于 {parts}
        如果 {x} 为空
          继续
        结束
        设 s = 替换 {x} ^\s+|\s+$
        如果 {s} 为空
          继续
        结束
        设 key = ,{s},
        如果 {seen} 包含 {key}
          继续
        结束
        设 seen = {seen}{s},
        设 sr = 查一行 app.db subject_student_row subject_id={subject_id} learner={s}
        如果 {sr} 为空
          设 n = 写库 app.db subject_student_assign_insert subject_id={subject_id} learner={s} by={learner} now={now}
          设 assigned = 计算 {assigned} + 1
        否则如果 {sr.status} 等于 revoked
          设 n = 写库 app.db subject_student_reactivate subject_id={subject_id} learner={s} by={learner}
          设 reactivated = 计算 {reactivated} + 1
        否则
          设 skipped = 计算 {skipped} + 1
        结束
      结束
    结束
    返回 {"assigned": {assigned}, "reactivated": {reactivated}, "skipped": {skipped}}
  结束

  公开 函数 撤销学生 learner subject_id student current_role? auth_mode?
    设 sd = {student 或}
    如果 {sd} 不为空
      设 sd = 替换 {sd} ^\s+|\s+$
    结束
    如果 {sd} 为空
      报错 400 学生用户名不能为空
    结束
    设 v = 调用 管理校验 learner={learner} subject_id={subject_id} need=assign current_role={current_role} auth_mode={auth_mode}
    设 sr = 查一行 app.db subject_student_row subject_id={subject_id} learner={sd}
    如果 {sr} 为空
      报错 404 该学生不在本科目
    结束
    如果 {sr.status} 不等于 active
      报错 404 该学生不在本科目
    结束
    如果 {v.via} 等于 public 且 {sr.assigned_by} 不等于 {learner}
      报错 403 只能撤销自己分配的学生
    结束
    设 n = 写库 app.db subject_student_revoke subject_id={subject_id} learner={sd}
    返回 {"ok": 1}
  结束

  公开 函数 科目老师设定 subject_id
    设 sid = {subject_id 或}
    设 mm = 匹配 {sid} ^[0-9]+$
    如果 {mm.matched} 不等于 是
      设 sid = 1
    结束
    设 si = 查一行 app.db subject_info_full id={sid}
    设 raw = 查一值 app.db subject_ai_persona subject_id={sid}
    设 custom = {raw 或}
    如果 {custom} 不为空
      设 custom = 替换 {custom} ^\s+|\s+$
    结束
    设 jp = 0
    如果 {sid} 等于 1 或 {si} 为空
      设 jp = 1
    结束
    设 nm = 日语语法
    如果 {si} 不为空
      设 nm = {si.name}
    结束
    如果 {custom} 不为空
      设 ps = 替换 {custom} [。！；，.!;,\s]+$
    否则如果 {jp} 等于 1
      设 ps = 你是一位中文老师，教中文学习者日语语法
    否则
      设 ps = 你是一位{nm}老师，用中文给学生讲解{nm}
    结束
    如果 {jp} 等于 1
      设 ot = 学生闲聊、与日语学习无关时，简短自然地回应，不要强行讲语法
      设 pw = 语法点
      设 ew = 语法讲解
    否则
      设 ot = 学生闲聊、与{nm}无关时，简短自然地回应，不要硬拉回{nm}；学生问的是别的科目的内容时，不要拒答，简短回答要点，并提醒可以在顶栏切换到对应科目再细问
      设 pw = 知识点
      设 ew = 讲解
    结束
    返回 {"name": "{nm}", "custom": "{custom}", "persona": "{ps}", "offtopic": "{ot}", "point_word": "{pw}", "explain_word": "{ew}"}
  结束

  公开 函数 科目助手设定 subject_id
    设 sid = {subject_id 或}
    设 mm = 匹配 {sid} ^[0-9]+$
    如果 {mm.matched} 不等于 是
      设 sid = 1
    结束
    设 si = 查一行 app.db subject_info_full id={sid}
    设 raw = 查一值 app.db subject_ai_assist_prompt subject_id={sid}
    设 custom = {raw 或}
    如果 {custom} 不为空
      设 custom = 替换 {custom} ^\s+|\s+$
    结束
    设 lvs = 调用 科目等级 subject_id={sid}
    设 lt = {zz 或}
    遍历 x 于 {lvs.levels}
      如果 {lt} 为空
        设 lt = {x}
      否则
        设 lt = {lt}、{x}
      结束
    结束
    设 jp = 0
    如果 {sid} 等于 1 或 {si} 为空
      设 jp = 1
    结束
    设 nm = 日语语法
    设 kd = language
    如果 {si} 不为空
      设 nm = {si.name}
      设 kd = {si.kind}
    结束
    如果 {jp} 等于 1
      设 sy = 日语学习系统
      设 pd = 知识点或语法条目
      设 tp = 这个语法、这个点
      设 pn = 编号前缀（非日语科目必须以它开头）
    否则
      设 sy = {nm}学习系统
      设 pd = 知识点或条目
      设 tp = 这个知识点、这个点
      设 pn = 编号前缀（本科目的编号必须以它开头）
    结束
    如果 {custom} 不为空
      设 it = 替换 {custom} [。！；，.!;,\s]+$
    否则
      设 it = 你是{sy}教师端的教学助手
    结束
    设 et = 【示例】
    如果 {jp} 等于 1 或 {kd} 等于 language
      设 et = 【例句】
    结束
    返回 {"name": "{nm}", "kind": "{kd}", "levels": "{lt}", "custom": "{custom}", "system": "{sy}", "intro": "{it}", "point_desc": "{pd}", "this_point": "{tp}", "prefix_note": "{pn}", "example_tag": "{et}"}
  结束

  函数 存科目人设 learner subject_id persona
    设 np = {persona 或}
    如果 {np} 不为空
      设 np = 替换 {np} ^\s+|\s+$
    结束
    设 cur = 查一值 app.db subject_ai_persona subject_id={subject_id}
    设 cp = {cur 或}
    如果 {cp} 不为空
      设 cp = 替换 {cp} ^\s+|\s+$
    结束
    设 same = 相等 {np} {cp}
    如果 {same} 等于 是
      返回 {"changed": 0}
    结束
    设 now = 当前时间
    设 row = {"subject_id": "{subject_id}", "persona": "{np}", "learner": "{learner}", "now": "{now}"}
    设 n = 写库表 app.db subject_ai_upsert {row}
    返回 {"changed": 1}
  结束

  公开 函数 科目管理页面 learner current_role? auth_mode?
    设 lm = 调用 列可管理科目 learner={learner} current_role={current_role} auth_mode={auth_mode}
    如果 {auth_mode} 等于 on
      设 rows = 查询 app.db subject_page_rows learner={learner}
    否则
      设 rows = 查询 app.db subject_page_rows_all
    结束
    返回 {"subjects": {rows}, "manage_head": "我能管理的科目共{lm.total}个", "can_create": 1}
  结束

  公开 函数 载入科目页面 learner subj_id? current_role? auth_mode?
    如果 {subj_id} 为空
      返回 {"subj_id": "", "subj_code": "", "subj_name": "", "subj_intro": "", "subj_kind": "通用", "subj_levels": "", "subj_persona": ""}
    结束
    设 v = 调用 管理校验 learner={learner} subject_id={subj_id} need=settings current_role={current_role} auth_mode={auth_mode}
    设 si = 查一行 app.db subject_info_full id={subj_id}
    设 kd = 通用
    如果 {si.kind} 等于 language
      设 kd = 语言
    结束
    设 lvs = 调用 科目等级 subject_id={subj_id}
    设 pr = 查一值 app.db subject_ai_persona subject_id={subj_id}
    返回 {"subj_id": {si.id}, "subj_code": "{si.code}", "subj_name": "{si.name}", "subj_intro": "{si.intro 或}", "subj_kind": "{kd}", "subj_levels": "{lvs.text}", "subj_persona": "{pr 或}"}
  结束

  公开 函数 保存科目页面 learner subj_name subj_id? subj_code? subj_intro? subj_kind? subj_levels? subj_persona? current_role? auth_mode?
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    设 pp = {subj_persona 或}
    如果 {pp} 不为空
      设 pp = 替换 {pp} ^\s+|\s+$
    结束
    设 ptail = 截取 {pp} 2001
    如果 {ptail} 不为空
      报错 400 AI老师设定最长2000字
    结束
    设 kd = {subj_kind 或}
    如果 {kd} 为空 或 {kd} 等于 通用
      设 kd = general
    否则如果 {kd} 等于 语言
      设 kd = language
    结束
    如果 {subj_id} 为空
      设 cr = 调用 建科目 learner={learner} code={subj_code} name={subj_name} intro={subj_intro} kind={kd} levels={subj_levels} current_role={current_role} auth_mode={auth_mode}
      设 sp = 调用 存科目人设 learner={learner} subject_id={cr.id} persona={pp}
    否则
      设 ed = 调用 改科目 learner={learner} subject_id={subj_id} name={subj_name} intro={subj_intro} levels={subj_levels} current_role={current_role} auth_mode={auth_mode}
      设 sp = 调用 存科目人设 learner={learner} subject_id={subj_id} persona={pp}
    结束
    设 pg = 调用 科目管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode}
    返回 {pg}
  结束

  公开 函数 设科目可见性页面 learner subj_id visibility current_role? auth_mode?
    设 r = 调用 设科目可见性 learner={learner} subject_id={subj_id} visibility={visibility} current_role={current_role} auth_mode={auth_mode}
    设 pg = 调用 科目管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode}
    返回 {pg}
  结束

  公开 函数 设科目状态页面 learner subj_id status current_role? auth_mode?
    设 r = 调用 设科目状态 learner={learner} subject_id={subj_id} status={status} current_role={current_role} auth_mode={auth_mode}
    设 pg = 调用 科目管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode}
    返回 {pg}
  结束

  公开 函数 译文 tbl row_key field lang
    如果 {lang} 不等于 ja
      返回 {"text": ""}
    结束
    设 te = 查一值 app.db subject_table_exists name=subject_content_translation
    如果 {te} 不大于 0
      返回 {"text": ""}
    结束
    设 tx = 查一值 app.db subject_content_translation_text tbl={tbl} row_key={row_key} field={field} lang={lang}
    设 t = {tx 或}
    返回 {"text": "{t}"}
  结束

  公开 函数 取界面语言 username
    设 ev = 查一值 app.db subject_table_exists name=account_user
    如果 {ev} 不大于 0
      返回 {"lang": "zh"}
    结束
    设 lg = 查一值 app.db subject_user_lang username={username}
    设 lv = {lg 或 zh}
    返回 {"lang": "{lv}"}
  结束
结束
