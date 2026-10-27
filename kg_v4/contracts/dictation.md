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
  learner 文本 学习者，每人一行
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

## 页面字段
页面 dictation_view 默写页面
  dict_direction 枚举 看中文写日语,看汉字写读音 方向
  dict_level 枚举 全部,N5,N4,N3,N2,N1 等级
  dict_source 枚举 随机,错词复习 题源
  dict_answer 文本 写出来的答案

## 函数
公开 函数 取状态 learner current_role?
  返回 没有进度时 {has_progress: 0}；有进度时 {has_progress: 1, direction, level, source, word_id, prompt, answered, hinted, asked_count, right_count, finished}。prompt 是题面（zh2jp 为中文意思，kanji2kana 为汉字），不含答案；word_id 为 0 时 finished=1 且 prompt 为空串
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 按 learner 和当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）查 dictation_progress 一行，查不到返回 {"has_progress": 0}
  伪代码 current_word_id 为 0：prompt 为空串，word_id=0，finished=1
  伪代码 current_word_id 不为 0：调用 vocab.取单词 word_id=current_word_id，取不到则 prompt 为空串；取到则 prompt = 题面(direction, 该词)；finished=0
  伪代码 返回 {"has_progress": 1, "direction": direction, "level": level, "source": source, "word_id": current_word_id, "prompt": prompt, "answered": answered, "hinted": hinted, "asked_count": asked_count, "right_count": right_count, "finished": finished}

公开 函数 开始 learner direction level? source? current_role?
  返回 {ok} 加上 取状态 的全部字段（新一轮的第一个词）
  报错 400 方向不对
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 开新轮 learner=learner direction=direction level=level source=source
  伪代码 返回开新轮的结果

公开 函数 再来一轮 learner current_role?
  返回 同「开始」
  报错 400 还没有开始
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 按 learner 和当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 用该行已存的 direction、level、source 调用 开新轮
  伪代码 返回开新轮的结果

公开 函数 下一个 learner current_role?
  返回 {ok} 加上 取状态 的全部字段；这一轮结束时 finished=1
  报错 400 还没有开始
  报错 400 当前词还没交答案
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 按 learner 和当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 current_word_id 不为 0 且 answered 等于 0，报错 400 当前词还没交答案
  伪代码 选词 用库里记的 direction、level、source 和 asked_ids（learner 传本人）。current_word_id 为 0，或 asked_count 不小于 10，或 选词 返回空（没有可出的词）：在库里把 current_word_id 置 0、answered 置 1，返回 {"ok": 1} 加 取状态 的字段（finished=1）
  伪代码 否则在一个事务里更新 dictation_progress：current_word_id=新词 id，answered=0，hinted=0，asked_ids 末尾追加新词 id，asked_count 加 1
  伪代码 返回 {"ok": 1} 加 取状态 的字段

公开 函数 提示 learner current_role?
  返回 {ok, hinted, first_kana, length}，first_kana 是当前词假名的第一个字，length 是假名字数
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 按 learner 和当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 current_word_id 为 0，报错 400 当前没有词；answered 等于 1，报错 400 当前词已经交过答案
  伪代码 调用 vocab.取单词 word_id=current_word_id，取不到报错 404 当前词已不存在
  伪代码 把 dictation_progress（该 learner 在当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）下那行）的 hinted 置 1
  伪代码 返回 {"ok": 1, "hinted": 1, "first_kana": 假名第一个字, "length": 假名字数}

