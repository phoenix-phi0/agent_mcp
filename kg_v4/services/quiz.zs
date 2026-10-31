业务 quiz
  依赖 kg lesson progress subject
  用包 common db text doc

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {"subject_id": {r.subject_id}}
  结束

  函数 编号前缀检查 subject_id code
    如果 {subject_id} 等于 1
      返回 {"ok": 1}
    结束
    设 sc = 查一值 app.db quiz_subject_code subject_id={subject_id}
    设 pre = {sc 或}
    如果 {pre} 为空
      报错 400 编号要以「{pre}.」开头
    结束
    设 pfx = {pre}.
    设 mm = 匹配 {code} ^[a-z][a-z0-9_]*\.[A-Za-z0-9_-]+$
    设 okp = 否
    如果 {code} 开头是 {pfx}
      设 okp = 是
    结束
    如果 {mm.matched} 不等于 是 或 {okp} 不等于 是
      报错 400 编号要以「{pre}.」开头
    结束
    返回 {"ok": 1}
  结束

  函数 是助手题号 subject_id code
    如果 {subject_id} 等于 1
      设 m1 = 匹配 {code} ^ta[0-9]+-[0-9]+$
      如果 {m1.matched} 等于 是
        返回 {"is_ta": 1}
      结束
      返回 {"is_ta": 0}
    结束
    设 sc = 查一值 app.db quiz_subject_code subject_id={subject_id}
    设 pre = {sc 或}
    如果 {pre} 为空
      返回 {"is_ta": 0}
    结束
    设 m2 = 匹配 {code} ^{pre}\.ta[0-9]+-[0-9]+$
    如果 {m2.matched} 等于 是
      返回 {"is_ta": 1}
    结束
    返回 {"is_ta": 0}
  结束

  函数 首个有题等级 pick_kind subject_id
    设 sl = 调用 subject.科目等级 subject_id={subject_id}
    设 pk = {pick_kind 或 全部}
    设 lv = {zz 或}
    遍历 lx 于 {sl.levels}
      如果 {lv} 为空
        如果 {pk} 等于 全部
          设 rows = 查询 app.db quiz_q_free_all level={lx} subject_id={subject_id}
        否则
          设 rows = 查询 app.db quiz_q_free_cat level={lx} category={pk} subject_id={subject_id}
        结束
        设 nrows = 列表长度 {rows}
        如果 {nrows} 大于 0
          设 lv = {lx}
        结束
      结束
    结束
    如果 {lv} 为空
      报错 404 没有可出的题
    结束
    返回 {"level": "{lv}"}
  结束

  函数 取轮大小 mode
    # 返回 整数，这一轮的题数
    # mode 等于 lesson 返回 5，否则返回 10
    如果 {mode} 等于 lesson
      返回 5
    结束
    返回 10
  结束

  函数 洗牌顺序 n seq
    # 返回 字符串，n 个下标 0..n-1 的排列用英文逗号连接，第 k 项表示显示位置 k 上放的是原第几个选项（下标从 0 起）
    # arr = [0,1,...,n-1]，state = seq
    # i 从 n-1 递减到 1：state = (state * 1103515245 + 12345) 对 2147483648 取余；j = state 对 (i+1) 取余；交换 arr[i] 与 arr[j]
    # 返回 arr 用英文逗号连接（例如 n=2、seq=1 得 "1,0"）
    设 s = 0
    设 k = 1
    当 {k} 小于 {n} 最多 200 次
      设 s = {s},{k}
      设 k = 计算 {k} + 1
    结束
    设 state = {seq}
    设 i = 计算 {n} - 1
    当 {i} 大于 0 最多 200 次
      设 state = 计算 ({state} * 1103515245 + 12345) % 2147483648
      设 j = 计算 {state} % ({i} + 1)
      设 parts = 按正则切分 {s} ,
      设 vi = 0
      设 vj = 0
      设 c = 0
      遍历 x 于 {parts}
        如果 {c} 等于 {i}
          设 vi = {x}
        结束
        如果 {c} 等于 {j}
          设 vj = {x}
        结束
        设 c = 计算 {c} + 1
      结束
      设 c = 0
      设 ns = {zz 或}
      遍历 x 于 {parts}
        设 y = {x}
        如果 {c} 等于 {i}
          设 y = {vj}
        否则如果 {c} 等于 {j}
          设 y = {vi}
        结束
        如果 {c} 等于 0
          设 ns = {y}
        否则
          设 ns = {ns},{y}
        结束
        设 c = 计算 {c} + 1
      结束
      设 s = {ns}
      设 i = 计算 {i} - 1
    结束
    返回 {s}
  结束

  函数 组题面 question_no seq subject_id
    # 返回 {question_no, course, level, category, stem, is_choice, options}；options 是 [{letter, text}]（已按 seq 打乱，letter 为显示字母 A B C…），非选择题为空列表；不含答案；题号查不到返回空
    # 按 question_no 查 quiz_question 一行，查不到返回空
    # options 字段为空：is_choice=0，options 为空列表
    # 否则按 ^ 拆成 n 个文字，is_choice=1；order = 洗牌顺序 n=n seq=seq；显示位置 k 的选项 = {letter: 第 k 个字母(A=0), text: 原第 order[k] 个文字}
    # 返回题面对象（绝不带 answer、accepted、explain）
    设 q = 查一行 app.db quiz_q_by_no question_no={question_no} subject_id={subject_id}
    如果 {q} 为空
      返回 {q}
    结束
    设 opts = {q.options}
    设 out = 解析JSON []
    设 isc = 0
    如果 {opts} 不为空
      设 isc = 1
      设 texts = 按正则切分 {opts} \^
      设 n = 列表长度 {texts}
      设 order = 调用 洗牌顺序 n={n} seq={seq}
      设 ords = 按正则切分 {order} ,
      设 k = 0
      遍历 oi 于 {ords}
        设 k1 = 计算 {k} + 1
        设 letter = 截取 ABCDEFGHIJKLMNOPQRSTUVWXYZ {k1} 1
        设 c = 0
        设 tx = {zz 或}
        遍历 t 于 {texts}
          如果 {c} 等于 {oi}
            设 tx = {t}
          结束
          设 c = 计算 {c} + 1
        结束
        设 item = {"letter": "{letter}", "text": "{tx}"}
        设 out = 列表加项 {out} {item}
        设 k = 计算 {k} + 1
      结束
    结束
    设 oqt = {"question_no": "{q.question_no}", "course": "{q.course}", "level": "{q.level}", "category": "{q.category}", "is_choice": {isc}, "options": {out}}
    设 out_q = 解析JSON {oqt}
    设 out_q.stem = {q.stem}
    返回 {out_q}
  结束

  函数 选题 learner mode level category lesson_code asked_nos asked_count new_seq subject_id
    # 返回 {question_no}；没有可出的题返回空
    # asked 为 asked_nos 按英文逗号拆开的题号集合；used_items 为 asked 中每个题号在 quiz_question 里的 item_code 集合（一轮里每个条目只出一题）
    # 「可出」指：题号不在 asked，且 item_code 不在 used_items
    # mode 为空（自由练）：取 quiz_question 中 level 相等的行（category 不为空时再要求 category 相等），按 id 升序，留下可出的，数量为 0 返回空；否则取第 ((new_seq - 1) 对数量取余) 个（从 0 起），返回其题号
    # mode 等于 lesson：调用 按课候选条目 lesson_code=lesson_code asked_count=asked_count，得到有序条目编号列表；依次取每个条目在 quiz_question 中 item_code 相等的行（按 id 升序），找到第一个可出的题就返回其题号；都没有返回空
    # mode 等于 review：依次构造候选题号列表（按顺序，去重）：
    # (1) 调用 progress.列低分点 learner=learner，对返回的每个 point_code 调用 kg.按知识点列条目 point_code=该编号，取这些条目在 quiz_question 中的题（按条目顺序、id 升序）
    # (2) 调用 progress.列错题 learner=learner，按返回顺序取每条 question_no（只保留在 quiz_question 中存在的）
    # (3) 调用 progress.列久未做已掌握点 learner=learner，对返回的每个 point_code 同 (1) 取题
    # 按候选顺序取第一个可出的题返回其题号，没有返回空
    设 askedS = ,{asked_nos},
    设 usedS = ,
    设 al = 按正则切分 {asked_nos} ,
    遍历 a 于 {al}
      如果 {a} 不为空
        设 ar = 查一行 app.db quiz_q_by_no question_no={a} subject_id={subject_id}
        如果 {ar} 不为空
          设 usedS = {usedS}{ar.item_code},
        结束
      结束
    结束
    设 cands = 解析JSON []
    如果 {mode} 为空
      如果 {category} 为空
        设 cands = 查询 app.db quiz_q_free_all level={level} subject_id={subject_id}
      否则
        设 cands = 查询 app.db quiz_q_free_cat level={level} category={category} subject_id={subject_id}
      结束
    否则如果 {mode} 等于 lesson
      设 cc = 调用 按课候选条目 lesson_code={lesson_code} asked_count={asked_count} subject_id={subject_id}
      遍历 ic 于 {cc.codes}
        设 rows = 查询 app.db quiz_q_by_item code={ic} subject_id={subject_id}
        遍历 rw 于 {rows}
          设 cands = 列表加项 {cands} {rw}
        结束
      结束
    否则如果 {mode} 等于 review
      设 lp = 调用 progress.列低分点 learner={learner} subject={subject_id}
      遍历 pt 于 {lp.points}
        设 il = 调用 kg.按知识点列条目 point_code={pt.point_code} subject={subject_id}
        遍历 itm 于 {il.items}
          设 rows = 查询 app.db quiz_q_by_item code={itm.code} subject_id={subject_id}
          遍历 rw 于 {rows}
            设 cands = 列表加项 {cands} {rw}
          结束
        结束
      结束
      设 we = 调用 progress.列错题 learner={learner} subject={subject_id}
      遍历 w 于 {we.wrongs}
        设 rw = 查一行 app.db quiz_q_by_no question_no={w.question_no} subject_id={subject_id}
        如果 {rw} 不为空
          设 cands = 列表加项 {cands} {rw}
        结束
      结束
      设 lz = 调用 progress.列久未做已掌握点 learner={learner} subject={subject_id}
      遍历 pt 于 {lz.points}
        设 il = 调用 kg.按知识点列条目 point_code={pt.point_code} subject={subject_id}
        遍历 itm 于 {il.items}
          设 rows = 查询 app.db quiz_q_by_item code={itm.code} subject_id={subject_id}
          遍历 rw 于 {rows}
            设 cands = 列表加项 {cands} {rw}
          结束
        结束
      结束
    结束
    设 elig = 解析JSON []
    遍历 cd 于 {cands}
      设 pat = ,{cd.question_no},
      设 ipat = ,{cd.item_code},
      如果 {askedS} 不包含 {pat} 且 {usedS} 不包含 {ipat}
        设 elig = 列表加项 {elig} {cd}
      结束
    结束
    设 cnt = 列表长度 {elig}
    如果 {cnt} 等于 0
      返回 {"question_no": ""}
    结束
    设 idx = 0
    如果 {mode} 为空
      设 idx = 计算 ({new_seq} - 1) % {cnt}
    结束
    设 c = 0
    设 sel = {zz 或}
    遍历 e1 于 {elig}
      如果 {c} 等于 {idx}
        设 sel = {e1.question_no}
      结束
      设 c = 计算 {c} + 1
    结束
    返回 {"question_no": "{sel}"}
  结束

  函数 按课候选条目 lesson_code asked_count subject_id
    # 返回 条目编号有序列表
    # 调用 lesson.取课文 code=lesson_code，查不到返回空列表
    # 调用 lesson.取课文关联条目 lesson_code=lesson_code，得本课条目 own（取不到则为空）
    # asked_count 等于 0（本轮第一题）：返回 own 的条目编号（本课 1 道）
    # 否则：先收易混对比条目——对 own 每个条目调用 kg.列对照 code=该条目编号，取每行不等于该条目的另一端，调用 kg.取条目 能取到的才算条目，且不在 own 里，去重
    # 再收同级条目——调用 lesson.列课文 series_code=本课 series_code level=本课 level，对每一课（跳过本课）调用 lesson.取课文关联条目，取其条目编号，不在 own 里，去重，追加在易混对比条目之后
    # 返回合并后的有序列表（易混对比在前，同级条目在后）
    设 ls = 调用 lesson.取课文 code={lesson_code} subject={subject_id}
    如果 {ls} 为空
      返回 {"codes": []}
    结束
    设 oi = 调用 lesson.取课文关联条目 lesson_code={lesson_code} subject={subject_id} 出错时 e
    设 own = 解析JSON []
    设 ownS = ,
    如果 {e} 为空
      遍历 o 于 {oi.items}
        设 own = 列表加项 {own} {o.code}
        设 ownS = {ownS}{o.code},
      结束
    结束
    如果 {asked_count} 等于 0
      返回 {"codes": {own}}
    结束
    设 out = 解析JSON []
    设 seen = {ownS}
    遍历 oc 于 {own}
      设 cr = 调用 kg.列对照 code={oc} subject={subject_id}
      遍历 row 于 {cr.contrasts}
        设 oth = {row.a_code}
        如果 {row.a_code} 等于 {oc}
          设 oth = {row.b_code}
        结束
        设 pat = ,{oth},
        如果 {seen} 不包含 {pat}
          设 ki = 调用 kg.取条目 code={oth} subject={subject_id}
          如果 {ki} 不为空
            设 out = 列表加项 {out} {oth}
            设 seen = {seen}{oth},
          结束
        结束
      结束
    结束
    设 sl = 调用 lesson.列课文 series_code={ls.series_code} level={ls.level} subject={subject_id}
    遍历 l 于 {sl.lessons}
      如果 {l.code} 不等于 {lesson_code}
        设 oi2 = 调用 lesson.取课文关联条目 lesson_code={l.code} subject={subject_id}
        遍历 o2 于 {oi2.items}
          设 pat = ,{o2.code},
          如果 {seen} 不包含 {pat}
            设 out = 列表加项 {out} {o2.code}
            设 seen = {seen}{o2.code},
          结束
        结束
      结束
    结束
    返回 {"codes": {out}}
  结束

  函数 出下一题 learner subject_id
    # 返回 {finished, question, asked_count, round_size, right_count}；finished 为 1 表示本轮已出满或再无可出的题，此时 question 为空串；否则 question 是 组题面 的对象
    # 报错 404 没有可出的题
    # 读 quiz_progress 该 learner 的行 r（调用方保证存在），round_size = 取轮大小 mode=r.mode
    # r.asked_count 不小于 round_size，返回 {"finished": 1, "question": "", "asked_count": r.asked_count, "round_size": round_size, "right_count": r.right_count}
    # new_seq = r.seq + 1；调用 选题 learner mode=r.mode level=r.level category=r.category lesson_code=r.lesson_code asked_nos=r.asked_nos asked_count=r.asked_count new_seq=new_seq
    # 选题 返回空：r.asked_count 等于 0 报错 404 没有可出的题；否则返回 finished=1 的对象（不改库）
    # 在一个事务里更新 quiz_progress 该行：current_no=选中的题号，answered=0，last_correct=0，asked_nos=（原为空则只写题号，否则原值+","+题号），asked_count+1，seq=new_seq
    # 返回 {"finished": 0, "question": 组题面(question_no=选中题号, seq=new_seq), "asked_count": 新 asked_count, "round_size": round_size, "right_count": r.right_count}
    设 sj.subject_id = {subject_id}
    设 r = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    设 mode = {r.mode 或}
    设 rs = 调用 取轮大小 mode={mode}
    如果 {r.asked_count} 不小于 {rs}
      返回 {"finished": 1, "question": "", "asked_count": {r.asked_count}, "round_size": {rs}, "right_count": {r.right_count}}
    结束
    设 ns = 计算 {r.seq} + 1
    设 sel = 调用 选题 learner={learner} mode={mode} level={r.level 或} category={r.category 或} lesson_code={r.lesson_code 或} asked_nos={r.asked_nos 或} asked_count={r.asked_count} new_seq={ns} subject_id={sj.subject_id}
    设 qn = {sel.question_no 或}
    如果 {qn} 为空
      如果 {r.asked_count} 等于 0
        报错 404 没有可出的题
      结束
      返回 {"finished": 1, "question": "", "asked_count": {r.asked_count}, "round_size": {rs}, "right_count": {r.right_count}}
    结束
    设 old = {r.asked_nos 或}
    设 nos = {qn}
    如果 {old} 不为空
      设 nos = {old},{qn}
    结束
    设 nc = 计算 {r.asked_count} + 1
    事务 app.db
      设 w = 写库 app.db quiz_p_next learner={learner} current_no={qn} asked_nos={nos} asked_count={nc} seq={ns} subject_id={sj.subject_id}
    结束
    设 qf = 调用 组题面 question_no={qn} seq={ns} subject_id={sj.subject_id}
    返回 {"finished": 0, "question": {qf}, "asked_count": {nc}, "round_size": {rs}, "right_count": {r.right_count}}
  结束

  函数 开新轮 learner mode level category lesson_code subject_id
    # 返回 同 出下一题；调用方已校验参数，mode 为空表示自由练
    # 报错 404 没有可出的题
    # 调用 progress.取区间作答 learner=learner start_id=0，取 max_id 作为 round_start_id
    # 在一个事务里：
    # 按 learner 查 quiz_progress：没有则插入 (learner, level, category, current_no 空, answered=0, right_count=0, asked_nos 空, asked_count=0, mode, lesson_code, round_start_id, seq=0, last_correct=0)
    # 有则更新：current_no 置空、answered=0、right_count=0、asked_nos 置空、asked_count=0、mode、lesson_code、round_start_id（seq 不动）；mode 为空（自由练）时同时更新 level、category 为入参，其它模式 level、category 保持原值
    # 调用 出下一题 learner=learner，出错（如 404）整个事务回滚、本函数原样报错
    # 返回 出下一题 的结果
    设 rng = 调用 progress.取区间作答 learner={learner} start_id=0 subject={subject_id}
    设 rsid = {rng.max_id 或 0}
    设 sj.subject_id = {subject_id}
    设 ex = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    事务 app.db
      如果 {ex} 为空
        设 w = 写库 app.db quiz_p_insert learner={learner} level={level} category={category} mode={mode} lesson_code={lesson_code} round_start_id={rsid} subject_id={sj.subject_id}
      否则
        如果 {mode} 为空
          设 w = 写库 app.db quiz_p_reset_free learner={learner} level={level} category={category} mode={mode} lesson_code={lesson_code} round_start_id={rsid} subject_id={sj.subject_id}
        否则
          设 w = 写库 app.db quiz_p_reset_other learner={learner} mode={mode} lesson_code={lesson_code} round_start_id={rsid} subject_id={sj.subject_id}
        结束
      结束
      设 res = 调用 出下一题 learner={learner} subject_id={subject_id}
    结束
    返回 {res}
  结束

  公开 函数 导入题库 file_path learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    # 返回 {ok, total, imported, skipped, skipped_nos}；total 是有效行数，imported 是写入题数，skipped 是条目对不上而没进库的题数，skipped_nos 是这些题号用英文逗号连接（报告里说明）
    # 报错 400 导入文件有错
    # 报错 400 题库有坏题
    # 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以
    # 每行格式「题号|课程|等级|考点类别|题干|选项|标准答案|可接受写法|解析|条目编号」，用 | 分隔；选项和可接受写法内部用 ^ 隔开；前 7 项必须出现，后 3 项可省略或为空
    # 题干换行转义：题干里要换行时写反斜杠加小写 n 两个字符，两个连着的反斜杠表示一个字面反斜杠；入库时由 quiz_q_insert.sql 用 replace 与 char(10) 还原，只处理题干
    # 坏题：字段数少于 7、题号为空、标准答案为空、同一文件内题号重复；出现任一，报错 400 题库有坏题（整批不写，库保持原样）
    # 条目编号为空，或调用 kg.取条目 code=条目编号 取不到：这一题不进库，计入 skipped 与 skipped_nos
    # 在一个事务里：删除 quiz_question 全部行（整表重灌），再逐题插入其余题 (question_no, course, level, category, stem, options, answer, accepted, explain, item_code)；quiz_progress 不动
    # 返回 {"ok": 1, "total": 有效行数, "imported": 写入数, "skipped": 跳过数, "skipped_nos": 逗号连接}
    设 d = 读文档 {file_path}
    设 er = {d.error 或}
    如果 {er} 不为空
      报错 400 导入文件有错
    结束
    设 lines = 按正则切分 {d.text} \r?\n
    设 total = 0
    设 imp = 0
    设 sk = 0
    设 skn = {zz 或}
    设 seen = ,
    设 kept = 0
    事务 app.db
      设 allq = 查询 app.db quiz_q_nos subject_id={sj.subject_id}
      遍历 aq 于 {allq}
        设 ta0 = 调用 是助手题号 subject_id={sj.subject_id} code={aq.question_no}
        如果 {ta0.is_ta} 等于 1
          设 kept = 计算 {kept} + 1
        否则
          设 w0 = 写库 app.db quiz_q_delete_one question_no={aq.question_no} subject_id={sj.subject_id}
        结束
      结束
      设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
      设 lvS = ,{sl.text},
      设 lvSlash = 替换 {sl.text} , /
      设 lnno = 0
      遍历 ln 于 {lines}
        设 lnno = 计算 {lnno} + 1
        设 mb = 匹配 {ln} ^\s*(#.*)?$
        如果 {mb.matched} 不等于 是
          设 total = 计算 {total} + 1
          设 parts = 按正则切分 {ln} \|
          设 np = 列表长度 {parts}
          如果 {np} 小于 7
            报错 400 题库有坏题
          结束
          设 f1 = {zz 或}
          设 f2 = {zz 或}
          设 f3 = {zz 或}
          设 f4 = {zz 或}
          设 f5 = {zz 或}
          设 f6 = {zz 或}
          设 f7 = {zz 或}
          设 f8 = {zz 或}
          设 f9 = {zz 或}
          设 f10 = {zz 或}
          设 c = 0
          遍历 x 于 {parts}
            设 c = 计算 {c} + 1
            设 y1 = 替换 {x} ^\s+
            设 y = 替换 {y1} \s+$
            如果 {c} 等于 1
              设 f1 = {y}
            否则如果 {c} 等于 2
              设 f2 = {y}
            否则如果 {c} 等于 3
              设 f3 = {y}
            否则如果 {c} 等于 4
              设 f4 = {y}
            否则如果 {c} 等于 5
              设 f5 = {y}
            否则如果 {c} 等于 6
              设 f6 = {y}
            否则如果 {c} 等于 7
              设 f7 = {y}
            否则如果 {c} 等于 8
              设 f8 = {y}
            否则如果 {c} 等于 9
              设 f9 = {y}
            否则如果 {c} 等于 10
              设 f10 = {y}
            结束
          结束
          如果 {f1} 为空 或 {f7} 为空
            报错 400 题库有坏题
          结束
          设 lvP = ,{f3},
          如果 {f3} 为空 或 {lvS} 不包含 {lvP}
            报错 400 题库有坏题：第{lnno}行等级{f3}不在本科目等级（{lvSlash}）里
          结束
          设 pat = ,{f1},
          如果 {seen} 包含 {pat}
            报错 400 题库有坏题
          结束
          设 seen = {seen}{f1},
          设 mc = 匹配 {f1} [,\s]
          如果 {mc.matched} 等于 是
            报错 400 题号不能含逗号或空白
          结束
          设 pc = 调用 编号前缀检查 subject_id={sj.subject_id} code={f1}
          设 tac = 调用 是助手题号 subject_id={sj.subject_id} code={f1}
          如果 {tac.is_ta} 等于 1
            报错 400 ta 格式的题号留给教师助手
          结束
          设 ot = 查一行 app.db quiz_q_other_subject question_no={f1} subject_id={sj.subject_id}
          如果 {ot} 不为空
            报错 400 题号已被其他科目使用
          结束
          设 okk = 0
          如果 {f10} 不为空
            设 ki = 调用 kg.取条目 code={f10} subject={sj.subject_id}
            如果 {ki} 不为空
              设 okk = 1
            结束
          结束
          如果 {okk} 等于 1
            设 row.question_no = {f1}
            设 row.course = {f2}
            设 row.level = {f3}
            设 row.category = {f4}
            设 row.stem = {f5}
            设 row.options = {f6}
            设 row.answer = {f7}
            设 row.accepted = {f8}
            设 row.explain = {f9}
            设 row.item_code = {f10}
            设 row.subject_id = {sj.subject_id}
            设 w1 = 写库表 app.db quiz_q_insert {row}
            设 imp = 计算 {imp} + 1
          否则
            设 sk = 计算 {sk} + 1
            如果 {skn} 为空
              设 skn = {f1}
            否则
              设 skn = {skn},{f1}
            结束
          结束
        结束
      结束
      如果 {total} 等于 0
        报错 400 导入文件有错
      结束
      设 w2 = 写库 app.db quiz_p_fix_stale subject_id={sj.subject_id}
    结束
    返回 {"ok": 1, "total": {total}, "imported": {imp}, "skipped": {sk}, "skipped_nos": "{skn}", "kept": {kept}}
  结束

  公开 函数 追加题目 rows_json learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 chk = 匹配 {rows_json} ^\s*\[
    如果 {chk.matched} 不等于 是
      报错 400 题目列表不对
    结束
    设 rows = 解析JSON {rows_json}
    设 nrows = 列表长度 {rows}
    如果 {nrows} 小于 1 或 {nrows} 大于 20
      报错 400 题目列表不对
    结束
    设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
    设 lvS = ,{sl.text},
    设 seenS = ,
    遍历 r 于 {rows}
      设 qn = 替换 {r.question_no 或} ^\s+|\s+$
      设 lv = 替换 {r.level 或} ^\s+|\s+$
      设 cg = 替换 {r.category 或} ^\s+|\s+$
      设 st = 替换 {r.stem 或} ^\s+|\s+$
      设 an = 替换 {r.answer 或} ^\s+|\s+$
      设 ic = 替换 {r.item_code 或} ^\s+|\s+$
      如果 {qn} 为空 或 {lv} 为空 或 {cg} 为空 或 {st} 为空 或 {an} 为空 或 {ic} 为空
        报错 400 题库有坏题
      结束
      设 lvP = ,{lv},
      如果 {lvS} 不包含 {lvP}
        报错 400 题库有坏题
      结束
      设 pt = ,{qn},
      如果 {seenS} 包含 {pt}
        报错 400 题库有坏题
      结束
      设 seenS = {seenS}{qn},
      设 op = {r.options 或}
      如果 {op} 不为空
        设 texts = 按正则切分 {op} \^
        设 n = 列表长度 {texts}
        如果 {n} 小于 2 或 {n} 大于 6
          报错 400 题库有坏题
        结束
        设 so = ^
        遍历 tx 于 {texts}
          设 tt = 替换 {tx} ^\s+|\s+$
          如果 {tt} 为空
            报错 400 题库有坏题
          结束
          设 tp = ^{tt}^
          如果 {so} 包含 {tp}
            报错 400 题库有坏题
          结束
          设 so = {so}{tt}^
        结束
        设 allowed = 截取 ABCDEF 1 {n}
        设 up = 转大写 {an}
        设 am = 匹配 {up} ^[A-F]$
        如果 {am.matched} 不等于 是
          报错 400 题库有坏题
        结束
        如果 {allowed} 不包含 {up}
          报错 400 题库有坏题
        结束
      结束
    结束
    遍历 r 于 {rows}
      设 qn = 替换 {r.question_no 或} ^\s+|\s+$
      设 mc = 匹配 {qn} [,\s]
      如果 {mc.matched} 等于 是
        报错 400 题号不能含逗号或空白
      结束
    结束
    遍历 r 于 {rows}
      设 qn = 替换 {r.question_no 或} ^\s+|\s+$
      设 pc = 调用 编号前缀检查 subject_id={sj.subject_id} code={qn}
    结束
    遍历 r 于 {rows}
      设 qn = 替换 {r.question_no 或} ^\s+|\s+$
      设 tac = 调用 是助手题号 subject_id={sj.subject_id} code={qn}
      如果 {tac.is_ta} 不等于 1
        报错 400 追加的题号必须是助手题号
      结束
    结束
    遍历 r 于 {rows}
      设 ic = 替换 {r.item_code 或} ^\s+|\s+$
      设 ki = 调用 kg.取条目 code={ic} subject={sj.subject_id}
      如果 {ki} 为空
        报错 400 条目不存在
      结束
    结束
    遍历 r 于 {rows}
      设 qn = 替换 {r.question_no 或} ^\s+|\s+$
      设 ex = 查一行 app.db quiz_q_exists question_no={qn}
      如果 {ex} 不为空
        报错 409 题号已存在
      结束
    结束
    设 qnos = {zz 或}
    设 cntw = 0
    事务 app.db
      遍历 r 于 {rows}
        设 qn = 替换 {r.question_no 或} ^\s+|\s+$
        设 an = 替换 {r.answer 或} ^\s+|\s+$
        设 ic = 替换 {r.item_code 或} ^\s+|\s+$
        设 row.question_no = {qn}
        设 row.course = {r.course 或}
        设 row.level = {r.level 或}
        设 row.category = {r.category 或}
        设 row.stem = {r.stem 或}
        设 row.options = {r.options 或}
        设 row.answer = {an}
        设 row.accepted = {r.accepted 或}
        设 row.explain = {r.explain 或}
        设 row.item_code = {ic}
        设 row.subject_id = {sj.subject_id}
        设 w = 写库表 app.db quiz_q_append {row}
        设 cntw = 计算 {cntw} + 1
        如果 {qnos} 为空
          设 qnos = {qn}
        否则
          设 qnos = {qnos},{qn}
        结束
      结束
    结束
    返回 {"ok": 1, "imported": {cntw}, "question_nos": "{qnos}"}
  结束

  公开 函数 删助手题目 question_nos learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 parts = 按正则切分 {question_nos} ,
    设 lst = 解析JSON []
    设 seenS = ,
    遍历 p 于 {parts}
      设 tq = 替换 {p} ^\s+|\s+$
      如果 {tq} 不为空
        设 pt = ,{tq},
        如果 {seenS} 不包含 {pt}
          设 seenS = {seenS}{tq},
          设 lst = 列表加项 {lst} {tq}
        结束
      结束
    结束
    设 cnt = 列表长度 {lst}
    如果 {cnt} 等于 0
      报错 400 题号列表不能为空
    结束
    遍历 q1 于 {lst}
      设 tac = 调用 是助手题号 subject_id={sj.subject_id} code={q1}
      如果 {tac.is_ta} 不等于 1
        报错 400 只能删助手题目
      结束
    结束
    遍历 q2 于 {lst}
      设 qr = 查一行 app.db quiz_q_by_no question_no={q2} subject_id={sj.subject_id}
      如果 {qr} 为空
        报错 404 没有这道题
      结束
    结束
    遍历 q3 于 {lst}
      设 pa = 查一行 app.db quiz_pa_by_no question_no={q3} subject_id={sj.subject_id}
      如果 {pa} 不为空
        报错 409 已有学生做过这道题，不能删除
      结束
    结束
    遍历 q4 于 {lst}
      设 pu = 查一行 app.db quiz_p_using question_no={q4} subject_id={sj.subject_id}
      如果 {pu} 不为空
        报错 409 有学生正在做这道题，不能删除
      结束
    结束
    事务 app.db
      遍历 q5 于 {lst}
        设 w = 写库 app.db quiz_q_delete_one question_no={q5} subject_id={sj.subject_id}
      结束
    结束
    返回 {"ok": 1, "deleted": {cnt}}
  结束

  公开 函数 取做题状态 learner current_role? auth_mode? subject?
    # 返回 {learner, started, mode, level, category, lesson_code, current_no, answered, right_count, asked_count, round_size, last_correct, round_key, question}；mode 为 free/lesson/review；question 是当前题的 组题面 对象（含已打乱选项，不含答案），没有当前题时为空串；没有进度行时 started=0、数字项为 0、字符串项为空串、mode=free、round_size=10
    # 按 learner 查 quiz_progress，没有则返回上述默认对象（started=0）
    # 有则 started=1，mode 库里空值转为 free，round_size = 取轮大小，round_key = round_start_id
    # current_no 不为空时 question = 组题面 question_no=current_no seq=该行 seq（题已不在库则为空串），否则空串
    # 返回上述对象
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    如果 {r} 为空
      返回 {"learner": "{learner}", "started": 0, "mode": "free", "level": "", "category": "", "lesson_code": "", "current_no": "", "answered": 0, "right_count": 0, "asked_count": 0, "round_size": 10, "last_correct": 0, "round_key": 0, "question": ""}
    结束
    设 m = {r.mode 或 free}
    设 rs = 调用 取轮大小 mode={m}
    设 cn = {r.current_no 或}
    设 q = {zz 或}
    如果 {cn} 不为空
      设 q = 调用 组题面 question_no={cn} seq={r.seq} subject_id={sj.subject_id}
    结束
    如果 {q} 为空
      返回 {"learner": "{learner}", "started": 1, "mode": "{m}", "level": "{r.level 或}", "category": "{r.category 或}", "lesson_code": "{r.lesson_code 或}", "current_no": "{cn}", "answered": {r.answered}, "right_count": {r.right_count}, "asked_count": {r.asked_count}, "round_size": {rs}, "last_correct": {r.last_correct}, "round_key": {r.round_start_id}, "question": ""}
    结束
    返回 {"learner": "{learner}", "started": 1, "mode": "{m}", "level": "{r.level 或}", "category": "{r.category 或}", "lesson_code": "{r.lesson_code 或}", "current_no": "{cn}", "answered": {r.answered}, "right_count": {r.right_count}, "asked_count": {r.asked_count}, "round_size": {rs}, "last_correct": {r.last_correct}, "round_key": {r.round_start_id}, "question": {q}}
  结束

  公开 函数 开始 learner mode? level? category? lesson_code? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    # 返回 同 出下一题：{finished, question, asked_count, round_size, right_count}
    # 报错 400 mode 不合法
    # 报错 400 等级不能为空
    # 报错 400 lesson_code 不能为空
    # 报错 404 没有这课
    # 报错 404 没有可出的题
    # mode 不为空、不等于 free、lesson、review 之一，报错 400 mode 不合法；mode 为空或 free 视为自由练（库里存空）
    # 自由练：level 为空报错 400 等级不能为空；category 为空表示该等级不限考点
    # 按课练：lesson_code 为空报错 400 lesson_code 不能为空；调用 lesson.取课文 code=lesson_code，取不到报错 404 没有这课
    # 复习薄弱点：不需要 level、category、lesson_code
    # 调用 开新轮 learner=learner mode=（自由练传空，否则 lesson/review） level=level category=category lesson_code=（按课练传 lesson_code，否则空）
    # 返回其结果（第一题已出）
    设 m = {mode 或}
    如果 {m} 不为空 且 {m} 不等于 free 且 {m} 不等于 lesson 且 {m} 不等于 review
      报错 400 mode 不合法
    结束
    设 m2 = {m}
    如果 {m} 等于 free
      设 m2 = {zz 或}
    结束
    设 lc = {zz 或}
    如果 {m2} 为空
      如果 {level} 为空
        报错 400 等级不能为空
      结束
      设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
      设 lvS = ,{sl.text},
      设 lvP = ,{level},
      如果 {lvS} 不包含 {lvP}
        报错 400 等级不在本科目里
      结束
    否则如果 {m2} 等于 lesson
      如果 {lesson_code} 为空
        报错 400 lesson_code 不能为空
      结束
      设 ls = 调用 lesson.取课文 code={lesson_code} subject={sj.subject_id}
      如果 {ls} 为空
        报错 404 没有这课
      结束
      设 lc = {lesson_code}
    结束
    设 res = 调用 开新轮 learner={learner} mode={m2} level={level} category={category} lesson_code={lc} subject_id={sj.subject_id}
    返回 {res}
  结束

  公开 函数 下一题 learner current_role? auth_mode? subject?
    # 返回 同 出下一题；finished 为 1 表示本轮结束，没有新题
    # 报错 400 还没有开始
    # 报错 400 先答完当前题
    # 按 learner 查 quiz_progress，没有报错 400 还没有开始
    # current_no 不为空且 answered 不等于 1，报错 400 先答完当前题
    # 调用 出下一题 learner=learner，返回其结果
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    如果 {r} 为空
      报错 400 还没有开始
    结束
    设 cn = {r.current_no 或}
    如果 {cn} 不为空 且 {r.answered} 不等于 1
      报错 400 先答完当前题
    结束
    设 res = 调用 出下一题 learner={learner} subject_id={sj.subject_id}
    返回 {res}
  结束

  公开 函数 提交答案 learner answer pass_line? fall_line? current_role? auth_mode? subject?
    # 返回 {ok, repeated, question_no, correct, correct_answer, explain, round_done, right_count, asked_count, round_size, score, mastered}；correct_answer 选择题是正确选项在本次显示中的字母，非选择题是标准答案；round_done 为 1 表示这是本轮最后一题；repeated 为 1 表示这道题已交过、本次不再计分（此时不写任何表，score、mastered 为空串）
    # 报错 400 答案不能为空
    # 报错 400 还没有出题
    # 报错 404 题目不存在
    # 报错 404 题目对不上条目
    # 报错 400 分数线不合法
    # answer 去掉首尾空白后为空，报错 400 答案不能为空
    # 按 learner 查 quiz_progress，没有或 current_no 为空，报错 400 还没有出题；判的永远是库里的 current_no，不接收前端题号
    # 按 current_no 查 quiz_question，查不到报错 404 题目不存在
    # 选择题（options 不为空，n=选项个数，order = 洗牌顺序 n=n seq=该行 seq，出题和判题算出同一个顺序）：取 answer 去空白转大写后出现的第一个 A–Z 字母，位置 pos=字母序号；没有字母或 pos 不小于 n 则 correct=0、stored_answer=去空白后的原答案；否则原字母 = 第 order[pos] 个选项的字母，correct = 原字母等于标准答案（去空白转大写），stored_answer = 原字母（库里存题库原字母）
    # 选择题的 correct_answer：标准答案的序号 s，找 order 中值为 s 的位置 k，取第 k 个字母；序号越界则取标准答案原文
    # 非选择题（接续题等）：answer 去首尾空白后整段比对，等于标准答案，或等于 accepted 按 ^ 拆开后某一项（各项也去首尾空白）则 correct=1，否则 0（只认标准答案和可接受写法）；stored_answer=去空白后的答案；correct_answer=标准答案
    # 该行 answered 等于 1（同一道题交两次只算一次）：不写库，返回 {"ok": 1, "repeated": 1, "question_no": current_no, "correct": last_correct, "correct_answer": ..., "explain": 解析, "round_done": ..., "right_count": ..., "asked_count": ..., "round_size": ..., "score": "", "mastered": ""}
    # 调用 kg.取条目 code=题目的 item_code，取不到报错 404 题目对不上条目；取其 point_code
    # 在一个事务里（记作答流水、更新掌握汇总、重算得分、更新掌握标记与本模块进度一起成功或一起失败）：
    # 调用 progress.记作答 learner=learner point_code=该 point_code question_no=current_no correct=correct answer=stored_answer pass_line=pass_line fall_line=fall_line，得到 score、mastered（其报错如 400 分数线不合法原样向上抛，整个事务不写）
    # 更新 quiz_progress 该行：answered=1、right_count=right_count+correct、last_correct=correct
    # round_size = 取轮大小 mode=该行 mode，round_done = asked_count 不小于 round_size 则 1 否则 0
    # 返回 {"ok": 1, "repeated": 0, "question_no": current_no, "correct": correct, "correct_answer": ..., "explain": 解析, "round_done": round_done, "right_count": 新值, "asked_count": asked_count, "round_size": round_size, "score": score, "mastered": mastered}
    设 a1 = 替换 {answer} ^\s+
    设 a2 = 替换 {a1} \s+$
    如果 {a2} 为空
      报错 400 答案不能为空
    结束
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    设 cn = {r.current_no 或}
    如果 {r} 为空 或 {cn} 为空
      报错 400 还没有出题
    结束
    设 q = 查一行 app.db quiz_q_by_no question_no={cn} subject_id={sj.subject_id}
    如果 {q} 为空
      报错 404 题目不存在
    结束
    设 opts = {q.options}
    设 ex = {q.expl 或}
    设 sa1 = 替换 {q.answer} \s+
    设 sU = 转大写 {sa1}
    设 correct = 0
    设 stored = {a2}
    设 ca = {q.answer}
    如果 {opts} 不为空
      设 texts = 按正则切分 {opts} \^
      设 n = 列表长度 {texts}
      设 order = 调用 洗牌顺序 n={n} seq={r.seq}
      设 ords = 按正则切分 {order} ,
      设 sidx = -1
      重复 26 次 计数 i
        设 ch = 截取 ABCDEFGHIJKLMNOPQRSTUVWXYZ {i} 1
        如果 {ch} 等于 {sU}
          设 sidx = 计算 {i} - 1
        结束
      结束
      设 c = 0
      遍历 o 于 {ords}
        如果 {o} 等于 {sidx}
          设 k1 = 计算 {c} + 1
          设 ca = 截取 ABCDEFGHIJKLMNOPQRSTUVWXYZ {k1} 1
        结束
        设 c = 计算 {c} + 1
      结束
      设 s2 = 替换 {a2} \s+
      设 stored = {s2}
      设 up = 转大写 {s2}
      设 lets = 找全部 {up} [A-Z]
      设 pos = -1
      遍历 L 于 {lets}
        重复 26 次 计数 i
          设 ch = 截取 ABCDEFGHIJKLMNOPQRSTUVWXYZ {i} 1
          如果 {ch} 等于 {L}
            设 pos = 计算 {i} - 1
          结束
        结束
        跳出
      结束
      如果 {pos} 不小于 0 且 {pos} 小于 {n}
        设 ov = -1
        设 c = 0
        遍历 o 于 {ords}
          如果 {c} 等于 {pos}
            设 ov = {o}
          结束
          设 c = 计算 {c} + 1
        结束
        设 ov1 = 计算 {ov} + 1
        设 origL = 截取 ABCDEFGHIJKLMNOPQRSTUVWXYZ {ov1} 1
        设 stored = {origL}
        如果 {origL} 等于 {sU}
          设 correct = 1
        结束
      结束
    否则
      如果 {a2} 等于 {q.answer}
        设 correct = 1
      结束
      设 acc = {q.accepted}
      如果 {acc} 不为空
        设 acl = 按正则切分 {acc} \^
        遍历 ai 于 {acl}
          设 t1 = 替换 {ai} ^\s+
          设 t2 = 替换 {t1} \s+$
          如果 {t2} 不为空 且 {t2} 等于 {a2}
            设 correct = 1
          结束
        结束
      结束
    结束
    设 rs = 调用 取轮大小 mode={r.mode 或}
    设 rd = 0
    如果 {r.asked_count} 不小于 {rs}
      设 rd = 1
    结束
    如果 {r.answered} 等于 1
      返回 {"ok": 1, "repeated": 1, "question_no": "{cn}", "correct": {r.last_correct}, "correct_answer": "{ca}", "explain": "{ex}", "round_done": {rd}, "right_count": {r.right_count}, "asked_count": {r.asked_count}, "round_size": {rs}, "score": "", "mastered": "", "changed": 0, "point_code": ""}
    结束
    设 it = 调用 kg.取条目 code={q.item_code} subject={sj.subject_id}
    如果 {it} 为空
      报错 404 题目对不上条目
    结束
    设 nr = 计算 {r.right_count} + {correct}
    事务 app.db
      设 pr = 调用 progress.记作答 learner={learner} point_code={it.point_code} question_no={cn} correct={correct} answer={stored} pass_line={pass_line} fall_line={fall_line} subject={sj.subject_id}
      设 w = 写库 app.db quiz_p_answer learner={learner} right_count={nr} last_correct={correct} subject_id={sj.subject_id}
    结束
    返回 {"ok": 1, "repeated": 0, "question_no": "{cn}", "correct": {correct}, "correct_answer": "{ca}", "explain": "{ex}", "round_done": {rd}, "right_count": {nr}, "asked_count": {r.asked_count}, "round_size": {rs}, "score": {pr.score}, "mastered": {pr.mastered}, "changed": {pr.changed}, "point_code": "{it.point_code}"}
  结束

  公开 函数 再来一轮 learner current_role? auth_mode? subject?
    # 返回 同 出下一题
    # 报错 400 还没有开始
    # 报错 404 没有可出的题
    # 按 learner 查 quiz_progress，没有报错 400 还没有开始
    # 调用 开新轮 learner=learner mode=该行 mode level=该行 level category=该行 category lesson_code=该行 lesson_code（沿用上一轮的模式、等级、考点、课）
    # 返回其结果
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    如果 {r} 为空
      报错 400 还没有开始
    结束
    设 res = 调用 开新轮 learner={learner} mode={r.mode 或} level={r.level 或} category={r.category 或} lesson_code={r.lesson_code 或} subject_id={sj.subject_id}
    返回 {res}
  结束

  公开 函数 取本轮作答 learner current_role? auth_mode? subject?
    # 返回 {learner, round_key, start_id, mode, lesson_code, total, answers}；round_key 是轮次标识（这一轮起点 id）；answers 同 progress.取区间作答 的 answers；没有进度行时 round_key=0、start_id=0、mode=free、lesson_code 为空串、total=0、answers 为空列表
    # 按 learner 查 quiz_progress，没有则返回上述默认对象
    # 调用 progress.取区间作答 learner=learner start_id=该行 round_start_id，得 total 和 answers
    # mode 库里空值转为 free
    # 返回 {"learner": learner, "round_key": round_start_id, "start_id": round_start_id, "mode": mode, "lesson_code": lesson_code, "total": total, "answers": answers}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    如果 {r} 为空
      返回 {"learner": "{learner}", "round_key": 0, "start_id": 0, "mode": "free", "lesson_code": "", "total": 0, "answers": []}
    结束
    设 rng = 调用 progress.取区间作答 learner={learner} start_id={r.round_start_id} subject={sj.subject_id}
    设 m = {r.mode 或 free}
    返回 {"learner": "{learner}", "round_key": {r.round_start_id}, "start_id": {r.round_start_id}, "mode": "{m}", "lesson_code": "{r.lesson_code 或}", "total": {rng.total}, "answers": {rng.answers}}
  结束

  公开 函数 取当前轮次信息 learner current_role? auth_mode? subject?
    # 返回 {learner, has_round, mode, lesson_code, level, category, round_key, asked_count, round_size, right_count, answered}；mode 为 free/lesson/review；没有进度行时 has_round=0、mode=free、round_size=10、其余数字为 0、字符串为空串
    # 按 learner 查 quiz_progress，没有则返回默认对象
    # 有则 has_round=1，mode 空值转 free，round_size=取轮大小，round_key=round_start_id，其余取该行字段
    # 返回上述对象
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 查一行 app.db quiz_p_get learner={learner} subject_id={sj.subject_id}
    如果 {r} 为空
      返回 {"learner": "{learner}", "has_round": 0, "mode": "free", "lesson_code": "", "level": "", "category": "", "round_key": 0, "asked_count": 0, "round_size": 10, "right_count": 0, "answered": 0}
    结束
    设 m = {r.mode 或 free}
    设 rs = 调用 取轮大小 mode={m}
    返回 {"learner": "{learner}", "has_round": 1, "mode": "{m}", "lesson_code": "{r.lesson_code 或}", "level": "{r.level 或}", "category": "{r.category 或}", "round_key": {r.round_start_id}, "asked_count": {r.asked_count}, "round_size": {rs}, "right_count": {r.right_count}, "answered": {r.answered}}
  结束

  函数 拼题卡 question
    设 opts = 解析JSON []
    设 qtype = {zz 或 接续}
    如果 {question.is_choice} 等于 1
      设 qtype = {zz 或 选择}
      遍历 o 于 {question.options}
        设 nit = {"key": "{o.letter}", "text": "{o.text}"}
        设 opts = 列表加项 {opts} {nit}
      结束
    结束
    设 head = {question.level}・{question.category}
    设 cdt = {"code": "{question.question_no}", "head": "{head}", "options": {opts}}
    设 card = 解析JSON {cdt}
    设 card.stem = {question.stem}
    返回 {"card": {card}, "qtype": "{qtype}"}
  结束

  函数 按课轮尾 lesson_code stat subject_id
    设 ls = 调用 lesson.取课文 code={lesson_code} subject={subject_id}
    设 text = 这一轮做完了（{stat}）。再来一轮会换一道本课的题，对比题也换；也可以换一课，或者回教材再看看这一课。
    返回 {"text": "{text}", "more": "#%E6%95%99%E6%9D%90", "back": "#%E6%95%99%E6%9D%90?lesson={lesson_code}", "explain": "#%E9%97%AE%E8%80%81%E5%B8%88?lesson={lesson_code}"}
  结束

  函数 复习薄弱点文案 learner subject_id
    设 lp = 调用 progress.列低分点 learner={learner} limit=3 subject={subject_id}
    设 names = {zz 或}
    遍历 pt 于 {lp.points}
      设 kp = 调用 kg.取知识点 code={pt.point_code} subject={subject_id}
      设 tt = {pt.point_code}
      如果 {kp} 不为空
        设 tt = {kp.title}
      结束
      如果 {names} 为空
        设 names = {tt}
      否则
        设 names = {names}、{tt}
      结束
    结束
    设 out = {zz 或 复习薄弱点}
    如果 {names} 不为空
      设 out = 复习薄弱点：{names}
    结束
    返回 {out}
  结束

  公开 函数 做题页面 learner current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 st = 调用 取做题状态 learner={learner} subject={sj.subject_id}
    设 lbl = {zz 或 这一轮}
    设 stat = {zz 或}
    如果 {st.started} 等于 1
      设 stat = {lbl} {st.right_count}/{st.asked_count}
    结束
    设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
    设 pl = {st.level 或 全部}
    设 pk = {st.category 或 全部}
    设 lvS = ,{sl.text},
    设 lvP = ,{pl},
    如果 {lvS} 不包含 {lvP}
      设 pl = {zz 或 全部}
    结束
    设 frm = {"pick_level": "{pl}", "pick_kind": "{pk}"}
    返回 {"stat": "{stat}", "form": {frm}, "level_options": {sl.options}}
  结束

  公开 函数 开始页面 learner pick_level? pick_kind? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 lbl = {zz 或 这一轮}
    设 pl = {pick_level 或 全部}
    设 pk = {pick_kind 或 全部}
    设 lv = {zz 或}
    设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
    如果 {pl} 不等于 全部
      设 lv = {pl}
    否则
      设 fr = 调用 首个有题等级 pick_kind={pk} subject_id={sj.subject_id}
      设 lv = {fr.level}
    结束
    设 cat = {zz 或}
    如果 {pk} 不等于 全部
      设 cat = {pk}
    结束
    设 res = 调用 开始 learner={learner} level={lv} category={cat} subject={sj.subject_id}
    设 stat = {lbl} {res.right_count}/{res.asked_count}
    设 qq = {res.question}
    设 tc = 调用 拼题卡 question={qq}
    设 card = {tc.card}
    设 rnd = {"text": "", "more": "", "back": "", "explain": ""}
    设 frm = {"pick_level": "{pl}", "pick_kind": "{pk}"}
    返回 {"phase": "ask", "qtype": "{tc.qtype}", "card": {card}, "scope": "", "stat": "{stat}", "cheer": "", "score_change": "", "round": {rnd}, "summary": "", "form": {frm}, "level_options": {sl.options}}
  结束

  公开 函数 判答案页面 learner choice? given? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 lbl = {zz 或 这一轮}
    设 st = 调用 取做题状态 learner={learner} subject={sj.subject_id}
    设 qs = {st.question}
    设 isc = 0
    如果 {qs} 不为空
      设 isc = {qs.is_choice}
    结束
    设 ans = {given 或}
    设 ch0 = {choice 或}
    如果 {isc} 等于 1
      设 ans = {ch0}
    结束
    设 prevs = 0
    如果 {qs} 不为空
      设 pq = 查一行 app.db quiz_q_by_no question_no={qs.question_no} subject_id={sj.subject_id}
      如果 {pq} 不为空
        设 pik = 调用 kg.取条目 code={pq.item_code} subject={sj.subject_id}
        设 psl = 调用 progress.列得分 learner={learner} subject={sj.subject_id}
        遍历 ps 于 {psl.scores}
          如果 {ps.point_code} 等于 {pik.point_code}
            设 prevs = {ps.score}
          结束
        结束
      结束
    结束
    设 res = 调用 提交答案 learner={learner} answer={ans} subject={sj.subject_id}
    设 tc = 调用 拼题卡 question={qs}
    设 sub = {zz 或}
    如果 {isc} 等于 1
      设 up = 转大写 {ans}
      设 lets = 找全部 {up} [A-Z]
      遍历 lt 于 {lets}
        设 sub = {lt}
        跳出
      结束
    结束
    设 opts2 = 解析JSON []
    遍历 op 于 {tc.card.options}
      设 stt = {zz 或 dim}
      如果 {op.key} 等于 {res.correct_answer}
        设 stt = {zz 或 right}
      否则如果 {op.key} 等于 {sub}
        设 stt = {zz 或 wrong}
      结束
      设 nit = {"key": "{op.key}", "text": "{op.text}", "state": "{stt}"}
      设 opts2 = 列表加项 {opts2} {nit}
    结束
    设 vd = {zz 或}
    如果 {res.correct} 等于 1
      设 o1 = {zz 或 ○}
      设 vd = {o1} 答对了
    否则
      设 x1 = {zz 或 ✗}
      设 vd = {x1} 正确答案是 {res.correct_answer}
    结束
    设 it2 = 查一行 app.db quiz_q_by_no question_no={res.question_no} subject_id={sj.subject_id}
    设 ik = 调用 kg.取条目 code={it2.item_code} subject={sj.subject_id}
    设 nm = {ik.name 或}
    设 ltail = {zz 或}
    设 ll = 调用 lesson.按条目列课文 item_code={it2.item_code} subject={sj.subject_id} 出错时 e
    如果 {e} 为空
      遍历 l 于 {ll.lessons}
        如果 {ltail} 为空
          设 ltail = 课文《{l.title}》{l.summary}
        结束
      结束
    结束
    设 ex2 = 查一值 app.db quiz_explain_tail expl={res.explain} name={nm} lt={ltail}
    设 card.code = {tc.card.code}
    设 card.head = {tc.card.head}
    设 card.stem = {tc.card.stem}
    设 card.options = {opts2}
    设 card.mine = {ans}
    设 card.verdict = {vd}
    设 card.explain = {ex2}
    设 ch = {zz 或}
    设 sc = {zz 或}
    如果 {res.repeated} 不等于 1 且 {res.changed} 等于 1
      设 kp2 = 调用 kg.取知识点 code={res.point_code} subject={sj.subject_id}
      设 ttl = {res.point_code}
      如果 {kp2} 不为空
        设 ttl = {kp2.title}
      结束
      设 sc = {ttl} 得分 {prevs} → {res.score}
      如果 {prevs} 小于 80 且 {res.score} 不小于 80
        设 ch = 「{ttl}」达标了，图上它后面的知识点可能解锁了。
      结束
    结束
    设 stat = {lbl} {res.right_count}/{res.asked_count}
    设 out.phase = {zz 或 done}
    设 out.card = {card}
    设 out.stat = {stat}
    设 out.cheer = {ch}
    设 out.score_change = {sc}
    设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
    设 out.level_options = {sl.options}
    返回 {out}
  结束

  公开 函数 下一题页面 learner current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 lbl = {zz 或 这一轮}
    设 ri = 调用 取当前轮次信息 learner={learner} subject={sj.subject_id}
    设 scope = {zz 或}
    如果 {ri.mode} 等于 lesson
      设 ls = 调用 lesson.取课文 code={ri.lesson_code} subject={sj.subject_id}
      设 scope = 本课《{ls.title}》（含对比题）
    否则如果 {ri.mode} 等于 review
      设 scope = 调用 复习薄弱点文案 learner={learner} subject_id={sj.subject_id}
    结束
    设 res = 调用 下一题 learner={learner} subject={sj.subject_id}
    设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
    设 stat = {lbl} {res.right_count}/{res.asked_count}
    设 rnd = {"text": "", "more": "", "back": "", "explain": ""}
    如果 {res.finished} 等于 0
      设 qq = {res.question}
      设 tc = 调用 拼题卡 question={qq}
      设 card = {tc.card}
      返回 {"phase": "ask", "qtype": "{tc.qtype}", "card": {card}, "scope": "{scope}", "stat": "{stat}", "cheer": "", "score_change": "", "round": {rnd}, "summary": "", "level_options": {sl.options}}
    结束
    如果 {ri.mode} 等于 lesson
      设 rt = 调用 按课轮尾 lesson_code={ri.lesson_code} stat={stat} subject_id={sj.subject_id}
      设 rnd = {rt}
    否则如果 {ri.mode} 等于 review
      设 txt = 这一轮复习做完了（{stat}）。可以请老师总结这一轮，或者再来一轮。
      设 rnd = {"text": "{txt}", "more": "", "back": "", "explain": ""}
    否则
      设 txt = 这一轮做完了（{stat}），{res.asked_count}道题各考一个不同的知识点。可以请老师总结这一轮，或者再来一轮。
      设 rnd = {"text": "{txt}", "more": "", "back": "", "explain": ""}
    结束
    返回 {"phase": "end", "scope": "{scope}", "stat": "{stat}", "round": {rnd}, "cheer": "", "score_change": "", "level_options": {sl.options}}
  结束

  公开 函数 再来一轮页面 learner current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 lbl = {zz 或 这一轮}
    设 ri = 调用 取当前轮次信息 learner={learner} subject={sj.subject_id}
    设 scope = {zz 或}
    如果 {ri.mode} 等于 lesson
      设 ls = 调用 lesson.取课文 code={ri.lesson_code} subject={sj.subject_id}
      设 scope = 本课《{ls.title}》（含对比题）
    否则如果 {ri.mode} 等于 review
      设 scope = 调用 复习薄弱点文案 learner={learner} subject_id={sj.subject_id}
    结束
    设 res = 调用 再来一轮 learner={learner} subject={sj.subject_id}
    设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
    设 stat = {lbl} {res.right_count}/{res.asked_count}
    设 rnd = {"text": "", "more": "", "back": "", "explain": ""}
    如果 {res.finished} 等于 0
      设 qq = {res.question}
      设 tc = 调用 拼题卡 question={qq}
      设 card = {tc.card}
      返回 {"phase": "ask", "qtype": "{tc.qtype}", "card": {card}, "scope": "{scope}", "stat": "{stat}", "cheer": "", "score_change": "", "round": {rnd}, "summary": "", "level_options": {sl.options}}
    结束
    如果 {ri.mode} 等于 lesson
      设 rt = 调用 按课轮尾 lesson_code={ri.lesson_code} stat={stat} subject_id={sj.subject_id}
      设 rnd = {rt}
    否则如果 {ri.mode} 等于 review
      设 txt = 这一轮复习做完了（{stat}）。可以请老师总结这一轮，或者再来一轮。
      设 rnd = {"text": "{txt}", "more": "", "back": "", "explain": ""}
    否则
      设 txt = 这一轮做完了（{stat}），{res.asked_count}道题各考一个不同的知识点。可以请老师总结这一轮，或者再来一轮。
      设 rnd = {"text": "{txt}", "more": "", "back": "", "explain": ""}
    结束
    返回 {"phase": "end", "scope": "{scope}", "stat": "{stat}", "round": {rnd}, "cheer": "", "score_change": "", "level_options": {sl.options}}
  结束

  公开 函数 课文页面 learner lesson? mode? level? kind? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 lbl = {zz 或 这一轮}
    设 res = {zz 或}
    设 scope = {zz 或}
    设 fl = {zz 或 全部}
    设 fk = {zz 或 全部}
    设 cm = {zz 或 free}
    设 lcode = {zz 或}
    设 sl = 调用 subject.科目等级 subject_id={sj.subject_id}
    如果 {lesson} 不为空
      设 res = 调用 开始 learner={learner} mode=lesson lesson_code={lesson} subject={sj.subject_id}
      设 ls = 调用 lesson.取课文 code={lesson} subject={sj.subject_id}
      设 scope = 本课《{ls.title}》（含对比题）
      设 st = 调用 取做题状态 learner={learner} subject={sj.subject_id}
      设 fl = {st.level 或 全部}
      设 fk = {st.category 或 全部}
      设 cm = {zz 或 lesson}
      设 lcode = {lesson}
    否则如果 {mode} 等于 review
      设 sl0 = 调用 progress.列得分 learner={learner} subject={sj.subject_id}
      设 nsc = 列表长度 {sl0.scores}
      如果 {nsc} 等于 0
        设 frm0 = {"pick_level": "{sl.first}", "pick_kind": "全部"}
        返回 {"phase": "noreview", "card": "", "scope": "", "cheer": "", "score_change": "", "round": "", "summary": "", "form": {frm0}, "level_options": {sl.options}}
      结束
      设 ri = 调用 取当前轮次信息 learner={learner} subject={sj.subject_id}
      如果 {ri.has_round} 等于 1 且 {ri.mode} 等于 review 且 {ri.asked_count} 小于 {ri.round_size}
        设 res = 调用 出下一题 learner={learner} subject_id={sj.subject_id}
      否则
        设 res = 调用 开始 learner={learner} mode=review subject={sj.subject_id}
      结束
      设 scope = 调用 复习薄弱点文案 learner={learner} subject_id={sj.subject_id}
      设 st = 调用 取做题状态 learner={learner} subject={sj.subject_id}
      设 fl = {st.level 或 全部}
      设 fk = {st.category 或 全部}
      设 cm = {zz 或 review}
    否则
      如果 {level} 为空 且 {kind} 为空
        报错 400 没有课文、等级或复习模式
      结束
      设 pl = {level 或 全部}
      设 pk = {kind 或 全部}
      设 lv = {zz 或}
      如果 {pl} 不等于 全部
        设 lv = {pl}
      否则
        设 fr = 调用 首个有题等级 pick_kind={pk} subject_id={sj.subject_id}
        设 lv = {fr.level}
      结束
      设 cat = {zz 或}
      如果 {pk} 不等于 全部
        设 cat = {pk}
      结束
      设 res = 调用 开始 learner={learner} level={lv} category={cat} subject={sj.subject_id}
      设 fl = {pl}
      设 fk = {pk}
    结束
    设 stat = {lbl} {res.right_count}/{res.asked_count}
    设 frm = {"pick_level": "{fl}", "pick_kind": "{fk}"}
    设 rnd = {"text": "", "more": "", "back": "", "explain": ""}
    如果 {res.finished} 等于 0
      设 qq = {res.question}
      设 tc = 调用 拼题卡 question={qq}
      设 card = {tc.card}
      返回 {"phase": "ask", "qtype": "{tc.qtype}", "card": {card}, "scope": "{scope}", "stat": "{stat}", "cheer": "", "score_change": "", "round": {rnd}, "summary": "", "form": {frm}, "level_options": {sl.options}}
    结束
    如果 {cm} 等于 lesson
      设 rt = 调用 按课轮尾 lesson_code={lcode} stat={stat} subject_id={sj.subject_id}
      设 rnd = {rt}
    否则如果 {cm} 等于 review
      设 txt = 这一轮复习做完了（{stat}）。可以请老师总结这一轮，或者再来一轮。
      设 rnd = {"text": "{txt}", "more": "", "back": "", "explain": ""}
    否则
      设 txt = 这一轮做完了（{stat}），{res.asked_count}道题各考一个不同的知识点。可以请老师总结这一轮，或者再来一轮。
      设 rnd = {"text": "{txt}", "more": "", "back": "", "explain": ""}
    结束
    返回 {"phase": "end", "scope": "{scope}", "stat": "{stat}", "round": {rnd}, "cheer": "", "score_change": "", "form": {frm}, "level_options": {sl.options}}
  结束

结束
