模块 teacher_rules
依赖 account

## 表
表 teacher_rules_setting
  kind 文本 种类：memory（记忆）/ note（作者注）/ card（关键词卡）
  student 文本 针对哪个学生，可空，空串或未填都表示全班
  keywords 文本 关键词，可空，半角逗号隔开
  content 长文本 设定内容（必填）
  enabled 整数 是否启用（1/0）
  once 整数 是否只用于下一条回复（1/0，只有 note 可为 1）
  version 整数 版本号，新建为 1，改了内容或重新启用时加 1，用来判断"只用于下一条"是否重新可用
  author 文本 写的人（教师用户名）
  updated_at 文本 更新时间（YYYY-MM-DD HH:MM:SS）
  subject_id 整数 所属科目，0 表示所有科目，默认 0

表 teacher_rules_setting_use
  reply_id 整数 老师回复编号
  student 文本 学生用户名
  setting_ids 文本 这条回复用到的设定编号，半角逗号隔开，按拼进提示词的顺序
  setting_versions 文本 与 setting_ids 一一对应的版本号，半角逗号隔开
  at 文本 记录时间

表 teacher_rules_relay
  urgency 文本 紧急程度：low（顺便）/ normal（尽快）/ urgent（立即），旧数据的 normal、urgent 含义不变
  tone 文本 口吻，可空
  must_info 长文本 必须准确传达的信息（必填）
  facts 文本 必须准确的信息，可空（要学生原样听到、不能改不能省的内容）
  keywords 文本 话题关键词，可空，半角逗号隔开（「顺便」档提示什么算沾边）
  rounds 整数 要传几轮（不小于 1）
  deadline 文本 截止日 YYYY-MM-DD，可空
  student 文本 针对谁，可空，空串或未填都表示全班
  enabled 整数 是否启用（1/0）
  author 文本 写的人（教师用户名）
  updated_at 文本 更新时间
  subject_id 整数 所属科目，0 表示所有科目，默认 0

表 teacher_rules_relay_state
  relay_id 整数 传达编号
  student 文本 学生用户名
  rounds_done 整数 已传了几轮
  finished 整数 是否传完（1/0）
  confirmed 整数 是否被判定已传达（1/0）
  updated_at 文本 更新时间

表 teacher_rules_relay_use
  reply_id 整数 老师回复编号
  student 文本 学生用户名
  relay_ids 文本 这条回复带上的传达编号，半角逗号隔开
  at 文本 记录时间

## 页面字段
页面 teacher_rules_view AI老师设定页面
  note_id 整数 设定表「编号」列
  note_kind 枚举 记忆,作者注,关键词卡 种类（页面值域是中文，存库时转 memory/note/card）
  note_keywords 文本 关键词，逗号分隔
  note_content 长文本 设定内容
  note_once 布尔 只用于下一条回复（只对作者注有效）
  note_scope 文本 设定表「范围」列（全班/个人）
  note_brief 文本 设定表「内容」列（摘要）
  note_state 文本 设定表「状态」列
  note_updated 文本 设定表「更新时间」列
  note_by 文本 设定表「写的人」列
  preview_student 文本 预览的学生（选项来自接口 note_students）
  preview_message 文本 预览的示例提问
  hit_keyword 文本 命中表「命中的关键词」列
  hit_placed 文本 命中表「放进去了吗」列
  relay_id 整数 传达表「编号」列
  relay_point 长文本 传达的要点（存库为 must_info）
  relay_urgency 枚举 顺便,尽快,立即 紧急程度（页面值域中文；顺便存 low、尽快存 normal、立即存 urgent）
  relay_voice 枚举 以老师名义,AI自己的口吻 口吻（存库为 tone）
  relay_facts 文本 必须准确的信息（存库为 facts）
  relay_keywords 文本 话题关键词（存库为 keywords）
  relay_rounds 整数 几轮没传达到
  relay_due 文本 截止日期
  relay_scope 文本 传达表「范围」列
  relay_brief 文本 传达表「要点」列（摘要）
  relay_done 文本 传达表「完成情况」列
  relay_state_text 文本 传达表「状态」列
  relay_updated 文本 传达表「更新时间」列
  relay_by 文本 传达表「写的人」列
  relay_student_label 文本 状态表「学生」列
  relay_excerpt 文本 AI原话列（v4 不存，值为占位）
  relay_msg_ask 长文本 传达记录浮层「学生问」
  relay_msg_reply 长文本 传达记录浮层「AI老师的回复」

## 函数
公开 函数 列设定 kind? student?
  返回 {items, total}，items 每项 {id, kind, student, keywords, content, enabled, once, version, author, updated_at}，按 id 升序
  伪代码 读 teacher_rules_setting 全部行
  伪代码 kind 不为空时只留 kind 相等的行
  伪代码 student 不为空时只留 student 等于它或 student 为空（全班）的行
  伪代码 返回 {"items": 行列表, "total": 行数}

公开 函数 取设定 setting_id
  返回 {id, kind, student, keywords, content, enabled, once, version, author, updated_at}
  报错 404 没有这条设定
  伪代码 按 id 查 teacher_rules_setting，查不到报错 404 没有这条设定
  伪代码 返回这一行

公开 函数 保存设定 kind content current_user setting_id? student? keywords? once?
  返回 {id, kind, student, keywords, content, enabled, once, version}
  报错 400 种类只能是 memory、note、card
  报错 400 内容必填
  报错 404 没有这条设定
  伪代码 kind 不是 memory、note、card 之一，报错 400 种类只能是 memory、note、card
  伪代码 content 去掉首尾空白后为空，报错 400 内容必填
  伪代码 规整 keywords：全角逗号、顿号、空白全部换成半角逗号，连续逗号合并为一个，去掉首尾逗号
  伪代码 once_val：kind 等于 note 且 once 等于 1 时为 1，否则为 0
  伪代码 setting_id 为空：往 teacher_rules_setting 插入一行 (kind, student, keywords, content, enabled=1, once=once_val, version=1, author=current_user, updated_at=当前时间)
  伪代码 setting_id 不为空：按 id 查旧行，查不到报错 404 没有这条设定；新 version = 旧 content 与新 content 不同时旧 version + 1，否则不变；更新该行的 kind, student, keywords, content, once, version, author=current_user, updated_at=当前时间，不改 enabled
  伪代码 返回保存后的这一行

公开 函数 设置设定启用 setting_id enabled
  返回 {id, enabled, version}
  报错 400 enabled 只能是 0 或 1
  报错 404 没有这条设定
  伪代码 enabled 不是 0 也不是 1，报错 400 enabled 只能是 0 或 1
  伪代码 按 id 查 teacher_rules_setting，查不到报错 404 没有这条设定
  伪代码 旧 enabled 为 0 且新 enabled 为 1 时 version 加 1（重新启用等于重新可用），否则 version 不变
  伪代码 更新 enabled, version, updated_at=当前时间
  伪代码 返回 {"id": id, "enabled": enabled, "version": version}

