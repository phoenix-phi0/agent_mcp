模块 assist_setting
依赖 assist_common teacher_rules subject

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，need=write 且没有写权限报 403 没有权限修改该科目，原样抛出）。本模块不传 need：执行、撤销函数会写别的模块的业务表，但写权限由调用方 assist_draft 的 确认草稿 / 撤销草稿 按 need=write 校验过，它调本模块时只传 subject=已解析的科目编号（同 P1 的 teacher_rules.保存传达）

公开 函数 设定候选 learner? current_role? auth_mode? subject?
  返回 {editable, readonly}；给 setting_save 提示词用的已有设定（P1b）：editable 是本科目（所属科目等于 subject_id）的设定 [{id, kind, student, keywords, content, enabled}]，模型要「改某条」时只能从这里选 target_id；readonly 是「全部科目」（所属科目 0）的设定 [{id, kind, content}]，只给模型看、注明助手不能改；assist_draft.生成草稿 备料时调
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 调用 teacher_rules.列设定 subject=subject_id 得 items（本科目 ∪ 0），按 id 降序取前 40 条
  伪代码 列设定 的返回里没有所属科目：逐条调用 teacher_rules.取设定 setting_id=该 id subject=subject_id 取 subject_id，等于本科目的进 editable（content 截前 200 字），等于 0 的进 readonly（content 截前 60 字）
  伪代码 返回 {"editable": …, "readonly": …}

公开 函数 校验设定草稿 payload_json learner? current_role? auth_mode? subject?
  返回 {ok, errors, normalized, title, preview}；setting_save 的内容校验（P1b，assist_draft.校验草稿 分派过来）；ok 为 1 表示 errors 为空；只读，内容错误进 errors 不报错
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 payload_json 是字典，或它的 JSON 文本（先解析）；解析失败或不是对象：errors=["输出不是 JSON 对象"]，直接返回 ok=0（assist_draft.校验草稿 传的是已解析的对象）；下面的 settings 指它的 settings 键
  伪代码 settings 不是列表或为空记「settings 不能为空」并停止逐条检查；超过 10 条记「一份草稿最多 10 条设定」并停止逐条检查
  伪代码 逐条（i 从 1 起，每条出错记「第 i 条：…」）：不是对象记「格式不对」；出现 scope、subject_id、setting_id、enabled、version、author 任一键记「不允许出现字段 <键>」（改哪条用 target_id；范围固定为本科目，助手不生成「全部科目」的设定，那要负责人权限；启停不归助手管）
  伪代码 target_id 为空或不出现：op=add（新建）。不为空：不是正整数记「target_id 不合法」；同一 target_id 在本草稿里出现第二次记「设定 #n 重复出现」；调用 teacher_rules.取设定 setting_id=target_id subject=subject_id 出错时 e，报 404 记「没有编号 n 的设定」（含别的科目的、模型编的编号）；取到的行 subject_id 等于 0 记「设定 #n 是全部科目的设定，请到 AI 老师设定页由负责人改」（design §2.4：协作教师改它会被 403，负责人也不走助手）；通过则 op=edit，取到的行记为 cur（只给预览做前后对比，不进 payload；确认时另取改前值）
  伪代码 op=edit 时 kind、student、keywords、once 四个键不出现就取 cur 的值（老师只说改内容时，不会把个人设定改成全班、把关键词清掉）；op=add 时不出现的取默认：kind 必填、student 空（全班）、keywords 空、once 0
  伪代码 kind 不是 memory、note、card 之一记「种类只能是 memory、note、card」；content 去首尾空白后为空记「内容不能为空」，超过 1000 字记「内容超过 1000 字」；keywords 字符串或字符串列表（列表用英文逗号连起来；规整交给 保存设定），kind 等于 card 且 keywords 为空记「关键词卡要写关键词」；once：kind 等于 note 且值为 1 或 true 时为 1，否则 0（与 保存设定 同口径，不报错）
  伪代码 student 不为空时调用 assist_common.匹配学生 name=student subject=subject_id（op=edit 且 student 取自 cur 的是用户名，照样匹配得 one）：none 记「没有找到叫「名字」的学生」，many 记「「名字」找到多位：显示名（用户名）、…，你指哪一位？」，one 收下 username 与 display_name；student 为空是全班
  伪代码 normalized：{"settings": [{"op": add|edit, "target_id": 编号或空串, "kind", "content", "student": username或空串, "student_name": 显示名或空串, "keywords", "once": 0|1}]}
  伪代码 title 为空时取「改 n 条 AI 老师设定」；preview 每条一段：add「i. 新建 种类名（全班 / 给 显示名）：content（换行）关键词：keywords（没有写无）；只用于下一条：是/否」；edit「i. 修改设定 #n（种类名，全班 / 给 显示名）（换行）改前：cur.content 的前 100 字（换行）改后：content（换行）关键词…；只用于下一条…」；种类名 memory→记忆、note→作者注、card→关键词卡；末尾一行「范围：本科目（助手不改「全部科目」的设定）」
  伪代码 返回 {"ok": errors 为空则 1 否则 0, "errors": …, "normalized": …（ok 为 0 时为空对象）, "title": …, "preview": …}

