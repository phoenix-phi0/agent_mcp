模块 quiz
依赖 kg lesson progress subject

## 表
表 quiz_question
  question_no 文本 题号，全局唯一（跨科目也不能重号）；不得含英文逗号或空白（asked_nos 按逗号拼接、拆分）
  course 文本 课程，可空
  level 文本 等级，本科目等级之一（subject.科目等级；日语 N5/N4/N3/N2/N1）
  category 文本 考点类别（如接续题）
  stem 长文本 题干
  options 长文本 选项文字，用 ^ 隔开，按位置依次对应字母 A B C…（字母不写进文字里）；非选择题为空，可空
  answer 文本 标准答案（选择题是题库原字母，如 A；非选择题是标准写法）
  accepted 文本 可接受写法，用 ^ 隔开，可空
  explain 长文本 解析，可空
  item_code 文本 所属表达方式条目编号（来自 kg_item）
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 quiz_progress 学习记录
  learner 文本 学习者；learner + subject_id 唯一
  level 文本 上次选的等级，可空
  category 文本 上次选的考点类别，可空
  current_no 文本 当前题题号，可空
  answered 整数 当前题是否已答（1/0）
  right_count 整数 这一轮答对几道
  asked_nos 长文本 这一轮出过的题号，英文逗号连接，可空
  asked_count 整数 这一轮第几道（已出题数）
  mode 文本 空=按等级考点自由练；lesson=按课练；review=复习薄弱点，可空
  lesson_code 文本 在练的课（按课练时有值），可空
  round_start_id 整数 这一轮起点（开轮时该学习者 progress_answer 的最大 id），即轮次标识
  seq 整数 每出一题加 1 的序号，用作选项打乱的随机种子
  last_correct 整数 当前题（或刚答完的题）判题结果 1/0
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 页面字段
页面 quiz_view 做题页面
  pick_level 文本 等级（下拉选项来自 level_options：「全部」加上本科目等级，即 subject.科目等级 的 options）
  pick_kind 枚举 全部,挖空,意思,接续,找错句 考点
  given 文本 接续题的作答内容

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400、need 不对报 400，原样抛出）

函数 首个有题等级 pick_kind subject_id
  返回 {level}；做题页选「全部」等级时，按本科目等级顺序找到的第一个有题的等级（开始页面、课文页面共用）
  报错 404 没有可出的题
  伪代码 调用 subject.科目等级 subject_id=subject_id 得 levels；按 levels 的顺序逐级找（pick_kind 为空或「全部」查 app.db quiz_q_free_all，否则查 quiz_q_free_cat；都只数本科目 subject_id 的题），返回第一个有题的等级 {"level": 该等级}
  伪代码 全都没有题，报错 404 没有可出的题
  伪代码 日语科目（或没有 subject_info 行、levels 为空串）等级是 N5,N4,N3,N2,N1，行为同旧

函数 编号前缀检查 subject_id code
  返回 {ok}
  报错 400 编号要以「<编码>.」开头
  伪代码 subject_id 等于 1（日语）：直接返回 {"ok": 1}，旧编号不动
  伪代码 否则按 subject_id 查 subject_info 的 code（科目编码，查询 quiz_subject_code）；编码为空、或 code 不匹配 ^[a-z][a-z0-9_]*\.[A-Za-z0-9_-]+$、或 code 不以「<编码>.」开头，报错 400 编号要以「<编码>.」开头（文案里的 <编码> 换成真实编码）
  伪代码 返回 {"ok": 1}

函数 是助手题号 subject_id code
  返回 {is_ta}；1 是教师助手出的题的题号（M4，题号由 assist_draft 确认出题草稿时生成），0 不是
  伪代码 subject_id 等于 1（日语）：code 匹配 ^ta[0-9]+-[0-9]+$ 为 1（如 ta12-3：草稿 12 的第 3 题）
  伪代码 其它科目：按 subject_id 查 subject_info 的 code（科目编码，查询 quiz_subject_code），code 匹配 ^<编码>\.ta[0-9]+-[0-9]+$ 为 1（如 math.ta12-3）；编码查不到为 0
  伪代码 其余为 0；只读，不报错

函数 取轮大小 mode
  返回 整数，这一轮的题数
  伪代码 mode 等于 lesson 返回 5，否则返回 10

函数 洗牌顺序 n seq
  返回 字符串，n 个下标 0..n-1 的排列用英文逗号连接，第 k 项表示显示位置 k 上放的是原第几个选项（下标从 0 起）
  伪代码 arr = [0,1,...,n-1]，state = seq
  伪代码 i 从 n-1 递减到 1：state = (state * 1103515245 + 12345) 对 2147483648 取余；j = state 对 (i+1) 取余；交换 arr[i] 与 arr[j]
  伪代码 返回 arr 用英文逗号连接（例如 n=2、seq=1 得 "1,0"）

函数 组题面 question_no seq subject_id
  返回 {question_no, course, level, category, stem, is_choice, options}；options 是 [{letter, text}]（已按 seq 打乱，letter 为显示字母 A B C…），非选择题为空列表；不含答案；题号查不到返回空
  伪代码 按 question_no 和 subject_id 查 quiz_question 一行，查不到（包括属于别的科目）返回空
  伪代码 options 字段为空：is_choice=0，options 为空列表
  伪代码 否则按 ^ 拆成 n 个文字，is_choice=1；order = 洗牌顺序 n=n seq=seq；显示位置 k 的选项 = {letter: 第 k 个字母(A=0), text: 原第 order[k] 个文字}
  伪代码 返回题面对象（绝不带 answer、accepted、explain）

函数 选题 learner mode level category lesson_code asked_nos asked_count new_seq subject_id
  返回 {question_no}；没有可出的题返回空
  伪代码 科目：只在本科目（subject_id）的题里挑：下面所有对 quiz_question 的查询都带 subject_id 等于入参，调用 kg./lesson./progress. 的函数一律带 subject=subject_id
  伪代码 asked 为 asked_nos 按英文逗号拆开的题号集合；used_items 为 asked 中每个题号在 quiz_question 里的 item_code 集合（一轮里每个条目只出一题）
  伪代码 「可出」指：题号不在 asked，且 item_code 不在 used_items
  伪代码 mode 为空（自由练）：取 quiz_question 中 level 相等的行（category 不为空时再要求 category 相等），按 id 升序，留下可出的，数量为 0 返回空；否则取第 ((new_seq - 1) 对数量取余) 个（从 0 起），返回其题号
  伪代码 mode 等于 lesson：调用 按课候选条目 lesson_code=lesson_code asked_count=asked_count subject_id=subject_id，得到有序条目编号列表；依次取每个条目在 quiz_question 中 item_code 相等的行（按 id 升序），找到第一个可出的题就返回其题号；都没有返回空
  伪代码 mode 等于 review：依次构造候选题号列表（按顺序，去重）：
  伪代码 (1) 调用 progress.列低分点 learner=learner subject=subject_id，对返回的每个 point_code 调用 kg.按知识点列条目 point_code=该编号 subject=subject_id，取这些条目在 quiz_question 中的题（按条目顺序、id 升序）
  伪代码 (2) 调用 progress.列错题 learner=learner subject=subject_id，按返回顺序取每条 question_no（只保留在 quiz_question 中存在的）
  伪代码 (3) 调用 progress.列久未做已掌握点 learner=learner subject=subject_id，对返回的每个 point_code 同 (1) 取题
  伪代码 按候选顺序取第一个可出的题返回其题号，没有返回空

函数 按课候选条目 lesson_code asked_count subject_id
  返回 条目编号有序列表
  伪代码 科目：subject_id 是调用方已解析的科目编号，调用 kg./lesson. 的函数一律带 subject=subject_id（别的科目的课、条目取不到）
  伪代码 调用 lesson.取课文 code=lesson_code subject=subject_id，查不到（包括属于别的科目）返回空列表
  伪代码 调用 lesson.取课文关联条目 lesson_code=lesson_code subject=subject_id，得本课条目 own（取不到则为空）
  伪代码 asked_count 等于 0（本轮第一题）：返回 own 的条目编号（本课 1 道）
  伪代码 否则：先收易混对比条目——对 own 每个条目调用 kg.列对照 code=该条目编号 subject=subject_id，取每行不等于该条目的另一端，调用 kg.取条目 code=该另一端编号 subject=subject_id 能取到的才算条目，且不在 own 里，去重
  伪代码 再收同级条目——调用 lesson.列课文 series_code=本课 series_code level=本课 level subject=subject_id，对每一课（跳过本课）调用 lesson.取课文关联条目 lesson_code=该课编号 subject=subject_id，取其条目编号，不在 own 里，去重，追加在易混对比条目之后
  伪代码 返回合并后的有序列表（易混对比在前，同级条目在后）

函数 出下一题 learner subject_id
  返回 {finished, question, asked_count, round_size, right_count}；finished 为 1 表示本轮已出满或再无可出的题，此时 question 为空串；否则 question 是 组题面 的对象
  报错 404 没有可出的题
  伪代码 科目：subject_id 是调用方已解析的科目编号（整数），本函数不再解析科目；下面所有查询和写入都只限这个 subject_id，调用 选题、组题面 时带 subject_id=subject_id，调用 kg./lesson./progress. 的函数时带 subject=subject_id
  伪代码 读 quiz_progress 该 learner 在科目 subject_id（入参）下的行 r（调用方保证存在），round_size = 取轮大小 mode=r.mode
  伪代码 r.asked_count 不小于 round_size，返回 {"finished": 1, "question": "", "asked_count": r.asked_count, "round_size": round_size, "right_count": r.right_count}
  伪代码 new_seq = r.seq + 1；调用 选题 learner=learner mode=r.mode level=r.level category=r.category lesson_code=r.lesson_code asked_nos=r.asked_nos asked_count=r.asked_count new_seq=new_seq subject_id=subject_id
  伪代码 选题 返回空：r.asked_count 等于 0 报错 404 没有可出的题；否则返回 finished=1 的对象（不改库）
  伪代码 在一个事务里更新 quiz_progress 该行：current_no=选中的题号，answered=0，last_correct=0，asked_nos=（原为空则只写题号，否则原值+","+题号），asked_count+1，seq=new_seq
  伪代码 返回 {"finished": 0, "question": 组题面(question_no=选中题号, seq=new_seq, subject_id=subject_id), "asked_count": 新 asked_count, "round_size": round_size, "right_count": r.right_count}

