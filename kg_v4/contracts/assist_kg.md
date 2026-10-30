模块 assist_kg
依赖 kg subject

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，need=write 且没有写权限报 403 没有权限修改该科目，原样抛出）。本模块不传 need：执行、撤销函数会写别的模块的业务表，但写权限由调用方 assist_draft 的 确认草稿 / 撤销草稿 按 need=write 校验过，它调本模块时只传 subject=已解析的科目编号（同 P1 的 teacher_rules.保存传达）

公开 函数 图谱编号前缀 learner? current_role? auth_mode? subject?
  返回 {prefix}；prefix 是本科目新建知识点、条目的编号要带的前缀（P1b；assist_draft.生成草稿 备料、本模块 校验图谱草稿 用）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 subject_id 等于 1（日语）prefix 为空串；其它科目调用 subject.科目详情 learner=learner subject_id=subject_id 取 code，prefix 为「<code>.」
  伪代码 返回 {"prefix": prefix}

函数 编号合规 code prefix
  返回 文本：编号不合规时的错误句子，合规为空串（P1b）；与 kg 的 编号格式检查 同一口径（那是 kg 的私有函数，这里照抄规则、不调用；确认时 kg.建知识点 / kg.建条目 会再查一遍，这里只为让草稿阶段就拦下）
  伪代码 code 不匹配 ^[A-Za-z0-9][A-Za-z0-9_.-]{0,59}$ 返回「编号只能用字母、数字、点、下划线、短横，最长60」；prefix 不为空且 code 不以 prefix 开头、或 prefix 后面没有字符，返回「编号要以「prefix」开头」；否则空串

公开 函数 校验图谱草稿 payload_json learner? current_role? auth_mode? subject?
  返回 {ok, errors, normalized, title, preview}；kg_add 的内容校验（P1b，assist_draft.校验草稿 分派过来）；ok 为 1 表示 errors 为空；只读，内容错误进 errors 不报错；编号由模型提、后端验（知识点、条目编号是有意义的标识，建后不可改，老师在预览里看得到）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 payload_json 是字典，或它的 JSON 文本（先解析）；解析失败或不是对象：errors=["输出不是 JSON 对象"]，直接返回 ok=0（assist_draft.校验草稿 传的是已解析的对象）；下面的 points、items、edges 指它的同名键
  伪代码 points、items、edges 三个键都可缺省（缺省当空列表），出现但不是列表记「<键> 必须是列表」；三个都空记「知识点、条目、前置边至少要有一项」；points 超过 10 个记「一份草稿最多 10 个知识点」、items 超过 30 个记「一份草稿最多 30 个条目」、edges 超过 30 条记「一份草稿最多 30 条前置边」；以上任一出错就停止逐条检查
  伪代码 调用本模块 图谱编号前缀 learner=learner subject=subject_id 得 prefix
  伪代码 逐个知识点（去首尾空白）：不是对象记「知识点 i：格式不对」；code 为空记「知识点 i：编号不能为空」；调用 编号合规 code=code prefix=prefix 不为空记「知识点 code：…」；title 为空记「知识点 code：名称不能为空」、超过 60 字记「知识点 code：名称最长60字」；调用 kg.取知识点 code=code subject=subject_id 取得到记「知识点 code 已存在」；本草稿里同号出现第二次记「知识点 code 重复」
  伪代码 逐个条目：不是对象记「条目 j：格式不对」；code 为空、编号不合规、name 为空或超过 60 字、after_form 超过 60 字，各记一条（文案同知识点，前缀「条目 code：」）；调用 kg.取条目 code=code subject=subject_id 取得到记「条目 code 已存在」；本草稿里重复记「条目 code 重复」；point_code 既不是本草稿的知识点、调用 kg.取知识点 code=point_code subject=subject_id 也取不到，记「条目 code：所属知识点 point_code 不在本科目」；prev_code 不为空时必须是本草稿里排在它前面的条目，或 kg.取条目 code=prev_code subject=subject_id 取得到，否则记「条目 code：前一个条目 prev_code 不在本科目」（按顺序建，排在后面的还不存在；等于自己也算不在）
  伪代码 逐条前置边：不是对象记「前置边 k：格式不对」；pre_code 或 point_code 为空记「前置边 k：编号不能为空」；两端相同记「前置边 a→b：不能以自己为前置」；每一端既不是本草稿的知识点、kg.取知识点 也取不到，记「前置边 a→b：知识点 x 不在本科目」；本草稿里重复记「前置边 a→b 重复」；两端都是已有知识点时调用 kg.列前置 code=point_code subject=subject_id，points 里已有 pre_code 记「前置边 a→b 已存在」（已有的边不进草稿：否则撤销时会把别人建的边删掉）
  伪代码 环检查：把本草稿的边和本科目已有的边合起来看（已有知识点的后代用 kg.列后代 code=该编号 subject=subject_id 取；新知识点只有本草稿的边），对每条边从 point_code 出发向下能走到 pre_code 就记「前置边 a→b 会形成环」（确认时 kg.加前置边 还会再查）
  伪代码 normalized：{"points": [{"code", "title"}], "items": [{"code", "name", "point_code", "after_form", "prev_code"}], "edges": [{"pre_code", "point_code"}]}（顺序即确认时的执行顺序）
  伪代码 title 为空时取「加 a 个知识点、b 个条目、c 条前置边」（为 0 的部分省掉）；preview「知识点：」下每个一行「・title（code）」；「条目：」下每个一行「・name（code），属于 point_code」，有 prev_code 加「，前一个 prev_code」、有 after_form 加「，接在 after_form 后」；「前置边：」下每条一行「・pre_code → point_code」；空的那一组不写；末尾一行「编号建后不可改」
  伪代码 返回 {"ok": errors 为空则 1 否则 0, "errors": …, "normalized": …（ok 为 0 时为空对象）, "title": …, "preview": …}