公开 函数 交答案 learner answer current_role?
  返回 {ok, correct, hinted, note, kanji, kana, meaning, asked_count, right_count}，correct 为 1/0，note 是给人看的一句补充（同义词也算对、写成了同读音的另一个词、这是另一个读法……，没有为空串），kanji、kana、meaning 是标准答案所在单词
  报错 400 答案不能为空
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 answer 去掉首尾空白后为空，报错 400 答案不能为空
  伪代码 按 learner 和当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）查 dictation_progress，查不到报错 400 还没有开始
  伪代码 判的永远是库里记的 current_word_id，不信前端传的；current_word_id 为 0 报错 400 当前没有词
  伪代码 answered 等于 1，报错 400 当前词已经交过答案（同一个词交两次只算一次，不写库）
  伪代码 调用 vocab.取单词 word_id=current_word_id，取不到报错 404 当前词已不存在
  伪代码 判对错：调用 判词 direction=direction word=该词 answer=answer，得 correct、note（direction 为 zh2jp 时写汉字或假名都算对，意思完全一样的同义词也算对；kanji2kana 时写假名才算对；比较前先归一：全角半角统一、去空白和句号逗号、片假名当平假名）
  伪代码 在一个事务里：往 dictation_attempt 插入一行 (learner, word_id=current_word_id, direction, answer, correct, hinted=progress.hinted, at=当前时间)；更新 dictation_progress：answered=1，答对时 right_count 加 1
  伪代码 默写不写做题的作答、掌握、得分表，不影响知识点分数
  伪代码 返回 {"ok": 1, "correct": correct, "hinted": progress.hinted, "note": note, "kanji": 汉字, "kana": 假名, "meaning": 意思, "asked_count": asked_count, "right_count": 更新后的 right_count}

公开 函数 列本轮错词 learner current_role?
  返回 {learner, total, words}，words 是 [{word_id, direction, kanji, kana, meaning, answer}]，按作答 id 升序；没有进度时 total 为 0、words 为空
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 按 learner 和当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）查 dictation_progress，查不到返回 {"learner": learner, "total": 0, "words": []}
  伪代码 查 dictation_attempt 中 learner 相等、id 大于 round_start、correct 等于 0 的行，按 id 升序
  伪代码 对每行调用 vocab.取单词 word_id=该行 word_id，取不到的行跳过；其余拼出 {word_id, direction, kanji, kana, meaning, answer}
  伪代码 返回 {"learner": learner, "total": 行数, "words": 列表}

公开 函数 取错词本 learner
  返回 {learner, total, words}，words 是 [{word_id, direction, kanji, kana, meaning, last_answer, last_at}]，按最近一次答错的作答 id 从大到小；last_answer 和 last_at 是最近一次答错时写的内容和时间
  伪代码 调用 算错词本 learner=learner 得到列表
  伪代码 返回 {"learner": learner, "total": 列表长度, "words": 列表}

公开 函数 统计错词本数 learner
  返回 {learner, total}，total 是错词本条数（某词某方向算一条）
  伪代码 调用 算错词本 learner=learner 得到列表
  伪代码 返回 {"learner": learner, "total": 列表长度}

公开 函数 取默写概况 learner
  返回 {learner, total, right, accuracy, wrong_book_count, last_at}，total 是默写作答总数，right 是答对数，accuracy 是正确率百分比（right*100/total 四舍五入取整，total 为 0 时 0），last_at 是最近一次作答时间（没有作答为空串）
  伪代码 统计 dictation_attempt 中 learner 相等的行数 total 和 correct 等于 1 的行数 right
  伪代码 last_at 取这些行中 id 最大的那行的 at，没有则空串
  伪代码 调用 算错词本 learner=learner，wrong_book_count 取列表长度
  伪代码 返回 {"learner": learner, "total": total, "right": right, "accuracy": accuracy, "wrong_book_count": wrong_book_count, "last_at": last_at}

公开 函数 默写页面 learner current_role?
  返回 {dstat, form}；默写页「进入时」的整页状态（进页面不推词卡、不动 dphase）：dstat 是这一轮成绩文本，没练过为空串；form 是顶栏三个下拉的回填 {dict_direction, dict_level, dict_source}，取库里上次选的，没选过填「看中文写日语」「全部」「随机」
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 取状态 learner=learner，得 s
  伪代码 返回 {"dstat": 成绩文本(s), "form": 表单回填(s)}