函数 开新轮 learner mode level category lesson_code subject_id
  返回 同 出下一题；调用方已校验参数，mode 为空表示自由练
  报错 404 没有可出的题
  伪代码 科目：subject_id 是调用方已解析的科目编号（整数），本函数不再解析科目；下面所有查询和写入都只限这个 subject_id，调用 选题、组题面 时带 subject_id=subject_id，调用 kg./lesson./progress. 的函数时带 subject=subject_id
  伪代码 调用 progress.取区间作答 learner=learner start_id=0 subject=subject_id，取 max_id 作为 round_start_id
  伪代码 在一个事务里：
  伪代码 按 learner 和科目 subject_id（入参）查 quiz_progress：没有则插入 (learner, subject_id, level, category, current_no 空, answered=0, right_count=0, asked_nos 空, asked_count=0, mode, lesson_code, round_start_id, seq=0, last_correct=0)
  伪代码 有则更新：current_no 置空、answered=0、right_count=0、asked_nos 置空、asked_count=0、mode、lesson_code、round_start_id（seq 不动）；mode 为空（自由练）时同时更新 level、category 为入参，其它模式 level、category 保持原值
  伪代码 调用 出下一题 learner=learner subject_id=subject_id，出错（如 404）整个事务回滚、本函数原样报错
  伪代码 返回 出下一题 的结果

公开 函数 导入题库 file_path learner? current_role? auth_mode? subject?
  返回 {ok, total, imported, skipped, skipped_nos, kept}；total 是有效行数，imported 是写入题数，skipped 是条目对不上而没进库的题数，skipped_nos 是这些题号用英文逗号连接（报告里说明），kept 是本科目保留下来的助手题数（D13）
  报错 400 导入文件有错
  报错 400 ta 格式的题号留给教师助手
  报错 400 题库有坏题
  报错 400 编号要以「<编码>.」开头
  报错 400 题号不能含逗号或空白
  报错 400 题号已被其他科目使用
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject），四个都不传得 1，行为同旧（init_data 固定导入 1 号科目）；写操作传 need=write，auth_mode 等于 on 时只有该科目的负责/协作教师可导入，公共科目的其他教师、学生报 403 没有权限修改该科目；下面所有查询和写入都只限这个 subject_id；调用 kg. 的函数时带 subject=subject_id（已解析，不再校验）
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略；没有有效行报错 400 导入文件有错
  伪代码 每行格式「题号|课程|等级|考点类别|题干|选项|标准答案|可接受写法|解析|条目编号」，用 | 分隔；选项和可接受写法内部用 ^ 隔开；前 7 项必须出现，后 3 项可省略或为空
  伪代码 题干里的换行转义：文件按行拆，所以题干里要换行时写字面的两个字符 \n（反斜杠加小写 n）；入库前把题干从左到右还原：连着的两个反斜杠 \\ 还原成一个字面反斜杠，\n 还原成一个真换行（char(10)），其它字符（包括后面不是 n 也不是反斜杠的单个反斜杠）原样保留；存库的 stem 是还原后的文本。要在题干里表示字面的 \n 两个字符，写 \\n。只处理题干，选项、答案、可接受写法、解析不做还原。可在插入时用 SQL 的 replace 与 char(10) 完成（先把 \\ 换成一个题干里不会出现的占位字符，再把 \n 换成 char(10)，最后把占位字符换回一个反斜杠）
  伪代码 做题页面的题卡 stem 原样带真换行（组题面 返回的 stem、card.stem 都不再做任何处理）。实现注意：题干可能含换行、双引号、反斜杠，不能写在 JSON 字面量的引号里（如 "stem": "{q.stem}"，含换行或引号时整个字面量解析失败、退化成文本，题卡会显示成未替换的占位）；组题面、拼题卡 要先把不含 stem 的字面量存进变量，用 设 对象 = 解析JSON {变量} 得到真正的字典（字面量变量本身只是文本，直接对它 设 对象.stem 会丢掉其余字段），再 设 对象.stem = {…} 单独写入题干
  伪代码 坏题：字段数少于 7、题号为空、标准答案为空、同一文件内题号重复、等级（第 3 列，去首尾空白）为空或不在本科目等级里（调用 subject.科目等级 subject_id=subject_id 的 levels；日语是 N5–N1，旧题库不受影响）；出现任一，报错 400 题库有坏题（整批不写，库保持原样）；等级不对时报错文案是「题库有坏题：第{行号}行等级{等级}不在本科目等级（{本科目等级用 / 连接}）里」（行号是文件里的第几行，从 1 起，含空行和 # 行；报第一个不对的）
  伪代码 题号字符：每行题号含英文逗号或任一空白字符（空格、制表符等），报错 400 题号不能含逗号或空白，整批不写（asked_nos 按英文逗号拼接和拆分，题号含逗号会让已出题集合错乱）；先于前缀检查
  伪代码 题号前缀：每行题号调用本模块 编号前缀检查 subject_id=subject_id code=题号（日语 subject_id=1 豁免，其它科目要以「<科目编码>.」开头），不符报错 400 编号要以「<编码>.」开头，整批不写
  伪代码 助手题号（D13）：每行题号调用本模块 是助手题号 subject_id=subject_id code=题号，任一行 is_ta 为 1，报错 400 ta 格式的题号留给教师助手，整批不写（文件里不许出现助手题号，这样保留下来的助手题不会和文件撞号）；在前缀检查之后
  伪代码 跨科目重号：题号全局唯一；任一题号已存在于别的科目（quiz_question 中 subject_id 不等于本科目）的行里，报错 400 题号已被其他科目使用，整批不写（本科目自己的旧题会被整表重灌覆盖，不算重号；本科目保留的助手题都是助手题号，文件里不会有）
  伪代码 条目编号为空，或调用 kg.取条目 code=条目编号 subject=subject_id 取不到（包括属于别的科目）：这一题不进库，计入 skipped 与 skipped_nos
  伪代码 在一个事务里：只删除 quiz_question 中 subject_id 等于本科目、且题号不是助手题号（是助手题号 为 0）的行（按科目重灌，别的科目的题不动；本科目的助手题保留，D13；kept 为保留下来的助手题数），再逐题插入其余题 (question_no, course, level, category, stem, options, answer, accepted, explain, item_code, subject_id)；然后清理本科目失效进度（同一事务内）：把 quiz_progress 中 subject_id 等于本科目、current_no 不为空、且 current_no 已不在 quiz_question 本科目的行重置为 current_no 空、answered=0、last_correct=0（level、category、mode、lesson_code、right_count、asked_nos、asked_count、round_start_id、seq 保持不动，学习者回到「未出当前题」状态，点下一题/再来一轮即可继续，不会卡在 404/400）；别的科目的 quiz_progress 行一律不动，current_no 仍指向存在的题的行也不动
  伪代码 返回 {"ok": 1, "total": 有效行数, "imported": 写入数, "skipped": 跳过数, "skipped_nos": 逗号连接, "kept": 保留的助手题数}

公开 函数 追加题目 rows_json learner? current_role? auth_mode? subject?
  返回 {ok, imported, question_nos}；imported 是写入题数，question_nos 是写入的题号按 rows 顺序用英文逗号连接。给 assist_draft 确认出题草稿用（M4）：只插入、不删旧题、不动 quiz_progress；整批要么全写、要么全不写
  报错 400 题目列表不对
  报错 400 题库有坏题
  报错 400 题号不能含逗号或空白
  报错 400 编号要以「<编码>.」开头
  报错 400 追加的题号必须是助手题号
  报错 400 条目不存在
  报错 409 题号已存在
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号，权限由调用方已校验），四个都不传得 1；写操作传 need=write，auth_mode 等于 on 时只有该科目的负责/协作教师能写，公共科目的其他教师、学生报 403 没有权限修改该科目；下面所有查询和写入都只限这个 subject_id；调用 kg. 的函数时带 subject=subject_id
  伪代码 rows_json 是题目列表（列表，或它的 JSON 文本，先解析）；每项 {question_no, course?, level, category, stem, options?, answer, accepted?, explain?, item_code}，字段含义与 quiz_question 列相同：options、accepted 是用 ^ 隔开的文本（选择题的 answer 是字母 A B C…，按 options 位置）；解析失败、不是列表、为空列表、或超过 20 项，报错 400 题目列表不对
  伪代码 校验全部做完才写库，任一不过整批不写，按下面顺序报第一个错：
  伪代码 ①坏题：question_no、level、category、stem、answer、item_code 任一去首尾空白后为空；level 不在本科目等级里（调用 subject.科目等级 subject_id=subject_id 的 levels）；同一批里题号重复；options 不为空时拆出的选项少于 2 个或多于 6 个、或有空选项、或有重复选项；options 不为空时 answer 不是 A 到第 n 个字母之一（n 为选项数）——报错 400 题库有坏题
  伪代码 ②题号字符：含英文逗号或任一空白字符，报错 400 题号不能含逗号或空白
  伪代码 ③题号前缀：调用本模块 编号前缀检查 subject_id=subject_id code=题号，不符原样报 400 编号要以「<编码>.」开头
  伪代码 ④助手题号：调用本模块 是助手题号 subject_id=subject_id code=题号，is_ta 为 0，报错 400 追加的题号必须是助手题号（题号由调用方给：日语 ta<草稿号>-<序号>，其它科目 <编码>.ta<草稿号>-<序号>；本函数只收助手题号，与导入题库的老师题号分开）
  伪代码 ⑤条目：调用 kg.取条目 code=item_code subject=subject_id 取不到（包括属于别的科目），报错 400 条目不存在（不像导入题库那样跳过）
  伪代码 ⑥同号：任一题号已在 quiz_question 里（不论科目），报错 409 题号已存在
  伪代码 在一个事务里逐题插入 (question_no, course, level, category, stem, options, answer, accepted, explain, item_code, subject_id)；stem 原样入库（不做 \n 转义还原：调用方给的是真换行）；插入出错（如并发撞了唯一约束）整批回滚并原样抛出
  伪代码 返回 {"ok": 1, "imported": 写入数, "question_nos": 逗号连接}