公开 函数 执行图谱草稿 payload_json learner? current_role? auth_mode? subject?
  返回 {items, done, total, error}；确认 kg_add 草稿时逐条调 kg 的写函数（P1b，assist_draft.确认草稿 分派过来）；不抛错；不写草稿表（落库归 assist_draft.确认草稿）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 payload_json 是草稿的 payload（校验图谱草稿 的 normalized），字典或它的 JSON 文本，先解析，不再校验
  伪代码 顺序：先 payload.points，再 payload.items，最后 payload.edges（条目要挂在知识点上、边要两端都在）；一条失败不中断，依赖它的后续条目会被 kg 自己的检查拦下（如所属知识点没建成 → 404 没有这个知识点）、照样逐条记下（D2）；调用 kg 的函数一律带 subject=subject_id，不传角色和登录模式（权限已由 assist_draft.确认草稿 按 need=write 校验，kg 写权限口径同样是负责+协作）
  伪代码 知识点：调用 kg.建知识点 code=该 code title=该 title subject=subject_id 出错时 e，记 {type: point, code, pre_code: "", point_code: "", label: 「知识点 title（code）」, ok, error, created: "", undo: ""}（失败如 409 编号已存在 / 编号已被其他科目使用，ok=0、error=e 的原文）
  伪代码 条目：调用 kg.建条目 code=该 code name=该 name point_code=该 point_code after_form=该 after_form prev_code=该 prev_code subject=subject_id 出错时 e，记 {type: item, code, label: 「条目 name（code）」, …}
  伪代码 前置边：调用 kg.加前置边 pre_code=该 pre_code point_code=该 point_code subject=subject_id 出错时 e，记 {type: edge, code: 「pre_code>point_code」, pre_code, point_code, label: 「前置边 pre_code→point_code」, ok, error, created: 返回的 created, undo: ""}；created=0（生成后别人先加了同一条边）也算 ok=1，但撤销时不动它
  伪代码 返回 {"items": …, "done": ok=1 的条数, "total": 条数, "error": 第一个失败的原文或空串}

公开 函数 撤销图谱草稿 result_json learner? current_role? auth_mode? subject?
  返回 {items, undone, total, error}；撤销 kg_add 草稿（P1b）：只删本草稿新建、现在没被引用的知识点 / 条目 / 前置边；不写草稿表（落库归 assist_draft.撤销草稿）
  报错 409 知识点或条目已被引用，不能撤销
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；四个都不传得 1；assist_draft 调用时传 subject=已解析的科目编号（不再校验）；本函数调用其它函数时一律带 subject=subject_id
  伪代码 result_json 是草稿的 result 列（字典或 JSON 文本，先解析）；下面的 result.items 指它的 items
  伪代码 要撤的是 result.items 里 ok 等于 1 且 undo 为空的条目；type 等于 edge 的只撤 created 等于 1 的（created=0 的边不是本草稿建的，直接记 undo=gone，不删）
  伪代码 还在不在（不写库）：边调用 kg.列前置 code=point_code subject=subject_id 出错时 e，报 404 或 points 里没有 pre_code 记 gone；条目调用 kg.取条目 code=该 code subject=subject_id 为空记 gone；知识点调用 kg.取知识点 code=该 code subject=subject_id 为空记 gone；其余的是「本草稿还在的对象」own
  伪代码 引用检查（不写库）：own 里每个条目调用 kg.查引用 code=该 code kind=item subject=subject_id、每个知识点调用 kg.查引用 code=该 code kind=point subject=subject_id，得 refs；逐项按 source 处理：「教师助手对话」忽略（对话流水里记过这个点，不算引用）；条目的「后一个条目」扣掉 own 里 prev_code 等于它的条目数；知识点的「下挂条目」扣掉 own 里 point_code 等于它的条目数、「前置边」扣掉 own 里一端是它的边数（这些会一起删）；其余各项（对照、题目、课文挂接、单词、作答记录、掌握记录、得分记录、默写进度）原样算。扣完仍大于 0 的记阻断原因「编号：source n」——与 kg.删知识点 不同，别人后来加的前置边和对照也挡撤销（kg.删知识点 会把它们连带删掉，助手撤销不能删别人的东西）
  伪代码 有阻断：一条都不动（上一步记的 gone 也不生效），报错 409 知识点或条目已被引用，不能撤销（文案后面接全部原因，如「（I1：题目2；P1：前置边1）」，用「；」连、不含空格）
  伪代码 都通过：按 边 → 条目（倒序，后建的先删，前一个条目链不会挡）→ 知识点（倒序）删。边：调用 kg.删前置边 pre_code=该 pre_code point_code=该 point_code subject=subject_id 出错时 e。条目：调用 kg.删条目 code=该 code subject=subject_id 出错时 e。知识点：调用 kg.删知识点 code=该 code subject=subject_id 出错时 e。三者都：成功 undo=deleted，报 404 undo=gone，其它错误（如检查之后刚被引用，kg 自己报的 409）记进该条 error、undo 保持空串，继续下一条
  伪代码 返回 {"items": …, "undone": 本次 undo 变为非空的条数, "total": ok=1 的条数, "error": 第一条撤销失败的原文或空串}

