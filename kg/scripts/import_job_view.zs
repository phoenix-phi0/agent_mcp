# 教材导入审阅页：一个任务的进度、块表、草稿课表；导入过的话还有导入报告和
# 拒收清单。由接口「执行」，直接往响应里放 state.job 和 lists。
#
# 参数 job：import_job 的 id。没有这个任务回 state.job.missing。

用包 db http common data

设 args.job = {job}
设 job_row = 查一行表 app.db import_job_one {args}
如果 {job_row.id 或} 为空
  设 missing.id = {job}
  设 missing.missing = 没有这个导入任务（{job}），可能已经删了。
  设 missing.running = 0
  设 missing.back = #%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5
  设 state.job = {missing}
  响应 state {state}
  返回 missing
结束

设 chunks = 查询表 app.db import_chunks {args}
设 drafts = 查询表 app.db import_drafts {args}
设 rejected = 解析JSON []
设 job_row.missing = 
设 job_row.report_note = 
设 job_row.textbook = 
设 report = 解析JSON {job_row.report}
设 report_keys = 条数 {report}
如果 {report_keys} 大于 0
  设 job_row.report_note = 导入报告：导入 {report.lessons} 课，映射到条目 {report.links} 条、知识点 {report.points} 条，拒收 {report.rejected} 行，没映射到任何条目知识点的课 {report.orphans} 课。
  设 got = {report.rejected_rows 或}
  设 got_n = 条数 {got}
  如果 {got_n} 大于 0
    设 rejected = {got}
  结束
  设 job_row.textbook = #%E6%95%99%E6%9D%90
结束
设 job_row.report = 
设 state.job = {job_row}
# 一次操作的提示（「通过了 3 课」）由接口在这之后另放，这里先清掉上次的
设 state.job_note = 
响应 state {state}
设 group.import_chunks = {chunks}
设 group.import_drafts = {drafts}
设 group.import_rejected = {rejected}
响应 lists {group}