公开 函数 删助手题目 question_nos learner? current_role? auth_mode? subject?
  返回 {ok, deleted}；给 assist_draft 撤销出题草稿用（M4）：只删本科目的助手题，整批要么全删、要么全不删
  报错 400 题号列表不能为空
  报错 400 只能删助手题目
  报错 404 没有这道题
  报错 409 已有学生做过这道题，不能删除
  报错 409 有学生正在做这道题，不能删除
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；入参约定同 追加题目；下面所有查询和写入都只限这个 subject_id
  伪代码 question_nos 按英文逗号拆开、去首尾空白、去掉空项、去重；拆完为空，报错 400 题号列表不能为空
  伪代码 每个题号调用本模块 是助手题号 subject_id=subject_id code=题号，任一 is_ta 为 0，报错 400 只能删助手题目（老师导入的题不能经这里删）
  伪代码 任一题号在 quiz_question 里查不到 subject_id 等于本科目的行（包括属于别的科目），报错 404 没有这道题
  伪代码 任一题号在 progress_answer 里有 question_no 相等且 subject_id 等于本科目的行（任何学习者；直读 progress 的表，只读，quiz 已依赖 progress），报错 409 已有学生做过这道题，不能删除
  伪代码 任一题号是 quiz_progress 中本科目某行的 current_no，或在其 asked_nos（英文逗号连接）里，报错 409 有学生正在做这道题，不能删除
  伪代码 在一个事务里删除这些题号在本科目的 quiz_question 行
  伪代码 返回 {"ok": 1, "deleted": 删除数}

公开 函数 取做题状态 learner current_role? auth_mode? subject?
  返回 {learner, started, mode, level, category, lesson_code, current_no, answered, right_count, asked_count, round_size, last_correct, round_key, question}；mode 为 free/lesson/review；question 是当前题的 组题面 对象（含已打乱选项，不含答案），没有当前题时为空串；没有进度行时 started=0、数字项为 0、字符串项为空串、mode=free、round_size=10
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 quiz_progress，没有则返回上述默认对象（started=0）
  伪代码 有则 started=1，mode 库里空值转为 free，round_size = 取轮大小，round_key = round_start_id
  伪代码 current_no 不为空时 question = 组题面 question_no=current_no seq=该行 seq subject_id=subject_id（题已不在库则为空串），否则空串
  伪代码 返回上述对象

公开 函数 开始 learner mode? level? category? lesson_code? current_role? auth_mode? subject?
  返回 同 出下一题：{finished, question, asked_count, round_size, right_count}
  报错 400 mode 不合法
  报错 400 等级不能为空
  报错 400 等级不在本科目里
  报错 400 lesson_code 不能为空
  报错 404 没有这课
  报错 404 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 mode 不为空、不等于 free、lesson、review 之一，报错 400 mode 不合法；mode 为空或 free 视为自由练（库里存空）
  伪代码 自由练：level 为空报错 400 等级不能为空；level 不在本科目等级里（调用 subject.科目等级 subject_id=subject_id 的 levels），报错 400 等级不在本科目里；category 为空表示该等级不限考点
  伪代码 按课练：lesson_code 为空报错 400 lesson_code 不能为空；调用 lesson.取课文 code=lesson_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这课
  伪代码 复习薄弱点：不需要 level、category、lesson_code
  伪代码 调用 开新轮 learner=learner mode=（自由练传空，否则 lesson/review） level=level category=category lesson_code=（按课练传 lesson_code，否则空） subject_id=subject_id
  伪代码 返回其结果（第一题已出）

公开 函数 下一题 learner current_role? auth_mode? subject?
  返回 同 出下一题；finished 为 1 表示本轮结束，没有新题
  报错 400 还没有开始
  报错 400 先答完当前题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 quiz_progress，没有报错 400 还没有开始
  伪代码 current_no 不为空且 answered 不等于 1，报错 400 先答完当前题
  伪代码 调用 出下一题 learner=learner subject_id=subject_id，返回其结果

公开 函数 提交答案 learner answer pass_line? fall_line? current_role? auth_mode? subject?
  返回 {ok, repeated, question_no, correct, correct_answer, explain, round_done, right_count, asked_count, round_size, score, mastered, changed, point_code}；changed 取自 progress.记作答 的 changed（1 表示本次新记了一行得分），point_code 是该题知识点编号；correct_answer 选择题是正确选项在本次显示中的字母，非选择题是标准答案；round_done 为 1 表示这是本轮最后一题；repeated 为 1 表示这道题已交过、本次不再计分（此时不写任何表，score、mastered、point_code 为空串，changed 为 0）
  报错 400 答案不能为空
  报错 400 还没有出题
  报错 404 题目不存在
  报错 404 题目对不上条目
  报错 400 分数线不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 answer 去掉首尾空白后为空，报错 400 答案不能为空
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 quiz_progress，没有或 current_no 为空，报错 400 还没有出题；判的永远是库里的 current_no，不接收前端题号
  伪代码 按 current_no 和 subject_id 查 quiz_question，查不到（包括属于别的科目）报错 404 题目不存在
  伪代码 选择题（options 不为空，n=选项个数，order = 洗牌顺序 n=n seq=该行 seq，出题和判题算出同一个顺序）：取 answer 去空白转大写后出现的第一个 A–Z 字母，位置 pos=字母序号；没有字母或 pos 不小于 n 则 correct=0、stored_answer=去空白后的原答案；否则原字母 = 第 order[pos] 个选项的字母，correct = 原字母等于标准答案（去空白转大写），stored_answer = 原字母（库里存题库原字母）
  伪代码 选择题的 correct_answer：标准答案的序号 s，找 order 中值为 s 的位置 k，取第 k 个字母；序号越界则取标准答案原文
  伪代码 非选择题（接续题等）：answer 去首尾空白后整段比对，等于标准答案，或等于 accepted 按 ^ 拆开后某一项（各项也去首尾空白）则 correct=1，否则 0（只认标准答案和可接受写法）；stored_answer=去空白后的答案；correct_answer=标准答案
  伪代码 该行 answered 等于 1（同一道题交两次只算一次）：不写库，返回 {"ok": 1, "repeated": 1, "question_no": current_no, "correct": last_correct, "correct_answer": ..., "explain": 解析, "round_done": ..., "right_count": ..., "asked_count": ..., "round_size": ..., "score": "", "mastered": "", "changed": 0, "point_code": ""}
  伪代码 调用 kg.取条目 code=题目的 item_code subject=subject_id，取不到（包括属于别的科目）报错 404 题目对不上条目；取其 point_code
  伪代码 在一个事务里（记作答流水、更新掌握汇总、重算得分、更新掌握标记与本模块进度一起成功或一起失败）：
  伪代码 调用 progress.记作答 learner=learner point_code=该 point_code question_no=current_no correct=correct answer=stored_answer pass_line=pass_line fall_line=fall_line subject=subject_id（流水、掌握汇总、得分都记在当前科目），得到 score、mastered、changed（其报错如 400 分数线不合法原样向上抛，整个事务不写）
  伪代码 更新 quiz_progress 该行：answered=1、right_count=right_count+correct、last_correct=correct
  伪代码 round_size = 取轮大小 mode=该行 mode，round_done = asked_count 不小于 round_size 则 1 否则 0
  伪代码 返回 {"ok": 1, "repeated": 0, "question_no": current_no, "correct": correct, "correct_answer": ..., "explain": 解析, "round_done": round_done, "right_count": 新值, "asked_count": asked_count, "round_size": round_size, "score": score, "mastered": mastered, "changed": changed, "point_code": 该 point_code}

公开 函数 再来一轮 learner current_role? auth_mode? subject?
  返回 同 出下一题
  报错 400 还没有开始
  报错 404 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 quiz_progress，没有报错 400 还没有开始
  伪代码 调用 开新轮 learner=learner mode=该行 mode level=该行 level category=该行 category lesson_code=该行 lesson_code subject_id=subject_id（沿用上一轮的模式、等级、考点、课）
  伪代码 返回其结果

公开 函数 取本轮作答 learner current_role? auth_mode? subject?
  返回 {learner, round_key, start_id, mode, lesson_code, total, answers}；round_key 是轮次标识（这一轮起点 id）；answers 同 progress.取区间作答 的 answers；没有进度行时 round_key=0、start_id=0、mode=free、lesson_code 为空串、total=0、answers 为空列表
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 quiz_progress，没有则返回上述默认对象
  伪代码 调用 progress.取区间作答 learner=learner start_id=该行 round_start_id subject=subject_id，得 total 和 answers
  伪代码 mode 库里空值转为 free
  伪代码 返回 {"learner": learner, "round_key": round_start_id, "start_id": round_start_id, "mode": mode, "lesson_code": lesson_code, "total": total, "answers": answers}

公开 函数 取当前轮次信息 learner current_role? auth_mode? subject?
  返回 {learner, has_round, mode, lesson_code, level, category, round_key, asked_count, round_size, right_count, answered}；mode 为 free/lesson/review；没有进度行时 has_round=0、mode=free、round_size=10、其余数字为 0、字符串为空串
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 quiz_progress，没有则返回默认对象
  伪代码 有则 has_round=1，mode 空值转 free，round_size=取轮大小，round_key=round_start_id，其余取该行字段
  伪代码 返回上述对象

