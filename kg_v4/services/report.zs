业务 report
  依赖 account progress dictation tutor teacher_rules kg lesson subject
  用包 common db text

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {r.subject_id}
  结束

  函数 学生范围 subject_id
    设 al = 调用 account.列学生 subject={subject_id}
    设 ss = 调用 subject.列科目学生 subject_id={subject_id}
    设 res = 解析JSON []
    遍历 a0 于 {al.students}
      设 ok = 0
      遍历 x0 于 {ss.students}
        如果 {x0.learner} 等于 {a0.username}
          设 ok = 1
        结束
      结束
      如果 {ok} 等于 1
        设 o.username = {a0.username}
        设 o.display_name = {a0.display_name}
        设 o.status = {a0.status}
        设 o.last_at = {a0.last_at 或}
        设 res = 列表加项 {res} {o}
      结束
    结束
    返回 {res}
  结束

  函数 取点等级 point_code subject_id
    # 返回 等级文本（N5 到 N1），取不到返回空串
    # 调用 lesson.取知识点等级 point_code=point_code 出错时 e
    # 出错（如 404）或其 level 为空，返回空串；否则返回其 level
    设 r = 调用 lesson.取知识点等级 point_code={point_code} subject={subject_id} 出错时 er
    设 lv = {r.level 或}
    如果 {er} 不为空
      设 lv = {zz 或}
    结束
    返回 {lv}
  结束

  函数 算学生指标 username subject_id
    # 返回 {answer_total, recent_accuracy, avg_score, mastered_count, wrong_book_count, weak_all}；weak_all 是该学生全部低分点 [{point_code, title, score}]，得分低的在前
    # 调用 progress.取概览 learner=username，取 answer_total、mastered_count
    # 调用 progress.列最近作答 learner=username limit=20，得 total 和 answers；recent_accuracy = 四舍五入(其中 correct 等于 1 的个数 * 100 / total)，total 为 0 时为 0（近期正确率按最近 20 条作答算）
    # 调用 progress.列得分 learner=username，avg_score = 四舍五入(各知识点当前 score 的平均值)，没有得分行为 0
    # 调用 progress.列低分点 learner=username limit=1000，得 weak_all（阈值取 progress 默认的 80 分以下）
    # 调用 dictation.统计错词本数 learner=username，取 total 为 wrong_book_count
    # 返回 {"answer_total": …, "recent_accuracy": …, "avg_score": …, "mastered_count": …, "wrong_book_count": …, "weak_all": …}
    设 ov = 调用 progress.取概览 learner={username} subject={subject_id}
    设 ra = 调用 progress.列最近作答 learner={username} limit=20 subject={subject_id}
    设 good = 0
    设 n = 列表长度 {ra.answers}
    遍历 a 于 {ra.answers}
      如果 {a.correct} 等于 1
        设 good = 计算 {good} + 1
      结束
    结束
    设 acc = 0
    如果 {n} 大于 0
      设 acc = 计算 四舍五入({good} * 100 / {n})
    结束
    设 sc = 调用 progress.列得分 learner={username} subject={subject_id}
    设 ssum = 0
    设 cnt = 0
    遍历 x 于 {sc.scores}
      设 ssum = 计算 {ssum} + {x.score}
      设 cnt = 计算 {cnt} + 1
    结束
    设 avg = 0
    如果 {cnt} 大于 0
      设 avg = 计算 四舍五入({ssum} / {cnt})
    结束
    设 wk = 调用 progress.列低分点 learner={username} limit=1000 subject={subject_id}
    设 wb = 调用 dictation.统计错词本数 learner={username} subject={subject_id}
    设 out.answer_total = {ov.answer_total}
    设 out.recent_accuracy = {acc}
    设 out.avg_score = {avg}
    设 out.mastered_count = {ov.mastered_count}
    设 out.wrong_book_count = {wb.total}
    设 out.weak_all = {wk.points}
    返回 {out}
  结束

  公开 函数 取全班学情 sort_by? student? learner? current_role? auth_mode? subject?
    # 返回 {total, students, weak_point_count, weak_item_count, weak_points, weak_items}；students 每项 {username, display_name, status, answer_total, recent_accuracy, avg_score, mastered_count, weak_count, weak_points, wrong_book_count, last_at}，weak_points 是该生最低分的前 5 个 [{point_code, title, score}]，weak_count 是该生低分点总数；全班 weak_points 是前 10 个 [{point_code, title, student_count, avg_score, level}]；weak_items 是前 10 个 [{code, name, point_code, student_count}]。只读；student 不为空时只统计该学生
    # 报错 400 排序方式不对
    # sort_by 为空取 last_at；不是 last_at 也不是 avg_score，报错 400 排序方式不对
    # 调用 account.列学生，得全部学生（含停用），带出 username、display_name、status、last_at；student 不为空时只留 username 等于它的学生
    # 对每个学生调用 算学生指标 username=该学生 username，拼出一行；weak_count 为 weak_all 个数，weak_points 取 weak_all 前 5 个
    # 排序：sort_by 为 last_at 时按 last_at 降序（最近学习的在前，没有作答 last_at 为空串的排最后），相同按 username 升序；sort_by 为 avg_score 时按 avg_score 升序（分低的在前），相同按 username 升序
    # 全班薄弱知识点：把所有学生的 weak_all 按 point_code 合并，student_count 是有该低分点的学生数，avg_score 是这些学生该点得分的平均（四舍五入），level 调用 取点等级 point_code=该编号；按 student_count 降序、avg_score 升序、point_code 升序，取前 10 个
    # 全班薄弱条目：对合并出的每个薄弱知识点（不限于前 10）调用 kg.按知识点列条目 point_code=该编号 出错时 e，出错的跳过；其每个条目的 student_count 取该知识点的 student_count；按 student_count 降序、code 升序，取前 10 个
    # weak_point_count 和 weak_item_count 是全班薄弱知识点、薄弱条目合并后的总数（取前 10 之前的个数）
    # 返回 {"total": 学生数, "students": 列表, "weak_point_count": …, "weak_item_count": …, "weak_points": 前10, "weak_items": 前10}
    设 sb = {sort_by}
    如果 {sb} 为空
      设 sb = last_at
    结束
    如果 {sb} 不等于 last_at 且 {sb} 不等于 avg_score
      报错 400 排序方式不对
    结束
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 ls = 调用 学生范围 subject_id={subject_id}
    设 rows = 解析JSON []
    设 agg = 解析JSON []
    遍历 s 于 {ls}
      如果 {student} 为空 或 {s.username} 等于 {student}
        设 m = 调用 算学生指标 username={s.username} subject_id={subject_id}
        设 wp5 = 解析JSON []
        设 k = 0
        遍历 w 于 {m.weak_all}
          如果 {k} 小于 5
            设 wp5 = 列表加项 {wp5} {w}
          结束
          设 k = 计算 {k} + 1
          设 na = 解析JSON []
          设 found = 0
          遍历 e 于 {agg}
            如果 {e.point_code} 等于 {w.point_code}
              设 ne.point_code = {e.point_code}
              设 ne.title = {e.title}
              设 ne.student_count = 计算 {e.student_count} + 1
              设 ne.total = 计算 {e.total} + {w.score}
              设 na = 列表加项 {na} {ne}
              设 found = 1
            否则
              设 na = 列表加项 {na} {e}
            结束
          结束
          如果 {found} 等于 0
            设 ne.point_code = {w.point_code}
            设 ne.title = {w.title}
            设 ne.student_count = 1
            设 ne.total = {w.score}
            设 na = 列表加项 {na} {ne}
          结束
          设 agg = {na}
        结束
        设 row.username = {s.username}
        设 row.display_name = {s.display_name}
        设 row.status = {s.status}
        设 row.answer_total = {m.answer_total}
        设 row.recent_accuracy = {m.recent_accuracy}
        设 row.avg_score = {m.avg_score}
        设 row.mastered_count = {m.mastered_count}
        设 row.weak_count = 列表长度 {m.weak_all}
        设 row.weak_points = {wp5}
        设 row.wrong_book_count = {m.wrong_book_count}
        设 row.last_at = {s.last_at 或}
        设 rows = 列表加项 {rows} {row}
      结束
    结束
    设 srt = 解析JSON []
    遍历 rw 于 {rows}
      设 nl = 解析JSON []
      设 placed = 0
      遍历 y 于 {srt}
        设 b = 0
        如果 {placed} 等于 0
          如果 {sb} 等于 last_at
            如果 {rw.last_at} 大于 {y.last_at}
              设 b = 1
            否则如果 {rw.last_at} 等于 {y.last_at} 且 {rw.username} 小于 {y.username}
              设 b = 1
            结束
          否则
            如果 {rw.avg_score} 小于 {y.avg_score}
              设 b = 1
            否则如果 {rw.avg_score} 等于 {y.avg_score} 且 {rw.username} 小于 {y.username}
              设 b = 1
            结束
          结束
        结束
        如果 {b} 等于 1
          设 nl = 列表加项 {nl} {rw}
          设 placed = 1
        结束
        设 nl = 列表加项 {nl} {y}
      结束
      如果 {placed} 等于 0
        设 nl = 列表加项 {nl} {rw}
      结束
      设 srt = {nl}
    结束
    设 wl = 解析JSON []
    设 il = 解析JSON []
    遍历 g 于 {agg}
      设 av = 计算 四舍五入({g.total} / {g.student_count})
      设 lv = 调用 取点等级 point_code={g.point_code} subject_id={subject_id}
      设 wi.point_code = {g.point_code}
      设 wi.title = {g.title}
      设 wi.student_count = {g.student_count}
      设 wi.avg_score = {av}
      设 wi.level = {lv}
      设 nl = 解析JSON []
      设 placed = 0
      遍历 y 于 {wl}
        设 b = 0
        如果 {placed} 等于 0
          如果 {wi.student_count} 大于 {y.student_count}
            设 b = 1
          否则如果 {wi.student_count} 等于 {y.student_count} 且 {wi.avg_score} 小于 {y.avg_score}
            设 b = 1
          否则如果 {wi.student_count} 等于 {y.student_count} 且 {wi.avg_score} 等于 {y.avg_score} 且 {wi.point_code} 小于 {y.point_code}
            设 b = 1
          结束
        结束
        如果 {b} 等于 1
          设 nl = 列表加项 {nl} {wi}
          设 placed = 1
        结束
        设 nl = 列表加项 {nl} {y}
      结束
      如果 {placed} 等于 0
        设 nl = 列表加项 {nl} {wi}
      结束
      设 wl = {nl}
      设 ki = 调用 kg.按知识点列条目 point_code={g.point_code} subject={subject_id} 出错时 er
      如果 {er} 为空
        遍历 it 于 {ki.items}
          设 ii.code = {it.code}
          设 ii.name = {it.name}
          设 ii.point_code = {it.point_code}
          设 ii.student_count = {g.student_count}
          设 nl = 解析JSON []
          设 placed = 0
          遍历 y 于 {il}
            设 b = 0
            如果 {placed} 等于 0
              如果 {ii.student_count} 大于 {y.student_count}
                设 b = 1
              否则如果 {ii.student_count} 等于 {y.student_count} 且 {ii.code} 小于 {y.code}
                设 b = 1
              结束
            结束
            如果 {b} 等于 1
              设 nl = 列表加项 {nl} {ii}
              设 placed = 1
            结束
            设 nl = 列表加项 {nl} {y}
          结束
          如果 {placed} 等于 0
            设 nl = 列表加项 {nl} {ii}
          结束
          设 il = {nl}
        结束
      结束
    结束
    设 top_w = 解析JSON []
    设 k = 0
    遍历 y 于 {wl}
      如果 {k} 小于 10
        设 top_w = 列表加项 {top_w} {y}
      结束
      设 k = 计算 {k} + 1
    结束
    设 top_i = 解析JSON []
    设 k = 0
    遍历 y 于 {il}
      如果 {k} 小于 10
        设 top_i = 列表加项 {top_i} {y}
      结束
      设 k = 计算 {k} + 1
    结束
    设 out.total = 列表长度 {srt}
    设 out.students = {srt}
    设 out.weak_point_count = 列表长度 {wl}
    设 out.weak_item_count = 列表长度 {il}
    设 out.weak_points = {top_w}
    设 out.weak_items = {top_i}
    返回 {out}
  结束

  公开 函数 取学生学情 student learner? current_role? auth_mode? subject?
    # 返回 {student, display_name, status, answer_total, recent_accuracy, avg_score, mastered_count, wrong_count, wrong_answers, wrong_book_count, wrong_book, weak_count, weak_points, question_count, dialog_last_at, recent_questions, relay_count, relays, has_summary, summary, summary_author, summary_at}；wrong_answers 是最近答错的题 [{point_code, title, question_no, answer, at, score, mastered}]（题干由 quiz 持有，本模块不依赖 quiz，故只给题号与知识点标题）；wrong_book 是错词本 [{word_id, direction, kanji, kana, meaning, last_answer, last_at}]；weak_points 是前 10 个低分点 [{point_code, title, score, level}]；recent_questions 是最近 5 条学生提问 [{content, intent, at}]；relays 是该生的传达状态 [{relay_id, must_info, rounds, rounds_done, finished, confirmed}]；has_summary 为 1 时 summary、summary_author、summary_at 是最近一份学情总结，否则为空串。只读
    # 报错 400 student 不能为空
    # 报错 404 没有这个学生
    # student 为空，报错 400 student 不能为空
    # 调用 account.取账号 username=student，取不到或 role 不等于 student，报错 404 没有这个学生
    # 调用 算学生指标 username=student，得各指标和 weak_all
    # 调用 progress.列错题 learner=student limit=10，得 wrong_answers 和 wrong_count（total）；每行调用 kg.取知识点 code=point_code 取 title，取不到取空串
    # 调用 dictation.取错词本 learner=student，得 wrong_book 和 wrong_book_count
    # weak_count 是 weak_all 个数；weak_points 取 weak_all 前 10 个，每个调用 取点等级 取 level
    # 调用 tutor.取对话摘要 learner=student，取 question_count、last_at（为 dialog_last_at）、recent（为 recent_questions）
    # 调用 teacher_rules.列传达状态 student=student，取 items 为 relays、total 为 relay_count
    # 调用 取最近总结 student=student，得 has_summary、summary、author、created_at
    # 返回上述对象，status 取自账号 disabled（1 为「停用」，否则「启用」）
    如果 {student} 为空
      报错 400 student 不能为空
    结束
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 acc = 调用 account.取账号 username={student}
    如果 {acc} 为空
      报错 404 没有这个学生
    结束
    如果 {acc.role} 不等于 student
      报错 404 没有这个学生
    结束
    设 scope = 调用 学生范围 subject_id={subject_id}
    设 inscope = 0
    遍历 sc0 于 {scope}
      如果 {sc0.username} 等于 {student}
        设 inscope = 1
      结束
    结束
    如果 {inscope} 等于 0
      报错 404 没有这个学生
    结束
    设 m = 调用 算学生指标 username={student} subject_id={subject_id}
    设 wr = 调用 progress.列错题 learner={student} limit=10 subject={subject_id}
    设 wa = 解析JSON []
    遍历 w 于 {wr.wrongs}
      设 kp = 调用 kg.取知识点 code={w.point_code} subject={subject_id} 出错时 er
      设 tt = {kp.title 或}
      如果 {er} 不为空
        设 tt = {zz 或}
      结束
      设 x.point_code = {w.point_code}
      设 x.title = {tt}
      设 x.question_no = {w.question_no}
      设 x.answer = {w.answer 或}
      设 x.at = {w.at 或}
      设 x.score = {w.score}
      设 x.mastered = {w.mastered}
      设 wa = 列表加项 {wa} {x}
    结束
    设 wb = 调用 dictation.取错词本 learner={student} subject={subject_id}
    设 wp = 解析JSON []
    设 k = 0
    遍历 w 于 {m.weak_all}
      如果 {k} 小于 10
        设 lv = 调用 取点等级 point_code={w.point_code} subject_id={subject_id}
        设 y.point_code = {w.point_code}
        设 y.title = {w.title}
        设 y.score = {w.score}
        设 y.level = {lv}
        设 wp = 列表加项 {wp} {y}
      结束
      设 k = 计算 {k} + 1
    结束
    设 td = 调用 tutor.取对话摘要 learner={student} subject={subject_id}
    设 rl = 调用 teacher_rules.列传达状态 student={student} subject={subject_id}
    设 sm = 调用 取最近总结 student={student} subject={subject_id}
    设 st = 启用
    如果 {acc.disabled} 等于 1
      设 st = 停用
    结束
    设 out.student = {student}
    设 out.display_name = {acc.display_name}
    设 out.status = {st}
    设 out.answer_total = {m.answer_total}
    设 out.recent_accuracy = {m.recent_accuracy}
    设 out.avg_score = {m.avg_score}
    设 out.mastered_count = {m.mastered_count}
    设 out.wrong_count = {wr.total}
    设 out.wrong_answers = {wa}
    设 out.wrong_book_count = {wb.total}
    设 out.wrong_book = {wb.words}
    设 out.weak_count = 列表长度 {m.weak_all}
    设 out.weak_points = {wp}
    设 out.question_count = {td.question_count}
    设 out.dialog_last_at = {td.last_at 或}
    设 out.recent_questions = {td.recent}
    设 out.relay_count = {rl.total}
    设 out.relays = {rl.items}
    设 out.has_summary = {sm.has_summary}
    设 out.summary = {sm.summary 或}
    设 out.summary_author = {sm.author 或}
    设 out.summary_at = {sm.created_at 或}
    返回 {out}
  结束

  公开 函数 写学情总结 student current_user current_role? auth_mode? subject?
    # 返回 {ok, id, student, summary, author, created_at}
    # 报错 400 student 不能为空
    # 报错 400 current_user 不能为空
    # 报错 404 没有这个学生
    # 报错 400 老师暂时无法回答
    # student 为空，报错 400 student 不能为空；current_user 为空，报错 400 current_user 不能为空
    # 调用 取学生学情 student=student（学生不存在或不是学生则报 404 没有这个学生）
    # 问（回答档）：把学情（近期正确率、平均得分、已掌握数、最近答错的题、错词本、薄弱点、问老师的提问摘要、传达状态）交给模型，要求写一段给教师看的学情总结；模型出错报错 400 老师暂时无法回答，不写库
    # 往 report_summary 插入一行 (student, summary=总结, author=current_user, created_at=当前时间)，取其 id（总结只存在本表，不写 tutor 的问老师对话记录）
    # 返回 {"ok": 1, "id": id, "student": student, "summary": 总结, "author": current_user, "created_at": 当前时间}
    如果 {student} 为空
      报错 400 student 不能为空
    结束
    如果 {current_user} 为空
      报错 400 current_user 不能为空
    结束
    设 subject_id = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 d = 调用 取学生学情 student={student} subject={subject_id}
    设 pt = 请根据下面的学情数据，为教师写一段简明的学情总结（中文，不超过300字）。学生：{d.display_name}；近期正确率：{d.recent_accuracy}%；平均得分：{d.avg_score}；已掌握知识点数：{d.mastered_count}；最近答错的题：{d.wrong_answers}；错词本：{d.wrong_book}；薄弱点：{d.weak_points}；问老师的提问摘要：{d.recent_questions}；传达状态：{d.relays}
    设 lg = 调用 account.取语言 username={current_user}
    如果 {lg.lang} 等于 ja
      设 pt = {pt} 请用日语回答，专业术语第一次出现时用括号标注中文；与其他提示里的语言要求冲突时，以本句为准。
    结束
    问 reply = {pt} 用 平衡 出错时 qe
    如果 {qe} 不为空
      报错 400 老师暂时无法回答
    结束
    如果 {reply} 为空
      报错 400 老师暂时无法回答
    结束
    设 now = 当前时间
    设 p.student = {student}
    设 p.summary = {reply}
    设 p.author = {current_user}
    设 p.created_at = {now}
    设 p.subject_id = {subject_id}
    事务 app.db
      设 n = 写库表 app.db report_summary_insert {p}
      设 nid = 查一值 app.db report_summary_last_id student={student} subject_id={subject_id}
    结束
    设 out.ok = 1
    设 out.id = {nid}
    设 out.student = {student}
    设 out.summary = {reply}
    设 out.author = {current_user}
    设 out.created_at = {now}
    返回 {out}
  结束

  公开 函数 取最近总结 student learner? current_role? auth_mode? subject?
    # 返回 {student, has_summary, id, summary, author, created_at}；该学生没有总结时 has_summary 为 0，id 为 0，其余为空串（下次打开直接看上一份，不调模型）
    # 报错 400 student 不能为空
    # student 为空，报错 400 student 不能为空
    # 查 report_summary 中 student 相等的行，取 id 最大的一行
    # 没有则返回 {"student": student, "has_summary": 0, "id": 0, "summary": "", "author": "", "created_at": ""}
    # 返回 {"student": student, "has_summary": 1, "id": 该行 id, "summary": 该行 summary, "author": 该行 author, "created_at": 该行 created_at}
    如果 {student} 为空
      报错 400 student 不能为空
    结束
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 row = 查一行 app.db report_summary_latest student={student} subject_id={subject_id}
    如果 {row} 为空
      返回 {"student": "{student}", "has_summary": 0, "id": 0, "summary": "", "author": "", "created_at": ""}
    结束
    设 out.student = {student}
    设 out.has_summary = 1
    设 out.id = {row.id}
    设 out.summary = {row.summary}
    设 out.author = {row.author}
    设 out.created_at = {row.created_at}
    返回 {out}
  结束

  函数 取题干 question_no
    # 返回 题干文本，查不到返回空串
    设 e0 = {zz 或}
    设 ex = 查一值 app.db report_quiz_exists
    如果 {ex} 等于 0
      返回 {e0}
    结束
    设 st = 查一值 app.db report_quiz_stem question_no={question_no}
    返回 {st 或}
  结束

  函数 缩略 text n
    # text 超过 n 个字时取前 n 个字加省略号
    设 e0 = {zz 或}
    如果 {text} 为空
      返回 {e0}
    结束
    设 n1 = 计算 {n} + 1
    设 tail = 截取 {text} {n1} 1
    如果 {tail} 为空
      返回 {text}
    结束
    设 hd = 截取 {text} 1 {n}
    设 res = {hd}…
    返回 {res}
  结束

  公开 函数 学情首页页面 report_sort? learner? current_role? auth_mode? subject?
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sb = last_at
    设 sel = 最近学习
    如果 {report_sort} 等于 平均得分
      设 sb = avg_score
      设 sel = 平均得分
    结束
    设 cw = 调用 取全班学情 sort_by={sb} subject={subject_id}
    设 ordl = 解析JSON []
    设 lastl = 解析JSON []
    遍历 s0 于 {cw.students}
      如果 {sel} 等于 平均得分 且 {s0.answer_total} 等于 0
        设 lastl = 列表加项 {lastl} {s0}
      否则
        设 ordl = 列表加项 {ordl} {s0}
      结束
    结束
    遍历 s1 于 {lastl}
      设 ordl = 列表加项 {ordl} {s1}
    结束
    设 rows = 解析JSON []
    设 agg = 解析JSON []
    遍历 s 于 {ordl}
      设 lb = {s.display_name 或}
      如果 {lb} 为空
        设 lb = {s.username}
      结束
      设 hf = #%E5%AD%A6%E6%83%85?student={s.username}
      设 rr = —
      设 av = —
      如果 {s.answer_total} 大于 0
        设 rr = {s.recent_accuracy}%
        设 av = {s.avg_score}
      结束
      设 wt = {zz 或}
      设 k = 0
      遍历 w 于 {s.weak_points}
        如果 {k} 小于 3
          如果 {wt} 为空
            设 wt = {w.title}
          否则
            设 wt = {wt}、{w.title}
          结束
        结束
        设 k = 计算 {k} + 1
      结束
      如果 {wt} 为空
        设 wt = —
      结束
      设 row.username = {s.username}
      设 row.label = {lb}
      设 row.href = {hf}
      设 row.last_active = {s.last_at 或}
      设 row.attempt_n = {s.answer_total}
      设 row.recent_rate = {rr}
      设 row.avg_score = {av}
      设 row.mastered_n = {s.mastered_count}
      设 row.weak_points = {wt}
      设 row.book_n = {s.wrong_book_count}
      设 rows = 列表加项 {rows} {row}
      设 stt = 调用 progress.取状态 learner={s.username} subject={subject_id}
      遍历 p 于 {stt.points}
        如果 {p.total} 大于 0
          设 wr = 计算 {p.total} - {p.right}
          设 lw = 0
          如果 {wr} 大于 0
            设 lw = 1
          结束
          设 na = 解析JSON []
          设 found = 0
          遍历 e 于 {agg}
            如果 {e.code} 等于 {p.code}
              设 ne.code = {e.code}
              设 ne.title = {e.title}
              设 ne.wrong_n = 计算 {e.wrong_n} + {wr}
              设 ne.answer_n = 计算 {e.answer_n} + {p.total}
              设 ne.learner_n = 计算 {e.learner_n} + {lw}
              设 na = 列表加项 {na} {ne}
              设 found = 1
            否则
              设 na = 列表加项 {na} {e}
            结束
          结束
          如果 {found} 等于 0
            设 ne.code = {p.code}
            设 ne.title = {p.title}
            设 ne.wrong_n = {wr}
            设 ne.answer_n = {p.total}
            设 ne.learner_n = {lw}
            设 na = 列表加项 {na} {ne}
          结束
          设 agg = {na}
        结束
      结束
    结束
    设 srt = 解析JSON []
    遍历 g 于 {agg}
      如果 {g.wrong_n} 大于 0
        设 nl = 解析JSON []
        设 placed = 0
        遍历 y 于 {srt}
          设 b = 0
          如果 {placed} 等于 0
            如果 {g.wrong_n} 大于 {y.wrong_n}
              设 b = 1
            否则如果 {g.wrong_n} 等于 {y.wrong_n} 且 {g.answer_n} 大于 {y.answer_n}
              设 b = 1
            否则如果 {g.wrong_n} 等于 {y.wrong_n} 且 {g.answer_n} 等于 {y.answer_n} 且 {g.code} 小于 {y.code}
              设 b = 1
            结束
          结束
          如果 {b} 等于 1
            设 nl = 列表加项 {nl} {g}
            设 placed = 1
          结束
          设 nl = 列表加项 {nl} {y}
        结束
        如果 {placed} 等于 0
          设 nl = 列表加项 {nl} {g}
        结束
        设 srt = {nl}
      结束
    结束
    设 cwp = 解析JSON []
    设 il = 解析JSON []
    设 k = 0
    遍历 g 于 {srt}
      如果 {k} 小于 10
        设 cp.label = {g.title}
        设 cp.wrong_n = {g.wrong_n}
        设 cp.answer_n = {g.answer_n}
        设 cp.learner_n = {g.learner_n}
        设 cwp = 列表加项 {cwp} {cp}
      结束
      设 k = 计算 {k} + 1
      设 ki = 调用 kg.按知识点列条目 point_code={g.code} subject={subject_id} 出错时 er
      如果 {er} 为空
        遍历 it 于 {ki.items}
          设 ii.label = {it.name}
          设 ii.point_label = {g.title}
          设 ii.wrong_n = {g.wrong_n}
          设 ii.answer_n = {g.answer_n}
          设 ii.learner_n = {g.learner_n}
          设 ii.code = {it.code}
          设 nl = 解析JSON []
          设 placed = 0
          遍历 y 于 {il}
            设 b = 0
            如果 {placed} 等于 0
              如果 {ii.wrong_n} 大于 {y.wrong_n}
                设 b = 1
              否则如果 {ii.wrong_n} 等于 {y.wrong_n} 且 {ii.answer_n} 大于 {y.answer_n}
                设 b = 1
              否则如果 {ii.wrong_n} 等于 {y.wrong_n} 且 {ii.answer_n} 等于 {y.answer_n} 且 {ii.code} 小于 {y.code}
                设 b = 1
              结束
            结束
            如果 {b} 等于 1
              设 nl = 列表加项 {nl} {ii}
              设 placed = 1
            结束
            设 nl = 列表加项 {nl} {y}
          结束
          如果 {placed} 等于 0
            设 nl = 列表加项 {nl} {ii}
          结束
          设 il = {nl}
        结束
      结束
    结束
    设 cwi = 解析JSON []
    设 k = 0
    遍历 y 于 {il}
      如果 {k} 小于 10
        设 cwi = 列表加项 {cwi} {y}
      结束
      设 k = 计算 {k} + 1
    结束
    设 cn = 列表长度 {rows}
    设 cc = 共{cn}个学生
    设 fm.report_sort = {sel}
    设 out.class_rows = {rows}
    设 out.class_weak_points = {cwp}
    设 out.class_weak_items = {cwi}
    设 out.class_count = {cc}
    设 out.form = {fm}
    返回 {out}
  结束

  公开 函数 学生页面 student learner? current_role? auth_mode? subject?
    如果 {student} 为空
      报错 400 student 不能为空
    结束
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 acc = 调用 account.取账号 username={student}
    设 bad = 0
    如果 {acc} 为空
      设 bad = 1
    否则如果 {acc.role} 不等于 student
      设 bad = 1
    结束
    设 scope2 = 调用 学生范围 subject_id={subject_id}
    设 ins2 = 0
    遍历 sc2 于 {scope2}
      如果 {sc2.username} 等于 {student}
        设 ins2 = 1
      结束
    结束
    如果 {ins2} 等于 0
      设 bad = 1
    结束
    设 bk = #%E5%AD%A6%E6%83%85
    如果 {bad} 等于 1
      设 mt = 没有这个学生（{student}），回全班表重新选。
      设 so.username = {student}
      设 so.missing = {mt}
      设 so.back = {bk}
      设 mo.student = {so}
      返回 {mo}
    结束
    设 g = 调用 取学生学情 student={student} subject={subject_id}
    设 ser = 调用 lesson.取当前系列 learner={student} subject={subject_id}
    设 recent = 调用 progress.列最近作答 learner={student} limit=20 subject={subject_id}
    设 dict = 调用 dictation.取默写概况 learner={student} subject={subject_id}
    设 ra1 = {zz 或}
    遍历 a 于 {recent.answers}
      如果 {ra1} 为空
        设 ra1 = {a.at 或}
      结束
    结束
    设 last = {zz 或}
    设 c1 = {g.dialog_last_at 或}
    如果 {c1} 不为空
      设 last = {c1}
    结束
    如果 {ra1} 不为空
      如果 {last} 为空
        设 last = {ra1}
      否则如果 {ra1} 大于 {last}
        设 last = {ra1}
      结束
    结束
    设 c3 = {dict.last_at 或}
    如果 {c3} 不为空
      如果 {last} 为空
        设 last = {c3}
      否则如果 {c3} 大于 {last}
        设 last = {c3}
      结束
    结束
    如果 {last} 为空
      设 last = 还没有
    结束
    设 head = {g.display_name}（{student}）　教材：{ser.name 或}　最近学习：{last}
    设 w1 = 已掌握
    设 ov = 还没有作答
    如果 {g.answer_total} 大于 0
      设 ov = {w1} {g.mastered_count} 个知识点　作答 {g.answer_total} 题　近期正确率 {g.recent_accuracy}%　平均得分 {g.avg_score}
    结束
    设 w2 = 单词默写：作答
    设 dc = 单词默写：还没有作答
    如果 {dict.total} 大于 0
      设 dc = {w2} {dict.total} 次，正确率 {dict.accuracy}%，错词本 {g.wrong_book_count} 个
    结束
    设 so.username = {student}
    设 so.head = {head}
    设 so.overview = {ov}
    设 so.dictation = {dc}
    设 so.missing = {zz 或}
    设 so.back = {bk}
    设 wa = AI
    设 sh = {zz 或}
    如果 {g.has_summary} 等于 1
      设 sh = {wa} 学情总结（{g.summary_at}，{g.summary_author} 请的）
    结束
    设 ssm.student = {student}
    设 ssm.head = {sh}
    设 ssm.text = {g.summary 或}
    设 stt = 调用 progress.取状态 learner={student} subject={subject_id}
    设 scs = 调用 progress.列得分 learner={student} subject={subject_id}
    设 pl = 解析JSON []
    遍历 p 于 {stt.points}
      设 hs = 0
      设 sv = 0
      遍历 x 于 {scs.scores}
        如果 {x.point_code} 等于 {p.code}
          设 hs = 1
          设 sv = {x.score}
        结束
      结束
      如果 {p.total} 大于 0 或 {hs} 等于 1
        设 ns = 1
        设 sx = —
        如果 {hs} 等于 1
          设 ns = 0
          设 sx = {sv}
        结束
        设 mx = {zz 或}
        如果 {p.mastered} 等于 1
          设 mx = 已掌握
        结束
        设 pr.label = {p.title}
        设 pr.tally = {p.right}/{p.total}
        设 pr.score_text = {sx}
        设 pr.mastered_text = {mx}
        设 pr.ns = {ns}
        设 pr.sv = {sv}
        设 pr.code = {p.code}
        设 nl = 解析JSON []
        设 placed = 0
        遍历 y 于 {pl}
          设 b = 0
          如果 {placed} 等于 0
            如果 {pr.ns} 小于 {y.ns}
              设 b = 1
            否则如果 {pr.ns} 等于 {y.ns} 且 {pr.sv} 小于 {y.sv}
              设 b = 1
            否则如果 {pr.ns} 等于 {y.ns} 且 {pr.sv} 等于 {y.sv} 且 {pr.code} 小于 {y.code}
              设 b = 1
            结束
          结束
          如果 {b} 等于 1
            设 nl = 列表加项 {nl} {pr}
            设 placed = 1
          结束
          设 nl = 列表加项 {nl} {y}
        结束
        如果 {placed} 等于 0
          设 nl = 列表加项 {nl} {pr}
        结束
        设 pl = {nl}
      结束
    结束
    设 spts = 解析JSON []
    遍历 y 于 {pl}
      设 cr.label = {y.label}
      设 cr.tally = {y.tally}
      设 cr.score_text = {y.score_text}
      设 cr.mastered_text = {y.mastered_text}
      设 spts = 列表加项 {spts} {cr}
    结束
    设 aw = 调用 progress.取区间作答 learner={student} start_id=0 subject={subject_id}
    设 qs = 解析JSON []
    遍历 a 于 {aw.answers}
      设 nq = 解析JSON []
      设 found = 0
      遍历 q 于 {qs}
        如果 {q.qn} 等于 {a.question_no}
          设 nw = {q.wrong_n}
          设 nr = {q.right_n}
          设 nlw = {q.last_wrong 或}
          如果 {a.correct} 等于 1
            设 nr = 计算 {nr} + 1
          否则
            设 nw = 计算 {nw} + 1
            如果 {nlw} 为空
              设 nlw = {a.at 或}
            否则如果 {a.at} 大于 {nlw}
              设 nlw = {a.at}
            结束
          结束
          设 nx.qn = {q.qn}
          设 nx.point_code = {q.point_code}
          设 nx.wrong_n = {nw}
          设 nx.right_n = {nr}
          设 nx.last_wrong = {nlw}
          设 nq = 列表加项 {nq} {nx}
          设 found = 1
        否则
          设 nq = 列表加项 {nq} {q}
        结束
      结束
      如果 {found} 等于 0
        设 nw = 0
        设 nr = 0
        设 nlw = {zz 或}
        如果 {a.correct} 等于 1
          设 nr = 1
        否则
          设 nw = 1
          设 nlw = {a.at 或}
        结束
        设 nx.qn = {a.question_no}
        设 nx.point_code = {a.point_code}
        设 nx.wrong_n = {nw}
        设 nx.right_n = {nr}
        设 nx.last_wrong = {nlw}
        设 nq = 列表加项 {nq} {nx}
      结束
      设 qs = {nq}
    结束
    设 wsort = 解析JSON []
    遍历 q 于 {qs}
      如果 {q.wrong_n} 大于 0
        设 nl = 解析JSON []
        设 placed = 0
        遍历 y 于 {wsort}
          设 b = 0
          如果 {placed} 等于 0
            如果 {q.wrong_n} 大于 {y.wrong_n}
              设 b = 1
            否则如果 {q.wrong_n} 等于 {y.wrong_n} 且 {q.last_wrong} 大于 {y.last_wrong}
              设 b = 1
            结束
          结束
          如果 {b} 等于 1
            设 nl = 列表加项 {nl} {q}
            设 placed = 1
          结束
          设 nl = 列表加项 {nl} {y}
        结束
        如果 {placed} 等于 0
          设 nl = 列表加项 {nl} {q}
        结束
        设 wsort = {nl}
      结束
    结束
    设 swr = 解析JSON []
    设 k = 0
    遍历 q 于 {wsort}
      如果 {k} 小于 10
        设 stem = 调用 取题干 question_no={q.qn}
        设 lab = 调用 缩略 text={stem} n=30
        如果 {lab} 为空
          设 lab = {q.qn}
        结束
        设 kp = 调用 kg.取知识点 code={q.point_code} subject={subject_id} 出错时 er
        设 pt = {kp.title 或}
        如果 {er} 不为空
          设 pt = {zz 或}
        结束
        如果 {pt} 为空
          设 pt = {q.point_code}
        结束
        设 tot = 计算 {q.wrong_n} + {q.right_n}
        设 wo.label = {lab}
        设 wo.point_label = {pt}
        设 wo.wrong_n = {q.wrong_n}
        设 wo.tally = {q.right_n}/{tot}
        设 wo.last_wrong = {q.last_wrong}
        设 swr = 列表加项 {swr} {wo}
      结束
      设 k = 计算 {k} + 1
    结束
    设 srec = 解析JSON []
    遍历 a 于 {recent.answers}
      设 kp = 调用 kg.取知识点 code={a.point_code} subject={subject_id} 出错时 er
      设 pt = {kp.title 或}
      如果 {er} 不为空
        设 pt = {zz 或}
      结束
      如果 {pt} 为空
        设 pt = {a.point_code}
      结束
      设 stem = 调用 取题干 question_no={a.question_no}
      设 sb2 = 调用 缩略 text={stem} n=40
      设 rs = 错
      如果 {a.correct} 等于 1
        设 rs = 对
      结束
      设 ro.at = {a.at 或}
      设 ro.point_label = {pt}
      设 ro.stem_brief = {sb2}
      设 ro.given_text = {a.answer 或}
      设 ro.result = {rs}
      设 srec = 列表加项 {srec} {ro}
    结束
    设 sbk = 解析JSON []
    遍历 bw 于 {g.wrong_book}
      设 bl = {bw.kana} {bw.meaning}
      如果 {bw.kanji} 不为空 且 {bw.kanji} 不等于 {bw.kana}
        设 bl = {bw.kanji}【{bw.kana}】{bw.meaning}
      结束
      设 dl = 看汉字写读音
      如果 {bw.direction} 等于 zh2jp
        设 dl = 看中文写日语
      结束
      设 bo.label = {bl}
      设 bo.direction_label = {dl}
      设 bo.last_wrong = {bw.last_at 或}
      设 sbk = 列表加项 {sbk} {bo}
    结束
    设 ch = 调用 tutor.列对话 learner={student} limit=40 subject={subject_id}
    设 sch = 解析JSON []
    遍历 mg 于 {ch.messages}
      设 who = 学生
      设 nt = {zz 或}
      如果 {mg.role} 等于 teacher
        设 who = 老师
        设 nr2 = 调用 teacher_rules.取回复用到 reply_id={mg.id} subject={subject_id}
        设 nt = {nr2.text 或}
      结束
      设 ct = 调用 缩略 text={mg.content} n=120
      设 co.chat_who = {who}
      设 co.chat_text = {ct}
      设 co.chat_at = {mg.at 或}
      设 co.chat_notes = {nt}
      设 sch = 列表加项 {sch} {co}
    结束
    设 snotes = 调用 teacher_rules.设定列表 student={student} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject_id}
    设 srel = 调用 teacher_rules.传达列表 student={student} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject_id}
    设 out.student = {so}
    设 out.student_summary = {ssm}
    设 out.student_points = {spts}
    设 out.student_wrong = {swr}
    设 out.student_recent = {srec}
    设 out.student_book = {sbk}
    设 out.student_chat = {sch}
    设 out.student_notes = {snotes}
    设 out.student_relays = {srel}
    返回 {out}
  结束

  公开 函数 写学情总结页面 student current_user current_role? auth_mode? subject?
    设 subject_id = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 w = 调用 写学情总结 student={student} current_user={current_user} subject={subject_id}
    设 sm = 调用 取最近总结 student={student} subject={subject_id}
    设 wa = AI
    设 hd = {wa} 学情总结（{sm.created_at}，{sm.author} 请的）
    设 so.student = {student}
    设 so.head = {hd}
    设 so.text = {sm.summary}
    设 out.student_summary = {so}
    返回 {out}
  结束

结束
