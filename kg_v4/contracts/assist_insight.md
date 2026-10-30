模块 assist_insight
依赖 assist_common progress report kg subject

# 教师助手的深度学情（M4-P4，design §6，D11 归因放助手侧、D12 字符图）。老师问「全班最近四周的趋势」「错得最多的是哪些知识点」「对比一下小明和小红」「有没有掉队的学生」，teacher_assist 判出 deep_analysis（analysis_kind 为 trend / attribution / compare / alert）后调本模块 分析上下文，拿到【数据】段和后端画好的字符图：模型只负责解读、只能原样引用这里算好的数字；字符图由 teacher_assist 原样附在回答末尾（不让模型画，模型会画错数字）。「给掉队的学生发传达」由 teacher_assist 先调 掉队名单 得名单，再作为 students 交给 assist_draft.生成草稿（assist_draft 不依赖本模块）。
#
# 不建表、不写库、不调模型。数据来源：progress.按天统计作答（M4-P4 新增：按天/按周、按学习者的作答数与答对数）、report.取学生学情（对比）、assist_common.学生范围 / 匹配学生（学生范围只算本科目登记的学生）、kg.取知识点 / 取条目（名称）。错题归因要从题号找到条目（quiz_question.item_code），progress 不依赖 quiz，按 D11 归因放在助手侧：本模块的查询直接只读 progress_answer 与 quiz_question（两张表都在本模块的上游：progress 是直接依赖，quiz 经 report → tutor → quiz 在上游；本模块不调 quiz 的函数，所以不声明 quiz 依赖，同 kg 查引用 直读别的模块表的做法）。
#
# 权限：只读，按读解析科目；不传 need。学生、知识点都只在本科目里找；所有统计只算本科目、只算 assist_common.学生范围 里的学生（撤销登记的学生的旧作答不计入）。
#
# 字符图（D12，E2 没批，不改引擎）：
# - 横条：字符条 rate → 10 格，█ 为满、░ 为空，满格数 = 四舍五入(rate / 10)，如 80 →「████████░░」；
# - 迷你图：每个时段一个字符，正确率 <20 ▁、<40 ▂、<60 ▃、<80 ▅、≥80 ▆，该时段没有作答写「·」；后面接「首个有作答时段的正确率%→最后一个的%」。
# 约定常量见 规则常量（掉队规则的阈值、趋势窗口、前 N）；改阈值只改这一处。
#
# 空态（design §6.3，5 种，原文照写，前两种不调模型，由 teacher_assist 直接回给老师）：
# ①本科目没有登记学生：「这个科目还没有学生，去「科目管理 → 成员」分配学生后再看」
# ②有学生但本科目 0 作答：「还没有作答记录，趋势、归因、预警都要等学生做过题才有」
# ③趋势里有作答的天数 <3：不画迷你图，chart 写「只有 n 天有作答，数据太少，先不画趋势」，其余照常（仍调模型解读）
# ④对比时某个学生 0 作答：这一行写「还没作答」，不参与排名
# ⑤掉队名单为空：「按现在的规则没有掉队的学生」，同时列出规则（rules_text），让老师知道是按什么判的

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出）。本模块只读，不传 need

函数 规则常量
  返回 约定常量 {"silent_days": 7, "drop_window": 14, "drop_pct": 15, "drop_min": 10, "trend_days": 28, "trend_min_days": 3, "top_n": 5, "compare_min": 2, "compare_max": 5, "relay_max": 30}
  伪代码 silent_days：掉队规则①，全班近 silent_days 天有作答、而这位学生 silent_days 天以上没有作答；drop_window、drop_pct、drop_min：掉队规则②，近 drop_window 天的正确率比之前 drop_window 天低 drop_pct 个百分点以上，两段都至少 drop_min 题才算；trend_days：趋势、归因默认窗口；trend_min_days：有作答的天数少于它不画趋势（空态③）；top_n：归因默认列前几个知识点；compare_min、compare_max：对比的人数范围；relay_max：给掉队学生发传达时一次最多带的人数（assist_draft 的传达上限 30）
  伪代码 规则文本 rules_text 也由这里的数拼：「规则：①全班近 7 天有作答、而这位学生 7 天以上没有作答；②近 14 天正确率比之前 14 天低 15 个百分点以上（两段都至少 10 题）」