公开 函数 开始页面 learner dict_direction? dict_level? dict_source? current_role?
  返回 默写页「开始」的整页状态，同 开轮页面：出得了词为 {dphase, dcard, dstat}，dphase=ask；错词复习但错词本里没有可出的词为 {dphase, dempty, dcard, dstat}，dphase=empty（不报错）
  报错 400 方向不对
  报错 400 题源不对
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 dict_direction 为空取「看中文写日语」、dict_level 为空取「全部」、dict_source 为空取「随机」（页面下拉的默认）
  伪代码 值域转换：调用 方向代号 得 direction；dict_level 为「全部」时 level 取空串，否则原值；dict_source 为「随机」时 source 取空串，「错词复习」取 review，其余报错 400 题源不对
  伪代码 返回 开轮页面 learner=learner direction=direction level=level source=source 的结果

公开 函数 随机页面 learner current_role?
  返回 默写页「随机练一轮」（错词本空时卡上的按钮）的整页状态：{dphase, dcard, dstat, form}，形状同 开轮页面；form 回填 {dict_direction, dict_level, dict_source}，题源回填「随机」
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 取状态 learner=learner，得 s；方向、等级照库里记的（没记过取 zh2jp、不限等级），题源随机（source 取空串）
  伪代码 调用 开轮页面 得 r，r 加上 form：方向转中文、等级空填「全部」、dict_source=「随机」

公开 函数 练错词页面 learner current_role?
  返回 默写页「练错词」（一轮结束时的按钮）的整页状态，形状同 随机页面；题源 review，form 的 dict_source 回填「错词复习」；错词本里没有可出的词时 dphase=empty
  报错 400 方向不对
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 取状态 learner=learner，得 s；方向、等级照库里记的（没记过取 zh2jp、不限等级），题源 review
  伪代码 调用 开轮页面 得 r，r 加上 form：方向转中文、等级空填「全部」、dict_source=「错词复习」

公开 函数 载入页面 learner source? direction? level? current_role?
  返回 默写页「载入」的整页状态（地址 #默写?source=review 进来，还可带 direction=reading|meaning、level=N4；前端把地址参数并进提交调用）：形状同 随机页面，form 回填本次所选
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 取状态 learner=learner，得 s；方向默认取库里的（没记过取 zh2jp），direction 参数 reading 换成 kanji2kana、meaning 换成 zh2jp，其他值不理；等级 level 参数不为空取参数（「全部」当空串）否则取库里的；题源默认取库里的（review 保持，其余空串），source 参数 review 换成 review、random 换成空串，其他值不理
  伪代码 调用 开轮页面 得 r，r 加上 form：方向转中文、等级空填「全部」、题源 review 回填「错词复习」否则「随机」

公开 函数 判答案页面 learner dict_answer? current_role?
  返回 默写页「交」的整页状态：{dphase, dcard, dstat}；dphase=done；dcard 是判完的词卡 {code, head, stem, sub, hint, verdict, right, mine, note}，code 与交之前同一张（前端不翻页），hint 看过提示才有，verdict 是「○对了」/「○对了（看了提示，不算进错词本的「连续答对」）」/「✗不对」，right 是「正确：汉字【读音】意思」（没汉字或汉字等于假名时是「读音 意思」，意思去掉开头的等级），mine 是「你写的：答案」，note 是 判词 的补充句
  报错 400 答案不能为空
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 取状态 learner=learner，得 s（要交之前的 word_id、direction、asked_count）；调用 交答案 learner=learner answer=dict_answer，得 r（报错原样向上抛）
  伪代码 word 取 {id: s.word_id, kanji: r.kanji, kana: r.kana, meaning: r.meaning}；调用 拼词卡 direction=s.direction word=word asked_count=r.asked_count hinted=r.hinted，得 card，再填 verdict、right、mine、note
  伪代码 返回 {"dphase": "done", "dcard": card, "dstat": 「这一轮 {r.right_count}/{r.asked_count}」}

