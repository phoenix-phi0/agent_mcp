业务 lesson
  依赖 kg subject
  用包 common db text doc data

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {"subject_id": {r.subject_id}}
  结束

  函数 编号前缀检查 subject_id code
    如果 {subject_id} 等于 1
      返回 {"ok": 1}
    结束
    设 sc = 查一值 app.db lesson_subject_code subject_id={subject_id}
    如果 {sc} 为空
      报错 400 编号要以「<编码>.」开头
    结束
    设 m = 匹配 {code} ^[a-z][a-z0-9_]*\.[A-Za-z0-9_-]+$
    如果 {m.matched} 不等于 是
      报错 400 编号要以「{sc}.」开头
    结束
    设 pre = {sc}.
    如果 {code} 开头是 {pre}
      返回 {"ok": 1}
    结束
    报错 400 编号要以「{sc}.」开头
  结束

  公开 函数 列系列 learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {total, series}，series 是 [{code, name, intro, source, license, sort_order}]，只含 sort_order 不小于 0 的系列，按 sort_order 升序、id 升序
    # 查 lesson_series 中 sort_order 不小于 0 的行，按 sort_order 升序、id 升序
    设 rows = 查询 app.db lesson_series_list subject_id={sj.subject_id}
    设 n = 列表长度 {rows}
    设 out.total = {n}
    设 out.series = {rows}
    返回 {out}
  结束

  公开 函数 取当前系列 learner current_role? auth_mode? subject?
    # 返回 {learner, series_code, name, is_default}；is_default 为 1 表示没选或所选系列已不可用，用了默认系列 hanabira
    # 按 learner 查 lesson_pref 一行
    # 有记录时，按其 series_code 查 lesson_series，存在且 sort_order 不小于 0，则返回 {"learner": learner, "series_code": 该编号, "name": 该系列 name, "is_default": 0}
    # 否则按 hanabira 查 lesson_series，name 取其 name，没有这行时 name 取 "hanabira"
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    设 pref = 查一行 app.db lesson_pref_get learner={learner} subject_id={sid}
    如果 {pref} 不为空
      设 s = 查一行 app.db lesson_series_get_subject code={pref.series_code} subject_id={sid}
      如果 {s} 不为空
        如果 {s.sort_order} 不小于 0
          设 out.learner = {learner}
          设 out.series_code = {s.code}
          设 out.name = {s.name}
          设 out.is_default = 0
          返回 {out}
        结束
      结束
    结束
    设 dname = hanabira
    设 dcode = hanabira
    如果 {sid} 等于 1
      设 h = 查一行 app.db lesson_series_get_subject code=hanabira subject_id=1
      如果 {h} 不为空
        设 dname = {h.name}
      结束
    否则
      设 fs = 查一行 app.db lesson_series_first subject_id={sid}
      如果 {fs} 为空
        设 out.learner = {learner}
        设 out.series_code = {zz 或}
        设 out.name = {zz 或}
        设 out.is_default = 1
        返回 {out}
      结束
      设 dcode = {fs.code}
      设 dname = {fs.name}
    结束
    设 out.learner = {learner}
    设 out.series_code = {dcode}
    设 out.name = {dname}
    设 out.is_default = 1
    返回 {out}
  结束

  公开 函数 选择系列 learner series_code current_role? auth_mode? subject?
    # 返回 {ok, learner, series_code}
    # 报错 404 没有这个系列
    # 按 series_code 查 lesson_series，查不到或 sort_order 小于 0，报错 404 没有这个系列
    # 按 learner 查 lesson_pref，没有则插入 (learner, series_code)，有则更新 series_code
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    设 s = 查一行 app.db lesson_series_get_subject code={series_code} subject_id={sid}
    如果 {s} 为空
      报错 404 没有这个系列
    结束
    如果 {s.sort_order} 小于 0
      报错 404 没有这个系列
    结束
    设 pref = 查一行 app.db lesson_pref_get learner={learner} subject_id={sid}
    如果 {pref} 为空
      设 n = 写库 app.db lesson_pref_insert learner={learner} subject_id={sid} series_code={series_code}
    否则
      设 n = 写库 app.db lesson_pref_update learner={learner} subject_id={sid} series_code={series_code}
    结束
    设 out.ok = 1
    设 out.learner = {learner}
    设 out.series_code = {series_code}
    返回 {out}
  结束

  公开 函数 列课文 series_code? level? keyword? learner? current_role? auth_mode? subject?
    # 返回 {total, lessons}，lessons 是 [{code, level, title, summary, series_code, seq}]，按 seq 升序、id 升序
    # 查 lesson_text 全部行
    # series_code 不为空时只留 series_code 相等的行
    # level 不为空时只留 level 相等的行
    # keyword 不为空时只留 code、title、summary 任一包含 keyword 的行
    设 q.series_code = {series_code 或}
    设 q.level = {level 或}
    设 q.keyword = {keyword 或}
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 q.subject_id = {sj.subject_id}
    设 rows = 查询表 app.db lesson_text_list {q}
    设 n = 列表长度 {rows}
    设 out.total = {n}
    设 out.lessons = {rows}
    返回 {out}
  结束

  公开 函数 取课文 code learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    # 返回 {code, level, title, summary, explain, connection, examples, examples_edited, orig_title, series_code, seq, point_codes}；point_codes 是该课挂的知识点编号用英文逗号连接（按挂接顺序）；查不到返回空
    # 按 code 查 lesson_text 一行，查不到则返回空
    # 查 lesson_point_link 中 lesson_code=code 的行，按 id 升序，取 point_code 用英文逗号连接成 point_codes
    设 r = 查一行 app.db lesson_text_get code={code} subject_id={sid}
    如果 {r} 为空
      返回 {r}
    结束
    设 pcs = 查询 app.db lesson_point_link_codes lesson_code={code} subject_id={sid}
    设 pc = {zz 或}
    遍历 x 于 {pcs}
      如果 {pc} 为空
        设 pc = {x.point_code}
      否则
        设 pc = {pc},{x.point_code}
      结束
    结束
    设 r.point_codes = {pc}
    返回 {r}
  结束

  公开 函数 按条目列课文 item_code learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    # 返回 {item_code, total, lessons}，lessons 是 [{code, level, title, summary, series_code, seq}]，按 seq 升序、id 升序
    # 报错 404 没有这个条目
    # 调用 kg.取条目 code=item_code，取不到报错 404 没有这个条目
    # 查 lesson_item_link 中 item_code 相等的行，连 lesson_text 取课文，同一课只算一次，按 seq 升序、id 升序
    设 k = 调用 kg.取条目 code={item_code} subject={sid}
    如果 {k} 为空
      报错 404 没有这个条目
    结束
    设 rows = 查询 app.db lesson_by_item item_code={item_code} subject_id={sid}
    设 n = 列表长度 {rows}
    设 out.item_code = {item_code}
    设 out.total = {n}
    设 out.lessons = {rows}
    返回 {out}
  结束

  公开 函数 按知识点列课文 point_code learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    # 返回 {point_code, total, lessons}，lessons 同「按条目列课文」（只含直接挂在该知识点上的课）
    # 报错 404 没有这个知识点
    # 调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
    # 查 lesson_point_link 中 point_code 相等的行，连 lesson_text 取课文，同一课只算一次，按 seq 升序、id 升序
    设 k = 调用 kg.取知识点 code={point_code} subject={sid}
    如果 {k} 为空
      报错 404 没有这个知识点
    结束
    设 rows = 查询 app.db lesson_by_point point_code={point_code} subject_id={sid}
    设 n = 列表长度 {rows}
    设 out.point_code = {point_code}
    设 out.total = {n}
    设 out.lessons = {rows}
    返回 {out}
  结束

  公开 函数 取课文关联条目 lesson_code learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    # 返回 {lesson_code, total, items}，items 是 [{code, name, point_code}]，按挂接顺序
    # 报错 404 没有这课
    # 按 lesson_code 查 lesson_text，查不到报错 404 没有这课
    # 查 lesson_item_link 中 lesson_code 相等的行，按 id 升序
    # 逐行调用 kg.取条目 code=该行 item_code，取到则收 {code, name, point_code}，取不到（条目已被删）跳过
    设 lt = 查一行 app.db lesson_text_get code={lesson_code} subject_id={sid}
    如果 {lt} 为空
      报错 404 没有这课
    结束
    设 links = 查询 app.db lesson_item_link_by_lesson lesson_code={lesson_code} subject_id={sid}
    设 items = 解析JSON []
    遍历 lk 于 {links}
      设 k = 调用 kg.取条目 code={lk.item_code} subject={sid}
      如果 {k} 不为空
        设 e.code = {k.code}
        设 e.name = {k.name}
        设 e.point_code = {k.point_code}
        设 items = 列表加项 {items} {e}
      结束
    结束
    设 n = 列表长度 {items}
    设 out.lesson_code = {lesson_code}
    设 out.total = {n}
    设 out.items = {items}
    返回 {out}
  结束

  公开 函数 取知识点等级 point_code learner? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    # 返回 {point_code, level, lesson_count}；level 是与该知识点相关的课文里最基础的等级（N5 最基础、N1 最难），没有相关课文时 level 为空串、lesson_count 为 0
    # 报错 404 没有这个知识点
    # 调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
    # 课文集合 = lesson_point_link 中 point_code 相等的课文编号，并上「调用 kg.按知识点列条目 point_code=point_code」得到的每个条目在 lesson_item_link 中挂的课文编号，去重
    # 连 lesson_text 取每课 level，lesson_count = 集合大小
    # 集合为空返回 {"point_code": point_code, "level": "", "lesson_count": 0}
    设 k = 调用 kg.取知识点 code={point_code} subject={sid}
    如果 {k} 为空
      报错 404 没有这个知识点
    结束
    设 ks = 调用 kg.按知识点列条目 point_code={point_code} subject={sid}
    设 s = {zz 或}
    遍历 it 于 {ks.items}
      设 s = {s}{it.code},
    结束
    设 q.point_code = {point_code}
    设 q.subject_id = {sid}
    设 q.items = {s}
    设 row = 查一行表 app.db lesson_level_by_point {q}
    如果 {row.cnt} 等于 0
      设 out.point_code = {point_code}
      设 out.level = {zz 或}
      设 out.lesson_count = 0
      返回 {out}
    结束
    设 out.point_code = {point_code}
    设 out.level = N{row.lv}
    设 out.lesson_count = {row.cnt}
    返回 {out}
  结束

  函数 校验行 line subject_id
    设 parts = 按正则切分 {line} \|
    设 n = 0
    设 code = {zz 或}
    设 level = {zz 或}
    设 title = {zz 或}
    设 edited = {zz 或}
    设 seq = {zz 或}
    设 items = {zz 或}
    设 points = {zz 或}
    遍历 f 于 {parts}
      设 n = 计算 {n} + 1
      如果 {n} 等于 1
        设 code = {f}
      否则如果 {n} 等于 2
        设 level = {f}
      否则如果 {n} 等于 3
        设 title = {f}
      否则如果 {n} 等于 8
        设 edited = {f}
      否则如果 {n} 等于 10
        设 seq = {f}
      否则如果 {n} 等于 11
        设 items = {f}
      否则如果 {n} 等于 12
        设 points = {f}
      结束
    结束
    如果 {code} 为空
      报错 400 导入文件有错
    结束
    如果 {title} 为空
      报错 400 导入文件有错
    结束
    设 m = 匹配 {level} ^N[1-5]$
    如果 {m.matched} 不等于 是
      报错 400 导入文件有错
    结束
    如果 {edited} 不为空
      设 m = 匹配 {edited} ^[01]$
      如果 {m.matched} 不等于 是
        报错 400 导入文件有错
      结束
    结束
    如果 {seq} 不为空
      设 m = 匹配 {seq} ^-?\d+$
      如果 {m.matched} 不等于 是
        报错 400 导入文件有错
      结束
    结束
    设 pf = 调用 编号前缀检查 subject_id={subject_id} code={code}
    设 ics = 按正则切分 {items} \s*,\s*
    遍历 c 于 {ics}
      如果 {c} 不为空
        设 k = 调用 kg.取条目 code={c} subject={subject_id}
        如果 {k} 为空
          报错 400 课文映射对不上
        结束
      结束
    结束
    设 pcs = 按正则切分 {points} \s*,\s*
    遍历 c 于 {pcs}
      如果 {c} 不为空
        设 k = 调用 kg.取知识点 code={c} subject={subject_id}
        如果 {k} 为空
          报错 400 课文映射对不上
        结束
      结束
    结束
    返回 {"code": "{code}"}
  结束

  函数 写入行 line series_code subject_id
    设 parts = 按正则切分 {line} \|
    设 n = 0
    设 q.code = {zz 或}
    设 q.level = {zz 或}
    设 q.title = {zz 或}
    设 q.summary = {zz 或}
    设 q.explain = {zz 或}
    设 q.connection = {zz 或}
    设 q.examples = {zz 或}
    设 q.examples_edited = 0
    设 q.orig_title = {zz 或}
    设 q.seq = 0
    设 q.series_code = {series_code}
    设 q.subject_id = {subject_id}
    设 items = {zz 或}
    设 points = {zz 或}
    遍历 f 于 {parts}
      设 n = 计算 {n} + 1
      如果 {n} 等于 1
        设 q.code = {f}
      否则如果 {n} 等于 2
        设 q.level = {f}
      否则如果 {n} 等于 3
        设 q.title = {f}
      否则如果 {n} 等于 4
        设 q.summary = {f}
      否则如果 {n} 等于 5
        设 q.explain = {f}
      否则如果 {n} 等于 6
        设 q.connection = {f}
      否则如果 {n} 等于 7
        设 q.examples = {f}
      否则如果 {n} 等于 8
        如果 {f} 不为空
          设 q.examples_edited = {f}
        结束
      否则如果 {n} 等于 9
        设 q.orig_title = {f}
      否则如果 {n} 等于 10
        如果 {f} 不为空
          设 q.seq = {f}
        结束
      否则如果 {n} 等于 11
        设 items = {f}
      否则如果 {n} 等于 12
        设 points = {f}
      结束
    结束
    设 w = 写库表 app.db lesson_text_insert {q}
    设 il = 0
    设 pl = 0
    设 seeni = @
    设 ics = 按正则切分 {items} \s*,\s*
    遍历 c 于 {ics}
      如果 {c} 不为空
        如果 {seeni} 不包含 @{c}@
          设 w = 写库 app.db lesson_item_link_insert lesson_code={q.code} item_code={c} subject_id={subject_id}
          设 seeni = {seeni}{c}@
          设 il = 计算 {il} + 1
        结束
      结束
    结束
    设 seenp = @
    设 pcs = 按正则切分 {points} \s*,\s*
    遍历 c 于 {pcs}
      如果 {c} 不为空
        如果 {seenp} 不包含 @{c}@
          设 w = 写库 app.db lesson_point_link_insert lesson_code={q.code} point_code={c} subject_id={subject_id}
          设 seenp = {seenp}{c}@
          设 pl = 计算 {pl} + 1
        结束
      结束
    结束
    返回 {"i": {il}, "p": {pl}}
  结束

  公开 函数 导入课文 series_code file_path series_name? intro? source? license? sort_order? learner? current_role? auth_mode? subject?
    如果 {series_code} 为空
      报错 400 series_code 不能为空
    结束
    如果 {sort_order} 不为空
      设 m = 匹配 {sort_order} ^-?\d+$
      如果 {m.matched} 不等于 是
        报错 400 导入文件有错
      结束
    结束
    设 doc = 读文档 {file_path}
    如果 {doc.error} 不为空
      报错 400 导入文件有错
    结束
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 r = 调用 导入课文数据 series_code={series_code} lessons_text={doc.text} subject_id={sj.subject_id} series_name={series_name} intro={intro} source={source} license={license} sort_order={sort_order}
    返回 {r}
  结束

  函数 导入课文数据 series_code lessons_text subject_id series_name? intro? source? license? sort_order?
    # 返回 {ok, series_code, total, item_links, point_links}
    # 报错 400 series_code 不能为空
    # 报错 400 导入文件有错
    # 报错 400 课号重复
    # 报错 400 课文映射对不上
    # series_code 为空，报错 400 series_code 不能为空
    # sort_order 不为空且不是整数，报错 400 导入文件有错
    # 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以
    # 每行格式「课号|等级|标题|一句话|讲解|接续|例句|是否改过例句|原标题|课序|条目编号列表|知识点编号列表」，用 | 分隔；例句字段原样整体存入；后面从「是否改过例句」起的字段可省略或为空；条目编号列表、知识点编号列表内用英文逗号隔开
    # 校验：课号、标题不能为空；等级必须是 N5 N4 N3 N2 N1 之一；是否改过例句为空当 0，只能是 0 或 1；课序为空当 0，否则必须是整数；任一不满足报错 400 导入文件有错
    # 同一文件内课号重复，或课号已存在于 series_code 以外的系列的 lesson_text 中，报错 400 课号重复
    # 条目编号列表里每个编号调用 kg.取条目 code=编号，取不到报错 400 课文映射对不上；知识点编号列表里每个编号调用 kg.取知识点 code=编号，取不到报错 400 课文映射对不上（映射只引用已有的，不新建）
    # 在一个事务里：
    # 按 series_code 查 lesson_series：没有则插入 (code=series_code, name=series_name 不为空取之否则取 series_code, intro, source, license, sort_order=sort_order 不为空取之否则 100)；有则对 series_name、intro、source、license、sort_order 中不为空的项更新对应列，为空的项不改
    # 删除 lesson_item_link、lesson_point_link 中属于 series_code 系列各课的行，再删除 lesson_text 中 series_code 相等的行（只动这个系列，其它系列和 lesson_pref 不动）
    # 逐行插入 lesson_text（series_code 取入参），对条目编号列表每个编号插入 lesson_item_link (lesson_code, item_code)，对知识点编号列表每个编号插入 lesson_point_link (lesson_code, point_code)，同一课内重复编号只插一次，统计 item_links、point_links
    如果 {series_code} 为空
      报错 400 series_code 不能为空
    结束
    如果 {sort_order} 不为空
      设 m = 匹配 {sort_order} ^-?\d+$
      如果 {m.matched} 不等于 是
        报错 400 导入文件有错
      结束
    结束
    设 lines = 按正则切分 {lessons_text} \r?\n
    设 valid = 解析JSON []
    设 seen = @
    设 total = 0
    遍历 raw 于 {lines}
      设 line = 替换 {raw} ^\s+|\s+$
      如果 {line} 为空
        继续
      结束
      设 mc = 匹配 {line} ^#
      如果 {mc.matched} 等于 是
        继续
      结束
      设 r = 调用 校验行 line={line} subject_id={subject_id}
      如果 {seen} 包含 @{r.code}@
        报错 400 课号重复
      结束
      设 oc = 查一值 app.db lesson_text_other_count code={r.code} series_code={series_code}
      如果 {oc} 大于 0
        报错 400 课号重复
      结束
      设 seen = {seen}{r.code}@
      设 total = 计算 {total} + 1
      设 valid = 列表加项 {valid} {line}
    结束
    如果 {total} 等于 0
      报错 400 导入文件有错
    结束
    设 il = 0
    设 pl = 0
    事务 app.db
      设 s = 查一行 app.db lesson_series_get code={series_code}
      设 s2 = 查一行 app.db lesson_series_get_subject code={series_code} subject_id={subject_id}
      如果 {s} 不为空
        如果 {s2} 为空
          报错 400 系列编号已被其他科目使用
        结束
      结束
      设 p.code = {series_code}
      设 p.subject_id = {subject_id}
      设 p.intro = {intro 或}
      设 p.source = {source 或}
      设 p.license = {license 或}
      设 p.sort_order = {sort_order 或}
      设 p.name = {series_name 或}
      如果 {s} 为空
        如果 {p.name} 为空
          设 p.name = {series_code}
        结束
        如果 {p.sort_order} 为空
          设 p.sort_order = 100
        结束
        设 w = 写库表 app.db lesson_series_insert {p}
      否则
        设 w = 写库表 app.db lesson_series_update {p}
      结束
      设 w = 写库 app.db lesson_item_link_delete_series series_code={series_code}
      设 w = 写库 app.db lesson_point_link_delete_series series_code={series_code}
      设 w = 写库 app.db lesson_text_delete_series series_code={series_code}
      遍历 vl 于 {valid}
        设 x = 调用 写入行 line={vl} series_code={series_code} subject_id={subject_id}
        设 il = 计算 {il} + {x.i}
        设 pl = 计算 {pl} + {x.p}
      结束
    结束
    返回 {"ok": 1, "series_code": "{series_code}", "total": {total}, "item_links": {il}, "point_links": {pl}}
  结束

  公开 函数 写入系列课文并重灌 series_code rows_json series_name? source? license? learner? current_role? auth_mode? subject?
    如果 {series_code} 为空
      报错 400 series_code 不能为空
    结束
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 sid = {sj.subject_id}
    设 mt = 匹配 {rows_json} ^\s*\[
    如果 {mt.matched} 不等于 是
      报错 400 课文数据有错
    结束
    设 rows = 解析JSON {rows_json}
    设 total = 列表长度 {rows}
    如果 {total} 等于 0
      报错 400 课文数据有错
    结束
    设 seen = @
    遍历 rw 于 {rows}
      设 c = {rw.code 或}
      设 t = {rw.title 或}
      设 lv = {rw.level 或}
      设 ee = {rw.examples_edited 或}
      设 sq = {rw.seq 或}
      如果 {c} 为空
        报错 400 课文数据有错
      结束
      如果 {t} 为空
        报错 400 课文数据有错
      结束
      如果 {lv} 为空
        报错 400 课文数据有错
      结束
      设 mt = 匹配 {lv} ^N[1-5]$
      如果 {mt.matched} 不等于 是
        报错 400 课文数据有错
      结束
      如果 {ee} 不为空
        设 mt = 匹配 {ee} ^[01]$
        如果 {mt.matched} 不等于 是
          报错 400 课文数据有错
        结束
      结束
      如果 {sq} 不为空
        设 mt = 匹配 {sq} ^-?\d+$
        如果 {mt.matched} 不等于 是
          报错 400 课文数据有错
        结束
      结束
      如果 {seen} 包含 @{c}@
        报错 400 课号重复
      结束
      设 oc = 查一值 app.db lesson_text_other_count code={c} series_code={series_code}
      如果 {oc} 大于 0
        报错 400 课号重复
      结束
      设 pf = 调用 编号前缀检查 subject_id={sid} code={c}
      设 seen = {seen}{c}@
    结束
    设 sa = 查一行 app.db lesson_series_get code={series_code}
    设 sb = 查一行 app.db lesson_series_get_subject code={series_code} subject_id={sid}
    如果 {sa} 不为空
      如果 {sb} 为空
        报错 400 系列编号已被其他科目使用
      结束
    结束
    写JSONL content/lesson/series/{series_code}.jsonl {rows}
    读JSONL frows = content/lesson/series/{series_code}.jsonl
    设 file_rows = 列表长度 {frows}
    设 good = 解析JSON []
    设 rejected = 解析JSON []
    遍历 rw 于 {frows}
      设 bad = {zz 或}
      设 ics = 解析JSON []
      如果 {rw.item_codes 或} 不为空
        设 ics = {rw.item_codes}
      结束
      设 pcs = 解析JSON []
      如果 {rw.point_codes 或} 不为空
        设 pcs = {rw.point_codes}
      结束
      遍历 ci 于 {ics}
        如果 {bad} 为空
          如果 {ci} 不为空
            设 k = 调用 kg.取条目 code={ci} subject={sid}
            如果 {k} 为空
              设 bad = 条目{ci}在库里没有
            结束
          结束
        结束
      结束
      遍历 cp 于 {pcs}
        如果 {bad} 为空
          如果 {cp} 不为空
            设 k = 调用 kg.取知识点 code={cp} subject={sid}
            如果 {k} 为空
              设 bad = 知识点{cp}在库里没有
            结束
          结束
        结束
      结束
      如果 {bad} 不为空
        设 rj.code = {rw.code}
        设 rj.reason = {bad}
        设 rejected = 列表加项 {rejected} {rj}
      否则
        设 good = 列表加项 {good} {rw}
      结束
    结束
    设 il = 0
    设 pl = 0
    事务 app.db
      设 s = 查一行 app.db lesson_series_get code={series_code}
      设 p.code = {series_code}
      设 p.subject_id = {sid}
      设 p.name = {series_name 或}
      设 p.intro = {zz 或}
      设 p.source = {source 或}
      设 p.license = {license 或}
      设 p.sort_order = {zz 或}
      如果 {s} 为空
        如果 {p.name} 为空
          设 p.name = {series_code}
        结束
        设 p.sort_order = 100
        设 w = 写库表 app.db lesson_series_insert {p}
      否则
        如果 {s.sort_order} 小于 0
          设 p.sort_order = 100
        结束
        设 w = 写库表 app.db lesson_series_update {p}
      结束
      设 w = 写库 app.db lesson_item_link_delete_series series_code={series_code}
      设 w = 写库 app.db lesson_point_link_delete_series series_code={series_code}
      设 w = 写库 app.db lesson_text_delete_series series_code={series_code}
      遍历 gw 于 {good}
        设 q.code = {gw.code}
        设 q.level = {gw.level}
        设 q.title = {gw.title}
        设 q.summary = {gw.summary 或}
        设 q.explain = {gw.explain 或}
        设 q.connection = {gw.connection 或}
        设 q.examples = {gw.examples 或}
        设 q.examples_edited = {gw.examples_edited 或 0}
        设 q.orig_title = {gw.orig_title 或}
        设 q.seq = {gw.seq 或 0}
        设 q.series_code = {series_code}
        设 q.subject_id = {sid}
        设 w = 写库表 app.db lesson_text_insert {q}
        设 gi = 解析JSON []
        如果 {gw.item_codes 或} 不为空
          设 gi = {gw.item_codes}
        结束
        设 gp = 解析JSON []
        如果 {gw.point_codes 或} 不为空
          设 gp = {gw.point_codes}
        结束
        设 seeni = @
        遍历 ci 于 {gi}
          如果 {ci} 不为空
            如果 {seeni} 不包含 @{ci}@
              设 w = 写库 app.db lesson_item_link_insert lesson_code={q.code} item_code={ci} subject_id={sid}
              设 seeni = {seeni}{ci}@
              设 il = 计算 {il} + 1
            结束
          结束
        结束
        设 seenp = @
        遍历 cp 于 {gp}
          如果 {cp} 不为空
            如果 {seenp} 不包含 @{cp}@
              设 w = 写库 app.db lesson_point_link_insert lesson_code={q.code} point_code={cp} subject_id={sid}
              设 seenp = {seenp}{cp}@
              设 pl = 计算 {pl} + 1
            结束
          结束
        结束
      结束
    结束
    设 nrej = 列表长度 {rejected}
    设 imported = 计算 {total} - {nrej}
    设 out.ok = 1
    设 out.series_code = {series_code}
    设 out.total = {total}
    设 out.imported = {imported}
    设 out.item_links = {il}
    设 out.point_links = {pl}
    设 out.file_rows = {file_rows}
    设 out.rejected = {rejected}
    返回 {out}
  结束

  公开 函数 撤下系列 series_code learner? current_role? auth_mode? subject?
    # 返回 {ok, series_code, removed_lessons}
    # 报错 404 没有这个系列
    # 按 series_code 查 lesson_series，查不到报错 404 没有这个系列
    # 在一个事务里：数出 series_code 系列的课文数 removed_lessons；删除这些课文在 lesson_item_link、lesson_point_link 中的行；删除 lesson_text 中该系列的行；把 lesson_series 该行 sort_order 改为 -1（系列行保留，lesson_pref 不动）
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 sid = {sj.subject_id}
    设 s = 查一行 app.db lesson_series_get_subject code={series_code} subject_id={sid}
    如果 {s} 为空
      报错 404 没有这个系列
    结束
    设 mv = 移动文件 content/lesson/series/{series_code}.jsonl content/lesson/series/{series_code}.withdrawn.jsonl
    设 moved = 0
    如果 {mv} 等于 是 或 {mv} 等于 True 或 {mv} 等于 true
      设 moved = 1
    结束
    设 cnt = 查一值 app.db lesson_text_count_series series_code={series_code}
    事务 app.db
      设 w = 写库 app.db lesson_item_link_delete_series series_code={series_code}
      设 w = 写库 app.db lesson_point_link_delete_series series_code={series_code}
      设 w = 写库 app.db lesson_text_delete_series series_code={series_code}
      设 w = 写库 app.db lesson_series_withdraw code={series_code}
    结束
    返回 {"ok": 1, "series_code": "{series_code}", "removed_lessons": {cnt}, "moved": {moved}}
  结束

  函数 题数表 subject_id
    设 c = 查一值 app.db lesson_qq_exists
    如果 {c} 等于 0
      设 e = 解析JSON []
      返回 {e}
    结束
    设 rows = 查询 app.db lesson_qcount subject_id={subject_id}
    返回 {rows}
  结束

  公开 函数 教材页面 learner series? lesson_level? keyword? current_role? auth_mode? subject?
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    设 sl = 调用 列系列 subject={sid}
    设 qt = 调用 题数表 subject_id={sid}
    设 found = 0
    设 cur_code = {zz 或}
    设 cur_name = {zz 或}
    如果 {series} 不为空
      遍历 s 于 {sl.series}
        如果 {s.code} 等于 {series}
          设 found = 1
          设 cur_name = {s.name}
        结束
      结束
    结束
    如果 {found} 等于 1
      设 sel = 调用 选择系列 learner={learner} series_code={series} subject={sid}
      设 cur_code = {series}
    否则
      设 cu = 调用 取当前系列 learner={learner} subject={sid}
      设 cur_code = {cu.series_code}
      设 cur_name = {cu.name}
    结束
    设 lv = {lesson_level 或}
    如果 {lv} 等于 全部
      设 lv = {zz 或}
    结束
    设 kw = {keyword 或}
    设 ls = 调用 列课文 series_code={cur_code} level={lv} keyword={kw} subject={sid}
    设 rows = 解析JSON []
    遍历 r 于 {ls.lessons}
      设 qn = 转数字 0
      遍历 x 于 {qt}
        如果 {x.lesson_code} 等于 {r.code}
          设 qn = {x.n}
        结束
      结束
      设 e1.code = {r.code}
      设 e1.level = {r.level}
      设 e1.title = {r.title}
      设 e1.summary = {r.summary 或}
      设 e1.qcount = {qn}
      设 e1.href = #%E6%95%99%E6%9D%90?lesson={r.code}
      设 rows = 列表加项 {rows} {e1}
    结束
    设 opts = 解析JSON []
    遍历 s 于 {sl.series}
      设 e2.value = {s.code}
      设 e2.label = {s.name}
      设 opts = 列表加项 {opts} {e2}
    结束
    设 fl = {lesson_level 或 全部}
    设 out.lessons = {rows}
    设 out.series_options = {opts}
    设 out.series_head = {cur_name}
    设 out.lesson_count = 共{ls.total}课
    设 out.form.series = {cur_code}
    设 out.form.lesson_level = {fl}
    设 out.form.keyword = {kw}
    返回 {out}
  结束

  公开 函数 课文页面 learner lesson? current_role? auth_mode? subject?
    如果 {lesson} 为空
      报错 400 lesson 不能为空
    结束
    设 sj = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 sid = {sj.subject_id}
    设 pg = 调用 教材页面 learner={learner} subject={sid}
    设 lt = 调用 取课文 code={lesson} subject={sid}
    如果 {lt} 为空
      设 o1.reading.code = {lesson}
      设 o1.reading.missing = 没有这一课（{lesson}），回课文表重新选。
      设 o1.reading.back = #%E6%95%99%E6%9D%90
      设 o1.form = {pg.form}
      返回 {o1}
    结束
    设 qt = 调用 题数表 subject_id={sid}
    设 n = 转数字 0
    遍历 x 于 {qt}
      如果 {x.lesson_code} 等于 {lesson}
        设 n = {x.n}
      结束
    结束
    设 qq.code = {lesson}
    设 qn1 = 查一行表 app.db lesson_seq_no {qq}
    设 nn = {qn1.nn}
    设 sl = 调用 列系列 subject={sid}
    设 slabel = {lt.series_code}
    遍历 s 于 {sl.series}
      如果 {s.code} 等于 {lt.series_code}
        设 slabel = {s.name}
      结束
    结束
    设 rd.code = {lt.code}
    设 rd.level = {lt.level}
    设 rd.title = {lt.title}
    设 rd.summary = {lt.summary 或}
    设 rd.formation = {lt.connection 或}
    设 rd.explanation = {lt.explain 或}
    设 rd.qcount = {n}
    设 rd.head = 《{lt.title}》　{lt.level}　第{nn}课（{lt.code}）
    设 rd.series = {lt.series_code}
    设 rd.series_label = {slabel}
    设 rd.practice = {zz 或}
    设 rd.quiz_note = 这一课还没有题，可以先问老师
    如果 {n} 大于 0
      设 rd.practice = #%E5%81%9A%E9%A2%98?lesson={lt.code}
      设 文案 = 这一课有
      设 rd.quiz_note = {文案} {n} 道题
    结束
    设 rd.ask = #%E9%97%AE%E8%80%81%E5%B8%88
    设 rd.explain = #%E9%97%AE%E8%80%81%E5%B8%88?lesson={lt.code}
    设 rd.back = #%E6%95%99%E6%9D%90
    设 rd.missing = {zz 或}
    设 exs = 解析JSON []
    设 etext = {lt.examples 或}
    设 sents = 按正则切分 {etext} @@
    遍历 sn 于 {sents}
      如果 {sn} 不为空
        设 segs = 按正则切分 {sn} \^\^
        设 sc = 列表长度 {segs}
        如果 {sc} 等于 2
          设 si = 0
          设 ex.jp = {zz 或}
          设 ex.zh = {zz 或}
          遍历 sg 于 {segs}
            设 si = 计算 {si} + 1
            如果 {si} 等于 1
              设 ex.jp = {sg}
            否则
              设 ex.zh = {sg}
            结束
          结束
          设 exs = 列表加项 {exs} {ex}
        结束
      结束
    结束
    设 gi = 调用 取课文关联条目 lesson_code={lesson} subject={sid}
    设 lis = 解析JSON []
    遍历 it 于 {gi.items}
      设 pl = {it.point_code}
      设 pk = 调用 kg.取知识点 code={it.point_code} subject={sid}
      如果 {pk} 不为空
        设 pl = {pk.title}
      结束
      设 li.code = {it.code}
      设 li.label = {it.name}
      设 li.point_label = {pl}
      设 lis = 列表加项 {lis} {li}
    结束
    设 pcs = 按正则切分 {lt.point_codes} ,
    遍历 pc 于 {pcs}
      如果 {pc} 不为空
        设 pl = {pc}
        设 pk = 调用 kg.取知识点 code={pc} subject={sid}
        如果 {pk} 不为空
          设 pl = {pk.title}
        结束
        设 lp.code = {pc}
        设 lp.label = （整个知识点）
        设 lp.point_label = {pl}
        设 lis = 列表加项 {lis} {lp}
      结束
    结束
    设 o2.reading = {rd}
    设 o2.examples = {exs}
    设 o2.lesson_items = {lis}
    设 o2.lessons = {pg.lessons}
    设 o2.series_options = {pg.series_options}
    设 o2.series_head = {pg.series_head}
    设 o2.lesson_count = {pg.lesson_count}
    设 o2.form = {pg.form}
    返回 {o2}
  结束

结束
