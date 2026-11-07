模块 progress
依赖 kg lesson dictation vocab subject

## 表
表 progress_answer 学习记录
  learner 文本 学习者
  point_code 文本 知识点编号
  question_no 文本 题号
  correct 整数 是否答对（1/0）
  answer 文本 作答内容，可空
  at 文本 作答时间，格式 YYYY-MM-DD HH:MM:SS
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 progress_mastery 学习记录
  learner 文本 学习者
  point_code 文本 知识点编号；learner + point_code 唯一（point_code 全局唯一，由 kg 口径 2 的编号前缀和跨科目重号拒绝保证，所以不必把 subject_id 放进唯一键；但读写本表一律再带 subject_id 条件，防止万一撞号时两个科目的掌握状态互串）
  right_count 整数 累计答对数
  total_count 整数 累计答题数
  mastered 整数 是否已掌握（1/0）
  updated_at 文本 更新时间
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 progress_score 学习记录
  learner 文本 学习者
  point_code 文本 知识点编号
  score 整数 得分 0–100
  at 文本 打分时间
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 页面字段
页面 progress_view 学习进度页面
  verdict 文本 在学表「是否达标」列
  depth 整数 能学表「第几步」列
  item_label 文本 最近作答表「条目」列
  answers 整数 等级表「答过的题」列
  value 整数 得分表「得分」列
  delta 文本 得分表「变化」列
  form 文本 条目表「接在」列
  point 文本 接续表「功能」列


## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出；progress 的公开函数都不传 need，即按 read）

函数 核对分数线 pass_line fall_line
  返回 {pass_line, fall_line}，为空的项分别取默认 80 和 60，均为整数
  报错 400 分数线不合法
  伪代码 pass_line 为空取 80，fall_line 为空取 60
  伪代码 任一不是 0 到 100 的整数，报错 400 分数线不合法
  伪代码 fall_line 大于 pass_line，报错 400 分数线不合法
  伪代码 返回 {"pass_line": pass_line, "fall_line": fall_line}

函数 重算点 learner point_code pass_line fall_line subject_id
  返回 {score, mastered, changed}；调用方保证 progress_mastery 里已有该 learner + point_code（subject_id 等于传入值）的行；subject_id 是已解析的科目编号（整数）
  伪代码 取 progress_answer 中该 learner、该 point_code、subject_id 等于传入值的最近 10 条（按 id 降序），数量 n，答对数 r
  伪代码 score = 四舍五入(r * 100 / n)，n 为 0 时 score 为 0
  伪代码 读 progress_mastery 该行（learner + point_code + subject_id 等于传入值）的旧 mastered 记为 prev
  伪代码 prev 等于 1：score 不小于 fall_line 则 mastered=1 否则 0；prev 不等于 1：score 不小于 pass_line 则 mastered=1 否则 0（掌握看得分，不看累计正确率）
  伪代码 取 progress_score 中该 learner、该 point_code、subject_id 等于传入值的最新一行（按 id 降序第一条）
  伪代码 没有，或其 score 不等于新 score：往 progress_score 插入 (learner, point_code, score, at=当前时间, subject_id=传入值)，changed=1；否则 changed=0（变了才记一行）
  伪代码 更新 progress_mastery 该行（learner + point_code + subject_id 等于传入值）的 mastered、updated_at=当前时间
  伪代码 返回 {"score": score, "mastered": mastered, "changed": changed}

公开 函数 记作答 learner point_code question_no correct answer? pass_line? fall_line? current_role? auth_mode? subject?
  返回 {ok, total, right, score, mastered, changed}；total/right 是该学习者在该知识点的累计答题数和答对数，score 是重算后的得分，mastered 是掌握标记，changed 为 1 表示本次新记了一行得分
  报错 400 learner 不能为空
  报错 400 题号不能为空
  报错 400 correct 只能是 0 或 1
  报错 400 分数线不合法
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；调用 kg./lesson./vocab./dictation. 的函数时一律只传 subject=subject_id（已解析，不再校验）；作答流水是学习者自己的数据，不传 need（按 read）
  伪代码 learner 为空，报错 400 learner 不能为空；question_no 为空，报错 400 题号不能为空
  伪代码 correct 不是 0 也不是 1，报错 400 correct 只能是 0 或 1
  伪代码 调用 kg.取知识点 code=point_code subject=subject_id，取不到（包括编号属于别的科目）报错 404 没有这个知识点
  伪代码 调用 核对分数线 pass_line=pass_line fall_line=fall_line，得到两条线
  伪代码 在一个事务里（中途出错全部不算）：
  伪代码 往 progress_answer 插入 (learner, point_code, question_no, correct, answer, at=当前时间, subject_id=subject_id)
  伪代码 传参（K170）：answer 是学生作答原文（POST /progress/answer 直接传进来的未去空白，填空答案可能首尾带空格、换行），原样存、不去空白；插入 progress_answer 的参数一律装进对象用 写库表 传，不得按位置 answer={…} 传（首尾有空白按位置传引擎直接报错）
  伪代码 按 learner + point_code + subject_id（等于本科目）查 progress_mastery：没有则插入 (right_count=correct, total_count=1, mastered=0, updated_at=当前时间, subject_id=subject_id)；有则 total_count+1、right_count+correct、updated_at=当前时间
  伪代码 调用 重算点 learner point_code 两条线 subject_id，得到 score、mastered、changed
  伪代码 事务结束后读 progress_mastery 该行（learner + point_code + subject_id 等于本科目）的 right_count、total_count
  伪代码 返回 {"ok": 1, "total": total_count, "right": right_count, "score": score, "mastered": mastered, "changed": changed}

公开 函数 取状态 learner point_code? current_role? auth_mode? subject?
  返回 {learner, total, mastered_count, unlocked_count, points}；points 是 [{code, title, right, total, mastered, score, unlocked}]，只含本科目的知识点，按知识点 id 升序；right/total 是累计答对/答题数，没记录为 0；score 是最新得分，没有为 0；unlocked 为 1 表示该点所有直接前置都已掌握（没有前置也为 1），即「现在能学」的解锁状态
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；调用 kg. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 point_code 不为空：调用 kg.取知识点 code=point_code subject=subject_id，取不到（包括编号属于别的科目）报错 404 没有这个知识点，只处理这一个点
  伪代码 point_code 为空：调用 kg.列知识点 subject=subject_id，处理本科目全部点
  伪代码 对每个点：读 progress_mastery 该 learner + point_code（subject_id 等于本科目）的行得 right、total、mastered（没有全为 0）；读 progress_score 同条件最新一行得 score（没有为 0）
  伪代码 对每个点：调用 kg.列前置 code=该点编号 subject=subject_id，所有前置在 progress_mastery 里（该 learner、subject_id 等于本科目）mastered=1 则 unlocked=1，否则 0
  伪代码 mastered_count 是 points 中 mastered=1 的个数，unlocked_count 是 unlocked=1 的个数
  伪代码 返回 {"learner": learner, "total": 点数, "mastered_count": mastered_count, "unlocked_count": unlocked_count, "points": 列表}