函数 拼题卡 question
  返回 {card, qtype}；把 组题面 的题面对象拼成页面题卡：card 是 {code, head, stem, options}，options 每项 {key, text}（前端选项组件按 key 认选项、把 key 写进表单提交），qtype 是 选择 / 接续
  伪代码 card 的 code 取 question 的 question_no，head=「{level}・{category}」，stem 取题干
  伪代码 is_choice 等于 1：qtype=选择，options 逐项由 {letter, text} 转成 {key: letter, text: text}；否则 qtype=接续，options 为空列表
  伪代码 返回 {"card": card, "qtype": qtype}

函数 按课轮尾 lesson_code stat subject_id
  返回 {text, more, back, explain}；按课练一轮做完时卡上那句说明和三个链接地址（地址空前端不画；界面名用编码写法，与原页一致）：换一课回教材页、回教材看这一课、请老师讲这课
  伪代码 科目：subject_id 是调用方已解析的科目编号，调用 lesson. 的函数带 subject=subject_id
  伪代码 调用 lesson.取课文 code=lesson_code subject=subject_id，得 title
  伪代码 text=「这一轮做完了（{stat}）。再来一轮会换一道本课的题，对比题也换；也可以换一课，或者回教材再看看这一课。」
  伪代码 more=#%E6%95%99%E6%9D%90，back=#%E6%95%99%E6%9D%90?lesson={lesson_code}，explain=#%E9%97%AE%E8%80%81%E5%B8%88?lesson={lesson_code}
  伪代码 返回上述对象

函数 复习薄弱点文案 learner subject_id
  返回 顶栏范围说明文本：有低分点为「复习薄弱点：标题1、标题2、标题3」，没有为「复习薄弱点」
  伪代码 科目：subject_id 是调用方已解析的科目编号，调用 progress./kg. 的函数一律带 subject=subject_id
  伪代码 调用 progress.列低分点 learner=learner limit=3 subject=subject_id，逐个调用 kg.取知识点 code=编号 subject=subject_id 取 title（取不到用编号）
  伪代码 有标题则用「、」连接拼「复习薄弱点：…」，否则返回「复习薄弱点」

公开 函数 做题页面 learner current_role? auth_mode? subject?
  返回 {stat, form, level_options}；做题页「进入时」的整页状态（进页面不推题卡、不动 phase/card/round/summary，只回顶栏成绩和顶栏下拉回填）：stat 是「这一轮 答对/已出」文本，没做过题为空串；form 是 {pick_level, pick_kind}，取库里上次选的等级考点，没选过填「全部」；level_options 是等级下拉选项（调用 subject.科目等级 subject_id=subject_id 的 options）。做题页所有回整页的函数（做题页面、开始页面、判答案页面、下一题页面、再来一轮页面、课文页面，含 noreview 和 end 分支）的返回都带这个键（前端下拉「选项来自 level_options」；引擎约定进界面时前端会先清空 lists，漏一个下拉就可能变空）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 调用 取做题状态 learner=learner subject=subject_id，得 started、right_count、asked_count、level、category
  伪代码 started 等于 1 则 stat=「这一轮 {right_count}/{asked_count}」否则空串；form 的 pick_level 取 level、pick_kind 取 category，为空填「全部」；level 不在本科目等级里（比如科目改过等级）时 pick_level 也填「全部」
  伪代码 返回 {"stat": stat, "form": {"pick_level": pick_level, "pick_kind": pick_kind}, "level_options": 科目等级 options}

公开 函数 开始页面 learner pick_level? pick_kind? current_role? auth_mode? subject?
  返回 做题页「开始」的整页状态：出题为 {phase, qtype, card, scope, stat, cheer, score_change, round, summary, form}，phase=ask、card 新题卡、round 四键空串、cheer/score_change 空串、summary 空串（收起上一轮总结卡）、scope 空串（自由练顶栏不显示范围）；form 回填本次所选（「全部」或具体等级考点）
  报错 404 没有可出的题
  报错 404 没有这课
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 pick_level 为空取「全部」、pick_kind 为空取「全部」（页面下拉默认就是全部）
  伪代码 等级确定：pick_level 不是「全部」直接用它（不在本科目等级里时由 开始 报 400 等级不在本科目里）；是「全部」则调用本模块 首个有题等级 pick_kind=pick_kind subject_id=subject_id（按 subject.科目等级 的 levels 顺序逐级找第一个有题的等级，全都没有报错 404 没有可出的题）
  伪代码 调用 开始 learner=learner level=等级 category=（pick_kind 为「全部」传空，否则原值） subject=subject_id，得 finished、question、asked_count、right_count（400/404 原样向上抛）
  伪代码 调用 拼题卡 question 得 card、qtype；返回 {"phase": "ask", "qtype": qtype, "card": card, "scope": "", "stat": "这一轮 {right_count}/{asked_count}", "cheer": "", "score_change": "", "round": {"text": "", "more": "", "back": "", "explain": ""}, "summary": "", "form": {"pick_level": pick_level, "pick_kind": pick_kind}, "level_options": subject.科目等级 subject_id=subject_id 的 options}

公开 函数 判答案页面 learner choice? given? current_role? auth_mode? subject?
  返回 做题页「作答」判完的整页状态：{phase, card, stat, cheer, score_change}；phase=done，card 是判完的题卡（options 每项补 state：答案那项 right、选错的 wrong、其余 dim；mine 是本次作答；verdict 一行结论；explain 解析末尾拼「考的是」），cheer 达标喜报、score_change 得分变化文本，都没有为空串；另带 level_options（同 做题页面）
  报错 400 答案不能为空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 调用 取做题状态 learner=learner subject=subject_id，得 started、question；作答取值同旧页：默认取 given，question 不为空且 is_choice 等于 1 则取 choice（两个键都可能留着旧值，按题型取才不会拿错）
  伪代码 取做题状态 得到的 question 为空（started 为 1 但题已不在库）时，跳过下面取旧分这一步（prev_score 不取），直接往下调 提交答案，由 提交答案 报 404（本页不自己报）
  伪代码 先取作答前旧分：由 question_no（取做题状态 得到的 question.question_no）查 app.db quiz_q_by_no 得 item_code（限本科目 subject_id），调 kg.取条目 code=item_code subject=subject_id 取 point_code；调用 progress.列得分 learner=learner subject=subject_id，取该 point_code 那一行的 score 作 prev_score，没有这一行（该知识点作答前从未记过分）prev_score 视为 0；这一步必须在 提交答案 之前（提交答案 内部的 记作答 会写新得分行）
  伪代码 调用 提交答案 learner=learner answer=作答 subject=subject_id，得 repeated、question_no、correct、correct_answer、explain、right_count、asked_count、score、changed、point_code（400/404 原样向上抛）
  伪代码 card 用 拼题卡 按 question 重建（和作答前同一张，code 不变不翻页）；选择题 options 逐项补 state：letter 等于 correct_answer 记 right、等于本次所交字母记 wrong、其余 dim；card 的 mine=本次作答；verdict=correct 等于 1 则「○ 答对了」否则「✗ 正确答案是 {correct_answer}」；explain 末尾拼「\n\n考的是：条目名」（查 app.db quiz_q_by_no 得 item_code，查询限本科目 subject_id；调 kg.取条目 code=item_code subject=subject_id 取 name），有课文再拼「　课文《标题》summary」（调 lesson.按条目列课文 item_code=item_code subject=subject_id 取第一课，取不到课就不拼那半句）；传参（K170）：拼接用的 quiz_explain_tail 的 expl（解析）、name（条目名）、lt（课文半句）装进对象用 查一值表 传，不得按位置 expl={…} 传——解析是题库原文、常以换行结尾，条目名、课文 summary 是库里的自由文本，按位置传引擎对首尾有空白的值直接报错（作答页 500）；解析原样拼、不去空白
  伪代码 cheer、score_change 以本次 提交答案 的返回为准，不再用 列得分 作答后的 prev_score/delta（作答后再取最新两行，得分没变时会把更早一次的 delta 重显，首次记分时 delta 为 0 又漏掉）：repeated 等于 1（同题交两次），或 changed 等于 0（本次没新记得分行，得分没变），cheer、score_change 都为空串；否则新分 = 提交答案 返回的 score，旧分 = 上面作答前取的 prev_score，title 调 kg.取知识点 code=point_code subject=subject_id 取（取不到用编号）：score_change=「{title} 得分 {prev_score} → {score}」；prev_score 小于 80 且 score 不小于 80 则 cheer=「「{title}」达标了，图上它后面的知识点可能解锁了。」（首次记分作答前没有得分行，prev_score 视为 0，所以首次直接达标也会触发 cheer）
  伪代码 stat=「这一轮 {right_count}/{asked_count}」；返回 {"phase": "done", "card": card, "stat": stat, "cheer": cheer, "score_change": score_change, "level_options": subject.科目等级 subject_id=subject_id 的 options}