公开 函数 提示页面 learner current_role?
  返回 默写页「提示」的整页状态：{dphase, dcard, dstat}；dphase=ask；dcard 是带提示的词卡（hint 为「提示：第一个假名是「x」，读音一共 n 个字」，verdict、right、mine、note 空串）
  报错 400 还没有开始
  报错 400 当前没有词
  报错 400 当前词已经交过答案
  报错 404 当前词已不存在
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 提示 learner=learner（报错原样向上抛）；调用 取状态 learner=learner，得 s；调用 vocab.取单词 word_id=s.word_id
  伪代码 调用 拼词卡 direction=s.direction word=该词 asked_count=s.asked_count hinted=1，得 card；返回 {"dphase": "ask", "dcard": card, "dstat": 成绩文本(s)}

公开 函数 下一个页面 learner current_role?
  返回 默写页「下一个」的整页状态：出下一个词为 {dphase, dcard, dstat}，dphase=ask；这一轮结束为 {dphase, dround, dstat, round_wrong}，dphase=end，dround 是 {text}，round_wrong 是这一轮错的词 [{label, mine}]
  报错 400 还没有开始
  报错 400 当前词还没交答案
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 下一个 learner=learner，得 s（报错原样向上抛）
  伪代码 s.finished 等于 0：调用 vocab.取单词 word_id=s.word_id，拼词卡 hinted=0，返回 {dphase: ask, dcard, dstat: 成绩文本(s)}
  伪代码 s.finished 等于 1：dphase=end；dround.text 在 right_count 等于 asked_count 时为「这一轮做完了：{asked_count} 个全对。」否则「这一轮做完了：答对 {right_count} 个，共 {asked_count} 个。」；round_wrong 调用 列本轮错词 learner=learner，逐项转 {label: 「汉字【读音】意思」（没汉字或汉字等于假名时「读音 意思」，意思去掉开头的等级）, mine: answer}

公开 函数 再来一轮页面 learner current_role?
  返回 默写页「再来一轮」的整页状态，形状同 开轮页面（新一轮第一个词 dphase=ask；题源是错词复习但错词本里没有可出的词 dphase=empty）
  报错 400 还没有开始
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 调用 取状态 learner=learner，得 s；has_progress 等于 0 报错 400 还没有开始
  伪代码 s.source 等于 review 且 调用 候选词 learner=learner direction=s.direction level=s.level source=review asked_ids=空串 得到空列表：返回 空错词状态 learner=learner direction=s.direction level=s.level
  伪代码 否则调用 再来一轮 learner=learner（报错原样向上抛）得 s2；调用 vocab.取单词 word_id=s2.word_id，拼词卡 hinted=0；返回 {dphase: ask, dcard, dstat: 成绩文本(s2)}

函数 题面 direction word
  返回 题面文字
  伪代码 direction 为 zh2jp 返回 word.meaning；否则返回 word.kanji

函数 选词 learner direction level source asked_ids
  返回 一个单词对象 {id, kanji, kana, meaning, point_code}；没有可出的词返回空
  伪代码 筛选和挑选全部下推到 vocab.挑默写词（SQL 里做），这里不对词表逐词循环；取不到词返回空。口径与原来一字不差：没练过优先、都练过了才从全部里挑、错词复习不分练没练过
  伪代码 seed = 当前时间戳（时间戳对候选数取余挑第几个，口径同原来）
  伪代码 source 等于 review：取错词本编号串 only_ids（同 候选词 的第一步，没有则返回空），调用 vocab.挑默写词 direction=direction level=level only_ids=only_ids skip_ids=asked_ids seed=seed，total 为 0 返回空，否则返回它的 word（按错词本顺序的第 (seed 对 total 取余) 个，口径同原来；不调用 候选词，也不在 DSL 里遍历取第几个）
  伪代码 source 不等于 review（随机，或按知识点编号）：practiced = 该 learner 在该 direction 上有过作答的单词编号（dictation_attempt 里 learner 相等、direction 相等的 word_id 去重，用一条查询在库里拼成逗号隔开的一个字符串，不看对错、不看有没有提示；别的方向、别的 learner 的不算）；先调用 vocab.挑默写词 direction=direction level=level point_code=source skip_ids=asked_ids 加 practiced（两个逗号串合并，空的不拼，不能出现开头、结尾或连续的逗号；asked_ids 为 0 当空）seed=seed，total 大于 0 就取它的 word（没练过的）；total 为 0 再调用 vocab.挑默写词 direction=direction level=level point_code=source skip_ids=asked_ids seed=seed（全练过了从全部候选里取），仍为 0 返回空
  伪代码 一轮里的词只出一次的约束靠 asked_ids 进 skip_ids 实现（asked_ids 逗号隔开，可空）