公开 函数 算下一步 learner current_role? auth_mode? subject?
  返回 {learner, total, next_code, points}；points 是现在能学的本科目知识点 [{code, title}]（前置都已掌握、自己还没掌握），按知识点 id 升序；next_code 是第一个的编号，没有则为空串
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它公开函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 调用 取状态 learner=learner subject=subject_id
  伪代码 从其 points 里留下 unlocked=1 且 mastered=0 的点，只取 code、title
  伪代码 返回 {"learner": learner, "total": 个数, "next_code": 第一个的 code 或空串, "points": 列表}

公开 函数 取概览 learner current_role? auth_mode? subject?
  返回 {learner, point_total, mastered_count, answer_total, right_total, accuracy, is_empty, hint}；都只算本科目；accuracy 是累计正确率百分比（四舍五入取整，没有作答为 0）；is_empty 为 1 表示本科目一道都没答过，此时 hint 为「还没有作答，先去做题吧」，否则 hint 为空串
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；调用 kg. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 调用 kg.列知识点 subject=subject_id 取 point_total
  伪代码 统计 progress_mastery 中该 learner、subject_id 等于本科目且 mastered=1 的行数为 mastered_count
  伪代码 统计 progress_answer 中该 learner、subject_id 等于本科目的行数为 answer_total、correct=1 的行数为 right_total
  伪代码 accuracy = 四舍五入(right_total * 100 / answer_total)，answer_total 为 0 时为 0
  伪代码 answer_total 为 0 则 is_empty=1 且 hint 如上，否则 is_empty=0、hint 为空串
  伪代码 返回上述对象

公开 函数 列得分 learner current_role? auth_mode? subject?
  返回 {learner, total, scores}；scores 是 [{point_code, title, score, prev_score, delta}]，本科目每个有过得分的知识点一行；score 是当前分（最新一行），prev_score 是上一行得分，没有上一行时等于 score，delta = score - prev_score；按 score 升序（分低的在前）、point_code 升序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；调用 kg. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 查 progress_score 中该 learner、subject_id 等于本科目的全部行，按 point_code 分组，各取 id 最大的两行
  伪代码 对每组计算 score、prev_score、delta；调用 kg.取知识点 code=该点编号 subject=subject_id 取 title，取不到 title 取空串
  伪代码 排序后返回 {"learner": learner, "total": 组数, "scores": 列表}

公开 函数 列最近作答 learner limit? current_role? auth_mode? subject?
  返回 {learner, total, answers}；answers 是 [{point_code, question_no, correct, answer, at}]，只含本科目，按 id 降序，最多 limit 条（默认 20）
  报错 400 limit 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id
  伪代码 limit 为空取 20；不是大于等于 1 的整数，报错 400 limit 不合法
  伪代码 查 progress_answer 中该 learner、subject_id 等于本科目的行，按 id 降序取前 limit 条
  伪代码 返回 {"learner": learner, "total": 条数, "answers": 列表}

公开 函数 按级统计掌握 learner current_role? auth_mode? subject?
  返回 {learner, covered_count, level_count, levels}；levels 是按本科目等级逐项的 [{level, mastered, total}]，项数等于本科目等级数、顺序就是 subject.科目等级 的 levels 顺序（日语仍是 5 项 N5 N4 N3 N2 N1，数值不变）；level_count 是 levels 的项数；total 是该等级下本科目的知识点数，mastered 是其中该学习者已掌握的个数；covered_count 是本科目有等级的知识点总数（点的等级取 lesson.取知识点等级，没有课文的科目按题目等级兜底；都取不到时为 0、各项全 0）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；调用 kg./lesson. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 调用 kg.列知识点 subject=subject_id 取本科目全部点
  伪代码 对每个点调用 lesson.取知识点等级 point_code=该点编号 subject=subject_id；level 为空串、或不在本科目等级里的点不计入任何等级
  伪代码 等级清单取 调用 subject.科目等级 subject_id=subject_id 的 levels；按 levels 逐项遍历，每个等级累计 total 和 mastered（读 progress_mastery 该 learner（subject_id 等于本科目）该点 mastered=1 的累计进 mastered），不再写死 5 组计数器
  伪代码 返回 {"learner": learner, "covered_count": 有等级的点数, "level_count": 等级数, "levels": 按科目等级逐项的列表}

公开 函数 重建全部得分 pass_line? fall_line?
  返回 {ok, pairs, changed}；pairs 是处理的 (学习者, 知识点) 对数，changed 是新记了得分行的对数
  报错 400 分数线不合法
  伪代码 本函数不加科目入参（教师维护动作，跨科目全量重算）：按 progress_answer 流水行里的 subject_id 分组重算，新记的 progress_score 行带该 subject_id，不解析科目、不调用别的模块
  伪代码 调用 核对分数线 pass_line=pass_line fall_line=fall_line
  伪代码 在一个事务里：
  伪代码 取 progress_answer 中全部不同的 (learner, point_code, subject_id)
  伪代码 每对：若 progress_mastery 没有该 learner + point_code + subject_id（该对的科目）的行，按 progress_answer 同条件统计 right_count、total_count 插入 (mastered=0, updated_at=当前时间, subject_id=该对的 subject_id)
  伪代码 每对：调用 重算点 learner point_code 两条线 subject_id（只新增得分行、更新掌握标记，不删除旧得分行，不改作答流水）
  伪代码 累计 pairs 和 changed
  伪代码 返回 {"ok": 1, "pairs": pairs, "changed": changed}

公开 函数 列低分点 learner below? limit? current_role? auth_mode? subject?
  返回 {learner, total, points}；points 是 [{point_code, title, score}]，取本科目每个点最新得分严格小于 below（默认 80）的点，按 score 升序、point_code 升序，最多 limit 个（默认 10）
  报错 400 参数不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；调用 kg. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 below 为空取 80，limit 为空取 10；below 不是 0 到 100 的整数或 limit 不是大于等于 1 的整数，报错 400 参数不合法
  伪代码 取该 learner 在 progress_score 里 subject_id 等于本科目的每个知识点 id 最大的那一行
  伪代码 留下 score 小于 below 的，调用 kg.取知识点 code=该点编号 subject=subject_id 取 title（取不到取空串），排序后取前 limit 个
  伪代码 返回 {"learner": learner, "total": 个数, "points": 列表}

