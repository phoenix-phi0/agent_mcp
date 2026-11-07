模块 dictation
依赖 vocab subject

## 表
表 dictation_attempt 学习记录
  learner 文本 学习者
  word_id 整数 单词编号（vocab_word 的 id，不加外键）
  direction 文本 方向：zh2jp（看中文写日语）或 kanji2kana（看汉字写读音）
  answer 文本 写的内容
  correct 整数 对错（1/0）
  hinted 整数 是否看了提示（1/0）
  at 文本 作答时间（格式 2026-01-01 09:00:00）
  subject_id 整数 所属科目，默认 1（1 是日语语法）

表 dictation_progress 学习记录
  learner 文本 学习者，每人每个科目一行（learner + subject_id 唯一）
  direction 文本 方向：zh2jp 或 kanji2kana
  level 文本 等级N5到N1，可空（非空时只出意思以[等级]开头的词，单词意思开头的[N4]就是等级）
  source 文本 题源，可空（空表示全部单词；review表示只出错词本里的词；否则是知识点编号，只出该知识点下的单词）
  current_word_id 整数 当前词的单词编号，0 表示当前没有词（这一轮已结束）
  answered 整数 当前词是否已交答案（1/0）
  hinted 整数 当前词是否看过提示（1/0）
  asked_ids 长文本 这一轮出过的单词编号，逗号隔开，可空
  asked_count 整数 这一轮出了几个
  right_count 整数 这一轮答对几个
  round_start 整数 这一轮起点：开轮时该学习者 dictation_attempt 的最大 id（没有则 0），id 大于它的作答属于本轮
  subject_id 整数 所属科目，默认 1（1 是日语语法）

表 dictation_question
  subject_id 整数 所属科目
  code 文本 本科目稳定题号（subject_id + code 唯一）
  point_code 文本 本科目知识点编号
  kind 文本 term 或 output
  level 文本 入门、基础或进阶
  prompt_zh 长文本 中文题面
  prompt_ja 长文本 日文题面
  answer 长文本 原始标准答案
  accepted_json 长文本 可接受答案字符串数组的 JSON
  explain_zh 长文本 中文解析
  explain_ja 长文本 日文解析
  enabled 整数 1 为可出题

表 dictation_question_attempt 学习记录
  learner 文本 学习者
  subject_id 整数 所属科目
  question_id 整数 dictation_question 的 id
  direction 文本 term 或 output
  answer 长文本 作答
  correct 整数 对错
  hinted 整数 恒为 0
  at 文本 作答时间

表 dictation_question_progress 学习记录
  learner 文本 学习者，每人每个科目一行（learner + subject_id 唯一）
  subject_id 整数 所属科目
  direction 文本 term 或 output
  level 文本 空或本科目等级
  source 文本 空、review 或本科目知识点编号
  current_question_id 整数 当前题，0 表示结束
  answered 整数 是否已交
  asked_ids 长文本 本轮已出题 id，逗号分隔
  asked_count 整数 本轮题数
  right_count 整数 本轮正确数
  round_start 整数 开轮时此学习者本科目新作答表最大 id，无则 0

## 页面字段
页面 dictation_view 默写页面
  dict_direction 枚举 看中文写日语,看汉字写读音 方向
  dict_level 枚举 全部,N5,N4,N3,N2,N1 等级
  dict_source 枚举 随机,错词复习 题源
  dict_answer 文本 写出来的答案
  py_kind 枚举 术语默写,代码输出 题型
  py_level 枚举 全部,入门,基础,进阶 等级
  py_source 枚举 随机,错题复习 题源
  py_term 文本 写出的术语
  py_output 长文本 写出的标准输出

## 函数
公开 函数 取状态 learner current_role? auth_mode? subject?
  返回 没有进度时 {has_progress: 0}；有进度时 {has_progress: 1, direction, level, source, word_id, prompt, answered, hinted, asked_count, right_count, finished}。prompt 是题面（zh2jp 为中文意思，kanji2kana 为汉字），不含答案；word_id 为 0 时 finished=1 且 prompt 为空串
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：改查 dictation_question_progress（learner、本科目 subject_id），查不到返回 {"has_progress": 0}；current_question_id 为 0 时 prompt 空串、finished=1；否则调用 Py取题 subject_id=subject_id question_id=current_question_id，取不到 prompt 空串，取到 prompt=Py题面(q=题, lang)，finished=0；返回 {has_progress: 1, direction, level, source, word_id: current_question_id, question_id: current_question_id, kind: direction, prompt, answered, hinted: 0, asked_count, right_count, finished}；不返回标准答案、accepted、解析。不读 vocab 和 dictation_progress
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 dictation_progress 一行，查不到返回 {"has_progress": 0}
  伪代码 current_word_id 为 0：prompt 为空串，word_id=0，finished=1
  伪代码 current_word_id 不为 0：调用 vocab.取单词 subject=subject_id word_id=current_word_id，取不到则 prompt 为空串；取到则 prompt = 题面(direction, 该词)；finished=0
  伪代码 返回 {"has_progress": 1, "direction": direction, "level": level, "source": source, "word_id": current_word_id, "prompt": prompt, "answered": answered, "hinted": hinted, "asked_count": asked_count, "right_count": right_count, "finished": finished}

公开 函数 开始 learner direction level? source? current_role? auth_mode? subject?
  返回 {ok} 加上 取状态 的全部字段（新一轮的第一个词）
  报错 400 方向不对
  报错 400 没有可出的词
  报错 400 本科目没开默写
  报错 400 等级不对
  报错 400 题源不对
  报错 400 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写（不能落到日语逻辑）；mode 为 python：direction 不是 term 也不是 output 报错 400 方向不对；level 不为空且不是 入门、基础、进阶 之一报错 400 等级不对；source 不为空也不是 review 时，本科目 dictation_question 里没有 point_code 等于 source 的题就报错 400 题源不对；然后返回 Py开新轮 learner=learner direction=direction level=level source=source subject_id=subject_id lang=lang 的结果
  伪代码 调用 开新轮 learner=learner subject_id=subject_id direction=direction level=level source=source
  伪代码 返回开新轮的结果

公开 函数 再来一轮 learner current_role? auth_mode? subject?
  返回 同「开始」
  报错 400 还没有开始
  报错 400 没有可出的词
  报错 400 本科目没开默写
  报错 400 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：查 dictation_question_progress（learner、本科目），查不到报错 400 还没有开始；用该行的 direction、level、source 返回 Py开新轮 的结果
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 用该行已存的 direction、level、source 调用 开新轮（learner=learner subject_id=subject_id）
  伪代码 返回开新轮的结果

公开 函数 下一个 learner current_role? auth_mode? subject?
  返回 {ok} 加上 取状态 的全部字段；这一轮结束时 finished=1
  报错 400 还没有开始
  报错 400 当前词还没交答案
  报错 400 本科目没开默写
  报错 400 当前题还没交答案
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：查 dictation_question_progress（learner、本科目），查不到报错 400 还没有开始；current_question_id 不为 0 且 answered 等于 0 报错 400 当前题还没交答案；current_question_id 为 0、或 asked_count 不小于 10、或 Py选题（库里的 direction、level、source、asked_ids）返回空：把 current_question_id 置 0、answered 置 1，返回 {"ok": 1} 加 取状态 的字段（finished=1）；否则在一个事务里更新这一行：current_question_id=新题 id，answered=0，asked_ids 末尾追加新题 id（逗号隔开），asked_count 加 1；返回 {"ok": 1} 加 取状态 的字段
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 current_word_id 不为 0 且 answered 等于 0，报错 400 当前词还没交答案
  伪代码 选词 用库里记的 direction、level、source 和 asked_ids（learner 传本人，subject_id 传本科目）。current_word_id 为 0，或 asked_count 不小于 10，或 选词 返回空（没有可出的词）：在库里把 current_word_id 置 0、answered 置 1，返回 {"ok": 1} 加 取状态 的字段（finished=1）
  伪代码 否则在一个事务里更新 dictation_progress（按 learner 和本科目 subject_id 定位那一行，同上）：current_word_id=新词 id，answered=0，hinted=0，asked_ids 末尾追加新词 id，asked_count 加 1
  伪代码 返回 {"ok": 1} 加 取状态 的字段

公开 函数 提示 learner current_role? auth_mode? subject?
  返回 {ok, hinted, first_kana, length}，first_kana 是当前词假名的第一个字，length 是假名字数
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  报错 400 这个科目的默写没有提示
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：报错 400 这个科目的默写没有提示，不读不写任何进度（伪造的提示请求不改变进度）
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 current_word_id 为 0，报错 400 当前没有词；answered 等于 1，报错 400 当前词已经交过答案
  伪代码 调用 vocab.取单词 subject=subject_id word_id=current_word_id，取不到报错 404 当前词已不存在
  伪代码 把 dictation_progress（该 learner 在当前科目 subject_id（本科目 得到的 subject_id）下那行）的 hinted 置 1
  伪代码 返回 {"ok": 1, "hinted": 1, "first_kana": 假名第一个字, "length": 假名字数}

公开 函数 交答案 learner answer current_role? auth_mode? subject?
  返回 {ok, correct, hinted, note, kanji, kana, meaning, asked_count, right_count}，correct 为 1/0，note 是给人看的一句补充（同义词也算对、写成了同读音的另一个词、这是另一个读法……，没有为空串），kanji、kana、meaning 是标准答案所在单词
  报错 400 答案不能为空
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  报错 400 本科目没开默写
  报错 400 当前没有题
  报错 400 当前题已经交过答案
  报错 404 当前题已不存在
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：下面日语那条「answer 去掉首尾空白后为空」的检查不走，改按这里：查 dictation_question_progress（learner、本科目），查不到报错 400 还没有开始；判的永远是库里的 current_question_id，不信前端传的题号或答案；current_question_id 为 0 报错 400 当前没有题；answered 等于 1 报错 400 当前题已经交过答案（不写库）；调用 Py取题 subject_id=subject_id question_id=current_question_id，取不到报错 404 当前题已不存在；题.kind 为 term 且 answer 去掉首尾空白后为空，报错 400 答案不能为空（output 题空串可以交，不做全局非空检查）；调用 Py判题 kind=题.kind answer=answer accepted_json=题.accepted_json 得 correct；在一个事务里：往 dictation_question_attempt 插一行 (learner, subject_id=本科目, question_id=current_question_id, direction=题.kind, answer=原样作答（不去空白）, correct, hinted=0, at=当前时间)，更新 dictation_question_progress 这一行 answered=1、答对时 right_count 加 1；不写 dictation_attempt、dictation_progress、vocab、做题作答、掌握、得分；返回 {"ok": 1, "correct": correct, "hinted": 0, "note": "", "kind": 题.kind, "prompt": Py题面(q=题, lang), "answer": 题.answer 原样, "explain": Py解析(q=题, lang), "asked_count": asked_count, "right_count": 更新后的 right_count}
  伪代码 answer 去掉首尾空白后为空，报错 400 答案不能为空
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 判的永远是库里记的 current_word_id，不信前端传的；current_word_id 为 0 报错 400 当前没有词
  伪代码 answered 等于 1，报错 400 当前词已经交过答案（同一个词交两次只算一次，不写库）
  伪代码 调用 vocab.取单词 subject=subject_id word_id=current_word_id，取不到报错 404 当前词已不存在
  伪代码 判对错：调用 判词 direction=direction word=该词 answer=answer subject_id=subject_id，得 correct、note（direction 为 zh2jp 时写汉字或假名都算对，意思完全一样的同义词也算对；kanji2kana 时写假名才算对；比较前先归一：全角半角统一、去空白和句号逗号、片假名当平假名）
  伪代码 在一个事务里：往 dictation_attempt 插入一行 (learner, word_id=current_word_id, direction, answer, correct, hinted=progress.hinted, at=当前时间, subject_id=本科目)；更新 dictation_progress（该 learner 在本科目 subject_id 下那行）：answered=1，答对时 right_count 加 1
  伪代码 默写不写做题的作答、掌握、得分表，不影响知识点分数；dictation_attempt、dictation_progress 的行都带本科目 subject_id
  伪代码 返回 {"ok": 1, "correct": correct, "hinted": progress.hinted, "note": note, "kanji": 汉字, "kana": 假名, "meaning": 意思, "asked_count": asked_count, "right_count": 更新后的 right_count}

