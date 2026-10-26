业务 teacher_rules
  依赖 account
  用包 common db text

  公开 函数 列设定 kind? student?
    # 返回 {items, total}，items 每项 {id, kind, student, keywords, content, enabled, once, version, author, updated_at}，按 id 升序
    # 读 teacher_rules_setting 全部行
    # kind 不为空时只留 kind 相等的行
    # student 不为空时只留 student 等于它或 student 为空（全班）的行
    # 返回 {"items": 行列表, "total": 行数}
    设 rows = 查询 app.db teacher_rules_setting_list kind={kind} student={student}
    设 n = 查一值 app.db teacher_rules_setting_count kind={kind} student={student}
    设 out.items = {rows}
    设 out.total = {n}
    返回 {out}
  结束

  公开 函数 取设定 setting_id
    # 返回 {id, kind, student, keywords, content, enabled, once, version, author, updated_at}
    # 报错 404 没有这条设定
    # 按 id 查 teacher_rules_setting，查不到报错 404 没有这条设定
    # 返回这一行
    设 p = 查一行 app.db teacher_rules_setting_get id={setting_id}
    如果 {p.id 或} 为空
      报错 404 没有这条设定
    结束
    返回 {p}
  结束

  公开 函数 保存设定 kind content current_user setting_id? student? keywords? once?
    # 返回 {id, kind, student, keywords, content, enabled, once, version}
    # 报错 400 种类只能是 memory、note、card
    # 报错 400 内容必填
    # 报错 404 没有这条设定
    # kind 不是 memory、note、card 之一，报错 400 种类只能是 memory、note、card
    # content 去掉首尾空白后为空，报错 400 内容必填
    # 规整 keywords：全角逗号、顿号、空白全部换成半角逗号，连续逗号合并为一个，去掉首尾逗号
    # once_val：kind 等于 note 且 once 等于 1 时为 1，否则为 0
    # setting_id 为空：往 teacher_rules_setting 插入一行 (kind, student, keywords, content, enabled=1, once=once_val, version=1, author=current_user, updated_at=当前时间)
    # setting_id 不为空：按 id 查旧行，查不到报错 404 没有这条设定；新 version = 旧 content 与新 content 不同时旧 version + 1，否则不变；更新该行的 kind, student, keywords, content, once, version, author=current_user, updated_at=当前时间，不改 enabled
    # 返回保存后的这一行
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
      设 args.kind = {kind}
      设 args.student = {student}
      设 args.keywords = {kw}
      设 args.content = {content}
      设 args.once = {once_val}
      设 args.author = {current_user}
      设 n = 写库表 app.db teacher_rules_setting_insert {args}
      设 sid = 查一值 app.db teacher_rules_setting_last_id
    否则
      设 old = 查一行 app.db teacher_rules_setting_get id={setting_id}
      如果 {old.id 或} 为空
        报错 404 没有这条设定
      结束
      设 args.id = {setting_id}
      设 args.kind = {kind}
      设 args.student = {student}
      设 args.keywords = {kw}
      设 args.content = {content}
      设 args.once = {once_val}
      设 args.author = {current_user}
      设 n = 写库表 app.db teacher_rules_setting_update {args}
      设 sid = {setting_id}
    结束
    设 p = 查一行 app.db teacher_rules_setting_get id={sid}
    返回 {p}
  结束

  公开 函数 设置设定启用 setting_id enabled
    # 返回 {id, enabled, version}
    # 报错 400 enabled 只能是 0 或 1
    # 报错 404 没有这条设定
    # enabled 不是 0 也不是 1，报错 400 enabled 只能是 0 或 1
    # 按 id 查 teacher_rules_setting，查不到报错 404 没有这条设定
    # 旧 enabled 为 0 且新 enabled 为 1 时 version 加 1（重新启用等于重新可用），否则 version 不变
    # 更新 enabled, version, updated_at=当前时间
    # 返回 {"id": id, "enabled": enabled, "version": version}
    如果 {enabled 或 none} 不等于 0 且 {enabled 或 none} 不等于 1
      报错 400 enabled 只能是 0 或 1
    结束
    设 old = 查一行 app.db teacher_rules_setting_get id={setting_id}
    如果 {old.id 或} 为空
      报错 404 没有这条设定
    结束
    设 n = 写库 app.db teacher_rules_setting_set_enabled id={setting_id} enabled={enabled}
    设 p = 查一行 app.db teacher_rules_setting_enabled_view id={setting_id}
    返回 {p}
  结束

  公开 函数 删除设定 setting_id
    # 返回 {ok}
    # 报错 404 没有这条设定
    # 按 id 查 teacher_rules_setting，查不到报错 404 没有这条设定
    # 删除该行（teacher_rules_setting_use 里的历史记录保留）
    # 返回 {"ok": 1}
    设 old = 查一行 app.db teacher_rules_setting_get id={setting_id}
    如果 {old.id 或} 为空
      报错 404 没有这条设定
    结束
    设 n = 写库 app.db teacher_rules_setting_delete id={setting_id}
    返回 {"ok": 1}
  结束

  公开 函数 取生效设定 student recent_text?
    # 返回 {memory_text, note_text, card_text, setting_ids, setting_versions, count}；三段文本是各自生效设定的内容用换行连接；setting_ids、setting_versions 是按 memory、note、card 顺序（同种类内全班在前、个人在后、同组按 id 升序）排好的编号和版本号，半角逗号隔开；count 是生效的设定条数。只读，不写库，供老师预览提示词和问老师拼提示词用
    # 读 teacher_rules_setting 中 enabled 等于 1 且（student 为空 或 student 等于入参 student）的行，排序：全班（student 为空）在前，个人在后，同组按 id 升序
    # memory 行：全部生效
    # note 行：once 等于 0 的生效；once 等于 1 的，读 teacher_rules_setting_use 中该 student 的所有行，把 setting_ids 与 setting_versions 按位置配对，若有配对 (设定 id, 设定当前 version) 完全相同说明已用过，不生效，否则生效
    # card 行：keywords 不为空且 recent_text 包含其中任意一个关键词才生效（recent_text 为空则都不生效）
    # 按 memory、note、card 顺序汇总，拼出三段文本、setting_ids、setting_versions、count
    # 返回 {"memory_text": …, "note_text": …, "card_text": …, "setting_ids": …, "setting_versions": …, "count": …}
    设 args.student = {student}
    设 args.recent = {recent_text}
    设 p = 查一行表 app.db teacher_rules_setting_effective {args}
    返回 {p}
  结束

  公开 函数 记回复用到设定 reply_id student setting_ids setting_versions
    # 返回 {ok, recorded}，recorded 为 1 表示写了一行，0 表示没有用到设定
    # 报错 400 设定编号与版本号个数不一致
    # setting_ids 为空：返回 {"ok": 1, "recorded": 0}，不写库
    # setting_ids 与 setting_versions 按逗号拆开后个数不同，报错 400 设定编号与版本号个数不一致
    # 往 teacher_rules_setting_use 插入一行 (reply_id, student, setting_ids, setting_versions, at=当前时间)；调用方（问老师）在写回复的同一个事务里调用本函数，这样与回复一起成败
    # 返回 {"ok": 1, "recorded": 1}
    如果 {setting_ids} 为空
      返回 {"ok": 1, "recorded": 0}
    结束
    设 bad = 查一值 app.db teacher_rules_pair_mismatch a={setting_ids} b={setting_versions}
    如果 {bad} 等于 1
      报错 400 设定编号与版本号个数不一致
    结束
    设 n = 写库 app.db teacher_rules_setting_use_insert reply_id={reply_id} student={student} setting_ids={setting_ids} setting_versions={setting_versions}
    返回 {"ok": 1, "recorded": 1}
  结束

  公开 函数 列传达
    # 返回 {items, total}，items 每项 {id, urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled, author, updated_at}，按 id 升序
    # 读 teacher_rules_relay 全部行，返回 {"items": 行列表, "total": 行数}
    设 rows = 查询 app.db teacher_rules_relay_list
    设 n = 查一值 app.db teacher_rules_relay_count
    设 out.items = {rows}
    设 out.total = {n}
    返回 {out}
  结束

  公开 函数 取传达 relay_id
    # 返回 {id, urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled, author, updated_at}（facts、keywords 可空取空串）
    # 报错 404 没有这条传达
    # 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
    # 返回这一行
    设 p = 查一行 app.db teacher_rules_relay_get id={relay_id}
    如果 {p.id 或} 为空
      报错 404 没有这条传达
    结束
    返回 {p}
  结束

  公开 函数 保存传达 urgency must_info rounds current_user relay_id? tone? deadline? student? facts? keywords?
    # 返回 {id, urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled}（facts、keywords 可空取空串）
    # 报错 400 紧急程度只能是 low、normal 或 urgent
    # 报错 400 必须准确的信息必填
    # 报错 400 轮数必须是不小于 1 的整数
    # 报错 400 截止日格式应为 YYYY-MM-DD
    # 报错 404 没有这条传达
    # urgency 不是 low、normal、urgent 之一，报错 400 紧急程度只能是 low、normal 或 urgent
    # must_info 去掉首尾空白后为空，报错 400 必须准确的信息必填
    # rounds 不是整数或小于 1，报错 400 轮数必须是不小于 1 的整数
    # deadline 不为空且不是 YYYY-MM-DD 格式，报错 400 截止日格式应为 YYYY-MM-DD
    # relay_id 为空：往 teacher_rules_relay 插入一行 (urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled=1, author=current_user, updated_at=当前时间)，facts、keywords 原样存不规整
    # relay_id 不为空：按 id 查，查不到报错 404 没有这条传达；更新 urgency, tone, must_info, facts, keywords, rounds, deadline, student, author=current_user, updated_at=当前时间，不改 enabled，不动已有的 teacher_rules_relay_state
    # 返回保存后的这一行
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
      设 args.urgency = {urgency}
      设 args.tone = {tone}
      设 args.must_info = {must_info}
      设 args.rounds = {rounds}
      设 args.deadline = {deadline}
      设 args.student = {student}
      设 args.facts = {facts}
      设 args.keywords = {keywords}
      设 args.author = {current_user}
      设 n = 写库表 app.db teacher_rules_relay_insert {args}
      设 rid = 查一值 app.db teacher_rules_relay_last_id
    否则
      设 old = 查一行 app.db teacher_rules_relay_get id={relay_id}
      如果 {old.id 或} 为空
        报错 404 没有这条传达
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
      设 n = 写库表 app.db teacher_rules_relay_update {args}
      设 rid = {relay_id}
    结束
    设 p = 查一行 app.db teacher_rules_relay_get id={rid}
    返回 {p}
  结束

  公开 函数 设置传达启用 relay_id enabled
    # 返回 {id, enabled}
    # 报错 400 enabled 只能是 0 或 1
    # 报错 404 没有这条传达
    # enabled 不是 0 也不是 1，报错 400 enabled 只能是 0 或 1
    # 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
    # 更新 enabled 和 updated_at=当前时间
    # 返回 {"id": id, "enabled": enabled}
    如果 {enabled 或 none} 不等于 0 且 {enabled 或 none} 不等于 1
      报错 400 enabled 只能是 0 或 1
    结束
    设 old = 查一行 app.db teacher_rules_relay_get id={relay_id}
    如果 {old.id 或} 为空
      报错 404 没有这条传达
    结束
    设 n = 写库 app.db teacher_rules_relay_set_enabled id={relay_id} enabled={enabled}
    设 p = 查一行 app.db teacher_rules_relay_enabled_view id={relay_id}
    返回 {p}
  结束

  公开 函数 删除传达 relay_id
    # 返回 {ok}
    # 报错 404 没有这条传达
    # 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
    # 在一个事务里：删除 teacher_rules_relay 该行，并删除 teacher_rules_relay_state 里 relay_id 相同的行（teacher_rules_relay_use 的历史记录保留）
    # 返回 {"ok": 1}
    设 old = 查一行 app.db teacher_rules_relay_get id={relay_id}
    如果 {old.id 或} 为空
      报错 404 没有这条传达
    结束
    事务 app.db
      设 n1 = 写库 app.db teacher_rules_relay_delete id={relay_id}
      设 n2 = 写库 app.db teacher_rules_relay_state_delete_by_relay relay_id={relay_id}
    结束
    返回 {"ok": 1}
  结束

  公开 函数 对学生发传达 relay_id student
    # 返回 {ok, relay_id, student}
    # 报错 404 没有这条传达
    # 报错 400 传达已停用
    # 报错 400 这条传达不是发给该学生的
    # 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
    # enabled 等于 0，报错 400 传达已停用
    # 传达的 student 不为空且不等于入参 student，报错 400 这条传达不是发给该学生的
    # 查 teacher_rules_relay_state 中 (relay_id, student)：没有则插入 (rounds_done=0, finished=0, confirmed=0, updated_at=当前时间)；有则把 rounds_done、finished、confirmed 都重置为 0 并更新 updated_at（让该学生重新开始接收这条传达）
    # 返回 {"ok": 1, "relay_id": relay_id, "student": student}
    设 r = 查一行 app.db teacher_rules_relay_get id={relay_id}
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

  公开 函数 列传达状态 student?
    # 返回 {items, total}，items 每项 {relay_id, student, must_info, rounds, rounds_done, finished, confirmed}，按 relay_id、student 升序，供学情页和老师设定页展示
    # 读 teacher_rules_relay_state 并按 relay_id 关联 teacher_rules_relay 取 must_info 和 rounds（传达已被删的状态行已随删除清掉）
    # student 不为空时只留该 student 的行
    # 返回 {"items": 列表, "total": 行数}
    设 rows = 查询 app.db teacher_rules_relay_state_list student={student}
    设 n = 查一值 app.db teacher_rules_relay_state_count student={student}
    设 out.items = {rows}
    设 out.total = {n}
    返回 {out}
  结束

  公开 函数 取待传达 student
    # 返回 {relay_ids, prompt_text, count}；relay_ids 是需要在这条回复里带上的传达编号，半角逗号隔开，按紧急程度排（urgent 在前、normal 次之、low 最后，顺便=最低优先，同档按 id 升序）；prompt_text 每条传达一行，格式「[传达#编号] 紧急:{中文紧急程度} 口吻:tone 必须准确:must_info」，facts 不为空时接「 原样说对:{facts}」，keywords 不为空时接「 沾边提示:{keywords}」，最后接「 截止:deadline」（可空，空就是「截止:」后面没有字），多行用换行连接；count 是条数；中文紧急程度 urgent→立即、normal→尽快、low→顺便
    # 读 teacher_rules_relay 中 enabled 等于 1 且（student 为空 或 student 等于入参 student）的行，排序 urgent 在前、normal 次之、low 在后（顺便=最低优先，参照旧 kg scripts 的口径），同档按 id 升序
    # 取运行时的当前日期 today（YYYY-MM-DD，不写死具体日期）；去掉 deadline 不为空且小于 today 的（已过截止日不再传）
    # 查 teacher_rules_relay_state 的 (relay_id, student)：存在且 finished 等于 1 的去掉
    # 剩下的拼出 relay_ids、prompt_text、count 返回；没有则 {"relay_ids": "", "prompt_text": "", "count": 0}
    设 today = 当前时间 日期
    设 p = 查一行 app.db teacher_rules_relay_pending student={student} today={today}
    返回 {p}
  结束

  公开 函数 记回复传达 reply_id student relay_ids
    # 返回 {ok, recorded}，recorded 为 1 表示写了一行，0 表示没带传达
    # 报错 404 没有这条传达
    # relay_ids 为空：返回 {"ok": 1, "recorded": 0}，不写库
    # relay_ids 按逗号拆开，其中任一编号在 teacher_rules_relay 查不到，报错 404 没有这条传达
    # 在一个事务里：往 teacher_rules_relay_use 插入一行 (reply_id, student, relay_ids, at=当前时间)；对每个编号，在 teacher_rules_relay_state 里找 (relay_id, student)，没有则插入 rounds_done=1，有则 rounds_done 加 1；若 rounds_done 不小于该传达的 rounds 则 finished=1；confirmed 保持原值，新建为 0；更新 updated_at
    # 返回 {"ok": 1, "recorded": 1}
    如果 {relay_ids} 为空
      返回 {"ok": 1, "recorded": 0}
    结束
    设 miss = 查一值 app.db teacher_rules_relay_missing_count ids={relay_ids}
    如果 {miss} 大于 0
      报错 404 没有这条传达
    结束
    事务 app.db
      设 n1 = 写库 app.db teacher_rules_relay_use_insert reply_id={reply_id} student={student} relay_ids={relay_ids}
      设 n2 = 写库 app.db teacher_rules_relay_state_bump ids={relay_ids} student={student}
      设 n3 = 写库 app.db teacher_rules_relay_state_insert_first ids={relay_ids} student={student}
    结束
    返回 {"ok": 1, "recorded": 1}
  结束

  公开 函数 记传达判定 student relay_id delivered
    # 返回 {ok, relay_id, student, confirmed, finished}
    # 报错 400 delivered 只能是 0 或 1
    # 报错 404 没有这条传达
    # 报错 404 没有传达状态
    # delivered 不是 0 也不是 1，报错 400 delivered 只能是 0 或 1
    # 按 relay_id 查 teacher_rules_relay，查不到报错 404 没有这条传达
    # 查 teacher_rules_relay_state 的 (relay_id, student)，查不到报错 404 没有传达状态
    # delivered 等于 1 时，把该状态行 confirmed 设为 1、finished 设为 1，更新 updated_at；等于 0 时不改状态
    # 返回该状态行的 {"ok": 1, "relay_id": …, "student": …, "confirmed": …, "finished": …}
    如果 {delivered 或 none} 不等于 0 且 {delivered 或 none} 不等于 1
      报错 400 delivered 只能是 0 或 1
    结束
    设 r = 查一行 app.db teacher_rules_relay_get id={relay_id}
    如果 {r.id 或} 为空
      报错 404 没有这条传达
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

  公开 函数 设定列表 student?
    设 rows = 查询 app.db teacher_rules_note_rows student={student}
    设 tv = 替换 文本=xtruex 正则=x
    设 fv = 替换 文本=xfalsex 正则=x
    设 out = 解析JSON []
    遍历 row 于 {rows}
      如果 {row.note_once} 等于 1
        设 row.note_once = {tv}
      否则
        设 row.note_once = {fv}
      结束
      设 out = 列表加项 {out} {row}
    结束
    返回 {out}
  结束

  公开 函数 传达列表 student?
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
    设 rows = 查询 app.db teacher_rules_relay_rows student={student} today={today} studs={studs} total={total}
    返回 {rows}
  结束

  公开 函数 传达状态列表
    设 today = 当前时间 日期
    设 studs = ,
    设 st = 调用 account.列学生
    遍历 u 于 {st.students}
      设 studs = {studs},{u.username}
    结束
    设 names = 查询 app.db teacher_rules_sorted_names studs={studs}
    设 rels = 查询 app.db teacher_rules_relay_list
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

  公开 函数 取回复用到 reply_id
    设 a = 查一值 app.db teacher_rules_reply_setting_text reply_id={reply_id}
    设 b = 查一值 app.db teacher_rules_reply_relay_text reply_id={reply_id}
    设 text = {a 或}
    如果 {a 或} 不为空 且 {b 或} 不为空
      设 text = {a}、{b}
    否则如果 {b 或} 不为空
      设 text = {b}
    结束
    设 out.text = {text}
    返回 {out}
  结束

  公开 函数 设定首页页面
    设 notes = 调用 设定列表
    设 relays = 调用 传达列表
    设 states = 调用 传达状态列表
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
    返回 {out}
  结束

  公开 函数 载入设定页面 note_id? student?
    如果 {note_id} 为空
      返回 {"student": "{student}", "note_kind": "记忆", "note_keywords": "", "note_content": "", "note_once": "false"}
    结束
    设 p = 调用 取设定 setting_id={note_id}
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

  公开 函数 保存设定页面 note_content current_user note_kind? note_id? student? note_keywords? note_once?
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
      设 old = 调用 取设定 setting_id={note_id}
      如果 {old.student 或 _} 不等于 {student 或 _}
        报错 404 没有这条设定
      结束
    结束
    设 once_v = 0
    设 raw_once = {note_once 或 0}
    如果 {raw_once} 等于 是 或 {raw_once} 等于 True 或 {raw_once} 等于 true 或 {raw_once} 等于 TRUE 或 {raw_once} 等于 1
      设 once_v = 1
    结束
    设 saved = 调用 保存设定 kind={kind_v} content={note_content} current_user={current_user} setting_id={note_id} student={student} keywords={note_keywords} once={once_v}
    设 notes = 调用 设定列表 student={student}
    如果 {student} 为空
      设 out.class_notes = {notes}
    否则
      设 out.student_notes = {notes}
    结束
    返回 {out}
  结束

  公开 函数 设置设定启用页面 note_id enabled student?
    设 old = 调用 取设定 setting_id={note_id}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条设定
    结束
    设 u = 调用 设置设定启用 setting_id={note_id} enabled={enabled}
    设 notes = 调用 设定列表 student={student}
    如果 {student} 为空
      设 out.class_notes = {notes}
    否则
      设 out.student_notes = {notes}
    结束
    返回 {out}
  结束

  公开 函数 删除设定页面 note_id student?
    设 old = 调用 取设定 setting_id={note_id}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条设定
    结束
    设 u = 调用 删除设定 setting_id={note_id}
    设 notes = 调用 设定列表 student={student}
    如果 {student} 为空
      设 out.class_notes = {notes}
    否则
      设 out.student_notes = {notes}
    结束
    返回 {out}
  结束

  公开 函数 设定预览页面 preview_student preview_message
    如果 {preview_student} 为空
      报错 400 先选一个学生
    结束
    如果 {preview_message} 为空
      报错 400 输一句示例提问
    结束
    设 ra = {blank 或}
    设 ex = 查一值 app.db teacher_rules_tutor_exists
    如果 {ex} 大于 0
      设 ra = 查一值 app.db teacher_rules_recent_asks learner={preview_student}
    结束
    设 recent_text = 查一值 app.db teacher_rules_text_join a={ra} b={preview_message}
    设 eff = 调用 取生效设定 student={preview_student} recent_text={recent_text}
    设 pend = 调用 取待传达 student={preview_student}
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
    设 hits = 查询 app.db teacher_rules_hit_cards student={preview_student} recent={recent_text}
    设 pv.ids = {ids}
    设 pv.relay_pick = {relay_pick}
    设 pv.layout = {layout}
    设 out.preview = {pv}
    设 out.preview_hits = {hits}
    返回 {out}
  结束

  公开 函数 载入传达页面 relay_id? student?
    如果 {relay_id} 为空
      返回 {"student": "{student}", "relay_point": "", "relay_urgency": "尽快", "relay_voice": "以老师名义", "relay_facts": "", "relay_keywords": "", "relay_rounds": 3, "relay_due": ""}
    结束
    设 p = 调用 取传达 relay_id={relay_id}
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
    设 out.relay_due = {p.deadline 或}
    返回 {out}
  结束

  公开 函数 保存传达页面 relay_point current_user relay_id? student? relay_urgency? relay_voice? relay_facts? relay_keywords? relay_rounds? relay_due?
    如果 {student} 不为空
      设 acc = 调用 account.取账号 username={student}
      如果 {acc.username 或} 为空 或 {acc.role 或 _} 不等于 student
        报错 404 没有这个学生
      结束
    结束
    如果 {relay_id} 不为空
      设 old = 调用 取传达 relay_id={relay_id}
      如果 {old.student 或 _} 不等于 {student 或 _}
        报错 404 没有这条传达
      结束
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
    设 saved = 调用 保存传达 urgency={urg} must_info={relay_point} rounds={rounds_v} current_user={current_user} relay_id={relay_id} tone={relay_voice} deadline={relay_due} student={student} facts={relay_facts} keywords={relay_keywords}
    如果 {student} 为空
      设 rl = 调用 传达列表
      设 rs = 调用 传达状态列表
      设 out.class_relays = {rl}
      设 out.class_relay_states = {rs}
    否则
      设 rl = 调用 传达列表 student={student}
      设 out.student_relays = {rl}
    结束
    返回 {out}
  结束

  公开 函数 设置传达启用页面 relay_id enabled student?
    设 old = 调用 取传达 relay_id={relay_id}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条传达
    结束
    设 u = 调用 设置传达启用 relay_id={relay_id} enabled={enabled}
    如果 {student} 为空
      设 rl = 调用 传达列表
      设 rs = 调用 传达状态列表
      设 out.class_relays = {rl}
      设 out.class_relay_states = {rs}
    否则
      设 rl = 调用 传达列表 student={student}
      设 out.student_relays = {rl}
    结束
    返回 {out}
  结束

  公开 函数 删除传达页面 relay_id student?
    设 old = 调用 取传达 relay_id={relay_id}
    如果 {old.student 或 _} 不等于 {student 或 _}
      报错 404 没有这条传达
    结束
    设 u = 调用 删除传达 relay_id={relay_id}
    如果 {student} 为空
      设 rl = 调用 传达列表
      设 rs = 调用 传达状态列表
      设 out.class_relays = {rl}
      设 out.class_relay_states = {rs}
    否则
      设 rl = 调用 传达列表 student={student}
      设 out.student_relays = {rl}
    结束
    返回 {out}
  结束

  公开 函数 传达记录页面 message_id
    设 sid = 查一值 app.db teacher_rules_relay_state_by_id id={message_id}
    如果 {sid 或} 为空
      报错 404 没有这条问老师记录
    结束
    返回 {"relay_msg_ask": "（暂不记录原话）", "relay_msg_reply": "（暂不记录原话）", "relay_excerpt": "（暂不记录原话）"}
  结束

结束