公开 函数 下一题页面 learner current_role? auth_mode? subject?
  返回 做题页「下一题」的整页状态，形状同 开始页面：出题 phase=ask（card 新题卡、round 四键空串、cheer/score_change/summary 空串）；一轮做完 phase=end、round.text 按模式给说明、按课练附三个地址
  报错 400 还没有开始
  报错 400 先答完当前题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 调用 取当前轮次信息 learner=learner subject=subject_id，得 mode、lesson_code
  伪代码 scope：lesson 模式=「本课《{title}》（含对比题）」（调 lesson.取课文 code=lesson_code subject=subject_id 取标题）；review 模式=调用 复习薄弱点文案 learner=learner subject_id=subject_id；自由练=空串
  伪代码 调用 下一题 learner=learner subject=subject_id，得 finished、question、asked_count、right_count（400 原样向上抛）
  伪代码 下面两个分支的返回都再带 level_options（subject.科目等级 subject_id=subject_id 的 options，同 做题页面）
  伪代码 finished 等于 0：拼题卡，返回 {phase:ask, qtype, card, scope, stat, cheer 空, score_change 空, round 四键空, summary 空}
  伪代码 finished 等于 1：phase=end；round 按模式：lesson=调用 按课轮尾 lesson_code=lesson_code stat=stat subject_id=subject_id；review 的 text=「这一轮复习做完了（{stat}）。可以请老师总结这一轮，或者再来一轮。」；自由练的 text=「这一轮做完了（{stat}），{asked_count}道题各考一个不同的知识点。可以请老师总结这一轮，或者再来一轮。」，其余三键空串；返回 {phase:end, scope, stat, round, cheer 空, score_change 空}

公开 函数 再来一轮页面 learner current_role? auth_mode? subject?
  返回 做题页「再来一轮」的整页状态，形状与分支同 下一题页面（新一轮第一题；一轮立即做完的 end 形态也按 下一题页面 处理）
  报错 400 还没有开始
  报错 404 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 调用 取当前轮次信息 learner=learner subject=subject_id，得 mode、lesson_code；scope 同 下一题页面
  伪代码 调用 再来一轮 learner=learner subject=subject_id，得 finished、question、asked_count、right_count（400/404 原样向上抛）
  伪代码 finished 等于 0 按出题分支拼整页返回，finished 等于 1 按 end 分支拼整页返回（同 下一题页面，两个分支都带 level_options）

公开 函数 课文页面 learner lesson? mode? level? kind? current_role? auth_mode? subject?
  返回 做题页「载入」的整页状态（地址 #做题?lesson=… / #做题?mode=review / #做题?level=…&kind=… 进来时前端把地址参数并进提交调用）：形状同 开始页面（form 回填）；复习但一道都没答过为 phase=noreview 的轻状态 {phase, card, scope, cheer, score_change, round, summary, form}（除 phase/form 外全空）
  报错 400 没有课文、等级或复习模式
  报错 400 等级不在本科目里
  报错 404 没有这课
  报错 404 没有可出的题
  伪代码 所有分支（含 noreview 轻状态、出题、end）的返回都带 level_options（subject.科目等级 subject_id=subject_id 的 options，同 做题页面）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 注意：参数名 lesson 是地址参数（课文编号字符串），与模块名 lesson.（lesson.取课文 等跨模块调用）只是同形：实现里别把参数 lesson 当成模块名用，跨模块调用永远写「模块名加点加函数名」的完整形式，传课编号一律写 lesson_code=lesson；参数名不改（路由、前端 #做题?lesson=… 都依赖它）
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），三个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id（quiz_question、quiz_progress 都带 subject_id 条件）；本函数在本模块内调用其它函数（含公开函数）、调用 kg./lesson./progress. 的函数时一律带 subject=subject_id（已解析，不再校验）；调用本模块内部函数（组题面、选题、出下一题、开新轮 等）带 subject_id=subject_id
  伪代码 lesson 不为空：调用 开始 learner=learner mode=lesson lesson_code=lesson subject=subject_id，按出题分支拼整页，scope=「本课《{title}》（含对比题）」（title 调 lesson.取课文 code=lesson subject=subject_id 取）；form 回填库里等级考点（调 取做题状态 learner=learner subject=subject_id 取 level/category，空填「全部」）；lesson 本身不回填（旧口径：课文只认地址，防止离开这课后台表还带着它）
  伪代码 mode 等于 review：先调 progress.列得分 learner=learner subject=subject_id，scores 为空（一道都没答过）则不出题不报错，返回 phase=noreview、card/scope/cheer/score_change/round/summary 全空、form 的 pick_level=本科目首级（subject.科目等级 subject_id=subject_id 的 first；日语是 N5）、pick_kind=「全部」（旧口径：界面让先按等级做几道）
  伪代码 否则（有作答记录）：调用 取当前轮次信息 learner=learner subject=subject_id，has_round=1 且 mode=review 且 asked_count 小于 round_size（这轮没出够，刷新/来回切接着这轮）则调用 出下一题 learner=learner subject_id=subject_id，否则调用 开始 learner=learner mode=review subject=subject_id；按出题分支拼整页，scope=调用 复习薄弱点文案 learner=learner subject_id=subject_id；end 分支同 下一题页面（text 用复习那句）
  伪代码 lesson 为空且 mode 不等于 review：level、kind 都为空报错 400 没有课文、等级或复习模式；等级确定同 开始页面（「全部」调用本模块 首个有题等级 pick_kind=kind subject_id=subject_id，按本科目等级顺序找第一个有题的等级，全没有报错 404 没有可出的题；具体等级不在本科目里由 开始 报 400 等级不在本科目里），调用 开始 learner=learner level=等级 category=（kind 为「全部」传空否则原值） subject=subject_id，按出题分支拼整页，scope 空串，form 回填所选等级考点

## 接口
GET /quiz/state -> 取做题状态 角色 student
POST /quiz/state -> 做题页面 动作 quiz_state 模板 页面状态 表单=form 角色 student
POST /quiz/start -> 开始页面 动作 quiz_start 模板 页面状态 去处=做题 角色 student
POST /quiz/next -> 下一题页面 动作 quiz_next 模板 页面状态 角色 student
POST /quiz/answer -> 判答案页面 动作 quiz_answer 模板 页面状态 角色 student
POST /quiz/again -> 再来一轮页面 动作 quiz_again 模板 页面状态 角色 student
POST /quiz/lesson -> 课文页面 动作 quiz_lesson 模板 页面状态 表单=form 角色 student
GET /quiz/round-answers -> 取本轮作答 角色 student
GET /quiz/round -> 取当前轮次信息 角色 student
POST /quiz/import -> 导入题库 上传 file 类型 md,txt 上限 20MB 角色 teacher

## 用例
用例 导入题库_正常
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 文件 quiz/q1.md 内容=Q1|C1|N5|接续|题干一|甲^乙|A||解析一|I1
  调用 导入题库 file_path=quiz/q1.md
  得 ok=1 total=1 imported=1 skipped=0
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=Q1 level=N5 category=接续 answer=A item_code=I1

用例 导入题库_条目对不上跳过
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I9
  先 文件 quiz/q2.md 内容=Q2|C1|N5|接续|题干二|甲^乙|A||解析|NOPE
  调用 导入题库 file_path=quiz/q2.md
  得 ok=1 total=1 imported=0 skipped=1 skipped_nos=Q2
  库 quiz_question 共 0 行

用例 导入题库_缺答案整批回滚
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I9
  先 文件 quiz/q3.md 内容=Q3|C1|N5|接续|题干三|甲^乙||
  调用 导入题库 file_path=quiz/q3.md
  报错 400
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=OLD

用例 导入题库_空文件
  先 文件 quiz/empty.md 内容=#只有注释
  调用 导入题库 file_path=quiz/empty.md
  报错 400

用例 取做题状态_没开始
  调用 取做题状态 learner=me
  得 started=0 answered=0 asked_count=0 round_size=10 mode=free

用例 取做题状态_开始后
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 取做题状态 learner=me
  得 started=1 mode=free current_no=Q1 answered=0 asked_count=1 right_count=0 round_size=10

用例 开始_自由练
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  调用 开始 learner=me level=N5 category=接续
  得 finished=0 asked_count=1 round_size=10 right_count=0
  库 quiz_progress 共 1 行
  库 quiz_progress 含 learner=me level=N5 category=接续 current_no=Q1 answered=0 asked_count=1 right_count=0 round_start_id=0 seq=1

用例 开始_缺等级
  调用 开始 learner=me
  报错 400
  库 quiz_progress 共 0 行

用例 开始_mode不合法
  调用 开始 learner=me mode=abc
  报错 400

用例 开始_没有题
  调用 开始 learner=me level=N1 category=接续
  报错 404
  库 quiz_progress 共 0 行

用例 开始_按课练
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  调用 开始 learner=me mode=lesson lesson_code=L1
  得 finished=0 asked_count=1 round_size=5
  库 quiz_progress 含 learner=me mode=lesson lesson_code=L1 current_no=Q1

用例 开始_按课练_没有这课
  调用 开始 learner=me mode=lesson lesson_code=NOPE
  报错 404

用例 开始_复习薄弱点
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 数据 progress_score learner=me point_code=P1 score=40 at=2026-01-01
  调用 开始 learner=me mode=review
  得 finished=0 asked_count=1 round_size=10
  库 quiz_progress 含 learner=me mode=review current_no=Q1

用例 开始_复习没有可复习的
  先 数据 kg_point code=P1 title=点一
  调用 开始 learner=me mode=review
  报错 404
  库 quiz_progress 共 0 行

用例 下一题_正常
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干一 answer=です item_code=I1
  先 数据 quiz_question question_no=Q2 level=N5 category=接续 stem=题干二 answer=です item_code=I2
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 提交答案 learner=me answer=です
  调用 下一题 learner=me
  得 finished=0 asked_count=2 right_count=1
  库 quiz_progress 含 learner=me current_no=Q2 answered=0 asked_count=2 asked_nos=Q1,Q2 seq=2

用例 下一题_按课练取易混对比
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P1
  先 数据 kg_contrast a_code=I1 b_code=I2
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干一 answer=です item_code=I1
  先 数据 quiz_question question_no=Q2 level=N5 category=接续 stem=题干二 answer=です item_code=I2
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  先 调用 开始 learner=me mode=lesson lesson_code=L1
  先 调用 提交答案 learner=me answer=です
  调用 下一题 learner=me
  得 finished=0 asked_count=2 round_size=5
  库 quiz_progress 含 learner=me current_no=Q2 asked_count=2