公开 函数 删除设定 setting_id
  返回 {ok}
  报错 404 没有这条设定
  伪代码 按 id 查 teacher_rules_setting，查不到报错 404 没有这条设定
  伪代码 删除该行（teacher_rules_setting_use 里的历史记录保留）
  伪代码 返回 {"ok": 1}

公开 函数 取生效设定 student recent_text?
  返回 {memory_text, note_text, card_text, setting_ids, setting_versions, count}；三段文本是各自生效设定的内容用换行连接；setting_ids、setting_versions 是按 memory、note、card 顺序（同种类内全班在前、个人在后、同组按 id 升序）排好的编号和版本号，半角逗号隔开；count 是生效的设定条数。只读，不写库，供老师预览提示词和问老师拼提示词用
  伪代码 读 teacher_rules_setting 中 enabled 等于 1 且（student 为空 或 student 等于入参 student）的行，排序：全班（student 为空）在前，个人在后，同组按 id 升序
  伪代码 memory 行：全部生效
  伪代码 note 行：once 等于 0 的生效；once 等于 1 的，读 teacher_rules_setting_use 中该 student 的所有行，把 setting_ids 与 setting_versions 按位置配对，若有配对 (设定 id, 设定当前 version) 完全相同说明已用过，不生效，否则生效
  伪代码 card 行：keywords 不为空且 recent_text 包含其中任意一个关键词才生效（recent_text 为空则都不生效）
  伪代码 按 memory、note、card 顺序汇总，拼出三段文本、setting_ids、setting_versions、count
  伪代码 返回 {"memory_text": …, "note_text": …, "card_text": …, "setting_ids": …, "setting_versions": …, "count": …}

公开 函数 记回复用到设定 reply_id student setting_ids setting_versions
  返回 {ok, recorded}，recorded 为 1 表示写了一行，0 表示没有用到设定
  报错 400 设定编号与版本号个数不一致
  伪代码 setting_ids 为空：返回 {"ok": 1, "recorded": 0}，不写库
  伪代码 setting_ids 与 setting_versions 按逗号拆开后个数不同，报错 400 设定编号与版本号个数不一致
  伪代码 往 teacher_rules_setting_use 插入一行 (reply_id, student, setting_ids, setting_versions, at=当前时间)；调用方（问老师）在写回复的同一个事务里调用本函数，这样与回复一起成败
  伪代码 返回 {"ok": 1, "recorded": 1}

公开 函数 列传达
  返回 {items, total}，items 每项 {id, urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled, author, updated_at}，按 id 升序
  伪代码 读 teacher_rules_relay 全部行，返回 {"items": 行列表, "total": 行数}

公开 函数 取传达 relay_id
  返回 {id, urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled, author, updated_at}（facts、keywords 可空取空串）
  报错 404 没有这条传达
  伪代码 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
  伪代码 返回这一行

公开 函数 保存传达 urgency must_info rounds current_user relay_id? tone? deadline? student? facts? keywords?
  返回 {id, urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled}（facts、keywords 可空取空串）
  报错 400 紧急程度只能是 low、normal 或 urgent
  报错 400 必须准确的信息必填
  报错 400 轮数必须是不小于 1 的整数
  报错 400 截止日格式应为 YYYY-MM-DD
  报错 404 没有这条传达
  伪代码 urgency 不是 low、normal、urgent 之一，报错 400 紧急程度只能是 low、normal 或 urgent
  伪代码 must_info 去掉首尾空白后为空，报错 400 必须准确的信息必填
  伪代码 rounds 不是整数或小于 1，报错 400 轮数必须是不小于 1 的整数
  伪代码 deadline 不为空且不是 YYYY-MM-DD 格式，报错 400 截止日格式应为 YYYY-MM-DD
  伪代码 relay_id 为空：往 teacher_rules_relay 插入一行 (urgency, tone, must_info, facts, keywords, rounds, deadline, student, enabled=1, author=current_user, updated_at=当前时间)，facts、keywords 原样存不规整
  伪代码 relay_id 不为空：按 id 查，查不到报错 404 没有这条传达；更新 urgency, tone, must_info, facts, keywords, rounds, deadline, student, author=current_user, updated_at=当前时间，不改 enabled，不动已有的 teacher_rules_relay_state
  伪代码 返回保存后的这一行

公开 函数 设置传达启用 relay_id enabled
  返回 {id, enabled}
  报错 400 enabled 只能是 0 或 1
  报错 404 没有这条传达
  伪代码 enabled 不是 0 也不是 1，报错 400 enabled 只能是 0 或 1
  伪代码 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
  伪代码 更新 enabled 和 updated_at=当前时间
  伪代码 返回 {"id": id, "enabled": enabled}

公开 函数 删除传达 relay_id
  返回 {ok}
  报错 404 没有这条传达
  伪代码 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
  伪代码 在一个事务里：删除 teacher_rules_relay 该行，并删除 teacher_rules_relay_state 里 relay_id 相同的行（teacher_rules_relay_use 的历史记录保留）
  伪代码 返回 {"ok": 1}

公开 函数 对学生发传达 relay_id student
  返回 {ok, relay_id, student}
  报错 404 没有这条传达
  报错 400 传达已停用
  报错 400 这条传达不是发给该学生的
  伪代码 按 id 查 teacher_rules_relay，查不到报错 404 没有这条传达
  伪代码 enabled 等于 0，报错 400 传达已停用
  伪代码 传达的 student 不为空且不等于入参 student，报错 400 这条传达不是发给该学生的
  伪代码 查 teacher_rules_relay_state 中 (relay_id, student)：没有则插入 (rounds_done=0, finished=0, confirmed=0, updated_at=当前时间)；有则把 rounds_done、finished、confirmed 都重置为 0 并更新 updated_at（让该学生重新开始接收这条传达）
  伪代码 返回 {"ok": 1, "relay_id": relay_id, "student": student}

公开 函数 列传达状态 student?
  返回 {items, total}，items 每项 {relay_id, student, must_info, rounds, rounds_done, finished, confirmed}，按 relay_id、student 升序，供学情页和老师设定页展示
  伪代码 读 teacher_rules_relay_state 并按 relay_id 关联 teacher_rules_relay 取 must_info 和 rounds（传达已被删的状态行已随删除清掉）
  伪代码 student 不为空时只留该 student 的行
  伪代码 返回 {"items": 列表, "total": 行数}

