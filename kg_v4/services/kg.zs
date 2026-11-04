业务 kg
  依赖 subject
  用包 common db text doc data

  公开 函数 取知识点 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {id, code, title}；查不到返回空
    # 按 code 查 kg_point 一行
    # 查不到则返回空
    # 返回 {"id": id, "code": code, "title": title}
    设 p = 查一行 app.db kg_point_by_code code={code} subject_id={sb.subject_id}
    返回 {p}
  结束

  公开 函数 列知识点 learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {total, points}，points 是 [{code, title}]，按 id 升序
    # 查 kg_point 全部行，按 id 升序
    # 返回 {"total": 行数, "points": 列表}
    设 rows = 查询 app.db kg_point_list subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "points": {rows}}
  结束

  公开 函数 列前置 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {code, total, points}，points 是该节点直接前置 [{code, title}]
    # 报错 404 没有这个知识点
    # 按 code 查 kg_point，查不到报错 404 没有这个知识点
    # 查 kg_edge 中 point_code=code 的行，取每行 pre_code，连 kg_point 取 title，按 id 升序
    # 返回 {"code": code, "total": 个数, "points": 列表}
    设 p = 查一行 app.db kg_point_by_code code={code} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 rows = 查询 app.db kg_prereq_list code={code} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"code": "{code}", "total": {n}, "points": {rows}}
  结束

  公开 函数 列后续 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {code, total, points}，points 是该节点直接后续 [{code, title}]
    # 报错 404 没有这个知识点
    # 按 code 查 kg_point，查不到报错 404 没有这个知识点
    # 查 kg_edge 中 pre_code=code 的行，取每行 point_code，连 kg_point 取 title，按 id 升序
    # 返回 {"code": code, "total": 个数, "points": 列表}
    设 p = 查一行 app.db kg_point_by_code code={code} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 rows = 查询 app.db kg_succ_list code={code} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"code": "{code}", "total": {n}, "points": {rows}}
  结束

  公开 函数 列祖先 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {code, total, points}，points 是该节点全部祖先（直接和间接前置，去重，不含自己）[{code, title}]
    # 报错 404 没有这个知识点
    # 按 code 查 kg_point，查不到报错 404 没有这个知识点
    # 从 code 出发，沿 kg_edge 的 point_code→pre_code 方向逐层向上取前置，已访问过的不再入队，直到没有新节点
    # 把访问到的节点（不含 code 自己）连 kg_point 取 title，按 id 升序
    # 返回 {"code": code, "total": 个数, "points": 列表}
    设 p = 查一行 app.db kg_point_by_code code={code} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 rows = 查询 app.db kg_ancestor_list code={code} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"code": "{code}", "total": {n}, "points": {rows}}
  结束

  公开 函数 列后代 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {code, total, points}，points 是该节点全部后代（直接和间接后续，去重，不含自己）[{code, title}]
    # 报错 404 没有这个知识点
    # 按 code 查 kg_point，查不到报错 404 没有这个知识点
    # 从 code 出发，沿 kg_edge 的 pre_code→point_code 方向逐层向下取后续，已访问过的不再入队，直到没有新节点
    # 把访问到的节点（不含 code 自己）连 kg_point 取 title，按 id 升序
    # 返回 {"code": code, "total": 个数, "points": 列表}
    设 p = 查一行 app.db kg_point_by_code code={code} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 rows = 查询 app.db kg_descendant_list code={code} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"code": "{code}", "total": {n}, "points": {rows}}
  结束

  公开 函数 列根节点 learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {total, points}，points 是没有任何前置的知识点 [{code, title}]
    # 取 kg_point 中 code 不出现在 kg_edge.point_code 里的行，按 id 升序
    # 返回 {"total": 个数, "points": 列表}
    设 rows = 查询 app.db kg_root_list subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "points": {rows}}
  结束

  公开 函数 列分层 learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {layer_count, layers}，layers 是 [{depth, points}]，points 是 [{code, title}]；节点的 depth = 0（无前置）或 其所有直接前置 depth 的最大值 + 1（按依赖深度分层）
    # 取全部 kg_point 和 kg_edge
    # 无前置的节点 depth=0；其余节点 depth = 其全部前置 depth 最大值 + 1（图无环，按拓扑顺序算）
    # 按 depth 升序分组，组内按 id 升序
    # 返回 {"layer_count": 层数, "layers": 列表}；没有知识点时 layer_count=0，layers 为空列表
    设 ds = 查询 app.db kg_layer_depths subject_id={sb.subject_id}
    设 layers = 解析JSON []
    遍历 dd 于 {ds}
      设 pts = 查询 app.db kg_layer_points depth={dd.depth} subject_id={sb.subject_id}
      设 item.depth = {dd.depth}
      设 item.points = {pts}
      设 layers = 列表加项 {layers} {item}
    结束
    设 n = 列表长度 {layers}
    返回 {"layer_count": {n}, "layers": {layers}}
  结束

  公开 函数 加前置边 pre_code point_code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    # 返回 {ok, created}，created 为 1 表示新加，0 表示这条边已存在
    # 报错 400 编号不能为空
    # 报错 400 不能以自己为前置
    # 报错 404 没有这个知识点
    # 报错 400 这条边会形成环
    # pre_code 或 point_code 为空，报错 400 编号不能为空
    # pre_code 等于 point_code，报错 400 不能以自己为前置
    # pre_code 或 point_code 不在 kg_point，报错 404 没有这个知识点
    # kg_edge 已有 (pre_code, point_code)，返回 {"ok": 1, "created": 0}
    # 环检查：从 point_code 沿 kg_edge 向下取全部后代，若包含 pre_code，报错 400 这条边会形成环
    # 往 kg_edge 插入一行 (pre_code, point_code)
    # 返回 {"ok": 1, "created": 1}
    如果 {pre_code} 为空 或 {point_code} 为空
      报错 400 编号不能为空
    结束
    如果 {pre_code} 等于 {point_code}
      报错 400 不能以自己为前置
    结束
    设 pa = 查一行 app.db kg_point_by_code code={pre_code} subject_id={sb.subject_id}
    设 pb = 查一行 app.db kg_point_by_code code={point_code} subject_id={sb.subject_id}
    如果 {pa} 为空 或 {pb} 为空
      报错 404 没有这个知识点
    结束
    设 ex = 查一值 app.db kg_edge_exists pre_code={pre_code} point_code={point_code} subject_id={sb.subject_id}
    如果 {ex} 大于 0
      返回 {"ok": 1, "created": 0}
    结束
    设 cy = 查一值 app.db kg_edge_cycle pre_code={pre_code} point_code={point_code} subject_id={sb.subject_id}
    如果 {cy} 大于 0
      报错 400 这条边会形成环
    结束
    设 w = 写库 app.db kg_edge_insert pre_code={pre_code} point_code={point_code} subject_id={sb.subject_id}
    返回 {"ok": 1, "created": 1}
  结束

  公开 函数 导出图 learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {point_count, edge_count, contrast_count, points, edges, contrasts}；points 是 [{code, title}]，edges 是 [{pre_code, point_code}]，contrasts 是 [{a_code, b_code}]
    # 分别查 kg_point、kg_edge、kg_contrast 全部行，按 id 升序
    # 返回三个列表和各自行数
    设 ps = 查询 app.db kg_point_list subject_id={sb.subject_id}
    设 es = 查询 app.db kg_edge_list subject_id={sb.subject_id}
    设 cs = 查询 app.db kg_contrast_list subject_id={sb.subject_id}
    设 pn = 列表长度 {ps}
    设 en = 列表长度 {es}
    设 cn = 列表长度 {cs}
    返回 {"point_count": {pn}, "edge_count": {en}, "contrast_count": {cn}, "points": {ps}, "edges": {es}, "contrasts": {cs}}
  结束

  公开 函数 取条目 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {id, code, name, point_code, after_form, prev_code}；查不到返回空
    # 按 code 查 kg_item 一行
    # 查不到则返回空
    # 返回该行各字段
    设 p = 查一行 app.db kg_item_by_code code={code} subject_id={sb.subject_id}
    返回 {p}
  结束

  公开 函数 列条目 learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {total, items}，items 是 [{code, name, point_code, after_form, prev_code}]，按 id 升序
    # 查 kg_item 全部行，按 id 升序
    # 返回 {"total": 行数, "items": 列表}
    设 rows = 查询 app.db kg_item_list subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "items": {rows}}
  结束

  公开 函数 按知识点列条目 point_code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {point_code, total, items}，items 同「列条目」
    # 报错 404 没有这个知识点
    # 按 point_code 查 kg_point，查不到报错 404 没有这个知识点
    # 查 kg_item 中 point_code 相等的行，按 id 升序
    # 返回 {"point_code": point_code, "total": 行数, "items": 列表}
    设 p = 查一行 app.db kg_point_by_code code={point_code} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 rows = 查询 app.db kg_item_by_point point_code={point_code} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    返回 {"point_code": "{point_code}", "total": {n}, "items": {rows}}
  结束

  公开 函数 列对照 code? learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {total, contrasts}，contrasts 是 [{a_code, b_code}]
    # code 为空：查 kg_contrast 全部行，按 id 升序
    # code 不为空：只取 a_code=code 或 b_code=code 的行（对照无向，任一端匹配都算）
    # 返回 {"total": 行数, "contrasts": 列表}
    如果 {code} 为空
      设 rows = 查询 app.db kg_contrast_list subject_id={sb.subject_id}
    否则
      设 rows = 查询 app.db kg_contrast_by_code code={code} subject_id={sb.subject_id}
    结束
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "contrasts": {rows}}
  结束

  公开 函数 核对条目存在 codes learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    # 返回 {ok, missing_count, missing}；codes 是用英文逗号隔开的编号，每个编号在 kg_item 或 kg_point 里有就算存在；ok 为 1 表示全部存在；missing 是不存在的编号用英文逗号连起来
    # 报错 400 codes 不能为空
    # codes 为空，报错 400 codes 不能为空
    # 按英文逗号拆开，去掉空白项
    # 逐个编号查 kg_item 和 kg_point，两张表都没有的记入 missing
    # 返回 {"ok": missing 为空则 1 否则 0, "missing_count": 个数, "missing": 逗号连接}
    如果 {codes} 为空
      报错 400 codes 不能为空
    结束
    设 parts = 按正则切分 {codes} \s*,\s*
    设 missing = {nothing 或}
    设 mc = 0
    遍历 cc 于 {parts}
      如果 {cc} 不为空
        设 cnt = 查一值 app.db kg_code_exists code={cc} subject_id={sb.subject_id}
        如果 {cnt} 等于 0
          设 mc = 计算 {mc} + 1
          如果 {missing} 为空
            设 missing = {cc}
          否则
            设 missing = {missing},{cc}
          结束
        结束
      结束
    结束
    设 okv = 0
    如果 {mc} 等于 0
      设 okv = 1
    结束
    返回 {"ok": {okv}, "missing_count": {mc}, "missing": "{missing}"}
  结束

  公开 函数 导入知识点 file_path learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    # 返回 {ok, total, created, updated}
    # 报错 400 导入文件有错
    # 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以
    # 每行格式「编号|中文名」，用 | 分隔；编号或中文名为空、或没有 | 就报错 400 导入文件有错（整批不写）
    # 在一个事务里：逐行按 code 查 kg_point，没有则插入 (code, title) 并 created+1，有则更新 title 并 updated+1
    # 同一文件里重复的编号后一行覆盖前一行（按已存在算更新）
    # 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}
    设 doc = 读文档 {file_path}
    如果 {doc.error} 不为空
      报错 400 导入文件有错
    结束
    设 lines = 按正则切分 {doc.text} \r?\n
    设 re = ^(?P<code>[^|]*)\|(?P<title>[^|]*)$
    设 lgr = 调用 subject.取界面语言 username={learner 或}
    设 lang = {lgr.lang}
    设 total = 0
    遍历 raw 于 {lines}
      设 line = 替换 {raw} ^\s+|\s+$
      设 cm = 匹配 {line} ^\x23
      如果 {line} 不为空 且 {cm.matched} 不等于 是
        设 mm = 匹配 {line} {re}
        如果 {mm.matched} 不等于 是
          报错 400 导入文件有错
        结束
        如果 {mm.named.code} 为空 或 {mm.named.title} 为空
          报错 400 导入文件有错
        结束
        设 cd = {mm.named.code}
        设 pc = 调用 编号前缀检查 subject_id={sb.subject_id} code={cd} lang={lang}
        设 oc = 查一值 app.db kg_point_other code={cd} subject_id={sb.subject_id}
        如果 {oc} 大于 0
          报错 400 编号已被其他科目使用
        结束
        设 total = 计算 {total} + 1
      结束
    结束
    设 created = 0
    设 updated = 0
    事务 app.db
      遍历 raw 于 {lines}
        设 line = 替换 {raw} ^\s+|\s+$
        设 cm = 匹配 {line} ^\x23
        如果 {line} 不为空 且 {cm.matched} 不等于 是
          设 mm = 匹配 {line} {re}
          设 pk.code = {mm.named.code}
          设 pk.subject_id = {sb.subject_id}
          设 pa.subject_id = {sb.subject_id}
          设 pa.code = {mm.named.code}
          设 pa.title = {mm.named.title}
          设 p = 查一行表 app.db kg_point_by_code {pk}
          如果 {p} 为空
            设 w = 写库表 app.db kg_point_insert {pa}
            设 created = 计算 {created} + 1
          否则
            设 w = 写库表 app.db kg_point_update {pa}
            设 updated = 计算 {updated} + 1
          结束
        结束
      结束
    结束
    返回 {"ok": 1, "total": {total}, "created": {created}, "updated": {updated}}
  结束

  公开 函数 导入条目 file_path learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    # 返回 {ok, total, created, updated}
    # 报错 400 导入文件有错
    # 报错 400 条目对不上知识点
    # 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以
    # 每行格式「编号|名称|知识点编号|接在哪个形式后|前一个条目编号」，用 | 分隔；后三项可以省略或为空（缺的尾部字段当空）；编号、名称、知识点编号任一为空，报错 400 导入文件有错
    # 在一个事务里：逐行按 code 查 kg_item，没有则插入并 created+1，有则更新 name、point_code、after_form、prev_code 并 updated+1
    # 全部行写完后校验：每个条目的 point_code 必须在 kg_point，前一个条目编号不为空时必须在 kg_item，否则报错 400 条目对不上知识点，事务回滚整批不写
    # 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}
    设 doc = 读文档 {file_path}
    如果 {doc.error} 不为空
      报错 400 导入文件有错
    结束
    设 lines = 按正则切分 {doc.text} \r?\n
    设 re = ^(?P<code>[^|]*)\|(?P<name>[^|]*)\|(?P<pc>[^|]*)\|(?P<af>[^|]*)\|(?P<pv>[^|]*)(?:\|.*)?$
    设 lgr = 调用 subject.取界面语言 username={learner 或}
    设 lang = {lgr.lang}
    设 total = 0
    遍历 raw 于 {lines}
      设 line = 替换 {raw} ^\s+|\s+$
      设 cm = 匹配 {line} ^\x23
      如果 {line} 不为空 且 {cm.matched} 不等于 是
        设 padded = {line}||||
        设 mm = 匹配 {padded} {re}
        如果 {mm.matched} 不等于 是
          报错 400 导入文件有错
        结束
        如果 {mm.named.code} 为空 或 {mm.named.name} 为空 或 {mm.named.pc} 为空
          报错 400 导入文件有错
        结束
        设 cd = {mm.named.code}
        设 pc = 调用 编号前缀检查 subject_id={sb.subject_id} code={cd} lang={lang}
        设 oc = 查一值 app.db kg_item_other code={cd} subject_id={sb.subject_id}
        如果 {oc} 大于 0
          报错 400 编号已被其他科目使用
        结束
        设 total = 计算 {total} + 1
      结束
    结束
    设 created = 0
    设 updated = 0
    事务 app.db
      遍历 raw 于 {lines}
        设 line = 替换 {raw} ^\s+|\s+$
        设 cm = 匹配 {line} ^\x23
        如果 {line} 不为空 且 {cm.matched} 不等于 是
          设 padded = {line}||||
          设 mm = 匹配 {padded} {re}
          设 ik.code = {mm.named.code}
          设 ik.subject_id = {sb.subject_id}
          设 ia.subject_id = {sb.subject_id}
          设 ia.code = {mm.named.code}
          设 ia.name = {mm.named.name}
          设 ia.point_code = {mm.named.pc}
          设 ia.after_form = {mm.named.af}
          设 ia.prev_code = {mm.named.pv}
          设 p = 查一行表 app.db kg_item_by_code {ik}
          如果 {p} 为空
            设 w = 写库表 app.db kg_item_insert {ia}
            设 created = 计算 {created} + 1
          否则
            设 w = 写库表 app.db kg_item_update {ia}
            设 updated = 计算 {updated} + 1
          结束
        结束
      结束
      设 bad = 查一值 app.db kg_item_bad_count subject_id={sb.subject_id}
      如果 {bad} 大于 0
        报错 400 条目对不上知识点
      结束
    结束
    返回 {"ok": 1, "total": {total}, "created": {created}, "updated": {updated}}
  结束

  公开 函数 导入对照 file_path learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    # 返回 {ok, total, created, updated}，重复的对照（不分顺序）算 updated，不新增行
    # 报错 400 导入文件有错
    # 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以
    # 每行格式「编号A|编号B」，用 | 分隔；任一为空、或两端相同，报错 400 导入文件有错（整批不写）；对照两端可以是知识点也可以是条目，不核对是否存在，不加外键，不做环检查
    # 在一个事务里：每行把两端按字符串大小规范化（小的为 a_code），按 (a_code, b_code) 查 kg_contrast，没有则插入并 created+1，有则 updated+1
    # 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}
    设 doc = 读文档 {file_path}
    如果 {doc.error} 不为空
      报错 400 导入文件有错
    结束
    设 lines = 按正则切分 {doc.text} \r?\n
    设 re = ^(?P<ca>[^|]*)\|(?P<cb>[^|]*)$
    设 lgr = 调用 subject.取界面语言 username={learner 或}
    设 lang = {lgr.lang}
    设 total = 0
    遍历 raw 于 {lines}
      设 line = 替换 {raw} ^\s+|\s+$
      设 cm = 匹配 {line} ^\x23
      如果 {line} 不为空 且 {cm.matched} 不等于 是
        设 mm = 匹配 {line} {re}
        如果 {mm.matched} 不等于 是
          报错 400 导入文件有错
        结束
        如果 {mm.named.ca} 为空 或 {mm.named.cb} 为空 或 {mm.named.ca} 等于 {mm.named.cb}
          报错 400 导入文件有错
        结束
        设 cda = {mm.named.ca}
        设 cdb = {mm.named.cb}
        设 pc1 = 调用 编号前缀检查 subject_id={sb.subject_id} code={cda} lang={lang}
        设 pc2 = 调用 编号前缀检查 subject_id={sb.subject_id} code={cdb} lang={lang}
        设 total = 计算 {total} + 1
      结束
    结束
    设 created = 0
    设 updated = 0
    事务 app.db
      遍历 raw 于 {lines}
        设 line = 替换 {raw} ^\s+|\s+$
        设 cm = 匹配 {line} ^\x23
        如果 {line} 不为空 且 {cm.matched} 不等于 是
          设 mm = 匹配 {line} {re}
          设 lo = 查一值 app.db kg_str_min a={mm.named.ca} b={mm.named.cb}
          设 hi = 查一值 app.db kg_str_max a={mm.named.ca} b={mm.named.cb}
          设 ex = 查一值 app.db kg_contrast_count a_code={lo} b_code={hi} subject_id={sb.subject_id}
          如果 {ex} 大于 0
            设 updated = 计算 {updated} + 1
          否则
            设 w = 写库 app.db kg_contrast_insert a_code={lo} b_code={hi} subject_id={sb.subject_id}
            设 created = 计算 {created} + 1
          结束
        结束
      结束
    结束
    返回 {"ok": 1, "total": {total}, "created": {created}, "updated": {updated}}
  结束

  公开 函数 建知识点 code title learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 cd = 替换 {code} ^\s+|\s+$
    设 tt = 替换 {title} ^\s+|\s+$
    如果 {cd} 为空
      报错 400 编号不能为空
    结束
    如果 {tt} 为空
      报错 400 名称不能为空
    结束
    设 lt = 截取 {tt} 61
    如果 {lt} 不为空
      报错 400 名称最长60字
    结束
    设 fc = 调用 编号格式检查 subject_id={sb.subject_id} code={cd}
    设 own = 查一行 app.db kg_point_by_code code={cd} subject_id={sb.subject_id}
    如果 {own} 不为空
      报错 409 编号已存在
    结束
    设 oc = 查一值 app.db kg_point_other code={cd} subject_id={sb.subject_id}
    如果 {oc} 大于 0
      报错 409 编号已被其他科目使用
    结束
    设 pa.code = {cd}
    设 pa.title = {tt}
    设 pa.subject_id = {sb.subject_id}
    设 w = 写库表 app.db kg_point_insert {pa}
    返回 {"ok": 1, "code": "{cd}"}
  结束

  公开 函数 改知识点 code title learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 cd = 替换 {code} ^\s+|\s+$
    设 tt = 替换 {title} ^\s+|\s+$
    如果 {cd} 为空
      报错 400 编号不能为空
    结束
    如果 {tt} 为空
      报错 400 名称不能为空
    结束
    设 lt = 截取 {tt} 61
    如果 {lt} 不为空
      报错 400 名称最长60字
    结束
    设 p = 查一行 app.db kg_point_by_code code={cd} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 pa.code = {cd}
    设 pa.title = {tt}
    设 pa.subject_id = {sb.subject_id}
    设 w = 写库表 app.db kg_point_update {pa}
    返回 {"ok": 1}
  结束

  函数 外部引用 kind code subject_id
    设 refs = 解析JSON []
    设 tot = 0
    如果 {kind} 等于 point
      设 t1 = 查一值 app.db kg_table_exists name=lesson_point_link
      如果 {t1} 大于 0
        设 n = 查一值 app.db kg_ref_lesson_point code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "课文挂接", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
      设 t2 = 查一值 app.db kg_table_exists name=vocab_word
      如果 {t2} 大于 0
        设 n = 查一值 app.db kg_ref_vocab code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "单词", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
      设 t3 = 查一值 app.db kg_table_exists name=progress_answer
      如果 {t3} 大于 0
        设 n = 查一值 app.db kg_ref_answer code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "作答记录", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
      设 t4 = 查一值 app.db kg_table_exists name=progress_mastery
      如果 {t4} 大于 0
        设 n = 查一值 app.db kg_ref_mastery code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "掌握记录", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
      设 t5 = 查一值 app.db kg_table_exists name=progress_score
      如果 {t5} 大于 0
        设 n = 查一值 app.db kg_ref_score code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "得分记录", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
      设 t6 = 查一值 app.db kg_table_exists name=dictation_progress
      如果 {t6} 大于 0
        设 n = 查一值 app.db kg_ref_dictation code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "默写进度", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
      设 t7 = 查一值 app.db kg_table_exists name=teacher_assist_message
      如果 {t7} 大于 0
        设 n = 查一值 app.db kg_ref_assist code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "教师助手对话", "n": {n}, "block": 0}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
    结束
    如果 {kind} 等于 item
      设 t8 = 查一值 app.db kg_table_exists name=lesson_item_link
      如果 {t8} 大于 0
        设 n = 查一值 app.db kg_ref_lesson_item code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "课文挂接", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
      设 t9 = 查一值 app.db kg_table_exists name=quiz_question
      如果 {t9} 大于 0
        设 n = 查一值 app.db kg_ref_quiz_item code={code} subject_id={subject_id}
        如果 {n} 大于 0
          设 it = {"source": "题目", "n": {n}, "block": 1}
          设 refs = 列表加项 {refs} {it}
          设 tot = 计算 {tot} + {n}
        结束
      结束
    结束
    返回 {"total": {tot}, "refs": {refs}}
  结束

  公开 函数 查引用 code kind? learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 cd = 替换 {code} ^\s+|\s+$
    如果 {cd} 为空
      报错 400 编号不能为空
    结束
    如果 {kind} 不为空 且 {kind} 不等于 point 且 {kind} 不等于 item
      报错 400 kind 只能是 point 或 item
    结束
    设 kd = {kind}
    如果 {kd} 为空
      设 pp = 查一行 app.db kg_point_by_code code={cd} subject_id={sb.subject_id}
      设 ii = 查一行 app.db kg_item_by_code code={cd} subject_id={sb.subject_id}
      如果 {pp} 不为空
        设 kd = point
      否则如果 {ii} 不为空
        设 kd = item
      否则
        报错 404 没有这个编号
      结束
    否则如果 {kd} 等于 point
      设 pp = 查一行 app.db kg_point_by_code code={cd} subject_id={sb.subject_id}
      如果 {pp} 为空
        报错 404 没有这个编号
      结束
    否则
      设 ii = 查一行 app.db kg_item_by_code code={cd} subject_id={sb.subject_id}
      如果 {ii} 为空
        报错 404 没有这个编号
      结束
    结束
    设 refs = 解析JSON []
    设 tot = 0
    如果 {kd} 等于 point
      设 n1 = 查一值 app.db kg_ref_item_point code={cd} subject_id={sb.subject_id}
      如果 {n1} 大于 0
        设 it = {"source": "下挂条目", "n": {n1}, "block": 1}
        设 refs = 列表加项 {refs} {it}
        设 tot = 计算 {tot} + {n1}
      结束
      设 n2 = 查一值 app.db kg_ref_edge code={cd} subject_id={sb.subject_id}
      如果 {n2} 大于 0
        设 it = {"source": "前置边", "n": {n2}, "block": 0}
        设 refs = 列表加项 {refs} {it}
        设 tot = 计算 {tot} + {n2}
      结束
    否则
      设 n1 = 查一值 app.db kg_ref_item_prev code={cd} subject_id={sb.subject_id}
      如果 {n1} 大于 0
        设 it = {"source": "后一个条目", "n": {n1}, "block": 1}
        设 refs = 列表加项 {refs} {it}
        设 tot = 计算 {tot} + {n1}
      结束
    结束
    设 n3 = 查一值 app.db kg_ref_contrast code={cd} subject_id={sb.subject_id}
    如果 {n3} 大于 0
      设 it = {"source": "对照", "n": {n3}, "block": 0}
      设 refs = 列表加项 {refs} {it}
      设 tot = 计算 {tot} + {n3}
    结束
    设 ex = 调用 外部引用 kind={kd} code={cd} subject_id={sb.subject_id}
    遍历 x 于 {ex.refs}
      设 refs = 列表加项 {refs} {x}
    结束
    设 tot = 计算 {tot} + {ex.total}
    设 bs = 0
    遍历 y 于 {refs}
      如果 {y.block} 等于 1
        设 bs = 计算 {bs} + {y.n}
      结束
    结束
    设 dl = 0
    如果 {bs} 等于 0
      设 dl = 1
    结束
    返回 {"code": "{cd}", "kind": "{kd}", "total": {tot}, "deletable": {dl}, "refs": {refs}}
  结束

  公开 函数 删知识点 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 cd = 替换 {code} ^\s+|\s+$
    如果 {cd} 为空
      报错 400 编号不能为空
    结束
    设 p = 查一行 app.db kg_point_by_code code={cd} subject_id={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 q = 调用 查引用 code={cd} kind=point subject={sb.subject_id}
    如果 {q.deletable} 等于 0
      设 detail = {nothing 或}
      遍历 x 于 {q.refs}
        如果 {x.block} 等于 1
          如果 {detail} 为空
            设 detail = {x.source}{x.n}
          否则
            设 detail = {detail}、{x.source}{x.n}
          结束
        结束
      结束
      设 lgr = 调用 subject.取界面语言 username={learner 或}
      如果 {lgr.lang} 等于 ja
        报错 409 知識ポイントはまだ参照されているため削除できません（{detail}）
      结束
      报错 409 知识点还被引用，不能删除（{detail}）
    结束
    设 er = 0
    设 cr = 0
    事务 app.db
      设 er = 写库 app.db kg_edge_delete code={cd} subject_id={sb.subject_id}
      设 cr = 写库 app.db kg_contrast_delete code={cd} subject_id={sb.subject_id}
      设 w = 写库 app.db kg_point_delete code={cd} subject_id={sb.subject_id}
    结束
    返回 {"ok": 1, "edges_removed": {er}, "contrasts_removed": {cr}}
  结束

  公开 函数 删前置边 pre_code point_code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    如果 {pre_code} 为空 或 {point_code} 为空
      报错 400 编号不能为空
    结束
    设 ex = 查一值 app.db kg_edge_exists pre_code={pre_code} point_code={point_code} subject_id={sb.subject_id}
    如果 {ex} 等于 0
      报错 404 没有这条前置边
    结束
    设 n = 写库 app.db kg_edge_delete_pair pre_code={pre_code} point_code={point_code} subject_id={sb.subject_id}
    返回 {"ok": 1, "removed": {n}}
  结束

  公开 函数 建条目 code name point_code after_form? prev_code? learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 cd = 替换 {code} ^\s+|\s+$
    设 nm = 替换 {name} ^\s+|\s+$
    设 pc = 替换 {point_code} ^\s+|\s+$
    设 af = 替换 {after_form 或} ^\s+|\s+$
    设 pv = 替换 {prev_code 或} ^\s+|\s+$
    如果 {cd} 为空
      报错 400 编号不能为空
    结束
    如果 {nm} 为空
      报错 400 名称不能为空
    结束
    设 lt = 截取 {nm} 61
    如果 {lt} 不为空
      报错 400 名称最长60字
    结束
    如果 {pc} 为空
      报错 404 没有这个知识点
    结束
    设 fc = 调用 编号格式检查 subject_id={sb.subject_id} code={cd}
    设 own = 查一行 app.db kg_item_by_code code={cd} subject_id={sb.subject_id}
    如果 {own} 不为空
      报错 409 编号已存在
    结束
    设 oc = 查一值 app.db kg_item_other code={cd} subject_id={sb.subject_id}
    如果 {oc} 大于 0
      报错 409 编号已被其他科目使用
    结束
    设 pp = 查一行 app.db kg_point_by_code code={pc} subject_id={sb.subject_id}
    如果 {pp} 为空
      报错 404 没有这个知识点
    结束
    如果 {pv} 不为空
      设 pi = 查一行 app.db kg_item_by_code code={pv} subject_id={sb.subject_id}
      如果 {pi} 为空
        报错 404 没有这个前一个条目
      结束
    结束
    设 ia.code = {cd}
    设 ia.name = {nm}
    设 ia.point_code = {pc}
    设 ia.after_form = {af}
    设 ia.prev_code = {pv}
    设 ia.subject_id = {sb.subject_id}
    设 w = 写库表 app.db kg_item_insert {ia}
    返回 {"ok": 1, "code": "{cd}"}
  结束

  公开 函数 改条目 code name point_code after_form? prev_code? learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 cd = 替换 {code} ^\s+|\s+$
    设 nm = 替换 {name} ^\s+|\s+$
    设 pc = 替换 {point_code} ^\s+|\s+$
    设 af = 替换 {after_form 或} ^\s+|\s+$
    设 pv = 替换 {prev_code 或} ^\s+|\s+$
    如果 {cd} 为空
      报错 400 编号不能为空
    结束
    如果 {nm} 为空
      报错 400 名称不能为空
    结束
    设 lt = 截取 {nm} 61
    如果 {lt} 不为空
      报错 400 名称最长60字
    结束
    设 it = 查一行 app.db kg_item_by_code code={cd} subject_id={sb.subject_id}
    如果 {it} 为空
      报错 404 没有这个条目
    结束
    设 pp = 查一行 app.db kg_point_by_code code={pc} subject_id={sb.subject_id}
    如果 {pp} 为空
      报错 404 没有这个知识点
    结束
    如果 {pv} 不为空
      如果 {pv} 等于 {cd}
        报错 400 不能以自己为前一个条目
      结束
      设 pi = 查一行 app.db kg_item_by_code code={pv} subject_id={sb.subject_id}
      如果 {pi} 为空
        报错 404 没有这个前一个条目
      结束
      设 cur = {pv}
      当 {cur} 不为空 最多 1000 次
        如果 {cur} 等于 {cd}
          报错 400 前一个条目会形成环
        结束
        设 row = 查一行 app.db kg_item_by_code code={cur} subject_id={sb.subject_id}
        设 cur = {row.prev_code 或}
      结束
    结束
    设 ia.code = {cd}
    设 ia.name = {nm}
    设 ia.point_code = {pc}
    设 ia.after_form = {af}
    设 ia.prev_code = {pv}
    设 ia.subject_id = {sb.subject_id}
    设 w = 写库表 app.db kg_item_update {ia}
    返回 {"ok": 1}
  结束

  公开 函数 删条目 code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 cd = 替换 {code} ^\s+|\s+$
    如果 {cd} 为空
      报错 400 编号不能为空
    结束
    设 it = 查一行 app.db kg_item_by_code code={cd} subject_id={sb.subject_id}
    如果 {it} 为空
      报错 404 没有这个条目
    结束
    设 q = 调用 查引用 code={cd} kind=item subject={sb.subject_id}
    如果 {q.deletable} 等于 0
      设 detail = {nothing 或}
      遍历 x 于 {q.refs}
        如果 {x.block} 等于 1
          如果 {detail} 为空
            设 detail = {x.source}{x.n}
          否则
            设 detail = {detail}、{x.source}{x.n}
          结束
        结束
      结束
      设 lgr = 调用 subject.取界面语言 username={learner 或}
      如果 {lgr.lang} 等于 ja
        报错 409 項目はまだ参照されているため削除できません（{detail}）
      结束
      报错 409 条目还被引用，不能删除（{detail}）
    结束
    设 cr = 0
    事务 app.db
      设 cr = 写库 app.db kg_contrast_delete code={cd} subject_id={sb.subject_id}
      设 w = 写库 app.db kg_item_delete code={cd} subject_id={sb.subject_id}
    结束
    返回 {"ok": 1, "contrasts_removed": {cr}}
  结束

  公开 函数 加对照 a_code b_code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 ca = 替换 {a_code} ^\s+|\s+$
    设 cb = 替换 {b_code} ^\s+|\s+$
    如果 {ca} 为空 或 {cb} 为空
      报错 400 编号不能为空
    结束
    如果 {ca} 等于 {cb}
      报错 400 对照两端不能相同
    结束
    设 na = 查一值 app.db kg_code_exists code={ca} subject_id={sb.subject_id}
    设 nb = 查一值 app.db kg_code_exists code={cb} subject_id={sb.subject_id}
    如果 {na} 等于 0 或 {nb} 等于 0
      报错 404 没有这个编号
    结束
    设 lo = 查一值 app.db kg_str_min a={ca} b={cb}
    设 hi = 查一值 app.db kg_str_max a={ca} b={cb}
    设 ex = 查一值 app.db kg_contrast_count a_code={lo} b_code={hi} subject_id={sb.subject_id}
    如果 {ex} 大于 0
      返回 {"ok": 1, "created": 0}
    结束
    设 w = 写库 app.db kg_contrast_insert a_code={lo} b_code={hi} subject_id={sb.subject_id}
    返回 {"ok": 1, "created": 1}
  结束

  公开 函数 删对照 a_code b_code learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 ca = 替换 {a_code} ^\s+|\s+$
    设 cb = 替换 {b_code} ^\s+|\s+$
    如果 {ca} 为空 或 {cb} 为空
      报错 400 编号不能为空
    结束
    设 lo = 查一值 app.db kg_str_min a={ca} b={cb}
    设 hi = 查一值 app.db kg_str_max a={ca} b={cb}
    设 ex = 查一值 app.db kg_contrast_count a_code={lo} b_code={hi} subject_id={sb.subject_id}
    如果 {ex} 等于 0
      报错 404 没有这条对照
    结束
    设 w = 写库 app.db kg_contrast_delete_pair a_code={lo} b_code={hi} subject_id={sb.subject_id}
    返回 {"ok": 1}
  结束

  函数 编号格式检查 subject_id code
    设 mt = 匹配 {code} ^[A-Za-z0-9][A-Za-z0-9_.-]*$
    设 lg = 截取 {code} 61
    如果 {mt.matched} 不等于 是 或 {lg} 不为空
      报错 400 编号只能用字母、数字、点、下划线、短横，最长60
    结束
    设 pc = 调用 编号前缀检查 subject_id={subject_id} code={code}
    返回 {"ok": 1}
  结束

  函数 本科目 learner current_role auth_mode subject need?
    # 返回 {subject_id}；本次请求用哪个科目
    设 r = 调用 subject.解析科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need={need 或}
    返回 {"subject_id": {r.subject_id}}
  结束

  函数 编号前缀检查 subject_id code lang?
    # 返回 {ok}；日语（1）豁免
    如果 {subject_id} 等于 1
      返回 {"ok": 1}
    结束
    设 sc = 查一值 app.db kg_subject_code subject_id={subject_id}
    设 pre = {sc}.
    设 mt = 匹配 {code} ^[a-z][a-z0-9_]*\.[A-Za-z0-9_-]+$
    设 bad = 1
    如果 {sc} 不为空 且 {mt.matched} 等于 是
      如果 {code} 开头是 {pre}
        设 bad = 0
      结束
    结束
    如果 {bad} 等于 1
      如果 {lang} 等于 ja
        报错 400 番号は「{sc}.」で始めてください
      结束
      报错 400 编号要以「{sc}.」开头
    结束
    返回 {"ok": 1}
  结束

  函数 拼原因 rs add
    如果 {rs} 为空
      返回 {"r": "{add}"}
    结束
    返回 {"r": "{rs}；{add}"}
  结束

  函数 边可达 edges start target
    设 vis = @{start}@
    设 changed = 1
    当 {changed} 等于 1 最多 500 次
      设 changed = 0
      遍历 ed 于 {edges}
        设 k1 = @{ed.pre_code}@
        如果 {vis} 包含 {k1}
          设 k2 = @{ed.point_code}@
          如果 {vis} 不包含 {k2}
            设 vis = {vis}{ed.point_code}@
            设 changed = 1
          结束
        结束
      结束
    结束
    设 tk = @{target}@
    设 rv = 0
    如果 {vis} 包含 {tk}
      设 rv = 1
    结束
    返回 {"r": {rv}}
  结束

  公开 函数 导入前置边 file_path learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 doc = 读文档 {file_path}
    如果 {doc.error} 不为空
      报错 400 导入文件有错
    结束
    设 lines = 按正则切分 {doc.text} \r?\n
    设 re = ^(?P<pa>[^|]*)[|](?P<pb>[^|]*)$
    设 total = 0
    遍历 raw 于 {lines}
      设 line = 替换 {raw} ^\s+|\s+$
      设 cm = 匹配 {line} ^\x23
      如果 {line} 不为空 且 {cm.matched} 不等于 是
        设 mm = 匹配 {line} {re}
        如果 {mm.matched} 不等于 是
          报错 400 导入文件有错
        结束
        如果 {mm.named.pa} 为空 或 {mm.named.pb} 为空 或 {mm.named.pa} 等于 {mm.named.pb}
          报错 400 导入文件有错
        结束
        设 p1 = 查一行 app.db kg_point_by_code code={mm.named.pa} subject_id={sb.subject_id}
        设 p2 = 查一行 app.db kg_point_by_code code={mm.named.pb} subject_id={sb.subject_id}
        如果 {p1} 为空 或 {p2} 为空
          报错 400 前置边对不上知识点
        结束
        设 total = 计算 {total} + 1
      结束
    结束
    设 created = 0
    设 updated = 0
    事务 app.db
      遍历 raw 于 {lines}
        设 line = 替换 {raw} ^\s+|\s+$
        设 cm = 匹配 {line} ^\x23
        如果 {line} 不为空 且 {cm.matched} 不等于 是
          设 mm = 匹配 {line} {re}
          设 pre = {mm.named.pa}
          设 pst = {mm.named.pb}
          设 ex = 查一值 app.db kg_edge_exists pre_code={pre} point_code={pst} subject_id={sb.subject_id}
          如果 {ex} 大于 0
            设 updated = 计算 {updated} + 1
          否则
            设 cy = 查一值 app.db kg_edge_cycle pre_code={pre} point_code={pst} subject_id={sb.subject_id}
            如果 {cy} 大于 0
              报错 400 这批前置边会形成环
            结束
            设 w = 写库 app.db kg_edge_insert pre_code={pre} point_code={pst} subject_id={sb.subject_id}
            设 created = 计算 {created} + 1
          结束
        结束
      结束
    结束
    返回 {"ok": 1, "total": {total}, "created": {created}, "updated": {updated}}
  结束

  函数 读导入行 kind file_path lang?
    设 rows = 解析JSON []
    设 m1 = 匹配 {file_path} (?i)[.](md|txt)$
    设 m2 = 匹配 {file_path} (?i)[.]csv$
    设 m3 = 匹配 {file_path} (?i)[.]json$
    如果 {m1.matched} 等于 是
      设 doc = 读文档 {file_path}
      如果 {doc.error} 不为空
        报错 400 导入文件读不了
      结束
      设 lines = 按正则切分 {doc.text} \r?\n
      设 re = ^(?P<a>[^|]*)[|](?P<b>[^|]*)[|](?P<c>[^|]*)[|](?P<d>[^|]*)[|](?P<e>[^|]*)(?:[|].*)?$
      设 ln = 0
      遍历 raw 于 {lines}
        设 ln = 计算 {ln} + 1
        设 line = 替换 {raw} ^\s+|\s+$
        设 cm = 匹配 {line} ^\x23
        如果 {line} 不为空 且 {cm.matched} 不等于 是
          设 padded = {line}||||
          设 mm = 匹配 {padded} {re}
          设 pcs = 找全部 {line} [|]
          设 pn = 列表长度 {pcs}
          设 np = 计算 {pn} + 1
          设 lim = 2
          如果 {kind} 等于 item
            设 lim = 5
          结束
          设 exf = 0
          如果 {np} 大于 {lim}
            设 exf = 1
          结束
          设 it = {"line": {ln}, "a": "{mm.named.a}", "b": "{mm.named.b}", "c": "{mm.named.c}", "d": "{mm.named.d}", "e": "{mm.named.e}", "extra": {exf}}
          设 rows = 列表加项 {rows} {it}
        结束
      结束
    否则如果 {m2.matched} 等于 是 或 {m3.matched} 等于 是
      设 src = 解析JSON []
      设 ln = 0
      如果 {m2.matched} 等于 是
        设 src = 读CSV {file_path}
        设 ln = 1
      否则
        读JSON js = {file_path}
        设 src = {js}
      结束
      设 c1 = code
      设 c2 = title
      设 c3 = {nothing 或}
      如果 {kind} 等于 item
        设 c2 = name
        设 c3 = point_code
      否则如果 {kind} 等于 edge
        设 c1 = pre_code
        设 c2 = point_code
      否则如果 {kind} 等于 contrast
        设 c1 = a_code
        设 c2 = b_code
      结束
      遍历 x 于 {src}
        设 ln = 计算 {ln} + 1
        设 ra = {nothing 或}
        设 rb = {nothing 或}
        设 rc = {nothing 或}
        设 rd = {nothing 或}
        设 rf = {nothing 或}
        如果 {kind} 等于 point
          设 ra = {x.code 或}
          设 rb = {x.title 或}
        否则如果 {kind} 等于 item
          设 ra = {x.code 或}
          设 rb = {x.name 或}
          设 rc = {x.point_code 或}
          设 rd = {x.after_form 或}
          设 rf = {x.prev_code 或}
        否则如果 {kind} 等于 edge
          设 ra = {x.pre_code 或}
          设 rb = {x.point_code 或}
        否则
          设 ra = {x.a_code 或}
          设 rb = {x.b_code 或}
        结束
        设 it = {"line": {ln}, "a": "{ra}", "b": "{rb}", "c": "{rc}", "d": "{rd}", "e": "{rf}", "extra": 0}
        设 rows = 列表加项 {rows} {it}
      结束
      设 n0 = 列表长度 {rows}
      如果 {n0} 大于 0
        设 hl = 读文本行 {file_path}
        设 hs = @
        设 jt = @
        如果 {m2.matched} 等于 是
          遍历 hh 于 {hl}
            设 h1 = 替换 {hh} ^\ufeff
            设 hparts = 按正则切分 {h1} ,
            遍历 pp 于 {hparts}
              设 p2 = 替换 {pp} ^\s+|\s+$
              设 hs = {hs}{p2}@
            结束
            跳出
          结束
        否则
          遍历 jj 于 {hl}
            设 jt = {jt}{jj}
          结束
        结束
        设 ok1 = 0
        设 ok2 = 0
        设 ok3 = 1
        如果 {m2.matched} 等于 是
          设 k1 = @{c1}@
          设 k2 = @{c2}@
          如果 {hs} 包含 {k1}
            设 ok1 = 1
          结束
          如果 {hs} 包含 {k2}
            设 ok2 = 1
          结束
          如果 {c3} 不为空
            设 k3 = @{c3}@
            如果 {hs} 不包含 {k3}
              设 ok3 = 0
            结束
          结束
        否则
          设 q1 = 匹配 {jt} "{c1}"\s*:
          设 q2 = 匹配 {jt} "{c2}"\s*:
          如果 {q1.matched} 等于 是
            设 ok1 = 1
          结束
          如果 {q2.matched} 等于 是
            设 ok2 = 1
          结束
          如果 {c3} 不为空
            设 q3 = 匹配 {jt} "{c3}"\s*:
            如果 {q3.matched} 不等于 是
              设 ok3 = 0
            结束
          结束
        结束
        如果 {ok1} 等于 0
          如果 {lang} 等于 ja
            报错 400 インポートファイルを読み込めません（{c1} がありません）
          结束
          报错 400 导入文件读不了（缺{c1}）
        结束
        如果 {ok2} 等于 0
          如果 {lang} 等于 ja
            报错 400 インポートファイルを読み込めません（{c2} がありません）
          结束
          报错 400 导入文件读不了（缺{c2}）
        结束
        如果 {ok3} 等于 0
          如果 {lang} 等于 ja
            报错 400 インポートファイルを読み込めません（{c3} がありません）
          结束
          报错 400 导入文件读不了（缺{c3}）
        结束
      结束
    否则
      报错 400 文件类型只能是 md、txt、csv、json
    结束
    设 n = 列表长度 {rows}
    如果 {n} 等于 0
      报错 400 导入文件没有数据行
    结束
    如果 {n} 大于 2000
      报错 400 一次最多导入2000行
    结束
    返回 {"rows": {rows}}
  结束

  公开 函数 导入预检 kind file_path learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    如果 {kind} 不等于 point 且 {kind} 不等于 item 且 {kind} 不等于 edge 且 {kind} 不等于 contrast
      报错 400 导入类型不对
    结束
    设 pm = 匹配 {file_path} ^uploads/[^/\\]+$
    设 pd = 匹配 {file_path} [.][.]
    如果 {pm.matched} 不等于 是 或 {pd.matched} 等于 是
      报错 400 导入文件路径不对
    结束
    设 sid = {sb.subject_id}
    设 acts = {"e": "报错", "u": "更新", "n": "新增"}
    设 lgr = 调用 subject.取界面语言 username={learner 或}
    设 rd = 调用 读导入行 kind={kind} file_path={file_path} lang={lgr.lang}
    设 fileitems = @
    如果 {kind} 等于 item
      遍历 x 于 {rd.rows}
        设 fileitems = {fileitems}{x.a}@
      结束
    结束
    设 mid = 解析JSON []
    遍历 x 于 {rd.rows}
      设 xa = {x.a}
      设 xb = {x.b}
      设 xc = {x.c}
      设 xd = {x.d}
      设 xe = {x.e}
      设 rs = {nothing 或}
      设 cdv = {xa}
      如果 {x.extra} 等于 1
        设 em = 项数多了：对照每行最多2项（编号A|编号B），行尾多余的|也算一项
        如果 {kind} 等于 point
          设 em = 项数多了：知识点每行最多2项（编号|名称），行尾多余的|也算一项
        否则如果 {kind} 等于 item
          设 em = 项数多了：条目每行最多5项（编号|名称|知识点编号|接在哪个形式后|前一个条目编号），行尾多余的|也算一项
        否则如果 {kind} 等于 edge
          设 em = 项数多了：前置边每行最多2项（前置编号|后续编号），行尾多余的|也算一项
        结束
        设 t = 调用 拼原因 rs={rs} add={em}
        设 rs = {t.r}
      结束
      如果 {kind} 等于 point
        如果 {xa} 为空
          设 t = 调用 拼原因 rs={rs} add=缺编号
          设 rs = {t.r}
        结束
        如果 {xb} 为空
          设 t = 调用 拼原因 rs={rs} add=缺名称
          设 rs = {t.r}
        结束
        如果 {xa} 不为空
          设 fc = 调用 编号格式检查 subject_id={sid} code={xa} 出错时 er
          如果 {er} 不为空
            设 t = 调用 拼原因 rs={rs} add={er.error}
            设 rs = {t.r}
          结束
          设 oc = 查一值 app.db kg_point_other code={xa} subject_id={sid}
          如果 {oc} 大于 0
            设 t = 调用 拼原因 rs={rs} add=编号已被其他科目使用
            设 rs = {t.r}
          结束
        结束
        设 lt = 截取 {xb} 61
        如果 {lt} 不为空
          设 t = 调用 拼原因 rs={rs} add=名称最长60字
          设 rs = {t.r}
        结束
      否则如果 {kind} 等于 item
        如果 {xa} 为空
          设 t = 调用 拼原因 rs={rs} add=缺编号
          设 rs = {t.r}
        结束
        如果 {xb} 为空
          设 t = 调用 拼原因 rs={rs} add=缺名称
          设 rs = {t.r}
        结束
        如果 {xc} 为空
          设 t = 调用 拼原因 rs={rs} add=缺知识点编号
          设 rs = {t.r}
        结束
        如果 {xa} 不为空
          设 fc = 调用 编号格式检查 subject_id={sid} code={xa} 出错时 er
          如果 {er} 不为空
            设 t = 调用 拼原因 rs={rs} add={er.error}
            设 rs = {t.r}
          结束
          设 oc = 查一值 app.db kg_item_other code={xa} subject_id={sid}
          如果 {oc} 大于 0
            设 t = 调用 拼原因 rs={rs} add=编号已被其他科目使用
            设 rs = {t.r}
          结束
        结束
        设 lt = 截取 {xb} 61
        如果 {lt} 不为空
          设 t = 调用 拼原因 rs={rs} add=名称最长60字
          设 rs = {t.r}
        结束
        如果 {xc} 不为空
          设 pp = 查一行 app.db kg_point_by_code code={xc} subject_id={sid}
          如果 {pp} 为空
            设 t = 调用 拼原因 rs={rs} add=没有这个知识点
            设 rs = {t.r}
          结束
        结束
        如果 {xe} 不为空
          设 pi = 查一行 app.db kg_item_by_code code={xe} subject_id={sid}
          设 fk = @{xe}@
          如果 {pi} 为空 且 {fileitems} 不包含 {fk}
            设 t = 调用 拼原因 rs={rs} add=没有这个前一个条目
            设 rs = {t.r}
          结束
        结束
      否则如果 {kind} 等于 edge
        设 cdv = {xa}>{xb}
        如果 {xa} 为空
          设 t = 调用 拼原因 rs={rs} add=缺前置编号
          设 rs = {t.r}
        结束
        如果 {xb} 为空
          设 t = 调用 拼原因 rs={rs} add=缺后续编号
          设 rs = {t.r}
        结束
        如果 {xa} 不为空 且 {xa} 等于 {xb}
          设 t = 调用 拼原因 rs={rs} add=不能以自己为前置
          设 rs = {t.r}
        结束
        设 nf = 0
        如果 {xa} 不为空
          设 p1 = 查一行 app.db kg_point_by_code code={xa} subject_id={sid}
          如果 {p1} 为空
            设 nf = 1
          结束
        结束
        如果 {xb} 不为空
          设 p2 = 查一行 app.db kg_point_by_code code={xb} subject_id={sid}
          如果 {p2} 为空
            设 nf = 1
          结束
        结束
        如果 {nf} 等于 1
          设 t = 调用 拼原因 rs={rs} add=没有这个知识点
          设 rs = {t.r}
        结束
      否则
        设 cdv = {xa}~{xb}
        如果 {xa} 为空 或 {xb} 为空
          设 t = 调用 拼原因 rs={rs} add=缺编号
          设 rs = {t.r}
        结束
        如果 {xa} 不为空 且 {xa} 等于 {xb}
          设 t = 调用 拼原因 rs={rs} add=对照两端不能相同
          设 rs = {t.r}
        结束
        如果 {xa} 不为空
          设 pc1 = 调用 编号前缀检查 subject_id={sid} code={xa} 出错时 er
          如果 {er} 不为空
            设 t = 调用 拼原因 rs={rs} add={er.error}
            设 rs = {t.r}
          结束
        结束
        如果 {xb} 不为空
          设 pc2 = 调用 编号前缀检查 subject_id={sid} code={xb} 出错时 er
          如果 {er} 不为空
            设 t = 调用 拼原因 rs={rs} add={er.error}
            设 rs = {t.r}
          结束
        结束
      结束
      设 mr = {"line": {x.line}, "code": "{cdv}", "label": "{xb}", "reason": "{rs}", "a": "{xa}", "b": "{xb}", "c": "{xc}", "d": "{xd}", "e": "{xe}"}
      设 mid = 列表加项 {mid} {mr}
    结束
    设 mid2 = {mid}
    如果 {kind} 等于 edge
      设 combined = 查询 app.db kg_edge_list subject_id={sid}
      遍历 x 于 {mid}
        如果 {x.reason} 为空
          设 ce = {"pre_code": "{x.a}", "point_code": "{x.b}"}
          设 combined = 列表加项 {combined} {ce}
        结束
      结束
      设 mid2 = 解析JSON []
      遍历 x 于 {mid}
        设 rs = {x.reason}
        如果 {rs} 为空
          设 rch = 调用 边可达 edges={combined} start={x.b} target={x.a}
          如果 {rch.r} 等于 1
            设 rs = 会形成环：{x.a}>{x.b}>…>{x.a}
          结束
        结束
        设 nr = {"line": {x.line}, "code": "{x.code}", "label": "{x.label}", "reason": "{rs}", "a": "{x.a}", "b": "{x.b}", "c": "{x.c}", "d": "{x.d}", "e": "{x.e}"}
        设 mid2 = 列表加项 {mid2} {nr}
      结束
    结束
    设 out = 解析JSON []
    设 seen = @
    设 dupkeys = @
    设 created = 0
    设 updated = 0
    设 errn = 0
    遍历 x 于 {mid2}
      设 rs = {x.reason}
      设 k = {nothing 或}
      设 act = {acts.e}
      如果 {rs} 不为空
        设 errn = 计算 {errn} + 1
      否则
        设 xa = {x.a}
        设 xb = {x.b}
        设 xc = {x.c}
        设 xd = {x.d}
        设 xe = {x.e}
        设 ex = 0
        设 same = 0
        设 k = {xa}
        如果 {kind} 等于 point
          设 p = 查一行 app.db kg_point_by_code code={xa} subject_id={sid}
          如果 {p} 不为空
            设 ex = 1
            如果 {p.title} 等于 {xb}
              设 same = 1
            结束
          结束
        否则如果 {kind} 等于 item
          设 p = 查一行 app.db kg_item_by_code code={xa} subject_id={sid}
          如果 {p} 不为空
            设 ex = 1
            设 paf = {p.after_form 或}
            设 ppv = {p.prev_code 或}
            如果 {p.name} 等于 {xb} 且 {p.point_code} 等于 {xc} 且 {paf} 等于 {xd} 且 {ppv} 等于 {xe}
              设 same = 1
            结束
          结束
        否则如果 {kind} 等于 edge
          设 k = {xa}>{xb}
          设 ec = 查一值 app.db kg_edge_exists pre_code={xa} point_code={xb} subject_id={sid}
          如果 {ec} 大于 0
            设 ex = 1
            设 same = 1
          结束
        否则
          设 lo = 查一值 app.db kg_str_min a={xa} b={xb}
          设 hi = 查一值 app.db kg_str_max a={xa} b={xb}
          设 k = {lo}~{hi}
          设 ec = 查一值 app.db kg_contrast_count a_code={lo} b_code={hi} subject_id={sid}
          如果 {ec} 大于 0
            设 ex = 1
            设 same = 1
          结束
        结束
        设 sk = @{k}@
        设 isdup = 0
        如果 {seen} 包含 {sk}
          设 isdup = 1
          设 dupkeys = {dupkeys}{k}@
        结束
        如果 {ex} 等于 1
          设 act = {acts.u}
          设 updated = 计算 {updated} + 1
          如果 {same} 等于 1
            如果 {kind} 等于 edge 或 {kind} 等于 contrast
              设 rs = 已存在
            否则
              设 rs = 内容相同
            结束
          结束
        否则如果 {seen} 包含 {sk}
          设 act = {acts.u}
          设 updated = 计算 {updated} + 1
          设 rs = {nothing 或}
        否则
          设 act = {acts.n}
          设 created = 计算 {created} + 1
        结束
        设 seen = {seen}{sk}
      结束
      设 orow = {"line": {x.line}, "code": "{x.code}", "label": "{x.label}", "action": "{act}", "k": "{k}", "reason": "{rs}", "a": "{x.a}", "b": "{x.b}", "c": "{x.c}", "d": "{x.d}", "e": "{x.e}"}
      设 out = 列表加项 {out} {orow}
    结束
    设 out2 = 解析JSON []
    遍历 y 于 {out}
      设 yr = {y.reason}
      设 yk = {y.k}
      设 ysk = @{yk}@
      如果 {yk} 不为空 且 {dupkeys} 包含 {ysk}
        设 lastl = {y.line}
        遍历 z 于 {out}
          如果 {z.k} 等于 {yk}
            设 lastl = {z.line}
          结束
        结束
        如果 {lastl} 不等于 {y.line}
          设 t = 调用 拼原因 rs={yr} add=被第{lastl}行覆盖
          设 yr = {t.r}
        否则
          设 t = 调用 拼原因 rs={yr} add=本文件重复，以本行为准
          设 yr = {t.r}
        结束
      结束
      设 orow2 = {"line": {y.line}, "code": "{y.code}", "label": "{y.label}", "action": "{y.action}", "reason": "{yr}", "a": "{y.a}", "b": "{y.b}", "c": "{y.c}", "d": "{y.d}", "e": "{y.e}"}
      设 out2 = 列表加项 {out2} {orow2}
    结束
    设 total = 列表长度 {out2}
    设 okn = 计算 {created} + {updated}
    返回 {"kind": "{kind}", "total": {total}, "ok_count": {okn}, "error_count": {errn}, "created": {created}, "updated": {updated}, "rows": {out2}}
  结束

  函数 写入导入行 kind rows subject_id
    设 created = 0
    设 updated = 0
    设 total = 0
    事务 app.db
      遍历 x 于 {rows}
        设 total = 计算 {total} + 1
        如果 {kind} 等于 point
          设 p = 查一行 app.db kg_point_by_code code={x.a} subject_id={subject_id}
          设 pa.code = {x.a}
          设 pa.title = {x.b}
          设 pa.subject_id = {subject_id}
          如果 {p} 为空
            设 w = 写库表 app.db kg_point_insert {pa}
            设 created = 计算 {created} + 1
          否则
            设 w = 写库表 app.db kg_point_update {pa}
            设 updated = 计算 {updated} + 1
          结束
        否则如果 {kind} 等于 item
          设 p = 查一行 app.db kg_item_by_code code={x.a} subject_id={subject_id}
          设 ia.code = {x.a}
          设 ia.name = {x.b}
          设 ia.point_code = {x.c}
          设 ia.after_form = {x.d}
          设 ia.prev_code = {x.e}
          设 ia.subject_id = {subject_id}
          如果 {p} 为空
            设 w = 写库表 app.db kg_item_insert {ia}
            设 created = 计算 {created} + 1
          否则
            设 w = 写库表 app.db kg_item_update {ia}
            设 updated = 计算 {updated} + 1
          结束
        否则如果 {kind} 等于 edge
          设 ex = 查一值 app.db kg_edge_exists pre_code={x.a} point_code={x.b} subject_id={subject_id}
          如果 {ex} 大于 0
            设 updated = 计算 {updated} + 1
          否则
            设 cy = 查一值 app.db kg_edge_cycle pre_code={x.a} point_code={x.b} subject_id={subject_id}
            如果 {cy} 大于 0
              报错 400 导入文件有错
            结束
            设 w = 写库 app.db kg_edge_insert pre_code={x.a} point_code={x.b} subject_id={subject_id}
            设 created = 计算 {created} + 1
          结束
        否则
          设 lo = 查一值 app.db kg_str_min a={x.a} b={x.b}
          设 hi = 查一值 app.db kg_str_max a={x.a} b={x.b}
          设 ex = 查一值 app.db kg_contrast_count a_code={lo} b_code={hi} subject_id={subject_id}
          如果 {ex} 大于 0
            设 updated = 计算 {updated} + 1
          否则
            设 w = 写库 app.db kg_contrast_insert a_code={lo} b_code={hi} subject_id={subject_id}
            设 created = 计算 {created} + 1
          结束
        结束
      结束
      如果 {kind} 等于 item
        设 bad = 查一值 app.db kg_item_bad_count subject_id={subject_id}
        如果 {bad} 大于 0
          报错 400 导入文件有错
        结束
      结束
    结束
    返回 {"ok": 1, "total": {total}, "created": {created}, "updated": {updated}}
  结束

  公开 函数 确认导入 kind file_path learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或} need=write
    设 sid = {sb.subject_id}
    设 pm = 匹配 {file_path} ^uploads/[^/\\]+$
    设 pd = 匹配 {file_path} [.][.]
    设 xm = 匹配 {file_path} (?i)[.](md|txt|csv|json)$
    如果 {pm.matched} 不等于 是 或 {pd.matched} 等于 是 或 {xm.matched} 不等于 是
      报错 400 导入文件路径不对
    结束
    设 pv = 调用 导入预检 kind={kind} file_path={file_path} subject={sid}
    如果 {pv.error_count} 大于 0
      设 lgr = 调用 subject.取界面语言 username={learner 或}
      设 msg = {nothing 或}
      遍历 x 于 {pv.rows}
        如果 {msg} 为空 且 {x.action} 等于 报错
          如果 {lgr.lang} 等于 ja
            设 msg = {x.line} 行目：{x.reason}
          否则
            设 msg = 第{x.line}行：{x.reason}
          结束
        结束
      结束
      如果 {lgr.lang} 等于 ja
        报错 400 インポートファイルにエラーがあります（{msg}）
      结束
      报错 400 导入文件有错（{msg}）
    结束
    设 tm = 匹配 {file_path} (?i)[.](md|txt)$
    如果 {tm.matched} 等于 是
      如果 {kind} 等于 point
        设 r = 调用 导入知识点 file_path={file_path} subject={sid}
      否则如果 {kind} 等于 item
        设 r = 调用 导入条目 file_path={file_path} subject={sid}
      否则如果 {kind} 等于 contrast
        设 r = 调用 导入对照 file_path={file_path} subject={sid}
      否则
        设 r = 调用 导入前置边 file_path={file_path} subject={sid}
      结束
    否则
      设 r = 调用 写入导入行 kind={kind} rows={pv.rows} subject_id={sid}
    结束
    返回 {"ok": 1, "kind": "{kind}", "total": {r.total}, "created": {r.created}, "updated": {r.updated}}
  结束

  公开 函数 导出文本 kind? learner? current_role? auth_mode? subject?
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 kd = {kind 或}
    如果 {kd} 为空
      设 kd = all
    结束
    如果 {kd} 不等于 all 且 {kd} 不等于 point 且 {kd} 不等于 item 且 {kd} 不等于 edge 且 {kd} 不等于 contrast
      报错 400 导出类型不对
    结束
    设 g = 调用 导出图 subject={sb.subject_id}
    设 il = 调用 列条目 subject={sb.subject_id}
    设 tp = {nothing 或}
    遍历 x 于 {g.points}
      设 l1 = {x.code}|{x.title}
      如果 {tp} 为空
        设 tp = {l1}
      否则
        设 tp = {tp}§{l1}
      结束
    结束
    设 ti = {nothing 或}
    遍历 x 于 {il.items}
      设 l1 = {x.code}|{x.name}|{x.point_code}|{x.after_form 或}|{x.prev_code 或}
      如果 {ti} 为空
        设 ti = {l1}
      否则
        设 ti = {ti}§{l1}
      结束
    结束
    设 te = {nothing 或}
    遍历 x 于 {g.edges}
      设 l1 = {x.pre_code}|{x.point_code}
      如果 {te} 为空
        设 te = {l1}
      否则
        设 te = {te}§{l1}
      结束
    结束
    设 tc = {nothing 或}
    遍历 x 于 {g.contrasts}
      设 l1 = {x.a_code}|{x.b_code}
      如果 {tc} 为空
        设 tc = {l1}
      否则
        设 tc = {tc}§{l1}
      结束
    结束
    设 cnt = 0
    设 txt = {nothing 或}
    如果 {kd} 等于 point
      设 txt = {tp}
      设 cnt = {g.point_count}
    否则如果 {kd} 等于 item
      设 txt = {ti}
      设 cnt = {il.total}
    否则如果 {kd} 等于 edge
      设 txt = {te}
      设 cnt = {g.edge_count}
    否则如果 {kd} 等于 contrast
      设 txt = {tc}
      设 cnt = {g.contrast_count}
    否则
      设 h1 = {"t": "# 知识点"}
      设 h2 = {"t": "# 条目"}
      设 h3 = {"t": "# 前置边"}
      设 h4 = {"t": "# 对照"}
      设 txt = {h1.t}§{tp}§{h2.t}§{ti}§{h3.t}§{te}§{h4.t}§{tc}
      设 cnt = 计算 {g.point_count} + {il.total} + {g.edge_count} + {g.contrast_count}
    结束
    设 txt = 替换 {txt} § \n
    返回 {"kind": "{kd}", "count": {cnt}, "text": "{txt}"}
  结束

  函数 页面身份 learner current_role auth_mode subject_id
    如果 {auth_mode} 不等于 on
      返回 {"can_write": 1, "kgm_role": "单人"}
    结束
    设 w = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={subject_id} need=write auth_mode={auth_mode}
    如果 {w.ok} 等于 1
      如果 {w.via} 等于 editor
        返回 {"can_write": 1, "kgm_role": "协作"}
      结束
      返回 {"can_write": 1, "kgm_role": "负责"}
    结束
    设 rd = 调用 subject.科目访问 learner={learner} current_role={current_role} subject_id={subject_id} need=read auth_mode={auth_mode}
    如果 {rd.via} 等于 public
      返回 {"can_write": 0, "kgm_role": "公共只读"}
    结束
    返回 {"can_write": 0, "kgm_role": "无权"}
  结束

  公开 函数 图谱管理页面 learner current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 sb = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 sid = {sb.subject_id}
    设 idn = 调用 页面身份 learner={learner} current_role={current_role} auth_mode={auth_mode} subject_id={sid}
    设 g = 调用 导出图 subject={sid}
    设 il = 调用 列条目 subject={sid}
    设 nodes = 解析JSON []
    设 kp = 解析JSON []
    设 opts = 解析JSON []
    遍历 p 于 {g.points}
      设 ni = 0
      遍历 i 于 {il.items}
        如果 {i.point_code} 等于 {p.code}
          设 ni = 计算 {ni} + 1
        结束
      结束
      设 pn = 0
      设 nn = 0
      设 desc = {nothing 或}
      遍历 e 于 {g.edges}
        如果 {e.point_code} 等于 {p.code}
          设 pn = 计算 {pn} + 1
          设 pt = {e.pre_code}
          遍历 q 于 {g.points}
            如果 {q.code} 等于 {e.pre_code}
              设 pt = {q.title}
            结束
          结束
          如果 {desc} 为空
            设 desc = {pt}
          否则
            设 desc = {desc}、{pt}
          结束
        结束
        如果 {e.pre_code} 等于 {p.code}
          设 nn = 计算 {nn} + 1
        结束
      结束
      如果 {desc} 为空
        设 desc = （起点）
      结束
      设 st = locked
      设 tn = 计算 {pn} + {nn}
      如果 {tn} 大于 0
        设 st = open
      结束
      设 nd = {"id": "{p.code}", "code": "{p.code}", "label": "{p.title}", "state": "{st}", "badge": {ni}, "desc": "{desc}"}
      设 nodes = 列表加项 {nodes} {nd}
      设 kr = {"kgp_orig": "{p.code}", "kgp_code": "{p.code}", "kgp_title": "{p.title}", "kgp_item_n": {ni}, "kgp_pre_n": {pn}, "kgp_next_n": {nn}}
      设 kp = 列表加项 {kp} {kr}
      设 op = {"value": "{p.code}", "label": "{p.code}（{p.title}）"}
      设 opts = 列表加项 {opts} {op}
    结束
    设 ki = 解析JSON []
    遍历 i 于 {il.items}
      设 ptl = {nothing 或}
      遍历 q 于 {g.points}
        如果 {q.code} 等于 {i.point_code}
          设 ptl = {q.title}
        结束
      结束
      设 ir = {"kgi_orig": "{i.code}", "kgi_code": "{i.code}", "kgi_name": "{i.name}", "kgi_point": "{i.point_code}", "kgi_point_title": "{ptl}", "kgi_after": "{i.after_form 或}", "kgi_prev": "{i.prev_code 或}"}
      设 ki = 列表加项 {ki} {ir}
    结束
    设 gedges = 解析JSON []
    设 ke = 解析JSON []
    遍历 e 于 {g.edges}
      设 ge = {"from": "{e.pre_code}", "to": "{e.point_code}", "kind": ""}
      设 gedges = 列表加项 {gedges} {ge}
      设 t1 = {e.pre_code}
      设 t2 = {e.point_code}
      遍历 q 于 {g.points}
        如果 {q.code} 等于 {e.pre_code}
          设 t1 = {q.title}
        结束
        如果 {q.code} 等于 {e.point_code}
          设 t2 = {q.title}
        结束
      结束
      设 er = {"edge_key": "{e.pre_code}>{e.point_code}", "edge_pre": "{e.pre_code}", "edge_point": "{e.point_code}", "edge_pre_title": "{t1}", "edge_point_title": "{t2}"}
      设 ke = 列表加项 {ke} {er}
    结束
    设 kc = 解析JSON []
    遍历 c 于 {g.contrasts}
      设 na = 0
      设 nb = 0
      设 la = {c.a_code}
      设 lb = {c.b_code}
      遍历 q 于 {g.points}
        如果 {q.code} 等于 {c.a_code}
          设 na = 1
          设 la = {q.code}（{q.title}）
        结束
        如果 {q.code} 等于 {c.b_code}
          设 nb = 1
          设 lb = {q.code}（{q.title}）
        结束
      结束
      遍历 q 于 {il.items}
        如果 {q.code} 等于 {c.a_code} 且 {na} 等于 0
          设 la = {q.code}（{q.name}）
        结束
        如果 {q.code} 等于 {c.b_code} 且 {nb} 等于 0
          设 lb = {q.code}（{q.name}）
        结束
      结束
      如果 {na} 等于 1 且 {nb} 等于 1
        设 ge = {"from": "{c.a_code}", "to": "{c.b_code}", "kind": "对照"}
        设 gedges = 列表加项 {gedges} {ge}
      结束
      设 cr = {"ct_key": "{c.a_code}~{c.b_code}", "ct_a": "{c.a_code}", "ct_b": "{c.b_code}", "ct_a_label": "{la}", "ct_b_label": "{lb}"}
      设 kc = 列表加项 {kc} {cr}
    结束
    设 lg = 调用 subject.取界面语言 username={learner}
    设 head = 共{g.point_count}个知识点、{g.edge_count}条前置边、{il.total}个条目、{g.contrast_count}条对照
    如果 {lg.lang} 等于 ja
      设 hj = {"h": "全 {g.point_count} 知識ポイント、前提辺 {g.edge_count} 本、項目 {il.total} 件、対照 {g.contrast_count} 件"}
      设 head = {hj.h}
    结束
    返回 {"graph": {"nodes": {nodes}, "edges": {gedges}}, "kgm_points": {kp}, "kgm_items": {ki}, "kgm_edges": {ke}, "kgm_contrasts": {kc}, "point_options": {opts}, "kgm_head": "{head}", "kgm_role": "{idn.kgm_role}", "can_write": {idn.can_write}}
  结束

  公开 函数 载入知识点页面 learner kgp_orig? code? current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 cd = {kgp_orig}
    如果 {cd} 为空
      设 cd = {code}
    结束
    如果 {cd} 为空
      返回 {"kgp_orig": "", "kgp_code": "", "kgp_title": "", "kgp_refs": ""}
    结束
    设 sb = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 p = 调用 取知识点 code={cd} subject={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 q = 调用 查引用 code={cd} kind=point subject={sb.subject_id}
    设 nrf = 列表长度 {q.refs}
    设 lg = 调用 subject.取界面语言 username={learner}
    设 txt = 没有被引用，可以删除
    如果 {lg.lang} 等于 ja
      设 txt = 参照されていないので削除できます
    结束
    如果 {nrf} 大于 0
      设 det = {nothing 或}
      遍历 x 于 {q.refs}
        设 sn = {x.source}
        如果 {lg.lang} 等于 ja
          如果 {sn} 等于 下挂条目
            设 sn = 配下の項目
          否则如果 {sn} 等于 前置边
            设 sn = 前提辺
          否则如果 {sn} 等于 对照
            设 sn = 対照
          否则如果 {sn} 等于 课文挂接
            设 sn = テキストの紐づけ
          否则如果 {sn} 等于 题目
            设 sn = 問題
          否则如果 {sn} 等于 单词
            设 sn = 単語
          否则如果 {sn} 等于 作答记录
            设 sn = 解答記録
          否则如果 {sn} 等于 掌握记录
            设 sn = 習得記録
          否则如果 {sn} 等于 得分记录
            设 sn = スコア記録
          否则如果 {sn} 等于 错题
            设 sn = 誤答
          否则如果 {sn} 等于 默写进度
            设 sn = 書き取り進捗
          否则如果 {sn} 等于 后一个条目
            设 sn = 次の項目
          否则如果 {sn} 等于 教师助手对话
            设 sn = 教師アシスタントの会話
          结束
        结束
        如果 {det} 为空
          设 det = {sn}{x.n}
        否则
          设 det = {det}、{sn}{x.n}
        结束
      结束
      如果 {lg.lang} 等于 ja
        设 txt = 参照：{det}
        如果 {q.deletable} 等于 0
          设 txt = {txt}。削除は拒否されます。名前は変更できます
        结束
      否则
        设 txt = 被引用：{det}
        如果 {q.deletable} 等于 0
          设 txt = {txt}。删除会被拒绝，可以改名
        结束
      结束
    结束
    返回 {"kgp_orig": "{cd}", "kgp_code": "{cd}", "kgp_title": "{p.title}", "kgp_refs": "{txt}"}
  结束

  公开 函数 保存知识点页面 learner kgp_title kgp_orig? kgp_code? current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    如果 {kgp_orig} 为空
      设 w = 调用 建知识点 code={kgp_code} title={kgp_title} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    否则
      设 w = 调用 改知识点 code={kgp_orig} title={kgp_title} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    结束
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 删知识点页面 learner kgp_orig current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 w = 调用 删知识点 code={kgp_orig} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 加前置边页面 learner edge_pre edge_point current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 w = 调用 加前置边 pre_code={edge_pre} point_code={edge_point} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 删前置边页面 learner edge_key current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 re = ^(?P<ea>[^>]+)>(?P<eb>.+)$
    设 mm = 匹配 {edge_key} {re}
    如果 {mm.matched} 不等于 是
      报错 400 前置边参数不对
    结束
    设 w = 调用 删前置边 pre_code={mm.named.ea} point_code={mm.named.eb} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 载入条目页面 learner kgi_orig? current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    如果 {kgi_orig} 为空
      返回 {"kgi_orig": "", "kgi_code": "", "kgi_name": "", "kgi_point": "", "kgi_after": "", "kgi_prev": ""}
    结束
    设 sb = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 p = 调用 取条目 code={kgi_orig} subject={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个条目
    结束
    返回 {"kgi_orig": "{p.code}", "kgi_code": "{p.code}", "kgi_name": "{p.name}", "kgi_point": "{p.point_code}", "kgi_after": "{p.after_form 或}", "kgi_prev": "{p.prev_code 或}"}
  结束

  公开 函数 保存条目页面 learner kgi_name kgi_point kgi_orig? kgi_code? kgi_after? kgi_prev? current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    如果 {kgi_orig} 为空
      设 w = 调用 建条目 code={kgi_code} name={kgi_name} point_code={kgi_point} after_form={kgi_after} prev_code={kgi_prev} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    否则
      设 w = 调用 改条目 code={kgi_orig} name={kgi_name} point_code={kgi_point} after_form={kgi_after} prev_code={kgi_prev} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    结束
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 删条目页面 learner kgi_orig current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 w = 调用 删条目 code={kgi_orig} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 加对照页面 learner ct_a ct_b current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 w = 调用 加对照 a_code={ct_a} b_code={ct_b} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 删对照页面 learner ct_key current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 re = ^(?P<ca>[^~]+)~(?P<cb>.+)$
    设 mm = 匹配 {ct_key} {re}
    如果 {mm.matched} 不等于 是
      报错 400 对照参数不对
    结束
    设 w = 调用 删对照 a_code={mm.named.ca} b_code={mm.named.cb} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {r}
  结束

  公开 函数 导入预检页面 learner imp_kind imp_upload_path current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    如果 {imp_kind} 等于 知识点
      设 kd = point
    否则如果 {imp_kind} 等于 条目
      设 kd = item
    否则如果 {imp_kind} 等于 前置边
      设 kd = edge
    否则如果 {imp_kind} 等于 对照
      设 kd = contrast
    否则
      报错 400 导入类型不对
    结束
    设 pv = 调用 导入预检 kind={kd} file_path={imp_upload_path} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 lg = 调用 subject.取界面语言 username={learner}
    设 rows = 解析JSON []
    遍历 x 于 {pv.rows}
      设 rsn = {x.reason 或}
      如果 {lg.lang} 等于 ja
        设 rsn = 替换 {rsn} 已存在 既に存在します
        设 rsn = 替换 {rsn} 内容相同 内容が同じです
      结束
      设 ir = {"imp_line": {x.line}, "imp_code": "{x.code}", "imp_label": "{x.label}", "imp_action": "{x.action}", "imp_reason": "{rsn}"}
      设 rows = 列表加项 {rows} {ir}
    结束
    设 head = 共{pv.total}行：新增{pv.created}、更新{pv.updated}、报错{pv.error_count}
    设 okv = 1
    如果 {pv.error_count} 大于 0
      设 okv = 0
      设 head = {head}。改好文件重新上传，一行都不会写入
    结束
    如果 {lg.lang} 等于 ja
      设 hj = {"h": "全 {pv.total} 行：新規 {pv.created}、更新 {pv.updated}、エラー {pv.error_count}"}
      设 head = {hj.h}
      如果 {pv.error_count} 大于 0
        设 head = {head}。ファイルを修正して再アップロードしてください。1 行も書き込まれません
      结束
    结束
    返回 {"imp_rows": {rows}, "imp_head": "{head}", "imp_ok": {okv}, "form": {"imp_kind": "{imp_kind}", "imp_file": "{imp_upload_path}"}}
  结束

  公开 函数 确认导入页面 learner imp_kind imp_file current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    如果 {imp_kind} 等于 知识点
      设 kd = point
    否则如果 {imp_kind} 等于 条目
      设 kd = item
    否则如果 {imp_kind} 等于 前置边
      设 kd = edge
    否则如果 {imp_kind} 等于 对照
      设 kd = contrast
    否则
      报错 400 导入类型不对
    结束
    设 cf = 调用 确认导入 kind={kd} file_path={imp_file} learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 r = 调用 图谱管理页面 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 lg = 调用 subject.取界面语言 username={learner}
    设 head = 已导入：新增{cf.created}、更新{cf.updated}
    如果 {lg.lang} 等于 ja
      设 head = インポートしました：新規 {cf.created}、更新 {cf.updated}
    结束
    返回 {"graph": {r.graph}, "kgm_points": {r.kgm_points}, "kgm_items": {r.kgm_items}, "kgm_edges": {r.kgm_edges}, "kgm_contrasts": {r.kgm_contrasts}, "point_options": {r.point_options}, "kgm_head": "{r.kgm_head}", "kgm_role": "{r.kgm_role}", "can_write": {r.can_write}, "imp_rows": [], "imp_ok": 0, "imp_head": "{head}"}
  结束

  公开 函数 导出页面 learner exp_kind? current_role? auth_mode? subject?
    如果 {auth_mode} 等于 on 且 {current_role} 不等于 teacher
      报错 403 只有教师可以管理图谱
    结束
    设 sb = 调用 本科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    如果 {exp_kind} 为空 或 {exp_kind} 等于 全部
      设 kd = all
    否则如果 {exp_kind} 等于 知识点
      设 kd = point
    否则如果 {exp_kind} 等于 条目
      设 kd = item
    否则如果 {exp_kind} 等于 前置边
      设 kd = edge
    否则如果 {exp_kind} 等于 对照
      设 kd = contrast
    否则
      报错 400 导出类型不对
    结束
    设 ex = 调用 导出文本 kind={kd} subject={sb.subject_id}
    设 lg = 调用 subject.取界面语言 username={learner}
    设 head = 共{ex.count}行
    如果 {kd} 等于 all
      设 head = {head}。四段要按段拆开分别导入
    结束
    如果 {lg.lang} 等于 ja
      设 hj = {"h": "全 {ex.count} 行"}
      设 head = {hj.h}
      如果 {kd} 等于 all
        设 head = {head}。4 つのセクションは分けて個別にインポートしてください
      结束
    结束
    返回 {"export_text": "{ex.text}", "export_head": "{head}"}
  结束

结束