公开 函数 列本轮错词 learner current_role? auth_mode? subject?
  返回 {learner, total, words}，words 是 [{word_id, direction, kanji, kana, meaning, answer}]，按作答 id 升序；没有进度时 total 为 0、words 为空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：查 dictation_question_progress（learner、本科目），查不到返回 {"learner": learner, "total": 0, "words": []}；查 dictation_question_attempt 中 learner 相等、subject_id 等于本科目、id 大于 round_start、correct 等于 0 的行，按 id 升序；对每行调用 Py取题，取不到跳过；words 每项 {question_id, word_id: question_id, direction, kind, prompt: Py题面(q=题, lang), answer: 该行作答}；返回 {learner, total: 行数, words}
  伪代码 按 learner 和当前科目 subject_id（本科目 得到的 subject_id）查 dictation_progress，查不到返回 {"learner": learner, "total": 0, "words": []}
  伪代码 查 dictation_attempt 中 learner 相等、subject_id 等于本科目、id 大于 round_start、correct 等于 0 的行，按 id 升序
  伪代码 对每行调用 vocab.取单词 subject=subject_id word_id=该行 word_id，取不到（包括属于别的科目的词）的行跳过；其余拼出 {word_id, direction, kanji, kana, meaning, answer}
  伪代码 返回 {"learner": learner, "total": 行数, "words": 列表}

公开 函数 取错词本 learner lang? current_role? auth_mode? subject?
  返回 {learner, total, words}，words 是 [{word_id, direction, kanji, kana, meaning, last_answer, last_at}]，按最近一次答错的作答 id 从大到小；last_answer 和 last_at 是最近一次答错时写的内容和时间
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：lang 参数不为空（zh 或 ja，教师看学生错题本时传教师自己的界面语言）就用它，否则用 learner 的界面语言；调用 Py算错题本 learner=learner subject_id=subject_id lang=lang 得列表；返回 {"learner": learner, "total": 列表长度, "words": 列表}；日语分支不看 lang 参数，words 每项 {question_id, word_id, direction, kind, prompt, last_answer, last_at}
  伪代码 调用 算错词本 learner=learner subject_id=subject_id 得到列表
  伪代码 返回 {"learner": learner, "total": 列表长度, "words": 列表}

公开 函数 统计错词本数 learner current_role? auth_mode? subject?
  返回 {learner, total}，total 是错词本条数（某词某方向算一条）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：调用 Py算错题本 learner=learner subject_id=subject_id lang=lang，返回 {"learner": learner, "total": 列表长度}
  伪代码 调用 算错词本 learner=learner subject_id=subject_id 得到列表
  伪代码 返回 {"learner": learner, "total": 列表长度}

公开 函数 取默写概况 learner current_role? auth_mode? subject?
  返回 {learner, total, right, accuracy, wrong_book_count, last_at, mode}（mode：本科目 科目模式 为 python 或 python_off 时是 python，否则 jp；K192 新增键，日语其余键一字不变），total 是默写作答总数，right 是答对数，accuracy 是正确率百分比（right*100/total 四舍五入取整，total 为 0 时 0），last_at 是最近一次作答时间（没有作答为空串）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：返回带 mode=python；mode 为 jp 时返回带 mode=jp。Python 时 total、right、last_at 改按 dictation_question_attempt（learner 相等、subject_id 等于本科目）统计，wrong_book_count 取 Py算错题本 的列表长度；accuracy 口径同下；返回形状同下
  伪代码 统计 dictation_attempt 中 learner 相等且 subject_id 等于本科目（别的科目的作答不算）的行数 total 和其中 correct 等于 1 的行数 right
  伪代码 last_at 取这些行中 id 最大的那行的 at，没有则空串
  伪代码 调用 算错词本 learner=learner subject_id=subject_id，wrong_book_count 取列表长度
  伪代码 返回 {"learner": learner, "total": total, "right": right, "accuracy": accuracy, "wrong_book_count": wrong_book_count, "last_at": last_at}

公开 函数 默写页面 learner current_role? auth_mode? subject?
  返回 {dstat, form}；默写页「进入时」的整页状态（进页面不推词卡、不动 dphase）：dstat 是这一轮成绩文本，没练过为空串；form 是顶栏三个下拉的回填 {dict_direction, dict_level, dict_source}，取库里上次选的，没选过填「看中文写日语」「全部」「随机」
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：成绩文本的前缀（中文「这一轮」）在 ja 下写「このセット」。词卡（拼词卡）在 ja 下：head 的方向写 中国語を見て日本語を書く（zh2jp）或 漢字を見て読みを書く（其他）；sub 写「意味：{bare}」；hint 写「ヒント：最初の仮名は「{fk}」、読みは全部で {len} 文字」。方向名 这个内部函数本身不改（表单回填和方向代号用它做下拉值），另外取日文名。lang 用 调用 subject.取界面语言 username=learner 取。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：返回 {"dstat": Py成绩文本(s, lang), "form": Py表单回填(s), "dmode": "python"}，s 是 取状态（走 Python 分支）的结果（python_off 也回 dmode=python：页面显示 Python 的下拉，点开始时才报 400 本科目没开默写）；mode 为 jp：在原来的返回上只多一个键 "dmode": "jp"，dstat、form 一字不变
  伪代码 调用 取状态 learner=learner subject=subject_id，得 s
  伪代码 返回 {"dstat": 成绩文本(s), "form": 表单回填(s)}

公开 函数 开始页面 learner dict_direction? dict_level? dict_source? py_kind? py_level? py_source? current_role? auth_mode? subject?
  返回 默写页「开始」的整页状态，同 开轮页面：出得了词为 {dphase, dcard, dstat}，dphase=ask；错词复习但错词本里没有可出的词为 {dphase, dempty, dcard, dstat}，dphase=empty（不报错）
  报错 400 方向不对
  报错 400 题源不对
  报错 400 没有可出的词
  报错 400 本科目没开默写
  报错 400 等级不对
  报错 400 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：dempty 在 ja 下写「「{方向日文名}」（レベル：{レベル}）の間違えた単語帳は空です。間違えた単語がないか、すべて2回連続で正解しています。まずランダムに1セット練習しましょう。」，レベル 为全部时写「すべて」。其余同 默写页面 的 K191 日语。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；参数 py_kind、py_level、py_source 只给 Python 用（日语科目不看它们，dict_* 照旧）；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：不看 dict_*；py_kind 为空取「术语默写」、py_level 为空取「全部」、py_source 为空取「随机」；py_kind「术语默写」转 term、「代码输出」转 output，其余报错 400 方向不对；py_level「全部」转空串，入门、基础、进阶 原值，其余报错 400 等级不对；py_source「随机」转空串、「错题复习」转 review，其余报错 400 题源不对；返回 Py开轮页面 learner=learner direction=direction level=level source=source subject_id=subject_id lang=lang 的结果
  伪代码 dict_direction 为空取「看中文写日语」、dict_level 为空取「全部」、dict_source 为空取「随机」（页面下拉的默认）
  伪代码 值域转换：调用 方向代号 得 direction；dict_level 为「全部」时 level 取空串，否则原值；dict_source 为「随机」时 source 取空串，「错词复习」取 review，其余报错 400 题源不对
  伪代码 返回 开轮页面 learner=learner direction=direction level=level source=source subject_id=subject_id 的结果

公开 函数 随机页面 learner current_role? auth_mode? subject?
  返回 默写页「随机练一轮」（错词本空时卡上的按钮）的整页状态：{dphase, dcard, dstat, form}，形状同 开轮页面；form 回填 {dict_direction, dict_level, dict_source}，题源回填「随机」
  报错 400 没有可出的词
  报错 400 本科目没开默写
  报错 400 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：调用 取状态 learner=learner subject=subject_id 得 s（Python 分支），direction 取 s.direction（没进度取 term），level 取 s.level（没进度空串），source 空串；调用 Py开轮页面 得 r，r 加上 form：{py_kind: term 为「术语默写」output 为「代码输出」, py_level: 空填「全部」否则原值, py_source: 「随机」}
  伪代码 调用 取状态 learner=learner subject=subject_id，得 s；方向、等级照库里记的（没记过取 zh2jp、不限等级），题源随机（source 取空串）
  伪代码 调用 开轮页面 learner=learner direction=s.direction level=s.level source=空串 subject_id=subject_id，得 r，r 加上 form：方向转中文、等级空填「全部」、dict_source=「随机」

公开 函数 练错词页面 learner current_role? auth_mode? subject?
  返回 默写页「练错词」（一轮结束时的按钮）的整页状态，形状同 随机页面；题源 review，form 的 dict_source 回填「错词复习」；错词本里没有可出的词时 dphase=empty
  报错 400 方向不对
  报错 400 本科目没开默写
  报错 400 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：同 随机页面 的 Python 分支，只是 source 取 review，form 的 py_source 回填「错题复习」；错题本里没有可出的题时 dphase=empty
  伪代码 调用 取状态 learner=learner subject=subject_id，得 s；方向、等级照库里记的（没记过取 zh2jp、不限等级），题源 review
  伪代码 调用 开轮页面 learner=learner direction=s.direction level=s.level source=review subject_id=subject_id，得 r，r 加上 form：方向转中文、等级空填「全部」、dict_source=「错词复习」