用例 下一题_一个条目一轮只出一题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干一 answer=です item_code=I1
  先 数据 quiz_question question_no=Q2 level=N5 category=接续 stem=题干二 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 提交答案 learner=me answer=です
  调用 下一题 learner=me
  得 finished=1 asked_count=1
  库 quiz_progress 含 learner=me current_no=Q1 answered=1 asked_count=1

用例 下一题_当前题没答完
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 下一题 learner=me
  报错 400

用例 下一题_没开始
  调用 下一题 learner=me
  报错 400

用例 提交答案_非选择题答对
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1 explain=解析一
  先 调用 开始 learner=me level=N5 category=接续
  调用 提交答案 learner=me answer=です
  得 ok=1 repeated=0 question_no=Q1 correct=1 correct_answer=です explain=解析一 round_done=0 right_count=1 asked_count=1 round_size=10 score=100 mastered=1
  库 progress_answer 共 1 行
  库 progress_answer 含 learner=me point_code=P1 question_no=Q1 correct=1 answer=です
  库 progress_mastery 含 learner=me point_code=P1 right_count=1 total_count=1 mastered=1
  库 progress_score 含 learner=me point_code=P1 score=100
  库 quiz_progress 含 learner=me answered=1 right_count=1 last_correct=1

用例 提交答案_可接受写法
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です accepted=である^なのだ item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 提交答案 learner=me answer=である
  得 correct=1 correct_answer=です right_count=1

用例 提交答案_非选择题答错
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 提交答案 learner=me answer=だ
  得 ok=1 correct=0 right_count=0 score=0 mastered=0
  库 progress_answer 含 learner=me question_no=Q1 correct=0 answer=だ
  库 quiz_progress 含 learner=me answered=1 right_count=0 last_correct=0

用例 提交答案_选择题按打乱后字母判对
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 options=甲^乙 answer=A item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 提交答案 learner=me answer=B
  得 correct=1 correct_answer=B score=100
  库 progress_answer 含 learner=me question_no=Q1 correct=1 answer=A

用例 提交答案_选择题按打乱后字母判错
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 options=甲^乙 answer=A item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 提交答案 learner=me answer=A
  得 correct=0 correct_answer=B score=0
  库 progress_answer 含 learner=me question_no=Q1 correct=0 answer=B

用例 提交答案_同题交两次只算一次
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 提交答案 learner=me answer=です
  调用 提交答案 learner=me answer=だ
  得 ok=1 repeated=1 correct=1 right_count=1
  库 progress_answer 共 1 行
  库 quiz_progress 含 learner=me right_count=1

用例 提交答案_一轮最后一题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=0 right_count=9 asked_nos=Q1 asked_count=10 round_start_id=0 seq=1 last_correct=0
  调用 提交答案 learner=me answer=です
  得 ok=1 correct=1 round_done=1 right_count=10 asked_count=10 round_size=10

用例 提交答案_答案为空
  调用 提交答案 learner=me answer=空
  报错 400

用例 提交答案_还没出题
  调用 提交答案 learner=me answer=A
  报错 400
  库 progress_answer 共 0 行

用例 提交答案_分数线不合法回滚
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 提交答案 learner=me answer=です pass_line=150
  报错 400
  库 progress_answer 共 0 行
  库 quiz_progress 含 learner=me answered=0 right_count=0

用例 再来一轮_正常
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 提交答案 learner=me answer=です
  调用 再来一轮 learner=me
  得 finished=0 asked_count=1 right_count=0 round_size=10
  库 quiz_progress 共 1 行
  库 quiz_progress 含 learner=me current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=1 seq=2

用例 再来一轮_没开始
  调用 再来一轮 learner=me
  报错 400

用例 取本轮作答_正常
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 提交答案 learner=me answer=です
  调用 取本轮作答 learner=me
  得 round_key=0 start_id=0 mode=free total=1

用例 取本轮作答_再来一轮后只含新一轮
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 提交答案 learner=me answer=です
  先 调用 再来一轮 learner=me
  调用 取本轮作答 learner=me
  得 round_key=1 total=0

用例 取本轮作答_没开始
  调用 取本轮作答 learner=me
  得 round_key=0 total=0 mode=free

用例 取当前轮次信息_按课练
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  先 调用 开始 learner=me mode=lesson lesson_code=L1
  调用 取当前轮次信息 learner=me
  得 has_round=1 mode=lesson lesson_code=L1 round_size=5 asked_count=1 right_count=0 answered=0 round_key=0

用例 取当前轮次信息_没有进度
  调用 取当前轮次信息 learner=me
  得 has_round=0 mode=free round_size=10 asked_count=0 right_count=0

用例 做题页面_没开始
  调用 做题页面 learner=me
  得 有返回

用例 开始页面_全部等级找到有题的
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  调用 开始页面 learner=me
  得 phase=ask qtype=接续
  库 quiz_progress 共 1 行
  库 quiz_progress 含 learner=me level=N5 mode=空 current_no=Q1

用例 判答案页面_接续题答对
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1 explain=解析一
  先 调用 开始 learner=me level=N5 category=接续
  调用 判答案页面 learner=me given=です
  得 phase=done
  库 progress_answer 共 1 行
  库 progress_answer 含 learner=me question_no=Q1 correct=1

用例 判答案页面_选择题按显示字母
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 options=甲^乙 answer=A item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 判答案页面 learner=me choice=B
  得 phase=done
  库 progress_answer 含 learner=me question_no=Q1 correct=1 answer=A

用例 下一题页面_一轮做完
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 判答案页面 learner=me given=です
  调用 下一题页面 learner=me
  得 phase=end

用例 再来一轮页面_正常
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  先 调用 判答案页面 learner=me given=です
  调用 再来一轮页面 learner=me
  得 phase=ask
  库 quiz_progress 含 learner=me asked_count=1 right_count=0

用例 课文页面_按课
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  调用 课文页面 learner=me lesson=L1
  得 phase=ask
  库 quiz_progress 含 learner=me mode=lesson lesson_code=L1

用例 课文页面_复习没记录
  调用 课文页面 learner=me mode=review
  得 phase=noreview

用例 课文页面_复习有记录
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 数据 progress_score learner=me point_code=P1 score=40 at=2026-01-01
  调用 课文页面 learner=me mode=review
  得 phase=ask
  库 quiz_progress 含 learner=me mode=review

用例 课文页面_什么都没带
  调用 课文页面 learner=me
  报错 400

用例 跨科目_开始只出本科目的题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=日语题 answer=です item_code=I1
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  调用 开始 learner=me level=N5 category=接续 subject=2
  得 finished=0 asked_count=1 round_size=10
  库 quiz_progress 共 1 行
  库 quiz_progress 含 learner=me current_no=math.q1 subject_id=2

用例 跨科目_开始日语的题对2号科目不可见
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=日语题 answer=です item_code=I1
  调用 开始 learner=me level=N5 category=接续 subject=2
  报错 404
  库 quiz_progress 共 0 行

用例 跨科目_取做题状态只看本科目
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=0
  调用 取做题状态 learner=me subject=2
  得 started=0 asked_count=0 mode=free

用例 跨科目_取做题状态本科目的进度
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=math.q1 answered=0 right_count=0 asked_nos=math.q1 asked_count=1 round_start_id=0 seq=1 last_correct=0 subject_id=2
  调用 取做题状态 learner=me subject=2
  得 started=1 current_no=math.q1 asked_count=1

用例 跨科目_提交答案记在当前科目的进度
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 调用 开始 learner=me level=N5 category=接续 subject=2
  调用 提交答案 learner=me answer=2 subject=2
  得 ok=1 repeated=0 question_no=math.q1 correct=1 right_count=1 score=100
  库 progress_answer 含 learner=me point_code=math.a question_no=math.q1 correct=1 subject_id=2
  库 progress_score 含 learner=me point_code=math.a score=100 subject_id=2
  库 quiz_progress 含 learner=me answered=1 right_count=1 subject_id=2

用例 跨科目_提交答案别的科目的当前题当不存在
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=日语题 answer=です item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=0 subject_id=2
  调用 提交答案 learner=me answer=です subject=2
  报错 404
  库 progress_answer 共 0 行

用例 跨科目_取本轮作答只看本科目
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=5 seq=1 last_correct=0
  调用 取本轮作答 learner=me subject=2
  得 round_key=0 total=0 mode=free

用例 跨科目_再来一轮另一个科目没开始
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=1
  调用 再来一轮 learner=me subject=2
  报错 400

用例 跨科目_取当前轮次信息只看本科目
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=0
  调用 取当前轮次信息 learner=me subject=2
  得 has_round=0 mode=free round_size=10

用例 跨科目_复习薄弱点用本科目的得分
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 数据 progress_score learner=me point_code=math.a score=40 at=2026-01-01 subject_id=2
  调用 开始 learner=me mode=review subject=2
  得 finished=0 asked_count=1
  库 quiz_progress 含 learner=me mode=review current_no=math.q1 subject_id=2

用例 跨科目_复习薄弱点日语看不到2号科目的得分
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 数据 progress_score learner=me point_code=math.a score=40 at=2026-01-01 subject_id=2
  调用 开始 learner=me mode=review
  报错 404
  库 quiz_progress 共 0 行

用例 跨科目_按课练别的科目的课404
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  调用 开始 learner=me mode=lesson lesson_code=L1 subject=2
  报错 404
  库 quiz_progress 共 0 行

用例 跨科目_做题页面只回本科目的上次选择
  先 数据 quiz_progress learner=me level=N3 category=挖空 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=0 subject_id=1
  调用 做题页面 learner=me subject=2
  得 stat=空

用例 跨科目_导入题库落当前科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I9
  先 文件 quiz/m1.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/m1.md subject=2
  得 ok=1 total=1 imported=1 skipped=0
  库 quiz_question 共 2 行
  库 quiz_question 含 question_no=math.q1 item_code=math.i1 subject_id=2
  库 quiz_question 含 question_no=OLD subject_id=1

