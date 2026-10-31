业务 assist_common
  依赖 account subject kg
  用包 db common text

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {r}
  结束

  公开 函数 学生范围 learner? current_role? auth_mode? subject?
    设 blank = {zz 或}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 al = 调用 account.列学生
    设 ss = 调用 subject.列科目学生 subject_id={subject_id}
    设 cnt = 0
    设 out = {blank}
    遍历 s 于 {al.students}
      设 hit = 0
      遍历 x 于 {ss.students}
        如果 {x.learner} 等于 {s.username}
          设 hit = 1
        结束
      结束
      如果 {hit} 等于 1
        设 cnt = 计算 {cnt} + 1
        设 it = {"username": "{s.username}", "display_name": "{s.display_name}", "status": "{s.status}", "last_at": "{s.last_at}"}
        如果 {out} 为空
          设 out = {it}
        否则
          设 out = {out},{it}
        结束
      结束
    结束
    返回 {"total": {cnt}, "students": [{out}]}
  结束

  公开 函数 匹配学生 name learner? current_role? auth_mode? subject?
    设 blank = {zz 或}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    设 r = 调用 学生范围 subject={subject_id}
    设 roster = {blank}
    设 i = 0
    遍历 s 于 {r.students}
      如果 {i} 小于 10
        如果 {roster} 为空
          设 roster = {s.display_name}（{s.username}）
        否则
          设 roster = {roster}、{s.display_name}（{s.username}）
        结束
        设 i = 计算 {i} + 1
      结束
    结束
    如果 {name} 为空
      返回 {"status": "none", "username": "", "display_name": "", "candidates": [], "roster": "{roster}"}
    结束
    设 n = 替换 {name} ^\s+|\s+$
    如果 {n} 为空
      返回 {"status": "none", "username": "", "display_name": "", "candidates": [], "roster": "{roster}"}
    结束
    设 n = 替换 {n} 同学$
    设 n = 替换 {n} ^\s+|\s+$
    如果 {n} 为空
      返回 {"status": "none", "username": "", "display_name": "", "candidates": [], "roster": "{roster}"}
    结束
    设 pa1 = {"s": "{n}"}
    设 ln = 查一值表 app.db assist_common_lower {pa1}
    设 pa2 = {"t": "{n}"}
    设 nlen = 查一值表 app.db assist_common_len {pa2}
    设 n1 = 0
    设 n2 = 0
    设 n3 = 0
    设 c1 = {blank}
    设 c2 = {blank}
    设 c3 = {blank}
    设 u1 = {blank}
    设 d1 = {blank}
    设 u2 = {blank}
    设 d2 = {blank}
    设 u3 = {blank}
    设 d3 = {blank}
    遍历 s 于 {r.students}
      设 pa3 = {"s": "{s.username}"}
      设 lu = 查一值表 app.db assist_common_lower {pa3}
      设 pa4 = {"t": "{s.display_name}"}
      设 dl = 查一值表 app.db assist_common_len {pa4}
      设 it = {"username": "{s.username}", "display_name": "{s.display_name}", "status": "{s.status}"}
      如果 {lu} 等于 {ln}
        如果 {c1} 为空
          设 c1 = {it}
        否则如果 {n1} 小于 5
          设 c1 = {c1},{it}
        结束
        如果 {n1} 等于 0
          设 u1 = {s.username}
          设 d1 = {s.display_name}
        结束
        设 n1 = 计算 {n1} + 1
      结束
      如果 {s.display_name} 等于 {n}
        如果 {c2} 为空
          设 c2 = {it}
        否则如果 {n2} 小于 5
          设 c2 = {c2},{it}
        结束
        如果 {n2} 等于 0
          设 u2 = {s.username}
          设 d2 = {s.display_name}
        结束
        设 n2 = 计算 {n2} + 1
      结束
      设 f3 = 0
      如果 {s.display_name} 包含 {n}
        设 f3 = 1
      结束
      如果 {dl} 不小于 2 且 {n} 包含 {s.display_name}
        设 f3 = 1
      结束
      如果 {nlen} 不小于 2 且 {lu} 包含 {ln}
        设 f3 = 1
      结束
      如果 {f3} 等于 1
        如果 {c3} 为空
          设 c3 = {it}
        否则如果 {n3} 小于 5
          设 c3 = {c3},{it}
        结束
        如果 {n3} 等于 0
          设 u3 = {s.username}
          设 d3 = {s.display_name}
        结束
        设 n3 = 计算 {n3} + 1
      结束
    结束
    设 cnt = 0
    设 un = {blank}
    设 dn = {blank}
    设 cs = {blank}
    如果 {n1} 大于 0
      设 cnt = {n1}
      设 un = {u1}
      设 dn = {d1}
      设 cs = {c1}
    否则如果 {n2} 大于 0
      设 cnt = {n2}
      设 un = {u2}
      设 dn = {d2}
      设 cs = {c2}
    否则如果 {n3} 大于 0
      设 cnt = {n3}
      设 un = {u3}
      设 dn = {d3}
      设 cs = {c3}
    结束
    如果 {cnt} 等于 0
      返回 {"status": "none", "username": "", "display_name": "", "candidates": [], "roster": "{roster}"}
    结束
    如果 {cnt} 等于 1
      返回 {"status": "one", "username": "{un}", "display_name": "{dn}", "candidates": [], "roster": "{roster}"}
    结束
    返回 {"status": "many", "username": "", "display_name": "", "candidates": [{cs}], "roster": "{roster}"}
  结束

  公开 函数 匹配知识点 keyword learner? current_role? auth_mode? subject?
    设 blank = {zz 或}
    设 sj = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 subject_id = {sj.subject_id}
    如果 {keyword} 为空
      返回 {"status": "none", "code": "", "title": "", "candidates": [], "total": 0}
    结束
    设 k = 替换 {keyword} ^\s+|\s+$
    如果 {k} 为空
      返回 {"status": "none", "code": "", "title": "", "candidates": [], "total": 0}
    结束
    设 k = 替换 {k} ^[～~〜]+
    如果 {k} 为空
      返回 {"status": "none", "code": "", "title": "", "candidates": [], "total": 0}
    结束
    设 k = 替换 {k} 的用法$
    设 k = 替换 {k} ^\s+|\s+$
    如果 {k} 为空
      返回 {"status": "none", "code": "", "title": "", "candidates": [], "total": 0}
    结束
    设 pa5 = {"s": "{k}"}
    设 lk = 查一值表 app.db assist_common_lower {pa5}
    设 pa6 = {"t": "{k}"}
    设 klen = 查一值表 app.db assist_common_len {pa6}
    设 r = 调用 kg.列知识点 subject={subject_id}
    设 n1 = 0
    设 n2 = 0
    设 n3 = 0
    设 n4 = 0
    设 c1 = {blank}
    设 c2 = {blank}
    设 c3 = {blank}
    设 c4 = {blank}
    设 a1 = {blank}
    设 b1 = {blank}
    设 a2 = {blank}
    设 b2 = {blank}
    设 a3 = {blank}
    设 b3 = {blank}
    设 a4 = {blank}
    设 b4 = {blank}
    遍历 p 于 {r.points}
      设 pa7 = {"s": "{p.code}"}
      设 lc = 查一值表 app.db assist_common_lower {pa7}
      设 pa8 = {"t": "{p.title}"}
      设 tl = 查一值表 app.db assist_common_len {pa8}
      设 it = {"code": "{p.code}", "title": "{p.title}"}
      如果 {lc} 等于 {lk}
        如果 {c1} 为空
          设 c1 = {it}
        否则如果 {n1} 小于 5
          设 c1 = {c1},{it}
        结束
        如果 {n1} 等于 0
          设 a1 = {p.code}
          设 b1 = {p.title}
        结束
        设 n1 = 计算 {n1} + 1
      结束
      如果 {p.title} 等于 {k}
        如果 {c2} 为空
          设 c2 = {it}
        否则如果 {n2} 小于 5
          设 c2 = {c2},{it}
        结束
        如果 {n2} 等于 0
          设 a2 = {p.code}
          设 b2 = {p.title}
        结束
        设 n2 = 计算 {n2} + 1
      结束
      设 f3 = 0
      如果 {p.title} 包含 {k}
        设 f3 = 1
      结束
      如果 {tl} 不小于 2 且 {k} 包含 {p.title}
        设 f3 = 1
      结束
      如果 {f3} 等于 1
        如果 {c3} 为空
          设 c3 = {it}
        否则如果 {n3} 小于 5
          设 c3 = {c3},{it}
        结束
        如果 {n3} 等于 0
          设 a3 = {p.code}
          设 b3 = {p.title}
        结束
        设 n3 = 计算 {n3} + 1
      结束
    结束
    如果 {n1} 等于 0 且 {n2} 等于 0 且 {n3} 等于 0
      设 its = 调用 kg.列条目 subject={subject_id}
      设 seen = ,
      遍历 x 于 {its.items}
        设 pa9 = {"t": "{x.name}"}
        设 xl = 查一值表 app.db assist_common_len {pa9}
        设 hit = 0
        如果 {x.name} 包含 {k}
          设 hit = 1
        结束
        如果 {xl} 不小于 2 且 {k} 包含 {x.name}
          设 hit = 1
        结束
        如果 {hit} 等于 1
          如果 {seen} 不包含 ,{x.point_code},
            设 seen = {seen}{x.point_code},
            设 pp = 调用 kg.取知识点 code={x.point_code} subject={subject_id}
            如果 {pp} 不为空
              设 it = {"code": "{x.point_code}", "title": "{pp.title}"}
              如果 {c4} 为空
                设 c4 = {it}
              否则如果 {n4} 小于 5
                设 c4 = {c4},{it}
              结束
              如果 {n4} 等于 0
                设 a4 = {x.point_code}
                设 b4 = {pp.title}
              结束
              设 n4 = 计算 {n4} + 1
            结束
          结束
        结束
      结束
    结束
    设 cnt = 0
    设 cc = {blank}
    设 ct = {blank}
    设 cs = {blank}
    如果 {n1} 大于 0
      设 cnt = {n1}
      设 cc = {a1}
      设 ct = {b1}
      设 cs = {c1}
    否则如果 {n2} 大于 0
      设 cnt = {n2}
      设 cc = {a2}
      设 ct = {b2}
      设 cs = {c2}
    否则如果 {n3} 大于 0
      设 cnt = {n3}
      设 cc = {a3}
      设 ct = {b3}
      设 cs = {c3}
    否则如果 {n4} 大于 0
      设 cnt = {n4}
      设 cc = {a4}
      设 ct = {b4}
      设 cs = {c4}
    结束
    如果 {cnt} 等于 0
      返回 {"status": "none", "code": "", "title": "", "candidates": [], "total": 0}
    结束
    如果 {cnt} 等于 1
      返回 {"status": "one", "code": "{cc}", "title": "{ct}", "candidates": [], "total": 1}
    结束
    返回 {"status": "many", "code": "", "title": "", "candidates": [{cs}], "total": {cnt}}
  结束
结束