公开 函数 列错题 learner limit? current_role? auth_mode? subject?
  返回 {learner, total, wrongs}；wrongs 是 [{point_code, question_no, answer, at, score, mastered}]，该学习者在本科目 correct=0 的作答按 id 降序，最多 limit 条（默认 10）；score 是该点最新得分（没有为 0），mastered 是该点掌握标记（没有为 0）
  报错 400 limit 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id
  伪代码 limit 为空取 10；不是大于等于 1 的整数，报错 400 limit 不合法
  伪代码 查 progress_answer 中该 learner、subject_id 等于本科目且 correct=0 的行，按 id 降序取前 limit 条
  伪代码 每行读 progress_score 该点（subject_id 等于本科目）最新一行的 score，progress_mastery 该点（learner、subject_id 等于本科目）的 mastered
  伪代码 返回 {"learner": learner, "total": 条数, "wrongs": 列表}

公开 函数 列久未做已掌握点 learner days? limit? current_role? auth_mode? subject?
  返回 {learner, total, points}；points 是 [{point_code, title, last_at}]，是本科目 mastered=1 且该点最后一次作答日期早于（当前日期 - days 天）的点，last_at 为该点最后一次作答的 at，按 last_at 升序（最久的在前），最多 limit 个（默认 10）
  报错 400 参数不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；调用 kg. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 days 为空取 7，limit 为空取 10；days 不是大于等于 0 的整数或 limit 不是大于等于 1 的整数，报错 400 参数不合法
  伪代码 查 progress_mastery 中该 learner、subject_id 等于本科目且 mastered=1 的行
  伪代码 每行取 progress_answer 该 learner + point_code（subject_id 等于本科目）中 id 最大一行的 at 为 last_at；没有作答行的点跳过
  伪代码 last_at 的前 10 个字符（日期）小于 当前日期 减 days 天 的日期才保留
  伪代码 调用 kg.取知识点 code=该点编号 subject=subject_id 取 title（取不到取空串），按 last_at 升序取前 limit 个
  伪代码 返回 {"learner": learner, "total": 个数, "points": 列表}

公开 函数 取区间作答 learner start_id end_id? current_role? auth_mode? subject?
  返回 {learner, start_id, max_id, total, answers}；answers 是该学习者在本科目作答流水中 id 大于 start_id（且 end_id 不为空时 id 不大于 end_id）的行 [{id, point_code, question_no, correct, answer, at}]，按 id 升序；max_id 是该学习者在本科目当前最大的作答 id（没有作答为 0），可用来当「这一轮起点」
  报错 400 start_id 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id
  伪代码 start_id 不是大于等于 0 的整数，报错 400 start_id 不合法；end_id 不为空且不是整数，同样报错 400 start_id 不合法
  伪代码 查 progress_answer 中该 learner、subject_id 等于本科目且 id 大于 start_id（end_id 不为空时再加 id 不大于 end_id）的行，按 id 升序
  伪代码 max_id 取该 learner 在 progress_answer 里 subject_id 等于本科目的最大的 id，没有为 0
  伪代码 返回 {"learner": learner, "start_id": start_id, "max_id": max_id, "total": 行数, "answers": 列表}

公开 函数 统计作答 learner? current_role? auth_mode? subject? student?
  报错 403 只有老师可以查看作答统计
  返回 {total, learners}；learners 是 [{learner, answer_count, last_at}]，本科目每个有过作答的学习者一行，last_at 是其在本科目最后一次作答的 at；筛选学习者 = student 不为空取 student，否则在非登录模式（auth_mode 不是 on）下取 learner（旧行为，旧调用 统计作答 learner=u1 不变），登录模式下 learner 只是调用者身份、不作筛选；筛选不为空时只返回该学习者；按 learner 升序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 先校验角色：auth_mode 等于 on 且 current_role 不等于 teacher（学生、空），报错 403 只有老师可以查看作答统计；非登录模式不校验（account 的 列学生、列学生页面 不传 auth_mode，走这一支）；这一步在 本科目 之前
  伪代码 科目：调用本模块 本科目 learner=（auth_mode 等于 on 取 learner，否则空串） current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject、student 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；角色消歧：解析科目用的是调用者身份（learner 仅在 auth_mode=on 时就是登录用户并传给 本科目，非登录模式不传），被查的学习者是筛选条件，登录模式下一律用新增的可选入参 student 传，不再占用 learner，所以教师按学生筛选不会按被查学生去解析科目（避免 403 或解析错科目）
  伪代码 查 progress_answer 中 subject_id 等于本科目的行，按 learner 分组统计行数 answer_count，last_at 取该组 id 最大一行的 at
  伪代码 筛选学习者（student 不为空取 student，否则非登录模式取 learner）不为空时只留该学习者
  伪代码 返回 {"total": 学习者数, "learners": 列表}

公开 函数 按天统计作答 days? week? student? learner? current_role? auth_mode? subject?
  报错 403 只有老师可以查看作答统计
  返回 {days, since, total, rows}；rows 是 [{period, learner, n, right}]：本科目最近 days 天（含今天，默认 28）的作答按「时段 + 学习者」分组的作答数 n 与答对数 right，按 period 升序、learner 升序；period 是日期 YYYY-MM-DD（week 为 1 时是该周周一的日期）；since 是窗口第一天 YYYY-MM-DD；total 是 rows 的行数。M4-P4 新增（design §6.1 趋势、掉队规则用；只读，给 assist_insight 调，学生范围、正确率、字符图都由调用方算）
  报错 400 days 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 先校验角色（同 统计作答）：auth_mode 等于 on 且 current_role 不等于 teacher，报错 403 只有老师可以查看作答统计；非登录模式不校验
  伪代码 科目：调用本模块 本科目 learner=（auth_mode 等于 on 取 learner，否则空串） current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；全部入参可选（别的模块调用时只传 subject=已解析的科目编号和需要的筛选），都不传得 1 号科目最近 28 天；下面的查询只限这个 subject_id
  伪代码 days 为空取 28；不是 1 到 90 的整数，报错 400 days 不合法
  伪代码 since = date(当前时间, 「-(days-1) days」)（当前时间同其它函数，用例里是 DSL_NOW=2026-01-01 09:00:00，days=28 时 since=2025-12-05）
  伪代码 查 progress_answer 中 subject_id 等于本科目、substr(at,1,10) 大于等于 since 的行（student 不为空时再加 learner=student）；period 取 substr(at,1,10)，week 等于 1 时取 date(at, '-6 days', 'weekday 1')（该周周一）；按 period、learner 分组，n=count(*)，right=sum(correct)（CAST 成整数）
  伪代码 返回 {"days": days, "since": since, "total": 行数, "rows": 列表}