用例 跨科目_导入题库只清本科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I9
  先 数据 quiz_question question_no=math.old level=N5 category=接续 stem=旧数学题 answer=x item_code=math.i1 subject_id=2
  先 文件 quiz/m2.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/m2.md subject=2
  得 ok=1 imported=1
  库 quiz_question 共 2 行
  库 quiz_question 含 question_no=OLD subject_id=1
  库 quiz_question 含 question_no=math.q1 subject_id=2

用例 跨科目_导入题库前缀不符
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 文件 quiz/m3.md 内容=Q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/m3.md subject=2
  报错 400
  库 quiz_question 共 0 行

用例 跨科目_导入题库题号被别的科目占用
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=旧题 answer=x item_code=I9
  先 文件 quiz/m4.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/m4.md subject=2
  报错 400
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=math.q1 subject_id=1

用例 跨科目_导入题库条目在别的科目对不上
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 文件 quiz/m5.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|I1
  调用 导入题库 file_path=quiz/m5.md subject=2
  得 ok=1 total=1 imported=0 skipped=1 skipped_nos=math.q1
  库 quiz_question 共 0 行

用例 跨科目_need导入题库公开科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 文件 quiz/m6.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/m6.md learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 quiz_question 共 0 行

用例 跨科目_need导入题库学生403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 文件 quiz/m7.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/m7.md learner=s1 current_role=student auth_mode=on subject=2
  报错 403
  库 quiz_question 共 0 行

用例 跨科目_need导入题库协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 文件 quiz/m8.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/m8.md learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 total=1 imported=1
  库 quiz_question 含 question_no=math.q1 subject_id=2

用例 导入题库_题号含逗号整批不写
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I1
  先 文件 quiz/c1.md 内容=Q2,Q3|C1|N5|接续|题干二|甲^乙|A||解析|I1
  调用 导入题库 file_path=quiz/c1.md
  报错 400
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=OLD

用例 导入题库_清理本科目失效进度且不动别的科目
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=OLD answered=1 right_count=1 asked_nos=OLD asked_count=1 round_start_id=0 seq=1 last_correct=1
  先 数据 quiz_progress learner=you level=N5 category=接续 current_no=Q1 answered=1 right_count=1 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=OLD answered=1 right_count=1 asked_nos=OLD asked_count=1 round_start_id=0 seq=1 last_correct=1 subject_id=2
  先 文件 quiz/p1.md 内容=Q1|C1|N5|接续|题干一|甲^乙|A||解析|I1
  调用 导入题库 file_path=quiz/p1.md
  得 ok=1 total=1 imported=1
  库 quiz_progress 共 3 行
  库 quiz_progress 含 learner=me subject_id=1 current_no=空 answered=0 last_correct=0 right_count=1 asked_count=1
  库 quiz_progress 含 learner=you subject_id=1 current_no=Q1 answered=1 last_correct=1
  库 quiz_progress 含 learner=me subject_id=2 current_no=OLD answered=1 last_correct=1

用例 导入题库_清理失效进度之后可以继续出题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=OLD answered=1 right_count=1 asked_nos=OLD asked_count=1 round_start_id=0 seq=1 last_correct=1
  先 文件 quiz/p2.md 内容=Q1|C1|N5|接续|题干一|甲^乙|A||解析|I1
  先 调用 导入题库 file_path=quiz/p2.md
  调用 取做题状态 learner=me
  得 started=1 current_no=空 question=空

用例 导入题库_负责教师可导入
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 文件 quiz/o1.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/o1.md learner=t1 current_role=teacher auth_mode=on subject=2
  得 ok=1 total=1 imported=1 skipped=0
  库 quiz_question 含 question_no=math.q1 subject_id=2

用例 导入题库_科目不存在404
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 quiz/n9.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/n9.md learner=t1 current_role=teacher auth_mode=on subject=9
  报错 404
  库 quiz_question 共 0 行

用例 导入题库_科目不是数字400
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 quiz/na.md 内容=math.q1|C1|N5|接续|题干一|甲^乙|A||解析一|math.i1
  调用 导入题库 file_path=quiz/na.md subject=abc
  报错 400
  库 quiz_question 共 0 行

用例 提交答案_返回changed和知识点
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题干 answer=です item_code=I1
  先 调用 开始 learner=me level=N5 category=接续
  调用 提交答案 learner=me answer=です
  得 ok=1 changed=1 point_code=P1 score=100

用例 跨科目_按课练2号科目只出2号的题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=日语题 answer=です item_code=I1
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_item_link lesson_code=L1 item_code=I1
  先 数据 lesson_text code=math.L1 level=N5 title=代数课 examples_edited=0 series_code=mathbook seq=1 subject_id=2
  先 数据 lesson_item_link lesson_code=math.L1 item_code=math.i1 subject_id=2
  调用 开始 learner=me mode=lesson lesson_code=math.L1 subject=2
  得 finished=0 asked_count=1 round_size=5
  库 quiz_progress 共 1 行
  库 quiz_progress 含 learner=me mode=lesson lesson_code=math.L1 current_no=math.q1 subject_id=2

用例 跨科目_按课练1号看不到2号的课
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 数据 lesson_text code=math.L1 level=N5 title=代数课 examples_edited=0 series_code=mathbook seq=1 subject_id=2
  先 数据 lesson_item_link lesson_code=math.L1 item_code=math.i1 subject_id=2
  调用 开始 learner=me mode=lesson lesson_code=math.L1
  报错 404
  库 quiz_progress 共 0 行

用例 跨科目_下一题2号科目只出2号的题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=日语题 answer=です item_code=I1
  先 数据 kg_item code=I2 name=条目二 point_code=P1
  先 数据 quiz_question question_no=Q2 level=N5 category=接续 stem=日语题二 answer=です item_code=I2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 数据 quiz_question question_no=math.q2 level=N5 category=接续 stem=数学题二 answer=2 item_code=math.i1 subject_id=2
  先 调用 开始 learner=me level=N5 category=接续 subject=2
  先 调用 提交答案 learner=me answer=2 subject=2
  调用 下一题 learner=me subject=2
  得 finished=1 asked_count=1
  库 quiz_progress 共 1 行
  库 quiz_progress 含 learner=me current_no=math.q1 asked_count=1 asked_nos=math.q1 subject_id=2

用例 跨科目_下一题1号不受2号进度影响
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=日语题 answer=です item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=math.q1 answered=1 right_count=1 asked_nos=math.q1 asked_count=1 round_start_id=0 seq=1 last_correct=1 subject_id=2
  调用 下一题 learner=me
  报错 400
  库 quiz_progress 含 learner=me current_no=math.q1 subject_id=2

用例 跨科目_组题面别的科目的当前题题面为空
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=日语题 answer=です item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=0 subject_id=2
  调用 取做题状态 learner=me subject=2
  得 started=1 current_no=Q1 question=空

用例 跨科目_组题面本科目的当前题有题面
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=math.q1 level=N5 category=接续 stem=数学题 answer=2 item_code=math.i1 subject_id=2
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=math.q1 answered=0 right_count=0 asked_nos=math.q1 asked_count=1 round_start_id=0 seq=1 last_correct=0 subject_id=2
  调用 取做题状态 learner=me subject=2
  得 started=1 current_no=math.q1

用例 追加题目_不删旧题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=旧题一 answer=A item_code=I1
  先 数据 quiz_question question_no=Q2 level=N5 category=接续 stem=旧题二 answer=A item_code=I1
  先 数据 quiz_question question_no=Q3 level=N5 category=接续 stem=旧题三 answer=A item_code=I1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"助手题一","options":"甲^乙","answer":"A","item_code":"I1"},{"question_no":"ta1-2","level":"N5","category":"接续","stem":"助手题二","options":"甲^乙^丙","answer":"C","accepted":"丙","explain":"解析","item_code":"I1"}]
  得 ok=1 imported=2 question_nos=ta1-1,ta1-2
  库 quiz_question 共 5 行
  库 quiz_question 含 question_no=Q1
  库 quiz_question 含 question_no=ta1-2 options=甲^乙^丙 answer=C item_code=I1 subject_id=1

用例 追加题目_不动做题进度
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=旧题一 answer=A item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=0 right_count=0 asked_nos=Q1 asked_count=1 round_start_id=0 seq=1 last_correct=0
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"助手题一","options":"甲^乙","answer":"A","item_code":"I1"}]
  得 ok=1 imported=1
  库 quiz_progress 含 learner=me current_no=Q1 asked_nos=Q1 asked_count=1

用例 追加题目_同号冲突409整批不写
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=已有助手题 answer=A item_code=I1
  调用 追加题目 rows_json=[{"question_no":"ta1-2","level":"N5","category":"接续","stem":"新题","options":"甲^乙","answer":"A","item_code":"I1"},{"question_no":"ta1-1","level":"N5","category":"接续","stem":"撞号","options":"甲^乙","answer":"A","item_code":"I1"}]
  报错 409
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=ta1-1 stem=已有助手题

用例 追加题目_题号被别的科目占用409
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=别科目的题 answer=A item_code=x subject_id=2
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"新题","options":"甲^乙","answer":"A","item_code":"I1"}]
  报错 409
  库 quiz_question 共 1 行

用例 追加题目_同批重号是坏题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"一","options":"甲^乙","answer":"A","item_code":"I1"},{"question_no":"ta1-1","level":"N5","category":"接续","stem":"二","options":"甲^乙","answer":"B","item_code":"I1"}]
  报错 400
  库 quiz_question 共 0 行

用例 追加题目_缺答案是坏题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"一","options":"甲^乙","answer":"","item_code":"I1"}]
  报错 400
  库 quiz_question 共 0 行