公开 函数 载入页面 learner source? direction? level? current_role? auth_mode? subject?
  返回 默写页「载入」的整页状态（地址 #默写?source=review 进来，还可带 direction=reading|meaning、level=N4；前端把地址参数并进提交调用）：形状同 随机页面，form 回填本次所选
  报错 400 没有可出的词
  报错 400 本科目没开默写
  报错 400 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：同 开始页面 的 K191 日语。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：调用 取状态（Python 分支）得 s；direction 参数是 term 或 output 时取参数，否则取 s.direction（没进度取 term；参数 reading、meaning 等日语值不理）；level 参数为「全部」当空串，是 入门、基础、进阶 时取参数，其余（含空）取 s.level（没进度空串）；source 参数 review 取 review、random 取空串，其余取库里的（review 保持，其余空串）；调用 Py开轮页面 得 r，r 加上 form：{py_kind, py_level（空填「全部」）, py_source（review 为「错题复习」否则「随机」）}
  伪代码 调用 取状态 learner=learner subject=subject_id，得 s；方向默认取库里的（没记过取 zh2jp），direction 参数 reading 换成 kanji2kana、meaning 换成 zh2jp，其他值不理；等级 level 参数不为空取参数（「全部」当空串）否则取库里的；题源默认取库里的（review 保持，其余空串），source 参数 review 换成 review、random 换成空串，其他值不理
  伪代码 调用 开轮页面 learner=learner direction=direction level=level source=source subject_id=subject_id，得 r，r 加上 form：方向转中文、等级空填「全部」、题源 review 回填「错词复习」否则「随机」

公开 函数 判答案页面 learner dict_answer? py_term? py_output? current_role? auth_mode? subject?
  返回 默写页「交」的整页状态：{dphase, dcard, dstat}；dphase=done；dcard 是判完的词卡 {code, head, stem, sub, hint, verdict, right, mine, note}，code 与交之前同一张（前端不翻页），hint 看过提示才有，verdict 是「○对了」/「○对了（看了提示，不算进错词本的「连续答对」）」/「✗不对」，right 是「正确：汉字【读音】意思」（没汉字或汉字等于假名时是「读音 意思」，意思去掉开头的等级），mine 是「你写的：答案」，note 是 判词 的补充句
  报错 400 答案不能为空
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  报错 400 本科目没开默写
  报错 400 当前没有题
  报错 400 当前题已经交过答案
  报错 404 当前题已不存在
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：lang 为 ja 时 verdict 写 ✗ 不正解、○ 正解、○ 正解（ヒントを見たので、間違えた単語帳の「連続正解」には数えません）；right 的前缀写「正解：」；mine 的前缀写「あなたの答え：」；stat 前缀写「このセット」。note（交答案 返回）在 ja 下也写日文：看 交答案 里 note 的几种取值，同义词也算对写「同じ意味の単語も正解です」，同读音的另一个词写「同じ読みの別の単語です」，另一个读法写「別の読み方です」，别的情形照中文语义翻成自然的日语。其余同 默写页面 的 K191 日语。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；参数 py_term、py_output 只给 Python 用；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：调用 取状态（Python 分支）得 s；作答 a：s.direction 为 term 取 py_term，为 output 取 py_output，原样不去空白（空也照传，由 交答案 决定能不能交）；调用 交答案 learner=learner subject=subject_id answer=a 得 r（报错原样向上抛）；调用 Py取题 subject_id=subject_id question_id=s.question_id，card=Py拼题卡(q=题, r.asked_count, lang)，再填 verdict（中文 答对「○对了」答错「✗不对」；ja「○ 正解」「✗ 不正解」）、answer=r.answer 原样、explain=r.explain、mine=a 原样；返回 {"dphase": "done", "dcard": card, "dstat": 中文「这一轮 {r.right_count}/{r.asked_count}」ja「このセット {r.right_count}/{r.asked_count}」, "dmode": "python"}
  伪代码 调用 取状态 learner=learner subject=subject_id，得 s（要交之前的 word_id、direction、asked_count）；调用 交答案 learner=learner subject=subject_id answer=dict_answer，得 r（报错原样向上抛）
  伪代码 word 取 {id: s.word_id, kanji: r.kanji, kana: r.kana, meaning: r.meaning}；调用 拼词卡 direction=s.direction word=word asked_count=r.asked_count hinted=r.hinted，得 card，再填 verdict、right、mine、note
  伪代码 返回 {"dphase": "done", "dcard": card, "dstat": 「这一轮 {r.right_count}/{r.asked_count}」}

公开 函数 提示页面 learner current_role? auth_mode? subject?
  返回 默写页「提示」的整页状态：{dphase, dcard, dstat}；dphase=ask；dcard 是带提示的词卡（hint 为「提示：第一个假名是「x」，读音一共 n 个字」，verdict、right、mine、note 空串）
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  报错 400 这个科目的默写没有提示
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：同 默写页面 的 K191 日语。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python 或 python_off：报错 400 这个科目的默写没有提示（同 提示，不改进度）
  伪代码 调用 提示 learner=learner subject=subject_id（报错原样向上抛）；调用 取状态 learner=learner subject=subject_id，得 s；调用 vocab.取单词 subject=subject_id word_id=s.word_id
  伪代码 调用 拼词卡 direction=s.direction word=该词 asked_count=s.asked_count hinted=1，得 card；返回 {"dphase": "ask", "dcard": card, "dstat": 成绩文本(s)}

公开 函数 下一个页面 learner current_role? auth_mode? subject?
  返回 默写页「下一个」的整页状态：出下一个词为 {dphase, dcard, dstat}，dphase=ask；这一轮结束为 {dphase, dround, dstat, round_wrong}，dphase=end，dround 是 {text}，round_wrong 是这一轮错的词 [{label, mine}]
  报错 400 还没有开始
  报错 400 当前词还没交答案
  报错 400 本科目没开默写
  报错 400 当前题还没交答案
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 K191 日语：lang 为 ja 时 round 文案写「このセットが終わりました：{asked_count} 問中 {right_count} 問正解。」，全对写「このセットが終わりました：{asked_count} 問すべて正解。」。其余同 默写页面 的 K191 日语。
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：调用 下一个 learner=learner subject=subject_id 得 s（Python 分支，报错原样抛）；s.finished 等于 0：Py取题 subject_id=subject_id question_id=s.question_id，card=Py拼题卡(q=题, s.asked_count, lang)，返回 {dphase: ask, dcard: card, dstat: Py成绩文本(s, lang), dmode: python}；s.finished 等于 1：dphase=end；dround.text 中文 全对「这一轮做完了：{asked_count} 道全对。」否则「这一轮做完了：答对 {right_count} 道，共 {asked_count} 道。」，ja 全对「このセットが終わりました：{asked_count} 問すべて正解。」否则「このセットが終わりました：{asked_count} 問中 {right_count} 問正解。」；round_wrong 调用 列本轮错词 learner=learner subject=subject_id（Python 分支），逐项转 {label: prompt, mine: answer}；返回 {dphase, dround, dstat, round_wrong, dmode: python}
  伪代码 调用 下一个 learner=learner subject=subject_id，得 s（报错原样向上抛）
  伪代码 s.finished 等于 0：调用 vocab.取单词 subject=subject_id word_id=s.word_id，拼词卡 hinted=0，返回 {dphase: ask, dcard, dstat: 成绩文本(s)}
  伪代码 s.finished 等于 1：dphase=end；dround.text 在 right_count 等于 asked_count 时为「这一轮做完了：{asked_count} 个全对。」否则「这一轮做完了：答对 {right_count} 个，共 {asked_count} 个。」；round_wrong 调用 列本轮错词 learner=learner subject=subject_id，逐项转 {label: 「汉字【读音】意思」（没汉字或汉字等于假名时「读音 意思」，意思去掉开头的等级）, mine: answer}

公开 函数 再来一轮页面 learner current_role? auth_mode? subject?
  返回 默写页「再来一轮」的整页状态，形状同 开轮页面（新一轮第一个词 dphase=ask；题源是错词复习但错词本里没有可出的词 dphase=empty）
  报错 400 还没有开始
  报错 400 没有可出的词
  报错 400 本科目没开默写
  报错 400 没有可出的题
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；current_role、auth_mode、subject 都可选（路由层注入登录角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id；本函数在本模块内调用其它函数（含公开函数）、调用 vocab. 的函数时一律带 subject=subject_id（已解析，不再校验）
  伪代码 K192 Python：科目那一步之后先调用本模块 科目模式 subject_id=subject_id 得 mode（python / python_off / jp）；lang 用 调用 subject.取界面语言 username=learner 取（Python 分支要用时才取）。mode 为 jp 时走下面原来的日语逻辑，一字不改；mode 为 python_off：报错 400 本科目没开默写；mode 为 python：调用 取状态（Python 分支）得 s，has_progress 等于 0 报错 400 还没有开始；s.source 等于 review 且 Py选题 learner direction=s.direction level=s.level source=review asked_ids=空串 返回空：返回 Py空错题状态 learner=learner direction=s.direction level=s.level subject_id=subject_id lang=lang；否则调用 再来一轮 learner=learner subject=subject_id（Python 分支）得 s2，Py取题 subject_id=subject_id question_id=s2.question_id，card=Py拼题卡(q=题, s2.asked_count, lang)，返回 {dphase: ask, dcard: card, dstat: Py成绩文本(s2, lang), dmode: python}
  伪代码 调用 取状态 learner=learner subject=subject_id，得 s；has_progress 等于 0 报错 400 还没有开始
  伪代码 s.source 等于 review 且 调用 候选词 learner=learner subject_id=subject_id direction=s.direction level=s.level source=review asked_ids=空串 得到空列表：返回 空错词状态 learner=learner subject_id=subject_id direction=s.direction level=s.level
  伪代码 否则调用 再来一轮 learner=learner subject=subject_id（报错原样向上抛）得 s2；调用 vocab.取单词 subject=subject_id word_id=s2.word_id，拼词卡 hinted=0；返回 {dphase: ask, dcard, dstat: 成绩文本(s2)}

函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出）；默写只有学习者自己的作答和偏好，都是读类，不传 need

函数 题面 direction word
  返回 题面文字
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 direction 为 zh2jp 返回 word.meaning；否则返回 word.kanji

函数 选词 learner direction level source asked_ids subject_id
  返回 一个单词对象 {id, kanji, kana, meaning, point_code}；没有可出的词返回空
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 筛选和挑选全部下推到 vocab.挑默写词（SQL 里做），这里不对词表逐词循环；取不到词返回空。口径与原来一字不差：没练过优先、都练过了才从全部里挑、错词复习不分练没练过
  伪代码 seed = 当前时间戳（时间戳对候选数取余挑第几个，口径同原来）
  伪代码 source 等于 review：取错词本编号串 only_ids（同 候选词 的第一步，限本科目 subject_id，没有则返回空），调用 vocab.挑默写词 subject=subject_id direction=direction level=level only_ids=only_ids skip_ids=asked_ids seed=seed，total 为 0 返回空，否则返回它的 word（按错词本顺序的第 (seed 对 total 取余) 个，口径同原来；不调用 候选词，也不在 DSL 里遍历取第几个）
  伪代码 source 不等于 review（随机，或按知识点编号）：practiced = 该 learner 在该 direction 上有过作答的单词编号（dictation_attempt 里 learner 相等、subject_id 等于本科目、direction 相等的 word_id 去重，用一条查询在库里拼成逗号隔开的一个字符串，不看对错、不看有没有提示；别的方向、别的 learner、别的科目的不算）；先调用 vocab.挑默写词 subject=subject_id direction=direction level=level point_code=source skip_ids=asked_ids 加 practiced（两个逗号串合并，空的不拼，不能出现开头、结尾或连续的逗号；asked_ids 为 0 当空）seed=seed，total 大于 0 就取它的 word（没练过的）；total 为 0 再调用 vocab.挑默写词 subject=subject_id direction=direction level=level point_code=source skip_ids=asked_ids seed=seed（全练过了从全部候选里取），仍为 0 返回空
  伪代码 一轮里的词只出一次的约束靠 asked_ids 进 skip_ids 实现（asked_ids 逗号隔开，可空）