函数 取点级映射 subject_id
  返回 {code: level}，本科目知识点编号到本科目等级（subject.科目等级；日语 N5–N1）的映射；没有等级的知识点不在映射里；subject_id 是已解析的科目编号（整数）
  伪代码 调用 kg.列知识点 subject=subject_id 得本科目全部点；对每点调用 lesson.取知识点等级 point_code=该点编号 subject=subject_id，level 非空才收

函数 得分视图 learner subject_id
  返回 {by_code: {code: score}, last: {code: at}, once: {code: 1或0}}；by_code 是本科目每个点最新得分（没有该点）；last 是每个点最近一次打分时间；once 为 1 表示该点只有一行得分（「首次」用）
  伪代码 直读 progress_score 中 learner 相等且 subject_id 等于传入值的行：按 point_code 分组，各组按 id 降序；最新一行的 score、at 进 by_code、last；组内只有一行则 once=1 否则 0

公开 函数 进度页面 learner current_role? auth_mode? subject?
  返回 {prog, doing, next, recent, levels, scores, dictation}；学习进度页「进入时」（动作 progress_page）的整页状态，全是读、不写库，全部只看本科目；prog 是概览对象，dictation 是单词默写对象，其余是页面五个列表
  报错 400 learner 不能为空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：lang 为 ja 时 head 写「習得済み {mastered_count} / 全知識ポイント {point_total}」；answers_text 写「累計解答 {n}」；rate_text 写「正答率 {x}」；score_text 写「平均スコア {x}」；verdict 写「まだ採点されていません」「達成（スコア {score}）」「スコア {score}、あと {gap} 点」；recent 的 result 写 正解、不正解；scores 的 delta 首次写「初回」；dictation.text 写「練習した単語 {words} 個、書き取り {total} 回、正答率 {drate}、間違えた単語帳 {wrong_book_count} 個」。中文分支一字不改。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它公开函数、调用 kg./lesson./dictation. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 learner 为空，报错 400 learner 不能为空
  伪代码 调用 取概览 learner=learner subject=subject_id 得 ov；调用 列得分 learner=learner subject=subject_id 得 sc（各点当前分与上一次）；用 得分视图 learner=learner subject_id=subject_id 得最新分/最近打分时间/是否只有一行
  伪代码 prog：head=「已掌握 {ov.mastered_count} / 总知识点 {ov.point_total}」；answers_text=「累计答题 {ov.answer_total}」；rate_text 在 answer_total 大于 0 时是「正确率 {ov.accuracy}%」否则「正确率 —」；score_text 在打过分的点数大于 0 时是「平均得分 {平均分}」（各点当前分平均、四舍五入取整，没打过分的点不算）否则「平均得分 —」；empty=ov.is_empty；quiz_link=「#%E5%81%9A%E9%A2%98」；review_link 在 answer_total 大于 0 时是「#%E5%81%9A%E9%A2%98?mode=review」否则空串
  伪代码 doing：调用 取状态 learner=learner subject=subject_id，留 total 大于 0 的点；每行 {label: title, tally: 「{right}/{total}」, verdict}；verdict 按最新分现算：没有得分行「还没打分」；得分不小于 80、或 mastered=1 且得分不小于 60，是「达标（得分 {score}）」；否则「得分 {score}，差 {80-score} 分」；顺序按 progress_mastery.updated_at 降序、id 降序（最近答过的在前，旧行为），最多 50 行
  伪代码 next：调用 算下一步 learner=learner subject=subject_id 得 points（前置都掌握、自己没掌握），取前 20 个；调用 kg.列分层 subject=subject_id 得每点依赖深度（取不到算 0）；每行 {label: title, depth}
  伪代码 recent：调用 列最近作答 learner=learner limit=20 subject=subject_id；每行 {at, label: 该点 title（调 kg.取知识点 code=该点编号 subject=subject_id，取不到用 point_code）, item_label: 空串（v4 作答流水不记条目）, result: correct=1 是「对」否则「错」}
  伪代码 levels：调用 按级统计掌握 learner=learner subject=subject_id 得每个本科目等级一行（日语仍是五行）；按等级逐项累计答题数（不再写死 5 段 if）；每行 {level, tally: 「{mastered}/{total}」, answers: 该级知识点的作答行数合计}（answers 用 取点级映射 subject_id=subject_id 把本科目 progress_answer 各行按所属点归级计数；v4 题不挂等级，与旧「按题挂级」口径的差别见报告）
  伪代码 scores：对 sc.scores 每行 {label: title, value: score, delta, at: last[code]}；delta：once[code]=1 是「首次」；本次分大于上次「+{差}」、小于「−{差}」（全角减号）、相等「±0」；顺序沿用 列得分（分低的在前、同分按编号）
  伪代码 dictation：调用 dictation.取默写概况 learner=learner subject=subject_id 得 d；练过词数 words = dictation_attempt（表带 subject_id 列，按本科目过滤）中该 learner、subject_id 等于本科目的不同 word_id 的个数；text=「练过 {words} 个词，默写 {d.total} 次，正确率 {d.total 大于 0 时 d.accuracy% 否则 —}，错词本 {d.wrong_book_count} 个」；link 在 wrong_book_count 大于 0 时是「#%E9%BB%98%E5%86%99?source=review」否则「#%E9%BB%98%E5%86%99」
  伪代码 K182 内容日语替换：lang = 调用 subject.取界面语言 username=learner 取 lang（表不存在或无行视为 zh）；ja 时 doing/next/recent/scores 各行 label（知识点 title）调用 subject.译文 tbl=kg_point row_key=该点编号 field=title lang=ja，非空才替换（缺译文回退中文）；zh 或无译文这些 label 与改前逐字一致
  伪代码 K192 Python 默写：d.mode 等于 python 时不数 dictation_attempt 的练过词数；dictation.text 中文「默写 {d.total} 次，正确率 {d.total 大于 0 时 d.accuracy% 否则 —}，错题 {d.wrong_book_count} 道」，ja「書き取り {d.total} 回、正答率 {同上}、間違えた問題 {d.wrong_book_count} 問」；link 同日语口径（wrong_book_count 大于 0 时 #%E9%BB%98%E5%86%99?source=review，否则 #%E9%BB%98%E5%86%99）；dictation 对象多一个 mode（python 或 jp），日语其余一字不变；正确率只用 取默写概况 的返回，不合并做题掌握
  伪代码 返回 {"prog": prog, "doing": doing, "next": next, "recent": recent, "levels": levels, "scores": scores, "dictation": {"text": …, "link": …, "mode": …}}

