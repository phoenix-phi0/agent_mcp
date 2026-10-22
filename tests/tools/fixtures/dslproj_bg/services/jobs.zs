业务 jobs
  用包 db text

  公开 函数 提交任务 title t1 t2 t3
    事务 app.db
      设 n = 写库 app.db jobs_task_insert title={title}
      设 job_id = 查一值 app.db jobs_task_max
      设 n = 写库 app.db jobs_item_insert task_id={job_id} body={t1}
      设 n = 写库 app.db jobs_item_insert task_id={job_id} body={t2}
      设 n = 写库 app.db jobs_item_insert task_id={job_id} body={t3}
    结束
    后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/jobs_run_fail.zs
    返回 {"job_id": {job_id}}
  结束

  公开 函数 任务进度 job_id
    设 task = 查一行 app.db jobs_task_one id={job_id}
    如果 {task} 为空
      报错 404 没有这个任务
    结束
    设 total = 查一值 app.db jobs_item_total task_id={job_id}
    设 done = 查一值 app.db jobs_item_count task_id={job_id} status=完成
    设 failed = 查一值 app.db jobs_item_count task_id={job_id} status=失败
    返回 {"status": "{task.status}", "total": {total}, "done": {done}, "failed": {failed}}
  结束

  公开 函数 各项状态 job_id
    设 rows = 查询 app.db jobs_item_list task_id={job_id}
    返回 {"items": {rows}}
  结束

  公开 函数 重试失败项 job_id
    设 task = 查一行 app.db jobs_task_one id={job_id}
    如果 {task} 为空
      报错 404 没有这个任务
    结束
    设 retried = 查一值 app.db jobs_item_count task_id={job_id} status=失败
    事务 app.db
      设 n = 写库 app.db jobs_item_reset task_id={job_id}
      设 n = 写库 app.db jobs_task_set id={job_id} status=待处理 error=
    结束
    后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/jobs_run_fail.zs
    返回 {"retried": {retried}}
  结束

  公开 函数 开始 job_id
    设 task = 查一行 app.db jobs_task_one id={job_id}
    如果 {task.title} 等于 explode
      报错 400 标题不能是explode
    结束
    设 n = 写库 app.db jobs_task_set id={job_id} status=处理中 error=
    返回 {"ok": 1}
  结束

  公开 函数 待处理项 job_id
    设 rows = 查询 app.db jobs_item_pending task_id={job_id}
    返回 {"items": {rows}}
  结束

  公开 函数 处理一项 item_id
    设 item = 查一行 app.db jobs_item_one id={item_id}
    如果 {item.body} 为空
      报错 400 内容为空
    结束
    设 up = 转大写 {item.body}
    设 n = 写库 app.db jobs_item_done id={item_id} result={up}
    返回 {"ok": 1}
  结束

  公开 函数 记项失败 item_id error
    设 n = 写库 app.db jobs_item_fail id={item_id} error={error}
    返回 {"ok": 1}
  结束

  公开 函数 收尾 job_id
    设 failed = 查一值 app.db jobs_item_count task_id={job_id} status=失败
    设 status = 完成
    如果 {failed} 大于 0
      设 status = 部分失败
    结束
    设 n = 写库 app.db jobs_task_set id={job_id} status={status} error=
    返回 {"status": "{status}"}
  结束

  公开 函数 标任务失败 job_id error
    设 n = 写库 app.db jobs_task_set id={job_id} status=失败 error={error}
    返回 {"ok": 1}
  结束
结束
