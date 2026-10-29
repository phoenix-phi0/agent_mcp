业务 teacher_assist
  依赖 assist_common assist_draft report progress kg lesson subject
  用包 db common text

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {r}
  结束

  函数 取最近对话 current_user limit subject_id
    设 blank = {zz 或}
    设 nl = 查一值 app.db teacher_assist_nl
    设 rows = 查询 app.db teacher_assist_recent teacher={current_user} n={limit} subject_id={subject_id}
    设 out = {blank}
    遍历 m 于 {rows}
      如果 {m.role} 等于 assistant
        设 line = 助手：{m.content}
      否则
        设 line = 老师：{m.content}
      结束
      如果 {out} 为空
        设 out = {line}
      否则
        设 out = {out}{nl}{line}
      结束
    结束
    返回 {out}
  结束

  函数 取上轮聚焦 current_user subject_id
    设 blank = {zz 或}
    设 row = 查一行 app.db teacher_assist_last_focus teacher={current_user} subject_id={subject_id}
    设 st = {row.student 或}
    设 pt = {row.point 或}
    设 sname = {blank}
    设 ptitle = {blank}
    如果 {st} 不为空
      设 r = 调用 学生范围 subject_id={subject_id}
      遍历 s 于 {r}
        如果 {s.username} 等于 {st}
          设 sname = {s.display_name}
        结束
      结束
    结束
    如果 {pt} 不为空
      设 p = 调用 kg.取知识点 code={pt} subject={subject_id}
      设 ptitle = {p.title 或}
    结束
    返回 {"student": "{st}", "student_name": "{sname}", "point": "{pt}", "point_title": "{ptitle}"}
  结束

  函数 班级上下文 current_user subject_id
    设 blank = {zz 或}
    设 nl = 查一值 app.db teacher_assist_nl
    设 today = 当前时间 日期
    设 r = 调用 report.取全班学情 sort_by=avg_score subject={subject_id}
    如果 {r.total} 等于 0
      设 out0 = 今天：{today}{nl}还没有学生账号
      返回 {out0}
    结束
    设 m = 0
    设 k = 0
    设 un = {blank}
    设 ui = 0
    遍历 s 于 {r.students}
      如果 {s.answer_total} 大于 0
        设 m = 计算 {m} + 1
      否则
        设 k = 计算 {k} + 1
        如果 {ui} 小于 10
          如果 {un} 为空
            设 un = {s.display_name}（{s.username}）
          否则
            设 un = {un}、{s.display_name}（{s.username}）
          结束
        结束
        设 ui = 计算 {ui} + 1
      结束
    结束
    设 tail = {blank}
    如果 {k} 大于 0
      设 tail = 还没作答：{un}
      如果 {k} 大于 10
        设 more = 计算 {k} - 10
        设 tail = {tail}等 {more} 人
      结束
    结束
    设 wps = 全班薄弱知识点：
    设 wi = 0
    遍历 w 于 {r.weak_points}
      如果 {wi} 小于 5
        设 wps = {wps}{nl}{w.title}（{w.level}）｜{w.student_count} 人低于 80 分｜这些人平均 {w.avg_score} 分
      结束
      设 wi = 计算 {wi} + 1
    结束
    如果 {tail} 为空
      设 tail = {wps}
    否则
      设 tail = {tail}{nl}{wps}
    结束
    设 lim = 30
    如果 {m} 大于 30
      设 lim = 20
    结束
    设 head = 今天：{today}{nl}全班 {r.total} 人，有作答的 {m} 人，还没作答的 {k} 人
    设 hl = 查一值 app.db teacher_assist_len t={head}
    设 tl = 查一值 app.db teacher_assist_len t={tail}
    设 budget = 计算 2500 - {hl} - {tl} - 20
    设 rows = {blank}
    设 shown = 0
    设 cut = 0
    遍历 s 于 {r.students}
      如果 {s.answer_total} 大于 0 且 {shown} 小于 {lim} 且 {cut} 等于 0
        设 wt = {blank}
        设 wn = 0
        遍历 w 于 {s.weak_points}
          如果 {wn} 小于 2
            如果 {wt} 为空
              设 wt = {w.title}
            否则
              设 wt = {wt}、{w.title}
            结束
          结束
          设 wn = 计算 {wn} + 1
        结束
        设 l10 = 查一值 app.db teacher_assist_substr t={s.last_at} n=10
        设 row = {s.display_name}（{s.username}）｜作答 {s.answer_total}｜近期正确率 {s.recent_accuracy}%｜平均分 {s.avg_score}｜已掌握 {s.mastered_count}｜低分点 {s.weak_count} 个（{wt}）｜最近学习 {l10}
        设 rl = 查一值 app.db teacher_assist_len t={row}
        设 used = 查一值 app.db teacher_assist_len t={rows}
        设 newlen = 计算 {used} + {rl} + 1
        如果 {newlen} 大于 {budget}
          设 cut = 1
        否则
          如果 {rows} 为空
            设 rows = {row}
          否则
            设 rows = {rows}{nl}{row}
          结束
          设 shown = 计算 {shown} + 1
        结束
      结束
    结束
    设 out = {head}
    如果 {rows} 不为空
      设 out = {out}{nl}{rows}
    结束
    如果 {m} 大于 30
      设 more2 = 计算 {m} - 20
      设 out = {out}{nl}另有 {more2} 人未列出
    结束
    如果 {cut} 等于 1
      设 out = {out}{nl}（表已截断）
    结束
    设 out = {out}{nl}{tail}
    返回 {out}
  结束

  函数 学生上下文 username display_name last_at subject_id
    设 blank = {zz 或}
    设 nl = 查一值 app.db teacher_assist_nl
    设 r = 调用 report.取学生学情 student={username} subject={subject_id}
    设 la = 没有作答
    如果 {last_at} 不为空
      设 la = 查一值 app.db teacher_assist_substr t={last_at} n=10
    结束
    设 out = 学生：{display_name}（{username}），状态 {r.status}，最近学习 {la}
    如果 {r.answer_total} 等于 0
      设 out = {out}{nl}还没有作答{nl}错词本 {r.wrong_book_count} 个{nl}问老师提问 {r.question_count} 次
      返回 {out}
    结束
    设 out = {out}{nl}作答 {r.answer_total} 题，近期正确率 {r.recent_accuracy}%，平均分 {r.avg_score}，已掌握 {r.mastered_count} 个知识点
    设 wl = {blank}
    设 i = 0
    遍历 x 于 {r.weak_points}
      如果 {i} 小于 5
        设 piece = {x.title}（{x.level}）得分 {x.score}
        如果 {wl} 为空
          设 wl = {piece}
        否则
          设 wl = {wl}；{piece}
        结束
      结束
      设 i = 计算 {i} + 1
    结束
    设 out = {out}{nl}低分点 {r.weak_count} 个，最低的 5 个：{wl}
    设 wa = {blank}
    设 i = 0
    遍历 x 于 {r.wrong_answers}
      如果 {i} 小于 5
        设 d10 = 查一值 app.db teacher_assist_substr t={x.at} n=10
        设 piece = {x.title} {d10}
        如果 {wa} 为空
          设 wa = {piece}
        否则
          设 wa = {wa}；{piece}
        结束
      结束
      设 i = 计算 {i} + 1
    结束
    设 out = {out}{nl}最近答错 {r.wrong_count} 题，最近 5 条：{wa}
    设 wb = {blank}
    设 i = 0
    遍历 x 于 {r.wrong_book}
      如果 {i} 小于 5
        设 piece = {x.kanji}【{x.kana}】{x.meaning}
        如果 {wb} 为空
          设 wb = {piece}
        否则
          设 wb = {wb}；{piece}
        结束
      结束
      设 i = 计算 {i} + 1
    结束
    设 out = {out}{nl}错词本 {r.wrong_book_count} 个，前 5 个：{wb}
    设 qs = {blank}
    设 i = 0
    遍历 x 于 {r.recent_questions}
      如果 {i} 小于 3 且 {x.content} 不为空
        设 piece = 查一值 app.db teacher_assist_substr t={x.content} n=40
        如果 {qs} 为空
          设 qs = {piece}
        否则
          设 qs = {qs}；{piece}
        结束
      结束
      设 i = 计算 {i} + 1
    结束
    设 out = {out}{nl}问老师提问 {r.question_count} 次，最近 3 条：{qs}
    设 unf = 0
    遍历 x 于 {r.relays}
      如果 {x.finished} 等于 0
        设 unf = 计算 {unf} + 1
      结束
    结束
    设 out = {out}{nl}未传达完的传达 {unf} 条
    如果 {r.has_summary} 等于 1
      设 sm = 查一值 app.db teacher_assist_substr t={r.summary} n=200
      设 out = {out}{nl}最近的 AI 学情总结（{r.summary_at}，{r.summary_author}）：{sm}
    结束
    设 ol = 查一值 app.db teacher_assist_len t={out}
    如果 {ol} 大于 1500
      设 out = 查一值 app.db teacher_assist_substr t={out} n=1500
    结束
    返回 {out}
  结束

  函数 知识点上下文 code title subject_id
    设 blank = {zz 或}
    设 nl = 查一值 app.db teacher_assist_nl
    设 lv = 调用 lesson.取知识点等级 point_code={code} subject={subject_id}
    设 level = {lv.level 或}
    设 its = 调用 kg.按知识点列条目 point_code={code} subject={subject_id}
    设 inames = {blank}
    设 i = 0
    遍历 x 于 {its.items}
      如果 {i} 小于 5
        如果 {inames} 为空
          设 inames = {x.name}
        否则
          设 inames = {inames}、{x.name}
        结束
      结束
      设 i = 计算 {i} + 1
    结束
    如果 {inames} 为空
      设 inames = 没有条目
    结束
    设 ls = 调用 lesson.按知识点列课文 point_code={code} subject={subject_id}
    设 lt = {blank}
    设 i = 0
    遍历 x 于 {ls.lessons}
      如果 {i} 小于 3
        设 piece = {x.code} {x.title}
        如果 {lt} 为空
          设 lt = {piece}
        否则
          设 lt = {lt}；{piece}
        结束
      结束
      设 i = 计算 {i} + 1
    结束
    如果 {lt} 为空
      设 lt = 没有课文
    结束
    设 out = 知识点：{title}（{code}），等级 {level}{nl}条目：{inames}{nl}相关课文：{lt}
    设 sl = 调用 学生范围 subject_id={subject_id}
    设 slt = 列表长度 {sl}
    如果 {slt} 等于 0
      设 out = {out}{nl}还没有学生账号
      返回 {out}
    结束
    设 a = 0
    设 b = 0
    设 c = 0
    设 attn = 0
    设 sum = 0
    设 items = {blank}
    设 nmast = {blank}
    设 mi = 0
    设 nun = {blank}
    设 ni = 0
    遍历 s 于 {sl}
      设 stt = 调用 progress.取状态 learner={s.username} point_code={code} subject={subject_id}
      设 rt = 0
      设 tt = 0
      设 ms = 0
      设 sc = 0
      遍历 pp 于 {stt.points}
        设 rt = {pp.right}
        设 tt = {pp.total}
        设 ms = {pp.mastered}
        设 sc = {pp.score}
      结束
      如果 {tt} 大于 0
        设 attn = 计算 {attn} + 1
        设 sum = 计算 {sum} + {sc}
      结束
      如果 {ms} 等于 1
        设 a = 计算 {a} + 1
        如果 {mi} 小于 10
          如果 {nmast} 为空
            设 nmast = {s.display_name}
          否则
            设 nmast = {nmast}、{s.display_name}
          结束
          设 mi = 计算 {mi} + 1
        结束
      否则如果 {tt} 大于 0
        设 b = 计算 {b} + 1
        设 it = {"score": {sc}, "line": "{s.display_name}（{s.username}）｜答对 {rt} / 作答 {tt}｜得分 {sc}"}
        如果 {items} 为空
          设 items = {it}
        否则
          设 items = {items},{it}
        结束
      否则
        设 c = 计算 {c} + 1
        如果 {ni} 小于 10
          如果 {nun} 为空
            设 nun = {s.display_name}
          否则
            设 nun = {nun}、{s.display_name}
          结束
          设 ni = 计算 {ni} + 1
        结束
      结束
    结束
    设 av = 没有
    如果 {attn} 大于 0
      设 av = 计算 四舍五入({sum} * 10 / {attn}) / 10
    结束
    设 out = {out}{nl}全班 {slt} 人：已掌握 {a} 人，作答过但未掌握 {b} 人，没作答 {c} 人；有作答的人平均分 {av}
    如果 {b} 大于 0
      设 j = [{items}]
      设 srt = 查询 app.db teacher_assist_sort j={j}
      设 xi = 0
      遍历 x 于 {srt}
        如果 {xi} 小于 15
          设 out = {out}{nl}{x.line}
        结束
        设 xi = 计算 {xi} + 1
      结束
      如果 {b} 大于 15
        设 rest = 计算 {b} - 15
        设 out = {out}{nl}等 {rest} 人
      结束
    结束
    如果 {c} 大于 0
      设 out = {out}{nl}没作答：{nun}
      如果 {c} 大于 10
        设 rest = 计算 {c} - 10
        设 out = {out}等 {rest} 人
      结束
    结束
    如果 {a} 大于 0
      设 out = {out}{nl}已掌握：{nmast}
    结束
    返回 {out}
  结束

  函数 建议上下文 current_user subject_id
    设 blank = {zz 或}
    设 nl = 查一值 app.db teacher_assist_nl
    设 base = 调用 班级上下文 current_user={current_user} subject_id={subject_id}
    设 r = 调用 report.取全班学情 subject={subject_id}
    设 out = {base}{nl}可对应的课文：
    设 wi = 0
    遍历 w 于 {r.weak_points}
      如果 {wi} 小于 5
        设 ls = 调用 lesson.按知识点列课文 point_code={w.point_code} subject={subject_id}
        设 lt = {blank}
        设 li = 0
        遍历 x 于 {ls.lessons}
          如果 {li} 小于 2
            设 piece = {x.code} {x.title}
            如果 {lt} 为空
              设 lt = {piece}
            否则
              设 lt = {lt}；{piece}
            结束
          结束
          设 li = 计算 {li} + 1
        结束
        如果 {lt} 为空
          设 lt = 该知识点暂无对应课文
        结束
        设 out = {out}{nl}{w.title} → {lt}
      结束
      设 wi = 计算 {wi} + 1
    结束
    设 out = {out}{nl}建议只能基于上面的数据和课文，课号和标题原样引用
    返回 {out}
  结束

  公开 函数 取助手上下文 intent student? point? learner? current_role? auth_mode? subject?
    设 blank = {zz 或}
    设 nl = 查一值 app.db teacher_assist_nl
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    如果 {intent} 不等于 class_overview 且 {intent} 不等于 student_detail 且 {intent} 不等于 point_status 且 {intent} 不等于 teaching_advice 且 {intent} 不等于 chitchat
      报错 400 intent 不合法
    结束
    设 status = ok
    设 st = {blank}
    设 sname = {blank}
    设 pt = {blank}
    设 ptitle = {blank}
    设 hint = {blank}
    设 ctx = {blank}
    如果 {intent} 等于 class_overview
      设 ctx = 调用 班级上下文 current_user=助手 subject_id={subject_id}
    否则如果 {intent} 等于 student_detail
      设 m = 调用 匹配学生 name={student} subject={subject_id}
      如果 {student} 为空
        设 status = ask
        设 hint = 你想看哪位学生？现有学生：{m.roster}
      否则如果 {m.status} 等于 none
        设 status = ask
        设 hint = 没有找到叫「{student}」的学生。现有学生：{m.roster}
      否则如果 {m.status} 等于 many
        设 status = ask
        设 names = {blank}
        遍历 x 于 {m.candidates}
          如果 {names} 为空
            设 names = {x.display_name}（{x.username}）
          否则
            设 names = {names}、{x.display_name}（{x.username}）
          结束
        结束
        设 hint = 找到多位：{names}，你指哪一位？
      否则
        设 la = {blank}
        设 r = 调用 学生范围 subject_id={subject_id}
        遍历 s 于 {r}
          如果 {s.username} 等于 {m.username}
            设 la = {s.last_at}
          结束
        结束
        设 ctx = 调用 学生上下文 username={m.username} display_name={m.display_name} last_at={la} subject_id={subject_id}
        设 st = {m.username}
        设 sname = {m.display_name}
      结束
    否则如果 {intent} 等于 point_status
      设 m = 调用 匹配知识点 keyword={point} subject={subject_id}
      如果 {point} 为空
        设 status = ask
        设 hint = 你想看哪个知识点？
      否则如果 {m.status} 等于 none
        设 status = ask
        设 hint = 没有找到「{point}」这个知识点或条目，换个说法试试（知识点名、条目名或编号都行）
      否则如果 {m.status} 等于 many
        设 status = ask
        设 names = {blank}
        遍历 x 于 {m.candidates}
          如果 {names} 为空
            设 names = {x.title}（{x.code}）
          否则
            设 names = {names}、{x.title}（{x.code}）
          结束
        结束
        设 hint = 找到多个：{names}（共 {m.total} 个，最多列 5 个），你指哪一个？
      否则
        设 ctx = 调用 知识点上下文 code={m.code} title={m.title} subject_id={subject_id}
        设 pt = {m.code}
        设 ptitle = {m.title}
      结束
    否则如果 {intent} 等于 teaching_advice
      设 ctx = 调用 建议上下文 current_user=助手 subject_id={subject_id}
      如果 {student} 不为空
        设 m = 调用 匹配学生 name={student} subject={subject_id}
        如果 {m.status} 等于 one
          设 la = {blank}
          设 r = 调用 学生范围 subject_id={subject_id}
          遍历 s 于 {r}
            如果 {s.username} 等于 {m.username}
              设 la = {s.last_at}
            结束
          结束
          设 sc = 调用 学生上下文 username={m.username} display_name={m.display_name} last_at={la} subject_id={subject_id}
          设 ctx = {ctx}{nl}{sc}
          设 st = {m.username}
          设 sname = {m.display_name}
        结束
      结束
      如果 {point} 不为空
        设 m2 = 调用 匹配知识点 keyword={point} subject={subject_id}
        如果 {m2.status} 等于 one
          设 pc = 调用 知识点上下文 code={m2.code} title={m2.title} subject_id={subject_id}
          设 ctx = {ctx}{nl}{pc}
          设 pt = {m2.code}
          设 ptitle = {m2.title}
        结束
      结束
      设 cl = 查一值 app.db teacher_assist_len t={ctx}
      如果 {cl} 大于 4500
        设 ctx = 查一值 app.db teacher_assist_substr t={ctx} n=4500
      结束
    否则
      设 ctx = 系统功能说明：{nl}教师端的页面有：学情（看全班和单个学生的学习情况，可生成AI学情总结）；教师助手（就是现在这个对话页，按数据回答老师的问题，也能按老师的话生成出题、给学生发传达两种草稿）；学生管理（建学生账号、重置密码、停用或启用）；科目管理（管理科目、协作教师和学生的分配）；图谱管理（管理本科目的知识点、条目、前置边和对照，可批量导入导出）；AI老师设定（设定学生端问老师的说话方式和规则）；教材导入（导入课文教材）。{nl}学生端共有6个页面：问老师（向AI老师提问）；做题（按知识点做题）；默写（单词默写）；教材（阅读课文）；学习进度（看进度和得分）；知识图谱（看知识点之间的前置关系）。{nl}助手能按老师的话生成「出题」「给学生发传达」两种草稿，草稿要老师在对话里或右边「待确认」列表里点「确认」才写入，7 天内可以撤销；助手不能直接改数据，不能改 AI 老师设定、科目设置和成员；只读老师只能提问不能生成草稿。
    结束
    返回 {"ok": 1, "intent": "{intent}", "status": "{status}", "student": "{st}", "student_name": "{sname}", "point": "{pt}", "point_title": "{ptitle}", "hint": "{hint}", "context_text": "{ctx}"}
  结束

  函数 判意图 message recent focus_text draft_text
    设 blank = {zz 或}
    设 nl = 查一值 app.db teacher_assist_nl
    设 pr = 你是日语学习系统里教师端助手的意图分类器。根据老师的话、最近对话、上一轮聚焦，判断意图并抽取学生名和知识点名。意图只能六选一：class_overview（问全班整体情况、班级薄弱点）、student_detail（问某个具体学生的情况）、point_status（问某个知识点或语法条目全班的掌握情况）、teaching_advice（想要教学建议、讲什么、怎么讲、推荐课文）、chitchat（闲聊、问系统怎么用、其他）、make_draft（老师要助手动手改数据：出题quiz_add、给学生发传达转告通知relay_add；只问情况问建议不算）。student填老师话里提到的学生名原文，point填提到的知识点名或条目名原文，没提到就留空；老师说他、她、这个学生时，student填上一轮聚焦的学生显示名；说这个语法、这个点时，point填上一轮聚焦的知识点标题；拿不准选chitchat。make_draft时draft_kind填quiz_add或relay_add，count填要出几道题的数字，relay_add时student填学生名（多个用顿号隔开）；待确认草稿不为空且老师要改这份草稿时intent为make_draft、draft_kind取这份草稿的类型、revise为1，否则revise为0。{nl}【上一轮聚焦】{focus_text}{nl}【待确认草稿】{draft_text}{nl}【最近对话】{recent}{nl}【老师的话】{message}
    问JSON j = {pr} 格式 intent:文本 student?:文本 point?:文本 draft_kind?:文本 count?:文本 revise?:文本 用 快 出错时 e
    设 intent = {j.intent 或}
    设 valid = 0
    如果 {intent} 等于 class_overview 或 {intent} 等于 student_detail 或 {intent} 等于 point_status 或 {intent} 等于 teaching_advice 或 {intent} 等于 chitchat 或 {intent} 等于 make_draft
      设 valid = 1
    结束
    如果 {valid} 等于 0
      设 intent = chitchat
      设 dk = {blank}
      设 rv = 0
      设 mm = 匹配 {message} 出[0-9一二两三四五六七八九十几]+道
      如果 {draft_text} 不为空 且 ({message} 包含 改 或 {message} 包含 换成 或 {message} 包含 换一 或 {message} 包含 删掉 或 {message} 包含 再加)
        设 intent = make_draft
        设 rv = 1
        设 dk = quiz_add
        如果 {draft_text} 包含 发传达
          设 dk = relay_add
        结束
      否则如果 {message} 包含 出题 或 {message} 包含 编题 或 {mm.matched} 等于 是
        设 intent = make_draft
        设 dk = quiz_add
      否则如果 {message} 包含 传达 或 {message} 包含 转告 或 {message} 包含 通知 或 {message} 包含 告诉
        设 intent = make_draft
        设 dk = relay_add
      否则如果 {message} 包含 全班 或 {message} 包含 班级 或 {message} 包含 大家 或 {message} 包含 整体 或 {message} 包含 所有学生
        设 intent = class_overview
      结束
      返回 {"intent": "{intent}", "student": "", "point": "", "draft_kind": "{dk}", "count": "", "revise": {rv}}
    结束
    设 st = {j.student 或}
    如果 {st} 不为空
      设 st = 替换 {st} ^\s+|\s+$
    结束
    设 pt = {j.point 或}
    如果 {pt} 不为空
      设 pt = 替换 {pt} ^\s+|\s+$
    结束
    设 dk = {j.draft_kind 或}
    如果 {intent} 不等于 make_draft
      设 dk = {blank}
    否则如果 {dk} 不等于 quiz_add 且 {dk} 不等于 relay_add
      设 dk = {blank}
      设 mm = 匹配 {message} 出[0-9一二两三四五六七八九十几]+道
      如果 {message} 包含 出题 或 {message} 包含 编题 或 {mm.matched} 等于 是
        设 dk = quiz_add
      否则如果 {message} 包含 传达 或 {message} 包含 转告 或 {message} 包含 通知 或 {message} 包含 告诉
        设 dk = relay_add
      结束
    结束
    设 ct = {j.count 或}
    如果 {ct} 不为空
      设 ct = 替换 {ct} ^\s+|\s+$
    结束
    设 rvv = {j.revise 或}
    设 rv = 0
    如果 {rvv} 等于 1 且 {draft_text} 不为空
      设 rv = 1
    结束
    返回 {"intent": "{intent}", "student": "{st}", "point": "{pt}", "draft_kind": "{dk}", "count": "{ct}", "revise": {rv}}
  结束

  函数 写一轮 current_user user_text reply intent student point status subject_id
    设 now = 当前时间
    事务 app.db
      设 row1 = {"teacher": "{current_user}", "role": "user", "content": "{user_text}", "intent": "{intent}", "student": "{student}", "point": "{point}", "status": "{status}", "at": "{now}", "subject_id": "{subject_id}"}
      设 n1 = 写库表 app.db teacher_assist_insert {row1}
      设 row2 = {"teacher": "{current_user}", "role": "assistant", "content": "{reply}", "intent": "{intent}", "student": "{student}", "point": "{point}", "status": "{status}", "at": "{now}", "subject_id": "{subject_id}"}
      设 n2 = 写库表 app.db teacher_assist_insert {row2}
      设 rid = 查一值 app.db teacher_assist_last_id teacher={current_user} subject_id={subject_id}
    结束
    返回 {rid}
  结束

  函数 答一轮 current_user user_text intent context_text student point subject_id
    设 nl = 查一值 app.db teacher_assist_nl
    设 recent = 调用 取最近对话 current_user={current_user} limit=6 subject_id={subject_id}
    设 sysp = 你是日语学习系统教师端的教学助手，像同事一样和老师说话，只读。回答规则：①数字、人名、名单、知识点名、课号、标题、日期只能原样取自【数据】，不得自己推算新数字，不得写大约、差不多之类的估算，唯一允许的是数一数【数据】里列出的行；②【数据】里没有的就直说「这份数据里没有」，不猜不编，也不要说系统没有的功能；③不要写昨天、上周、几天前这类相对时间，只能原样引用【数据】里写明的日期；④最近对话里出现过的数字可能已过时，以【数据】为准；⑤你不能直接改数据：出题、给学生发传达只能生成草稿等老师确认（老师直接说出题或给某某发传达就会生成）；改AI老师设定、科目设置、成员你做不了，告诉老师去哪个页面做；⑥只输出纯文本，不用Markdown的标题、加粗、表格、列表符号，不用emoji；名单每人一行，行首用「・」；⑦一般不超过300字，名单最多列10人；⑧给教学建议时先说依据（引用【数据】里的哪几项），再给1到3条具体做法，推荐课文只能用【数据】里的课号和标题；⑨闲聊或问系统用法时简短自然地回应，用法只依据【数据】里的系统功能说明。
    设 full = {sysp}{nl}{nl}【数据】{nl}{context_text}{nl}{nl}【最近对话】{nl}{recent}{nl}{nl}【老师最新一句】{nl}{user_text}
    问 reply = {full} 用 平衡 出错时 e
    如果 {e} 不为空 或 {reply} 为空
      报错 400 助手暂时无法回答
    结束
    设 rid = 调用 写一轮 current_user={current_user} user_text={user_text} reply={reply} intent={intent} student={student} point={point} status=ok subject_id={subject_id}
    返回 {"reply_id": {rid}, "reply": "{reply}"}
  结束

  公开 函数 问助手 current_user message current_role? auth_mode? subject?
    设 blank = {zz 或}
    如果 {current_user} 为空
      报错 400 current_user 不能为空
    结束
    如果 {message} 为空
      报错 400 消息不能为空
    结束
    设 msg = 替换 {message} ^\s+|\s+$
    如果 {msg} 为空
      报错 400 消息不能为空
    结束
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 recent = 调用 取最近对话 current_user={current_user} limit=6 subject_id={subject_id}
    设 f = 调用 取上轮聚焦 current_user={current_user} subject_id={subject_id}
    设 fs = {blank}
    如果 {f.student} 不为空
      设 fs = 学生：{f.student_name}（{f.student}）
    结束
    设 fp = {blank}
    如果 {f.point} 不为空
      设 fp = 知识点：{f.point_title}（{f.point}）
    结束
    设 focus_text = 无
    如果 {fs} 不为空 且 {fp} 不为空
      设 focus_text = {fs}；{fp}
    否则如果 {fs} 不为空
      设 focus_text = {fs}
    否则如果 {fp} 不为空
      设 focus_text = {fp}
    结束
    设 pl = 调用 列草稿 current_user={current_user} status=pending limit=1 subject={subject_id}
    设 pend_id = {blank}
    设 pend_kind = {blank}
    设 draft_text = {blank}
    遍历 x0 于 {pl.drafts}
      如果 {pend_id} 为空
        设 pend_id = {x0.draft_id}
        设 pend_kind = quiz_add
        如果 {x0.draft_kind} 等于 发传达
          设 pend_kind = relay_add
        结束
        设 pre = 草稿
        设 draft_text = {pre} #{pend_id}（{x0.draft_kind}）：{x0.draft_brief}
      结束
    结束
    设 d = 调用 判意图 message={msg} recent={recent} focus_text={focus_text} draft_text={draft_text}
    设 intent = {d.intent}
    设 st = {d.student}
    设 pt = {d.point}
    如果 {intent} 等于 student_detail 且 {st} 为空 且 {f.student} 不为空
      设 st = {f.student_name}
      如果 {st} 为空
        设 st = {f.student}
      结束
    结束
    如果 {intent} 等于 point_status 且 {pt} 为空 且 {f.point} 不为空
      设 pt = {f.point_title}
      如果 {pt} 为空
        设 pt = {f.point}
      结束
    结束
    如果 {intent} 等于 make_draft
      设 nl = 查一值 app.db teacher_assist_nl
      设 dk = {d.draft_kind}
      设 rep = {blank}
      设 did = {blank}
      设 status = ask
      设 reply = {blank}
      设 wp = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject_id} need=write 出错时 we
      如果 {we} 不为空
        如果 {we.code} 不等于 403
          报错 400 {we.error}
        结束
        设 reply = 你在这个科目只有读权限，不能让助手生成改动草稿（出题、发传达）；学情照样可以问。
      否则
        如果 {d.revise} 等于 1 且 {pend_id} 不为空
          设 rep = {pend_id}
          设 dk = {pend_kind}
        结束
        如果 {dk} 为空
          设 reply = 你是想让我出题，还是给学生发传达？
        否则
          设 st2 = {d.student}
          设 pt2 = {d.point}
          如果 {dk} 等于 relay_add 且 {st2} 为空 且 {f.student_name} 不为空
            设 st2 = {f.student_name}
          结束
          如果 {dk} 等于 quiz_add 且 {pt2} 为空 且 {f.point_title} 不为空
            设 pt2 = {f.point_title}
          结束
          设 g = 调用 生成草稿 current_user={current_user} kind={dk} message={msg} point={pt2} students={st2} count={d.count} replaces_id={rep} subject={subject_id}
          如果 {g.status} 等于 ask
            设 reply = {g.hint}
          否则
            设 status = ok
            设 did = {g.draft_id}
            设 pv = 查一值 app.db teacher_assist_substr t={g.preview} n=300
            设 pre = 已生成草稿
            设 reply = {pre} #{g.draft_id}：{g.title}{nl}{pv}{nl}点「确认」才会写入；不要就点「放弃」。也可以直接说哪里要改，我出一份修订稿。
          结束
        结束
      结束
      设 rid = 调用 写一轮 current_user={current_user} user_text={msg} reply={reply} intent=make_draft student={blank} point={blank} status={status} subject_id={subject_id}
      如果 {did} 不为空
        设 n0 = 写库 app.db teacher_assist_draft_source id={did} msg={rid}
      结束
      返回 {"ok": 1, "reply_id": {rid}, "reply": "{reply}", "intent": "make_draft", "student": "", "point": "", "status": "{status}", "draft_id": "{did}"}
    结束
    设 c = 调用 取助手上下文 intent={intent} student={st} point={pt} subject={subject_id}
    如果 {c.status} 等于 ask
      设 rid = 调用 写一轮 current_user={current_user} user_text={msg} reply={c.hint} intent={intent} student={blank} point={blank} status=ask subject_id={subject_id}
      返回 {"ok": 1, "reply_id": {rid}, "reply": "{c.hint}", "intent": "{intent}", "student": "{c.student}", "point": "{c.point}", "status": "ask", "draft_id": ""}
    结束
    设 a = 调用 答一轮 current_user={current_user} user_text={msg} intent={intent} context_text={c.context_text} student={c.student} point={c.point} subject_id={subject_id}
    返回 {"ok": 1, "reply_id": {a.reply_id}, "reply": "{a.reply}", "intent": "{intent}", "student": "{c.student}", "point": "{c.point}", "status": "ok", "draft_id": ""}
  结束

  公开 函数 列对话 current_user limit? current_role? auth_mode? subject?
    如果 {current_user} 为空
      报错 400 current_user 不能为空
    结束
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 lim = {limit}
    如果 {lim} 为空
      设 lim = 50
    结束
    设 bad = 替换 {lim} [0-9]
    如果 {bad} 不为空
      报错 400 limit 不合法
    结束
    如果 {lim} 小于 1
      报错 400 limit 不合法
    结束
    设 rows = 查询 app.db teacher_assist_list teacher={current_user} n={lim} subject_id={subject_id}
    设 total = 列表长度 {rows}
    返回 {"teacher": "{current_user}", "total": {total}, "messages": {rows}}
  结束

  公开 函数 列对话页面 current_user current_role? auth_mode? subject?
    设 blank = {zz 或}
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 r = 调用 列对话 current_user={current_user} limit=40 subject={subject_id}
    设 talk = {blank}
    遍历 x 于 {r.messages}
      如果 {x.role} 等于 assistant
        设 it = {"who": "助手", "text": "{x.content}", "kind": ""}
        设 dq = 查一行 app.db teacher_assist_draft_by_source teacher={current_user} subject_id={subject_id} msg={x.id}
        如果 {dq} 不为空
          设 bt = 调用 草稿按钮 draft={dq}
          设 it = {"who": "助手", "text": "{x.content}", "kind": "draft", "actions": {bt.actions}, "links": {bt.links}}
        结束
      否则
        设 it = {"who": "你", "text": "{x.content}", "kind": "user"}
      结束
      如果 {talk} 为空
        设 talk = {it}
      否则
        设 talk = {talk},{it}
      结束
    结束
    设 dl = 调用 列草稿 current_user={current_user} subject={subject_id}
    设 ac = 调用 subject.科目访问 learner={current_user} current_role={current_role} subject_id={subject_id} need=write auth_mode={auth_mode}
    设 ro = 0
    如果 {ac.ok} 等于 0
      设 ro = 1
    结束
    返回 {"talk": [{talk}], "drafts": {dl.drafts}, "readonly": {ro}}
  结束

  公开 函数 问助手页面 current_user message current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 r = 调用 问助手 current_user={current_user} message={message} current_role={current_role} auth_mode={auth_mode} subject={subject_id}
    设 pg = 调用 列对话页面 current_user={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject_id}
    返回 {"ok": 1, "reply_id": {r.reply_id}, "reply": "{r.reply}", "intent": "{r.intent}", "student": "{r.student}", "point": "{r.point}", "status": "{r.status}", "draft_id": "{r.draft_id}", "page": {pg}}
  结束

  函数 记一条 current_user content subject_id
    设 now = 当前时间
    设 row = {"teacher": "{current_user}", "role": "assistant", "content": "{content}", "intent": "make_draft", "student": "", "point": "", "status": "ok", "at": "{now}", "subject_id": "{subject_id}"}
    设 n = 写库表 app.db teacher_assist_insert {row}
    设 rid = 查一值 app.db teacher_assist_last_id teacher={current_user} subject_id={subject_id}
    返回 {rid}
  结束

  公开 函数 取草稿页面 current_user draft_id current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 d = 调用 取草稿 current_user={current_user} draft_id={draft_id} subject={subject_id}
    返回 {d}
  结束

  公开 函数 确认草稿页面 current_user draft_id current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 subject_id = {sj.subject_id}
    设 x = 调用 确认草稿 current_user={current_user} draft_id={draft_id} subject={subject_id}
    设 page = 调用 列对话页面 current_user={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject_id}
    设 d = 调用 取草稿 current_user={current_user} draft_id={draft_id} subject={subject_id}
    返回 {"talk": {page.talk}, "drafts": {page.drafts}, "readonly": {page.readonly}, "draft": {d.draft}}
  结束

  公开 函数 放弃草稿页面 current_user draft_id current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 x = 调用 放弃草稿 current_user={current_user} draft_id={draft_id} subject={subject_id}
    设 page = 调用 列对话页面 current_user={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject_id}
    设 d = 调用 取草稿 current_user={current_user} draft_id={draft_id} subject={subject_id}
    返回 {"talk": {page.talk}, "drafts": {page.drafts}, "readonly": {page.readonly}, "draft": {d.draft}}
  结束

  公开 函数 撤销草稿页面 current_user draft_id current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 subject_id = {sj.subject_id}
    设 x = 调用 撤销草稿 current_user={current_user} draft_id={draft_id} subject={subject_id}
    设 page = 调用 列对话页面 current_user={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject_id}
    设 d = 调用 取草稿 current_user={current_user} draft_id={draft_id} subject={subject_id}
    返回 {"talk": {page.talk}, "drafts": {page.drafts}, "readonly": {page.readonly}, "draft": {d.draft}}
  结束
结束