公开 函数 执行设定草稿 payload_json current_user current_role? auth_mode? subject?
  返回 {items, snapshot, done, total, error}；确认 setting_save 草稿时逐条调 teacher_rules 的写函数（P1b）；items 即写进 result 的 items，snapshot 是写进草稿 snapshot 列的对象（没有修改条目时为空串）；error 是第一个失败的原文；不抛错（被调函数的错误都记进对应条目）；不写草稿表（落库归 assist_draft.确认草稿）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 payload_json 是草稿的 payload（校验设定草稿 的 normalized），字典或它的 JSON 文本，先解析，不再校验
  伪代码 按 payload.settings 的顺序逐条执行，前一条失败不影响后一条（D2）；调用 teacher_rules 的函数一律带 subject=subject_id、不传 scope（落在本科目），权限已由 assist_draft.确认草稿 按 need=write 校验，不传角色和登录模式（同 P1 的 保存传达）
  伪代码 op=add：调用 teacher_rules.保存设定 kind=该条 kind content=该条 content current_user=current_user student=该条 student keywords=该条 keywords once=该条 once subject=subject_id 出错时 e（不传 setting_id：新建，enabled=1）；成功记 {op: add, setting_id: 返回的 id, label: 「新建 种类名（全班 / 给 显示名）」, ok: 1, error: "", written: 返回值里的 {kind, student, keywords, content, once, enabled}, undo: ""}；失败记 {…, setting_id: "", ok: 0, error: e 的原文, written: {}, undo: ""}
  伪代码 op=edit：先调用 teacher_rules.取设定 setting_id=target_id subject=subject_id 出错时 e（确认那一刻的改前值；生成后被删了报 404 → 这一条失败，error=e 的原文）；取到的行 subject_id 等于 0（生成后被负责人改成了全部科目）→ 这一条失败「设定 #n 是全部科目的设定，助手不能改」，不调写函数；否则调用 teacher_rules.保存设定 setting_id=target_id kind=该条 kind content=该条 content current_user=current_user student=该条 student keywords=该条 keywords once=该条 once subject=subject_id 出错时 e（不传 scope：不改所属科目；保存设定 不改 enabled）；成功记 op=edit、written=返回值，并把 {"setting_id": n, "before": 取到的行的 {kind, student, keywords, content, once, enabled}} 追加进 snapshot.settings；写失败记 ok=0，不进 snapshot
  伪代码 返回 {"items": …, "snapshot": snapshot.settings 为空时空串否则 {"settings": …}, "done": ok=1 的条数, "total": 条数, "error": 第一个失败的原文或空串}