函数 候选词 learner direction level source asked_ids
  返回 可出的单词列表 [{id, kanji, kana, meaning, point_code}]，保持错词本的顺序（last_wrong_id 从大到小）；只给错词复习（source 等于 review）用，随机和按知识点不再经过它
  伪代码 错词本编号串：用一条查询在库里取出该 learner 在 direction 方向上的错词本单词编号，按 last_wrong_id 从大到小，拼成逗号隔开的一个字符串 only_ids（口径同 算错词本 的错词本查询：只是多一个 direction 条件、只取 word_id；不在 DSL 里对错词逐条循环、不逐条调 vocab.取单词）；没有则返回空列表
  伪代码 调用 vocab.列默写词 direction=direction level=level only_ids=only_ids skip_ids=asked_ids（asked_ids 为空或 0 时传空串），它按 only_ids 的先后排序并负责全部排除规则（level 前缀、meaning/kanji 非空、五十音、语法说明、bare 规则、已被删的词自然不在其中）；直接返回它的 words（不再自己逐词循环、不做二重循环对号）

函数 开新轮 learner direction level? source? current_role?
  返回 {ok} 加上 取状态 的全部字段
  报错 400 方向不对
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 direction 不是 zh2jp 也不是 kanji2kana，报错 400 方向不对
  伪代码 调用 选词 learner=learner direction=direction level=level source=source asked_ids=空串，返回空则报错 400 没有可出的词
  伪代码 base = dictation_attempt 中该 learner 的最大 id，没有则 0
  伪代码 在一个事务里：该 learner 在当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）下 dictation_progress 已有行则更新，没有则插入（插入时写 subject_id）；写入 direction、level、source、current_word_id=新词 id、answered=0、hinted=0、asked_ids=新词 id、asked_count=1、right_count=0、round_start=base
  伪代码 返回 {"ok": 1} 加 取状态 的字段

函数 判词 direction word answer
  返回 {correct, note}；correct 为 1/0，note 是给人看的一句补充（同义词也算对、写成了同读音的另一个词、这是另一个读法……），没有为空串
  伪代码 找沾边的候选词：调用 vocab.列单词 keyword=该词假名；该词汉字不为空时再调用 keyword=汉字；该词意思去掉开头的 [N4] 等级前缀后不为空时再调用 keyword=去等级后的意思；三次结果合并、按 id 去重、去掉这个词自己，最多留 50 个，每项留 {kanji, kana, meaning}
  伪代码 调用 判默写（japanese 包的现有动词），参数是一个结构 {方向, 作答, 词, 候选}：direction 为 zh2jp 时方向取 meaning，否则取 reading；作答=answer；词={kanji, kana, meaning}；候选=上一步的列表
  伪代码 返回 {"correct": 判默写的 correct 转成整数, "note": 判默写的 note}

函数 拼词卡 direction word asked_count hinted
  返回 词卡对象 {code, head, stem, sub, hint, verdict, right, mine, note}；verdict、right、mine、note 都是空串（判完才填）
  伪代码 bare 取 word.meaning 去掉开头的「[N1]」到「[N5]」等级前缀再去首尾空白；level 取前缀里的等级（没有为空串）
  伪代码 code=「{word.id}-{asked_count}」（同一张卡判完前后 code 不变）；head 在 level 不为空时是「{level}・{方向名}」，否则只有方向名
  伪代码 direction 为 zh2jp：stem=bare，sub 空串；否则 stem=word.kanji，sub=「意思：{bare}」
  伪代码 hinted 等于 1：hint=「提示：第一个假名是「{假名第一个字}」，读音一共 {假名字数} 个字」，否则空串