函数 候选词 learner direction level source asked_ids subject_id
  返回 可出的单词列表 [{id, kanji, kana, meaning, point_code}]，保持错词本的顺序（last_wrong_id 从大到小）；只给错词复习（source 等于 review）用，随机和按知识点不再经过它
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 错词本编号串：用一条查询在库里取出该 learner 在本科目 subject_id 下、direction 方向上的错词本单词编号，按 last_wrong_id 从大到小，拼成逗号隔开的一个字符串 only_ids（口径同 算错词本 的错词本查询：只是多一个 direction 条件、只取 word_id；不在 DSL 里对错词逐条循环、不逐条调 vocab.取单词）；没有则返回空列表
  伪代码 调用 vocab.列默写词 subject=subject_id direction=direction level=level only_ids=only_ids skip_ids=asked_ids（asked_ids 为空或 0 时传空串），它按 only_ids 的先后排序并负责全部排除规则（level 前缀、meaning/kanji 非空、五十音、语法说明、bare 规则、已被删的词自然不在其中）；直接返回它的 words（不再自己逐词循环、不做二重循环对号）

函数 开新轮 learner direction level? source? subject_id
  返回 {ok} 加上 取状态 的全部字段
  报错 400 方向不对
  报错 400 没有可出的词
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 direction 不是 zh2jp 也不是 kanji2kana，报错 400 方向不对
  伪代码 调用 选词 learner=learner direction=direction level=level source=source asked_ids=空串 subject_id=subject_id，返回空则报错 400 没有可出的词
  伪代码 base = dictation_attempt 中该 learner 在本科目 subject_id 下的最大 id，没有则 0
  伪代码 在一个事务里：该 learner 在当前科目 subject_id（调用方传入）下 dictation_progress 已有行则更新，没有则插入（插入时写 subject_id）；写入 direction、level、source、current_word_id=新词 id、answered=0、hinted=0、asked_ids=新词 id、asked_count=1、right_count=0、round_start=base
  伪代码 返回 {"ok": 1} 加 取状态 的字段

函数 判词 direction word answer subject_id
  返回 {correct, note}；correct 为 1/0，note 是给人看的一句补充（同义词也算对、写成了同读音的另一个词、这是另一个读法……），没有为空串
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 找沾边的候选词：调用 vocab.列单词 subject=subject_id keyword=该词假名；该词汉字不为空时再调用 vocab.列单词 subject=subject_id keyword=汉字；该词意思去掉开头的 [N4] 等级前缀后不为空时再调用 vocab.列单词 subject=subject_id keyword=去等级后的意思（候选只在本科目里找）；三次结果合并、按 id 去重、去掉这个词自己，最多留 50 个，每项留 {kanji, kana, meaning}
  伪代码 调用 判默写（japanese 包的现有动词），参数是一个结构 {方向, 作答, 词, 候选}：direction 为 zh2jp 时方向取 meaning，否则取 reading；作答=answer；词={kanji, kana, meaning}；候选=上一步的列表
  伪代码 返回 {"correct": 判默写的 correct 转成整数, "note": 判默写的 note}

函数 拼词卡 direction word asked_count hinted
  返回 词卡对象 {code, head, stem, sub, hint, verdict, right, mine, note}；verdict、right、mine、note 都是空串（判完才填）
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 bare 取 word.meaning 去掉开头的「[N1]」到「[N5]」等级前缀再去首尾空白；level 取前缀里的等级（没有为空串）
  伪代码 code=「{word.id}-{asked_count}」（同一张卡判完前后 code 不变）；head 在 level 不为空时是「{level}・{方向名}」，否则只有方向名
  伪代码 direction 为 zh2jp：stem=bare，sub 空串；否则 stem=word.kanji，sub=「意思：{bare}」
  伪代码 hinted 等于 1：hint=「提示：第一个假名是「{假名第一个字}」，读音一共 {假名字数} 个字」，否则空串

函数 方向名 direction
  返回 方向的中文：zh2jp 是「看中文写日语」，kanji2kana 是「看汉字写读音」
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id

函数 方向代号 label
  返回 方向的代号：「看中文写日语」是 zh2jp，「看汉字写读音」是 kanji2kana
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  报错 400 方向不对
  伪代码 label 是这两句之外的值，报错 400 方向不对

函数 成绩文本 s
  返回 这一轮成绩文本；s 是 取状态 的结果，没有进度为空串，否则「这一轮 {right_count}/{已答数}」，已答数 = asked_count，当前词还没交答案（word_id 不为 0 且 answered 等于 0）时减 1
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id

函数 表单回填 s
  返回 {dict_direction, dict_level, dict_source}，都是顶栏下拉的中文值；没有进度时「看中文写日语」「全部」「随机」
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 有进度：方向按 direction 转中文，level 为空填「全部」，source 等于 review 为「错词复习」其余「随机」

函数 空错词状态 learner direction level subject_id
  返回 {dphase, dempty, dcard, dstat}；dphase=empty，dempty=「「{方向名}」这个方向（等级：{level 为空填全部}）的错词本是空的——没有答错过的词，或者都已经连续答对两次了。先随机练一轮吧。」，dcard、dstat 空串
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 记下这次的选择（下次进页面顶栏还是它）：该 learner 在当前科目 subject_id（调用方传入）下 dictation_progress 已有行：current_word_id 为 0（没有进行中的题）或 answered 等于 1（当前词已交、卡上只剩「下一个」）时才只更新 direction、level、source=review（本轮其余字段不动），current_word_id 不为 0 且 answered 等于 0（有还没交的题）时不改这三项，免得还没答的词题面方向中途变掉（K192 按现行代码写明，查询 dictation_progress_settings 的 WHERE current_word_id = 0 OR answered = 1，一字不改）（返回照常给空错词状态）；没有行则插入（subject_id 取当前科目，current_word_id=0、answered=1、hinted=0、asked_ids 空、asked_count=0、right_count=0、round_start=该 learner 在本科目 subject_id 下 dictation_attempt 的最大 id，没有为 0）

函数 开轮页面 learner direction level source subject_id
  返回 {dphase, dcard, dstat}；出得了词 dphase=ask，dcard 是新词卡，dstat 是「这一轮 0/0」；source 等于 review 但错词本里没有可出的词时返回 空错词状态 的结果
  报错 400 方向不对
  报错 400 没有可出的词
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 source 等于 review：调用 候选词 learner=learner subject_id=subject_id direction=direction level=level source=review asked_ids=空串，为空则返回 空错词状态 learner=learner subject_id=subject_id direction=direction level=level
  伪代码 调用 开始 learner=learner subject=subject_id direction=direction level=level source=source，得 s（报错原样向上抛）；调用 vocab.取单词 subject=subject_id word_id=s.word_id，拼词卡 hinted=0
  伪代码 返回 {"dphase": "ask", "dcard": card, "dstat": 成绩文本(s)}

函数 算错词本 learner subject_id
  返回 列表 [{word_id, direction, kanji, kana, meaning, last_answer, last_at, last_wrong_id}]，按 last_wrong_id 从大到小
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）；下面所有查询和写入都只限这个 subject_id；调用 vocab. 的函数时一律带 subject=subject_id
  伪代码 查 dictation_attempt 中该 learner 且 subject_id 等于传入 subject_id 的全部行（别的科目的作答不进错词本），按 (word_id, direction) 分组，各组内按 id 排序
  伪代码 实现要求（性能）：错词本这一条查询要在一遍扫描里做完（SQL 里用窗口函数 MAX(CASE WHEN correct=0 THEN id END) OVER (PARTITION BY word_id, direction) 先算出每组的 last_wrong_id，再按组数「之后连续答对」；不能对每个 (词, 方向) 再回头扫一遍该学习者的作答），学习者有一万多条作答、几百个错词时也要在 0.1 秒内
  伪代码 每组取 correct 等于 0 的最大 id 为 last_wrong_id，该组没有答错的行则跳过
  伪代码 数该组中 id 大于 last_wrong_id、correct 等于 1 且 hinted 等于 0 的行数；不小于 2 则该词该方向已出本，跳过（看过提示答对不算进连续两次）
  伪代码 对留下的组调用 vocab.取单词 subject=subject_id word_id=word_id，取不到（词已被删，或属于别的科目）则跳过；其余拼出条目，last_answer、last_at 取 last_wrong_id 那行的 answer、at
  伪代码 按 last_wrong_id 从大到小排序后返回

函数 科目模式 subject_id
  返回 {mode}：python（本科目 subject_info.code 是 python 且 caps 里 dictation 为 1）、python_off（code 是 python 但 caps 没开 dictation）、jp（其余科目，包括 subject_info 里没有这一行）
  伪代码 subject_id 是调用方传入的已解析科目编号（整数）
  伪代码 用一条查询（dictation_subject_mode）按 id=subject_id 在 subject_info 取一行算 mode：code 不等于 python 为 jp；code 等于 python 时 caps 是合法 JSON（json_valid）且 json_extract(caps,'$.dictation') 等于 1 为 python，否则 python_off；查不到行为 jp。SQL 里先判 code 再判 JSON（CASE 嵌套），caps 不是合法 JSON（例如 x）时不能报错
  伪代码 只读，不改 caps；其余科目一律 jp，保证日语和别的科目行为一字不变

函数 Py取题 subject_id question_id
  返回 题对象 {id, code, point_code, kind, level, prompt_zh, prompt_ja, answer, accepted_json, explain_zh, explain_ja, enabled}；取不到返回空
  伪代码 按 id=question_id 且 subject_id=本科目 取 dictation_question 一行（别的科目的题当取不到）；不看 enabled（已经出了的题停用后照样能交、错题本照样显示）

函数 Py题面 q lang
  返回 题面文字
  伪代码 lang 为 ja 且 q.prompt_ja 去首尾空白后不为空，返回 q.prompt_ja；否则返回 q.prompt_zh；原样返回，不经过词表、不做任何替换（题面里有代码）

函数 Py解析 q lang
  返回 解析文字
  伪代码 lang 为 ja 且 q.explain_ja 去首尾空白后不为空，返回 q.explain_ja；否则返回 q.explain_zh；原样返回，不经过词表

函数 Py方向名 direction lang
  返回 题型显示名：term 为「术语默写」（ja「用語の書き取り」），output 为「代码输出」（ja「コードの出力」）

函数 Py等级名 level lang
  返回 等级显示名：入门、基础、进阶 原样（ja 入門、基礎、応用），空串为「全部」（ja「すべて」）