函数 字符条 rate
  返回 文本：10 格横条；rate 是 0 到 100 的整数（超出按边界算，空串当 0）；满格数 = 四舍五入(rate / 10)，前面满格 █、后面空格 ░，共 10 个字符

函数 迷你图 rates
  返回 文本：rates 是按时段排好的正确率列表（没有作答的时段是空串），每项一个字符：空串「·」，<20「▁」，<40「▂」，<60「▃」，<80「▅」，其余「▆」

函数 空态 subject_id
  返回 {status, hint, students, answered}；status 为 ok / empty；students 是本科目学生范围（assist_common.学生范围 的 students）；answered 是其中在本科目有过作答的 username 列表
  伪代码 调用 assist_common.学生范围 subject=subject_id 得 students；人数为 0：status=empty，hint=空态①原文
  伪代码 调用 progress.统计作答 subject=subject_id 得 learners，answered = learners 中 answer_count 大于 0 且 learner 在 students 里的 learner；为空：status=empty，hint=空态②原文
  伪代码 否则 status=ok，hint 为空串

公开 函数 学情趋势 student? days? week? learner? current_role? auth_mode? subject?
  返回 {status, hint, student, days, week, active_days, rows, spark, chart, context_text}；status 为 ok / empty / ask（empty、ask 时 hint 是回给老师的模板话，其余为空）；rows 是 [{ana_day, ana_n, ana_rate, ana_bar}]（只列有作答的时段：时段、作答数、正确率%、字符条）；active_days 是窗口内有作答的天数；spark 是迷你图；chart 是附在回答末尾的整段字符图；context_text 是给模型的【数据】段
  报错 400 days 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；本函数调用其它函数时一律带 subject=subject_id
  伪代码 days 为空取 规则常量 的 trend_days（28）；不是 7 到 90 的整数报错 400 days 不合法；week 为空时 days 大于 14 取 1（按周）否则 0（按天）
  伪代码 调用 空态 subject_id=subject_id；empty 原样返回（status=empty、hint）
  伪代码 student 不为空：调用 assist_common.匹配学生 name=student subject=subject_id；none：status=ask，hint「没有找到叫「student」的学生。现有学生：roster」；many：status=ask，hint「找到多位：显示名（用户名）、…，你指哪一位？」；one：只看这位学生（username）
  伪代码 d = 调用 progress.按天统计作答 days=days student=username（没指定学生为空） subject=subject_id（按天）；只留 learner 在学生范围里的行；active_days = 不同 period 的个数
  伪代码 week 等于 1 时再调用 progress.按天统计作答 days=days week=1 student=username subject=subject_id，同样过滤；按 period 汇总 n、right、人数（不同 learner 数）；week 等于 0 时用 d 汇总
  伪代码 每个时段 rate = 四舍五入(right * 100 / n)；rows 的 ana_day 是 period（按周时写「period 起一周」），ana_n 是「n 题 / m 人」，ana_rate 是 rate，ana_bar 是 字符条 rate=rate
  伪代码 spark：从 since 起把窗口里每个时段（按天每天一个、按周每周一个）都排上，没有作答的是空串，调用 迷你图 得字符串
  伪代码 chart：active_days 小于 trend_min_days：「只有 active_days 天有作答，数据太少，先不画趋势」（空态③，rows 仍返回）；否则第一行「近 days 天（按周/按天）正确率 spark 首个有作答时段的 rate%→最后一个的 rate%（共作答 N 题）」，下面每个有作答的时段一行「ana_day ana_bar rate%（ana_n）」，最多 12 行（多了只留最近 12 个）
  伪代码 context_text：「今天：当前日期」+「分析：作答趋势，范围 全班 或 显示名（用户名），最近 days 天，按周/按天」+ 每个时段一行「period｜作答 n｜答对 right｜正确率 rate%｜人数 m」+「【后端算好的字符图】」+ chart
  伪代码 返回 {"status": "ok", "hint": "", "student": username 或空串, "days": days, "week": week, "active_days": active_days, "rows": rows, "spark": spark, "chart": chart, "context_text": context_text}

