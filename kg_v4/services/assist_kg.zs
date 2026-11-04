业务 assist_kg
  依赖 kg subject
  用包 db common text

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    设 sid = {r.subject_id}
    返回 {sid}
  结束

  公开 函数 图谱编号前缀 learner? current_role? auth_mode? subject?
    设 sid = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 prefix = {zz 或}
    如果 {sid} 不等于 1
      设 dt = 调用 subject.科目详情 learner={learner} subject_id={sid}
      设 prefix = {dt.code}.
    结束
    返回 {"prefix": "{prefix}"}
  结束

  函数 编号合规 code prefix
    设 msg = {zz 或}
    设 mm = 匹配 {code} ^[A-Za-z0-9][A-Za-z0-9_.-]*$
    设 lg = 截取 {code} 61
    如果 {mm.matched} 不等于 是 或 {lg} 不为空
      设 msg = 编号只能用字母、数字、点、下划线、短横，最长60
      返回 {msg}
    结束
    如果 {prefix} 不为空
      设 okp = 1
      如果 {code} 开头是 {prefix}
        如果 {code} 等于 {prefix}
          设 okp = 0
        结束
      否则
        设 okp = 0
      结束
      如果 {okp} 等于 0
        设 msg = 编号要以「{prefix}」开头
        返回 {msg}
      结束
    结束
    返回 {msg}
  结束

  函数 倒序 lst
    设 tx = {zz 或}
    遍历 x 于 {lst}
      如果 {tx} 为空
        设 tx = {x}
      否则
        设 tx = {x},{tx}
      结束
    结束
    设 rev = 解析JSON [{tx}]
    返回 {rev}
  结束

  函数 成环 pre point edges sid
    设 reach = ,{point},
    设 ex = 调用 kg.取知识点 code={point} subject={sid}
    如果 {ex} 不为空
      设 ds = 调用 kg.列后代 code={point} subject={sid}
      遍历 d 于 {ds.points}
        设 reach = {reach}{d.code},
      结束
    结束
    重复 30 次
      遍历 e 于 {edges}
        如果 {reach} 包含 ,{e.pre_code}, 且 {reach} 不包含 ,{e.point_code},
          设 reach = {reach}{e.point_code},
          设 ex2 = 调用 kg.取知识点 code={e.point_code} subject={sid}
          如果 {ex2} 不为空
            设 ds2 = 调用 kg.列后代 code={e.point_code} subject={sid}
            遍历 d2 于 {ds2.points}
              设 reach = {reach}{d2.code},
            结束
          结束
        结束
      结束
    结束
    如果 {reach} 包含 ,{pre},
      返回 1
    结束
    返回 0
  结束

  公开 函数 校验图谱草稿 payload_json learner? current_role? auth_mode? subject?
    设 sid = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 errors = 解析JSON []
    设 empty = 解析JSON 无
    设 nl = 解析JSON "\n"
    设 kw = 知识点
    设 tw = 条目
    设 ew = 前置边
    设 pl = 解析JSON {payload_json}
    如果 {pl} 为空
      设 jw = 输出不是
      设 msg = {jw} JSON 对象
      设 errors = 列表加项 {errors} {msg}
      返回 {"ok": 0, "errors": {errors}, "normalized": {empty}, "title": "", "preview": ""}
    结束
    设 pts = 解析JSON []
    设 its = 解析JSON []
    设 egs = 解析JSON []
    如果 {pl.points 或} 不为空
      设 lm = 匹配 {pl.points} ^\s*\[
      如果 {lm.matched} 等于 是
        设 pts = {pl.points}
      否则
        设 k1 = points
        设 msg = {k1} 必须是列表
        设 errors = 列表加项 {errors} {msg}
      结束
    结束
    如果 {pl.items 或} 不为空
      设 lm = 匹配 {pl.items} ^\s*\[
      如果 {lm.matched} 等于 是
        设 its = {pl.items}
      否则
        设 k1 = items
        设 msg = {k1} 必须是列表
        设 errors = 列表加项 {errors} {msg}
      结束
    结束
    如果 {pl.edges 或} 不为空
      设 lm = 匹配 {pl.edges} ^\s*\[
      如果 {lm.matched} 等于 是
        设 egs = {pl.edges}
      否则
        设 k1 = edges
        设 msg = {k1} 必须是列表
        设 errors = 列表加项 {errors} {msg}
      结束
    结束
    设 pn = 列表长度 {pts}
    设 itn = 列表长度 {its}
    设 en = 列表长度 {egs}
    设 ec = 列表长度 {errors}
    如果 {ec} 等于 0 且 {pn} 等于 0 且 {itn} 等于 0 且 {en} 等于 0
      设 msg = 知识点、条目、前置边至少要有一项
      设 errors = 列表加项 {errors} {msg}
    结束
    设 w = 一份草稿最多
    如果 {pn} 大于 10
      设 msg = {w} 10 个知识点
      设 errors = 列表加项 {errors} {msg}
    结束
    如果 {itn} 大于 30
      设 msg = {w} 30 个条目
      设 errors = 列表加项 {errors} {msg}
    结束
    如果 {en} 大于 30
      设 msg = {w} 30 条前置边
      设 errors = 列表加项 {errors} {msg}
    结束
    设 ec = 列表长度 {errors}
    如果 {ec} 大于 0
      返回 {"ok": 0, "errors": {errors}, "normalized": {empty}, "title": "", "preview": ""}
    结束
    设 pf = 调用 图谱编号前缀 learner={learner} subject={sid}
    设 prefix = {pf.prefix 或}
    设 seenp = ,
    设 np = 解析JSON []
    设 i = 0
    遍历 p 于 {pts}
      设 i = 计算 {i} + 1
      设 pm = 匹配 {p} ^\x7b
      如果 {pm.matched} 不等于 是
        设 msg = {kw} {i}：格式不对
        设 errors = 列表加项 {errors} {msg}
        继续
      结束
      设 code = 替换 {p.code 或} ^\s+|\s+$
      设 ttl = 替换 {p.title 或} ^\s+|\s+$
      如果 {code} 为空
        设 msg = {kw} {i}：编号不能为空
        设 errors = 列表加项 {errors} {msg}
      否则
        设 cm = 调用 编号合规 code={code} prefix={prefix}
        如果 {cm} 不为空
          设 msg = {kw} {code}：{cm}
          设 errors = 列表加项 {errors} {msg}
        结束
        设 ex = 调用 kg.取知识点 code={code} subject={sid}
        如果 {ex} 不为空
          设 msg = {kw} {code} 已存在
          设 errors = 列表加项 {errors} {msg}
        结束
        如果 {seenp} 包含 ,{code},
          设 msg = {kw} {code} 重复
          设 errors = 列表加项 {errors} {msg}
        结束
        设 seenp = {seenp}{code},
        如果 {ttl} 为空
          设 msg = {kw} {code}：名称不能为空
          设 errors = 列表加项 {errors} {msg}
        结束
        设 l61 = 截取 {ttl} 61
        如果 {l61} 不为空
          设 msg = {kw} {code}：名称最长60字
          设 errors = 列表加项 {errors} {msg}
        结束
      结束
      设 o = {"code": "{code}", "title": "{ttl}"}
      设 np = 列表加项 {np} {o}
    结束
    设 seeni = ,
    设 ni = 解析JSON []
    设 i = 0
    遍历 p 于 {its}
      设 i = 计算 {i} + 1
      设 pm = 匹配 {p} ^\x7b
      如果 {pm.matched} 不等于 是
        设 msg = {tw} {i}：格式不对
        设 errors = 列表加项 {errors} {msg}
        继续
      结束
      设 code = 替换 {p.code 或} ^\s+|\s+$
      设 nm = 替换 {p.name 或} ^\s+|\s+$
      设 pc = 替换 {p.point_code 或} ^\s+|\s+$
      设 af = 替换 {p.after_form 或} ^\s+|\s+$
      设 pv0 = 替换 {p.prev_code 或} ^\s+|\s+$
      如果 {code} 为空
        设 msg = {tw} {i}：编号不能为空
        设 errors = 列表加项 {errors} {msg}
      否则
        设 cm = 调用 编号合规 code={code} prefix={prefix}
        如果 {cm} 不为空
          设 msg = {tw} {code}：{cm}
          设 errors = 列表加项 {errors} {msg}
        结束
        如果 {nm} 为空
          设 msg = {tw} {code}：名称不能为空
          设 errors = 列表加项 {errors} {msg}
        结束
        设 l61 = 截取 {nm} 61
        如果 {l61} 不为空
          设 msg = {tw} {code}：名称最长60字
          设 errors = 列表加项 {errors} {msg}
        结束
        设 l61 = 截取 {af} 61
        如果 {l61} 不为空
          设 msg = {tw} {code}：接在的内容最长60字
          设 errors = 列表加项 {errors} {msg}
        结束
        设 ex = 调用 kg.取条目 code={code} subject={sid}
        如果 {ex} 不为空
          设 msg = {tw} {code} 已存在
          设 errors = 列表加项 {errors} {msg}
        结束
        如果 {seeni} 包含 ,{code},
          设 msg = {tw} {code} 重复
          设 errors = 列表加项 {errors} {msg}
        结束
        设 pok = 0
        如果 {seenp} 包含 ,{pc},
          设 pok = 1
        否则
          设 ex = 调用 kg.取知识点 code={pc} subject={sid}
          如果 {ex} 不为空
            设 pok = 1
          结束
        结束
        如果 {pok} 等于 0
          设 msg = {tw} {code}：所属知识点 {pc} 不在本科目
          设 errors = 列表加项 {errors} {msg}
        结束
        如果 {pv0} 不为空
          设 vok = 0
          如果 {seeni} 包含 ,{pv0},
            设 vok = 1
          否则
            设 ex = 调用 kg.取条目 code={pv0} subject={sid}
            如果 {ex} 不为空
              设 vok = 1
            结束
          结束
          如果 {vok} 等于 0
            设 msg = {tw} {code}：前一个条目 {pv0} 不在本科目
            设 errors = 列表加项 {errors} {msg}
          结束
        结束
        设 seeni = {seeni}{code},
      结束
      设 o = {"code": "{code}", "name": "{nm}", "point_code": "{pc}", "after_form": "{af}", "prev_code": "{pv0}"}
      设 ni = 列表加项 {ni} {o}
    结束
    设 seene = ,
    设 ne = 解析JSON []
    设 i = 0
    遍历 g 于 {egs}
      设 i = 计算 {i} + 1
      设 pm = 匹配 {g} ^\x7b
      如果 {pm.matched} 不等于 是
        设 msg = {ew} {i}：格式不对
        设 errors = 列表加项 {errors} {msg}
        继续
      结束
      设 a = 替换 {g.pre_code 或} ^\s+|\s+$
      设 b = 替换 {g.point_code 或} ^\s+|\s+$
      如果 {a} 为空 或 {b} 为空
        设 msg = {ew} {i}：编号不能为空
        设 errors = 列表加项 {errors} {msg}
        继续
      结束
      如果 {a} 等于 {b}
        设 msg = {ew} {a}→{b}：不能以自己为前置
        设 errors = 列表加项 {errors} {msg}
        继续
      结束
      设 pre_x = 0
      设 po_x = 0
      如果 {seenp} 不包含 ,{a},
        设 ex = 调用 kg.取知识点 code={a} subject={sid}
        如果 {ex} 为空
          设 msg = {ew} {a}→{b}：{kw} {a} 不在本科目
          设 errors = 列表加项 {errors} {msg}
        否则
          设 pre_x = 1
        结束
      结束
      如果 {seenp} 不包含 ,{b},
        设 ex = 调用 kg.取知识点 code={b} subject={sid}
        如果 {ex} 为空
          设 msg = {ew} {a}→{b}：{kw} {b} 不在本科目
          设 errors = 列表加项 {errors} {msg}
        否则
          设 po_x = 1
        结束
      结束
      设 key = ,{a}>{b},
      如果 {seene} 包含 {key}
        设 msg = {ew} {a}→{b} 重复
        设 errors = 列表加项 {errors} {msg}
      否则
        设 seene = {seene}{a}>{b},
      结束
      如果 {pre_x} 等于 1 且 {po_x} 等于 1
        设 lp = 调用 kg.列前置 code={b} subject={sid}
        遍历 q 于 {lp.points}
          如果 {q.code} 等于 {a}
            设 msg = {ew} {a}→{b} 已存在
            设 errors = 列表加项 {errors} {msg}
          结束
        结束
      结束
      设 o = {"pre_code": "{a}", "point_code": "{b}"}
      设 ne = 列表加项 {ne} {o}
    结束
    设 ec = 列表长度 {errors}
    如果 {ec} 等于 0
      遍历 g 于 {ne}
        设 cy = 调用 成环 pre={g.pre_code} point={g.point_code} edges={ne} sid={sid}
        如果 {cy} 等于 1
          设 msg = {ew} {g.pre_code}→{g.point_code} 会形成环
          设 errors = 列表加项 {errors} {msg}
        结束
      结束
    结束
    设 ec = 列表长度 {errors}
    如果 {ec} 大于 0
      返回 {"ok": 0, "errors": {errors}, "normalized": {empty}, "title": "", "preview": ""}
    结束
    设 pn = 列表长度 {np}
    设 itn = 列表长度 {ni}
    设 en = 列表长度 {ne}
    设 jia = 加
    设 body = {zz 或}
    如果 {pn} 大于 0
      设 body = {pn} 个知识点
    结束
    如果 {itn} 大于 0
      如果 {body} 不为空
        设 body = {body}、{itn} 个条目
      否则
        设 body = {itn} 个条目
      结束
    结束
    如果 {en} 大于 0
      如果 {body} 不为空
        设 body = {body}、{en} 条前置边
      否则
        设 body = {en} 条前置边
      结束
    结束
    设 gtitle = {jia} {body}
    设 pv = {zz 或}
    如果 {pn} 大于 0
      设 pv = {pv}{nl}知识点：
      遍历 q 于 {np}
        设 pv = {pv}{nl}・{q.title}（{q.code}）
      结束
    结束
    如果 {itn} 大于 0
      设 pv = {pv}{nl}条目：
      遍历 q 于 {ni}
        设 ln = ・{q.name}（{q.code}），属于 {q.point_code}
        如果 {q.prev_code} 不为空
          设 ln = {ln}，前一个 {q.prev_code}
        结束
        如果 {q.after_form} 不为空
          设 ln = {ln}，接在 {q.after_form} 后
        结束
        设 pv = {pv}{nl}{ln}
      结束
    结束
    如果 {en} 大于 0
      设 pv = {pv}{nl}前置边：
      遍历 q 于 {ne}
        设 pv = {pv}{nl}・{q.pre_code} → {q.point_code}
      结束
    结束
    设 pv = {pv}{nl}编号建后不可改
    设 pv = 替换 {pv} ^\x0a
    设 norm = {"points": {np}, "items": {ni}, "edges": {ne}}
    返回 {"ok": 1, "errors": {errors}, "normalized": {norm}, "title": "{gtitle}", "preview": "{pv}"}
  结束

  公开 函数 执行图谱草稿 payload_json learner? current_role? auth_mode? subject?
    设 sid = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 pl = 解析JSON {payload_json}
    设 out = 解析JSON []
    设 done = 0
    设 total = 0
    设 first = {zz 或}
    设 kw = 知识点
    设 tw = 条目
    设 ew = 前置边
    如果 {pl.points 或} 不为空
      遍历 p 于 {pl.points}
        设 total = 计算 {total} + 1
        设 r = 调用 kg.建知识点 code={p.code} title={p.title} subject={sid} 出错时 e
        设 label = {kw} {p.title}（{p.code}）
        如果 {e} 为空
          设 o = {"type": "point", "code": "{p.code}", "pre_code": "", "point_code": "", "label": "{label}", "ok": 1, "error": "", "created": "", "undo": ""}
          设 done = 计算 {done} + 1
        否则
          设 o = {"type": "point", "code": "{p.code}", "pre_code": "", "point_code": "", "label": "{label}", "ok": 0, "error": "{e.error}", "created": "", "undo": ""}
          如果 {first} 为空
            设 first = {e.error}
          结束
        结束
        设 out = 列表加项 {out} {o}
      结束
    结束
    如果 {pl.items 或} 不为空
      遍历 p 于 {pl.items}
        设 total = 计算 {total} + 1
        设 r = 调用 kg.建条目 code={p.code} name={p.name} point_code={p.point_code} after_form={p.after_form 或} prev_code={p.prev_code 或} subject={sid} 出错时 e
        设 label = {tw} {p.name}（{p.code}）
        如果 {e} 为空
          设 o = {"type": "item", "code": "{p.code}", "pre_code": "", "point_code": "{p.point_code}", "label": "{label}", "ok": 1, "error": "", "created": "", "undo": ""}
          设 done = 计算 {done} + 1
        否则
          设 o = {"type": "item", "code": "{p.code}", "pre_code": "", "point_code": "{p.point_code}", "label": "{label}", "ok": 0, "error": "{e.error}", "created": "", "undo": ""}
          如果 {first} 为空
            设 first = {e.error}
          结束
        结束
        设 out = 列表加项 {out} {o}
      结束
    结束
    如果 {pl.edges 或} 不为空
      遍历 p 于 {pl.edges}
        设 total = 计算 {total} + 1
        设 r = 调用 kg.加前置边 pre_code={p.pre_code} point_code={p.point_code} subject={sid} 出错时 e
        设 label = {ew} {p.pre_code}→{p.point_code}
        如果 {e} 为空
          设 o = {"type": "edge", "code": "{p.pre_code}>{p.point_code}", "pre_code": "{p.pre_code}", "point_code": "{p.point_code}", "label": "{label}", "ok": 1, "error": "", "created": "{r.created}", "undo": ""}
          设 done = 计算 {done} + 1
        否则
          设 o = {"type": "edge", "code": "{p.pre_code}>{p.point_code}", "pre_code": "{p.pre_code}", "point_code": "{p.point_code}", "label": "{label}", "ok": 0, "error": "{e.error}", "created": "", "undo": ""}
          如果 {first} 为空
            设 first = {e.error}
          结束
        结束
        设 out = 列表加项 {out} {o}
      结束
    结束
    返回 {"items": {out}, "done": {done}, "total": {total}, "error": "{first}"}
  结束

  公开 函数 撤销图谱草稿 result_json learner? current_role? auth_mode? subject?
    设 sid = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 rs = 解析JSON {result_json}
    设 its = 解析JSON []
    如果 {rs.items 或} 不为空
      设 its = {rs.items}
    结束
    设 gone_s = ,
    设 del_s = ,
    设 own_e = 解析JSON []
    设 own_i = 解析JSON []
    设 own_p = 解析JSON []
    设 total = 0
    遍历 x 于 {its}
      如果 {x.ok 或} 等于 1
        设 total = 计算 {total} + 1
        如果 {x.undo 或} 为空
          设 key = ,{x.type}:{x.code},
          如果 {x.type} 等于 edge
            如果 {x.created 或} 不等于 1
              设 gone_s = {gone_s}{x.type}:{x.code},
            否则
              设 lp = 调用 kg.列前置 code={x.point_code} subject={sid} 出错时 e
              设 found = 0
              设 isgone = 0
              如果 {e} 不为空
                如果 {e.code} 等于 404
                  设 isgone = 1
                结束
              否则
                遍历 q 于 {lp.points}
                  如果 {q.code} 等于 {x.pre_code}
                    设 found = 1
                  结束
                结束
                如果 {found} 等于 0
                  设 isgone = 1
                结束
              结束
              如果 {isgone} 等于 1
                设 gone_s = {gone_s}{x.type}:{x.code},
              否则
                设 o = {"pre_code": "{x.pre_code}", "point_code": "{x.point_code}", "key": "{key}"}
                设 own_e = 列表加项 {own_e} {o}
              结束
            结束
          结束
          如果 {x.type} 等于 item
            设 tt = 调用 kg.取条目 code={x.code} subject={sid}
            如果 {tt} 为空
              设 gone_s = {gone_s}{x.type}:{x.code},
            否则
              设 o = {"code": "{x.code}", "point_code": "{tt.point_code}", "prev_code": "{tt.prev_code}", "key": "{key}"}
              设 own_i = 列表加项 {own_i} {o}
            结束
          结束
          如果 {x.type} 等于 point
            设 tt = 调用 kg.取知识点 code={x.code} subject={sid}
            如果 {tt} 为空
              设 gone_s = {gone_s}{x.type}:{x.code},
            否则
              设 o = {"code": "{x.code}", "key": "{key}"}
              设 own_p = 列表加项 {own_p} {o}
            结束
          结束
        结束
      结束
    结束
    设 reasons = {zz 或}
    遍历 it 于 {own_i}
      设 rf = 调用 kg.查引用 code={it.code} kind=item subject={sid}
      遍历 rr 于 {rf.refs}
        如果 {rr.source} 不等于 教师助手对话
          设 rem = {rr.n}
          如果 {rr.source} 等于 后一个条目
            遍历 o 于 {own_i}
              如果 {o.prev_code} 等于 {it.code}
                设 rem = 计算 {rem} - 1
              结束
            结束
          结束
          如果 {rem} 大于 0
            设 rt = {it.code}：{rr.source}{rem}
            如果 {reasons} 为空
              设 reasons = {rt}
            否则
              设 reasons = {reasons}；{rt}
            结束
          结束
        结束
      结束
    结束
    遍历 it 于 {own_p}
      设 rf = 调用 kg.查引用 code={it.code} kind=point subject={sid}
      遍历 rr 于 {rf.refs}
        如果 {rr.source} 不等于 教师助手对话
          设 rem = {rr.n}
          如果 {rr.source} 等于 下挂条目
            遍历 o 于 {own_i}
              如果 {o.point_code} 等于 {it.code}
                设 rem = 计算 {rem} - 1
              结束
            结束
          结束
          如果 {rr.source} 等于 前置边
            遍历 o 于 {own_e}
              如果 {o.pre_code} 等于 {it.code} 或 {o.point_code} 等于 {it.code}
                设 rem = 计算 {rem} - 1
              结束
            结束
          结束
          如果 {rem} 大于 0
            设 rt = {it.code}：{rr.source}{rem}
            如果 {reasons} 为空
              设 reasons = {rt}
            否则
              设 reasons = {reasons}；{rt}
            结束
          结束
        结束
      结束
    结束
    如果 {reasons} 不为空
      设 lg = 调用 subject.取界面语言 username={learner}
      如果 {lg.lang 或} 等于 ja
        报错 409 知識ポイントまたは項目が参照されているため取り消せません（{reasons}）
      结束
      报错 409 知识点或条目已被引用，不能撤销（{reasons}）
    结束
    设 errl = 解析JSON []
    设 first = {zz 或}
    遍历 x 于 {own_e}
      设 rr = 调用 kg.删前置边 pre_code={x.pre_code} point_code={x.point_code} subject={sid} 出错时 e
      如果 {e} 为空
        设 del_s = {del_s}{x.key}
      否则
        如果 {e.code} 等于 404
          设 gone_s = {gone_s}{x.key}
        否则
          设 o = {"key": "{x.key}", "error": "{e.error}"}
          设 errl = 列表加项 {errl} {o}
          如果 {first} 为空
            设 first = {e.error}
          结束
        结束
      结束
    结束
    设 revi = 调用 倒序 lst={own_i}
    遍历 x 于 {revi}
      设 rr = 调用 kg.删条目 code={x.code} subject={sid} 出错时 e
      如果 {e} 为空
        设 del_s = {del_s}{x.key}
      否则
        如果 {e.code} 等于 404
          设 gone_s = {gone_s}{x.key}
        否则
          设 o = {"key": "{x.key}", "error": "{e.error}"}
          设 errl = 列表加项 {errl} {o}
          如果 {first} 为空
            设 first = {e.error}
          结束
        结束
      结束
    结束
    设 revp = 调用 倒序 lst={own_p}
    遍历 x 于 {revp}
      设 rr = 调用 kg.删知识点 code={x.code} subject={sid} 出错时 e
      如果 {e} 为空
        设 del_s = {del_s}{x.key}
      否则
        如果 {e.code} 等于 404
          设 gone_s = {gone_s}{x.key}
        否则
          设 o = {"key": "{x.key}", "error": "{e.error}"}
          设 errl = 列表加项 {errl} {o}
          如果 {first} 为空
            设 first = {e.error}
          结束
        结束
      结束
    结束
    设 out = 解析JSON []
    设 undone = 0
    遍历 x 于 {its}
      设 u = {x.undo 或}
      设 er = {x.error 或}
      如果 {x.ok 或} 等于 1 且 {u} 为空
        设 key = ,{x.type}:{x.code},
        如果 {gone_s} 包含 {key}
          设 u = gone
        否则如果 {del_s} 包含 {key}
          设 u = deleted
        否则
          遍历 q 于 {errl}
            如果 {q.key} 等于 {key}
              设 er = {q.error}
            结束
          结束
        结束
        如果 {u} 不为空
          设 undone = 计算 {undone} + 1
        结束
      结束
      设 o = {"type": "{x.type}", "code": "{x.code}", "pre_code": "{x.pre_code 或}", "point_code": "{x.point_code 或}", "label": "{x.label 或}", "ok": {x.ok 或 0}, "error": "{er}", "created": "{x.created 或}", "undo": "{u}"}
      设 out = 列表加项 {out} {o}
    结束
    返回 {"items": {out}, "undone": {undone}, "total": {total}, "error": "{first}"}
  结束
结束