公开 函数 撤销设定草稿 result_json snapshot_json current_user current_role? auth_mode? subject?
  返回 {items, undone, total, error}；撤销 setting_save 草稿（P1b，D3：被他人改过的设定不撤）；items 是更新了 undo 的 result.items；undone 是本次撤掉的条数；total 是 ok=1 的条数；不写草稿表（落库归 assist_draft.撤销草稿）
  报错 409 设定已被改动，不能撤销
  报错 409 设定已被删除，不能恢复
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 result_json、snapshot_json 是草稿的 result、snapshot 列（字典或 JSON 文本，先解析；snapshot 为空串当没有修改条目）；current_user 是草稿所属教师（assist_draft.撤销草稿 只许本人撤，等于 draft.teacher）
  伪代码 要撤的是 result.items 里 ok 等于 1 且 undo 为空的条目（partial 里失败的不撤；上次没撤完的只处理剩下的）；改前值按 setting_id 从 snapshot_json 的 settings 取
  伪代码 先逐条检查、不写库：调用 teacher_rules.取设定 setting_id=该 setting_id subject=subject_id 出错时 e。报 404：op=add 的记 undo=gone（老师已在设定页删掉，算撤掉）；op=edit 的记阻断「设定 #n 已被删除」（恢复等于重建，不做）。取到：把当前行的 kind、student、keywords、content、once、enabled 与该条 written 逐键比（按文本比，整数 1 与 "1" 相等），有一个不等记阻断「设定 #n 在确认后被改过」（别人改过内容、停用过都算）；当前行 subject_id 不等于本科目（被负责人改成了「全部科目」0）同样记阻断「设定 #n 已被改成全部科目」——下面的 删除设定 / 保存设定 不传 auth_mode，teacher_rules 的 own 校验不生效，必须在这里挡，否则协作教师撤销会删或改到全部科目的设定
  伪代码 有阻断：一条都不动（上一步记的 gone 也不生效），有「改过」或「改成全部科目」的报错 409 设定已被改动，不能撤销，只有「已被删除」的报错 409 设定已被删除，不能恢复；文案后面接全部阻断原因（如「（设定 #3 在确认后被改过；设定 #5 已被删除）」，用「；」连）
  伪代码 都通过：按 items 倒序执行。op=add：调用 teacher_rules.删除设定 setting_id=该 setting_id subject=subject_id 出错时 e，成功 undo=deleted，报 404 undo=gone；op=edit：调用 teacher_rules.保存设定 setting_id=该 setting_id kind=before.kind content=before.content current_user=current_user student=before.student keywords=before.keywords once=before.once subject=subject_id 出错时 e，成功 undo=restored（version 会再加 1；enabled 不用恢复：确认时 保存设定 没改它，检查时又确认了它没变）；其它错误记进该条 error，undo 保持空串，继续下一条
  伪代码 返回 {"items": …, "undone": 本次 undo 变为非空的条数, "total": ok=1 的条数, "error": 第一条撤销失败的原文或空串}

## 用例
用例 设定候选_分本科目和全部科目
  先 数据 teacher_rules_setting kind=note student=空 keywords=空 content=本科目的 enabled=1 once=0 version=1 author=t1 updated_at=2025-12-31 subject_id=1
  先 数据 teacher_rules_setting kind=note student=空 keywords=空 content=全部科目的 enabled=1 once=0 version=1 author=t1 updated_at=2025-12-31 subject_id=0
  调用 设定候选
  得 有返回

用例 校验设定草稿_新建合法
  调用 校验设定草稿 payload_json={"title":"加一条作者注","settings":[{"kind":"note","content":"多鼓励少批评","once":1}]}
  得 ok=1
  库 teacher_rules_setting 共 0 行

用例 校验设定草稿_改全部科目的被拒
  先 数据 teacher_rules_setting kind=note student=空 keywords=空 content=旧内容 enabled=1 once=0 version=1 author=t1 updated_at=2025-12-31 subject_id=0
  调用 校验设定草稿 payload_json={"settings":[{"target_id":1,"content":"新内容"}]}
  得 ok=0