公开 函数 错题归因 student? days? top? learner? current_role? auth_mode? subject?
  返回 {status, hint, days, total, points, rows, chart, context_text}；把最近 days 天的错题归到知识点：points 是错题最多的前 top 个知识点 [{point_code, title, n, wrong, rate, learners, items}]（n 作答数、wrong 答错数、rate 错误率%、learners 答错过的人数、items 是这个知识点里错得最多的前 3 个条目 [{code, name, wrong}]）；total 是有错题的知识点个数（取前 top 之前）；rows 是给分析列表的 [{ana_day, ana_n, ana_rate, ana_bar}]（ana_day 放知识点标题，ana_rate 是错误率）
  报错 400 days 不合法
  报错 400 top 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；本函数调用其它函数时一律带 subject=subject_id
  伪代码 days 为空取 trend_days（28），不是 7 到 90 的整数报错 400 days 不合法；top 为空取 top_n（5），不是 1 到 10 的整数报错 400 top 不合法
  伪代码 调用 空态 subject_id=subject_id；empty 原样返回；student 不为空时同 学情趋势 用 assist_common.匹配学生 定下 username（none / many 回 ask）
  伪代码 查询（本模块的 SQL，只读）：progress_answer 中 subject_id=本科目、substr(at,1,10) 大于等于 since（同 按天统计作答 的算法：当前日期往前 days-1 天）、learner 在学生范围里（学生范围的 username 列表作为 JSON 参数，SQL 里 json_each 展开；指定了学生时只这一位）的行，按 point_code 分组：n=count(*)，wrong=sum(correct=0)，learners=答错过的不同 learner 数；只留 wrong 大于 0 的，按 wrong 降序、错误率降序、point_code 升序
  伪代码 条目：同样的行里 correct=0 的，LEFT JOIN quiz_question ON question_no 相同且 subject_id 相同，按 point_code、item_code 分组数 wrong；每个知识点取 wrong 最多的前 3 个；item_code 为空（题库外的题，如问老师里出的模板题）记成「（题库外的题）」
  伪代码 名称：调用 kg.取知识点 code=point_code subject=subject_id 取 title（取不到用编号）；调用 kg.取条目 code=item_code subject=subject_id 取 name（取不到用编号）
  伪代码 rate = 四舍五入(wrong * 100 / n)
  伪代码 没有任何错题：status=ok，points 为空，chart「最近 days 天没有答错的题」
  伪代码 chart：第一行「最近 days 天错题最多的 k 个知识点（错误率 = 答错 / 作答）：」，每个知识点一行「title 字符条 rate=rate rate%（错 wrong / 作答 n 题，learners 人）」，下一行缩进「错得多的条目：name（wrong）、…」
  伪代码 context_text：「今天：当前日期」+「分析：错题归因，范围 全班 或 显示名（用户名），最近 days 天，有错题的知识点共 total 个，下面是前 k 个」+ 每个知识点一行「title（point_code）｜作答 n｜答错 wrong｜错误率 rate%｜答错的人 learners｜条目：name 错 x 题、…」+「【后端算好的字符图】」+ chart
  伪代码 返回 {"status": "ok", "hint": "", "days": days, "total": total, "points": points, "rows": rows, "chart": chart, "context_text": context_text}

公开 函数 学生对比 students learner? current_role? auth_mode? subject?
  返回 {status, hint, total, ranked, rows, chart, context_text}；students 是老师说的 2 到 5 个学生名（「、」「，」英文逗号或空白隔开）；rows 是 [{ana_day, ana_n, ana_rate, ana_bar}]（ana_day 放显示名，ana_n 放作答数，ana_rate 近期正确率，没作答的 ana_rate 为空串、ana_bar 为「还没作答」）；ranked 是参与排名的人数（有作答的）；total 是对比的人数
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；本函数调用其它函数时一律带 subject=subject_id
  伪代码 调用 空态 subject_id=subject_id；status 为 empty 且是空态①（没有学生）原样返回；空态②（全班都没作答）不拦，下面每人都会是「还没作答」
  伪代码 students 拆开去空、去重；个数小于 compare_min 或大于 compare_max：status=ask，hint「对比要说 2 到 5 位学生的名字，用「、」隔开」
  伪代码 逐个调用 assist_common.匹配学生 name=该名字 subject=subject_id。有 none 的：本函数回 ask，hint「没有找到叫「名字」的学生。现有学生：roster」；有 many 的：本函数回 ask，hint「「名字」找到多位：显示名（用户名）、…，你指哪一位？」；两个名字匹配到同一个人只算一次，去重后不足 2 人同样回上面「对比要说 2 到 5 位」那句
  伪代码 每人调用 report.取学生学情 student=username subject=subject_id，取 answer_total、recent_accuracy、avg_score、mastered_count、weak_count、weak_points 前 3 个
  伪代码 answer_total 等于 0 的：这一行写「还没作答」（空态④），不参与排名；其余按 recent_accuracy 降序、avg_score 降序、username 升序排名
  伪代码 chart：参与排名的每人一行「名次. 显示名 字符条 rate=recent_accuracy 近期正确率 recent_accuracy%｜平均分 avg_score｜已掌握 mastered_count｜低分点 weak_count 个」，后面是没作答的每人一行「显示名：还没作答」
  伪代码 context_text：「今天：当前日期」+「分析：学生对比（近期正确率按每人最近 20 次作答算）」+ 每人一行「显示名（用户名）｜作答 answer_total｜近期正确率 recent_accuracy%｜平均分 avg_score｜已掌握 mastered_count｜低分点 weak_count 个（最低：标题 得分、…）」或「显示名（用户名）｜还没作答」+「【后端算好的字符图】」+ chart
  伪代码 返回 {"status": "ok", "hint": "", "total": 人数, "ranked": 参与排名人数, "rows": rows, "chart": chart, "context_text": context_text}