公开 函数 图谱页面 learner current_role? auth_mode? subject?
  返回 {graph, node_count, edge_count}；node_count、edge_count 是顶层计数，等于 graph.nodes、graph.edges 的个数（本科目可见的点数和边数，前置边与对照边都算，丢掉的条目端对照边不算）；graph={nodes, edges}；知识图谱页「进入时」（动作 node_list）的整页状态，全是读，只含本科目的知识点和边；nodes 每点 {id: 编号, code, label: title, state, badge, desc}；state 是 done（已掌握）/open（可学）/locked（锁定）：mastered=1 是 done，否则所有直接前置都 mastered=1（没有前置也算）是 open，其余 locked；badge 是后代（直接和间接后续）个数（角标，标「往下解锁」的瓶颈）；desc 是直接前置的 title 用「、」连，没有前置是「（起点）」（点开浮层时页面写进 sel.desc）；edges 两类：前置边 {from: pre_code, to: point_code, kind: 空串}，对照边 {from: a_code, to: b_code, kind: 对照}（对照两端都得是本科目的知识点，条目端丢掉；旧行为）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：lang 为 ja 时 desc 的（起点）写（起点）不变（日中同形）；节点的 kind「对照」是内部值不改。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它公开函数、调用 kg. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 调用 取状态 learner=learner subject=subject_id 得每点 mastered（right/total 顺带不用）；调用 kg.列知识点 subject=subject_id 得本科目全部点；badge 对每点调用 kg.列后代 code=该点编号 subject=subject_id 取 total；desc 对每点调用 kg.列前置 code=该点编号 subject=subject_id 拼 title
  伪代码 edges 直读 kg_edge 与 kg_contrast（两张表都带 subject_id 列，按本科目过滤，只取 subject_id 等于本科目的行）；对照两端各是知识点或条目，要通过 kg_point（带 subject_id 列，等于本科目）确认两端都是本科目的知识点才收，条目端丢掉（kg_point 的 code 全局唯一，不会误认别科目的点）
  伪代码 K182 内容日语替换：lang = 调用 subject.取界面语言 username=learner 取 lang（表不存在或无行视为 zh）；ja 时 nodes 每点 label 与 desc 里的前置 title 调用 subject.译文 tbl=kg_point row_key=该点编号 field=title lang=ja，非空才替换；对照边只有编号不翻
  伪代码 返回 {"graph": {"nodes": 按编号升序, "edges": 前置边在前按 id、对照边按 id}, "node_count": nodes 的个数, "edge_count": edges 的个数}（前端只读 graph，多余键忽略）

公开 函数 知识点页面 learner code current_role? auth_mode? subject?
  返回 {node_tally, node_score, items, forms, point_words}；知识图谱页浮层「载入」（动作 node_detail）的页面状态；node_tally/node_score 铺进共享状态，items/forms/point_words 喂浮层三张表；全部只看本科目
  报错 400 code 不能为空
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：lang 为 ja 时 node_tally 写「正解 {right} / 解答 {total}」，已掌握写「（習得済み）」，没做过写「まだ解いていません」；forms 的 label、point 里的标题走已有的译文。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 learner 和 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询都只限这个 subject_id；本函数在本模块内调用其它公开函数、调用 kg./vocab. 的函数时一律只传 subject=subject_id（已解析，不再校验）
  伪代码 code 为空，报错 400 code 不能为空；调用 kg.取知识点 code=code subject=subject_id，取不到（包括编号属于别的科目）报错 404 没有这个知识点
  伪代码 调用 取状态 learner=learner point_code=code subject=subject_id 得该点 right/total/mastered：total 大于 0 时 node_tally=「答对 {right} / 答题 {total}」加 mastered=1 时的「（已掌握）」，否则「还没做过」
  伪代码 K182 内容日语替换：lang = 调用 subject.取界面语言 username=learner 取 lang（表不存在或无行视为 zh）；ja 时 items 各行条目名调 subject.译文 tbl=kg_item row_key=条目编号 field=name lang=ja，forms 各行 label 与 point（所属知识点名）分别调 tbl=kg_item field=name / tbl=kg_point field=title，均非空才替换
  伪代码 用 得分视图 learner=learner subject_id=subject_id：by_code 里有该点则 node_score=最新得分，否则空串（浮层上那一格不显示）
  伪代码 items：调用 kg.按知识点列条目 point_code=code subject=subject_id；每行 {label: name, form: after_form 为空取空串}
  伪代码 forms：调用 kg.列条目 subject=subject_id 留 after_form 等于 code 的行；每行 {label: name, point: 所属知识点 title（调 kg.取知识点 code=所属知识点编号 subject=subject_id，取不到空串）}
  伪代码 point_words：调用 vocab.按知识点列单词 point_code=code subject=subject_id，words 取前 200；每行 {kanji, kana, meaning}（空原样给）
  伪代码 返回 {"node_tally": …, "node_score": …, "items": …, "forms": …, "point_words": …}

## 接口
POST /progress/answer -> 记作答 角色 student
GET /progress/state -> 取状态 角色 student
GET /progress/next -> 算下一步 角色 student
GET /progress/overview -> 取概览 角色 student
GET /progress/scores -> 列得分 角色 student
GET /progress/recent -> 列最近作答 角色 student
GET /progress/levels -> 按级统计掌握 角色 student
POST /progress/scores/rebuild -> 重建全部得分 角色 teacher
POST /progress/page -> 进度页面 动作 progress_page 模板 页面状态 角色 student
POST /progress/graph -> 图谱页面 动作 node_list 模板 页面状态 角色 student
POST /progress/point -> 知识点页面 动作 node_detail 模板 页面状态 角色 student

## 用例
用例 记作答_答对
  先 数据 kg_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1 answer=A
  得 ok=1 total=1 right=1 score=100 mastered=1 changed=1
  库 progress_answer 共 1 行
  库 progress_answer 含 learner=u1 point_code=P1 question_no=Q1 correct=1 answer=A
  库 progress_mastery 共 1 行
  库 progress_mastery 含 learner=u1 point_code=P1 right_count=1 total_count=1 mastered=1
  库 progress_score 共 1 行
  库 progress_score 含 learner=u1 point_code=P1 score=100

用例 记作答_答错未掌握
  先 数据 kg_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=0 answer=B
  得 ok=1 total=1 right=0 score=0 mastered=0 changed=1
  库 progress_mastery 含 learner=u1 point_code=P1 right_count=0 total_count=1 mastered=0
  库 progress_score 含 learner=u1 point_code=P1 score=0

用例 记作答_掌握后回落线内继续掌握
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q3 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q4 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q5 correct=0
  调用 记作答 learner=u1 point_code=P1 question_no=Q6 correct=0
  得 total=6 right=4 score=67 mastered=1 changed=1
  库 progress_score 共 3 行
  库 progress_mastery 含 learner=u1 point_code=P1 mastered=1