函数 Py选题 learner direction level source asked_ids subject_id
  返回 一个题对象（同 Py取题）；没有可出的题返回空
  伪代码 筛选和挑选都在 SQL 里做（不在 DSL 里逐题循环）：dictation_question 中 subject_id=本科目、enabled=1、kind=direction；level 不为空时 level 相等；source 为空不限知识点，source 为 review 见下，否则 point_code=source；id 不在 asked_ids 里（asked_ids 逗号隔开，可空；用 instr(','||:asked_ids||',', ','||id||',')=0 这类写法）
  伪代码 source 为 review：只取 Py算错题本 口径下该 learner 在本科目、direction 方向仍在错题本里的题（最近一次错误之后无提示答对不到 2 次），按 last_wrong_id 从大到小取第一个不在 asked_ids 里的；不分练没练过
  伪代码 source 不为 review（随机或按知识点）：先在没练过的题里挑（dictation_question_attempt 中该 learner、本科目、该 direction 没有作答过的题；别人、别的科目、别的题型的作答不算），没有再从全部候选里挑；挑法：seed=当前时间戳，按 id 排序取第 (seed 对候选数取余) 个
  伪代码 一轮里同一题只出一次靠 asked_ids 排除实现

函数 Py开新轮 learner direction level source subject_id lang
  返回 {ok} 加上 取状态 的全部字段（Python 分支的形状）
  报错 400 没有可出的题
  伪代码 调用 Py选题 learner=learner direction=direction level=level source=source asked_ids=空串 subject_id=subject_id，返回空则报错 400 没有可出的题
  伪代码 base = dictation_question_attempt 中该 learner 在本科目下的最大 id，没有则 0
  伪代码 在一个事务里：dictation_question_progress 中该 learner、本科目已有行则更新，没有则插入（插入时写 subject_id）；写 direction、level、source、current_question_id=新题 id、answered=0、asked_ids=新题 id、asked_count=1、right_count=0、round_start=base
  伪代码 返回 {"ok": 1} 加 取状态 learner=learner subject=subject_id 的字段

函数 Py判题 kind answer accepted_json
  返回 {correct}，1 或 0
  伪代码 accepted_json 解析成字符串列表；作答和每个可接受答案用同一种规整后比较，任一项相等 correct=1，否则 0
  伪代码 kind 为 term：规整 = 只去掉首尾 Unicode 空白（text 包 替换 {x} ^\s+|\s+$）；按 Unicode 原样比较、大小写敏感，不做括号、限定名、全半角或大小写归一；只有 accepted 显式列出时才接受 print() 或 str.split 这类写法
  伪代码 kind 为 output：规整 = 先把 CRLF 和单独的 CR 都换成 LF（替换 正则 \r\n? 为 \n），再逐行去掉行末的空格和制表符（正则 (?m)[\x20\t]+$ 替换为空；动词参数按空格切，正则里空格写 \x20），最后去掉末尾全部 LF（正则 \n+$ 替换为空）；不对全串 trim，行首空白、行内空白、大小写、引号原样比较；空作答规整后是空串，只有某个可接受答案规整后也是空串才算对
  伪代码 判题只在服务层做，客户端交上来的只有作答文字

函数 Py拼题卡 q asked_count lang
  返回 题卡对象 {code, head, stem, sub, hint, kind, answer_mode, input_hint, verdict, right, mine, note, answer, explain}；询问时 verdict、right、mine、note、answer、explain 都是空串（不把标准答案、可接受答案、解析发给还没作答的客户端）
  伪代码 code=「{q.id}-{asked_count}」（判完前后同一张卡 code 不变）；head=「{Py等级名(q.level, lang)}・{Py方向名(q.kind, lang)}」；stem=Py题面(q, lang)；sub、hint 空串；kind=q.kind
  伪代码 answer_mode：term 为 line，output 为 multiline；input_hint：term 中文「写出术语，Enter 交」ja「用語を入力（Enter で送信）」，output 中文「写出标准输出，可换行」ja「標準出力を入力（改行可）」

函数 Py成绩文本 s lang
  返回 这一轮成绩文本：s 是 取状态（Python 分支）的结果；没有进度为空串，否则 中文「这一轮 {right_count}/{已答数}」ja「このセット {right_count}/{已答数}」，已答数 = asked_count，当前题还没交（question_id 不为 0 且 answered 等于 0）时减 1

函数 Py表单回填 s
  返回 {py_kind, py_level, py_source}：没有进度为「术语默写」「全部」「随机」；有进度时 direction term 为「术语默写」output 为「代码输出」，level 空填「全部」否则原值，source 为 review 填「错题复习」其余「随机」

函数 Py空错题状态 learner direction level subject_id lang
  返回 {dphase, dempty, dcard, dstat, dmode}；dphase=empty，dmode=python，dcard、dstat 空串；dempty 中文「「{Py方向名}」（等级：{Py等级名}）的错题本是空的——没有答错过的题，或者都已经连续答对两次了。先随机练一轮吧。」，ja「「{Py方向名}」（レベル：{Py等级名}）の間違いノートは空です。間違えた問題がないか、すべて2回連続で正解しています。まずランダムに1セット練習しましょう。」
  伪代码 记下这次的选择：该 learner 在本科目的 dictation_question_progress 已有行时，current_question_id 为 0 才只更新 direction、level、source=review（其余不动），不为 0 时不改；没有行则插入（current_question_id=0、answered=1、asked_ids 空、asked_count=0、right_count=0、round_start=该 learner 本科目 dictation_question_attempt 的最大 id，没有为 0）

函数 Py开轮页面 learner direction level source subject_id lang
  返回 {dphase, dcard, dstat, dmode}；出得了题 dphase=ask，dcard 是新题卡，dstat 是 Py成绩文本，dmode=python；source 为 review 但错题本里没有可出的题时返回 Py空错题状态 的结果
  报错 400 没有可出的题
  伪代码 source 为 review 且 Py选题 learner=learner direction=direction level=level source=review asked_ids=空串 subject_id=subject_id 返回空：返回 Py空错题状态 learner=learner direction=direction level=level subject_id=subject_id lang=lang
  伪代码 调用 Py开新轮 得 s（报错原样向上抛）；Py取题 subject_id=subject_id question_id=s.question_id，card=Py拼题卡(q=题, s.asked_count, lang)；返回 {"dphase": "ask", "dcard": card, "dstat": Py成绩文本(s, lang), "dmode": "python"}

函数 Py算错题本 learner subject_id lang
  返回 列表 [{question_id, word_id, direction, kind, prompt, last_answer, last_at, last_wrong_id}]，按 last_wrong_id 从大到小；word_id 等于 question_id（给沿用 word_id 键的调用方）
  伪代码 一条查询在一遍扫描里做完（同 算错词本 的窗口函数写法）：dictation_question_attempt 中该 learner 且 subject_id=本科目 的行，按 (question_id, direction) 分组；每组 correct=0 的最大 id 为 last_wrong_id，没有答错的组跳过；该组 id 大于 last_wrong_id、correct=1 且 hinted=0 的行数不小于 2 则已出本，跳过
  伪代码 同一条查询里 join dictation_question（id=question_id 且 subject_id=本科目），题已被删或属于别的科目的组跳过；prompt 取 Py题面 口径（lang 为 ja 且 prompt_ja 非空取 prompt_ja，否则 prompt_zh），kind 取题的 kind；last_answer、last_at 取 last_wrong_id 那行的 answer、at
  伪代码 统计（统计错词本数、取默写概况的 wrong_book_count）和列表（取错词本）都用这一个函数，口径一致

## 接口
GET /dictation/state -> 取状态 角色 student
POST /dictation/state -> 默写页面 动作 dictation_state 模板 页面状态 表单=form 角色 student
POST /dictation/start -> 开始页面 动作 dictation_start 模板 页面状态 角色 student
POST /dictation/random -> 随机页面 动作 dictation_random 模板 页面状态 表单=form 角色 student
POST /dictation/wrong -> 练错词页面 动作 dictation_wrong 模板 页面状态 表单=form 角色 student
POST /dictation/load -> 载入页面 动作 dictation_load 模板 页面状态 表单=form 角色 student
POST /dictation/again -> 再来一轮页面 动作 dictation_again 模板 页面状态 角色 student
POST /dictation/next -> 下一个页面 动作 dictation_next 模板 页面状态 角色 student
POST /dictation/hint -> 提示页面 动作 dictation_hint 模板 页面状态 角色 student
POST /dictation/answer -> 判答案页面 动作 dictation_answer 模板 页面状态 角色 student
GET /dictation/round-wrong -> 列本轮错词 角色 student
GET /dictation/wrong-book -> 取错词本 角色 student
GET /dictation/wrong-book/count -> 统计错词本数 角色 student
GET /dictation/overview -> 取默写概况 角色 student

## 用例
用例 取状态_没有进度
  调用 取状态 learner=me
  得 has_progress=0

用例 取状态_有进度
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 取状态 learner=me
  得 has_progress=1 direction=zh2jp prompt=学校 answered=0 hinted=0 asked_count=1 right_count=0 finished=0

用例 开始_正常
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  调用 开始 learner=me direction=zh2jp level=N5
  得 ok=1 finished=0 prompt=[N5]学校 asked_count=1 right_count=0 answered=0 hinted=0
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me direction=zh2jp level=N5 asked_count=1 answered=0 round_start=0

用例 开始_方向不对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=bad
  报错 400
  库 dictation_progress 共 0 行

用例 开始_没有可出的词
  调用 开始 learner=me direction=zh2jp
  报错 400
  库 dictation_progress 共 0 行

用例 开始_按题源筛词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=zh2jp source=P9
  报错 400
  库 dictation_progress 共 0 行

用例 再来一轮_正常
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 交答案 learner=me answer=がっこう
  调用 再来一轮 learner=me
  得 ok=1 finished=0 asked_count=1 right_count=0 answered=0
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me round_start=1 asked_count=1 right_count=0
  库 dictation_attempt 共 1 行

用例 再来一轮_还没开始
  调用 再来一轮 learner=me
  报错 400

用例 下一个_正常
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 交答案 learner=me answer=x
  调用 下一个 learner=me
  得 ok=1 finished=0 asked_count=2 answered=0 hinted=0
  库 dictation_progress 含 learner=me asked_count=2 answered=0

用例 下一个_没词可出算本轮结束
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 交答案 learner=me answer=x
  调用 下一个 learner=me
  得 ok=1 finished=1 asked_count=1 right_count=0
  库 dictation_progress 含 learner=me current_word_id=0 answered=1

用例 下一个_没交答案
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 下一个 learner=me
  报错 400

用例 下一个_还没开始
  调用 下一个 learner=me
  报错 400

用例 提示_正常
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 提示 learner=me
  得 ok=1 hinted=1 first_kana=が length=4
  库 dictation_progress 含 learner=me hinted=1

用例 提示_已交答案
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 交答案 learner=me answer=がっこう
  调用 提示 learner=me
  报错 400

用例 提示_还没开始
  调用 提示 learner=me
  报错 400

用例 交答案_写假名答对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 交答案 learner=me answer=がっこう
  得 ok=1 correct=1 hinted=0 kana=がっこう kanji=学校 asked_count=1 right_count=1
  库 dictation_attempt 共 1 行
  库 dictation_attempt 含 learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0
  库 dictation_progress 含 learner=me answered=1 right_count=1

用例 交答案_看中文写日语写汉字也对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 交答案 learner=me answer=学校
  得 ok=1 correct=1 right_count=1

用例 交答案_答错
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 交答案 learner=me answer=がくこう
  得 ok=1 correct=0 right_count=0
  库 dictation_attempt 含 learner=me word_id=1 correct=0 hinted=0
  库 dictation_progress 含 learner=me answered=1 right_count=0