公开 函数 掉队名单 learner? current_role? auth_mode? subject?
  返回 {status, hint, total, students, rules_text, chart, context_text}；按 规则常量 的两条规则（不让模型判断）算出的掉队学生：students 是 [{username, display_name, reasons, last_at}]（reasons 是命中的规则说明列表，last_at 是最近一次作答的日期，没作答过为空串），按 username 升序；status 为 ok（有名单）/ empty（空态①②，或名单为空即空态⑤；hint 是回给老师的原文，名单为空时 hint =「按现在的规则没有掉队的学生。」+ rules_text）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；本函数调用其它函数时一律带 subject=subject_id
  伪代码 调用 空态 subject_id=subject_id；empty 原样返回（total=0、students 为空、rules_text 照给）
  伪代码 d = 调用 progress.按天统计作答 days=两倍 drop_window（28） subject=subject_id（按天，按学习者分行）；只留学生范围里的学习者；停用的学生（学生范围 status 为「停用」）不判
  伪代码 规则①：全班（学生范围里的人）在最近 silent_days 天（period 大于等于 当前日期往前 silent_days-1 天）有作答时才判；这位学生在这段时间里没有任何作答 → 命中，reasons 加「近 7 天没有作答（最近一次 last_at）」，last_at 取学生范围里的 last_at 前 10 个字符，为空写「从没作答过」；全班近 7 天都没作答（放假）时规则①对谁都不命中
  伪代码 规则②：近 drop_window 天（period 大于等于 当前日期往前 13 天）的作答 n1、答对 r1，之前 drop_window 天（再往前 14 天）的 n0、r0；n1、n0 都大于等于 drop_min 时，rate1=四舍五入(r1*100/n1)、rate0=四舍五入(r0*100/n0)，rate0 − rate1 大于等于 drop_pct → 命中，reasons 加「近 14 天正确率 rate1%，之前 14 天 rate0%，降了 x 个百分点」（按四舍五入后的整数比较）
  伪代码 任一规则命中就进名单；超过 relay_max 人时名单全给，由调用方截
  伪代码 rules_text 见 规则常量
  伪代码 名单为空：status=empty，hint=「按现在的规则没有掉队的学生。」+ rules_text（空态⑤），chart 同 hint
  伪代码 chart：第一行「掉队名单 n 人（rules_text）」，每人一行「・显示名（用户名）：reasons 用「；」连接」
  伪代码 context_text：「今天：当前日期」+「分析：掉队名单（规则由系统判定，不要自己增减名单）」+ 每人一行同 chart + rules_text +「【后端算好的字符图】」+ chart
  伪代码 返回 {"status": …, "hint": …, "total": 人数, "students": 列表, "rules_text": rules_text, "chart": chart, "context_text": context_text}