用例 记作答_得分没变不记新行
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=1
  得 total=2 right=2 score=100 mastered=1 changed=0
  库 progress_score 共 1 行
  库 progress_answer 共 2 行

用例 记作答_没有知识点
  调用 记作答 learner=u1 point_code=NOPE question_no=Q1 correct=1
  报错 404
  库 progress_answer 共 0 行
  库 progress_mastery 共 0 行

用例 记作答_correct非法
  先 数据 kg_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=2
  报错 400
  库 progress_answer 共 0 行

用例 记作答_分数线不合法
  先 数据 kg_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1 pass_line=50 fall_line=60
  报错 400
  库 progress_answer 共 0 行

用例 取状态_全部
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_edge pre_code=P1 point_code=P2
  调用 取状态 learner=u1
  得 learner=u1 total=2 mastered_count=0 unlocked_count=1

用例 取状态_前置掌握后解锁
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_edge pre_code=P1 point_code=P2
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 取状态 learner=u1 point_code=P2
  得 total=1 mastered_count=0 unlocked_count=1

用例 取状态_没有知识点
  调用 取状态 learner=u1 point_code=NOPE
  报错 404

用例 算下一步_只有根节点可学
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_edge pre_code=P1 point_code=P2
  调用 算下一步 learner=u1
  得 total=1 next_code=P1

用例 算下一步_掌握前置后轮到后续
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_edge pre_code=P1 point_code=P2
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 算下一步 learner=u1
  得 total=1 next_code=P2

用例 取概览_有作答
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=0
  调用 取概览 learner=u1
  得 point_total=2 mastered_count=0 answer_total=2 right_total=1 accuracy=50 is_empty=0

用例 取概览_一道没答过
  先 数据 kg_point code=P1 title=一次函数
  调用 取概览 learner=u1
  得 point_total=1 mastered_count=0 answer_total=0 right_total=0 accuracy=0 is_empty=1

用例 列得分_有变化
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=0
  调用 列得分 learner=u1
  得 learner=u1 total=1

用例 列得分_没有记录
  调用 列得分 learner=u1
  得 total=0

用例 列最近作答_limit截断
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=0
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q3 correct=1
  调用 列最近作答 learner=u1 limit=2
  得 learner=u1 total=2

用例 列最近作答_默认
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 列最近作答 learner=u1
  得 total=1

用例 列最近作答_limit非法
  调用 列最近作答 learner=u1 limit=0
  报错 400

用例 按级统计掌握_有等级
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_point_link lesson_code=L1 point_code=P1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 按级统计掌握 learner=u1
  得 learner=u1 covered_count=1

用例 按级统计掌握_没有课文
  先 数据 kg_point code=P1 title=一次函数
  调用 按级统计掌握 learner=u1
  得 covered_count=0

用例 重建全部得分_从流水补算
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 answer=A at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q2 correct=0 answer=B at=2025-12-02
  调用 重建全部得分
  得 ok=1 pairs=1 changed=1
  库 progress_score 共 1 行
  库 progress_score 含 learner=u1 point_code=P1 score=50
  库 progress_mastery 含 learner=u1 point_code=P1 right_count=1 total_count=2 mastered=0

用例 重建全部得分_没变化不新增
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 重建全部得分
  得 ok=1 pairs=1 changed=0
  库 progress_score 共 1 行

用例 重建全部得分_分数线不合法
  调用 重建全部得分 pass_line=50 fall_line=60
  报错 400

用例 列低分点_有低分
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=0
  调用 列低分点 learner=u1
  得 learner=u1 total=1

用例 列低分点_都达标
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 列低分点 learner=u1
  得 total=0

用例 列低分点_参数非法
  调用 列低分点 learner=u1 below=abc
  报错 400

用例 列错题_只含答错
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=0
  调用 列错题 learner=u1
  得 learner=u1 total=1

用例 列错题_limit截断
  先 数据 kg_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=0
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=0
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q3 correct=0
  调用 列错题 learner=u1 limit=2
  得 total=2

用例 列错题_limit非法
  调用 列错题 learner=u1 limit=0
  报错 400

用例 列久未做已掌握点_久没做
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_mastery learner=u1 point_code=P1 right_count=1 total_count=1 mastered=1 updated_at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  调用 列久未做已掌握点 learner=u1 days=7
  得 learner=u1 total=1

用例 列久未做已掌握点_最近做过
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_mastery learner=u1 point_code=P1 right_count=1 total_count=1 mastered=1 updated_at=2025-12-30
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-30
  调用 列久未做已掌握点 learner=u1 days=7
  得 total=0

用例 列久未做已掌握点_未掌握不算
  先 数据 kg_point code=P1 title=一次函数
  先 数据 progress_mastery learner=u1 point_code=P1 right_count=0 total_count=1 mastered=0 updated_at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=0 at=2025-12-01
  调用 列久未做已掌握点 learner=u1
  得 total=0

用例 列久未做已掌握点_days非法
  调用 列久未做已掌握点 learner=u1 days=-1
  报错 400

用例 取区间作答_从起点取
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u2 point_code=P1 question_no=Q1 correct=0 at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q2 correct=0 at=2025-12-02
  调用 取区间作答 learner=u1 start_id=0
  得 learner=u1 start_id=0 total=2

用例 取区间作答_起点之后没有
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  调用 取区间作答 learner=u1 start_id=999999
  得 total=0

用例 取区间作答_起点非法
  调用 取区间作答 learner=u1 start_id=abc
  报错 400

用例 统计作答_全部学习者
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q2 correct=0 at=2025-12-02
  先 数据 progress_answer learner=u2 point_code=P1 question_no=Q1 correct=1 at=2025-12-03
  调用 统计作答
  得 total=2

用例 统计作答_按学习者
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u2 point_code=P1 question_no=Q1 correct=1 at=2025-12-03
  调用 统计作答 learner=u1
  得 total=1

用例 统计作答_学生被拒
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  调用 统计作答 learner=u1 current_role=student auth_mode=on
  报错 403

用例 统计作答_没有作答
  调用 统计作答
  得 total=0

用例 进度页面_一道没答过
  先 数据 kg_point code=P1 title=一次函数
  调用 进度页面 learner=u1
  得 有返回
  库 progress_answer 共 0 行

用例 进度页面_有作答与得分
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_edge pre_code=P1 point_code=P2
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q2 correct=1
  调用 进度页面 learner=u1
  得 有返回
  库 progress_answer 共 2 行
  库 progress_score 共 1 行

用例 进度页面_learner为空
  调用 进度页面 learner=空
  报错 400