用例 追加题目_选择题答案越界是坏题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"一","options":"甲^乙","answer":"C","item_code":"I1"}]
  报错 400
  库 quiz_question 共 0 行

用例 追加题目_选项重复是坏题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"一","options":"甲^甲","answer":"A","item_code":"I1"}]
  报错 400
  库 quiz_question 共 0 行

用例 追加题目_空列表
  调用 追加题目 rows_json=[]
  报错 400

用例 追加题目_不是JSON
  调用 追加题目 rows_json=abc
  报错 400

用例 追加题目_非助手题号400
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"Q9","level":"N5","category":"接续","stem":"一","options":"甲^乙","answer":"A","item_code":"I1"}]
  报错 400
  库 quiz_question 共 0 行

用例 追加题目_题号含逗号400
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1,ta1-2","level":"N5","category":"接续","stem":"一","options":"甲^乙","answer":"A","item_code":"I1"}]
  报错 400
  库 quiz_question 共 0 行

用例 追加题目_条目不存在整批不写
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"一","options":"甲^乙","answer":"A","item_code":"I1"},{"question_no":"ta1-2","level":"N5","category":"接续","stem":"二","options":"甲^乙","answer":"A","item_code":"NOPE"}]
  报错 400
  库 quiz_question 共 0 行

用例 跨科目_追加题目条目在别的科目400
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"一","options":"甲^乙","answer":"A","item_code":"math.i1"}]
  报错 400
  库 quiz_question 共 0 行

用例 跨科目_追加题目其它科目带编码前缀
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=初一,初二 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 追加题目 rows_json=[{"question_no":"math.ta3-1","level":"初一","category":"计算","stem":"一","options":"1^2","answer":"B","item_code":"math.i1"}] subject=2
  得 ok=1 imported=1 question_nos=math.ta3-1
  库 quiz_question 含 question_no=math.ta3-1 subject_id=2

用例 跨科目_追加题目其它科目缺编码前缀400
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=初一,初二 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 追加题目 rows_json=[{"question_no":"ta3-1","level":"初一","category":"计算","stem":"一","options":"1^2","answer":"B","item_code":"math.i1"}] subject=2
  报错 400
  库 quiz_question 共 0 行

用例 跨科目_追加题目公开科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=初一,初二 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 追加题目 rows_json=[{"question_no":"math.ta3-1","level":"初一","category":"计算","stem":"一","options":"1^2","answer":"B","item_code":"math.i1"}] learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 quiz_question 共 0 行

用例 跨科目_追加题目学生403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=初一,初二 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 追加题目 rows_json=[{"question_no":"math.ta3-1","level":"初一","category":"计算","stem":"一","options":"1^2","answer":"B","item_code":"math.i1"}] learner=s1 current_role=student auth_mode=on subject=2
  报错 403
  库 quiz_question 共 0 行

用例 跨科目_追加题目协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=初一,初二 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  调用 追加题目 rows_json=[{"question_no":"math.ta3-1","level":"初一","category":"计算","stem":"一","options":"1^2","answer":"B","item_code":"math.i1"}] learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1 imported=1
  库 quiz_question 含 question_no=math.ta3-1 subject_id=2

用例 删助手题目_正常
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=老师的题 answer=A item_code=I1
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=助手题一 answer=A item_code=I1
  先 数据 quiz_question question_no=ta1-2 level=N5 category=接续 stem=助手题二 answer=A item_code=I1
  调用 删助手题目 question_nos=ta1-1,ta1-2
  得 ok=1 deleted=2
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=Q1

用例 删助手题目_已被作答409整批不删
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=助手题一 answer=A item_code=I1
  先 数据 quiz_question question_no=ta1-2 level=N5 category=接续 stem=助手题二 answer=A item_code=I1
  先 数据 progress_answer learner=s1 point_code=P1 question_no=ta1-2 correct=1 at=2026-01-01
  调用 删助手题目 question_nos=ta1-1,ta1-2
  报错 409
  库 quiz_question 共 2 行

用例 删助手题目_在本轮题单里409
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=助手题一 answer=A item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=Q1 answered=1 right_count=1 asked_nos=Q1,ta1-1 asked_count=2 round_start_id=0 seq=2 last_correct=1
  调用 删助手题目 question_nos=ta1-1
  报错 409
  库 quiz_question 共 1 行

用例 删助手题目_是当前题409
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=助手题一 answer=A item_code=I1
  先 数据 quiz_progress learner=me level=N5 category=接续 current_no=ta1-1 answered=0 right_count=0 asked_nos=ta1-1 asked_count=1 round_start_id=0 seq=1 last_correct=0
  调用 删助手题目 question_nos=ta1-1
  报错 409
  库 quiz_question 共 1 行

用例 删助手题目_老师的题不能删
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=老师的题 answer=A item_code=I1
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=助手题一 answer=A item_code=I1
  调用 删助手题目 question_nos=ta1-1,Q1
  报错 400
  库 quiz_question 共 2 行

用例 删助手题目_题号为空
  调用 删助手题目 question_nos=空
  报错 400

用例 跨科目_删助手题目别的科目的题404
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=别科目同号 answer=A item_code=x subject_id=2
  调用 删助手题目 question_nos=ta1-1
  报错 404
  库 quiz_question 共 1 行

用例 跨科目_删助手题目公开科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=初一,初二 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 quiz_question question_no=math.ta1-1 level=初一 category=计算 stem=一 answer=A item_code=math.i1 subject_id=2
  调用 删助手题目 question_nos=math.ta1-1 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 quiz_question 共 1 行

用例 导入题库_保留助手题
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I1
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=助手题 answer=A item_code=I1
  先 文件 quiz/k1.md 内容=Q1|C1|N5|接续|题干一|甲^乙|A||解析|I1
  调用 导入题库 file_path=quiz/k1.md
  得 ok=1 total=1 imported=1 kept=1
  库 quiz_question 共 2 行
  库 quiz_question 含 question_no=ta1-1 stem=助手题
  库 quiz_question 无 question_no=OLD

用例 导入题库_文件里有助手题号整批不写
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=OLD level=N5 category=接续 stem=旧题 answer=x item_code=I1
  先 文件 quiz/k2.md 内容=Q1|C1|N5|接续|题干一|甲^乙|A||解析|I1\nta5-1|C1|N5|接续|题干二|甲^乙|A||解析|I1
  调用 导入题库 file_path=quiz/k2.md
  报错 400
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=OLD

用例 跨科目_导入题库保留本科目助手题不动别科目
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=初一,初二 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 quiz_question question_no=ta1-1 level=N5 category=接续 stem=日语助手题 answer=A item_code=I1
  先 数据 quiz_question question_no=math.old level=初一 category=计算 stem=旧数学题 answer=A item_code=math.i1 subject_id=2
  先 数据 quiz_question question_no=math.ta2-1 level=初一 category=计算 stem=数学助手题 answer=A item_code=math.i1 subject_id=2
  先 文件 quiz/k3.md 内容=math.q1|C1|初一|计算|题干一|1^2|A||解析|math.i1
  调用 导入题库 file_path=quiz/k3.md subject=2
  得 ok=1 imported=1 kept=1
  库 quiz_question 共 3 行
  库 quiz_question 含 question_no=ta1-1 subject_id=1
  库 quiz_question 含 question_no=math.ta2-1 subject_id=2
  库 quiz_question 无 question_no=math.old

用例 开始页面_自定义等级全部按科目顺序逐级
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=进阶 category=接续 stem=难题 answer=です item_code=I1
  先 数据 quiz_question question_no=Q2 level=基础 category=接续 stem=中题 answer=です item_code=I1
  调用 开始页面 learner=me pick_level=全部
  得 phase=ask
  库 quiz_progress 含 learner=me level=基础 current_no=Q2

用例 开始页面_自定义等级指定一级
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=进阶 category=接续 stem=难题 answer=です item_code=I1
  先 数据 quiz_question question_no=Q2 level=基础 category=接续 stem=中题 answer=です item_code=I1
  调用 开始页面 learner=me pick_level=进阶
  得 phase=ask
  库 quiz_progress 含 learner=me level=进阶 current_no=Q1

用例 开始页面_自定义等级全没题404
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=旧题 answer=です item_code=I1
  调用 开始页面 learner=me pick_level=全部
  报错 404

用例 开始_等级不在本科目里400
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=旧题 answer=です item_code=I1
  调用 开始 learner=me level=N5 category=接续
  报错 400
  库 quiz_progress 共 0 行

用例 课文页面_等级不在本科目里400
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=旧题 answer=です item_code=I1
  调用 课文页面 learner=me level=N5
  报错 400

用例 导入题库_等级不在本科目里整批400
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=OLD level=入门 category=接续 stem=旧题 answer=x item_code=I1
  先 文件 quiz/lv1.md 内容=Q1|C1|N5|接续|题干一|甲^乙|A||解析一|I1
  调用 导入题库 file_path=quiz/lv1.md
  报错 400
  库 quiz_question 共 1 行
  库 quiz_question 含 question_no=OLD

用例 导入题库_自定义等级正常导入
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 文件 quiz/lv2.md 内容=Q1|C1|基础|接续|题干一|甲^乙|A||解析一|I1
  调用 导入题库 file_path=quiz/lv2.md
  得 ok=1 imported=1
  库 quiz_question 含 question_no=Q1 level=基础

用例 追加题目_等级不在本科目里400
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"N5","category":"接续","stem":"助手题一","options":"甲^乙","answer":"A","item_code":"I1"}]
  报错 400
  库 quiz_question 共 0 行

用例 追加题目_自定义等级正常写入
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 追加题目 rows_json=[{"question_no":"ta1-1","level":"入门","category":"接续","stem":"助手题一","options":"甲^乙","answer":"A","item_code":"I1"}]
  得 ok=1 imported=1
  库 quiz_question 含 question_no=ta1-1 level=入门
