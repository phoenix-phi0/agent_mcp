业务 textbook_import
  依赖 kg lesson
  用包 common db text doc

  公开 函数 新建导入 series_code series_name code_prefix file_path source? license? file_name? file_size? file_ext? lesson_level? rewrite? overwrite?
    # 返回 {ok, task_id, duplicate, chunk_count}；duplicate 为 1 表示库里已有内容完全相同的任务（不分系列），直接返回那一个，不再新存
    # 报错 400 series_code 不能为空
    # 报错 400 series_name 不能为空
    # 报错 400 code_prefix 不能为空
    # 报错 400 只收 pdf docx md txt 文件
    # 报错 400 文件不能超过 20MB
    # 报错 400 文件没有可读文本
    # series_code 为空，报错 400 series_code 不能为空；series_name 为空，报错 400 series_name 不能为空；code_prefix 为空，报错 400 code_prefix 不能为空
    # file_ext 不为空时，去掉开头的点并转小写后不是 pdf docx md txt 之一，报错 400 只收 pdf docx md txt 文件
    # file_size 不为空时，数值大于 20971520（20MB），报错 400 文件不能超过 20MB
    # 用 doc 包「读文档」读 file_path 取纯文本 text；text 去掉空白后为空，报错 400 文件没有可读文本
    # 查 textbook_import_task 中 raw_text 等于 text 的行（不限系列），有则返回 {"ok": 1, "task_id": 该行 id, "duplicate": 1, "chunk_count": 该任务块数}（同一文件传两次只存一份）
    # 切块：按行拆开；以
    # 在一个事务里：往 textbook_import_task 插入 (series_code, series_name, source, license, code_prefix, file_name, raw_text=text, status=处理中, display_title=series_name 加 "-" 加 file_name（file_name 为空时只取 series_name）, created_at=当前时间)；每块往 textbook_import_chunk 插入 (task_id, seq, title, content, status=待处理, retry_count=0)
    # 事务结束之后：后台执行 scripts/textbook_import_run.zs task_id=<任务id> on_error=scripts/textbook_import_run_fail.zs
    # 返回 {"ok": 1, "task_id": 任务id, "duplicate": 0, "chunk_count": 块数}
    如果 {series_code} 为空
      报错 400 series_code 不能为空
    结束
    如果 {series_name} 为空
      报错 400 series_name 不能为空
    结束
    如果 {code_prefix} 为空
      报错 400 code_prefix 不能为空
    结束
    设 scm = 匹配 {series_code} ^[a-z][a-z0-9_-]*$
    设 sover = 截取 {series_code} 41
    如果 {scm.matched} 不等于 是 或 {sover} 不为空
      报错 400 系列代号只能用小写字母开头，后面是小写字母、数字、下划线、连字符，不超过 40 个字
    结束
    如果 {series_code} 等于 hanabira
      报错 400 hanabira 是主教材，不能用导入覆盖它
    结束
    设 pm = 匹配 {code_prefix} ^[a-z][a-z0-9]*$
    设 pover = 截取 {code_prefix} 21
    如果 {pm.matched} 不等于 是 或 {pover} 不为空
      报错 400 课号前缀只能用小写字母开头，后面是小写字母、数字，不超过 20 个字
    结束
    设 px = 查一值 app.db textbook_import_prefix_taken series_code={series_code} code_prefix={code_prefix}
    如果 {px} 大于 0
      报错 400 课号前缀已经被别的系列用了，换一个
    结束
    如果 {lesson_level} 不为空
      如果 {lesson_level} 不等于 全部 且 {lesson_level} 不等于 N5 且 {lesson_level} 不等于 N4 且 {lesson_level} 不等于 N3 且 {lesson_level} 不等于 N2 且 {lesson_level} 不等于 N1
        报错 400 等级范围只能是全部或 N5 到 N1
      结束
    结束
    如果 {overwrite} 不等于 1
      设 sx = 查一值 app.db textbook_import_series_exists series_code={series_code}
      如果 {sx} 等于 1
        报错 400 系列已经有了，要覆盖就勾上覆盖已有系列，不然换个代号
      结束
    结束
    如果 {file_ext} 不为空
      设 ext0 = 替换 {file_ext} ^\.+
      设 ext = 转大写 {ext0}
      如果 {ext} 不等于 PDF 且 {ext} 不等于 DOCX 且 {ext} 不等于 MD 且 {ext} 不等于 TXT
        报错 400 只收 pdf docx md txt 文件
      结束
    结束
    如果 {file_size} 不为空
      设 sz = 转数字 {file_size}
      如果 {sz} 大于 20971520
        报错 400 文件不能超过 20MB
      结束
    结束
    设 d = 读文档 {file_path}
    设 body = {d.text 或}
    设 tt = 替换 {body} \s
    如果 {tt} 为空
      报错 400 文件没有可读文本
    结束
    设 q.raw_text = {body}
    设 ex = 查一行表 app.db textbook_import_task_by_raw {q}
    如果 {ex} 不为空
      设 ecnt = 查一值 app.db textbook_import_chunk_count_by_task task_id={ex.id}
      返回 {"ok": 1, "task_id": {ex.id}, "duplicate": 1, "chunk_count": {ecnt}}
    结束
    设 hm = 匹配 {body} (^|\n)(#|第[^\n]*课)
    如果 {hm.matched} 等于 是
      设 pieces = 按正则切分 {body} \n(?=#|第[^\n]*课)
    否则
      设 pieces = 找全部 {body} (?s).{1,2000}
    结束
    设 now = 当前时间
    如果 {file_name} 为空
      设 dt = {series_name}
    否则
      设 dt = {series_name}-{file_name}
    结束
    设 tp.series_code = {series_code}
    设 tp.series_name = {series_name}
    设 tp.source = {source 或}
    设 tp.license = {license 或}
    设 tp.code_prefix = {code_prefix}
    设 tp.file_name = {file_name 或}
    设 tp.raw_text = {body}
    设 tp.display_title = {dt}
    设 ll = {lesson_level 或 全部}
    设 rwv = 1
    如果 {rewrite} 不为空 且 {rewrite} 等于 0
      设 rwv = 0
    结束
    设 owv = 0
    如果 {overwrite} 等于 1
      设 owv = 1
    结束
    设 tp.created_at = {now}
    设 tp.lesson_level = {ll}
    设 tp.rewrite = {rwv}
    设 tp.overwrite = {owv}
    设 tid = 0
    设 seq = 0
    事务 app.db
      设 n1 = 写库表 app.db textbook_import_task_insert {tp}
      设 tid = 查一值 app.db textbook_import_task_max_id
      遍历 p 于 {pieces}
        设 pt2 = 替换 {p} \s
        如果 {pt2} 不为空
          设 seq = 计算 {seq} + 1
          设 fl = 替换 {p} (?s)[\r\n].*$
          设 ttl = 截取 {fl} 1 50
          设 cp.task_id = {tid}
          设 cp.seq = {seq}
          设 cp.title = {ttl}
          设 cp.content = {p}
          设 n2 = 写库表 app.db textbook_import_chunk_insert {cp}
        结束
      结束
    结束
    后台执行 scripts/textbook_import_run.zs task_id={tid} on_error=scripts/textbook_import_run_fail.zs
    设 cc = 查一值 app.db textbook_import_chunk_count_by_task task_id={tid}
    返回 {"ok": 1, "task_id": {tid}, "duplicate": 0, "chunk_count": {cc}}
  结束

  公开 函数 处理任务 task_id
    # 返回 {ok, task_id, chunk_total, failed}；failed 是本次处理后失败的块数
    # 报错 404 没有这个任务
    # 按 task_id 查 textbook_import_task，查不到报错 404 没有这个任务
    # 查该任务 status=待处理 的块，按 seq 升序，逐块调用本模块 处理块 chunk_id=该块 id（单块失败只记在块上，不中断）
    # 全部块处理完后，把任务 status 改为 待审阅
    # 统计该任务 status=失败 的块数 failed
    # 返回 {"ok": 1, "task_id": task_id, "chunk_total": 块总数, "failed": failed}
    设 t = 查一行 app.db textbook_import_task_by_id id={task_id}
    如果 {t} 为空
      报错 404 没有这个任务
    结束
    设 rows = 查询 app.db textbook_import_chunks_pending task_id={task_id}
    遍历 c 于 {rows}
      设 r = 调用 处理块 chunk_id={c.id} 出错时 e0
    结束
    设 n1 = 写库 app.db textbook_import_task_set_status id={task_id} status=待审阅
    设 total = 查一值 app.db textbook_import_chunk_count_by_task task_id={task_id}
    设 failed = 查一值 app.db textbook_import_chunk_count_status task_id={task_id} status=失败
    返回 {"ok": 1, "task_id": {task_id}, "chunk_total": {total}, "failed": {failed}}
  结束

  公开 函数 处理块 chunk_id
    # 返回 {ok, chunk_id, status, draft_count}；status 是处理后块的状态（完成 或 失败）
    # 报错 404 没有这个块
    # 按 chunk_id 查 textbook_import_chunk，查不到报错 404 没有这个块；再取所属任务（取课号前缀 code_prefix）
    # 把块 status 改为 处理中
    # 调用 kg.列条目 取全部条目 [{code, name, point_code}]，调用 kg.列知识点 取全部知识点 [{code, title}]，作为模型可映射的候选
    # 问JSON（调模型）：给出块文本和候选条目、知识点，要求抽出本块里的课，返回 {"lessons": [{"title", "level", "summary", "explain", "connection", "examples", "orig_title", "item_codes": [编号], "point_codes": [编号]}]}，编号只能从候选里选，不许新造；调模型出错或返回里没有 lessons 列表，把块 status 改为 失败、fail_reason 写出错原因，返回 {"ok": 1, "chunk_id": chunk_id, "status": "失败", "draft_count": 0}
    # 对每个模型给的编号核对：item_codes 里每个编号调用 kg.取条目 code=编号，point_codes 里每个编号调用 kg.取知识点 code=编号，取不到的编号丢弃（映射只引用已有的，绝不新建），其余保留；level 转大写
    # 在一个事务里：先删除该块已有的草稿课（重试时覆盖）；逐课插入 textbook_import_draft (task_id, chunk_id, code=code_prefix + 该任务草稿课总数加 1 的序号, level, title, summary, explain, connection, examples, examples_edited=0, orig_title, seq=该序号, item_codes 逗号连接, point_codes 逗号连接, status=待审, display_title=code 加 "-" 加 title)；块 status 改为 完成、fail_reason 置空
    # 返回 {"ok": 1, "chunk_id": chunk_id, "status": "完成", "draft_count": 插入的课数}
    设 ch = 查一行 app.db textbook_import_chunk_by_id id={chunk_id}
    如果 {ch} 为空
      报错 404 没有这个块
    结束
    设 t = 查一行 app.db textbook_import_task_by_id id={ch.task_id}
    设 n0 = 写库 app.db textbook_import_chunk_set_processing id={chunk_id}
    设 bp = 调用 块提示词 chunk_id={chunk_id}
    设 res = 调用 抽课 prompt={bp.prompt} 出错时 e
    如果 {e} 不为空
      设 reason = {e.error 或 模型调用出错}
      设 fp.id = {chunk_id}
      设 fp.fail_reason = {reason}
      设 n1 = 写库表 app.db textbook_import_chunk_set_failed {fp}
      返回 {"ok": 1, "chunk_id": {chunk_id}, "status": "失败", "draft_count": 0}
    结束
    设 ls = {res.lessons}
    设 draft_count = 0
    事务 app.db
      设 n2 = 写库 app.db textbook_import_draft_delete_by_chunk chunk_id={chunk_id}
      设 cnt = 查一值 app.db textbook_import_draft_count_by_task task_id={ch.task_id}
      遍历 les 于 {ls}
        设 ics = {nothing 或}
        设 pcs = {nothing 或}
        设 dis = {nothing 或}
        设 dps = {nothing 或}
        设 dil = @,
        设 dpl = @,
        如果 {les.item_codes 或} 不为空
          遍历 c 于 {les.item_codes}
            设 it = 调用 kg.取条目 code={c}
            如果 {it} 不为空
              如果 {ics} 为空
                设 ics = {c}
              否则
                设 ics = {ics},{c}
              结束
            结束
            如果 {it} 为空
              如果 {dil} 不包含 ,{c},
                设 dil = {dil}{c},
                如果 {dis} 为空
                  设 dis = {c}
                否则
                  设 dis = {dis}、{c}
                结束
              结束
            结束
          结束
        结束
        如果 {les.point_codes 或} 不为空
          遍历 c2 于 {les.point_codes}
            设 pt = 调用 kg.取知识点 code={c2}
            如果 {pt} 不为空
              如果 {pcs} 为空
                设 pcs = {c2}
              否则
                设 pcs = {pcs},{c2}
              结束
            结束
            如果 {pt} 为空
              如果 {dpl} 不包含 ,{c2},
                设 dpl = {dpl}{c2},
                如果 {dps} 为空
                  设 dps = {c2}
                否则
                  设 dps = {dps}、{c2}
                结束
              结束
            结束
          结束
        结束
        设 cnt = 计算 {cnt} + 1
        设 code = {t.code_prefix}{cnt}
        设 lv0 = {les.level 或}
        设 lv = 转大写 {lv0}
        设 ttl = {les.title 或}
        设 dtitle = {code}-{ttl}
        设 cf0 = {les.confidence 或}
        设 cfv = {nothing 或}
        设 cf1 = 替换 {cf0} \s
        设 cfm = 匹配 {cf1} ^-?\d+(\.\d+)?$
        如果 {cfm.matched} 等于 是
          设 cn = 转数字 {cf1}
          如果 {cn} 大于 0 且 {cn} 不大于 1
            设 cfv = 计算 四舍五入({cn} * 100)
          否则如果 {cn} 大于 1
            设 cfv = 计算 最小(100, 四舍五入({cn}))
          结束
        结束
        设 rs0 = {les.reason 或}
        设 rs1 = 替换 {rs0} ^\s+|\s+$
        设 kw1 = 条目
        设 kw2 = 知识点
        设 dtxt = {nothing 或}
        如果 {dis} 不为空
          设 dtxt = {kw1} {dis}
        结束
        如果 {dps} 不为空
          如果 {dtxt} 为空
            设 dtxt = {kw2} {dps}
          否则
            设 dtxt = {dtxt}；{kw2} {dps}
          结束
        结束
        设 dp = 解析JSON 空对象
        设 dp.task_id = {ch.task_id}
        设 dp.chunk_id = {chunk_id}
        设 dp.code = {code}
        设 dp.level = {lv}
        设 dp.title = {ttl}
        设 dp.summary = {les.summary 或}
        设 dp.explain = {les.explain 或}
        设 dp.connection = {les.connection 或}
        设 dp.examples = {les.examples 或}
        设 dp.orig_title = {les.orig_title 或}
        设 dp.seq = {cnt}
        设 dp.item_codes = {ics 或}
        设 dp.point_codes = {pcs 或}
        设 dp.display_title = {dtitle}
        设 dp.confidence = {cfv 或}
        设 dp.dropped_codes = {dtxt 或}
        设 dp.reason = {rs1 或}
        设 n3 = 写库表 app.db textbook_import_draft_insert {dp}
        设 draft_count = 计算 {draft_count} + 1
      结束
      设 n4 = 写库 app.db textbook_import_chunk_set_done id={chunk_id}
    结束
    返回 {"ok": 1, "chunk_id": {chunk_id}, "status": "完成", "draft_count": {draft_count}}
  结束

  公开 函数 标记任务失败 task_id error
    # 返回 {ok}
    # 报错 404 没有这个任务
    # 按 task_id 查 textbook_import_task，查不到报错 404 没有这个任务
    # 把任务 status 改为 失败，fail_reason 写 error
    # 返回 {"ok": 1}
    设 t = 查一行 app.db textbook_import_task_by_id id={task_id}
    如果 {t} 为空
      报错 404 没有这个任务
    结束
    设 tf.id = {task_id}
    设 tf.reason = {error}
    设 n1 = 写库表 app.db textbook_import_task_fail {tf}
    返回 {"ok": 1}
  结束

  公开 函数 重试块 chunk_id
    # 返回 {ok, chunk_id, task_id, status}；status 是提交后块的状态（待处理，后台处理，前端通过 取任务 轮询进度）
    # 报错 404 没有这个块
    # 报错 400 只有失败的块可以重试
    # 按 chunk_id 查 textbook_import_chunk，查不到报错 404 没有这个块
    # 块 status 不等于 失败，报错 400 只有失败的块可以重试
    # 在一个事务里：块 status 改为 待处理、fail_reason 置空、retry_count 加 1；所属任务 status 改为 处理中
    # 事务结束之后：后台执行 scripts/textbook_import_run.zs task_id=<所属任务id> on_error=scripts/textbook_import_run_fail.zs（脚本只处理该任务里待处理的块，处理完任务回到待审阅）
    # 返回 {"ok": 1, "chunk_id": chunk_id, "task_id": 所属任务id, "status": "待处理"}
    设 ch = 查一行 app.db textbook_import_chunk_by_id id={chunk_id}
    如果 {ch} 为空
      报错 404 没有这个块
    结束
    如果 {ch.status} 不等于 失败
      报错 400 只有失败的块可以重试
    结束
    事务 app.db
      设 n1 = 写库 app.db textbook_import_chunk_retry id={chunk_id}
      设 n2 = 写库 app.db textbook_import_task_set_status id={ch.task_id} status=处理中
    结束
    后台执行 scripts/textbook_import_run.zs task_id={ch.task_id} on_error=scripts/textbook_import_run_fail.zs
    返回 {"ok": 1, "chunk_id": {chunk_id}, "task_id": {ch.task_id}, "status": "待处理"}
  结束

  公开 函数 列任务
    # 返回 {total, tasks}，tasks 是 [{task_id, series_code, series_name, display_title, status, chunk_total, pending_count, draft_total, created_at}]，按 id 倒序
    # 查 textbook_import_task 全部行，按 id 倒序
    # 每行统计其块数 chunk_total、status 为 待处理 或 处理中 的块数 pending_count、草稿课数 draft_total
    # 返回 {"total": 行数, "tasks": 列表}
    设 rows = 查询 app.db textbook_import_tasks_list
    设 n = 列表长度 {rows}
    返回 {"total": {n}, "tasks": {rows}}
  结束

  公开 函数 取任务 task_id
    # 返回 {task_id, series_code, series_name, source, license, code_prefix, file_name, display_title, status, fail_reason, report, created_at, chunk_total, chunk_pending, chunk_done, chunk_failed, chunks, drafts}；chunks 是 [{id, seq, title, status, fail_reason, retry_count}] 按 seq 升序；drafts 是 [{id, code, display_title, title, level, seq, status, item_count, point_count}] 按 seq 升序、id 升序
    # 报错 404 没有这个任务
    # 按 task_id 查 textbook_import_task，查不到报错 404 没有这个任务
    # 查该任务的块和草稿课；chunk_pending 是 status 为 待处理 或 处理中 的块数，chunk_done 是 status=完成 的块数，chunk_failed 是 status=失败 的块数；item_count、point_count 是对应编号列表里的个数
    # 返回上述结构（不返回 raw_text）
    设 t = 查一行 app.db textbook_import_task_by_id id={task_id}
    如果 {t} 为空
      报错 404 没有这个任务
    结束
    设 chunks = 查询 app.db textbook_import_chunks_by_task task_id={task_id}
    设 drafts = 查询 app.db textbook_import_drafts_by_task task_id={task_id}
    设 ct = 列表长度 {chunks}
    设 cp = 查一值 app.db textbook_import_chunk_pending_count task_id={task_id}
    设 cd = 查一值 app.db textbook_import_chunk_count_status task_id={task_id} status=完成
    设 cf = 查一值 app.db textbook_import_chunk_count_status task_id={task_id} status=失败
    设 out.task_id = {t.id}
    设 out.series_code = {t.series_code}
    设 out.series_name = {t.series_name}
    设 out.source = {t.source}
    设 out.license = {t.license}
    设 out.code_prefix = {t.code_prefix}
    设 out.file_name = {t.file_name}
    设 out.display_title = {t.display_title}
    设 out.status = {t.status}
    设 out.fail_reason = {t.fail_reason}
    设 out.report = {t.report}
    设 out.created_at = {t.created_at}
    设 out.chunk_total = {ct}
    设 out.chunk_pending = {cp}
    设 out.chunk_done = {cd}
    设 out.chunk_failed = {cf}
    设 out.chunks = {chunks}
    设 out.drafts = {drafts}
    返回 {out}
  结束

  公开 函数 取草稿课 draft_id
    # 返回 {id, task_id, chunk_id, code, display_title, level, title, summary, explain, connection, examples, examples_edited, orig_title, seq, item_codes, point_codes, status}
    # 报错 404 没有这个草稿课
    # 按 draft_id 查 textbook_import_draft，查不到报错 404 没有这个草稿课
    # 返回该行各字段
    设 d = 查一行 app.db textbook_import_draft_by_id id={draft_id}
    如果 {d} 为空
      报错 404 没有这个草稿课
    结束
    设 out.id = {d.id}
    设 out.task_id = {d.task_id}
    设 out.chunk_id = {d.chunk_id}
    设 out.code = {d.code}
    设 out.display_title = {d.display_title}
    设 out.level = {d.level}
    设 out.title = {d.title}
    设 out.summary = {d.summary}
    设 out.explain = {d.explain}
    设 out.connection = {d.connection}
    设 out.examples = {d.examples}
    设 out.examples_edited = {d.examples_edited}
    设 out.orig_title = {d.orig_title}
    设 out.seq = {d.seq}
    设 out.item_codes = {d.item_codes}
    设 out.point_codes = {d.point_codes}
    设 out.status = {d.status}
    设 out.confidence = {d.confidence 或}
    设 out.dropped_codes = {d.dropped_codes 或}
    设 out.reason = {d.reason 或}
    返回 {out}
  结束

  公开 函数 修改草稿课 draft_id title level summary explain connection examples seq
    # 返回 {ok, draft_id}
    # 报错 404 没有这个草稿课
    # 报错 400 已导入的课不能再改
    # 报错 400 草稿课字段有错
    # 按 draft_id 查 textbook_import_draft，查不到报错 404 没有这个草稿课
    # 所属任务 status 等于 已导入，报错 400 已导入的课不能再改（其它状态都允许修改）
    # title 为空，或 level 不是 N5 N4 N3 N2 N1 之一，或 seq 不是整数，报错 400 草稿课字段有错
    # examples 与原 examples 不同时，examples_edited 置 1（已是 1 的保持 1）
    # 更新该行 title、level、summary、explain、connection、examples、seq，display_title 重算为 code 加 "-" 加 title（课号 code 和 status 不改）
    # 返回 {"ok": 1, "draft_id": draft_id}
    设 d = 查一行 app.db textbook_import_draft_by_id id={draft_id}
    如果 {d} 为空
      报错 404 没有这个草稿课
    结束
    设 t = 查一行 app.db textbook_import_task_by_id id={d.task_id}
    如果 {t.status} 等于 已导入
      报错 400 已导入的课不能再改
    结束
    设 sm = 匹配 {seq} ^-?\d+$
    设 bad = 0
    如果 {title} 为空
      设 bad = 1
    结束
    如果 {level} 不等于 N5 且 {level} 不等于 N4 且 {level} 不等于 N3 且 {level} 不等于 N2 且 {level} 不等于 N1
      设 bad = 1
    结束
    如果 {sm.matched} 不等于 是
      设 bad = 1
    结束
    如果 {bad} 等于 1
      报错 400 草稿课字段有错
    结束
    设 ee = {d.examples_edited}
    设 same = 相等 {examples} {d.examples}
    如果 {same} 等于 否
      设 ee = 1
    结束
    设 dtitle = {d.code}-{title}
    设 up.id = {draft_id}
    设 up.title = {title}
    设 up.level = {level}
    设 up.summary = {summary 或}
    设 up.explain = {explain 或}
    设 up.connection = {connection 或}
    设 up.examples = {examples 或}
    设 up.examples_edited = {ee}
    设 up.seq = {seq}
    设 up.display_title = {dtitle}
    设 n1 = 写库表 app.db textbook_import_draft_update {up}
    返回 {"ok": 1, "draft_id": {draft_id}}
  结束

  公开 函数 改映射 draft_id kind action code
    # 返回 {ok, item_codes, point_codes}
    # 报错 404 没有这个草稿课
    # 报错 400 已导入的课不能再改
    # 报错 400 kind 只能是 item 或 point
    # 报错 400 action 只能是 add 或 remove
    # 报错 404 没有这个条目
    # 报错 404 没有这个知识点
    # 按 draft_id 查 textbook_import_draft，查不到报错 404 没有这个草稿课
    # 所属任务 status 等于 已导入，报错 400 已导入的课不能再改
    # kind 不是 item 也不是 point，报错 400 kind 只能是 item 或 point；action 不是 add 也不是 remove，报错 400 action 只能是 add 或 remove
    # action 为 add：kind 为 item 时调用 kg.取条目 code=code，取不到报错 404 没有这个条目；kind 为 point 时调用 kg.取知识点 code=code，取不到报错 404 没有这个知识点（手动加的先查库，绝不新建）；编号不在对应列表时追加到末尾，已在则不重复
    # action 为 remove：从对应列表里去掉 code，不在列表里也不报错
    # 更新该行 item_codes 或 point_codes（英文逗号连接）
    # 返回 {"ok": 1, "item_codes": 新 item_codes, "point_codes": 新 point_codes}
    设 d = 查一行 app.db textbook_import_draft_by_id id={draft_id}
    如果 {d} 为空
      报错 404 没有这个草稿课
    结束
    设 t = 查一行 app.db textbook_import_task_by_id id={d.task_id}
    如果 {t.status} 等于 已导入
      报错 400 已导入的课不能再改
    结束
    如果 {kind} 不等于 item 且 {kind} 不等于 point
      报错 400 kind 只能是 item 或 point
    结束
    如果 {action} 不等于 add 且 {action} 不等于 remove
      报错 400 action 只能是 add 或 remove
    结束
    设 ics = {d.item_codes 或}
    设 pcs = {d.point_codes 或}
    如果 {kind} 等于 item
      设 cur = {ics 或}
    否则
      设 cur = {pcs 或}
    结束
    设 nw = {cur 或}
    如果 {action} 等于 add
      如果 {kind} 等于 item
        设 it = 调用 kg.取条目 code={code}
        如果 {it} 为空
          报错 404 没有这个条目
        结束
      否则
        设 pt = 调用 kg.取知识点 code={code}
        如果 {pt} 为空
          报错 404 没有这个知识点
        结束
      结束
      如果 {cur} 为空
        设 nw = {code}
      否则
        设 wrapped = ,{cur},
        如果 {wrapped} 不包含 ,{code},
          设 nw = {cur},{code}
        结束
      结束
    否则
      设 nw = {nothing 或}
      设 parts = 按正则切分 {cur} ,
      遍历 p 于 {parts}
        如果 {p} 不为空 且 {p} 不等于 {code}
          如果 {nw} 为空
            设 nw = {p}
          否则
            设 nw = {nw},{p}
          结束
        结束
      结束
    结束
    如果 {kind} 等于 item
      设 n1 = 写库 app.db textbook_import_draft_set_item_codes id={draft_id} codes={nw}
      设 ics = {nw 或}
    否则
      设 n2 = 写库 app.db textbook_import_draft_set_point_codes id={draft_id} codes={nw}
      设 pcs = {nw 或}
    结束
    返回 {"ok": 1, "item_codes": "{ics}", "point_codes": "{pcs}"}
  结束

  公开 函数 审核草稿课 draft_id decision
    # 返回 {ok, draft_id, status}
    # 报错 404 没有这个草稿课
    # 报错 400 已导入的课不能再改
    # 报错 400 decision 只能是 approve 或 reject
    # 报错 400 草稿课字段有错
    # 按 draft_id 查 textbook_import_draft，查不到报错 404 没有这个草稿课
    # 所属任务 status 等于 已导入，报错 400 已导入的课不能再改
    # decision 不是 approve 也不是 reject，报错 400 decision 只能是 approve 或 reject
    # decision 为 approve：title 为空或 level 不是 N5 N4 N3 N2 N1 之一，报错 400 草稿课字段有错；否则 status 改为 通过
    # decision 为 reject：status 改为 驳回
    # 返回 {"ok": 1, "draft_id": draft_id, "status": 新 status}
    设 d = 查一行 app.db textbook_import_draft_by_id id={draft_id}
    如果 {d} 为空
      报错 404 没有这个草稿课
    结束
    设 t = 查一行 app.db textbook_import_task_by_id id={d.task_id}
    如果 {t.status} 等于 已导入
      报错 400 已导入的课不能再改
    结束
    如果 {decision} 不等于 approve 且 {decision} 不等于 reject
      报错 400 decision 只能是 approve 或 reject
    结束
    设 st = 驳回
    如果 {decision} 等于 approve
      设 bad = 0
      如果 {d.title} 为空
        设 bad = 1
      结束
      如果 {d.level} 不等于 N5 且 {d.level} 不等于 N4 且 {d.level} 不等于 N3 且 {d.level} 不等于 N2 且 {d.level} 不等于 N1
        设 bad = 1
      结束
      如果 {bad} 等于 1
        报错 400 草稿课字段有错
      结束
      设 st = 通过
    结束
    设 n1 = 写库 app.db textbook_import_draft_set_status id={draft_id} status={st}
    返回 {"ok": 1, "draft_id": {draft_id}, "status": "{st}"}
  结束

  公开 函数 一键通过 task_id
    # 返回 {ok, approved, skipped}；approved 是本次改为通过的课数，skipped 是仍待审但没通过的课数
    # 报错 404 没有这个任务
    # 报错 400 已导入的课不能再改
    # 按 task_id 查 textbook_import_task，查不到报错 404 没有这个任务；status 等于 已导入，报错 400 已导入的课不能再改
    # 把该任务 status=待审 且（item_codes 或 point_codes 不为空）且 title 不为空且 level 是 N5 N4 N3 N2 N1 之一的草稿课 status 改为 通过，数出 approved
    # skipped = 该任务仍为 待审 的草稿课数
    # 返回 {"ok": 1, "approved": approved, "skipped": skipped}
    设 t = 查一行 app.db textbook_import_task_by_id id={task_id}
    如果 {t} 为空
      报错 404 没有这个任务
    结束
    如果 {t.status} 等于 已导入
      报错 400 已导入的课不能再改
    结束
    设 approved = 写库 app.db textbook_import_draft_approve_mapped task_id={task_id}
    设 skipped = 查一值 app.db textbook_import_draft_count_status task_id={task_id} status=待审
    返回 {"ok": 1, "approved": {approved}, "skipped": {skipped}}
  结束

  公开 函数 确认导入 task_id
    # 返回 {ok, series_code, total, imported, rejected_count, rejected, item_links, point_links, file_rows}；total、imported、item_links、point_links、file_rows、rejected 取自 lesson.写入系列课文并重灌 的返回，rejected 是 [{code, reason}]，rejected_count 是 rejected 的个数
    # 报错 404 没有这个任务
    # 报错 400 已导入的课不能再改
    # 报错 400 没有通过的课
    # 按 task_id 查 textbook_import_task，查不到报错 404 没有这个任务；status 等于 已导入，报错 400 已导入的课不能再改
    # 取该任务 status=通过 的草稿课，按 seq 升序、id 升序；没有则报错 400 没有通过的课
    # 组成 rows_json（JSON 数组），每课 {code, level, title, summary, explain, connection, examples, examples_edited, orig_title, seq, item_codes: 编号数组, point_codes: 编号数组}（编号列表按英文逗号拆开，空则空数组）
    # 调用 lesson.写入系列课文并重灌 series_code=任务 series_code rows_json=rows_json series_name=任务 series_name source=任务 source license=任务 license 得 r（写内容文件、按系列清空重灌、拒收映射对不上的课都由 lesson 完成；lesson 报的错原样向上抛，任务状态不变）
    # 把任务 status 改为 已导入，report 写 r 的 JSON 文本
    # 返回 {"ok": 1, "series_code": 任务 series_code, "total": r.total, "imported": r.imported, "rejected_count": r.rejected 的个数, "rejected": r.rejected, "item_links": r.item_links, "point_links": r.point_links, "file_rows": r.file_rows}
    设 t = 查一行 app.db textbook_import_task_by_id id={task_id}
    如果 {t} 为空
      报错 404 没有这个任务
    结束
    如果 {t.status} 等于 已导入
      报错 400 已导入的课不能再改
    结束
    如果 {t.series_code} 等于 hanabira
      报错 400 hanabira 是主教材，不能用导入覆盖它
    结束
    设 ow0 = {t.overwrite 或 0}
    如果 {ow0} 不等于 1
      设 sx = 查一值 app.db textbook_import_series_exists series_code={t.series_code}
      如果 {sx} 等于 1
        报错 400 系列已经有了，这个任务没勾覆盖已有系列
      结束
    结束
    设 ds = 查询 app.db textbook_import_drafts_approved task_id={task_id}
    设 dn = 列表长度 {ds}
    如果 {dn} 等于 0
      报错 400 没有通过的课
    结束
    设 rows = 解析JSON []
    遍历 d 于 {ds}
      设 ia = 解析JSON []
      如果 {d.item_codes} 不为空
        设 ia = 按正则切分 {d.item_codes} ,
      结束
      设 pa = 解析JSON []
      如果 {d.point_codes} 不为空
        设 pa = 按正则切分 {d.point_codes} ,
      结束
      设 xr = 调用 例句转教材格式 examples={d.examples 或}
      设 rw2 = 解析JSON 空对象
      设 rw2.code = {d.code}
      设 rw2.level = {d.level}
      设 rw2.title = {d.title}
      设 rw2.summary = {d.summary 或}
      设 rw2.explain = {d.explain 或}
      设 rw2.connection = {d.connection 或}
      设 rw2.examples = {xr.text 或}
      设 rw2.examples_edited = {d.examples_edited 或 0}
      设 rw2.orig_title = {d.orig_title 或}
      设 rw2.seq = {d.seq 或 0}
      设 rw2.item_codes = {ia}
      设 rw2.point_codes = {pa}
      设 rows = 列表加项 {rows} {rw2}
    结束
    设 r = 调用 lesson.写入系列课文并重灌 series_code={t.series_code} rows_json={rows} series_name={t.series_name} source={t.source} license={t.license}
    设 rc = 列表长度 {r.rejected}
    设 rep = {"ok": {r.ok}, "series_code": "{r.series_code}", "total": {r.total}, "imported": {r.imported}, "item_links": {r.item_links}, "point_links": {r.point_links}, "file_rows": {r.file_rows}, "rejected": {r.rejected}}
    设 ip.id = {task_id}
    设 ip.report = {rep}
    设 n1 = 写库表 app.db textbook_import_task_set_imported {ip}
    返回 {"ok": 1, "series_code": "{t.series_code}", "total": {r.total}, "imported": {r.imported}, "rejected_count": {rc}, "rejected": {r.rejected}, "item_links": {r.item_links}, "point_links": {r.point_links}, "file_rows": {r.file_rows}}
  结束

  公开 函数 删除任务 task_id
    # 返回 {ok, task_id}
    # 报错 404 没有这个任务
    # 按 task_id 查 textbook_import_task，查不到报错 404 没有这个任务
    # 在一个事务里：删除该任务的 textbook_import_draft、textbook_import_chunk，再删除任务行（只删草稿，不调用 lesson，已导入的课不动）
    # 返回 {"ok": 1, "task_id": task_id}
    设 t = 查一行 app.db textbook_import_task_by_id id={task_id}
    如果 {t} 为空
      报错 404 没有这个任务
    结束
    事务 app.db
      设 n1 = 写库 app.db textbook_import_draft_delete_by_task task_id={task_id}
      设 n2 = 写库 app.db textbook_import_chunk_delete_by_task task_id={task_id}
      设 n3 = 写库 app.db textbook_import_task_delete id={task_id}
    结束
    返回 {"ok": 1, "task_id": {task_id}}
  结束

  公开 函数 列已导入系列 series_code?
    # 返回 {total, series, lesson_total, lessons}；series 是 [{code, name, sort_order, lesson_count}]；series_code 不为空时 lessons 是该系列的课文 [{code, level, title, summary, series_code, seq}]，lesson_total 是其个数；为空时 lessons 为空列表、lesson_total 为 0
    # 调用 lesson.列系列 得系列列表（只含未撤下的系列）
    # 每个系列调用 lesson.列课文 series_code=该系列编号，lesson_count 取返回的 total
    # series_code 不为空时，调用 lesson.列课文 series_code=series_code，取其 lessons 和 total
    # 返回 {"total": 系列数, "series": 列表, "lesson_total": 课数, "lessons": 课文列表}
    设 sl = 调用 lesson.列系列
    设 series = 解析JSON []
    遍历 s 于 {sl.series}
      设 lc = 调用 lesson.列课文 series_code={s.code}
      设 s.lesson_count = {lc.total}
      设 series = 列表加项 {series} {s}
    结束
    设 n = 列表长度 {series}
    设 lessons = 解析JSON []
    设 lt = 0
    如果 {series_code} 不为空
      设 ll = 调用 lesson.列课文 series_code={series_code}
      设 lessons = {ll.lessons}
      设 lt = {ll.total}
    结束
    返回 {"total": {n}, "series": {series}, "lesson_total": {lt}, "lessons": {lessons}}
  结束

  公开 函数 撤下已导入系列 series_code
    # 返回 {ok, series_code, removed_lessons, moved}，removed_lessons、moved 取自 lesson.撤下系列 的返回
    # 报错 404 没有这个系列
    # 调用 lesson.撤下系列 series_code=series_code 得 r（挪走内容文件、清课文及挂接、排序改 -1 都由 lesson 完成；没有这个系列时 lesson 报 404 原样向上抛）
    # 把 textbook_import_task 中 series_code 相等且 status=已导入 的行 status 改为 已撤下
    # 返回 {"ok": 1, "series_code": series_code, "removed_lessons": r.removed_lessons, "moved": r.moved}
    如果 {series_code} 等于 hanabira
      报错 400 hanabira 是主教材，不能撤下
    结束
    设 r = 调用 lesson.撤下系列 series_code={series_code}
    设 n1 = 写库 app.db textbook_import_task_withdraw series_code={series_code}
    返回 {"ok": 1, "series_code": "{series_code}", "removed_lessons": {r.removed_lessons}, "moved": {r.moved}}
  结束

  公开 函数 块提示词 chunk_id
    设 ch = 查一行 app.db textbook_import_chunk_by_id id={chunk_id}
    如果 {ch} 为空
      报错 404 没有这个块
    结束
    设 t = 查一行 app.db textbook_import_task_by_id id={ch.task_id}
    设 rw = 1
    如果 {t.rewrite} 等于 0
      设 rw = 0
    结束
    设 lv = {t.lesson_level 或 全部}
    设 il = 调用 kg.列条目
    设 pl = 调用 kg.列知识点
    设 cand = {il.items}
    如果 {lv} 等于 N5 或 {lv} 等于 N4 或 {lv} 等于 N3 或 {lv} 等于 N2 或 {lv} 等于 N1
      设 cand = 解析JSON []
      设 lk1 = @,
      设 rows1 = 查询 app.db textbook_import_item_linked
      遍历 r1 于 {rows1}
        设 lk1 = {lk1}{r1.item_code},
      结束
      设 lk2 = @,
      设 rows2 = 查询 app.db textbook_import_item_linked_level level={lv}
      遍历 r2 于 {rows2}
        设 lk2 = {lk2}{r2.item_code},
      结束
      遍历 ci 于 {il.items}
        设 key = ,{ci.code},
        如果 {lk1} 不包含 {key} 或 {lk2} 包含 {key}
          设 cand = 列表加项 {cand} {ci}
        结束
      结束
    结束
    设 ic = 列表长度 {cand}
    设 pc = 列表长度 {pl.points}
    设 base = 你是日语教材整理助手。下面是一块教材文本，请抽出其中的每一课，返回lessons列表，列表每项含title、level（N5/N4/N3/N2/N1）、summary（一句话）、explain（讲解）、connection（接续）、examples（例句，是数组，每项是有jp和zh两个键的对象）、orig_title（原标题）、item_codes（编号数组）、point_codes（编号数组）、confidence（你对映射的把握，0到1的小数）、reason（一句话说为什么这样映射）。item_codes和point_codes只能从候选里选编号，不许新造，没有合适的就给空数组。
    如果 {rw} 等于 1
      设 style = 风格要求：这是商业教材，原文不能入库：title只写语法点的名称，summary、explain、connection、examples一律用自己的话重新写，不要照抄原文的句子，例句自己造，每课2到4句，日语加中文翻译；只有语法点名称、课序、等级这类事实可以照原文。
    否则
      设 style = 风格要求：讲解、例句可以参照原文来写，例句可以沿用原文的。
    结束
    设 prompt = {base}候选条目：{cand}。候选知识点：{pl.points}。{style}教材文本：{ch.content}
    设 out.chunk_id = {chunk_id}
    设 out.rewrite = {rw}
    设 out.lesson_level = {lv}
    设 out.item_count = {ic}
    设 out.point_count = {pc}
    设 out.prompt = {prompt}
    返回 {out}
  结束

  公开 函数 创建导入任务 series_code series_name document_path code_prefix? source? license? lesson_level? rewrite? overwrite? file_name? file_size? file_ext?
    设 cp = {code_prefix 或}
    如果 {cp} 为空 且 {series_code} 不为空
      设 cp1 = 替换 {series_code} [-_]
      设 cp = {cp1}
    结束
    设 ll = {lesson_level 或 全部}
    设 rw = 1
    设 rwu = {rewrite 或}
    如果 {rwu} 不为空
      设 rwu = 转大写 {rwu}
      如果 {rwu} 等于 FALSE 或 {rwu} 等于 0 或 {rwu} 等于 否 或 {rwu} 等于 OFF
        设 rw = 0
      结束
    结束
    设 ow = 0
    设 owu = {overwrite 或}
    如果 {owu} 不为空
      设 owu = 转大写 {owu}
      如果 {owu} 等于 TRUE 或 {owu} 等于 1 或 {owu} 等于 是 或 {owu} 等于 ON
        设 ow = 1
      结束
    结束
    设 r = 调用 新建导入 series_code={series_code} series_name={series_name} code_prefix={cp} file_path={document_path} source={source 或} license={license 或} file_name={file_name 或} file_size={file_size 或} file_ext={file_ext 或} lesson_level={ll} rewrite={rw} overwrite={ow}
    返回 {r}
  结束

  公开 函数 导入首页
    设 tl = 调用 列任务
    设 jobs = 解析JSON []
    遍历 tk 于 {tl.tasks}
      设 tr0 = 查一行 app.db textbook_import_task_by_id id={tk.task_id}
      设 js = 调用 任务进度文本 task_id={tk.task_id}
      设 row = 解析JSON 空对象
      设 row.job = {tk.task_id}
      设 row.series = {tk.series_code}
      设 row.label = {tk.series_name}
      设 row.file_name = {tr0.file_name}
      设 row.created = {tk.created_at}
      设 row.job_state = {js.text}
      设 row.href = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?job={tk.task_id}
      设 jobs = 列表加项 {jobs} {row}
    结束
    设 sl = 调用 列已导入系列
    设 ser = 解析JSON []
    遍历 sv 于 {sl.series}
      如果 {sv.code} 不等于 hanabira
        设 srow = 解析JSON 空对象
        设 srow.code = {sv.code}
        设 srow.label = {sv.name}
        设 srow.lesson_n = 转数字 {sv.lesson_count}
        设 srow.series_state = 在用
        设 srow.href = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?manage={sv.code}
        设 ser = 列表加项 {ser} {srow}
      结束
    结束
    返回 {"import_jobs": {jobs}, "import_series": {ser}, "form": {"lesson_level": "全部", "rewrite": "true", "overwrite": "false"}}
  结束

  函数 例句转教材格式 examples
    设 e0 = {examples 或}
    设 e1 = 替换 {e0} \s
    设 res = {zz 或}
    如果 {e1} 不为空
      设 jq.examples = {e0}
      设 isarr = 查一值表 app.db textbook_import_json_is_array {jq}
      如果 {isarr} 等于 1
        设 res = 查一值表 app.db textbook_import_examples_convert {jq}
      否则
        设 res = {e0}
      结束
    结束
    设 o.text = {res 或}
    返回 {o}
  结束

  函数 抽课 prompt
    问JSON r = {prompt} 格式 lessons:列表
    返回 {r}
  结束

  公开 函数 任务视图 task_id
    设 tr = 查一行 app.db textbook_import_task_by_id id={task_id}
    如果 {tr} 为空
      返回 {"job": {"id": {task_id}, "missing": "没有这个导入任务（{task_id}），可能已经删了。", "running": 0, "back": "#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5"}}
    结束
    设 t = 调用 取任务 task_id={task_id}
    设 running = 转数字 0
    如果 {t.status} 等于 处理中
      设 running = 转数字 1
    结束
    设 nd = 列表长度 {t.drafts}
    设 np = 转数字 0
    设 nr = 0
    遍历 dd 于 {t.drafts}
      如果 {dd.status} 等于 通过
        设 np = 计算 {np} + 1
      结束
      如果 {dd.status} 等于 驳回
        设 nr = 计算 {nr} + 1
      结束
    结束
    设 cf = 查一值 app.db textbook_import_chunk_count_status task_id={task_id} status=失败
    设 cdn = 查一值 app.db textbook_import_chunk_count_status task_id={task_id} status=完成
    设 fin = 计算 {cdn} + {cf}
    如果 {tr.rewrite} 不等于 0
      设 hd2 = 讲解和例句由模型改写
    否则
      设 hd2 = 保留原文讲解（没勾改写）
    结束
    设 head = 系列{t.series_code}（{t.series_name}）· 课号前缀 {t.code_prefix} · 文件 {t.file_name} · {hd2}
    设 extra = {zz 或}
    如果 {t.status} 等于 处理中
      如果 {cf} 大于 0
        设 extra = ，出错{cf}块
      结束
      设 progress = 正在解析：{fin}/{t.chunk_total}块做完{extra}。这页会自己刷新，可以先去别的页面。
    否则如果 {t.status} 等于 失败
      设 progress = 解析失败：{t.fail_reason}
    否则
      如果 {cf} 大于 0
        设 extra = ，出错{cf}块（在块表里重试）
      结束
      设 done = {zz 或}
      如果 {t.status} 等于 已导入
        设 done = 已导入。
      结束
      设 progress = 解析完了：{t.chunk_total}块，抽出{nd}课{extra}。通过{np}课、驳回{nr}课。{done}
    结束
    设 report_note = {zz 或}
    设 textbook = {zz 或}
    设 rej = 解析JSON []
    如果 {tr.report} 不为空
      设 rp = 解析JSON {tr.report}
      设 rej = {rp.rejected}
      设 rc = 列表长度 {rej}
      设 report_note = 导入报告：导入{rp.imported}课，映射到条目{rp.item_links}条、知识点{rp.point_links}条，拒收{rc}行。
      设 textbook = #%E6%95%99%E6%9D%90
    结束
    设 job = 解析JSON 空对象
    设 job.id = {t.task_id}
    设 job.series = {t.series_code}
    设 job.label = {t.series_name}
    设 job.running = 转数字 {running}
    设 job.passed = 转数字 {np}
    设 job.head = {head}
    设 job.progress = {progress}
    设 job.report_note = {report_note}
    设 job.textbook = {textbook}
    设 job.missing = {zz 或}
    设 job.back = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5
    设 crows = 解析JSON []
    遍历 ck 于 {t.chunks}
      设 cs = {ck.status}
      如果 {ck.status} 等于 待处理
        设 cs = 待解析
      结束
      如果 {ck.status} 等于 处理中
        设 cs = 解析中
      结束
      如果 {ck.status} 等于 失败
        设 cs = 出错
      结束
      设 rc0 = {ck.retry_count 或 0}
      设 tries = 转数字 {rc0}
      如果 {ck.status} 不等于 待处理
        设 tries = 计算 {tries} + 1
      结束
      设 crow = 解析JSON 空对象
      设 crow.chunk_id = {ck.id}
      设 crow.seq = 转数字 {ck.seq}
      设 crow.title = {ck.title}
      设 crow.chunk_status = {cs}
      设 crow.error = {ck.fail_reason}
      设 crow.tries = 转数字 {tries}
      设 crows = 列表加项 {crows} {crow}
    结束
    设 tds = 查询 app.db textbook_import_drafts_by_task task_id={task_id}
    设 drows = 解析JSON []
    遍历 dd2 于 {t.drafts}
      设 df = 查一行 app.db textbook_import_draft_by_id id={dd2.id}
      设 dx = 调用 取草稿课 draft_id={dd2.id}
      设 mp = 调用 映射文本 item_codes={df.item_codes} point_codes={df.point_codes}
      设 iss = 调用 问题文本 draft={df} task_drafts={tds}
      设 dl = {df.level 或}
      如果 {dl} 为空
        设 dl = ?
      结束
      设 drow = 解析JSON 空对象
      设 drow.draft = 转数字 {dd2.id}
      设 drow.seq = 转数字 {dd2.seq}
      设 drow.title = {dd2.title}
      设 drow.draft_level = {dl}
      设 drow.mapping = {mp.text}
      设 drow.issues = {iss.text}
      如果 {dx.confidence} 不为空
        设 drow.confidence = {dx.confidence}%
      否则
        设 drow.confidence = {zz 或}
      结束
      设 drow.review = {dd2.status}
      设 drow.href = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?draft={dd2.id}
      设 drows = 列表加项 {drows} {drow}
    结束
    返回 {"job": {job}, "job_note": "", "import_chunks": {crows}, "import_drafts": {drows}, "import_rejected": {rej}}
  结束

  公开 函数 草稿视图 draft_id with_form?
    设 ef = 解析JSON 空对象
    设 dr = 查一行 app.db textbook_import_draft_by_id id={draft_id}
    如果 {dr} 为空
      返回 {"draft": {"draft": {draft_id}, "missing": "没有这一课草稿（{draft_id}），可能任务已经删了。", "back": "#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5"}, "form": {ef}}
    结束
    设 d = 调用 取草稿课 draft_id={draft_id}
    设 t = 查一行 app.db textbook_import_task_by_id id={d.task_id}
    设 ch = 查一行 app.db textbook_import_chunk_by_id id={d.chunk_id}
    设 fc = 第?块「?」
    如果 {ch} 不为空
      设 fc = 第{ch.seq}块「{ch.title}」
    结束
    设 tds = 查询 app.db textbook_import_drafts_by_task task_id={d.task_id}
    设 iss = 调用 问题文本 draft={dr} task_drafts={tds}
    设 ex = {d.examples 或}
    如果 {ex} 为空
      设 ex = []
    结束
    设 head = 系列{t.series_code} · 第{d.seq}课 · {d.status}
    设 draft = 解析JSON 空对象
    设 draft.draft = 转数字 {d.id}
    设 draft.job = 转数字 {d.task_id}
    设 draft.seq = 转数字 {d.seq}
    设 draft.title = {d.title}
    设 draft.draft_level = {d.level}
    设 draft.summary = {d.summary}
    设 draft.explanation = {d.explain}
    设 draft.formation = {d.connection}
    设 draft.examples = {ex}
    设 draft.dropped = {d.dropped_codes 或}
    设 draft.issues = {iss.text}
    设 draft.reason = {d.reason 或}
    如果 {d.confidence} 不为空
      设 draft.confidence = {d.confidence}%
    否则
      设 draft.confidence = {zz 或}
    结束
    设 draft.review = {d.status}
    设 draft.series = {t.series_code}
    设 draft.head = {head}
    设 draft.from_chunk = {fc}
    设 draft.back = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?job={d.task_id}
    设 draft.missing = {zz 或}
    设 maps = 解析JSON []
    设 ia = 解析JSON []
    如果 {d.item_codes} 不为空
      设 ia = 按正则切分 {d.item_codes} ,
    结束
    遍历 ic 于 {ia}
      如果 {ic} 不为空
        设 it = 调用 kg.取条目 code={ic}
        如果 {it} 不为空
          设 lab = {it.name}
          如果 {it.point_code} 不为空
            设 pt0 = 调用 kg.取知识点 code={it.point_code}
            如果 {pt0} 不为空
              设 lab = {it.name}（属于 {pt0.title}）
            结束
          结束
          设 mrow = 解析JSON 空对象
          设 mrow.map_kind = 条目
          设 mrow.map_code = {ic}
          设 mrow.map_label = {lab}
          设 maps = 列表加项 {maps} {mrow}
        结束
      结束
    结束
    设 pa = 解析JSON []
    如果 {d.point_codes} 不为空
      设 pa = 按正则切分 {d.point_codes} ,
    结束
    遍历 pcd 于 {pa}
      如果 {pcd} 不为空
        设 pt1 = 调用 kg.取知识点 code={pcd}
        如果 {pt1} 不为空
          设 mrow2 = 解析JSON 空对象
          设 mrow2.map_kind = 知识点
          设 mrow2.map_code = {pcd}
          设 mrow2.map_label = {pt1.title}
          设 maps = 列表加项 {maps} {mrow2}
        结束
      结束
    结束
    设 oitems = 调用 kg.列条目
    设 opts = 解析JSON []
    遍历 oi 于 {oitems.items}
      设 orow = 解析JSON 空对象
      设 orow.value = {oi.code}
      设 orow.label = {oi.name}（条目，{oi.code}）
      设 opts = 列表加项 {opts} {orow}
    结束
    设 opoints = 调用 kg.列知识点
    遍历 op 于 {opoints.points}
      设 prow = 解析JSON 空对象
      设 prow.value = {op.code}
      设 prow.label = 〔{op.title}〕（知识点，{op.code}）
      设 opts = 列表加项 {opts} {prow}
    结束
    如果 {with_form} 等于 是
      设 form = 解析JSON 空对象
      设 form.title = {d.title}
      设 form.draft_level = {d.level}
      设 form.seq = {d.seq}
      设 form.summary = {d.summary}
      设 form.formation = {d.connection}
      设 form.explanation = {d.explain}
      设 form.examples = {ex}
      设 form.map_add = {zz 或}
      设 form.map_typed = {zz 或}
    否则
      设 form = {"map_add": "", "map_typed": ""}
    结束
    返回 {"draft": {draft}, "draft_note": "", "draft_maps": {maps}, "map_options": {opts}, "form": {form}}
  结束

  函数 系列视图 series_code
    设 sl = 调用 列已导入系列 series_code={series_code}
    设 found = 0
    设 fname = {zz 或}
    设 flc = 0
    遍历 x 于 {sl.series}
      如果 {x.code} 等于 {series_code}
        设 found = 1
        设 fname = {x.name}
        设 flc = {x.lesson_count}
      结束
    结束
    设 can = 转数字 0
    如果 {found} 等于 1
      如果 {series_code} 不等于 hanabira
        设 can = 转数字 1
      结束
      设 head = 系列{series_code}（{fname}）：{flc}课。在用，教材页的下拉里能选到。
    否则
      设 head = 没有这个系列（{series_code}），可能已经撤下了。
    结束
    返回 {"series_view": {"code": "{series_code}", "head": "{head}", "note": "", "can_withdraw": {can}, "back": "#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5"}}
  结束

  公开 函数 导入视图 task_id? draft_id? series_code?
    设 ef = 解析JSON 空对象
    如果 {task_id} 不为空
      设 v = 调用 任务视图 task_id={task_id}
      设 v.form = {ef}
      返回 {v}
    否则如果 {draft_id} 不为空
      设 v = 调用 草稿视图 draft_id={draft_id} with_form=是
      返回 {v}
    否则如果 {series_code} 不为空
      设 v = 调用 系列视图 series_code={series_code}
      设 v.form = {ef}
      返回 {v}
    结束
    返回 {"form": {ef}}
  结束

  公开 函数 一键通过页面 task_id
    设 r = 调用 一键通过 task_id={task_id}
    设 v = 调用 任务视图 task_id={task_id}
    设 v.job_note = 通过了：{r.approved}课（有映射、还待审的）。
    返回 {v}
  结束

  公开 函数 确认导入页面 task_id
    设 r = 调用 确认导入 task_id={task_id}
    设 v = 调用 任务视图 task_id={task_id}
    返回 {v}
  结束

  公开 函数 审核草稿页面 draft_id decision job?
    设 r = 调用 审核草稿课 draft_id={draft_id} decision={decision}
    如果 {job} 不为空
      设 v = 调用 任务视图 task_id={job}
      设 ef = 解析JSON 空对象
      设 v.form = {ef}
    否则
      设 v = 调用 草稿视图 draft_id={draft_id} with_form=否
    结束
    返回 {v}
  结束

  公开 函数 保存草稿页面 draft_id title draft_level seq summary? formation? explanation? examples?
    设 d0 = 查一行 app.db textbook_import_draft_by_id id={draft_id}
    如果 {d0} 为空
      报错 404 没有这个草稿课
    结束
    如果 {examples} 不为空
      设 same = 相等 {examples} {d0.examples}
      如果 {same} 等于 否
        设 jq.examples = {examples}
        设 isarr = 查一值表 app.db textbook_import_json_is_array {jq}
        如果 {isarr} 不等于 1
          报错 400 例句要写成 JSON 数组，每句一个对象（jp 日语、zh 中文）
        结束
      结束
    结束
    设 r = 调用 修改草稿课 draft_id={draft_id} title={title} level={draft_level} summary={summary 或} explain={explanation 或} connection={formation 或} examples={examples 或} seq={seq}
    设 v = 调用 草稿视图 draft_id={draft_id} with_form=是
    设 v.draft_note = 保存了。
    返回 {v}
  结束

  公开 函数 加映射页面 draft_id map_typed? map_add?
    设 code = {map_typed 或}
    如果 {code} 为空
      设 code = {map_add 或}
    结束
    如果 {code} 为空
      报错 400 从下拉里选一个条目或知识点，或者输入编号
    结束
    设 kind = item
    设 it = 调用 kg.取条目 code={code}
    如果 {it} 为空
      设 pt = 调用 kg.取知识点 code={code}
      如果 {pt} 为空
        报错 400 库里没有编号「{code}」，只能挑已有的条目、知识点（不新建）
      结束
      设 kind = point
    结束
    设 r = 调用 改映射 draft_id={draft_id} kind={kind} action=add code={code}
    设 v = 调用 草稿视图 draft_id={draft_id} with_form=否
    返回 {v}
  结束

  公开 函数 去掉映射页面 draft_id map_code
    设 d = 调用 取草稿课 draft_id={draft_id}
    设 kind = point
    设 wrapped = ,{d.item_codes},
    如果 {wrapped} 包含 ,{map_code},
      设 kind = item
    结束
    设 r = 调用 改映射 draft_id={draft_id} kind={kind} action=remove code={map_code}
    设 v = 调用 草稿视图 draft_id={draft_id} with_form=否
    返回 {v}
  结束

  公开 函数 重试块页面 chunk_id
    设 r = 调用 重试块 chunk_id={chunk_id}
    设 v = 调用 任务视图 task_id={r.task_id}
    返回 {v}
  结束

  公开 函数 撤下系列页面 series_code
    设 sl = 调用 列已导入系列
    设 nm = {series_code}
    遍历 x 于 {sl.series}
      如果 {x.code} 等于 {series_code}
        设 nm = {x.name}
      结束
    结束
    设 r = 调用 撤下已导入系列 series_code={series_code}
    设 h = 调用 导入首页
    设 note = 撤下了：库里删掉{r.removed_lessons}课（连同映射），教材页的下拉里不再有它。
    如果 {r.moved} 不等于 0
      设 note = {note}课文文件留在 content/lesson/series/{series_code}.withdrawn.jsonl。
    结束
    设 head = 系列{series_code}（{nm}）：0课。已撤下，教材页的下拉里没有它。
    返回 {"series_view": {"code": "{series_code}", "head": "{head}", "note": "{note}", "can_withdraw": 0, "back": "#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5"}, "import_jobs": {h.import_jobs}, "import_series": {h.import_series}}
  结束

  函数 任务进度文本 task_id
    设 t = 调用 取任务 task_id={task_id}
    设 cf = {t.chunk_failed}
    设 cdn = 查一值 app.db textbook_import_chunk_count_status task_id={task_id} status=完成
    设 fin = 计算 {cdn} + {cf}
    设 extra = {zz 或}
    如果 {cf} 大于 0
      设 extra = ，出错{cf}块
    结束
    如果 {t.status} 等于 处理中
      设 s = 解析中{fin}/{t.chunk_total}块{extra}
    否则如果 {t.status} 等于 失败
      设 s = 失败：{t.fail_reason}
    否则如果 {t.status} 等于 已导入
      设 s = 已导入
    否则如果 {t.status} 等于 已撤下
      设 s = 已撤下
    否则
      设 nd = 列表长度 {t.drafts}
      设 np = 转数字 0
      设 nr = 0
      遍历 dd 于 {t.drafts}
        如果 {dd.status} 等于 通过
          设 np = 计算 {np} + 1
        结束
        如果 {dd.status} 等于 驳回
          设 nr = 计算 {nr} + 1
        结束
      结束
      设 s = 待审{nd}课（通过{np}、驳回{nr}）{extra}
    结束
    设 o.text = {s}
    返回 {o}
  结束

  函数 映射文本 item_codes point_codes
    设 names = {zz 或}
    设 pts = {zz 或}
    设 ia = 解析JSON []
    如果 {item_codes} 不为空
      设 ia = 按正则切分 {item_codes} ,
    结束
    遍历 c 于 {ia}
      如果 {c} 不为空
        设 it = 调用 kg.取条目 code={c}
        如果 {it} 不为空
          如果 {names} 为空
            设 names = {it.name}
          否则
            设 names = {names}、{it.name}
          结束
        结束
      结束
    结束
    设 pa = 解析JSON []
    如果 {point_codes} 不为空
      设 pa = 按正则切分 {point_codes} ,
    结束
    遍历 c2 于 {pa}
      如果 {c2} 不为空
        设 pt = 调用 kg.取知识点 code={c2}
        如果 {pt} 不为空
          如果 {pts} 为空
            设 pts = 〔{pt.title}〕
          否则
            设 pts = {pts}、〔{pt.title}〕
          结束
        结束
      结束
    结束
    设 s = （没有）
    如果 {names} 不为空 且 {pts} 不为空
      设 s = {names} / {pts}
    否则如果 {names} 不为空
      设 s = {names}
    否则如果 {pts} 不为空
      设 s = {pts}
    结束
    设 o.text = {s}
    返回 {o}
  结束

  函数 问题文本 draft task_drafts
    设 out = {zz 或}
    设 lv = {draft.level 或}
    如果 {lv} 不等于 N5 且 {lv} 不等于 N4 且 {lv} 不等于 N3 且 {lv} 不等于 N2 且 {lv} 不等于 N1
      设 out = 等级没认出
    结束
    设 ic0 = {draft.item_codes 或}
    设 pc0 = {draft.point_codes 或}
    如果 {ic0} 为空 且 {pc0} 为空
      设 msg = 没映射到已有条目或知识点
      如果 {out} 为空
        设 out = {msg}
      否则
        设 out = {out}；{msg}
      结束
    结束
    设 e1 = {draft.explain 或}
    设 e2 = {zz 或}
    如果 {e1} 不为空
      设 e2 = 替换 {e1} \s
    结束
    如果 {e2} 为空
      设 msg = 讲解是空的
      如果 {out} 为空
        设 out = {msg}
      否则
        设 out = {out}；{msg}
      结束
    结束
    设 s1 = {draft.summary 或}
    设 s2 = {zz 或}
    如果 {s1} 不为空
      设 s2 = 替换 {s1} \s
    结束
    如果 {s2} 为空
      设 msg = 一句话是空的
      如果 {out} 为空
        设 out = {msg}
      否则
        设 out = {out}；{msg}
      结束
    结束
    如果 {draft.status} 不等于 驳回
      设 dup = 0
      遍历 o2 于 {task_drafts}
        如果 {o2.id} 不等于 {draft.id} 且 {o2.seq} 等于 {draft.seq} 且 {o2.status} 不等于 驳回
          设 dup = 1
          跳出
        结束
      结束
      如果 {dup} 等于 1
        设 msg = 课序跟别的课重复
        如果 {out} 为空
          设 out = {msg}
        否则
          设 out = {out}；{msg}
        结束
      结束
    结束
    设 o.text = {out}
    返回 {o}
  结束

结束