用例 图谱页面_初始只有根可学
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  先 数据 kg_contrast a_code=A b_code=C
  调用 图谱页面 learner=u1
  得 node_count=3 edge_count=3

用例 图谱页面_前置掌握后解锁
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  先 调用 记作答 learner=u1 point_code=A question_no=Q1 correct=1
  调用 图谱页面 learner=u1
  得 node_count=2 edge_count=1

用例 知识点页面_正常
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_item code=I1 name=条目一 point_code=P1 after_form=て形
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  调用 知识点页面 learner=u1 code=P1
  得 有返回

用例 知识点页面_接在这个形式后面的
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 kg_item code=I1 name=条目一 point_code=P1 after_form=P2
  调用 知识点页面 learner=u1 code=P2
  得 有返回

用例 知识点页面_没有这个知识点
  调用 知识点页面 learner=u1 code=NOPE
  报错 404

用例 知识点页面_code为空
  调用 知识点页面 learner=u1 code=空
  报错 400

用例 跨科目_记作答落当前科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 记作答 learner=u1 point_code=math.a question_no=Q1 correct=1 answer=A subject=2
  得 ok=1 total=1 right=1 score=100 mastered=1 changed=1
  库 progress_answer 含 learner=u1 point_code=math.a question_no=Q1 subject_id=2
  库 progress_mastery 含 learner=u1 point_code=math.a mastered=1 subject_id=2
  库 progress_score 含 learner=u1 point_code=math.a score=100 subject_id=2

用例 跨科目_不传科目记作答落日语
  先 数据 kg_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1
  得 ok=1
  库 progress_answer 含 learner=u1 point_code=P1 subject_id=1
  库 progress_mastery 含 learner=u1 point_code=P1 subject_id=1
  库 progress_score 含 learner=u1 point_code=P1 subject_id=1

用例 跨科目_记作答别的科目的点404
  先 数据 kg_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 question_no=Q1 correct=1 subject=2
  报错 404
  库 progress_answer 共 0 行
  库 progress_mastery 共 0 行
  库 progress_score 共 0 行

用例 跨科目_记作答日语看不到2号的点
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 记作答 learner=u1 point_code=math.a question_no=Q1 correct=1
  报错 404
  库 progress_answer 共 0 行

用例 跨科目_取状态只看本科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  调用 取状态 learner=u1 subject=2
  得 learner=u1 total=2

用例 跨科目_取状态不传科目是日语
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 取状态 learner=u1
  得 total=1

用例 跨科目_取状态别的科目的点404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 取状态 learner=u1 point_code=math.a
  报错 404

用例 跨科目_取状态前置只走本科目的边
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  调用 取状态 learner=u1 subject=2
  得 total=2 mastered_count=0 unlocked_count=1

用例 跨科目_算下一步只看本科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  调用 算下一步 learner=u1 subject=2
  得 total=1 next_code=math.a

用例 跨科目_取概览不混科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q2 correct=1 at=2025-12-02
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q1 correct=0 at=2025-12-03 subject_id=2
  调用 取概览 learner=u1 subject=2
  得 point_total=1 answer_total=1 right_total=0 accuracy=0 is_empty=0

用例 跨科目_取概览日语看不到2号的作答
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q1 correct=0 at=2025-12-03 subject_id=2
  调用 取概览 learner=u1
  得 point_total=1 answer_total=1 right_total=1 accuracy=100

用例 跨科目_取概览2号一道没答过
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  调用 取概览 learner=u1 subject=2
  得 point_total=1 answer_total=0 is_empty=1

用例 跨科目_列得分只看本科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_score learner=u1 point_code=P1 score=40 at=2025-12-01
  先 数据 progress_score learner=u1 point_code=math.a score=90 at=2025-12-02 subject_id=2
  调用 列得分 learner=u1 subject=2
  得 total=1

用例 跨科目_列最近作答只看本科目
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q1 correct=0 at=2025-12-02 subject_id=2
  调用 列最近作答 learner=u1 subject=2
  得 total=1

用例 跨科目_列低分点只看本科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_score learner=u1 point_code=P1 score=40 at=2025-12-01
  先 数据 progress_score learner=u1 point_code=math.a score=50 at=2025-12-02 subject_id=2
  调用 列低分点 learner=u1 subject=2
  得 total=1

用例 跨科目_列错题只看本科目
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=0 at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q1 correct=0 at=2025-12-02 subject_id=2
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q2 correct=1 at=2025-12-03 subject_id=2
  调用 列错题 learner=u1 subject=2
  得 total=1

用例 跨科目_列久未做已掌握点只看本科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 progress_mastery learner=u1 point_code=P1 right_count=1 total_count=1 mastered=1 updated_at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_mastery learner=u1 point_code=math.a right_count=1 total_count=1 mastered=1 updated_at=2025-12-01 subject_id=2
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q1 correct=1 at=2025-12-01 subject_id=2
  调用 列久未做已掌握点 learner=u1 days=7 subject=2
  得 total=1

用例 跨科目_取区间作答只看本科目
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q1 correct=0 at=2025-12-02 subject_id=2
  调用 取区间作答 learner=u1 start_id=0 subject=2
  得 learner=u1 start_id=0 total=1

用例 跨科目_统计作答只看本科目
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=1 at=2025-12-01
  先 数据 progress_answer learner=u2 point_code=math.a question_no=Q1 correct=0 at=2025-12-02 subject_id=2
  调用 统计作答 subject=2
  得 total=1

用例 跨科目_按级统计掌握只看本科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_point_link lesson_code=L1 point_code=P1
  调用 按级统计掌握 learner=u1 subject=2
  得 learner=u1 covered_count=0

用例 跨科目_重建全部得分带原科目
  先 数据 progress_answer learner=u1 point_code=math.a question_no=Q1 correct=1 answer=A at=2025-12-01 subject_id=2
  先 数据 progress_answer learner=u1 point_code=P1 question_no=Q1 correct=0 answer=B at=2025-12-02
  调用 重建全部得分
  得 ok=1 pairs=2 changed=2
  库 progress_score 含 learner=u1 point_code=math.a score=100 subject_id=2
  库 progress_score 含 learner=u1 point_code=P1 score=0 subject_id=1
  库 progress_mastery 含 learner=u1 point_code=math.a subject_id=2

用例 跨科目_进度页面只看本科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  先 调用 记作答 learner=u1 point_code=math.a question_no=Q1 correct=1 subject=2
  调用 进度页面 learner=u1
  得 doing=[] next=[] recent=[] scores=[]
  库 progress_answer 共 1 行

用例 跨科目_图谱页面只看本科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  先 数据 kg_contrast a_code=math.a b_code=math.b subject_id=2
  调用 图谱页面 learner=u1 subject=2
  得 node_count=2 edge_count=2

