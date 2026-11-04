业务 assist_setting
  依赖 assist_common teacher_rules subject
  用包 db common text

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {"subject_id": {r.subject_id}}
  结束

  公开 函数 设定候选 learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 lst = 调用 teacher_rules.列设定 subject={sid}
    设 total = 列表长度 {lst.items}
    设 skipn = 计算 最大(0, {total} - 40)
    设 editable = []
    设 readonly = []
    设 k = 0
    遍历 it 于 {lst.items}
      设 k = 计算 {k} + 1
      如果 {k} 大于 {skipn}
        设 g = 调用 teacher_rules.取设定 setting_id={it.id} subject={sid}
        如果 {g.subject_id} 等于 0
          设 c = 截取 {g.content} 1 60
          设 one = {"id": {g.id}, "kind": "{g.kind}", "content": "{c}"}
          设 readonly = 列表加项 {readonly} {one}
        否则
          设 c = 截取 {g.content} 1 200
          设 one = {"id": {g.id}, "kind": "{g.kind}", "student": "{g.student}", "keywords": "{g.keywords}", "content": "{c}", "enabled": {g.enabled}}
          设 editable = 列表加项 {editable} {one}
        结束
      结束
    结束
    返回 {"editable": {editable}, "readonly": {readonly}}
  结束

  公开 函数 校验设定草稿 payload_json learner? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 p = 解析JSON {payload_json}
    如果 {p} 为空
      返回 {"ok": 0, "errors": ["输出不是 JSON 对象"], "normalized": {}, "title": "", "preview": ""}
    结束
    设 nlo = {"n": "\n"}
    设 nl = {nlo.n}
    设 errors = []
    设 ns = []
    设 preview = {zz 或}
    设 seen = x
    如果 {p.settings 或} 为空
      设 m = settings不能为空
      设 errors = 列表加项 {errors} {m}
    否则
      设 n = 列表长度 {p.settings}
      如果 {n} 大于 10
        设 m = 一份草稿最多10条设定
        设 errors = 列表加项 {errors} {m}
      否则
        设 i = 0
        遍历 st 于 {p.settings}
          设 i = 计算 {i} + 1
          设 n0 = 列表长度 {errors}
          设 isobj = 匹配 {st} ^\x7b
          如果 {isobj.matched} 不等于 是
            设 m = 第{i}条：格式不对
            设 errors = 列表加项 {errors} {m}
            继续
          结束
          如果 {st.scope 或} 不为空
            设 m = 第{i}条：不允许出现字段scope
            设 errors = 列表加项 {errors} {m}
          结束
          如果 {st.subject_id 或} 不为空
            设 m = 第{i}条：不允许出现字段subject_id
            设 errors = 列表加项 {errors} {m}
          结束
          如果 {st.setting_id 或} 不为空
            设 m = 第{i}条：不允许出现字段setting_id
            设 errors = 列表加项 {errors} {m}
          结束
          如果 {st.enabled 或} 不为空
            设 m = 第{i}条：不允许出现字段enabled
            设 errors = 列表加项 {errors} {m}
          结束
          如果 {st.version 或} 不为空
            设 m = 第{i}条：不允许出现字段version
            设 errors = 列表加项 {errors} {m}
          结束
          如果 {st.author 或} 不为空
            设 m = 第{i}条：不允许出现字段author
            设 errors = 列表加项 {errors} {m}
          结束
          设 tid = {st.target_id 或}
          设 op = add
          设 skip = 0
          设 cur = {}
          如果 {tid} 不为空
            设 mt = 匹配 {tid} ^[1-9][0-9]*$
            如果 {mt.matched} 不等于 是
              设 skip = 1
              设 m = 第{i}条：target_id不合法
              设 errors = 列表加项 {errors} {m}
            否则
              如果 {seen} 包含 x{tid}x
                设 skip = 1
                设 m = 第{i}条：设定#{tid}重复出现
                设 errors = 列表加项 {errors} {m}
              否则
                设 seen = {seen}{tid}x
                设 cur = 调用 teacher_rules.取设定 setting_id={tid} subject={sid} 出错时 e
                如果 {e} 不为空
                  设 skip = 1
                  设 m = 第{i}条：没有编号{tid}的设定
                  设 errors = 列表加项 {errors} {m}
                否则如果 {cur.subject_id} 等于 0
                  设 skip = 1
                  设 m = 第{i}条：设定#{tid}是全部科目的设定，请到AI老师设定页由负责人改
                  设 errors = 列表加项 {errors} {m}
                否则
                  设 op = edit
                结束
              结束
            结束
          结束
          如果 {skip} 等于 1
            继续
          结束
          设 kind = {st.kind 或}
          设 student = {st.student 或}
          设 kw = {st.keywords 或}
          设 once = {st.once 或}
          如果 {op} 等于 edit
            如果 {kind} 为空
              设 kind = {cur.kind}
            结束
            如果 {student} 为空
              设 student = {cur.student}
            结束
            如果 {kw} 为空
              设 kw = {cur.keywords}
            结束
            如果 {once} 为空
              设 once = {cur.once}
            结束
          结束
          设 mk = 匹配 {kw} ^\x5b
          如果 {mk.matched} 等于 是
            设 kwl = 解析JSON {kw}
            设 kw = {nn 或}
            遍历 x 于 {kwl}
              如果 {kw} 为空
                设 kw = {x}
              否则
                设 kw = {kw},{x}
              结束
            结束
          结束
          如果 {kind} 不等于 memory 且 {kind} 不等于 note 且 {kind} 不等于 card
            设 m = 第{i}条：种类只能是memory、note、card
            设 errors = 列表加项 {errors} {m}
          结束
          设 content = {st.content 或}
          设 content = 替换 {content} ^\s+|\s+$
          如果 {content} 为空
            设 m = 第{i}条：内容不能为空
            设 errors = 列表加项 {errors} {m}
          否则
            设 over = 截取 {content} 1001
            如果 {over} 不为空
              设 m = 第{i}条：内容超过1000字
              设 errors = 列表加项 {errors} {m}
            结束
          结束
          如果 {kind} 等于 card 且 {kw} 为空
            设 m = 第{i}条：关键词卡要写关键词
            设 errors = 列表加项 {errors} {m}
          结束
          如果 {kind} 等于 note 且 ({once} 等于 1 或 {once} 等于 true 或 {once} 等于 True)
            设 once = 1
          否则
            设 once = 0
          结束
          设 su = {nn 或}
          设 sn = {nn 或}
          如果 {student} 不为空
            设 mr = 调用 assist_common.匹配学生 name={student} subject={sid}
            如果 {mr.status} 等于 one
              设 su = {mr.username}
              设 sn = {mr.display_name}
            否则如果 {mr.status} 等于 many
              设 cl = {nn 或}
              遍历 cc 于 {mr.candidates}
                设 cl = {cl}{cc.display_name}（{cc.username}）、
              结束
              设 cl = 替换 {cl} 、$
              设 m = 第{i}条：「{student}」找到多位：{cl}，你指哪一位？
              设 errors = 列表加项 {errors} {m}
            否则
              设 m = 第{i}条：没有找到叫「{student}」的学生
              设 errors = 列表加项 {errors} {m}
            结束
          结束
          设 n1 = 列表长度 {errors}
          如果 {n1} 等于 {n0}
            设 one = {"op": "{op}", "target_id": "{tid}", "kind": "{kind}", "content": "{content}", "student": "{su}", "student_name": "{sn}", "keywords": "{kw}", "once": {once}}
            设 ns = 列表加项 {ns} {one}
            设 kn = 记忆
            如果 {kind} 等于 note
              设 kn = 作者注
            否则如果 {kind} 等于 card
              设 kn = 关键词卡
            结束
            设 sc = 全班
            如果 {su} 不为空
              设 sc = 给{sn}
            结束
            设 kwt = 无
            如果 {kw} 不为空
              设 kwt = {kw}
            结束
            设 ot = 否
            如果 {once} 等于 1
              设 ot = 是
            结束
            如果 {op} 等于 add
              设 pv = 第{i}条：新建{kn}（{sc}）：{content}{nl}关键词：{kwt}；只用于下一条：{ot}
            否则
              设 oc = 截取 {cur.content} 1 100
              设 pv = 第{i}条：修改设定#{tid}（{kn}，{sc}）{nl}改前：{oc}{nl}改后：{content}{nl}关键词：{kwt}；只用于下一条：{ot}
            结束
            如果 {preview} 为空
              设 preview = {pv}
            否则
              设 preview = {preview}{nl}{pv}
            结束
          结束
        结束
      结束
    结束
    设 pre = 范围：本科目（助手不改「全部科目」的设定）
    如果 {preview} 为空
      设 preview = {pre}
    否则
      设 preview = {preview}{nl}{pre}
    结束
    设 ne = 列表长度 {errors}
    设 ok = 0
    设 normalized = {}
    如果 {ne} 等于 0
      设 ok = 1
      设 normalized = {"settings": {ns}}
    结束
    设 title = {p.title 或}
    如果 {title} 为空
      设 cnt = 列表长度 {ns}
      设 title = 改{cnt}条AI老师设定
    结束
    返回 {"ok": {ok}, "errors": {errors}, "normalized": {normalized}, "title": "{title}", "preview": "{preview}"}
  结束

  公开 函数 执行设定草稿 payload_json current_user current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 p = 解析JSON {payload_json}
    设 items = []
    设 snap = []
    设 done = 0
    设 total = 0
    设 err = {nn 或}
    遍历 st 于 {p.settings}
      设 total = 计算 {total} + 1
      设 kn = 记忆
      如果 {st.kind 或} 等于 note
        设 kn = 作者注
      否则如果 {st.kind 或} 等于 card
        设 kn = 关键词卡
      结束
      设 sc = 全班
      如果 {st.student_name 或} 不为空
        设 sc = 给{st.student_name}
      否则如果 {st.student 或} 不为空
        设 sc = 给{st.student}
      结束
      如果 {st.op 或} 等于 edit
        设 label = 修改{kn}（{sc}）
        设 cur = 调用 teacher_rules.取设定 setting_id={st.target_id} subject={sid} 出错时 e1
        如果 {e1} 不为空
          设 one = {"op": "edit", "setting_id": "{st.target_id}", "label": "{label}", "ok": 0, "error": "{e1.error}", "written": {}, "undo": ""}
          设 items = 列表加项 {items} {one}
          如果 {err} 为空
            设 err = {e1.error}
          结束
        否则如果 {cur.subject_id} 等于 0
          设 msg = 设定#{st.target_id}是全部科目的设定，助手不能改
          设 one = {"op": "edit", "setting_id": "{st.target_id}", "label": "{label}", "ok": 0, "error": "{msg}", "written": {}, "undo": ""}
          设 items = 列表加项 {items} {one}
          如果 {err} 为空
            设 err = {msg}
          结束
        否则
          设 w = 调用 teacher_rules.保存设定 setting_id={st.target_id} kind={st.kind} content={st.content} current_user={current_user} student={st.student 或} keywords={st.keywords 或} once={st.once 或} subject={sid} 出错时 e2
          如果 {e2} 不为空
            设 one = {"op": "edit", "setting_id": "{st.target_id}", "label": "{label}", "ok": 0, "error": "{e2.error}", "written": {}, "undo": ""}
            设 items = 列表加项 {items} {one}
            如果 {err} 为空
              设 err = {e2.error}
            结束
          否则
            设 done = 计算 {done} + 1
            设 one = {"op": "edit", "setting_id": {w.id}, "label": "{label}", "ok": 1, "error": "", "written": {"kind": "{w.kind}", "student": "{w.student}", "keywords": "{w.keywords}", "content": "{w.content}", "once": {w.once}, "enabled": {w.enabled}}, "undo": ""}
            设 items = 列表加项 {items} {one}
            设 sn1 = {"setting_id": {w.id}, "before": {"kind": "{cur.kind}", "student": "{cur.student}", "keywords": "{cur.keywords}", "content": "{cur.content}", "once": {cur.once}, "enabled": {cur.enabled}}}
            设 snap = 列表加项 {snap} {sn1}
          结束
        结束
      否则
        设 label = 新建{kn}（{sc}）
        设 w = 调用 teacher_rules.保存设定 kind={st.kind} content={st.content} current_user={current_user} student={st.student 或} keywords={st.keywords 或} once={st.once 或} subject={sid} 出错时 e3
        如果 {e3} 不为空
          设 one = {"op": "add", "setting_id": "", "label": "{label}", "ok": 0, "error": "{e3.error}", "written": {}, "undo": ""}
          设 items = 列表加项 {items} {one}
          如果 {err} 为空
            设 err = {e3.error}
          结束
        否则
          设 done = 计算 {done} + 1
          设 one = {"op": "add", "setting_id": {w.id}, "label": "{label}", "ok": 1, "error": "", "written": {"kind": "{w.kind}", "student": "{w.student}", "keywords": "{w.keywords}", "content": "{w.content}", "once": {w.once}, "enabled": {w.enabled}}, "undo": ""}
          设 items = 列表加项 {items} {one}
        结束
      结束
    结束
    设 ns = 列表长度 {snap}
    如果 {ns} 等于 0
      返回 {"items": {items}, "snapshot": "", "done": {done}, "total": {total}, "error": "{err}"}
    结束
    返回 {"items": {items}, "snapshot": {"settings": {snap}}, "done": {done}, "total": {total}, "error": "{err}"}
  结束

  公开 函数 撤销设定草稿 result_json snapshot_json current_user current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sr.subject_id}
    设 res = 解析JSON {result_json}
    设 snap = 解析JSON {snapshot_json}
    设 blocks = {nn 或}
    设 nchg = 0
    设 gone = x
    设 total = 0
    遍历 it 于 {res.items}
      如果 {it.ok} 等于 1
        设 total = 计算 {total} + 1
        如果 {it.undo 或} 为空
          设 cur = 调用 teacher_rules.取设定 setting_id={it.setting_id} subject={sid} 出错时 e
          设 m = {nn 或}
          如果 {e} 不为空
            如果 {e.code} 等于 404
              如果 {it.op} 等于 add
                设 gone = {gone}{it.setting_id}x
              否则
                设 m = 设定#{it.setting_id}已被删除
              结束
            否则
              设 nchg = 计算 {nchg} + 1
              设 m = 设定#{it.setting_id}在确认后被改过
            结束
          否则如果 {cur.subject_id} 不等于 {sid}
            设 nchg = 计算 {nchg} + 1
            设 m = 设定#{it.setting_id}已被改成全部科目
          否则
            设 diff = 0
            如果 {cur.kind} 不等于 {it.written.kind}
              设 diff = 1
            结束
            如果 {cur.student} 不等于 {it.written.student}
              设 diff = 1
            结束
            如果 {cur.keywords} 不等于 {it.written.keywords}
              设 diff = 1
            结束
            如果 {cur.content} 不等于 {it.written.content}
              设 diff = 1
            结束
            如果 {cur.once} 不等于 {it.written.once}
              设 diff = 1
            结束
            如果 {cur.enabled} 不等于 {it.written.enabled}
              设 diff = 1
            结束
            如果 {diff} 等于 1
              设 nchg = 计算 {nchg} + 1
              设 m = 设定#{it.setting_id}在确认后被改过
            结束
          结束
          如果 {m} 不为空
            如果 {blocks} 为空
              设 blocks = {m}
            否则
              设 blocks = {blocks}；{m}
            结束
          结束
        结束
      结束
    结束
    如果 {blocks} 不为空
      设 lg = 调用 subject.取界面语言 username={current_user}
      如果 {nchg} 大于 0
        如果 {lg.lang} 等于 ja
          报错 409 設定が変更されているため取り消せません（{blocks}）
        结束
        报错 409 设定已被改动，不能撤销（{blocks}）
      否则
        如果 {lg.lang} 等于 ja
          报错 409 設定が削除されているため復元できません（{blocks}）
        结束
        报错 409 设定已被删除，不能恢复（{blocks}）
      结束
    结束
    设 newitems = []
    设 undone = 0
    设 err = {nn 或}
    遍历 it 于 {res.items}
      如果 {it.ok} 等于 1 且 {it.undo 或} 为空
        如果 {it.op} 等于 add
          如果 {gone} 包含 x{it.setting_id}x
            设 it.undo = gone
            设 undone = 计算 {undone} + 1
          否则
            设 dr = 调用 teacher_rules.删除设定 setting_id={it.setting_id} subject={sid} 出错时 e4
            如果 {e4} 为空
              设 it.undo = deleted
              设 undone = 计算 {undone} + 1
            否则如果 {e4.code} 等于 404
              设 it.undo = gone
              设 undone = 计算 {undone} + 1
            否则
              设 it.error = {e4.error}
              如果 {err} 为空
                设 err = {e4.error}
              结束
            结束
          结束
        否则
          设 bf = {}
          如果 {snap.settings 或} 不为空
            遍历 sn 于 {snap.settings}
              如果 {sn.setting_id} 等于 {it.setting_id}
                设 bf = {sn.before}
              结束
            结束
          结束
          如果 {bf} 为空
            设 it.error = 没有改前值
            如果 {err} 为空
              设 err = 没有改前值
            结束
          否则
            设 sv = 调用 teacher_rules.保存设定 setting_id={it.setting_id} kind={bf.kind} content={bf.content} current_user={current_user} student={bf.student} keywords={bf.keywords} once={bf.once} subject={sid} 出错时 e5
            如果 {e5} 为空
              设 it.undo = restored
              设 undone = 计算 {undone} + 1
            否则
              设 it.error = {e5.error}
              如果 {err} 为空
                设 err = {e5.error}
              结束
            结束
          结束
        结束
      结束
      设 newitems = 列表加项 {newitems} {it}
    结束
    返回 {"items": {newitems}, "undone": {undone}, "total": {total}, "error": "{err}"}
  结束
结束