用例 交答案_看汉字写读音写汉字算错
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=kanji2kana
  调用 交答案 learner=me answer=学校
  得 correct=0
  库 dictation_attempt 含 learner=me direction=kanji2kana correct=0

用例 交答案_看汉字写读音答对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=kanji2kana
  调用 交答案 learner=me answer=がっこう
  得 correct=1 right_count=1
  库 dictation_attempt 含 learner=me direction=kanji2kana correct=1

用例 交答案_看过提示答对仍记对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 提示 learner=me
  调用 交答案 learner=me answer=がっこう
  得 correct=1 hinted=1 right_count=1
  库 dictation_attempt 含 learner=me word_id=1 correct=1 hinted=1

用例 交答案_同一个交两次只算一次
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 交答案 learner=me answer=がっこう
  调用 交答案 learner=me answer=がっこう
  报错 400
  库 dictation_attempt 共 1 行
  库 dictation_progress 含 learner=me right_count=1

用例 交答案_还没出词
  调用 交答案 learner=me answer=がっこう
  报错 400
  库 dictation_attempt 共 0 行

用例 交答案_答案为空白
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 交答案 learner=me answer=空
  报错 400
  库 dictation_attempt 共 0 行

用例 列本轮错词_有错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 交答案 learner=me answer=x
  调用 列本轮错词 learner=me
  得 learner=me total=1

用例 列本轮错词_新一轮清零
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 交答案 learner=me answer=x
  先 调用 再来一轮 learner=me
  调用 列本轮错词 learner=me
  得 learner=me total=0

用例 列本轮错词_没有进度
  调用 列本轮错词 learner=me
  得 learner=me total=0

用例 取错词本_最近一次答错在本里
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 取错词本 learner=me
  得 learner=me total=1

用例 取错词本_不看提示连续答对两次出本
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-01
  调用 取错词本 learner=me
  得 learner=me total=0

用例 取错词本_看提示答对不算连续
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=1 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=1 at=2026-01-01
  调用 取错词本 learner=me
  得 learner=me total=1

用例 取错词本_只答对一次还在本里
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-01
  调用 取错词本 learner=me
  得 learner=me total=1

用例 取错词本_方向各算各的
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=kanji2kana answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=kanji2kana answer=がっこう correct=1 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=kanji2kana answer=がっこう correct=1 hinted=0 at=2026-01-01
  调用 取错词本 learner=me
  得 learner=me total=1

用例 取错词本_词被删了跳过
  先 数据 dictation_attempt learner=me word_id=99 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 取错词本 learner=me
  得 learner=me total=0

用例 取错词本_没有作答
  调用 取错词本 learner=me
  得 learner=me total=0

用例 统计错词本数_有错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 统计错词本数 learner=me
  得 learner=me total=2

用例 统计错词本数_没有作答
  调用 统计错词本数 learner=me
  得 learner=me total=0

用例 取默写概况_有作答
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-01
  调用 取默写概况 learner=me
  得 learner=me total=3 right=2 accuracy=67 wrong_book_count=1 last_at=2026-01-01

用例 取默写概况_没有作答
  调用 取默写概况 learner=me
  得 learner=me total=0 right=0 accuracy=0 wrong_book_count=0

用例 交答案_同义词也算对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=校舎 kana=こうしゃ meaning=[N4]学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp level=N5
  调用 交答案 learner=me answer=こうしゃ
  得 ok=1 correct=1 right_count=1
  库 dictation_attempt 含 learner=me word_id=1 direction=zh2jp answer=こうしゃ correct=1

用例 交答案_片假名当平假名
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 交答案 learner=me answer=ガッコウ
  得 ok=1 correct=1

用例 交答案_另一个词不是同义词算错
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=[N4]老师 point_code=P1
  先 调用 开始 learner=me direction=zh2jp level=N5
  调用 交答案 learner=me answer=せんせい
  得 ok=1 correct=0 right_count=0

用例 开始_按等级筛词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=[N4]老师 point_code=P1
  调用 开始 learner=me direction=zh2jp level=N4
  得 ok=1 word_id=2
  库 dictation_progress 含 learner=me level=N4 current_word_id=2

用例 开始_错词复习只出错词本里的词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp source=review
  得 ok=1 word_id=1
  库 dictation_progress 含 learner=me source=review current_word_id=1

用例 开始_错词复习没有错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=zh2jp source=review
  报错 400
  库 dictation_progress 共 0 行

用例 开始_随机先出没练过的词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=2
  库 dictation_progress 含 learner=me current_word_id=2

用例 开始_练过的方向才算练过
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=kanji2kana answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=2

用例 开始_别人练过的不算
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=other word_id=1 direction=zh2jp answer=x correct=1 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=1

用例 开始_都练过了照样能出
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp
  得 ok=1 finished=0
  库 dictation_progress 含 learner=me asked_count=1

用例 再来一轮_先出没练过的词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=1 answered=1 hinted=0 asked_ids=1 asked_count=1 right_count=0 round_start=0
  调用 再来一轮 learner=me
  得 ok=1 word_id=2

用例 下一个_先出没练过的词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 vocab_word kanji=朝 kana=あさ meaning=早上 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=1 answered=1 hinted=0 asked_ids=1 asked_count=1 right_count=0 round_start=0
  调用 下一个 learner=me
  得 ok=1 word_id=3

用例 开始_错词复习不分练没练过
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp source=review
  得 ok=1 word_id=1

用例 开始_不出五十音
  先 数据 vocab_word kana=あ meaning=あ point_code=hiragana
  先 数据 vocab_word kana=ア meaning=ア point_code=katakana
  先 数据 vocab_word kana=きゃ meaning=きゃ point_code=youon
  先 数据 vocab_word kana=が meaning=が point_code=dakuon
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=5

用例 开始_只有五十音没有可出的词
  先 数据 vocab_word kana=あ meaning=あ point_code=hiragana
  调用 开始 learner=me direction=zh2jp
  报错 400
  库 dictation_progress 共 0 行

用例 开始_不出活用形和量词音变的说明
  先 数据 vocab_word kanji=食べる kana=たべる meaning=食べる的可能形 point_code=potential
  先 数据 vocab_word kanji=行く kana=いく meaning=行く的意志形 point_code=volitional
  先 数据 vocab_word kanji=書く kana=かく meaning=书写的命令形 point_code=imperative
  先 数据 vocab_word kanji=見る kana=みる meaning=见的使役形 point_code=causative
  先 数据 vocab_word kanji=飲む kana=のむ meaning=饮的使役被动形 point_code=causative-passive
  先 数据 vocab_word kanji=本 kana=ほん meaning=促音加ぽ point_code=counters-sound
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=7

用例 开始_不出意思是语法说明的词
  先 数据 vocab_word kanji=です kana=です meaning=[N5]です的礼貌形 point_code=P1
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=2

用例 开始_意思只剩等级前缀不出
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5] point_code=P1
  调用 开始 learner=me direction=zh2jp
  报错 400

用例 开始_错词复习也不出语法说明
  先 数据 vocab_word kanji=食べる kana=たべる meaning=食べる的可能形 point_code=potential
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp source=review
  报错 400
  库 dictation_progress 共 0 行

用例 开始_看汉字写读音也不出语法说明
  先 数据 vocab_word kanji=食べる kana=たべる meaning=食べる的可能形 point_code=potential
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=kanji2kana
  得 ok=1 word_id=2

用例 默写页面_没进度
  调用 默写页面 learner=me
  得 有返回

用例 默写页面_有进度
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=kanji2kana
  调用 默写页面 learner=me
  得 有返回

用例 开始页面_看中文写日语
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始页面 learner=me dict_direction=看中文写日语 dict_level=全部 dict_source=随机
  得 dphase=ask
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me direction=zh2jp asked_count=1 current_word_id=1

用例 开始页面_看汉字写读音
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始页面 learner=me dict_direction=看汉字写读音
  得 dphase=ask
  库 dictation_progress 含 learner=me direction=kanji2kana

用例 开始页面_等级筛选
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=[N4]老师 point_code=P1
  调用 开始页面 learner=me dict_direction=看中文写日语 dict_level=N4 dict_source=随机
  得 dphase=ask
  库 dictation_progress 含 learner=me level=N4 current_word_id=2

用例 开始页面_等级下没有词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始页面 learner=me dict_level=N1
  报错 400
  库 dictation_progress 共 0 行

用例 开始页面_方向不对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始页面 learner=me dict_direction=bad
  报错 400
  库 dictation_progress 共 0 行

用例 开始页面_题源不对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始页面 learner=me dict_source=bad
  报错 400

用例 开始页面_错词复习有词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始页面 learner=me dict_direction=看中文写日语 dict_level=全部 dict_source=错词复习
  得 dphase=ask
  库 dictation_progress 含 learner=me source=review current_word_id=1

用例 开始页面_错词复习没有错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始页面 learner=me dict_direction=看中文写日语 dict_source=错词复习
  得 dphase=empty
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me direction=zh2jp source=review current_word_id=0

用例 开始页面_错词复习方向各算各的
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=kanji2kana answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始页面 learner=me dict_direction=看中文写日语 dict_source=错词复习
  得 dphase=empty

用例 随机页面_正常
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始页面 learner=me dict_direction=看汉字写读音 dict_source=错词复习
  调用 随机页面 learner=me
  得 dphase=ask
  库 dictation_progress 含 learner=me direction=kanji2kana source=空 current_word_id=1

用例 练错词页面_有错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 练错词页面 learner=me
  得 dphase=ask
  库 dictation_progress 含 learner=me direction=zh2jp source=review current_word_id=1

用例 练错词页面_没有错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 练错词页面 learner=me
  得 dphase=empty

用例 载入页面_错词复习
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 载入页面 learner=me source=review direction=meaning
  得 dphase=ask
  库 dictation_progress 含 learner=me direction=zh2jp source=review current_word_id=1

用例 载入页面_读音方向
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 载入页面 learner=me source=random direction=reading level=全部
  得 dphase=ask
  库 dictation_progress 含 learner=me direction=kanji2kana source=空

用例 载入页面_什么都没带
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 载入页面 learner=me
  得 dphase=ask
  库 dictation_progress 含 learner=me direction=zh2jp

用例 判答案页面_答对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 判答案页面 learner=me dict_answer=がっこう
  得 dphase=done
  库 dictation_attempt 共 1 行
  库 dictation_attempt 含 learner=me word_id=1 correct=1 answer=がっこう
  库 dictation_progress 含 learner=me answered=1 right_count=1

用例 判答案页面_答错
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 判答案页面 learner=me dict_answer=がくこう
  得 dphase=done
  库 dictation_attempt 含 learner=me word_id=1 correct=0

用例 判答案页面_同义词也算对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=校舎 kana=こうしゃ meaning=[N4]学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp level=N5
  调用 判答案页面 learner=me dict_answer=校舎
  得 dphase=done
  库 dictation_attempt 含 learner=me word_id=1 answer=校舎 correct=1

