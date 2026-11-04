业务 dictation
  依赖 vocab subject
  用包 common db text japanese

  公开 函数 取状态 learner current_role? auth_mode? subject?
    # 返回 没有进度时 {has_progress: 0}；有进度时 {has_progress: 1, direction, level, source, word_id, prompt, answered, hinted, asked_count, right_count, finished}。prompt 是题面（zh2jp 为中文意思，kanji2kana 为汉字），不含答案；word_id 为 0 时 finished=1 且 prompt 为空串
    # 按 learner 查 dictation_progress 一行，查不到返回 {"has_progress": 0}
    # current_word_id 为 0：prompt 为空串，word_id=0，finished=1
    # current_word_id 不为 0：调用 vocab.取单词 word_id=current_word_id，取不到则 prompt 为空串；取到则 prompt = 题面(direction, 该词)；finished=0
    # 返回 {"has_progress": 1, "direction": direction, "level": level, "source": source, "word_id": current_word_id, "prompt": prompt, "answered": answered, "hinted": hinted, "asked_count": asked_count, "right_count": right_count, "finished": finished}
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 p = 查一行 app.db dictation_progress_get learner={learner} subject_id={sb.subject_id}
    如果 {p} 为空
      返回 {"has_progress": 0}
    结束
    设 prompt = {zz 或}
    设 finished = 1
    如果 {p.current_word_id} 不等于 0
      设 finished = 0
      设 w = 调用 vocab.取单词 word_id={p.current_word_id} subject={sb.subject_id}
      如果 {w} 不为空
        如果 {p.direction} 等于 zh2jp
          设 prompt = {w.meaning}
        否则
          设 prompt = {w.kanji}
        结束
      结束
    结束
    设 s.has_progress = 1
    设 s.direction = {p.direction}
    设 s.level = {p.level}
    设 s.source = {p.source}
    设 s.word_id = {p.current_word_id}
    设 s.prompt = {prompt}
    设 s.answered = {p.answered}
    设 s.hinted = {p.hinted}
    设 s.asked_count = {p.asked_count}
    设 s.right_count = {p.right_count}
    设 s.finished = {finished}
    设 lgs = 调用 subject.取界面语言 username={learner}
    设 s.lang = {lgs.lang 或}
    返回 {s}
  结束

  公开 函数 开始 learner direction level? source? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {ok} 加上 取状态 的全部字段（新一轮的第一个词）
    # 报错 400 方向不对
    # 报错 400 没有可出的词
    # 调用 开新轮 learner=learner direction=direction level=level source=source
    # 返回开新轮的结果
    设 r = 调用 开新轮 learner={learner} direction={direction} level={level} source={source} subject_id={sb.subject_id}
    返回 {r}
  结束

  公开 函数 再来一轮 learner current_role? auth_mode? subject?
    # 返回 同「开始」
    # 报错 400 还没有开始
    # 报错 400 没有可出的词
    # 按 learner 查 dictation_progress，查不到报错 400 还没有开始
    # 用该行已存的 direction、level、source 调用 开新轮
    # 返回开新轮的结果
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 p = 查一行 app.db dictation_progress_get learner={learner} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 400 还没有开始
    结束
    设 r = 调用 开新轮 learner={learner} direction={p.direction} level={p.level} source={p.source} subject_id={sb.subject_id}
    返回 {r}
  结束

  公开 函数 下一个 learner current_role? auth_mode? subject?
    # 返回 {ok} 加上 取状态 的全部字段；这一轮结束时 finished=1
    # 报错 400 还没有开始
    # 报错 400 当前词还没交答案
    # 按 learner 查 dictation_progress，查不到报错 400 还没有开始
    # current_word_id 不为 0 且 answered 等于 0，报错 400 当前词还没交答案
    # current_word_id 为 0，或 asked_count 不小于 10，或 选词 返回空（没有可出的词）：在库里把 current_word_id 置 0、answered 置 1，返回 {"ok": 1} 加 取状态 的字段（finished=1）
    # 否则在一个事务里更新 dictation_progress：current_word_id=新词 id，answered=0，hinted=0，asked_ids 末尾追加新词 id，asked_count 加 1
    # 返回 {"ok": 1} 加 取状态 的字段
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 p = 查一行 app.db dictation_progress_get learner={learner} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 400 还没有开始
    结束
    如果 {p.current_word_id} 不等于 0 且 {p.answered} 等于 0
      报错 400 当前词还没交答案
    结束
    设 w = 调用 选词 learner={learner} direction={p.direction} level={p.level} source={p.source} asked_ids={p.asked_ids} subject_id={sb.subject_id}
    如果 {p.current_word_id} 等于 0 或 {p.asked_count} 不小于 10 或 {w} 为空
      设 n = 写库 app.db dictation_progress_finish learner={learner} subject_id={sb.subject_id}
    否则
      设 new_ids = {p.asked_ids},{w.id}
      事务 app.db
        设 n = 写库 app.db dictation_progress_advance learner={learner} word_id={w.id} asked_ids={new_ids} subject_id={sb.subject_id}
      结束
    结束
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    设 s.ok = 1
    返回 {s}
  结束

  公开 函数 提示 learner current_role? auth_mode? subject?
    # 返回 {ok, hinted, first_kana, length}，first_kana 是当前词假名的第一个字，length 是假名字数
    # 报错 400 还没有开始
    # 报错 400 当前没有词
    # 报错 400 当前词已经交过答案
    # 报错 404 当前词已不存在
    # 按 learner 查 dictation_progress，查不到报错 400 还没有开始
    # current_word_id 为 0，报错 400 当前没有词；answered 等于 1，报错 400 当前词已经交过答案
    # 调用 vocab.取单词 word_id=current_word_id，取不到报错 404 当前词已不存在
    # 把 dictation_progress 的 hinted 置 1
    # 返回 {"ok": 1, "hinted": 1, "first_kana": 假名第一个字, "length": 假名字数}
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 p = 查一行 app.db dictation_progress_get learner={learner} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 400 还没有开始
    结束
    如果 {p.current_word_id} 等于 0
      报错 400 当前没有词
    结束
    如果 {p.answered} 等于 1
      报错 400 当前词已经交过答案
    结束
    设 w = 调用 vocab.取单词 word_id={p.current_word_id} subject={sb.subject_id}
    如果 {w} 为空
      报错 404 当前词已不存在
    结束
    设 n = 写库 app.db dictation_progress_hint learner={learner} subject_id={sb.subject_id}
    设 chars = 找全部 {w.kana} .
    设 len = 列表长度 {chars}
    设 fk = 截取 {w.kana} 1 1
    设 out.ok = 1
    设 out.hinted = 1
    设 out.first_kana = {fk}
    设 out.length = {len}
    返回 {out}
  结束

  公开 函数 交答案 learner answer current_role? auth_mode? subject?
    # 返回 {ok, correct, hinted, kanji, kana, meaning, asked_count, right_count}，correct 为 1/0，kanji、kana、meaning 是标准答案所在单词
    # 报错 400 答案不能为空
    # 报错 400 还没有开始
    # 报错 400 当前没有词
    # 报错 400 当前词已经交过答案
    # 报错 404 当前词已不存在
    # answer 去掉首尾空白后为空，报错 400 答案不能为空
    # 按 learner 查 dictation_progress，查不到报错 400 还没有开始
    # 判的永远是库里记的 current_word_id，不信前端传的；current_word_id 为 0 报错 400 当前没有词
    # answered 等于 1，报错 400 当前词已经交过答案（同一个词交两次只算一次，不写库）
    # 调用 vocab.取单词 word_id=current_word_id，取不到报错 404 当前词已不存在
    # 判对错：direction 为 zh2jp 时，answer 等于该词假名，或（该词汉字不为空且 answer 等于汉字）算对；direction 为 kanji2kana 时，answer 等于该词假名才算对；其余算错
    # 在一个事务里：往 dictation_attempt 插入一行 (learner, word_id=current_word_id, direction, answer, correct, hinted=progress.hinted, at=当前时间)；更新 dictation_progress：answered=1，答对时 right_count 加 1
    # 默写不写做题的作答、掌握、得分表，不影响知识点分数
    # 返回 {"ok": 1, "correct": correct, "hinted": progress.hinted, "kanji": 汉字, "kana": 假名, "meaning": 意思, "asked_count": asked_count, "right_count": 更新后的 right_count}
    设 a = 替换 {answer} ^\s+|\s+$
    如果 {a} 为空
      报错 400 答案不能为空
    结束
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 p = 查一行 app.db dictation_progress_get learner={learner} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 400 还没有开始
    结束
    如果 {p.current_word_id} 等于 0
      报错 400 当前没有词
    结束
    如果 {p.answered} 等于 1
      报错 400 当前词已经交过答案
    结束
    设 w = 调用 vocab.取单词 word_id={p.current_word_id} subject={sb.subject_id}
    如果 {w} 为空
      报错 404 当前词已不存在
    结束
    设 j = 调用 判词 direction={p.direction} word={w} answer={a} subject_id={sb.subject_id}
    设 correct = {j.correct}
    设 note = {j.note 或}
    设 now = 当前时间
    设 row.learner = {learner}
    设 row.word_id = {p.current_word_id}
    设 row.direction = {p.direction}
    设 row.answer = {a}
    设 row.correct = {correct}
    设 row.hinted = {p.hinted}
    设 row.at = {now}
    设 row.subject_id = {sb.subject_id}
    事务 app.db
      设 n1 = 写库表 app.db dictation_attempt_insert {row}
      设 n2 = 写库 app.db dictation_progress_answered learner={learner} correct={correct} subject_id={sb.subject_id}
    结束
    设 rc = 计算 {p.right_count} + {correct}
    设 out.ok = 1
    设 out.correct = {correct}
    设 out.hinted = {p.hinted}
    设 out.note = {note}
    设 out.kanji = {w.kanji}
    设 out.kana = {w.kana}
    设 out.meaning = {w.meaning}
    设 out.asked_count = {p.asked_count}
    设 out.right_count = {rc}
    返回 {out}
  结束

  公开 函数 列本轮错词 learner current_role? auth_mode? subject?
    # 返回 {learner, total, words}，words 是 [{word_id, direction, kanji, kana, meaning, answer}]，按作答 id 升序；没有进度时 total 为 0、words 为空
    # 按 learner 查 dictation_progress，查不到返回 {"learner": learner, "total": 0, "words": []}
    # 查 dictation_attempt 中 learner 相等、id 大于 round_start、correct 等于 0 的行，按 id 升序
    # 对每行调用 vocab.取单词 word_id=该行 word_id，取不到的行跳过；其余拼出 {word_id, direction, kanji, kana, meaning, answer}
    # 返回 {"learner": learner, "total": 行数, "words": 列表}
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 p = 查一行 app.db dictation_progress_get learner={learner} subject_id={sb.subject_id}
    设 words = 解析JSON []
    设 out.learner = {learner}
    如果 {p} 为空
      设 out.total = 0
      设 out.words = {words}
      返回 {out}
    结束
    设 rows = 查询 app.db dictation_attempt_round_wrong learner={learner} round_start={p.round_start} subject_id={sb.subject_id}
    遍历 r 于 {rows}
      设 w = 调用 vocab.取单词 word_id={r.word_id} subject={sb.subject_id}
      如果 {w} 不为空
        设 item = 解析JSON {}
        设 item.word_id = {r.word_id}
        设 item.direction = {r.direction}
        设 item.kanji = {w.kanji}
        设 item.kana = {w.kana}
        设 item.meaning = {w.meaning}
        设 item.answer = {r.answer}
        设 words = 列表加项 {words} {item}
      结束
    结束
    设 total = 列表长度 {rows}
    设 out.total = {total}
    设 out.words = {words}
    返回 {out}
  结束

  公开 函数 取错词本 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {learner, total, words}，words 是 [{word_id, direction, kanji, kana, meaning, last_answer, last_at}]，按最近一次答错的作答 id 从大到小；last_answer 和 last_at 是最近一次答错时写的内容和时间
    # 调用 算错词本 learner=learner 得到列表
    # 返回 {"learner": learner, "total": 列表长度, "words": 列表}
    设 list = 调用 算错词本 learner={learner} subject_id={sb.subject_id}
    设 n = 列表长度 {list}
    设 out.learner = {learner}
    设 out.total = {n}
    设 out.words = {list}
    返回 {out}
  结束

  公开 函数 统计错词本数 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {learner, total}，total 是错词本条数（某词某方向算一条）
    # 调用 算错词本 learner=learner 得到列表
    # 返回 {"learner": learner, "total": 列表长度}
    设 list = 调用 算错词本 learner={learner} subject_id={sb.subject_id}
    设 n = 列表长度 {list}
    设 out.learner = {learner}
    设 out.total = {n}
    返回 {out}
  结束

  公开 函数 取默写概况 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {learner, total, right, accuracy, wrong_book_count, last_at}，total 是默写作答总数，right 是答对数，accuracy 是正确率百分比（right*100/total 四舍五入取整，total 为 0 时 0），last_at 是最近一次作答时间（没有作答为空串）
    # 统计 dictation_attempt 中 learner 相等的行数 total 和 correct 等于 1 的行数 right
    # last_at 取这些行中 id 最大的那行的 at，没有则空串
    # 调用 算错词本 learner=learner，wrong_book_count 取列表长度
    # 返回 {"learner": learner, "total": total, "right": right, "accuracy": accuracy, "wrong_book_count": wrong_book_count, "last_at": last_at}
    设 st = 查一行 app.db dictation_attempt_stats learner={learner} subject_id={sb.subject_id}
    设 accuracy = 0
    如果 {st.total} 大于 0
      设 accuracy = 计算 四舍五入({st.right} * 100 / {st.total})
    结束
    设 list = 调用 算错词本 learner={learner} subject_id={sb.subject_id}
    设 n = 列表长度 {list}
    设 out.learner = {learner}
    设 out.total = {st.total}
    设 out.right = {st.right}
    设 out.accuracy = {accuracy}
    设 out.wrong_book_count = {n}
    设 out.last_at = {st.last_at}
    返回 {out}
  结束

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need 或}
    返回 {r}
  结束

  函数 题面 direction word
    # 返回 题面文字
    # direction 为 zh2jp 返回 word.meaning；否则返回 word.kanji
    如果 {direction} 等于 zh2jp
      返回 {word.meaning}
    结束
    返回 {word.kanji}
  结束

  函数 候选词 learner direction level source asked_ids subject_id
    # 返回 一个单词对象 {id, kanji, kana, meaning, point_code}；没有可出的词返回空
    # source 不为空时调用 vocab.列单词 point_code=source，否则调用 vocab.列单词 不带筛选
    # 留下可出的词：direction 为 zh2jp 要求 meaning 不为空；direction 为 kanji2kana 要求 kanji 不为空；并且 id 不在 asked_ids（逗号隔开）里，一轮里每个词只出一次
    # 一个都没有返回空；否则随机取一个返回
    设 lvbad = 匹配 {level} p\.(level|source)
    如果 {lvbad.matched} 等于 是
      设 level = {zz 或}
    结束
    设 only_ids = 查一值 app.db dictation_wrong_ids learner={learner} direction={direction} subject_id={subject_id}
    设 res = 解析JSON []
    如果 {only_ids} 为空
      返回 {res}
    结束
    设 sk = {asked_ids 或}
    如果 {sk} 等于 0
      设 sk = {zz 或}
    结束
    设 r = 调用 vocab.列默写词 direction={direction} level={level} only_ids={only_ids} skip_ids={sk} subject={subject_id}
    设 ws = {r.words}
    返回 {ws}
  结束

  函数 选词 learner direction level source asked_ids subject_id
    设 none = {zz 或}
    设 lvbad = 匹配 {level} p\.(level|source)
    如果 {lvbad.matched} 等于 是
      设 level = {none}
    结束
    设 srbad = 匹配 {source} p\.(level|source)
    如果 {srbad.matched} 等于 是
      设 source = {none}
    结束
    设 ts = 当前时间 时间戳
    如果 {source} 等于 review
      设 only_ids = 查一值 app.db dictation_wrong_ids learner={learner} direction={direction} subject_id={subject_id}
      如果 {only_ids} 为空
        返回 {none}
      结束
      设 ai0 = {asked_ids 或}
      如果 {ai0} 等于 0
        设 ai0 = {none}
      结束
      设 r0 = 调用 vocab.挑默写词 direction={direction} level={level} only_ids={only_ids} skip_ids={ai0} seed={ts} subject={subject_id}
      如果 {r0.total} 等于 0
        返回 {none}
      结束
      返回 {r0.word}
    结束
    设 practiced = 查一值 app.db dictation_attempt_practiced learner={learner} direction={direction} subject_id={subject_id}
    设 ai = {asked_ids 或}
    如果 {ai} 等于 0
      设 ai = {none}
    结束
    设 skip = {practiced 或}
    如果 {ai} 不为空
      如果 {skip} 为空
        设 skip = {ai}
      否则
        设 skip = {ai},{practiced}
      结束
    结束
    设 r1 = 调用 vocab.挑默写词 direction={direction} level={level} point_code={source} skip_ids={skip} seed={ts} subject={subject_id}
    如果 {r1.total} 大于 0
      返回 {r1.word}
    结束
    设 r2 = 调用 vocab.挑默写词 direction={direction} level={level} point_code={source} skip_ids={ai} seed={ts} subject={subject_id}
    如果 {r2.total} 大于 0
      返回 {r2.word}
    结束
    返回 {none}
  结束

  函数 开新轮 learner direction level? source? subject_id
    # 返回 {ok} 加上 取状态 的全部字段
    # 报错 400 方向不对
    # 报错 400 没有可出的词
    # direction 不是 zh2jp 也不是 kanji2kana，报错 400 方向不对
    # 调用 选词 direction=direction source=source asked_ids=空串，返回空则报错 400 没有可出的词
    # base = dictation_attempt 中该 learner 的最大 id，没有则 0
    # 在一个事务里：该 learner 在 dictation_progress 已有行则更新，没有则插入；写入 direction、level、source、current_word_id=新词 id、answered=0、hinted=0、asked_ids=新词 id、asked_count=1、right_count=0、round_start=base
    # 返回 {"ok": 1} 加 取状态 的字段
    如果 {direction} 不等于 zh2jp 且 {direction} 不等于 kanji2kana
      报错 400 方向不对
    结束
    设 w = 调用 选词 learner={learner} direction={direction} level={level} source={source} asked_ids=0 subject_id={subject_id}
    如果 {w} 为空
      报错 400 没有可出的词
    结束
    设 base = 查一值 app.db dictation_attempt_max_id learner={learner} subject_id={subject_id}
    设 p = 查一行 app.db dictation_progress_get learner={learner} subject_id={subject_id}
    设 row.learner = {learner}
    设 row.subject_id = {subject_id}
    设 row.direction = {direction}
    设 row.level = {level}
    设 row.source = {source}
    设 row.current_word_id = {w.id}
    设 row.asked_ids = {w.id}
    设 row.round_start = {base}
    事务 app.db
      如果 {p} 为空
        设 n = 写库表 app.db dictation_progress_insert {row}
      否则
        设 n = 写库表 app.db dictation_progress_reset {row}
      结束
    结束
    设 s = 调用 取状态 learner={learner} subject={subject_id}
    设 s.ok = 1
    返回 {s}
  结束

  函数 算错词本 learner subject_id
    # 返回 列表 [{word_id, direction, kanji, kana, meaning, last_answer, last_at, last_wrong_id}]，按 last_wrong_id 从大到小
    # 查 dictation_attempt 中该 learner 的全部行，按 (word_id, direction) 分组，各组内按 id 排序
    # 每组取 correct 等于 0 的最大 id 为 last_wrong_id，该组没有答错的行则跳过
    # 数该组中 id 大于 last_wrong_id、correct 等于 1 且 hinted 等于 0 的行数；不小于 2 则该词该方向已出本，跳过（看过提示答对不算进连续两次）
    # 对留下的组调用 vocab.取单词 word_id=word_id，取不到（词已被删）则跳过；其余拼出条目，last_answer、last_at 取 last_wrong_id 那行的 answer、at
    # 按 last_wrong_id 从大到小排序后返回
    设 rows = 查询 app.db dictation_wrong_book learner={learner} subject_id={subject_id}
    设 list = 解析JSON []
    遍历 r 于 {rows}
      设 w = 调用 vocab.取单词 word_id={r.word_id} subject={subject_id}
      如果 {w} 不为空
        设 item = 解析JSON {}
        设 item.word_id = {r.word_id}
        设 item.direction = {r.direction}
        设 item.kanji = {w.kanji}
        设 item.kana = {w.kana}
        设 item.meaning = {w.meaning}
        设 item.last_answer = {r.last_answer}
        设 item.last_at = {r.last_at}
        设 item.last_wrong_id = {r.last_wrong_id}
        设 list = 列表加项 {list} {item}
      结束
    结束
    返回 {list}
  结束

  函数 判词 direction word answer subject_id
    设 kws = 解析JSON []
    设 kws = 列表加项 {kws} {word.kana}
    如果 {word.kanji} 不为空
      设 kws = 列表加项 {kws} {word.kanji}
    结束
    设 bare = 替换 {word.meaning} ^\[N[1-5]\]
    设 bare = 替换 {bare} ^\s+|\s+$
    如果 {bare} 不为空
      设 kws = 列表加项 {kws} {bare}
    结束
    设 cands = 解析JSON []
    设 seen = {zz 或}
    设 cnt = 0
    遍历 kw 于 {kws}
      设 rr = 调用 vocab.列单词 keyword={kw} subject={subject_id}
      遍历 x 于 {rr.words}
        设 key = ,{x.id},
        如果 {seen} 不包含 {key} 且 {x.id} 不等于 {word.id} 且 {cnt} 小于 50
          设 seen = {seen}{key}
          设 item = 解析JSON {}
          设 item.kanji = {x.kanji}
          设 item.kana = {x.kana}
          设 item.meaning = {x.meaning}
          设 cands = 列表加项 {cands} {item}
          设 cnt = 计算 {cnt} + 1
        结束
      结束
    结束
    设 wd = 解析JSON {}
    设 wd.kanji = {word.kanji}
    设 wd.kana = {word.kana}
    设 wd.meaning = {word.meaning}
    如果 {direction} 等于 zh2jp
      设 judge_args.方向 = meaning
    否则
      设 judge_args.方向 = reading
    结束
    设 judge_args.作答 = {answer}
    设 judge_args.词 = {wd}
    设 judge_args.候选 = {cands}
    设 judged = 判默写 {judge_args}
    设 cv = 转数字 {judged.correct}
    设 out.correct = {cv}
    设 out.note = {judged.note 或}
    返回 {out}
  结束

  函数 拼词卡 direction word asked_count hinted
    设 mm = 匹配 {word.meaning} ^\[N[1-5]\]
    设 level = {zz 或}
    如果 {mm.matched} 等于 是
      设 level = 截取 {word.meaning} 2 2
    结束
    设 bare = 替换 {word.meaning} ^\[N[1-5]\]
    设 bare = 替换 {bare} ^\s+|\s+$
    设 dn = 调用 方向名 direction={direction}
    设 lg = {word.lang 或}
    如果 {lg} 等于 ja
      设 dn = 漢字を見て読みを書く
      如果 {direction} 等于 zh2jp
        设 dn = 中国語を見て日本語を書く
      结束
    结束
    设 head = {dn}
    如果 {level} 不为空
      设 head = {level}・{dn}
    结束
    设 stem = {bare}
    设 sub = {zz 或}
    如果 {direction} 不等于 zh2jp
      设 stem = {word.kanji}
      设 sub = 意思：{bare}
      如果 {lg} 等于 ja
        设 sub = 意味：{bare}
      结束
    结束
    设 hint = {zz 或}
    如果 {hinted} 等于 1
      设 fk = 截取 {word.kana} 1 1
      设 chars = 找全部 {word.kana} .
      设 len = 列表长度 {chars}
      设 hint = 提示：第一个假名是「{fk}」，读音一共 {len} 个字
      如果 {lg} 等于 ja
        设 hint = ヒント：最初の仮名は「{fk}」、読みは全部で {len} 文字
      结束
    结束
    设 card.code = {word.id}-{asked_count}
    设 card.head = {head}
    设 card.stem = {stem}
    设 card.sub = {sub}
    设 card.hint = {hint}
    设 card.verdict = {zz 或}
    设 card.right = {zz 或}
    设 card.mine = {zz 或}
    设 card.note = {zz 或}
    返回 {card}
  结束

  函数 方向名 direction
    设 t = 看汉字写读音
    如果 {direction} 等于 zh2jp
      设 t = 看中文写日语
    结束
    返回 {t}
  结束

  函数 方向代号 label
    如果 {label} 等于 看中文写日语
      设 d = zh2jp
      返回 {d}
    结束
    如果 {label} 等于 看汉字写读音
      设 d = kanji2kana
      返回 {d}
    结束
    报错 400 方向不对
  结束

  函数 成绩文本 s
    设 t = {zz 或}
    如果 {s.has_progress} 等于 1
      设 asked = {s.asked_count}
      如果 {s.word_id} 不等于 0 且 {s.answered} 等于 0
        设 asked = 计算 {asked} - 1
      结束
      设 pre = 这一轮
      如果 {s.lang 或} 等于 ja
        设 pre = このセット
      结束
      设 t = {pre} {s.right_count}/{asked}
    结束
    返回 {t}
  结束

  函数 表单回填 s
    设 out.dict_direction = 看中文写日语
    设 out.dict_level = 全部
    设 out.dict_source = 随机
    如果 {s.has_progress} 等于 1
      设 dn = 调用 方向名 direction={s.direction}
      设 out.dict_direction = {dn}
      如果 {s.level} 不为空
        设 out.dict_level = {s.level}
      结束
      如果 {s.source} 等于 review
        设 out.dict_source = 错词复习
      结束
    结束
    返回 {out}
  结束

  函数 空错词状态 learner direction level subject_id
    设 n = 写库 app.db dictation_progress_settings learner={learner} direction={direction} level={level} source=review subject_id={subject_id}
    设 dn = 调用 方向名 direction={direction}
    设 lv = 全部
    如果 {level} 不为空
      设 lv = {level}
    结束
    设 out.dphase = empty
    设 out.dempty = 「{dn}」这个方向（等级：{lv}）的错词本是空的——没有答错过的词，或者都已经连续答对两次了。先随机练一轮吧。
    设 lgx = 调用 subject.取界面语言 username={learner}
    如果 {lgx.lang} 等于 ja
      设 dnj = 漢字を見て読みを書く
      如果 {direction} 等于 zh2jp
        设 dnj = 中国語を見て日本語を書く
      结束
      设 lvj = すべて
      如果 {level} 不为空
        设 lvj = {level}
      结束
      设 out.dempty = 「{dnj}」（レベル：{lvj}）の間違えた単語帳は空です。間違えた単語がないか、すべて2回連続で正解しています。まずランダムに1セット練習しましょう。
    结束
    设 out.dcard = {zz 或}
    设 out.dstat = {zz 或}
    返回 {out}
  结束

  函数 开轮页面 learner direction level source subject_id
    如果 {source} 等于 review
      设 e0 = {zz 或}
      设 cl = 调用 候选词 learner={learner} direction={direction} level={level} source=review asked_ids={e0} subject_id={subject_id}
      设 cn = 列表长度 {cl}
      如果 {cn} 等于 0
        设 es = 调用 空错词状态 learner={learner} direction={direction} level={level} subject_id={subject_id}
        返回 {es}
      结束
    结束
    设 s = 调用 开始 learner={learner} direction={direction} level={level} source={source} subject={subject_id}
    设 w = 调用 vocab.取单词 word_id={s.word_id} subject={subject_id}
    设 w.lang = {s.lang 或}
    设 card = 调用 拼词卡 direction={direction} word={w} asked_count={s.asked_count} hinted=0
    设 st = 调用 成绩文本 s={s}
    设 out.dphase = ask
    设 out.dcard = {card}
    设 out.dstat = {st}
    返回 {out}
  结束

  公开 函数 默写页面 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    设 st = 调用 成绩文本 s={s}
    设 fm = 调用 表单回填 s={s}
    设 out.dstat = {st}
    设 out.form = {fm}
    返回 {out}
  结束

  公开 函数 开始页面 learner dict_direction? dict_level? dict_source? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    如果 {dict_direction} 为空
      设 dict_direction = 看中文写日语
    结束
    如果 {dict_level} 为空
      设 dict_level = 全部
    结束
    如果 {dict_source} 为空
      设 dict_source = 随机
    结束
    设 dir = 调用 方向代号 label={dict_direction}
    设 lv = {dict_level}
    如果 {dict_level} 等于 全部
      设 lv = {zz 或}
    结束
    设 src = {zz 或}
    如果 {dict_source} 等于 随机
      设 src = {zz 或}
    否则如果 {dict_source} 等于 错词复习
      设 src = review
    否则
      报错 400 题源不对
    结束
    设 r = 调用 开轮页面 learner={learner} direction={dir} level={lv} source={src} subject_id={sb.subject_id}
    返回 {r}
  结束

  公开 函数 随机页面 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    设 dir = zh2jp
    设 lv = {zz 或}
    如果 {s.has_progress} 等于 1
      设 dir = {s.direction}
      设 lv = {s.level}
    结束
    设 src = {zz 或}
    设 r = 调用 开轮页面 learner={learner} direction={dir} level={lv} source={src} subject_id={sb.subject_id}
    设 dn = 调用 方向名 direction={dir}
    设 dl = 全部
    如果 {lv} 不为空
      设 dl = {lv}
    结束
    设 form = 解析JSON {}
    设 form.dict_direction = {dn}
    设 form.dict_level = {dl}
    设 form.dict_source = 随机
    设 r.form = {form}
    返回 {r}
  结束

  公开 函数 练错词页面 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    设 dir = zh2jp
    设 lv = {zz 或}
    如果 {s.has_progress} 等于 1
      设 dir = {s.direction}
      设 lv = {s.level}
    结束
    设 r = 调用 开轮页面 learner={learner} direction={dir} level={lv} source=review subject_id={sb.subject_id}
    设 dn = 调用 方向名 direction={dir}
    设 dl = 全部
    如果 {lv} 不为空
      设 dl = {lv}
    结束
    设 form = 解析JSON {}
    设 form.dict_direction = {dn}
    设 form.dict_level = {dl}
    设 form.dict_source = 错词复习
    设 r.form = {form}
    返回 {r}
  结束

  公开 函数 载入页面 learner source? direction? level? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    设 dir = zh2jp
    设 lv = {zz 或}
    设 src = {zz 或}
    如果 {s.has_progress} 等于 1
      设 dir = {s.direction}
      设 lv = {s.level}
      如果 {s.source} 等于 review
        设 src = review
      结束
    结束
    如果 {direction} 等于 reading
      设 dir = kanji2kana
    否则如果 {direction} 等于 meaning
      设 dir = zh2jp
    结束
    如果 {level} 不为空
      如果 {level} 等于 全部
        设 lv = {zz 或}
      否则
        设 lv = {level}
      结束
    结束
    如果 {source} 等于 review
      设 src = review
    否则如果 {source} 等于 random
      设 src = {zz 或}
    结束
    设 r = 调用 开轮页面 learner={learner} direction={dir} level={lv} source={src} subject_id={sb.subject_id}
    设 dn = 调用 方向名 direction={dir}
    设 dl = 全部
    如果 {lv} 不为空
      设 dl = {lv}
    结束
    设 ds = 随机
    如果 {src} 等于 review
      设 ds = 错词复习
    结束
    设 form = 解析JSON {}
    设 form.dict_direction = {dn}
    设 form.dict_level = {dl}
    设 form.dict_source = {ds}
    设 r.form = {form}
    返回 {r}
  结束

  公开 函数 判答案页面 learner dict_answer? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    设 r = 调用 交答案 learner={learner} answer={dict_answer} subject={sb.subject_id}
    设 word.id = {s.word_id}
    设 word.kanji = {r.kanji}
    设 word.kana = {r.kana}
    设 word.meaning = {r.meaning}
    设 word.lang = {s.lang 或}
    设 card = 调用 拼词卡 direction={s.direction} word={word} asked_count={r.asked_count} hinted={r.hinted}
    设 bare = 替换 {r.meaning} ^\[N[1-5]\]
    设 bare = 替换 {bare} ^\s+|\s+$
    设 lg = {s.lang 或}
    设 vd = ✗不对
    如果 {lg} 等于 ja
      设 vd = ✗不正解
    结束
    如果 {r.correct} 等于 1
      设 vd = ○对了
      如果 {lg} 等于 ja
        设 vd = ○正解
      结束
      如果 {r.hinted} 等于 1
        设 vd = ○对了（看了提示，不算进错词本的「连续答对」）
        如果 {lg} 等于 ja
          设 vd = ○正解（ヒントを見たので、間違えた単語帳の「連続正解」には数えません）
        结束
      结束
    结束
    设 pre = 正确：
    如果 {lg} 等于 ja
      设 pre = 正解：
    结束
    如果 {r.kanji} 为空 或 {r.kanji} 等于 {r.kana}
      设 rt = {pre}{r.kana} {bare}
    否则
      设 rt = {pre}{r.kanji}【{r.kana}】{bare}
    结束
    设 mp = 你写的：
    如果 {lg} 等于 ja
      设 mp = あなたの答え：
    结束
    设 nt = {r.note 或}
    如果 {lg} 等于 ja 且 {nt} 不为空
      设 nt0 = {nt}
      设 nt = {nt0}
      如果 {nt0} 包含 同义
        设 nt = 同じ意味の単語も正解です
      否则如果 {nt0} 包含 读音
        设 nt = 同じ読みの別の単語です
      否则如果 {nt0} 包含 读法
        设 nt = 別の読み方です
      结束
    结束
    设 card.verdict = {vd}
    设 card.right = {rt}
    设 card.mine = {mp}{dict_answer}
    设 card.note = {nt}
    设 pre2 = 这一轮
    如果 {lg} 等于 ja
      设 pre2 = このセット
    结束
    设 st = {pre2} {r.right_count}/{r.asked_count}
    设 out.dphase = done
    设 out.dcard = {card}
    设 out.dstat = {st}
    返回 {out}
  结束

  公开 函数 提示页面 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 h = 调用 提示 learner={learner} subject={sb.subject_id}
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    设 w = 调用 vocab.取单词 word_id={s.word_id} subject={sb.subject_id}
    设 w.lang = {s.lang 或}
    设 card = 调用 拼词卡 direction={s.direction} word={w} asked_count={s.asked_count} hinted=1
    设 st = 调用 成绩文本 s={s}
    设 out.dphase = ask
    设 out.dcard = {card}
    设 out.dstat = {st}
    返回 {out}
  结束

  公开 函数 下一个页面 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 s = 调用 下一个 learner={learner} subject={sb.subject_id}
    设 st = 调用 成绩文本 s={s}
    如果 {s.finished} 等于 0
      设 w = 调用 vocab.取单词 word_id={s.word_id} subject={sb.subject_id}
      设 w.lang = {s.lang 或}
      设 card = 调用 拼词卡 direction={s.direction} word={w} asked_count={s.asked_count} hinted=0
      设 out.dphase = ask
      设 out.dcard = {card}
      设 out.dstat = {st}
      返回 {out}
    结束
    设 txt = 这一轮做完了：答对 {s.right_count} 个，共 {s.asked_count} 个。
    如果 {s.right_count} 等于 {s.asked_count}
      设 txt = 这一轮做完了：{s.asked_count} 个全对。
    结束
    如果 {s.lang 或} 等于 ja
      设 txt = このセットが終わりました：{s.asked_count} 問中 {s.right_count} 問正解。
      如果 {s.right_count} 等于 {s.asked_count}
        设 txt = このセットが終わりました：{s.asked_count} 問すべて正解。
      结束
    结束
    设 dr.text = {txt}
    设 lw = 调用 列本轮错词 learner={learner} subject={sb.subject_id}
    设 rw = 解析JSON []
    遍历 x 于 {lw.words}
      设 bare = 替换 {x.meaning} ^\[N[1-5]\]
      设 bare = 替换 {bare} ^\s+|\s+$
      如果 {x.kanji} 为空 或 {x.kanji} 等于 {x.kana}
        设 label = {x.kana} {bare}
      否则
        设 label = {x.kanji}【{x.kana}】{bare}
      结束
      设 item = 解析JSON {}
      设 item.label = {label}
      设 item.mine = {x.answer}
      设 rw = 列表加项 {rw} {item}
    结束
    设 out.dphase = end
    设 out.dround = {dr}
    设 out.dstat = {st}
    设 out.round_wrong = {rw}
    返回 {out}
  结束

  公开 函数 再来一轮页面 learner current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 s = 调用 取状态 learner={learner} subject={sb.subject_id}
    如果 {s.has_progress} 等于 0
      报错 400 还没有开始
    结束
    如果 {s.source} 等于 review
      设 e0 = {zz 或}
      设 cl = 调用 候选词 learner={learner} direction={s.direction} level={s.level} source=review asked_ids={e0} subject_id={sb.subject_id}
      设 cn = 列表长度 {cl}
      如果 {cn} 等于 0
        设 es = 调用 空错词状态 learner={learner} direction={s.direction} level={s.level} subject_id={sb.subject_id}
        返回 {es}
      结束
    结束
    设 s2 = 调用 再来一轮 learner={learner} subject={sb.subject_id}
    设 w = 调用 vocab.取单词 word_id={s2.word_id} subject={sb.subject_id}
    设 w.lang = {s2.lang 或}
    设 card = 调用 拼词卡 direction={s.direction} word={w} asked_count={s2.asked_count} hinted=0
    设 st = 调用 成绩文本 s={s2}
    设 out.dphase = ask
    设 out.dcard = {card}
    设 out.dstat = {st}
    返回 {out}
  结束

结束