公开 函数 取待传达 student
  返回 {relay_ids, prompt_text, count}；relay_ids 是需要在这条回复里带上的传达编号，半角逗号隔开，按紧急程度排（urgent 在前、normal 次之、low 最后，顺便=最低优先，同档按 id 升序）；prompt_text 每条传达一行，格式「[传达#编号] 紧急:{中文紧急程度} 口吻:tone 必须准确:must_info」，facts 不为空时接「 原样说对:{facts}」，keywords 不为空时接「 沾边提示:{keywords}」，最后接「 截止:deadline」（可空，空就是「截止:」后面没有字），多行用换行连接；count 是条数；中文紧急程度 urgent→立即、normal→尽快、low→顺便
  伪代码 读 teacher_rules_relay 中 enabled 等于 1 且（student 为空 或 student 等于入参 student）的行，排序 urgent 在前、normal 次之、low 在后（顺便=最低优先，参照旧 kg scripts 的口径），同档按 id 升序
  伪代码 取运行时的当前日期 today（YYYY-MM-DD，不写死具体日期）；去掉 deadline 不为空且小于 today 的（已过截止日不再传）
  伪代码 查 teacher_rules_relay_state 的 (relay_id, student)：存在且 finished 等于 1 的去掉
  伪代码 剩下的拼出 relay_ids、prompt_text、count 返回；没有则 {"relay_ids": "", "prompt_text": "", "count": 0}

公开 函数 记回复传达 reply_id student relay_ids
  返回 {ok, recorded}，recorded 为 1 表示写了一行，0 表示没带传达
  报错 404 没有这条传达
  伪代码 relay_ids 为空：返回 {"ok": 1, "recorded": 0}，不写库
  伪代码 relay_ids 按逗号拆开，其中任一编号在 teacher_rules_relay 查不到，报错 404 没有这条传达
  伪代码 在一个事务里：往 teacher_rules_relay_use 插入一行 (reply_id, student, relay_ids, at=当前时间)；对每个编号，在 teacher_rules_relay_state 里找 (relay_id, student)，没有则插入 rounds_done=1，有则 rounds_done 加 1；若 rounds_done 不小于该传达的 rounds 则 finished=1；confirmed 保持原值，新建为 0；更新 updated_at
  伪代码 返回 {"ok": 1, "recorded": 1}

公开 函数 记传达判定 student relay_id delivered
  返回 {ok, relay_id, student, confirmed, finished}
  报错 400 delivered 只能是 0 或 1
  报错 404 没有这条传达
  报错 404 没有传达状态
  伪代码 delivered 不是 0 也不是 1，报错 400 delivered 只能是 0 或 1
  伪代码 按 relay_id 查 teacher_rules_relay，查不到报错 404 没有这条传达
  伪代码 查 teacher_rules_relay_state 的 (relay_id, student)，查不到报错 404 没有传达状态
  伪代码 delivered 等于 1 时，把该状态行 confirmed 设为 1、finished 设为 1，更新 updated_at；等于 0 时不改状态
  伪代码 返回该状态行的 {"ok": 1, "relay_id": …, "student": …, "confirmed": …, "finished": …}

公开 函数 设定列表 student?
  返回 数组 [{note_id, note_kind, note_scope, note_keywords, note_brief, note_state, note_updated, note_by, mine, note_content, note_once, student}]（设定页和学情学生页的设定表一行一条，行键与页面列一字不差）；student 为空是「AI老师设定」页：只列全班的；student 不为空是学情学生页：全班的（只读，范围「全班」）和该学生个人的放一起，全班在前
  伪代码 读 teacher_rules_setting 全部行；student 为空只留 student 为空的行，否则只留 student 为空或等于入参 student 的行
  伪代码 排序：kind 按 memory、note、card，再全班（student 为空）在前个人在后，再按 id 升序
  伪代码 note_id=id；note_kind 转中文（memory→记忆、note→作者注、card→关键词卡）；note_scope 为「全班」或「个人」；note_keywords 原样；note_brief 是 content 超过 60 个字时取前 60 个字加「…」，否则原文；note_updated=updated_at；note_by=author；note_content 是完整内容；student 原样
  伪代码 mine：该行的 student 等于入参 student（入参为空时按空串比）为 1，否则 0——这一页能改的才是 1，行上编辑/停用/启用/删除按钮看它
  伪代码 note_once：该行 once 等于 1 为文本「true」，否则文本「false」（是文本不是布尔：DSL 的布尔值输出成 JSON 会变成空对象；前端开关认 'true'/'false'）
  伪代码 note_state：enabled 等于 0 为「停用」；once 等于 1 且 student 入参不为空：该学生在 teacher_rules_setting_use 里有一行 setting_ids 与 setting_versions 按位置配出 (本设定 id, 本设定当前 version) 为「只用于下一条·这个学生已用过」，否则「只用于下一条·还没用」；once 等于 1 且 student 入参为空：数出有这样配对的不同学生数 n，为「只用于下一条·已有 n 个学生用过」；其余为「启用」

公开 函数 传达列表 student?
  返回 数组 [{relay_id, relay_scope, relay_urgency, relay_voice, relay_brief, relay_facts, relay_due, relay_done, relay_state_text, relay_enabled_text, relay_excerpt, relay_updated, relay_by, mine, relay_point, relay_keywords, relay_rounds, student, message_id}]；student 为空是「AI老师设定」页的全班传达表；student 不为空是学情学生页：全班的（只读）和该学生个人的放一起，全班在前
  伪代码 读 teacher_rules_relay 全部行；student 为空只留 student 为空的行，否则只留 student 为空或等于入参 student 的行；全班在前个人在后，再按 id 升序
  伪代码 relay_id=id；relay_scope 为「全班」或「个人」；relay_urgency 中文（urgent→立即、normal→尽快、low→顺便）；relay_voice=tone（可空）；relay_brief 是 must_info 超过 60 个字时取前 60 个字加「…」；relay_point 是完整 must_info；relay_facts=facts（可空取空串）；relay_keywords=keywords（可空取空串）；relay_due=deadline（可空取空串）；relay_rounds=rounds；relay_updated=updated_at；relay_by=author；relay_enabled_text 为「启用」或「停用」；mine 为该行 student 等于入参 student（入参为空按空串比）则 1 否则 0；student 原样
  伪代码 relay_excerpt 恒为「（暂不记录原话）」（v4 不存 AI 原话，列保留、值给占位，后续单独立项）
  伪代码 relay_done：只在 student 入参为空时有值，否则空串。调用 account.列学生 得学生总数 total；done 是该传达在 teacher_rules_relay_state 里 confirmed 等于 1 且 student 属于这些学生的行数；文本「已传达 {done}/总 {total}」；deadline 不为空且小于今天（取运行时当前日期）且 done 小于 total，再接「，已过期 {total-done}」
  伪代码 relay_state_text：student 入参不为空时是该学生在这条上的状态，按 传达状态列表 的 relay_state_text 口径（student 入参所指学生）；student 入参为空时是「启用」或「停用」
  伪代码 message_id：student 入参不为空且该学生在这条上有 teacher_rules_relay_state 行时取该行 id，否则 0（0 时前端不画「看那条回复」）

公开 函数 传达状态列表
  返回 数组 [{relay_id, relay_brief, relay_student_label, relay_state_text, relay_excerpt, message_id}]；「AI老师设定」页「各学生的传达状态」表：每条全班传达（student 为空）对每个学生账号一行，还没带入过的也列
  伪代码 调用 account.列学生 得学生；对 student 为空的每条传达（按 id）× 每个学生（按用户名升序）出一行
  伪代码 relay_brief 是 must_info 超过 30 个字时取前 30 个字加「…」；relay_student_label 是「显示名（用户名）」，显示名为空只写用户名；relay_excerpt 恒为「（暂不记录原话）」；message_id 是该 (传达, 学生) 的 teacher_rules_relay_state 行 id，没有行为 0
  伪代码 relay_state_text：停用的传达前缀「停用·」；该 (传达, 学生) 有状态行且 confirmed 等于 1：「已传达（{状态行 updated_at}）」；否则 deadline 不为空且小于今天：「已过期（截止 {deadline}，没传达到）」；否则「待传达（已带入 {rounds_done，没状态行为 0} 轮）」，状态行 finished 等于 1 的再接「·已带满」

公开 函数 取回复用到 reply_id
  返回 {text}；学情学生页「问老师记录」里老师那条回答当时用到的设定和传达，写成「记忆#3、作者注#5、传达#2」，没有为空串
  伪代码 查 teacher_rules_setting_use 中 reply_id 相等的行（取 id 最大的一行）：setting_ids 按逗号拆开，每个编号按 id 查 teacher_rules_setting，查到的写「{种类中文}#{编号}」，设定后来被删了的写「已删#{编号}」
  伪代码 查 teacher_rules_relay_use 中 reply_id 相等的行（取 id 最大的一行）：relay_ids 按逗号拆开，每个编号查 teacher_rules_relay，查到的写「传达#{编号}」，被删了的写「已删传达#{编号}」
  伪代码 把设定的写法和传达的写法按顺序用「、」连接得 text；两处都没有为空串

公开 函数 设定首页页面
  返回 {class_notes, note_students, class_relays, class_relay_states}；「AI老师设定」页「进入时」的整页状态（动作 teacher_note_home）；note_students 是预览「学生」下拉的 [{value, label}]
  伪代码 class_notes=设定列表（student 空）；class_relays=传达列表（student 空）；class_relay_states=传达状态列表
  伪代码 note_students：调用 account.列学生，每个学生转 {value: username, label: 显示名（用户名），显示名为空只写用户名}，按用户名升序

公开 函数 载入设定页面 note_id? student?
  返回 回填表单 {student, note_kind, note_keywords, note_content, note_once}（动作 teacher_note_open，浮层「载入」：行上点「编辑」时整行已拷进表单，这个函数是带着地址进来的刷新用）
  报错 404 没有这条设定
  伪代码 note_id 为空返回空表单 {"student": student 或空串, "note_kind": "记忆", "note_keywords": "", "note_content": "", "note_once": "false"}
  伪代码 note_id 不为空：调用 取设定 setting_id=note_id；取不到，或其 student（空按空串）不等于入参 student（空按空串），报错 404 没有这条设定（只拉这一页能改的）
  伪代码 返回 {"student": 入参 student 或空串, "note_kind": 中文种类, "note_keywords": keywords, "note_content": content, "note_once": once 等于 1 时文本「true」，否则文本「false」}

公开 函数 保存设定页面 note_content current_user note_kind? note_id? student? note_keywords? note_once?
  返回 刷新后的设定表：student 为空 {class_notes}，否则 {student_notes}（各自是 设定列表 的口径）
  报错 400 种类只能是 memory、note、card
  报错 400 内容必填
  报错 404 没有这条设定
  报错 404 没有这个学生
  伪代码 前端键收旧口径：note_kind 是中文「记忆」「作者注」「关键词卡」，空当「记忆」，转成 memory、note、card；其它值原样交给 保存设定（由它报 400 种类只能是 memory、note、card）
  伪代码 student 不为空：调用 account.取账号 username=student，取不到或 role 不等于 student，报错 404 没有这个学生
  伪代码 note_id 不为空：调用 取设定（取不到报 404），其 student（空按空串）不等于入参 student（空按空串），报错 404 没有这条设定（全班的设定要到「AI老师设定」页改，个人的要到学生页改）
  伪代码 once：note_once（不用文本动词，直接比较）等于 是、True、true、TRUE 或 1 时为 1，否则 0（前端开关提交的 JSON 布尔 true 在 DSL 里的文本是「是」（false 是「否」），字符串 True/true 也要认；note_once 没传按 0，不要对它用归一化/转大写等文本动词）；调用 保存设定 kind=转换后 content=note_content current_user=current_user setting_id=note_id student=student keywords=note_keywords once=once
  伪代码 返回刷新后的设定表（student 为空 {"class_notes": 设定列表（student 空）}，否则 {"student_notes": 设定列表 student=student}）

公开 函数 设置设定启用页面 note_id enabled student?
  返回 刷新后的设定表，形状同 保存设定页面
  报错 400 enabled 只能是 0 或 1
  报错 404 没有这条设定
  伪代码 note_id 对应的设定取不到，或其 student（空按空串）不等于入参 student（空按空串），报错 404 没有这条设定
  伪代码 调用 设置设定启用 setting_id=note_id enabled=enabled，再返回刷新后的设定表

公开 函数 删除设定页面 note_id student?
  返回 刷新后的设定表，形状同 保存设定页面
  报错 404 没有这条设定
  伪代码 校验同 设置设定启用页面；调用 删除设定 setting_id=note_id，再返回刷新后的设定表

公开 函数 设定预览页面 preview_student preview_message
  返回 {preview, preview_hits}；preview 是 {ids, relay_pick, layout}，preview_hits 是命中的关键词卡 [{note_id, hit_keyword, note_brief, hit_placed}]；只读，不写库，「只用于下一条」不会被用掉
  报错 400 先选一个学生
  报错 400 输一句示例提问
  伪代码 preview_student 为空报错 400 先选一个学生；preview_message 为空报错 400 输一句示例提问
  伪代码 recent_text：用 app.db 查询 teacher_rules_tutor_exists（sqlite_master 里有没有 tutor_message 表，没有就当没有最近对话——模块用例的库不含下游 tutor 的表），有则查 teacher_rules_recent_asks 取该学生最近 3 条学生提问（role 为 user，按 id 降序），按旧到新用换行连接；再换行接 preview_message
  伪代码 调用 取生效设定 student=preview_student recent_text=recent_text 得生效设定；调用 取待传达 student=preview_student 得待传达
  伪代码 ids：取生效设定 的 setting_ids，为空写「（无）」
  伪代码 relay_pick：取待传达 的 relay_ids 为空写「（没有待传达的要点）」；否则取第一个编号，查该传达得 must_info 摘要（超过 30 字取前 30 加「…」）和 urgency（urgent 写立即、normal 写尽快、low 写顺便），写「传达#{编号}「{摘要}」，这次按「{紧急程度}」带；后面还排着{count-1}条（一条回复只带一条）」
  伪代码 layout：「【系统提示词】你是一位耐心的日语老师……你不要自己写网址。」接 memory_text（不为空时前加一个换行），再空一行（两个换行）接「【发给模型的提示词】学生现在用的教材：【……】课文、进度等材料：【……】」，card_text 不为空时先换行再接 card_text 再换行，接「最近的对话（旧的在前）：【……】」，待传达的 prompt_text 不为空时先换行再接它，note_text 不为空时先换行再接它，最后换行接「学生现在说：【{preview_message}】请直接回答学生现在这句话。」；某段为空就什么都不接（换行也不接）
  伪代码 preview_hits：读 teacher_rules_setting 中 enabled 等于 1、kind 为 card、student 为空或等于 preview_student 的行（全班在前，再按 id）；keywords 按逗号拆开，recent_text 包含其中任一个的取第一个命中的为 hit_keyword；note_brief 同 设定列表 的摘要写法，hit_placed 恒为「放进去了」（v4 不设命中卡字数上限）
  伪代码 返回 {"preview": {"ids": ids, "relay_pick": relay_pick, "layout": layout}, "preview_hits": 列表}

公开 函数 载入传达页面 relay_id? student?
  返回 回填表单 {student, relay_point, relay_urgency, relay_voice, relay_facts, relay_keywords, relay_rounds, relay_due}（动作 teacher_relay_open）
  报错 404 没有这条传达
  伪代码 relay_id 为空返回空表单 {"student": student 或空串, "relay_point": "", "relay_urgency": "尽快", "relay_voice": "以老师名义", "relay_facts": "", "relay_keywords": "", "relay_rounds": 3, "relay_due": ""}
  伪代码 relay_id 不为空：调用 取传达；取不到，或其 student（空按空串）不等于入参 student（空按空串），报错 404 没有这条传达
  伪代码 返回 {"student": …, "relay_point": must_info, "relay_urgency": 中文（urgent→立即、normal→尽快、low→顺便）, "relay_voice": tone 为空取「以老师名义」, "relay_facts": facts 或空串, "relay_keywords": keywords 或空串, "relay_rounds": rounds, "relay_due": deadline 或空串}

公开 函数 保存传达页面 relay_point current_user relay_id? student? relay_urgency? relay_voice? relay_facts? relay_keywords? relay_rounds? relay_due?
  返回 刷新后的传达表：student 为空 {class_relays, class_relay_states}，否则 {student_relays}（各自是 传达列表、传达状态列表 的口径）
  报错 400 必须准确的信息必填
  报错 400 轮数必须是不小于 1 的整数
  报错 400 截止日格式应为 YYYY-MM-DD
  报错 404 没有这条传达
  报错 404 没有这个学生
  伪代码 student 不为空：调用 account.取账号 校验同 保存设定页面（报 404 没有这个学生）；relay_id 不为空：调用 取传达，取不到或其 student（空按空串）不等于入参 student，报错 404 没有这条传达
  伪代码 前端键收旧口径：relay_point 存为 must_info；relay_urgency 是「顺便」「尽快」「立即」：顺便→low、尽快→normal（空或其他值也按 normal，旧口径兜底）、立即→urgent；relay_voice 存为 tone（空串不存）；relay_facts 存为 facts、relay_keywords 存为 keywords（原样存，不规整）；relay_rounds 空或 0 当 3；relay_due 空串当没有
  伪代码 调用 保存传达 urgency=转换后 must_info=relay_point rounds=转换后 current_user=current_user relay_id=relay_id tone=relay_voice deadline=relay_due student=student facts=relay_facts keywords=relay_keywords（校验报错原样向上抛）
  伪代码 返回刷新后的传达表

公开 函数 设置传达启用页面 relay_id enabled student?
  返回 刷新后的传达表，形状同 保存传达页面
  报错 400 enabled 只能是 0 或 1
  报错 404 没有这条传达
  伪代码 relay_id 对应的传达取不到，或其 student（空按空串）不等于入参 student（空按空串），报错 404 没有这条传达；调用 设置传达启用 relay_id=relay_id enabled=enabled，再返回刷新后的传达表

公开 函数 删除传达页面 relay_id student?
  返回 刷新后的传达表，形状同 保存传达页面
  报错 404 没有这条传达
  伪代码 校验同 设置传达启用页面；调用 删除传达 relay_id=relay_id（同时清掉该传达的状态行），再返回刷新后的传达表

公开 函数 传达记录页面 message_id
  返回 回填表单 {relay_msg_ask, relay_msg_reply, relay_excerpt}，三项都是占位「（暂不记录原话）」（v4 不存 AI 原话，后续单独立项）
  报错 404 没有这条问老师记录
  伪代码 message_id 就是 传达列表/传达状态列表 行上的 message_id（teacher_rules_relay_state 的行 id）；按 id 查 teacher_rules_relay_state，查不到报错 404 没有这条问老师记录
  伪代码 返回 {"relay_msg_ask": "（暂不记录原话）", "relay_msg_reply": "（暂不记录原话）", "relay_excerpt": "（暂不记录原话）"}

## 接口
GET /teacher_rules/settings -> 列设定 角色 teacher
GET /teacher_rules/setting -> 取设定 角色 teacher
POST /teacher_rules/setting/save -> 保存设定 角色 teacher
POST /teacher_rules/setting/enable -> 设置设定启用 角色 teacher
DELETE /teacher_rules/setting/delete -> 删除设定 角色 teacher
GET /teacher_rules/prompt -> 取生效设定 角色 teacher
GET /teacher_rules/relays -> 列传达 角色 teacher
GET /teacher_rules/relay -> 取传达 角色 teacher
POST /teacher_rules/relay/save -> 保存传达 角色 teacher
POST /teacher_rules/relay/enable -> 设置传达启用 角色 teacher
DELETE /teacher_rules/relay/delete -> 删除传达 角色 teacher
POST /teacher_rules/relay/send -> 对学生发传达 角色 teacher
GET /teacher_rules/relay/states -> 列传达状态 角色 teacher
POST /teacher_rules/note/home -> 设定首页页面 动作 teacher_note_home 模板 页面状态 角色 teacher
POST /teacher_rules/note/open -> 载入设定页面 动作 teacher_note_open 模板 回填 角色 teacher
POST /teacher_rules/note/save -> 保存设定页面 动作 teacher_note_save 模板 页面状态消息 消息=设定已保存 角色 teacher
POST /teacher_rules/note/disable -> 设置设定启用页面 动作 teacher_note_disable 模板 页面状态消息 消息=已停用 传 enabled=0 角色 teacher
POST /teacher_rules/note/enable -> 设置设定启用页面 动作 teacher_note_enable 模板 页面状态消息 消息=已启用 传 enabled=1 角色 teacher
POST /teacher_rules/note/delete -> 删除设定页面 动作 teacher_note_delete 模板 页面状态消息 消息=已删除 角色 teacher
POST /teacher_rules/note/preview -> 设定预览页面 动作 teacher_note_preview 模板 页面状态 角色 teacher
POST /teacher_rules/relay/open -> 载入传达页面 动作 teacher_relay_open 模板 回填 角色 teacher
POST /teacher_rules/relay/page-save -> 保存传达页面 动作 teacher_relay_save 模板 页面状态消息 消息=传达已保存 角色 teacher
POST /teacher_rules/relay/page-disable -> 设置传达启用页面 动作 teacher_relay_disable 模板 页面状态消息 消息=传达已停用 传 enabled=0 角色 teacher
POST /teacher_rules/relay/page-enable -> 设置传达启用页面 动作 teacher_relay_enable 模板 页面状态消息 消息=传达已启用 传 enabled=1 角色 teacher
POST /teacher_rules/relay/page-delete -> 删除传达页面 动作 teacher_relay_delete 模板 页面状态消息 消息=传达已删除 角色 teacher
POST /teacher_rules/relay/message -> 传达记录页面 动作 teacher_relay_message 模板 回填 角色 teacher

## 用例
用例 列设定_按种类和学生过滤
  先 数据 teacher_rules_setting kind=memory student=s1 content=A enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=memory content=B enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=memory student=s2 content=C enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=note content=D enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 列设定 kind=memory student=s1
  得 total=2

用例 列设定_无数据
  调用 列设定
  得 total=0

用例 取设定_存在
  先 数据 teacher_rules_setting kind=memory content=A enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取设定 setting_id=1
  得 id=1 kind=memory content=A enabled=1 version=1

用例 取设定_不存在
  调用 取设定 setting_id=99
  报错 404

用例 保存设定_新建记忆
  调用 保存设定 kind=memory content=多用中文解释 current_user=t1
  得 kind=memory enabled=1 once=0 version=1
  库 teacher_rules_setting 共 1 行
  库 teacher_rules_setting 含 kind=memory content=多用中文解释 enabled=1 version=1 author=t1

用例 保存设定_关键词规整
  调用 保存设定 kind=card keywords=は，が、を content=X current_user=t1
  得 keywords=は,が,を
  库 teacher_rules_setting 含 kind=card keywords=は,が,を

用例 保存设定_只有作者注可只用一次
  先 调用 保存设定 kind=memory content=M once=1 current_user=t1
  调用 保存设定 kind=note content=N once=1 current_user=t1
  得 once=1
  库 teacher_rules_setting 含 kind=memory once=0
  库 teacher_rules_setting 含 kind=note once=1

用例 保存设定_改内容版本加一
  先 数据 teacher_rules_setting kind=note content=旧 enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 保存设定 setting_id=1 kind=note content=新 once=1 current_user=t1
  得 id=1 content=新 version=2 enabled=1
  库 teacher_rules_setting 共 1 行

用例 保存设定_内容不变版本不变
  先 数据 teacher_rules_setting kind=note content=旧 enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 保存设定 setting_id=1 kind=note content=旧 once=1 student=s1 current_user=t1
  得 version=1 student=s1

用例 保存设定_内容必填
  调用 保存设定 kind=memory content=空 current_user=t1
  报错 400
  库 teacher_rules_setting 共 0 行

用例 保存设定_种类非法
  调用 保存设定 kind=other content=X current_user=t1
  报错 400
  库 teacher_rules_setting 共 0 行

用例 保存设定_不存在
  调用 保存设定 setting_id=99 kind=memory content=X current_user=t1
  报错 404

用例 设置设定启用_重新启用版本加一
  先 数据 teacher_rules_setting kind=note content=N enabled=0 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置设定启用 setting_id=1 enabled=1
  得 enabled=1 version=2
  库 teacher_rules_setting 含 id=1 enabled=1 version=2

用例 设置设定启用_停用版本不变
  先 数据 teacher_rules_setting kind=note content=N enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置设定启用 setting_id=1 enabled=0
  得 enabled=0 version=1

用例 设置设定启用_值非法
  先 数据 teacher_rules_setting kind=note content=N enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置设定启用 setting_id=1 enabled=2
  报错 400

用例 设置设定启用_不存在
  调用 设置设定启用 setting_id=99 enabled=1
  报错 404

用例 删除设定_正常
  先 数据 teacher_rules_setting kind=memory content=A enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 删除设定 setting_id=1
  得 ok=1
  库 teacher_rules_setting 共 0 行

用例 删除设定_不存在
  调用 删除设定 setting_id=99
  报错 404

用例 取生效设定_全班在前个人在后
  先 数据 teacher_rules_setting kind=memory student=s1 content=P enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=memory content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=memory student=s2 content=O enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取生效设定 student=s1
  得 count=2 setting_ids=2,1 setting_versions=1,1

用例 取生效设定_停用的不带
  先 数据 teacher_rules_setting kind=memory content=G enabled=0 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取生效设定 student=s1
  得 count=0

用例 取生效设定_只用一次用过就不带
  先 数据 teacher_rules_setting kind=note content=N enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 调用 记回复用到设定 reply_id=1 student=s1 setting_ids=1 setting_versions=1
  调用 取生效设定 student=s1
  得 count=0

用例 取生效设定_只用一次按学生算
  先 数据 teacher_rules_setting kind=note content=N enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 调用 记回复用到设定 reply_id=1 student=s1 setting_ids=1 setting_versions=1
  调用 取生效设定 student=s2
  得 count=1 setting_ids=1

用例 取生效设定_重新启用后重新可用
  先 数据 teacher_rules_setting kind=note content=N enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 调用 记回复用到设定 reply_id=1 student=s1 setting_ids=1 setting_versions=1
  先 调用 设置设定启用 setting_id=1 enabled=0
  先 调用 设置设定启用 setting_id=1 enabled=1
  调用 取生效设定 student=s1
  得 count=1 setting_ids=1 setting_versions=2

用例 取生效设定_关键词卡命中
  先 数据 teacher_rules_setting kind=card keywords=は,が content=C enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取生效设定 student=s1 recent_text=今日は雨
  得 count=1 setting_ids=1

用例 取生效设定_关键词卡未命中
  先 数据 teacher_rules_setting kind=card keywords=は,が content=C enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取生效设定 student=s1 recent_text=你好
  得 count=0

用例 取生效设定_关键词卡无最近发言不带
  先 数据 teacher_rules_setting kind=card keywords=は content=C enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取生效设定 student=s1
  得 count=0

用例 记回复用到设定_正常
  调用 记回复用到设定 reply_id=5 student=s1 setting_ids=1,2 setting_versions=1,3
  得 ok=1 recorded=1
  库 teacher_rules_setting_use 共 1 行
  库 teacher_rules_setting_use 含 reply_id=5 student=s1 setting_ids=1,2 setting_versions=1,3

用例 记回复用到设定_没用设定不记
  调用 记回复用到设定 reply_id=5 student=s1 setting_ids=空 setting_versions=空
  得 ok=1 recorded=0
  库 teacher_rules_setting_use 共 0 行

用例 记回复用到设定_个数不一致
  调用 记回复用到设定 reply_id=5 student=s1 setting_ids=1,2 setting_versions=1
  报错 400
  库 teacher_rules_setting_use 共 0 行

用例 列传达_全部
  先 数据 teacher_rules_relay urgency=normal must_info=下周三小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay urgency=urgent must_info=作业改期 rounds=1 student=s1 enabled=0 author=t1 updated_at=2026-01-01_09:00:00
  调用 列传达
  得 total=2

用例 列传达_无数据
  调用 列传达
  得 total=0

用例 取传达_存在
  先 数据 teacher_rules_relay urgency=normal must_info=下周三小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取传达 relay_id=1
  得 id=1 urgency=normal must_info=下周三小测 rounds=2 enabled=1

用例 取传达_不存在
  调用 取传达 relay_id=99
  报错 404

用例 保存传达_新建
  调用 保存传达 urgency=urgent must_info=下周三小测 rounds=2 deadline=2026-01-07 current_user=t1
  得 urgency=urgent must_info=下周三小测 rounds=2 deadline=2026-01-07 enabled=1
  库 teacher_rules_relay 共 1 行
  库 teacher_rules_relay 含 urgency=urgent rounds=2 enabled=1 author=t1

用例 保存传达_修改
  先 数据 teacher_rules_relay urgency=normal must_info=旧 rounds=2 enabled=0 author=t1 updated_at=2026-01-01_09:00:00
  调用 保存传达 relay_id=1 urgency=urgent must_info=新 rounds=3 student=s1 current_user=t2
  得 id=1 urgency=urgent must_info=新 rounds=3 student=s1 enabled=0
  库 teacher_rules_relay 共 1 行
  库 teacher_rules_relay 含 id=1 author=t2

用例 保存传达_顺便档和facts关键词
  调用 保存传达 urgency=low must_info=周五带复习卡片 rounds=1 facts=卡片在教室抽屉里 keywords=复习,单词 current_user=t1
  得 urgency=low facts=卡片在教室抽屉里 keywords=复习,单词
  库 teacher_rules_relay 含 urgency=low facts=卡片在教室抽屉里 keywords=复习,单词

用例 保存传达_紧急程度非法
  调用 保存传达 urgency=high must_info=X rounds=1 current_user=t1
  报错 400
  库 teacher_rules_relay 共 0 行

用例 保存传达_信息必填
  调用 保存传达 urgency=normal must_info=空 rounds=1 current_user=t1
  报错 400

用例 保存传达_轮数非法
  调用 保存传达 urgency=normal must_info=X rounds=0 current_user=t1
  报错 400

用例 保存传达_截止日格式非法
  调用 保存传达 urgency=normal must_info=X rounds=1 deadline=明天 current_user=t1
  报错 400

用例 保存传达_不存在
  调用 保存传达 relay_id=99 urgency=normal must_info=X rounds=1 current_user=t1
  报错 404

用例 设置传达启用_正常
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=1 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置传达启用 relay_id=1 enabled=0
  得 id=1 enabled=0
  库 teacher_rules_relay 含 id=1 enabled=0

用例 设置传达启用_值非法
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=1 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置传达启用 relay_id=1 enabled=5
  报错 400

用例 设置传达启用_不存在
  调用 设置传达启用 relay_id=99 enabled=1
  报错 404

用例 删除传达_连状态一起删
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=0 updated_at=2026-01-01_09:00:00
  调用 删除传达 relay_id=1
  得 ok=1
  库 teacher_rules_relay 共 0 行
  库 teacher_rules_relay_state 共 0 行

用例 删除传达_不存在
  调用 删除传达 relay_id=99
  报错 404

用例 对学生发传达_新建状态
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 对学生发传达 relay_id=1 student=s1
  得 ok=1 relay_id=1 student=s1
  库 teacher_rules_relay_state 共 1 行
  库 teacher_rules_relay_state 含 relay_id=1 student=s1 rounds_done=0 finished=0 confirmed=0

用例 对学生发传达_重置已传完的状态
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=2 finished=1 confirmed=1 updated_at=2026-01-01_09:00:00
  调用 对学生发传达 relay_id=1 student=s1
  得 ok=1
  库 teacher_rules_relay_state 共 1 行
  库 teacher_rules_relay_state 含 relay_id=1 student=s1 rounds_done=0 finished=0 confirmed=0

用例 对学生发传达_已停用
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=0 author=t1 updated_at=2026-01-01_09:00:00
  调用 对学生发传达 relay_id=1 student=s1
  报错 400
  库 teacher_rules_relay_state 共 0 行

用例 对学生发传达_不是该学生的
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 student=s2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 对学生发传达 relay_id=1 student=s1
  报错 400

用例 对学生发传达_不存在
  调用 对学生发传达 relay_id=99 student=s1
  报错 404

用例 列传达状态_按学生
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=0 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s2 rounds_done=2 finished=1 confirmed=1 updated_at=2026-01-01_09:00:00
  调用 列传达状态 student=s1
  得 total=1

用例 列传达状态_无数据
  调用 列传达状态
  得 total=0

用例 取待传达_全班传达
  先 数据 teacher_rules_relay urgency=normal must_info=下周三小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取待传达 student=s1
  得 count=1 relay_ids=1

用例 取待传达_顺便最低优先
  先 数据 teacher_rules_relay urgency=low must_info=顺便甲 rounds=1 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay urgency=urgent must_info=立即乙 facts=乙的事实 keywords=乙词 rounds=1 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay urgency=normal must_info=尽快丙 rounds=1 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取待传达 student=s1
  得 count=3 relay_ids=2,3,1

用例 取待传达_过了截止日不带
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 deadline=2025-12-31 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 取待传达 student=s1
  得 count=0

用例 取待传达_已传完不带
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=2 finished=1 confirmed=0 updated_at=2026-01-01_09:00:00
  调用 取待传达 student=s1
  得 count=0

用例 取待传达_别的学生的和停用的不带
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 student=s2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay urgency=normal must_info=Y rounds=2 enabled=0 author=t1 updated_at=2026-01-01_09:00:00
  调用 取待传达 student=s1
  得 count=0

用例 记回复传达_第一轮
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 记回复传达 reply_id=7 student=s1 relay_ids=1
  得 ok=1 recorded=1
  库 teacher_rules_relay_use 共 1 行
  库 teacher_rules_relay_use 含 reply_id=7 student=s1 relay_ids=1
  库 teacher_rules_relay_state 含 relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=0

用例 记回复传达_传满轮数
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 调用 记回复传达 reply_id=7 student=s1 relay_ids=1
  调用 记回复传达 reply_id=8 student=s1 relay_ids=1
  得 ok=1 recorded=1
  库 teacher_rules_relay_state 共 1 行
  库 teacher_rules_relay_state 含 relay_id=1 student=s1 rounds_done=2 finished=1

用例 记回复传达_没带传达不记
  调用 记回复传达 reply_id=7 student=s1 relay_ids=空
  得 ok=1 recorded=0
  库 teacher_rules_relay_use 共 0 行

用例 记回复传达_传达不存在
  调用 记回复传达 reply_id=7 student=s1 relay_ids=99
  报错 404
  库 teacher_rules_relay_use 共 0 行
  库 teacher_rules_relay_state 共 0 行

用例 记传达判定_已传达
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=3 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=0 updated_at=2026-01-01_09:00:00
  调用 记传达判定 student=s1 relay_id=1 delivered=1
  得 ok=1 confirmed=1 finished=1
  库 teacher_rules_relay_state 含 relay_id=1 student=s1 confirmed=1 finished=1

用例 记传达判定_未传达不改状态
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=3 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=0 updated_at=2026-01-01_09:00:00
  调用 记传达判定 student=s1 relay_id=1 delivered=0
  得 ok=1 confirmed=0 finished=0

用例 记传达判定_值非法
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=3 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 记传达判定 student=s1 relay_id=1 delivered=3
  报错 400

用例 记传达判定_没有状态
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=3 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 记传达判定 student=s1 relay_id=1 delivered=1
  报错 404

用例 记传达判定_传达不存在
  调用 记传达判定 student=s1 relay_id=99 delivered=1
  报错 404

用例 设定列表_学生页含全班和个人
  先 数据 teacher_rules_setting kind=memory content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=note student=s1 content=P enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting kind=note student=s2 content=O enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设定列表 student=s1
  得 有返回

用例 传达列表_全班
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 teacher_rules_relay urgency=normal must_info=下周三小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=1 updated_at=2026-01-02_09:00:00
  调用 传达列表
  得 有返回

用例 传达状态列表_每个学生一行
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 teacher_rules_relay urgency=normal must_info=下周三小测 rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 传达状态列表
  得 有返回

用例 取回复用到_设定和传达
  先 数据 teacher_rules_setting kind=memory content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_setting_use reply_id=5 student=s1 setting_ids=1 setting_versions=1 at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_use reply_id=5 student=s1 relay_ids=1 at=2026-01-01_09:00:00
  调用 取回复用到 reply_id=5
  得 text=记忆#1、传达#1

用例 取回复用到_没有用到
  调用 取回复用到 reply_id=9
  得 有返回

用例 设定首页页面_有学生有设定
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 teacher_rules_setting kind=memory content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设定首页页面
  得 有返回

用例 载入设定页面_空表单
  调用 载入设定页面
  得 note_kind=记忆 note_once=false

用例 载入设定页面_取回一条
  先 数据 teacher_rules_setting kind=note content=X enabled=1 once=1 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 载入设定页面 note_id=1
  得 note_kind=作者注 note_content=X note_once=true

用例 载入设定页面_范围不符
  先 数据 teacher_rules_setting kind=note student=s1 content=X enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 载入设定页面 note_id=1
  报错 404

用例 保存设定页面_新建全班记忆
  调用 保存设定页面 note_kind=记忆 note_content=多用中文解释 current_user=t1
  得 有返回
  库 teacher_rules_setting 共 1 行
  库 teacher_rules_setting 含 kind=memory content=多用中文解释 enabled=1 author=t1

用例 保存设定页面_关键词卡
  调用 保存设定页面 note_kind=关键词卡 note_keywords=ばかり,たばかり note_content=强调区别 current_user=t1
  库 teacher_rules_setting 含 kind=card keywords=ばかり,たばかり

用例 保存设定页面_学生个人
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  调用 保存设定页面 note_kind=作者注 note_once=true note_content=简短 current_user=t1 student=s1
  库 teacher_rules_setting 含 kind=note student=s1 once=1

用例 保存设定页面_布尔真值也认
  调用 保存设定页面 note_kind=作者注 note_once=是 note_content=简短 current_user=t1
  库 teacher_rules_setting 含 kind=note once=1

用例 保存设定页面_没有这个学生
  调用 保存设定页面 note_kind=记忆 note_content=A current_user=t1 student=nobody
  报错 404
  库 teacher_rules_setting 共 0 行

用例 保存设定页面_学生页不能改全班的
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 teacher_rules_setting kind=memory content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 保存设定页面 note_id=1 note_kind=记忆 note_content=改 current_user=t1 student=s1
  报错 404
  库 teacher_rules_setting 含 id=1 content=G

用例 保存设定页面_内容必填
  调用 保存设定页面 note_kind=记忆 note_content=空 current_user=t1
  报错 400
  库 teacher_rules_setting 共 0 行

用例 设置设定启用页面_停用
  先 数据 teacher_rules_setting kind=memory content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置设定启用页面 note_id=1 enabled=0
  得 有返回
  库 teacher_rules_setting 含 id=1 enabled=0

用例 设置设定启用页面_范围不符
  先 数据 teacher_rules_setting kind=memory student=s1 content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置设定启用页面 note_id=1 enabled=0
  报错 404

用例 删除设定页面_正常
  先 数据 teacher_rules_setting kind=memory content=G enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 删除设定页面 note_id=1
  得 有返回
  库 teacher_rules_setting 共 0 行

用例 设定预览页面_命中关键词卡
  先 数据 teacher_rules_setting kind=card keywords=ばかり content=强调区别 enabled=1 once=0 version=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设定预览页面 preview_student=s1 preview_message=ばかり是什么
  得 有返回
  库 teacher_rules_setting_use 共 0 行

用例 载入传达页面_空表单
  调用 载入传达页面
  得 relay_urgency=尽快 relay_rounds=3

用例 载入传达页面_取回一条
  先 数据 teacher_rules_relay urgency=urgent tone=AI自己的口吻 must_info=X facts=要说对的关键句 keywords=作业 rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 载入传达页面 relay_id=1
  得 relay_point=X relay_urgency=立即 relay_voice=AI自己的口吻 relay_rounds=2 relay_facts=要说对的关键句 relay_keywords=作业

用例 载入传达页面_顺便档
  先 数据 teacher_rules_relay urgency=low must_info=Y rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 载入传达页面 relay_id=1
  得 relay_urgency=顺便

用例 保存传达页面_新建
  调用 保存传达页面 relay_point=下周三小测 relay_urgency=立即 relay_rounds=2 current_user=t1
  得 有返回
  库 teacher_rules_relay 共 1 行
  库 teacher_rules_relay 含 must_info=下周三小测 urgency=urgent rounds=2 enabled=1

用例 保存传达页面_默认值
  调用 保存传达页面 relay_point=作业截止日改了 current_user=t1
  库 teacher_rules_relay 含 urgency=normal rounds=3

用例 保存传达页面_顺便档和facts关键词存进库
  调用 保存传达页面 relay_point=下周三小测 relay_urgency=顺便 relay_facts=范围第1到3课 relay_keywords=小测 current_user=t1
  库 teacher_rules_relay 含 must_info=下周三小测 urgency=low facts=范围第1到3课 keywords=小测

用例 保存传达页面_截止日格式不对
  调用 保存传达页面 relay_point=X relay_due=bad current_user=t1
  报错 400
  库 teacher_rules_relay 共 0 行

用例 保存传达页面_没有这个学生
  调用 保存传达页面 relay_point=X current_user=t1 student=nobody
  报错 404

用例 设置传达启用页面_停用
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  调用 设置传达启用页面 relay_id=1 enabled=0
  得 有返回
  库 teacher_rules_relay 含 id=1 enabled=0

用例 删除传达页面_同时清状态
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=0 updated_at=2026-01-01_09:00:00
  调用 删除传达页面 relay_id=1
  得 有返回
  库 teacher_rules_relay 共 0 行
  库 teacher_rules_relay_state 共 0 行

用例 传达记录页面_占位
  先 数据 teacher_rules_relay urgency=normal must_info=X rounds=2 enabled=1 author=t1 updated_at=2026-01-01_09:00:00
  先 数据 teacher_rules_relay_state relay_id=1 student=s1 rounds_done=1 finished=0 confirmed=1 updated_at=2026-01-01_09:00:00
  调用 传达记录页面 message_id=1
  得 relay_excerpt=（暂不记录原话）

用例 传达记录页面_不存在
  调用 传达记录页面 message_id=99
  报错 404