公开 函数 分析上下文 kind student? days? top? learner? current_role? auth_mode? subject?
  返回 {status, kind, hint, chart, context_text}；teacher_assist 的 deep_analysis 唯一入口：按 kind 分到上面四个函数，把它们的 status、hint、chart、context_text 原样带回；status 为 ok（调模型解读，chart 附在回答末尾）/ empty（空态①②⑤，hint 直接回给老师，不调模型）/ ask（要老师补充，hint 直接回，不调模型）
  报错 400 分析类型不对
  报错 400 days 不合法
  报错 400 top 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；本函数调用本模块函数时一律带 subject=subject_id
  伪代码 kind 不是 trend、attribution、compare、alert 之一，报错 400 分析类型不对
  伪代码 trend：调用 学情趋势 student=student days=days subject=subject_id；attribution：调用 错题归因 student=student days=days top=top subject=subject_id；compare：调用 学生对比 students=student subject=subject_id（student 是老师话里的多个名字）；alert：调用 掉队名单 subject=subject_id
  伪代码 返回 {"status": r.status, "kind": kind, "hint": r.hint, "chart": status 为 ok 时 r.chart 否则空串, "context_text": status 为 ok 时 r.context_text 否则空串}

## 用例
用例 分析上下文_没有学生空态
  调用 分析上下文 kind=trend
  得 status=empty kind=trend context_text=空

用例 分析上下文_有学生没作答空态
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 分析上下文 kind=attribution
  得 status=empty kind=attribution

用例 分析上下文_类型不对
  调用 分析上下文 kind=bad
  报错 400

用例 学情趋势_不足3天不画趋势
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-30
  调用 学情趋势
  得 status=ok active_days=1 week=1

用例 学情趋势_只算本科目登记的学生
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-20
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q2 correct=0 at=2025-12-25
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q3 correct=1 at=2025-12-30
  先 数据 progress_answer learner=s9 point_code=P1 question_no=q1 correct=1 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q4 correct=1 at=2025-12-31 subject_id=2
  调用 学情趋势 days=14
  得 status=ok active_days=3 week=0

用例 错题归因_按知识点排前N
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 kg_point code=P2 title=点二
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 quiz_question question_no=Q1 level=N5 category=接续 stem=题一 answer=A item_code=I1
  先 数据 progress_answer learner=s1 point_code=P1 question_no=Q1 correct=0 at=2025-12-30
  先 数据 progress_answer learner=s1 point_code=P1 question_no=Q1 correct=0 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P2 question_no=q9 correct=0 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P2 question_no=q9 correct=1 at=2025-12-31
  调用 错题归因 top=1
  得 status=ok total=2

用例 学生对比_没作答的不参与排名
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 kg_point code=P1 title=点一
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-30
  先 数据 progress_score learner=s1 point_code=P1 score=60 at=2025-12-30
  调用 学生对比 students=小一、小二
  得 status=ok total=2 ranked=1

用例 学生对比_只说一位要追问
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  调用 学生对比 students=小一
  得 status=ask

用例 掉队名单_近7天没作答进名单
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 account_user username=s2 password_hash=x display_name=小二 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s2 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-31
  先 数据 progress_answer learner=s2 point_code=P1 question_no=q1 correct=1 at=2025-12-10
  调用 掉队名单
  得 status=ok total=1

用例 掉队名单_正确率降15点进名单
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-10
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q2 correct=1 at=2025-12-10
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q3 correct=1 at=2025-12-10
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q4 correct=1 at=2025-12-10
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q5 correct=1 at=2025-12-10
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q6 correct=1 at=2025-12-11
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q7 correct=1 at=2025-12-11
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q8 correct=1 at=2025-12-11
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q9 correct=1 at=2025-12-11
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q10 correct=1 at=2025-12-11
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q11 correct=0 at=2025-12-30
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q12 correct=0 at=2025-12-30
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q13 correct=0 at=2025-12-30
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q14 correct=1 at=2025-12-30
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q15 correct=1 at=2025-12-30
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q16 correct=1 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q17 correct=1 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q18 correct=1 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q19 correct=1 at=2025-12-31
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q20 correct=1 at=2025-12-31
  调用 掉队名单
  得 status=ok total=1

用例 掉队名单_没有掉队空态
  先 数据 account_user username=s1 password_hash=x display_name=小一 role=student disabled=0 created_at=2025-12-01
  先 数据 subject_student subject_id=1 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 progress_answer learner=s1 point_code=P1 question_no=q1 correct=1 at=2025-12-31
  调用 掉队名单
  得 status=empty total=0
