业务 progress
  依赖 kg lesson dictation vocab subject
  用包 common db text

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {"subject_id": {r.subject_id}}
  结束

  函数 核对分数线 pass_line fall_line
    # 返回 {pass_line, fall_line}，为空的项分别取默认 80 和 60，均为整数
    # 报错 400 分数线不合法
    # pass_line 为空取 80，fall_line 为空取 60
    # 任一不是 0 到 100 的整数，报错 400 分数线不合法
    # fall_line 大于 pass_line，报错 400 分数线不合法
    # 返回 {"pass_line": pass_line, "fall_line": fall_line}
    设 p = {pass_line 或 80}
    设 f = {fall_line 或 60}
    设 m1 = 匹配 {p} ^\d+$
    设 m2 = 匹配 {f} ^\d+$
    如果 {m1.matched} 不等于 是 或 {m2.matched} 不等于 是
      报错 400 分数线不合法
    结束
    设 pn = 转数字 {p}
    设 fn = 转数字 {f}
    如果 {pn} 大于 100 或 {fn} 大于 100 或 {fn} 大于 {pn}
      报错 400 分数线不合法
    结束
    返回 {"pass_line": {pn}, "fall_line": {fn}}
  结束

  函数 重算点 learner point_code pass_line fall_line subject_id
    # 返回 {score, mastered, changed}；调用方保证 progress_mastery 里已有该 learner + point_code 的行
    # 取 progress_answer 中该 learner、该 point_code 最近 10 条（按 id 降序），数量 n，答对数 r
    # score = 四舍五入(r * 100 / n)，n 为 0 时 score 为 0
    # 读 progress_mastery 该行的旧 mastered 记为 prev
    # prev 等于 1：score 不小于 fall_line 则 mastered=1 否则 0；prev 不等于 1：score 不小于 pass_line 则 mastered=1 否则 0（掌握看得分，不看累计正确率）
    # 取 progress_score 中该 learner、该 point_code 最新一行（按 id 降序第一条）
    # 没有，或其 score 不等于新 score：往 progress_score 插入 (learner, point_code, score, at=当前时间)，changed=1；否则 changed=0（变了才记一行）
    # 更新 progress_mastery 该行的 mastered、updated_at=当前时间
    # 返回 {"score": score, "mastered": mastered, "changed": changed}
    设 st = 查一行 app.db progress_recent10 learner={learner} point_code={point_code} subject_id={subject_id}
    设 n = {st.n 或 0}
    设 r = {st.r 或 0}
    设 score = 0
    如果 {n} 大于 0
      设 score = 计算 四舍五入({r} * 100 / {n})
    结束
    设 mo = 查一行 app.db progress_mastery_get learner={learner} point_code={point_code} subject_id={subject_id}
    设 prev = {mo.mastered 或 0}
    设 mastered = 0
    如果 {prev} 等于 1
      如果 {score} 不小于 {fall_line}
        设 mastered = 1
      结束
    否则
      如果 {score} 不小于 {pass_line}
        设 mastered = 1
      结束
    结束
    设 now = 当前时间
    设 last = 查一行 app.db progress_score_latest learner={learner} point_code={point_code} subject_id={subject_id}
    设 changed = 0
    如果 {last} 为空
      设 w1 = 写库 app.db progress_score_insert learner={learner} point_code={point_code} score={score} at={now} subject_id={subject_id}
      设 changed = 1
    否则如果 {last.score} 不等于 {score}
      设 w1 = 写库 app.db progress_score_insert learner={learner} point_code={point_code} score={score} at={now} subject_id={subject_id}
      设 changed = 1
    结束
    设 w2 = 写库 app.db progress_mastery_set learner={learner} point_code={point_code} mastered={mastered} at={now} subject_id={subject_id}
    返回 {"score": {score}, "mastered": {mastered}, "changed": {changed}}
  结束

  公开 函数 记作答 learner point_code question_no correct answer? pass_line? fall_line? current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {ok, total, right, score, mastered, changed}；total/right 是该学习者在该知识点的累计答题数和答对数，score 是重算后的得分，mastered 是掌握标记，changed 为 1 表示本次新记了一行得分
    # 报错 400 learner 不能为空
    # 报错 400 题号不能为空
    # 报错 400 correct 只能是 0 或 1
    # 报错 400 分数线不合法
    # 报错 404 没有这个知识点
    # learner 为空，报错 400 learner 不能为空；question_no 为空，报错 400 题号不能为空
    # correct 不是 0 也不是 1，报错 400 correct 只能是 0 或 1
    # 调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
    # 调用 核对分数线 pass_line=pass_line fall_line=fall_line，得到两条线
    # 在一个事务里（中途出错全部不算）：
    # 往 progress_answer 插入 (learner, point_code, question_no, correct, answer, at=当前时间)
    # 按 learner + point_code 查 progress_mastery：没有则插入 (right_count=correct, total_count=1, mastered=0, updated_at=当前时间)；有则 total_count+1、right_count+correct、updated_at=当前时间
    # 调用 重算点 learner point_code 两条线，得到 score、mastered、changed
    # 事务结束后读 progress_mastery 该行的 right_count、total_count
    # 返回 {"ok": 1, "total": total_count, "right": right_count, "score": score, "mastered": mastered, "changed": changed}
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    如果 {question_no} 为空
      报错 400 题号不能为空
    结束
    设 mc = 匹配 {correct} ^[01]$
    如果 {mc.matched} 不等于 是
      报错 400 correct 只能是 0 或 1
    结束
    设 p = 调用 kg.取知识点 code={point_code} subject={sid}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 lines = 调用 核对分数线 pass_line={pass_line} fall_line={fall_line}
    设 now = 当前时间
    事务 app.db
      设 arec = {"learner": "{learner}", "point_code": "{point_code}", "question_no": "{question_no}", "correct": "{correct}", "answer": "{answer}", "at": "{now}", "subject_id": "{sid}"}
      设 w1 = 写库表 app.db progress_answer_insert {arec}
      设 mrow = 查一行 app.db progress_mastery_get learner={learner} point_code={point_code} subject_id={sid}
      如果 {mrow} 为空
        设 w2 = 写库 app.db progress_mastery_insert learner={learner} point_code={point_code} right_count={correct} total_count=1 at={now} subject_id={sid}
      否则
        设 w2 = 写库 app.db progress_mastery_bump learner={learner} point_code={point_code} correct={correct} at={now} subject_id={sid}
      结束
      设 res = 调用 重算点 learner={learner} point_code={point_code} pass_line={lines.pass_line} fall_line={lines.fall_line} subject_id={sid}
    结束
    设 mrow2 = 查一行 app.db progress_mastery_get learner={learner} point_code={point_code} subject_id={sid}
    返回 {"ok": 1, "total": {mrow2.total_count}, "right": {mrow2.right_count}, "score": {res.score}, "mastered": {res.mastered}, "changed": {res.changed}}
  结束

  公开 函数 取状态 learner point_code? current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, total, mastered_count, unlocked_count, points}；points 是 [{code, title, right, total, mastered, score, unlocked}]，按知识点 id 升序；right/total 是累计答对/答题数，没记录为 0；score 是最新得分，没有为 0；unlocked 为 1 表示该点所有直接前置都已掌握（没有前置也为 1），即「现在能学」的解锁状态
    # 报错 404 没有这个知识点
    # point_code 不为空：调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点，只处理这一个点
    # point_code 为空：调用 kg.列知识点，处理全部点
    # 对每个点：读 progress_mastery 该 learner + point_code 的行得 right、total、mastered（没有全为 0）；读 progress_score 最新一行得 score（没有为 0）
    # 对每个点：调用 kg.列前置 code=该点编号，所有前置在 progress_mastery 里 mastered=1 则 unlocked=1，否则 0
    # mastered_count 是 points 中 mastered=1 的个数，unlocked_count 是 unlocked=1 的个数
    # 返回 {"learner": learner, "total": 点数, "mastered_count": mastered_count, "unlocked_count": unlocked_count, "points": 列表}
    设 src = 解析JSON []
    如果 {point_code} 不为空
      设 p = 调用 kg.取知识点 code={point_code} subject={sid}
      如果 {p} 为空
        报错 404 没有这个知识点
      结束
      设 it0 = {"code": "{p.code}", "title": "{p.title}"}
      设 src = 列表加项 {src} {it0}
    否则
      设 lst = 调用 kg.列知识点 subject={sid}
      设 src = {lst.points}
    结束
    设 pts = 解析JSON []
    设 mcnt = 0
    设 ucnt = 0
    遍历 pt 于 {src}
      设 mrow = 查一行 app.db progress_mastery_get learner={learner} point_code={pt.code} subject_id={sid}
      设 right = {mrow.right_count 或 0}
      设 tot = {mrow.total_count 或 0}
      设 ms = {mrow.mastered 或 0}
      设 sc = 查一行 app.db progress_score_latest learner={learner} point_code={pt.code} subject_id={sid}
      设 score = {sc.score 或 0}
      设 pre = 调用 kg.列前置 code={pt.code} subject={sid}
      设 un = 1
      遍历 q 于 {pre.points}
        设 qm = 查一行 app.db progress_mastery_get learner={learner} point_code={q.code} subject_id={sid}
        设 qv = {qm.mastered 或 0}
        如果 {qv} 不等于 1
          设 un = 0
        结束
      结束
      如果 {ms} 等于 1
        设 mcnt = 计算 {mcnt} + 1
      结束
      如果 {un} 等于 1
        设 ucnt = 计算 {ucnt} + 1
      结束
      设 item = {"code": "{pt.code}", "title": "{pt.title}", "right": {right}, "total": {tot}, "mastered": {ms}, "score": {score}, "unlocked": {un}}
      设 pts = 列表加项 {pts} {item}
    结束
    设 cnt = 列表长度 {pts}
    返回 {"learner": "{learner}", "total": {cnt}, "mastered_count": {mcnt}, "unlocked_count": {ucnt}, "points": {pts}}
  结束

  公开 函数 算下一步 learner current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, total, next_code, points}；points 是现在能学的知识点 [{code, title}]（前置都已掌握、自己还没掌握），按知识点 id 升序；next_code 是第一个的编号，没有则为空串
    # 调用 取状态 learner=learner
    # 从其 points 里留下 unlocked=1 且 mastered=0 的点，只取 code、title
    # 返回 {"learner": learner, "total": 个数, "next_code": 第一个的 code 或空串, "points": 列表}
    设 st = 调用 取状态 learner={learner} subject={sid}
    设 out = 解析JSON []
    设 nxt = {nxt 或}
    遍历 pt 于 {st.points}
      如果 {pt.unlocked} 等于 1 且 {pt.mastered} 等于 0
        设 item = {"code": "{pt.code}", "title": "{pt.title}"}
        设 out = 列表加项 {out} {item}
        如果 {nxt} 为空
          设 nxt = {pt.code}
        结束
      结束
    结束
    设 cnt = 列表长度 {out}
    返回 {"learner": "{learner}", "total": {cnt}, "next_code": "{nxt}", "points": {out}}
  结束

  公开 函数 取概览 learner current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, point_total, mastered_count, answer_total, right_total, accuracy, is_empty, hint}；accuracy 是累计正确率百分比（四舍五入取整，没有作答为 0）；is_empty 为 1 表示一道都没答过，此时 hint 为「还没有作答，先去做题吧」，否则 hint 为空串
    # 调用 kg.列知识点 取 point_total
    # 统计 progress_mastery 中该 learner 且 mastered=1 的行数为 mastered_count
    # 统计 progress_answer 中该 learner 的行数为 answer_total、correct=1 的行数为 right_total
    # accuracy = 四舍五入(right_total * 100 / answer_total)，answer_total 为 0 时为 0
    # answer_total 为 0 则 is_empty=1 且 hint 如上，否则 is_empty=0、hint 为空串
    # 返回上述对象
    设 lst = 调用 kg.列知识点 subject={sid}
    设 mcnt = 查一值 app.db progress_mastered_count learner={learner} subject_id={sid}
    设 at_ = 查一值 app.db progress_answer_count learner={learner} subject_id={sid}
    设 rt = 查一值 app.db progress_answer_right learner={learner} subject_id={sid}
    设 acc = 0
    设 empty = 1
    设 hint = 还没有作答，先去做题吧
    如果 {at_} 大于 0
      设 acc = 计算 四舍五入({rt} * 100 / {at_})
      设 empty = 0
      设 hint = {zz 或}
    结束
    返回 {"learner": "{learner}", "point_total": {lst.total}, "mastered_count": {mcnt}, "answer_total": {at_}, "right_total": {rt}, "accuracy": {acc}, "is_empty": {empty}, "hint": "{hint}"}
  结束

  公开 函数 列得分 learner current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, total, scores}；scores 是 [{point_code, title, score, prev_score, delta}]，每个有过得分的知识点一行；score 是当前分（最新一行），prev_score 是上一行得分，没有上一行时等于 score，delta = score - prev_score；按 score 升序（分低的在前）、point_code 升序
    # 查 progress_score 中该 learner 的全部行，按 point_code 分组，各取 id 最大的两行
    # 对每组计算 score、prev_score、delta；调用 kg.取知识点 取 title，取不到 title 取空串
    # 排序后返回 {"learner": learner, "total": 组数, "scores": 列表}
    设 rows = 查询 app.db progress_scores_list learner={learner} subject_id={sid}
    设 out = 解析JSON []
    遍历 row 于 {rows}
      设 tp = 调用 kg.取知识点 code={row.point_code} subject={sid}
      设 title = {tp.title 或}
      设 delta = 计算 {row.score} - {row.prev_score}
      设 item = {"point_code": "{row.point_code}", "title": "{title}", "score": {row.score}, "prev_score": {row.prev_score}, "delta": {delta}}
      设 out = 列表加项 {out} {item}
    结束
    设 cnt = 列表长度 {out}
    返回 {"learner": "{learner}", "total": {cnt}, "scores": {out}}
  结束

  公开 函数 列最近作答 learner limit? current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, total, answers}；answers 是 [{point_code, question_no, correct, answer, at}]，按 id 降序，最多 limit 条（默认 20）
    # 报错 400 limit 不合法
    # limit 为空取 20；不是大于等于 1 的整数，报错 400 limit 不合法
    # 查 progress_answer 中该 learner 的行，按 id 降序取前 limit 条
    # 返回 {"learner": learner, "total": 条数, "answers": 列表}
    设 lim = {limit 或 20}
    设 ml = 匹配 {lim} ^[1-9]\d*$
    如果 {ml.matched} 不等于 是
      报错 400 limit 不合法
    结束
    设 rows = 查询 app.db progress_recent_list learner={learner} limit={lim} subject_id={sid}
    设 cnt = 列表长度 {rows}
    返回 {"learner": "{learner}", "total": {cnt}, "answers": {rows}}
  结束

  公开 函数 按级统计掌握 learner current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, covered_count, levels}；levels 恒为 5 项、顺序 N5 N4 N3 N2 N1 的 [{level, mastered, total}]；total 是该等级下的知识点数，mastered 是其中该学习者已掌握的个数；covered_count 是有等级的知识点总数
    # 调用 kg.列知识点 取全部点
    # 对每个点调用 lesson.取知识点等级 point_code=该点编号；level 为空串的点不计入任何等级
    # 按等级累计 total；读 progress_mastery 该 learner 该点 mastered=1 的累计进 mastered
    # 返回 {"learner": learner, "covered_count": 有等级的点数, "levels": 5 项列表}
    设 lst = 调用 kg.列知识点 subject={sid}
    设 sl = 调用 subject.科目等级 subject_id={sid}
    设 pl = 解析JSON []
    遍历 pt 于 {lst.points}
      设 lv = 调用 lesson.取知识点等级 point_code={pt.code} subject={sid}
      如果 {lv.level} 不为空
        设 mm = 查一行 app.db progress_mastery_get learner={learner} point_code={pt.code} subject_id={sid}
        设 mv = {mm.mastered 或 0}
        设 ent = {"level": "{lv.level}", "mv": {mv}}
        设 pl = 列表加项 {pl} {ent}
      结束
    结束
    设 covered = 0
    设 outl = 解析JSON []
    遍历 ln 于 {sl.levels}
      设 tt = 0
      设 mt = 0
      遍历 e 于 {pl}
        如果 {e.level} 等于 {ln}
          设 tt = 计算 {tt} + 1
          设 mt = 计算 {mt} + {e.mv}
        结束
      结束
      设 covered = 计算 {covered} + {tt}
      设 item = {"level": "{ln}", "mastered": {mt}, "total": {tt}}
      设 outl = 列表加项 {outl} {item}
    结束
    设 lcnt = 列表长度 {outl}
    返回 {"learner": "{learner}", "covered_count": {covered}, "level_count": {lcnt}, "levels": {outl}}
  结束

  公开 函数 重建全部得分 pass_line? fall_line?
    # 返回 {ok, pairs, changed}；pairs 是处理的 (学习者, 知识点) 对数，changed 是新记了得分行的对数
    # 报错 400 分数线不合法
    # 调用 核对分数线 pass_line=pass_line fall_line=fall_line
    # 在一个事务里：
    # 取 progress_answer 中全部不同的 (learner, point_code)
    # 每对：若 progress_mastery 没有该行，按 progress_answer 统计 right_count、total_count 插入 (mastered=0, updated_at=当前时间)
    # 每对：调用 重算点 learner point_code 两条线（只新增得分行、更新掌握标记，不删除旧得分行，不改作答流水）
    # 累计 pairs 和 changed
    # 返回 {"ok": 1, "pairs": pairs, "changed": changed}
    设 lines = 调用 核对分数线 pass_line={pass_line} fall_line={fall_line}
    设 pairs = 0
    设 changed = 0
    事务 app.db
      设 prs = 查询 app.db progress_pairs
      遍历 pr 于 {prs}
        设 now = 当前时间
        设 mrow = 查一行 app.db progress_mastery_get learner={pr.learner} point_code={pr.point_code} subject_id={pr.subject_id}
        如果 {mrow} 为空
          设 w1 = 写库 app.db progress_mastery_rebuild_insert learner={pr.learner} point_code={pr.point_code} at={now} subject_id={pr.subject_id}
        结束
        设 res = 调用 重算点 learner={pr.learner} point_code={pr.point_code} pass_line={lines.pass_line} fall_line={lines.fall_line} subject_id={pr.subject_id}
        设 pairs = 计算 {pairs} + 1
        设 changed = 计算 {changed} + {res.changed}
      结束
    结束
    返回 {"ok": 1, "pairs": {pairs}, "changed": {changed}}
  结束

  公开 函数 列低分点 learner below? limit? current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, total, points}；points 是 [{point_code, title, score}]，取每个点最新得分严格小于 below（默认 80）的点，按 score 升序、point_code 升序，最多 limit 个（默认 10）
    # 报错 400 参数不合法
    # below 为空取 80，limit 为空取 10；below 不是 0 到 100 的整数或 limit 不是大于等于 1 的整数，报错 400 参数不合法
    # 取该 learner 在 progress_score 里每个知识点 id 最大的那一行
    # 留下 score 小于 below 的，调用 kg.取知识点 取 title（取不到取空串），排序后取前 limit 个
    # 返回 {"learner": learner, "total": 个数, "points": 列表}
    设 b = {below 或 80}
    设 l = {limit 或 10}
    设 mb = 匹配 {b} ^\d+$
    设 ml = 匹配 {l} ^[1-9]\d*$
    如果 {mb.matched} 不等于 是 或 {ml.matched} 不等于 是
      报错 400 参数不合法
    结束
    设 bn = 转数字 {b}
    如果 {bn} 大于 100
      报错 400 参数不合法
    结束
    设 rows = 查询 app.db progress_low_list learner={learner} below={b} limit={l} subject_id={sid}
    设 out = 解析JSON []
    遍历 row 于 {rows}
      设 tp = 调用 kg.取知识点 code={row.point_code} subject={sid}
      设 title = {tp.title 或}
      设 item = {"point_code": "{row.point_code}", "title": "{title}", "score": {row.score}}
      设 out = 列表加项 {out} {item}
    结束
    设 cnt = 列表长度 {out}
    返回 {"learner": "{learner}", "total": {cnt}, "points": {out}}
  结束

  公开 函数 列错题 learner limit? current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, total, wrongs}；wrongs 是 [{point_code, question_no, answer, at, score, mastered}]，该学习者 correct=0 的作答按 id 降序，最多 limit 条（默认 10）；score 是该点最新得分（没有为 0），mastered 是该点掌握标记（没有为 0）
    # 报错 400 limit 不合法
    # limit 为空取 10；不是大于等于 1 的整数，报错 400 limit 不合法
    # 查 progress_answer 中该 learner 且 correct=0 的行，按 id 降序取前 limit 条
    # 每行读 progress_score 该点最新一行的 score，progress_mastery 该点的 mastered
    # 返回 {"learner": learner, "total": 条数, "wrongs": 列表}
    设 lim = {limit 或 10}
    设 ml = 匹配 {lim} ^[1-9]\d*$
    如果 {ml.matched} 不等于 是
      报错 400 limit 不合法
    结束
    设 rows = 查询 app.db progress_wrongs learner={learner} limit={lim} subject_id={sid}
    设 cnt = 列表长度 {rows}
    返回 {"learner": "{learner}", "total": {cnt}, "wrongs": {rows}}
  结束

  公开 函数 列久未做已掌握点 learner days? limit? current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, total, points}；points 是 [{point_code, title, last_at}]，是 mastered=1 且该点最后一次作答日期早于（当前日期 - days 天）的点，last_at 为该点最后一次作答的 at，按 last_at 升序（最久的在前），最多 limit 个（默认 10）
    # 报错 400 参数不合法
    # days 为空取 7，limit 为空取 10；days 不是大于等于 0 的整数或 limit 不是大于等于 1 的整数，报错 400 参数不合法
    # 查 progress_mastery 中该 learner 且 mastered=1 的行
    # 每行取 progress_answer 该 learner + point_code 中 id 最大一行的 at 为 last_at；没有作答行的点跳过
    # last_at 的前 10 个字符（日期）小于 当前日期 2026-01-01 减 days 天 的日期才保留
    # 调用 kg.取知识点 取 title（取不到取空串），按 last_at 升序取前 limit 个
    # 返回 {"learner": learner, "total": 个数, "points": 列表}
    设 dy = {days 或 7}
    设 l = {limit 或 10}
    设 md = 匹配 {dy} ^\d+$
    设 ml = 匹配 {l} ^[1-9]\d*$
    如果 {md.matched} 不等于 是 或 {ml.matched} 不等于 是
      报错 400 参数不合法
    结束
    设 today = 当前时间 日期
    设 cutoff = 查一值 app.db progress_cutoff today={today} days={dy}
    设 rows = 查询 app.db progress_stale learner={learner} cutoff={cutoff} limit={l} subject_id={sid}
    设 out = 解析JSON []
    遍历 row 于 {rows}
      设 tp = 调用 kg.取知识点 code={row.point_code} subject={sid}
      设 title = {tp.title 或}
      设 item = {"point_code": "{row.point_code}", "title": "{title}", "last_at": "{row.last_at}"}
      设 out = 列表加项 {out} {item}
    结束
    设 cnt = 列表长度 {out}
    返回 {"learner": "{learner}", "total": {cnt}, "points": {out}}
  结束

  公开 函数 取区间作答 learner start_id end_id? current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    # 返回 {learner, start_id, max_id, total, answers}；answers 是该学习者作答流水中 id 大于 start_id（且 end_id 不为空时 id 不大于 end_id）的行 [{id, point_code, question_no, correct, answer, at}]，按 id 升序；max_id 是该学习者当前最大的作答 id（没有作答为 0），可用来当「这一轮起点」
    # 报错 400 start_id 不合法
    # start_id 不是大于等于 0 的整数，报错 400 start_id 不合法；end_id 不为空且不是整数，同样报错 400 start_id 不合法
    # 查 progress_answer 中该 learner 且 id 大于 start_id（end_id 不为空时再加 id 不大于 end_id）的行，按 id 升序
    # max_id 取该 learner 在 progress_answer 里最大的 id，没有为 0
    # 返回 {"learner": learner, "start_id": start_id, "max_id": max_id, "total": 行数, "answers": 列表}
    设 ms = 匹配 {start_id} ^\d+$
    如果 {ms.matched} 不等于 是
      报错 400 start_id 不合法
    结束
    如果 {end_id} 不为空
      设 me = 匹配 {end_id} ^-?\d+$
      如果 {me.matched} 不等于 是
        报错 400 start_id 不合法
      结束
    结束
    设 rows = 查询 app.db progress_range learner={learner} start_id={start_id} end_id={end_id} subject_id={sid}
    设 mx = 查一值 app.db progress_maxid learner={learner} subject_id={sid}
    设 cnt = 列表长度 {rows}
    返回 {"learner": "{learner}", "start_id": {start_id}, "max_id": {mx}, "total": {cnt}, "answers": {rows}}
  结束

  公开 函数 统计作答 learner? current_role? auth_mode? subject? student?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有老师可以查看作答统计
    结束
    设 lr = {zz 或}
    如果 {auth_mode} 等于 on
      设 lr = {learner}
    结束
    设 s0 = 调用 本科目 learner={lr} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    设 flt = {student 或}
    如果 {flt} 为空 且 {auth_mode} 不等于 on
      设 flt = {learner}
    结束
    # 返回 {total, learners}；learners 是 [{learner, answer_count, last_at}]，每个有过作答的学习者一行，last_at 是其最后一次作答的 at；learner 不为空时只返回该学习者；按 learner 升序
    # 查 progress_answer，按 learner 分组统计行数 answer_count，last_at 取该组 id 最大一行的 at
    # learner 不为空时只留该学习者
    # 返回 {"total": 学习者数, "learners": 列表}
    设 rows = 查询 app.db progress_stats learner={flt} subject_id={sid}
    设 cnt = 列表长度 {rows}
    返回 {"total": {cnt}, "learners": {rows}}
  结束

  公开 函数 按天统计作答 days? week? student? learner? current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有老师可以查看作答统计
    结束
    设 lr = {zz 或}
    如果 {auth_mode} 等于 on
      设 lr = {learner}
    结束
    设 s0 = 调用 本科目 learner={lr} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    设 dy = {days 或 28}
    设 md = 匹配 {dy} ^\d+$
    如果 {md.matched} 不等于 是
      报错 400 days 不合法
    结束
    设 dn = 转数字 {dy}
    如果 {dn} 小于 1 或 {dn} 大于 90
      报错 400 days 不合法
    结束
    设 back = 计算 {dn} - 1
    设 today = 当前时间 日期
    设 since = 查一值 app.db progress_cutoff today={today} days={back}
    设 wk = {week 或 0}
    设 st = {student 或}
    设 rows = 查询 app.db progress_daily since={since} week={wk} student={st} subject_id={sid}
    设 cnt = 列表长度 {rows}
    返回 {"days": {dn}, "since": "{since}", "total": {cnt}, "rows": {rows}}
  结束

  函数 取点级映射 subject_id
    设 lst = 调用 kg.列知识点 subject={subject_id}
    设 out = 解析JSON []
    遍历 pt 于 {lst.points}
      设 lv = 调用 lesson.取知识点等级 point_code={pt.code} subject={subject_id}
      如果 {lv.level} 不为空
        设 item = {"code": "{pt.code}", "level": "{lv.level}"}
        设 out = 列表加项 {out} {item}
      结束
    结束
    返回 {"items": {out}}
  结束

  函数 得分视图 learner subject_id
    设 rows = 查询 app.db progress_score_view learner={learner} subject_id={subject_id}
    返回 {"rows": {rows}}
  结束

  公开 函数 进度页面 learner current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    如果 {learner} 为空
      报错 400 learner 不能为空
    结束
    设 lg = 调用 subject.取界面语言 username={learner}
    设 lang = {lg.lang 或 zh}
    设 ov = 调用 取概览 learner={learner} subject={sid}
    设 vw = 调用 得分视图 learner={learner} subject_id={sid}
    设 w1 = 已掌握
    设 w2 = 累计答题
    设 w3 = 正确率
    设 w4 = 平均得分
    设 w1b = 总知识点
    如果 {lang} 等于 ja
      设 w1 = 習得済み
      设 w2 = 累計解答
      设 w3 = 正答率
      设 w4 = 平均スコア
      设 w1b = 全知識ポイント
    结束
    设 head = {w1} {ov.mastered_count} / {w1b} {ov.point_total}
    设 answers_text = {w2} {ov.answer_total}
    设 rate_text = {w3} —
    设 review_link = {review_link 或}
    设 qlink = #%E5%81%9A%E9%A2%98
    如果 {ov.answer_total} 大于 0
      设 rate_text = {w3} {ov.accuracy}%
      设 review_link = #%E5%81%9A%E9%A2%98?mode=review
    结束
    设 ssum = 0
    设 scnt = 0
    遍历 vr 于 {vw.rows}
      设 ssum = 计算 {ssum} + {vr.score}
      设 scnt = 计算 {scnt} + 1
    结束
    设 score_text = {w4} —
    如果 {scnt} 大于 0
      设 avg = 计算 四舍五入({ssum} / {scnt})
      设 score_text = {w4} {avg}
    结束
    设 prog = {"head": "{head}", "answers_text": "{answers_text}", "rate_text": "{rate_text}", "score_text": "{score_text}", "empty": {ov.is_empty}, "quiz_link": "{qlink}", "review_link": "{review_link}"}
    设 doing = 解析JSON []
    设 wd = 达标（得分
    设 wf = 得分
    设 wnone = 还没打分
    设 wc1 = ，
    设 wg1 = 差
    设 wg2 = 分
    如果 {lang} 等于 ja
      设 wd = 達成（スコア
      设 wf = スコア
      设 wnone = まだ採点されていません
      设 wc1 = 、
      设 wg1 = あと
      设 wg2 = 点
    结束
    设 drows = 查询 app.db progress_doing_rows learner={learner} subject_id={sid}
    遍历 dr 于 {drows}
      设 tp = 调用 kg.取知识点 code={dr.point_code} subject={sid}
      设 dtitle = {tp.title 或}
      如果 {lang} 等于 ja
        设 tr = 调用 subject.译文 tbl=kg_point row_key={dr.point_code} field=title lang=ja
        如果 {tr.text} 不为空
          设 dtitle = {tr.text}
        结束
      结束
      设 sc = 查一行 app.db progress_score_latest learner={learner} point_code={dr.point_code} subject_id={sid}
      设 verdict = {wnone}
      如果 {sc} 不为空
        设 okf = 0
        如果 {sc.score} 不小于 80
          设 okf = 1
        结束
        如果 {dr.mastered} 等于 1 且 {sc.score} 不小于 60
          设 okf = 1
        结束
        如果 {okf} 等于 1
          设 verdict = {wd} {sc.score}）
        否则
          设 gap = 计算 80 - {sc.score}
          设 verdict = {wf} {sc.score}{wc1}{wg1} {gap} {wg2}
        结束
      结束
      设 item = {"label": "{dtitle}", "tally": "{dr.right_count}/{dr.total_count}", "verdict": "{verdict}"}
      设 doing = 列表加项 {doing} {item}
    结束
    设 nx = 调用 算下一步 learner={learner} subject={sid}
    设 ly = 调用 kg.列分层 subject={sid}
    设 nxt = 解析JSON []
    设 nc = 0
    遍历 np 于 {nx.points}
      如果 {nc} 不小于 20
        跳出
      结束
      设 nc = 计算 {nc} + 1
      设 dep = 0
      遍历 lay 于 {ly.layers}
        遍历 lp 于 {lay.points}
          如果 {lp.code} 等于 {np.code}
            设 dep = {lay.depth}
          结束
        结束
      结束
      设 ntitle = {np.title}
      如果 {lang} 等于 ja
        设 tr = 调用 subject.译文 tbl=kg_point row_key={np.code} field=title lang=ja
        如果 {tr.text} 不为空
          设 ntitle = {tr.text}
        结束
      结束
      设 item = {"label": "{ntitle}", "depth": {dep}}
      设 nxt = 列表加项 {nxt} {item}
    结束
    设 rc = 调用 列最近作答 learner={learner} limit=20 subject={sid}
    设 rec = 解析JSON []
    遍历 ra 于 {rc.answers}
      设 tp = 调用 kg.取知识点 code={ra.point_code} subject={sid}
      设 rtitle = {tp.title 或}
      如果 {rtitle} 为空
        设 rtitle = {ra.point_code}
      结束
      如果 {lang} 等于 ja
        设 tr = 调用 subject.译文 tbl=kg_point row_key={ra.point_code} field=title lang=ja
        如果 {tr.text} 不为空
          设 rtitle = {tr.text}
        结束
      结束
      设 res_t = 错
      设 res_ok = 对
      如果 {lang} 等于 ja
        设 res_t = 不正解
        设 res_ok = 正解
      结束
      如果 {ra.correct} 等于 1
        设 res_t = {res_ok}
      结束
      设 item = {"at": "{ra.at}", "label": "{rtitle}", "item_label": "", "result": "{res_t}"}
      设 rec = 列表加项 {rec} {item}
    结束
    设 lv = 调用 按级统计掌握 learner={learner} subject={sid}
    设 mp = 调用 取点级映射 subject_id={sid}
    设 acl = 解析JSON []
    遍历 mi 于 {mp.items}
      设 ac = 查一值 app.db progress_answer_point_count learner={learner} point_code={mi.code} subject_id={sid}
      设 acn = {"level": "{mi.level}", "ac": {ac}}
      设 acl = 列表加项 {acl} {acn}
    结束
    设 lvs = 解析JSON []
    遍历 lr 于 {lv.levels}
      设 an = 0
      遍历 ae 于 {acl}
        如果 {ae.level} 等于 {lr.level}
          设 an = 计算 {an} + {ae.ac}
        结束
      结束
      设 item = {"level": "{lr.level}", "tally": "{lr.mastered}/{lr.total}", "answers": {an}}
      设 lvs = 列表加项 {lvs} {item}
    结束
    设 scs = 解析JSON []
    遍历 vr2 于 {vw.rows}
      设 tp = 调用 kg.取知识点 code={vr2.point_code} subject={sid}
      设 stitle = {tp.title 或}
      如果 {lang} 等于 ja
        设 tr = 调用 subject.译文 tbl=kg_point row_key={vr2.point_code} field=title lang=ja
        如果 {tr.text} 不为空
          设 stitle = {tr.text}
        结束
      结束
      设 dl = 首次
      如果 {lang} 等于 ja
        设 dl = 初回
      结束
      如果 {vr2.n} 大于 1
        设 df = 计算 {vr2.score} - {vr2.prev_score}
        如果 {df} 大于 0
          设 dl = +{df}
        否则如果 {df} 小于 0
          设 ab = 计算 绝对值({df})
          设 dl = −{ab}
        否则
          设 dl = ±0
        结束
      结束
      设 item = {"label": "{stitle}", "value": {vr2.score}, "delta": "{dl}", "at": "{vr2.at}"}
      设 scs = 列表加项 {scs} {item}
    结束
    设 d = 调用 dictation.取默写概况 learner={learner} subject={sid}
    设 words = 查一值 app.db progress_dict_words learner={learner} subject_id={sid}
    设 w5 = 练过
    设 drate = —
    如果 {d.total} 大于 0
      设 drate = {d.accuracy}%
    结束
    设 dtext = {w5} {words} 个词，默写 {d.total} 次，正确率 {drate}，错词本 {d.wrong_book_count} 个
    如果 {lang} 等于 ja
      设 w5 = 練習した単語
      设 dtext = {w5} {words} 個、書き取り {d.total} 回、正答率 {drate}、間違えた単語帳 {d.wrong_book_count} 個
    结束
    设 dlink = #%E9%BB%98%E5%86%99
    如果 {d.wrong_book_count} 大于 0
      设 dlink = #%E9%BB%98%E5%86%99?source=review
    结束
    返回 {"prog": {prog}, "doing": {doing}, "next": {nxt}, "recent": {rec}, "levels": {lvs}, "scores": {scs}, "dictation": {"text": "{dtext}", "link": "{dlink}"}}
  结束

  公开 函数 图谱页面 learner current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    设 lg = 调用 subject.取界面语言 username={learner}
    设 lang = {lg.lang 或 zh}
    设 st = 调用 取状态 learner={learner} subject={sid}
    设 nodes = 解析JSON []
    遍历 pt 于 {st.points}
      设 ds = 调用 kg.列后代 code={pt.code} subject={sid}
      设 pr = 调用 kg.列前置 code={pt.code} subject={sid}
      设 desc = {zz 或}
      遍历 q 于 {pr.points}
        设 qt = {q.title}
        如果 {lang} 等于 ja
          设 tr = 调用 subject.译文 tbl=kg_point row_key={q.code} field=title lang=ja
          如果 {tr.text} 不为空
            设 qt = {tr.text}
          结束
        结束
        如果 {desc} 为空
          设 desc = {qt}
        否则
          设 desc = {desc}、{qt}
        结束
      结束
      如果 {desc} 为空
        设 desc = （起点）
      结束
      设 stv = locked
      如果 {pt.mastered} 等于 1
        设 stv = done
      否则如果 {pt.unlocked} 等于 1
        设 stv = open
      结束
      设 ptitle = {pt.title}
      如果 {lang} 等于 ja
        设 tr = 调用 subject.译文 tbl=kg_point row_key={pt.code} field=title lang=ja
        如果 {tr.text} 不为空
          设 ptitle = {tr.text}
        结束
      结束
      设 item = {"id": "{pt.code}", "code": "{pt.code}", "label": "{ptitle}", "state": "{stv}", "badge": {ds.total}, "desc": "{desc}"}
      设 nodes = 列表加项 {nodes} {item}
    结束
    设 edges = 解析JSON []
    设 erows = 查询 app.db progress_edge_list subject_id={sid}
    遍历 er 于 {erows}
      设 item = {"from": "{er.pre_code}", "to": "{er.point_code}", "kind": ""}
      设 edges = 列表加项 {edges} {item}
    结束
    设 crows = 查询 app.db progress_contrast_list subject_id={sid}
    遍历 cr 于 {crows}
      设 item = {"from": "{cr.a_code}", "to": "{cr.b_code}", "kind": "对照"}
      设 edges = 列表加项 {edges} {item}
    结束
    设 ncnt = 列表长度 {nodes}
    设 ecnt = 列表长度 {edges}
    返回 {"graph": {"nodes": {nodes}, "edges": {edges}}, "node_count": {ncnt}, "edge_count": {ecnt}}
  结束

  公开 函数 知识点页面 learner code current_role? auth_mode? subject?
    设 s0 = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {s0.subject_id}
    如果 {code} 为空
      报错 400 code 不能为空
    结束
    设 kp = 调用 kg.取知识点 code={code} subject={sid}
    如果 {kp} 为空
      报错 404 没有这个知识点
    结束
    设 lg = 调用 subject.取界面语言 username={learner}
    设 lang = {lg.lang 或 zh}
    设 st = 调用 取状态 learner={learner} point_code={code} subject={sid}
    设 w6 = 答对
    设 nt = 还没做过
    设 w7 = 答题
    设 w8 = （已掌握）
    如果 {lang} 等于 ja
      设 w6 = 正解
      设 w7 = 解答
      设 w8 = （習得済み）
      设 nt = まだ解いていません
    结束
    遍历 pt 于 {st.points}
      如果 {pt.total} 大于 0
        设 nt = {w6} {pt.right} / {w7} {pt.total}
        如果 {pt.mastered} 等于 1
          设 nt = {nt}{w8}
        结束
      结束
    结束
    设 ns = {ns 或}
    设 sc = 查一行 app.db progress_score_latest learner={learner} point_code={code} subject_id={sid}
    如果 {sc} 不为空
      设 ns = {sc.score}
    结束
    设 its = 调用 kg.按知识点列条目 point_code={code} subject={sid}
    设 items = 解析JSON []
    遍历 x 于 {its.items}
      设 xname = {x.name}
      如果 {lang} 等于 ja
        设 tr = 调用 subject.译文 tbl=kg_item row_key={x.code} field=name lang=ja
        如果 {tr.text} 不为空
          设 xname = {tr.text}
        结束
      结束
      设 item = {"label": "{xname}", "form": "{x.after_form 或}"}
      设 items = 列表加项 {items} {item}
    结束
    设 all = 调用 kg.列条目 subject={sid}
    设 forms = 解析JSON []
    遍历 y 于 {all.items}
      如果 {y.after_form} 等于 {code}
        设 yp = 调用 kg.取知识点 code={y.point_code} subject={sid}
        设 ytitle = {yp.title 或}
        设 yname = {y.name}
        如果 {lang} 等于 ja
          设 tr = 调用 subject.译文 tbl=kg_item row_key={y.code} field=name lang=ja
          如果 {tr.text} 不为空
            设 yname = {tr.text}
          结束
          设 tr2 = 调用 subject.译文 tbl=kg_point row_key={y.point_code} field=title lang=ja
          如果 {tr2.text} 不为空
            设 ytitle = {tr2.text}
          结束
        结束
        设 item = {"label": "{yname}", "point": "{ytitle}"}
        设 forms = 列表加项 {forms} {item}
      结束
    结束
    设 vw = 调用 vocab.按知识点列单词 point_code={code} subject={sid}
    设 pw = 解析JSON []
    设 wc = 0
    遍历 w 于 {vw.words}
      如果 {wc} 不小于 200
        跳出
      结束
      设 wc = 计算 {wc} + 1
      设 item = {"kanji": "{w.kanji 或}", "kana": "{w.kana 或}", "meaning": "{w.meaning 或}"}
      设 pw = 列表加项 {pw} {item}
    结束
    返回 {"node_tally": "{nt}", "node_score": "{ns}", "items": {items}, "forms": {forms}, "point_words": {pw}}
  结束

结束