## 用例
用例 图谱编号前缀_日语为空
  调用 图谱编号前缀
  得 prefix=空

用例 跨科目_图谱编号前缀带科目编码
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 图谱编号前缀 learner=t1 subject=2
  得 prefix=math.

用例 校验图谱草稿_合法
  先 数据 kg_point code=P1 title=点一
  调用 校验图谱草稿 payload_json={"points":[{"code":"P2","title":"点二"}],"items":[{"code":"I2","name":"条目二","point_code":"P2"}],"edges":[{"pre_code":"P1","point_code":"P2"}]}
  得 ok=1
  库 kg_point 共 1 行
  库 kg_item 共 0 行
  库 kg_edge 共 0 行

用例 校验图谱草稿_编号不合规
  调用 校验图谱草稿 payload_json={"points":[{"code":"点二","title":"点二"}]}
  得 ok=0

用例 跨科目_校验图谱草稿编号要带科目前缀
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 校验图谱草稿 payload_json={"points":[{"code":"p2","title":"方程"}]} learner=t1 subject=2
  得 ok=0

用例 执行图谱草稿_建知识点条目和前置边
  先 数据 kg_point code=P1 title=点一
  调用 执行图谱草稿 payload_json={"points":[{"code":"P2","title":"点二"}],"items":[{"code":"I2","name":"条目二","point_code":"P2","after_form":"","prev_code":""}],"edges":[{"pre_code":"P1","point_code":"P2"}]}
  得 done=3 total=3
  库 kg_point 共 2 行
  库 kg_point 含 code=P2 title=点二 subject_id=1
  库 kg_item 含 code=I2 point_code=P2 subject_id=1
  库 kg_edge 含 pre_code=P1 point_code=P2

用例 执行图谱草稿_知识点重号记失败不中断
  先 数据 kg_point code=P2 title=别人建的
  调用 执行图谱草稿 payload_json={"points":[{"code":"P2","title":"点二"},{"code":"P3","title":"点三"}],"items":[{"code":"I3","name":"条目三","point_code":"P3","after_form":"","prev_code":""}],"edges":[]}
  得 done=2 total=3
  库 kg_point 共 2 行
  库 kg_point 含 code=P2 title=别人建的
  库 kg_item 含 code=I3 point_code=P3

用例 撤销图谱草稿_删本草稿建的
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_point code=P2 title=点二
  先 数据 kg_item code=I2 name=条目二 point_code=P2
  先 数据 kg_edge pre_code=P1 point_code=P2
  调用 撤销图谱草稿 result_json={"items":[{"type":"point","code":"P2","pre_code":"","point_code":"","label":"x","ok":1,"error":"","created":"","undo":""},{"type":"item","code":"I2","pre_code":"","point_code":"","label":"x","ok":1,"error":"","created":"","undo":""},{"type":"edge","code":"P1>P2","pre_code":"P1","point_code":"P2","label":"x","ok":1,"error":"","created":1,"undo":""}]}
  得 undone=3 total=3
  库 kg_point 共 1 行
  库 kg_point 含 code=P1
  库 kg_item 共 0 行
  库 kg_edge 共 0 行

用例 撤销图谱草稿_别人加了前置边409
  先 数据 kg_point code=P2 title=点二
  先 数据 kg_point code=P3 title=别人的点
  先 数据 kg_edge pre_code=P2 point_code=P3
  调用 撤销图谱草稿 result_json={"items":[{"type":"point","code":"P2","pre_code":"","point_code":"","label":"x","ok":1,"error":"","created":"","undo":""}]}
  报错 409
  库 kg_point 共 2 行
  库 kg_edge 共 1 行