用例 跨科目_图谱页面计数不含别科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_point code=math.b title=几何 subject_id=2
  先 数据 kg_edge pre_code=math.a point_code=math.b subject_id=2
  先 数据 kg_contrast a_code=math.a b_code=math.b subject_id=2
  调用 图谱页面 learner=u1
  得 node_count=1 edge_count=0

用例 跨科目_知识点页面本科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 kg_item code=math.i1 name=条目 point_code=math.a subject_id=2
  先 数据 vocab_word kanji=式 kana=しき meaning=公式 point_code=math.a subject_id=2
  先 调用 记作答 learner=u1 point_code=math.a question_no=Q1 correct=1 subject=2
  先 数据 progress_score learner=u1 point_code=math.a score=30 at=2099-01-01 subject_id=1
  调用 知识点页面 learner=u1 code=math.a subject=2
  得 node_score=100

用例 跨科目_知识点页面条目和单词不串科目
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_item code=math.i1 name=条目 point_code=P1 after_form=P1 subject_id=2
  先 数据 vocab_word kanji=式 kana=しき meaning=公式 point_code=P1 subject_id=2
  调用 知识点页面 learner=u1 code=P1
  得 items=[] forms=[] point_words=[]

用例 跨科目_知识点页面别的科目的点404
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 知识点页面 learner=u1 code=math.a
  报错 404

用例 登录模式_记作答学生已分配科目可记作答
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 记作答 learner=s1 point_code=math.a question_no=Q1 correct=1 current_role=student auth_mode=on subject=2
  得 ok=1 total=1 right=1
  库 progress_answer 含 learner=s1 point_code=math.a subject_id=2

用例 登录模式_记作答学生未分配科目被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 记作答 learner=s1 point_code=math.a question_no=Q1 correct=1 current_role=student auth_mode=on subject=2
  报错 403
  库 progress_answer 共 0 行
  库 progress_mastery 共 0 行

用例 登录模式_记作答科目不存在
  调用 记作答 learner=s1 point_code=math.a question_no=Q1 correct=1 current_role=student auth_mode=on subject=9
  报错 404
  库 progress_answer 共 0 行

用例 登录模式_记作答科目不是数字
  调用 记作答 learner=s1 point_code=P1 question_no=Q1 correct=1 subject=abc
  报错 400
  库 progress_answer 共 0 行

用例 登录模式_取状态科目不存在
  调用 取状态 learner=s1 current_role=student auth_mode=on subject=9
  报错 404

用例 登录模式_算下一步科目不是数字
  调用 算下一步 learner=u1 subject=abc
  报错 400

用例 登录模式_取概览无权科目被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 取概览 learner=t9 current_role=teacher auth_mode=on subject=2
  报错 403

用例 登录模式_列得分科目不存在
  调用 列得分 learner=s1 current_role=student auth_mode=on subject=9
  报错 404

用例 登录模式_列最近作答科目不是数字
  调用 列最近作答 learner=u1 subject=abc
  报错 400

用例 登录模式_按级统计掌握无权科目被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 按级统计掌握 learner=s1 current_role=student auth_mode=on subject=2
  报错 403

用例 登录模式_列低分点科目不存在
  调用 列低分点 learner=s1 current_role=student auth_mode=on subject=9
  报错 404

用例 登录模式_列错题科目不是数字
  调用 列错题 learner=u1 subject=abc
  报错 400

用例 登录模式_列久未做已掌握点无权科目被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 列久未做已掌握点 learner=t9 current_role=teacher auth_mode=on subject=2
  报错 403

用例 登录模式_取区间作答科目不存在
  调用 取区间作答 learner=s1 start_id=0 current_role=student auth_mode=on subject=9
  报错 404

用例 登录模式_统计作答科目不是数字
  调用 统计作答 learner=u1 subject=abc
  报错 400

用例 登录模式_进度页面无权科目被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 进度页面 learner=s1 current_role=student auth_mode=on subject=2
  报错 403

用例 登录模式_图谱页面科目不存在
  调用 图谱页面 learner=s1 current_role=student auth_mode=on subject=9
  报错 404

用例 登录模式_知识点页面科目不是数字
  调用 知识点页面 learner=u1 code=math.a subject=abc
  报错 400

用例 登录模式_统计作答教师按学生筛选
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=math.a question_no=Q1 correct=1 at=2026-01-02 subject_id=2
  先 数据 progress_answer learner=s2 point_code=math.a question_no=Q1 correct=0 at=2026-01-03 subject_id=2
  调用 统计作答 learner=t1 current_role=teacher auth_mode=on subject=2 student=s1
  得 total=1

用例 登录模式_统计作答不带筛选看全部
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=private owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=math.a question_no=Q1 correct=1 at=2026-01-02 subject_id=2
  先 数据 progress_answer learner=s2 point_code=math.a question_no=Q1 correct=0 at=2026-01-03 subject_id=2
  调用 统计作答 learner=t1 current_role=teacher auth_mode=on subject=2
  得 total=2

用例 按天统计作答_按天按人分组只取窗口内
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-30
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q2 correct=0 at=2025-12-30
  先 数据 progress_answer learner=s2 point_code=P1 question_no=q1 correct=1 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q3 correct=1 at=2025-11-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q4 correct=1 at=2025-12-30 subject_id=2
  调用 按天统计作答
  得 days=28 since=2025-12-05 total=2

用例 按天统计作答_按学生筛选
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-30
  先 数据 progress_answer learner=s2 point_code=P1 question_no=q1 correct=1 at=2025-12-31
  调用 按天统计作答 student=s2 days=7
  得 total=1 since=2025-12-26

用例 按级统计掌握_日语仍是五项
  先 数据 kg_point code=P1 title=一次函数
  调用 按级统计掌握 learner=u1
  得 learner=u1 covered_count=0 level_count=5

用例 按级统计掌握_三档科目三项
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 kg_point code=P2 title=二次函数
  先 数据 lesson_text code=L1 level=基础 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_point_link lesson_code=L1 point_code=P1
  调用 按级统计掌握 learner=u1
  得 learner=u1 covered_count=1 level_count=3

用例 按级统计掌握_不在科目等级里的不计
  先 数据 subject_info code=py name=编程 levels=入门,基础,进阶 kind=general caps=x qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 kg_point code=P1 title=一次函数
  先 数据 lesson_text code=L1 level=N5 title=第一课 examples_edited=0 series_code=hanabira seq=1
  先 数据 lesson_point_link lesson_code=L1 point_code=P1
  调用 按级统计掌握 learner=u1
  得 covered_count=0 level_count=3
