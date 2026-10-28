业务 kg
  依赖 subject
  用包 common db text doc

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
        设 pc = 调用 编号前缀检查 subject_id={sb.subject_id} code={cd}
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
        设 pc = 调用 编号前缀检查 subject_id={sb.subject_id} code={cd}
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
        设 pc1 = 调用 编号前缀检查 subject_id={sb.subject_id} code={cda}
        设 pc2 = 调用 编号前缀检查 subject_id={sb.subject_id} code={cdb}
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

  函数 编号前缀检查 subject_id code
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
      报错 400 编号要以「{sc}.」开头
    结束
    返回 {"ok": 1}
  结束

结束