用例 校验设定草稿_学生找不到
  先 数据 account_user username=s1 password_hash=x display_name=小明 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 校验设定草稿 payload_json={"settings":[{"kind":"memory","content":"喜欢动漫","student":"张三"}]}
  得 ok=0

用例 执行设定草稿_新建和修改
  先 数据 teacher_rules_setting kind=note student=空 keywords=空 content=旧内容 enabled=1 once=0 version=1 author=t1 updated_at=2025-12-31 subject_id=1
  调用 执行设定草稿 payload_json={"settings":[{"op":"add","target_id":"","kind":"memory","content":"喜欢动漫","student":"","student_name":"","keywords":"","once":0},{"op":"edit","target_id":1,"kind":"note","content":"新内容","student":"","student_name":"","keywords":"","once":0}]} current_user=t1
  得 done=2 total=2
  库 teacher_rules_setting 共 2 行
  库 teacher_rules_setting 含 id=1 content=新内容 version=2 subject_id=1
  库 teacher_rules_setting 含 kind=memory content=喜欢动漫 enabled=1 author=t1 subject_id=1

用例 执行设定草稿_修改目标已被删记失败
  调用 执行设定草稿 payload_json={"settings":[{"op":"add","target_id":"","kind":"memory","content":"喜欢动漫","student":"","student_name":"","keywords":"","once":0},{"op":"edit","target_id":9,"kind":"note","content":"新内容","student":"","student_name":"","keywords":"","once":0}]} current_user=t1
  得 done=1 total=2
  库 teacher_rules_setting 共 1 行

用例 撤销设定草稿_删新建恢复修改
  先 数据 teacher_rules_setting kind=note student=空 keywords=空 content=新内容 enabled=1 once=0 version=2 author=t1 updated_at=2025-12-31 subject_id=1
  先 数据 teacher_rules_setting kind=memory student=空 keywords=空 content=喜欢动漫 enabled=1 once=0 version=1 author=t1 updated_at=2025-12-31 subject_id=1
  调用 撤销设定草稿 result_json={"items":[{"op":"edit","setting_id":1,"label":"x","ok":1,"error":"","written":{"kind":"note","student":"","keywords":"","content":"新内容","once":0,"enabled":1},"undo":""},{"op":"add","setting_id":2,"label":"x","ok":1,"error":"","written":{"kind":"memory","student":"","keywords":"","content":"喜欢动漫","once":0,"enabled":1},"undo":""}]} snapshot_json={"settings":[{"setting_id":1,"before":{"kind":"note","student":"","keywords":"","content":"旧内容","once":0,"enabled":1}}]} current_user=t1
  得 undone=2 total=2
  库 teacher_rules_setting 共 1 行
  库 teacher_rules_setting 含 id=1 kind=note content=旧内容 subject_id=1

用例 撤销设定草稿_被别人改过409
  先 数据 teacher_rules_setting kind=note student=空 keywords=空 content=别人又改了 enabled=1 once=0 version=3 author=t3 updated_at=2025-12-31 subject_id=1
  先 数据 teacher_rules_setting kind=memory student=空 keywords=空 content=喜欢动漫 enabled=1 once=0 version=1 author=t1 updated_at=2025-12-31 subject_id=1
  调用 撤销设定草稿 result_json={"items":[{"op":"edit","setting_id":1,"label":"x","ok":1,"error":"","written":{"kind":"note","student":"","keywords":"","content":"新内容","once":0,"enabled":1},"undo":""},{"op":"add","setting_id":2,"label":"x","ok":1,"error":"","written":{"kind":"memory","student":"","keywords":"","content":"喜欢动漫","once":0,"enabled":1},"undo":""}]} snapshot_json={"settings":[{"setting_id":1,"before":{"kind":"note","student":"","keywords":"","content":"旧内容","once":0,"enabled":1}}]} current_user=t1
  报错 409
  库 teacher_rules_setting 共 2 行
  库 teacher_rules_setting 含 id=1 content=别人又改了