用例 判答案页面_答案为空白
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  # 约定检查豁免 可选传空 dict_answer：答案为空（不传也是空串）一律报 400 答案不能为空，用例期望与不传一致
  调用 判答案页面 learner=me dict_answer=空
  报错 400
  库 dictation_attempt 共 0 行

用例 判答案页面_还没开始
  调用 判答案页面 learner=me dict_answer=がっこう
  报错 400

用例 提示页面_正常
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 提示页面 learner=me
  得 dphase=ask
  库 dictation_progress 含 learner=me hinted=1

用例 提示页面_还没开始
  调用 提示页面 learner=me
  报错 400

用例 下一个页面_出下一个词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 判答案页面 learner=me dict_answer=x
  调用 下一个页面 learner=me
  得 dphase=ask
  库 dictation_progress 含 learner=me asked_count=2 answered=0

用例 下一个页面_一轮做完
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 判答案页面 learner=me dict_answer=x
  调用 下一个页面 learner=me
  得 dphase=end
  库 dictation_progress 含 learner=me current_word_id=0 answered=1

用例 下一个页面_没交答案
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  调用 下一个页面 learner=me
  报错 400

用例 再来一轮页面_正常
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始 learner=me direction=zh2jp
  先 调用 判答案页面 learner=me dict_answer=がっこう
  调用 再来一轮页面 learner=me
  得 dphase=ask
  库 dictation_progress 含 learner=me asked_count=1 right_count=0 round_start=1

用例 再来一轮页面_错词复习没有错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 调用 开始页面 learner=me dict_direction=看中文写日语 dict_source=错词复习
  调用 再来一轮页面 learner=me
  得 dphase=empty

用例 再来一轮页面_还没开始
  调用 再来一轮页面 learner=me
  报错 400

用例 跨科目_开始只出本科目的词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  调用 开始 learner=me direction=zh2jp subject=2
  得 ok=1 word_id=2 prompt=数字
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me subject_id=2 current_word_id=2 asked_count=1

用例 跨科目_2号科目没词不能开始
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 开始 learner=me direction=zh2jp subject=2
  报错 400
  库 dictation_progress 共 0 行

用例 跨科目_不传科目是日语
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=1
  库 dictation_progress 含 learner=me subject_id=1 current_word_id=1

用例 跨科目_进度按科目分开
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp
  调用 取状态 learner=me subject=2
  得 has_progress=0

用例 跨科目_取状态看本科目的进度
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  调用 取状态 learner=me subject=2
  得 has_progress=1 word_id=2 prompt=数字

用例 跨科目_取状态当前词是别的科目的词当不存在
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=1 answered=0 hinted=0 asked_ids=1 asked_count=1 right_count=0 round_start=0
  调用 取状态 learner=me
  得 has_progress=1 finished=0 prompt=空

用例 跨科目_交答案作答落当前科目
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  调用 交答案 learner=me answer=かず subject=2
  得 ok=1 correct=1 right_count=1
  库 dictation_attempt 共 1 行
  库 dictation_attempt 含 learner=me word_id=1 correct=1 subject_id=2
  库 dictation_progress 含 learner=me answered=1 right_count=1 subject_id=2

用例 跨科目_交答案当前词是别的科目的词404
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=1 answered=0 hinted=0 asked_ids=1 asked_count=1 right_count=0 round_start=0
  调用 交答案 learner=me answer=かず
  报错 404
  库 dictation_attempt 共 0 行

用例 跨科目_提示当前词是别的科目的词404
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=1 answered=0 hinted=0 asked_ids=1 asked_count=1 right_count=0 round_start=0
  调用 提示 learner=me
  报错 404

用例 跨科目_再来一轮别的科目没有进度
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  调用 再来一轮 learner=me
  报错 400

用例 跨科目_下一个别的科目没有进度
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  调用 下一个 learner=me
  报错 400

用例 跨科目_列本轮错词只看本科目
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  先 调用 交答案 learner=me answer=x subject=2
  调用 列本轮错词 learner=me subject=2
  得 learner=me total=1

用例 跨科目_列本轮错词对1号科目不可见
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  先 调用 交答案 learner=me answer=x subject=2
  调用 列本轮错词 learner=me
  得 learner=me total=0

用例 跨科目_取错词本只看本科目
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 取错词本 learner=me subject=2
  得 learner=me total=1

用例 跨科目_取错词本不传科目是日语
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 取错词本 learner=me
  得 learner=me total=1

用例 跨科目_取错词本2号科目的错词对1号不可见
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 取错词本 learner=me
  得 learner=me total=0

用例 跨科目_取错词本作答属于本科目但词不是跳过
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 取错词本 learner=me subject=2
  得 learner=me total=0

用例 跨科目_统计错词本数只看本科目
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 统计错词本数 learner=me subject=2
  得 learner=me total=1

用例 跨科目_统计错词本数2号科目对1号不可见
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 统计错词本数 learner=me
  得 learner=me total=0

用例 跨科目_取默写概况只按本科目统计
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-03
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=かず correct=1 hinted=0 at=2026-01-01 subject_id=2
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-02 subject_id=2
  调用 取默写概况 learner=me subject=2
  得 learner=me total=2 right=1 accuracy=50 wrong_book_count=1 last_at=2026-01-02

用例 跨科目_取默写概况不传科目是日语
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=がっこう correct=1 hinted=0 at=2026-01-03
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-02 subject_id=2
  调用 取默写概况 learner=me
  得 learner=me total=1 right=1 accuracy=100 wrong_book_count=0 last_at=2026-01-03

用例 跨科目_取默写概况2号科目对1号不可见
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 取默写概况 learner=me
  得 learner=me total=0 right=0 accuracy=0 wrong_book_count=0

用例 跨科目_错词复习只出本科目的错词
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 开始 learner=me direction=zh2jp source=review subject=2
  得 ok=1 word_id=2
  库 dictation_progress 含 learner=me subject_id=2 source=review current_word_id=2

用例 跨科目_错词复习2号科目的错词对1号不可见
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  调用 开始 learner=me direction=zh2jp source=review
  报错 400
  库 dictation_progress 共 0 行

用例 跨科目_随机练没练过只看本科目
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 vocab_word kanji=円 kana=えん meaning=圆 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01 subject_id=2
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp subject=2
  得 ok=1 word_id=2

用例 跨科目_开始页面落当前科目
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  调用 开始页面 learner=me dict_direction=看中文写日语 dict_level=全部 dict_source=随机 subject=2
  得 dphase=ask
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me subject_id=2 current_word_id=1

用例 跨科目_开始页面错词复习没有错词空状态落当前科目
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始页面 learner=me dict_source=错词复习 subject=2
  得 dphase=empty
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me subject_id=2 source=review current_word_id=0

用例 跨科目_默写页面别的科目没有进度
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp
  调用 默写页面 learner=me subject=2
  得 dstat=空
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me subject_id=1 current_word_id=1
  库 dictation_progress 无 learner=me subject_id=2

用例 跨科目_判答案页面作答落当前科目
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  调用 判答案页面 learner=me dict_answer=かず subject=2
  得 dphase=done
  库 dictation_attempt 含 learner=me word_id=1 correct=1 subject_id=2

用例 跨科目_再来一轮页面别的科目没有进度
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp subject=2
  调用 再来一轮页面 learner=me
  报错 400

用例 跨科目_登录模式学生未分配该科目403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  调用 开始 learner=s1 direction=zh2jp current_role=student auth_mode=on subject=2
  报错 403
  库 dictation_progress 共 0 行

用例 跨科目_登录模式学生已分配可开始
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_student subject_id=2 learner=s1 assigned_by=t1 status=active created_at=2026-01-01
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  调用 开始 learner=s1 direction=zh2jp current_role=student auth_mode=on subject=2
  得 ok=1 word_id=1
  库 dictation_progress 含 learner=s1 subject_id=2 current_word_id=1

用例 跨科目_登录模式科目不存在404
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 取默写概况 learner=s1 current_role=student auth_mode=on subject=9
  报错 404

用例 跨科目_科目不是数字400
  调用 取错词本 learner=me subject=abc
  报错 400

用例 进度每人每科目一行_对2号科目的操作不动1号行
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 vocab_word kanji=円 kana=えん meaning=圆 point_code=P2 subject_id=2
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=1 answered=0 hinted=0 asked_ids=1 asked_count=1 right_count=0 round_start=0
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=2 answered=1 hinted=0 asked_ids=2 asked_count=1 right_count=1 round_start=0 subject_id=2
  调用 下一个 learner=me subject=2
  得 ok=1 word_id=3 asked_count=2 right_count=1
  库 dictation_progress 共 2 行
  库 dictation_progress 含 learner=me subject_id=2 current_word_id=3 asked_count=2 answered=0
  库 dictation_progress 含 learner=me subject_id=1 current_word_id=1 asked_count=1 answered=0 asked_ids=1

用例 进度每人每科目一行_同一学生两科目各开一轮不互相覆盖
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=zh2jp
  先 调用 开始 learner=me direction=kanji2kana subject=2
  调用 开始 learner=me direction=zh2jp subject=2
  得 ok=1 word_id=2 asked_count=1
  库 dictation_progress 共 2 行
  库 dictation_progress 含 learner=me subject_id=1 direction=zh2jp current_word_id=1
  库 dictation_progress 含 learner=me subject_id=2 direction=zh2jp current_word_id=2

用例 开新轮_round_start按本科目最大id不取全局
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-02 subject_id=2
  先 数据 dictation_attempt learner=me word_id=2 direction=zh2jp answer=y correct=0 hinted=0 at=2026-01-03 subject_id=2
  调用 开始 learner=me direction=zh2jp
  得 ok=1 word_id=1
  库 dictation_progress 含 learner=me subject_id=1 round_start=1
  库 dictation_progress 无 learner=me round_start=3

用例 开新轮_2号科目没有作答时round_start为0不取别科目的id
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=zh2jp subject=2
  得 ok=1 word_id=1
  库 dictation_progress 含 learner=me subject_id=2 round_start=0

用例 判词_同义词不跨科目
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=校舎 kana=こうしゃ meaning=[N4]学校 point_code=P1 subject_id=2
  先 调用 开始 learner=me direction=zh2jp level=N5
  调用 交答案 learner=me answer=こうしゃ
  得 ok=1 correct=0 right_count=0
  库 dictation_attempt 含 learner=me word_id=1 answer=こうしゃ correct=0 subject_id=1

用例 判词_别科目的同词不判对
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 调用 开始 learner=me direction=kanji2kana subject=2
  调用 交答案 learner=me answer=がっこう subject=2
  得 ok=1 correct=0 right_count=0
  库 dictation_attempt 含 learner=me word_id=2 correct=0 subject_id=2

用例 空错词状态_有进行中的题不改方向等级题源
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=1 answered=0 hinted=0 asked_ids=1 asked_count=1 right_count=0 round_start=0
  调用 开始页面 learner=me dict_direction=看汉字写读音 dict_level=N5 dict_source=错词复习
  得 dphase=empty
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me direction=zh2jp current_word_id=1 answered=0 asked_count=1
  库 dictation_progress 无 learner=me direction=kanji2kana
  库 dictation_progress 无 learner=me source=review