函数 方向名 direction
  返回 方向的中文：zh2jp 是「看中文写日语」，kanji2kana 是「看汉字写读音」

函数 方向代号 label
  返回 方向的代号：「看中文写日语」是 zh2jp，「看汉字写读音」是 kanji2kana
  报错 400 方向不对
  伪代码 label 是这两句之外的值，报错 400 方向不对

函数 成绩文本 s
  返回 这一轮成绩文本；s 是 取状态 的结果，没有进度为空串，否则「这一轮 {right_count}/{已答数}」，已答数 = asked_count，当前词还没交答案（word_id 不为 0 且 answered 等于 0）时减 1

函数 表单回填 s
  返回 {dict_direction, dict_level, dict_source}，都是顶栏下拉的中文值；没有进度时「看中文写日语」「全部」「随机」
  伪代码 有进度：方向按 direction 转中文，level 为空填「全部」，source 等于 review 为「错词复习」其余「随机」

函数 空错词状态 learner direction level current_role?
  返回 {dphase, dempty, dcard, dstat}；dphase=empty，dempty=「「{方向名}」这个方向（等级：{level 为空填全部}）的错词本是空的——没有答错过的词，或者都已经连续答对两次了。先随机练一轮吧。」，dcard、dstat 空串
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 记下这次的选择（下次进页面顶栏还是它）：该 learner 在当前科目 subject_id（调用 subject.当前科目 learner=learner current_role=current_role 得到）下 dictation_progress 已有行则只更新 direction、level、source=review（本轮其余字段不动），没有则插入（subject_id 取当前科目，current_word_id=0、answered=1、hinted=0、asked_ids 空、asked_count=0、right_count=0、round_start=该 learner dictation_attempt 最大 id，没有为 0）

函数 开轮页面 learner direction level source current_role?
  返回 {dphase, dcard, dstat}；出得了词 dphase=ask，dcard 是新词卡，dstat 是「这一轮 0/0」；source 等于 review 但错词本里没有可出的词时返回 空错词状态 的结果
  报错 400 方向不对
  报错 400 没有可出的词
  伪代码 current_role 可选（路由注入的登录角色），原样传给 subject.当前科目 以及本函数调用的本模块函数；不传时行为同旧
  伪代码 source 等于 review：调用 候选词 learner=learner direction=direction level=level source=review asked_ids=空串，为空则返回 空错词状态 learner=learner direction=direction level=level
  伪代码 调用 开始 learner=learner direction=direction level=level source=source，得 s（报错原样向上抛）；调用 vocab.取单词 word_id=s.word_id，拼词卡 hinted=0
  伪代码 返回 {"dphase": "ask", "dcard": card, "dstat": 成绩文本(s)}

函数 算错词本 learner
  返回 列表 [{word_id, direction, kanji, kana, meaning, last_answer, last_at, last_wrong_id}]，按 last_wrong_id 从大到小
  伪代码 查 dictation_attempt 中该 learner 的全部行，按 (word_id, direction) 分组，各组内按 id 排序
  伪代码 实现要求（性能）：错词本这一条查询要在一遍扫描里做完（SQL 里用窗口函数 MAX(CASE WHEN correct=0 THEN id END) OVER (PARTITION BY word_id, direction) 先算出每组的 last_wrong_id，再按组数「之后连续答对」；不能对每个 (词, 方向) 再回头扫一遍该学习者的作答），学习者有一万多条作答、几百个错词时也要在 0.1 秒内
  伪代码 每组取 correct 等于 0 的最大 id 为 last_wrong_id，该组没有答错的行则跳过
  伪代码 数该组中 id 大于 last_wrong_id、correct 等于 1 且 hinted 等于 0 的行数；不小于 2 则该词该方向已出本，跳过（看过提示答对不算进连续两次）
  伪代码 对留下的组调用 vocab.取单词 word_id=word_id，取不到（词已被删）则跳过；其余拼出条目，last_answer、last_at 取 last_wrong_id 那行的 answer、at
  伪代码 按 last_wrong_id 从大到小排序后返回

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
