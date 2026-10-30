业务 assist_insight
  依赖 assist_common progress report kg subject
  用包 db common text data

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {r.subject_id}
  结束

  函数 规则常量
    返回 {"silent_days": 7, "drop_window": 14, "drop_pct": 15, "drop_min": 10, "trend_days": 28, "trend_min_days": 3, "top_n": 5, "compare_min": 2, "compare_max": 5, "relay_max": 30}
  结束

  函数 字符条 rate
    设 o = {"a": "█", "b": "░", "z": ""}
    设 r = {rate 或 0}
    如果 {r} 小于 0
      设 r = 0
    结束
    如果 {r} 大于 100
      设 r = 100
    结束
    设 full = 计算 ({r} + 5) // 10
    设 rest = 计算 10 - {full}
    设 bar = {o.z 或}
    重复 {full} 次
      设 bar = {bar}{o.a}
    结束
    重复 {rest} 次
      设 bar = {bar}{o.b}
    结束
    返回 {bar}
  结束

  函数 迷你图 rates
    设 o = {"a": "·", "b": "▁", "c": "▂", "d": "▃", "e": "▅", "f": "▆", "z": ""}
    设 s = {o.z 或}
    遍历 r 于 {rates}
      如果 {r} 为空 或 {r} 等于 无
        设 s = {s}{o.a}
      否则如果 {r} 小于 20
        设 s = {s}{o.b}
      否则如果 {r} 小于 40
        设 s = {s}{o.c}
      否则如果 {r} 小于 60
        设 s = {s}{o.d}
      否则如果 {r} 小于 80
        设 s = {s}{o.e}
      否则
        设 s = {s}{o.f}
      结束
    结束
    返回 {s}
  结束

  函数 空态 subject_id
    设 o = {"p": "|"}
    设 st = 调用 assist_common.学生范围 subject={subject_id}
    如果 {st.total} 等于 0
      返回 {"status": "empty", "hint": "这个科目还没有学生，去「科目管理 → 成员」分配学生后再看", "students": [], "answered": []}
    结束
    设 names = {o.p}
    遍历 s 于 {st.students}
      设 names = {names}{s.username}{o.p}
    结束
    设 answered = []
    设 pr = 调用 progress.统计作答 subject={subject_id}
    遍历 l 于 {pr.learners}
      设 key = {o.p}{l.learner}{o.p}
      如果 {l.answer_count} 大于 0 且 {names} 包含 {key}
        设 answered = 列表加项 {answered} {l.learner}
      结束
    结束
    设 an = 列表长度 {answered}
    如果 {an} 等于 0
      返回 {"status": "empty", "hint": "还没有作答记录，趋势、归因、预警都要等学生做过题才有", "students": {st.students}, "answered": []}
    结束
    返回 {"status": "ok", "hint": "", "students": {st.students}, "answered": {answered}}
  结束

  公开 函数 学情趋势 student? days? week? learner? current_role? auth_mode? subject?
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 c = 调用 规则常量
    设 o = {"nl": "\n", "z": "", "p": "|", "all": "全班", "wk": "按周", "dy": "按天", "wz": "无"}
    如果 {days} 为空
      设 days = {c.trend_days}
    结束
    设 m = 匹配 {days} ^\d+$
    如果 {m.matched} 不等于 是
      报错 400 days 不合法
    结束
    设 days = 计算 {days} + 0
    如果 {days} 小于 7 或 {days} 大于 90
      报错 400 days 不合法
    结束
    如果 {week} 为空
      如果 {days} 大于 14
        设 week = 1
      否则
        设 week = 0
      结束
    否则如果 {week} 等于 1
      设 week = 1
    否则
      设 week = 0
    结束
    设 es = 调用 空态 subject_id={subject_id}
    如果 {es.status} 等于 empty
      返回 {"status": "empty", "hint": "{es.hint}", "student": "", "days": {days}, "week": {week}, "active_days": 0, "rows": [], "spark": "", "chart": "", "context_text": ""}
    结束
    设 names = {o.p}
    遍历 s 于 {es.students}
      设 names = {names}{s.username}{o.p}
    结束
    设 username = {o.z 或}
    设 scope = {o.all}
    如果 {student} 不为空
      设 mt = 调用 assist_common.匹配学生 name={student} subject={subject_id}
      如果 {mt.status} 等于 none
        返回 {"status": "ask", "hint": "没有找到叫「{student}」的学生。现有学生：{mt.roster}", "student": "", "days": {days}, "week": {week}, "active_days": 0, "rows": [], "spark": "", "chart": "", "context_text": ""}
      结束
      如果 {mt.status} 等于 many
        设 cl = {o.z 或}
        遍历 cd 于 {mt.candidates}
          如果 {cl} 为空
            设 cl = {cd.display_name}（{cd.username}）
          否则
            设 cl = {cl}、{cd.display_name}（{cd.username}）
          结束
        结束
        返回 {"status": "ask", "hint": "找到多位：{cl}，你指哪一位？", "student": "", "days": {days}, "week": {week}, "active_days": 0, "rows": [], "spark": "", "chart": "", "context_text": ""}
      结束
      设 username = {mt.username}
      设 scope = {mt.display_name}（{mt.username}）
      设 names = {o.p}{mt.username}{o.p}
    结束
    设 d = 调用 progress.按天统计作答 days={days} student={username} subject={subject_id}
    设 since = {d.since}
    设 drows = []
    遍历 r 于 {d.rows}
      设 key = {o.p}{r.learner}{o.p}
      如果 {names} 包含 {key}
        设 drows = 列表加项 {drows} {r}
      结束
    结束
    设 active_days = 0
    设 last = {o.wz}
    遍历 r 于 {drows}
      如果 {r.period} 不等于 {last}
        设 active_days = 计算 {active_days} + 1
        设 last = {r.period}
      结束
    结束
    设 src = {drows}
    如果 {week} 等于 1
      设 dw = 调用 progress.按天统计作答 days={days} week=1 student={username} subject={subject_id}
      设 wrows = []
      遍历 r 于 {dw.rows}
        设 key = {o.p}{r.learner}{o.p}
        如果 {names} 包含 {key}
          设 wrows = 列表加项 {wrows} {r}
        结束
      结束
      设 src = {wrows}
    结束
    设 agg = []
    设 cur = {o.wz}
    设 pn = 0
    设 pr = 0
    设 pm = 0
    遍历 r 于 {src}
      如果 {r.period} 不等于 {cur}
        如果 {cur} 不等于 {o.wz}
          设 item = {"period": "{cur}", "n": {pn}, "right": {pr}, "m": {pm}}
          设 agg = 列表加项 {agg} {item}
        结束
        设 cur = {r.period}
        设 pn = {r.n}
        设 pr = {r.right}
        设 pm = 1
      否则
        设 pn = 计算 {pn} + {r.n}
        设 pr = 计算 {pr} + {r.right}
        设 pm = 计算 {pm} + 1
      结束
    结束
    如果 {cur} 不等于 {o.wz}
      设 item = {"period": "{cur}", "n": {pn}, "right": {pr}, "m": {pm}}
      设 agg = 列表加项 {agg} {item}
    结束
    如果 {week} 等于 1
      设 wl = {o.wk}
    否则
      设 wl = {o.dy}
    结束
    设 rows = []
    设 ar = []
    设 chbody = {o.z 或}
    设 ctxbody = {o.z 或}
    设 na = 列表长度 {agg}
    设 skip = 计算 {na} - 12
    设 idx = 0
    设 tot = 0
    设 firstrate = {o.z 或}
    设 lastrate = {o.z 或}
    遍历 a 于 {agg}
      如果 {na} 等于 0
        继续
      结束
      设 idx = 计算 {idx} + 1
      设 rate = 计算 ({a.right} * 200 + {a.n}) // (2 * {a.n})
      设 bar = 调用 字符条 rate={rate}
      设 lab = {a.period}
      如果 {week} 等于 1
        设 lab = {a.period} 起一周
      结束
      设 cnt = {a.n} 题 / {a.m} 人
      设 ri = {"ana_day": "{lab}", "ana_n": "{cnt}", "ana_rate": {rate}, "ana_bar": "{bar}"}
      设 rows = 列表加项 {rows} {ri}
      设 ai = {"period": "{a.period}", "rate": {rate}}
      设 ar = 列表加项 {ar} {ai}
      设 tot = 计算 {tot} + {a.n}
      如果 {idx} 等于 1
        设 firstrate = {rate}
      结束
      设 lastrate = {rate}
      设 ctxbody = {ctxbody}{o.nl}{a.period}｜作答 {a.n}｜答对 {a.right}｜正确率 {rate}%｜人数 {a.m}
      如果 {idx} 大于 {skip}
        设 chbody = {chbody}{o.nl}{lab} {bar} {rate}%（{cnt}）
      结束
    结束
    设 today = 当前时间 日期
    设 rates = []
    如果 {week} 等于 1
      设 start = 查一值 app.db assist_insight_week_start d={since}
      设 diff = 查一值 app.db assist_insight_date_diff a={start} b={today}
      设 np = 计算 {diff} // 7 + 1
      设 step = 7
    否则
      设 start = {since}
      设 np = {days}
      设 step = 1
    结束
    重复 {np} 次 计数 i
      设 off = 计算 ({i} - 1) * {step}
      设 per = 查一值 app.db assist_insight_date_shift d={start} n={off}
      设 rv = {o.wz}
      遍历 x 于 {ar}
        如果 {na} 等于 0
          继续
        结束
        如果 {x.period} 等于 {per}
          设 rv = {x.rate}
        结束
      结束
      设 rates = 列表加项 {rates} {rv}
    结束
    设 spark = 调用 迷你图 rates={rates}
    如果 {active_days} 小于 {c.trend_min_days}
      设 oc = {"c": "只有 {active_days} 天有作答，数据太少，先不画趋势"}
      设 chart = {oc.c}
    否则
      设 oc = {"c": "近 {days} 天（{wl}）正确率 {spark} {firstrate}%→{lastrate}%（共作答 {tot} 题）"}
      设 chart = {oc.c}{chbody}
    结束
    设 ox = {"t": "今天：{today}{o.nl}分析：作答趋势，范围 {scope}，最近 {days} 天，{wl}{ctxbody}{o.nl}【后端算好的字符图】{o.nl}{chart}"}
    返回 {"status": "ok", "hint": "", "student": "{username}", "days": {days}, "week": {week}, "active_days": {active_days}, "rows": {rows}, "spark": "{spark}", "chart": "{chart}", "context_text": "{ox.t}"}
  结束

  公开 函数 错题归因 student? days? top? learner? current_role? auth_mode? subject?
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 c = 调用 规则常量
    设 o = {"nl": "\n", "z": "", "p": "|", "all": "全班", "out": "（题库外的题）"}
    如果 {days} 为空
      设 days = {c.trend_days}
    结束
    设 m = 匹配 {days} ^\d+$
    如果 {m.matched} 不等于 是
      报错 400 days 不合法
    结束
    设 days = 计算 {days} + 0
    如果 {days} 小于 7 或 {days} 大于 90
      报错 400 days 不合法
    结束
    如果 {top} 为空
      设 top = {c.top_n}
    结束
    设 m2 = 匹配 {top} ^\d+$
    如果 {m2.matched} 不等于 是
      报错 400 top 不合法
    结束
    设 top = 计算 {top} + 0
    如果 {top} 小于 1 或 {top} 大于 10
      报错 400 top 不合法
    结束
    设 es = 调用 空态 subject_id={subject_id}
    如果 {es.status} 等于 empty
      返回 {"status": "empty", "hint": "{es.hint}", "days": {days}, "total": 0, "points": [], "rows": [], "chart": "", "context_text": ""}
    结束
    设 names = {o.p}
    遍历 s 于 {es.students}
      设 names = {names}{s.username}{o.p}
    结束
    设 scope = {o.all}
    如果 {student} 不为空
      设 mt = 调用 assist_common.匹配学生 name={student} subject={subject_id}
      如果 {mt.status} 等于 none
        返回 {"status": "ask", "hint": "没有找到叫「{student}」的学生。现有学生：{mt.roster}", "days": {days}, "total": 0, "points": [], "rows": [], "chart": "", "context_text": ""}
      结束
      如果 {mt.status} 等于 many
        设 cl = {o.z 或}
        遍历 cd 于 {mt.candidates}
          如果 {cl} 为空
            设 cl = {cd.display_name}（{cd.username}）
          否则
            设 cl = {cl}、{cd.display_name}（{cd.username}）
          结束
        结束
        返回 {"status": "ask", "hint": "找到多位：{cl}，你指哪一位？", "days": {days}, "total": 0, "points": [], "rows": [], "chart": "", "context_text": ""}
      结束
      设 scope = {mt.display_name}（{mt.username}）
      设 names = {o.p}{mt.username}{o.p}
    结束
    设 today = 当前时间 日期
    设 off = 计算 1 - {days}
    设 since = 查一值 app.db assist_insight_date_shift d={today} n={off}
    设 wp = 查询 app.db assist_insight_wrong_points subject={subject_id} since={since} names={names}
    设 wi = 查询 app.db assist_insight_wrong_items subject={subject_id} since={since} names={names}
    设 total = 列表长度 {wp}
    设 points = []
    设 rows = []
    设 idx = 0
    设 chbody = {o.z 或}
    设 ctxbody = {o.z 或}
    遍历 p 于 {wp}
      设 idx = 计算 {idx} + 1
      如果 {idx} 不大于 {top}
        设 kp = 调用 kg.取知识点 code={p.point_code} subject={subject_id}
        设 title = {kp.title 或}
        如果 {title} 为空
          设 title = {p.point_code}
        结束
        设 rate = 计算 ({p.wrong} * 200 + {p.n}) // (2 * {p.n})
        设 bar = 调用 字符条 rate={rate}
        设 its = []
        设 itxt = {o.z 或}
        设 ctxt = {o.z 或}
        设 cnt = 0
        遍历 w 于 {wi}
          如果 {w.point_code} 等于 {p.point_code} 且 {cnt} 小于 3
            设 cnt = 计算 {cnt} + 1
            设 nm = {o.out}
            如果 {w.item_code} 不为空
              设 ki = 调用 kg.取条目 code={w.item_code} subject={subject_id}
              设 nm = {ki.name 或}
              如果 {nm} 为空
                设 nm = {w.item_code}
              结束
            结束
            设 ii = {"code": "{w.item_code}", "name": "{nm}", "wrong": {w.wrong}}
            设 its = 列表加项 {its} {ii}
            如果 {itxt} 为空
              设 itxt = {nm}（{w.wrong}）
              设 ctxt = {nm} 错 {w.wrong} 题
            否则
              设 itxt = {itxt}、{nm}（{w.wrong}）
              设 ctxt = {ctxt}、{nm} 错 {w.wrong} 题
            结束
          结束
        结束
        设 pi = {"point_code": "{p.point_code}", "title": "{title}", "n": {p.n}, "wrong": {p.wrong}, "rate": {rate}, "learners": {p.learners}, "items": {its}}
        设 points = 列表加项 {points} {pi}
        设 ri = {"ana_day": "{title}", "ana_n": {p.n}, "ana_rate": {rate}, "ana_bar": "{bar}"}
        设 rows = 列表加项 {rows} {ri}
        设 lt = {"t": "{title} {bar} {rate}%（错 {p.wrong} / 作答 {p.n} 题，{p.learners} 人）{o.nl}  错得多的条目：{itxt}"}
        设 chbody = {chbody}{o.nl}{lt.t}
        设 xt = {"t": "{title}（{p.point_code}）｜作答 {p.n}｜答错 {p.wrong}｜错误率 {rate}%｜答错的人 {p.learners}｜条目：{ctxt}"}
        设 ctxbody = {ctxbody}{o.nl}{xt.t}
      结束
    结束
    设 k = 列表长度 {points}
    如果 {total} 等于 0
      设 oc = {"c": "最近 {days} 天没有答错的题"}
      设 chart = {oc.c}
    否则
      设 oc = {"c": "最近 {days} 天错题最多的 {k} 个知识点（错误率 = 答错 / 作答）：{chbody}"}
      设 chart = {oc.c}
    结束
    设 ox = {"t": "今天：{today}{o.nl}分析：错题归因，范围 {scope}，最近 {days} 天，有错题的知识点共 {total} 个，下面是前 {k} 个{ctxbody}{o.nl}【后端算好的字符图】{o.nl}{chart}"}
    返回 {"status": "ok", "hint": "", "days": {days}, "total": {total}, "points": {points}, "rows": {rows}, "chart": "{chart}", "context_text": "{ox.t}"}
  结束

  公开 函数 学生对比 students learner? current_role? auth_mode? subject?
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 c = 调用 规则常量
    设 o = {"nl": "\n", "z": "", "p": "|"}
    设 es = 调用 空态 subject_id={subject_id}
    设 sn = 列表长度 {es.students}
    如果 {es.status} 等于 empty 且 {sn} 等于 0
      返回 {"status": "empty", "hint": "{es.hint}", "total": 0, "ranked": 0, "rows": [], "chart": "", "context_text": ""}
    结束
    设 parts = 按正则切分 {students} [、，,\s]+
    设 nlist = []
    设 seen = {o.p}
    遍历 pt 于 {parts}
      设 key = {o.p}{pt}{o.p}
      如果 {pt} 不为空 且 {seen} 不包含 {key}
        设 seen = {seen}{pt}{o.p}
        设 nlist = 列表加项 {nlist} {pt}
      结束
    结束
    设 cnt = 列表长度 {nlist}
    如果 {cnt} 小于 {c.compare_min} 或 {cnt} 大于 {c.compare_max}
      返回 {"status": "ask", "hint": "对比要说 2 到 5 位学生的名字，用「、」隔开", "total": 0, "ranked": 0, "rows": [], "chart": "", "context_text": ""}
    结束
    设 people = []
    设 seenu = {o.p}
    遍历 nm 于 {nlist}
      设 mt = 调用 assist_common.匹配学生 name={nm} subject={subject_id}
      如果 {mt.status} 等于 none
        返回 {"status": "ask", "hint": "没有找到叫「{nm}」的学生。现有学生：{mt.roster}", "total": 0, "ranked": 0, "rows": [], "chart": "", "context_text": ""}
      结束
      如果 {mt.status} 等于 many
        设 cl = {o.z 或}
        遍历 cd 于 {mt.candidates}
          如果 {cl} 为空
            设 cl = {cd.display_name}（{cd.username}）
          否则
            设 cl = {cl}、{cd.display_name}（{cd.username}）
          结束
        结束
        返回 {"status": "ask", "hint": "「{nm}」找到多位：{cl}，你指哪一位？", "total": 0, "ranked": 0, "rows": [], "chart": "", "context_text": ""}
      结束
      设 key = {o.p}{mt.username}{o.p}
      如果 {seenu} 不包含 {key}
        设 seenu = {seenu}{mt.username}{o.p}
        设 pe = {"username": "{mt.username}", "dn": "{mt.display_name}"}
        设 people = 列表加项 {people} {pe}
      结束
    结束
    设 pc = 列表长度 {people}
    如果 {pc} 小于 {c.compare_min}
      返回 {"status": "ask", "hint": "对比要说 2 到 5 位学生的名字，用「、」隔开", "total": 0, "ranked": 0, "rows": [], "chart": "", "context_text": ""}
    结束
    设 plist = []
    遍历 pe 于 {people}
      设 rp = 调用 report.取学生学情 student={pe.username} subject={subject_id}
      设 wt = {o.z 或}
      设 wi = 0
      遍历 w 于 {rp.weak_points}
        设 wi = 计算 {wi} + 1
        如果 {wi} 不大于 3
          如果 {wt} 为空
            设 wt = {w.title} {w.score}
          否则
            设 wt = {wt}、{w.title} {w.score}
          结束
        结束
      结束
      设 po = {"u": "{pe.username}", "dn": "{pe.dn}", "total": {rp.answer_total 或 0}, "acc": {rp.recent_accuracy 或 0}, "avg": {rp.avg_score 或 0}, "mc": {rp.mastered_count 或 0}, "wc": {rp.weak_count 或 0}, "wt": "{wt}"}
      设 plist = 列表加项 {plist} {po}
    结束
    设 used = {o.p}
    设 ranked = []
    重复 5 次
      设 hasb = 0
      设 best = {o.z 或}
      遍历 po 于 {plist}
        设 key = {o.p}{po.u}{o.p}
        如果 {po.total} 大于 0 且 {used} 不包含 {key}
          如果 {hasb} 等于 0
            设 best = {po}
            设 hasb = 1
          否则如果 {po.acc} 大于 {best.acc}
            设 best = {po}
          否则如果 {po.acc} 等于 {best.acc} 且 {po.avg} 大于 {best.avg}
            设 best = {po}
          否则如果 {po.acc} 等于 {best.acc} 且 {po.avg} 等于 {best.avg} 且 {po.u} 小于 {best.u}
            设 best = {po}
          结束
        结束
      结束
      如果 {hasb} 等于 1
        设 used = {used}{best.u}{o.p}
        设 ranked = 列表加项 {ranked} {best}
      结束
    结束
    设 rk = 0
    设 rows = []
    设 chbody = {o.z 或}
    设 ctxbody = {o.z 或}
    设 rn0 = 列表长度 {ranked}
    遍历 po 于 {ranked}
      如果 {rn0} 等于 0
        继续
      结束
      设 rk = 计算 {rk} + 1
      设 bar = 调用 字符条 rate={po.acc}
      设 ri = {"ana_day": "{po.dn}", "ana_n": {po.total}, "ana_rate": {po.acc}, "ana_bar": "{bar}"}
      设 rows = 列表加项 {rows} {ri}
      设 chbody = {chbody}{o.nl}{rk}. {po.dn} {bar} 近期正确率 {po.acc}%｜平均分 {po.avg}｜已掌握 {po.mc}｜低分点 {po.wc} 个
      设 ctxbody = {ctxbody}{o.nl}{po.dn}（{po.u}）｜作答 {po.total}｜近期正确率 {po.acc}%｜平均分 {po.avg}｜已掌握 {po.mc}｜低分点 {po.wc} 个（最低：{po.wt}）
    结束
    遍历 po 于 {plist}
      如果 {po.total} 等于 0
        设 ri = {"ana_day": "{po.dn}", "ana_n": 0, "ana_rate": "", "ana_bar": "还没作答"}
        设 rows = 列表加项 {rows} {ri}
        设 chbody = {chbody}{o.nl}{po.dn}：还没作答
        设 ctxbody = {ctxbody}{o.nl}{po.dn}（{po.u}）｜还没作答
      结束
    结束
    设 chart = 截取 {chbody} 2
    设 rn = 列表长度 {ranked}
    设 today = 当前时间 日期
    设 ox = {"t": "今天：{today}{o.nl}分析：学生对比（近期正确率按每人最近 20 次作答算）{ctxbody}{o.nl}【后端算好的字符图】{o.nl}{chart}"}
    返回 {"status": "ok", "hint": "", "total": {pc}, "ranked": {rn}, "rows": {rows}, "chart": "{chart}", "context_text": "{ox.t}"}
  结束

  公开 函数 掉队名单 learner? current_role? auth_mode? subject?
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 c = 调用 规则常量
    设 o = {"nl": "\n", "z": "", "p": "|", "never": "从没作答过"}
    设 orl = {"t": "规则：①全班近 {c.silent_days} 天有作答、而这位学生 {c.silent_days} 天以上没有作答；②近 {c.drop_window} 天正确率比之前 {c.drop_window} 天低 {c.drop_pct} 个百分点以上（两段都至少 {c.drop_min} 题）"}
    设 rt = {orl.t}
    设 es = 调用 空态 subject_id={subject_id}
    如果 {es.status} 等于 empty
      返回 {"status": "empty", "hint": "{es.hint}", "total": 0, "students": [], "rules_text": "{rt}", "chart": "", "context_text": ""}
    结束
    设 names = {o.p}
    遍历 s 于 {es.students}
      设 names = {names}{s.username}{o.p}
    结束
    设 today = 当前时间 日期
    设 days2 = 计算 {c.drop_window} * 2
    设 d = 调用 progress.按天统计作答 days={days2} subject={subject_id}
    设 rows2 = []
    设 classact = 0
    遍历 r 于 {d.rows}
      设 key = {o.p}{r.learner}{o.p}
      如果 {names} 包含 {key}
        设 dist = 查一值 app.db assist_insight_date_diff a={r.period} b={today}
        设 xr = {"u": "{r.learner}", "dist": {dist}, "n": {r.n}, "right": {r.right}}
        设 rows2 = 列表加项 {rows2} {xr}
        如果 {dist} 小于 {c.silent_days}
          设 classact = 1
        结束
      结束
    结束
    设 hits = []
    设 chbody = {o.z 或}
    遍历 s 于 {es.students}
      如果 {s.status} 不等于 停用
        设 recent = 0
        设 n1 = 0
        设 r1 = 0
        设 n0 = 0
        设 r0 = 0
        遍历 x 于 {rows2}
          如果 {x.u} 等于 {s.username}
            如果 {x.dist} 小于 {c.silent_days}
              设 recent = 1
            结束
            如果 {x.dist} 小于 {c.drop_window}
              设 n1 = 计算 {n1} + {x.n}
              设 r1 = 计算 {r1} + {x.right}
            否则如果 {x.dist} 小于 {days2}
              设 n0 = 计算 {n0} + {x.n}
              设 r0 = 计算 {r0} + {x.right}
            结束
          结束
        结束
        设 la = {o.z 或}
        设 lat = {o.never}
        如果 {s.last_at} 不为空
          设 la = 截取 {s.last_at} 1 10
          设 lat = {la}
        结束
        设 reasons = []
        设 jt = {o.z 或}
        如果 {classact} 等于 1 且 {recent} 等于 0
          设 or1 = {"t": "近 {c.silent_days} 天没有作答（最近一次 {lat}）"}
          设 reasons = 列表加项 {reasons} {or1.t}
          设 jt = {or1.t}
        结束
        如果 {n1} 不小于 {c.drop_min} 且 {n0} 不小于 {c.drop_min}
          设 rate1 = 计算 ({r1} * 200 + {n1}) // (2 * {n1})
          设 rate0 = 计算 ({r0} * 200 + {n0}) // (2 * {n0})
          设 dp = 计算 {rate0} - {rate1}
          如果 {dp} 不小于 {c.drop_pct}
            设 or2 = {"t": "近 {c.drop_window} 天正确率 {rate1}%，之前 {c.drop_window} 天 {rate0}%，降了 {dp} 个百分点"}
            设 reasons = 列表加项 {reasons} {or2.t}
            如果 {jt} 为空
              设 jt = {or2.t}
            否则
              设 jt = {jt}；{or2.t}
            结束
          结束
        结束
        设 rc = 列表长度 {reasons}
        如果 {rc} 大于 0
          设 so = {"username": "{s.username}", "display_name": "{s.display_name}", "reasons": {reasons}, "last_at": "{la}"}
          设 hits = 列表加项 {hits} {so}
          设 chbody = {chbody}{o.nl}・{s.display_name}（{s.username}）：{jt}
        结束
      结束
    结束
    设 total = 列表长度 {hits}
    如果 {total} 等于 0
      设 ho = {"t": "按现在的规则没有掉队的学生。{rt}"}
      返回 {"status": "empty", "hint": "{ho.t}", "total": 0, "students": [], "rules_text": "{rt}", "chart": "{ho.t}", "context_text": ""}
    结束
    设 oc = {"t": "掉队名单 {total} 人（{rt}）{chbody}"}
    设 ox = {"t": "今天：{today}{o.nl}分析：掉队名单（规则由系统判定，不要自己增减名单）{chbody}{o.nl}{rt}{o.nl}【后端算好的字符图】{o.nl}{oc.t}"}
    返回 {"status": "ok", "hint": "", "total": {total}, "students": {hits}, "rules_text": "{rt}", "chart": "{oc.t}", "context_text": "{ox.t}"}
  结束

  公开 函数 分析上下文 kind student? days? top? learner? current_role? auth_mode? subject?
    设 subject_id = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    如果 {kind} 不等于 trend 且 {kind} 不等于 attribution 且 {kind} 不等于 compare 且 {kind} 不等于 alert
      报错 400 分析类型不对
    结束
    如果 {kind} 等于 trend
      设 r = 调用 学情趋势 student={student} days={days} subject={subject_id}
    否则如果 {kind} 等于 attribution
      设 r = 调用 错题归因 student={student} days={days} top={top} subject={subject_id}
    否则如果 {kind} 等于 compare
      设 r = 调用 学生对比 students={student} subject={subject_id}
    否则
      设 r = 调用 掉队名单 subject={subject_id}
    结束
    设 o = {"z": ""}
    设 ch = {o.z 或}
    设 cx = {o.z 或}
    如果 {r.status} 等于 ok
      设 ch = {r.chart}
      设 cx = {r.context_text}
    结束
    返回 {"status": "{r.status}", "kind": "{kind}", "hint": "{r.hint}", "chart": "{ch}", "context_text": "{cx}"}
  结束
结束