用例 空错词状态_没有进行中的题才写方向等级题源
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_progress learner=me direction=zh2jp current_word_id=0 answered=1 hinted=0 asked_ids=1 asked_count=1 right_count=1 round_start=0
  调用 开始页面 learner=me dict_direction=看汉字写读音 dict_level=N5 dict_source=错词复习
  得 dphase=empty
  库 dictation_progress 共 1 行
  库 dictation_progress 含 learner=me direction=kanji2kana level=N5 source=review current_word_id=0 asked_count=1 right_count=1

用例 Py_开始_出术语题且不碰日语表
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print","print()"] explain_zh=用print explain_ja=printを使う enabled=1
  调用 开始 learner=me direction=term subject=2
  得 ok=1 finished=0 question_id=1 kind=term prompt=打印函数？ asked_count=1 right_count=0 answered=0
  库 dictation_question_progress 共 1 行
  库 dictation_question_progress 含 learner=me subject_id=2 direction=term current_question_id=1 asked_count=1 answered=0 round_start=0
  库 dictation_progress 共 0 行

用例 Py_没开默写能力拒绝开始
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"kg":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  调用 开始 learner=me direction=zh2jp subject=2
  报错 400
  库 dictation_progress 共 0 行
  库 dictation_question_progress 共 0 行

用例 Py_方向不对
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  调用 开始 learner=me direction=zh2jp subject=2
  报错 400
  库 dictation_question_progress 共 0 行

用例 Py_等级不对
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  调用 开始 learner=me direction=term level=N5 subject=2
  报错 400
  库 dictation_question_progress 共 0 行

用例 Py_题源不是本科目知识点
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  调用 开始 learner=me direction=term source=python.nope subject=2
  报错 400
  库 dictation_question_progress 共 0 行

用例 Py_按等级和题型筛题
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=进阶 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split"] explain_zh=用split explain_ja=splitを使う enabled=1
  先 数据 dictation_question subject_id=2 code=q3 point_code=python.str kind=output level=进阶 prompt_zh=输出？ prompt_ja=出力？ answer=5 accepted_json=["5\n"] explain_zh=加法 explain_ja=加算 enabled=1
  调用 开始 learner=me direction=term level=进阶 subject=2
  得 ok=1 question_id=2 kind=term prompt=拆分方法？

用例 Py_按知识点出题
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=入门 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split"] explain_zh=用split explain_ja=splitを使う enabled=1
  调用 开始 learner=me direction=term source=python.str subject=2
  得 ok=1 question_id=2
  库 dictation_question_progress 含 learner=me subject_id=2 source=python.str

用例 Py_停用的题不出
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=0
  调用 开始 learner=me direction=term subject=2
  报错 400
  库 dictation_question_progress 共 0 行

用例 Py_术语等价写法判对
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print","print()"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  调用 交答案 learner=me answer=print() subject=2
  得 ok=1 correct=1 hinted=0 answer=print explain=用print right_count=1 asked_count=1
  库 dictation_question_attempt 共 1 行
  库 dictation_question_attempt 含 learner=me subject_id=2 question_id=1 direction=term answer=print() correct=1 hinted=0
  库 dictation_question_progress 含 learner=me subject_id=2 answered=1 right_count=1
  库 dictation_attempt 共 0 行

用例 Py_术语大小写不同判错
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print","print()"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  调用 交答案 learner=me answer=Print subject=2
  得 ok=1 correct=0 right_count=0
  库 dictation_question_attempt 含 learner=me question_id=1 answer=Print correct=0

用例 Py_术语没列出的写法判错
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=入门 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split","split()","str.split","str.split()"] explain_zh=用split explain_ja=splitを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  调用 交答案 learner=me answer=SPLIT subject=2
  得 ok=1 correct=0

用例 Py_术语限定名列出了就判对
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=入门 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split","split()","str.split","str.split()"] explain_zh=用split explain_ja=splitを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  调用 交答案 learner=me answer=str.split() subject=2
  得 ok=1 correct=1

用例 Py_代码输出末尾换行可省
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q3 point_code=python.str kind=output level=入门 prompt_zh=输出？ prompt_ja=出力？ answer=5 accepted_json=["5\n"] explain_zh=加法 explain_ja=加算 enabled=1
  先 调用 开始 learner=me direction=output subject=2
  调用 交答案 learner=me answer=5 subject=2
  得 ok=1 correct=1 kind=output right_count=1

用例 Py_代码输出行内差异判错
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q3 point_code=python.str kind=output level=入门 prompt_zh=输出？ prompt_ja=出力？ answer=A-B! accepted_json=["A-B!"] explain_zh=分隔 explain_ja=区切り enabled=1
  先 调用 开始 learner=me direction=output subject=2
  调用 交答案 learner=me answer=a-b! subject=2
  得 ok=1 correct=0

用例 Py_代码输出空作答可以交
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q3 point_code=python.str kind=output level=入门 prompt_zh=输出？ prompt_ja=出力？ answer=5 accepted_json=["5\n"] explain_zh=加法 explain_ja=加算 enabled=1
  先 调用 开始 learner=me direction=output subject=2
  调用 交答案 learner=me answer=空 subject=2
  得 ok=1 correct=0
  库 dictation_question_attempt 共 1 行

用例 Py_术语空作答不能交
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  调用 交答案 learner=me answer=空 subject=2
  报错 400
  库 dictation_question_attempt 共 0 行

用例 Py_重复提交400
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  先 调用 交答案 learner=me answer=print subject=2
  调用 交答案 learner=me answer=print subject=2
  报错 400
  库 dictation_question_attempt 共 1 行

用例 Py_提示被拒不改进度
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  调用 提示 learner=me subject=2
  报错 400
  库 dictation_question_progress 含 learner=me subject_id=2 answered=0 current_question_id=1

用例 Py_下一个一轮不重复
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  先 调用 交答案 learner=me answer=print subject=2
  调用 下一个 learner=me subject=2
  得 ok=1 finished=1 asked_count=1 right_count=1
  库 dictation_question_progress 含 learner=me subject_id=2 current_question_id=0 answered=1

用例 Py_下一个没交答案400
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=入门 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split"] explain_zh=用split explain_ja=splitを使う enabled=1
  先 调用 开始 learner=me direction=term subject=2
  调用 下一个 learner=me subject=2
  报错 400

用例 Py_随机先出没练过的题
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=入门 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split"] explain_zh=用split explain_ja=splitを使う enabled=1
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=print correct=1 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=term subject=2
  得 ok=1 question_id=2

用例 Py_错题复习只出错题本里的题
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=入门 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split"] explain_zh=用split explain_ja=splitを使う enabled=1
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=2 direction=term answer=x correct=0 hinted=0 at=2026-01-01
  调用 开始 learner=me direction=term source=review subject=2
  得 ok=1 question_id=2
  库 dictation_question_progress 含 learner=me subject_id=2 source=review current_question_id=2

用例 Py_错题复习没有错题是空状态
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  调用 开始页面 learner=me py_kind=术语默写 py_level=全部 py_source=错题复习 subject=2
  得 dphase=empty dmode=python
  库 dictation_question_progress 含 learner=me subject_id=2 source=review current_question_id=0

用例 Py_错题本两次无提示答对出本
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question subject_id=2 code=q2 point_code=python.str kind=term level=入门 prompt_zh=拆分方法？ prompt_ja=分割メソッド？ answer=split accepted_json=["split"] explain_zh=用split explain_ja=splitを使う enabled=1
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=print correct=1 hinted=0 at=2026-01-02
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=print correct=1 hinted=0 at=2026-01-03
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=2 direction=term answer=y correct=0 hinted=0 at=2026-01-04
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=2 direction=term answer=split correct=1 hinted=0 at=2026-01-05
  调用 取错词本 learner=me subject=2
  得 learner=me total=1

用例 Py_统计错题本数
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=x correct=0 hinted=0 at=2026-01-01
  调用 统计错词本数 learner=me subject=2
  得 learner=me total=1

用例 Py_默写概况按新作答表
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 vocab_word kanji=数 kana=かず meaning=数字 point_code=P2 subject_id=2
  先 数据 dictation_attempt learner=me word_id=1 direction=zh2jp answer=かず correct=1 hinted=0 at=2026-01-09 subject_id=2
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=x correct=0 hinted=0 at=2026-01-01
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=print correct=1 hinted=0 at=2026-01-02
  调用 取默写概况 learner=me subject=2
  得 learner=me total=2 right=1 accuracy=50 wrong_book_count=1 last_at=2026-01-02

用例 Py_默写页面回dmode和Python下拉
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 默写页面 learner=me subject=2
  得 dmode=python dstat=空

用例 Py_日语科目默写页面dmode是jp
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 默写页面 learner=me
  得 dmode=jp dstat=空

用例 Py_开始页面出代码题
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q3 point_code=python.str kind=output level=基础 prompt_zh=输出？ prompt_ja=出力？ answer=5 accepted_json=["5\n"] explain_zh=加法 explain_ja=加算 enabled=1
  调用 开始页面 learner=me py_kind=代码输出 py_level=基础 py_source=随机 subject=2
  得 dphase=ask dmode=python
  库 dictation_question_progress 含 learner=me subject_id=2 direction=output level=基础 current_question_id=1

用例 Py_判答案页面用代码框作答
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q3 point_code=python.str kind=output level=基础 prompt_zh=输出？ prompt_ja=出力？ answer=5 accepted_json=["5\n"] explain_zh=加法 explain_ja=加算 enabled=1
  先 调用 开始页面 learner=me py_kind=代码输出 subject=2
  调用 判答案页面 learner=me py_term=x py_output=5 subject=2
  得 dphase=done dmode=python
  库 dictation_question_attempt 含 learner=me question_id=1 answer=5 correct=1

用例 Py_提示页面被拒
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始页面 learner=me py_kind=术语默写 subject=2
  调用 提示页面 learner=me subject=2
  报错 400

用例 Py_别的科目的题不可见
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=3 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  调用 开始 learner=me direction=term subject=2
  报错 400
  库 dictation_question_progress 共 0 行

用例 Py_日语科目不受影响
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 调用 开始 learner=me direction=zh2jp subject=1
  调用 交答案 learner=me answer=がっこう subject=1
  得 ok=1 correct=1 kanji=学校 kana=がっこう
  库 dictation_attempt 含 learner=me word_id=1 correct=1 subject_id=1
  库 dictation_question_attempt 共 0 行
  库 dictation_question_progress 共 0 行

用例 Py_默写概况回mode
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 取默写概况 learner=me subject=2
  得 learner=me total=0 mode=python

用例 Py_日语默写概况mode是jp
  调用 取默写概况 learner=me
  得 learner=me total=0 mode=jp

用例 Py_取错词本按传入语言给题面
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=python name=Python kind=general caps={"dictation":1} levels=入门,基础,进阶 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 dictation_question subject_id=2 code=q1 point_code=python.env kind=term level=入门 prompt_zh=打印函数？ prompt_ja=表示関数？ answer=print accepted_json=["print"] explain_zh=用print explain_ja=printを使う enabled=1
  先 数据 dictation_question_attempt learner=me subject_id=2 question_id=1 direction=term answer=x correct=0 hinted=0 at=2026-01-01
  调用 取错词本 learner=me lang=ja subject=2
  得 learner=me total=1
