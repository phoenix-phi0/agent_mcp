# 后台逐项处理一个任务（jobs.提交任务 / jobs.重试失败项 用「后台执行」交过来）。只做编排，状态都由本模块的函数读写。
# 参数 job_id：任务 id。
设 s = 调用 jobs.开始 job_id={job_id}
设 r = 调用 jobs.待处理项 job_id={job_id}
遍历 item 于 {r.items} 序号 i
  设 ok = 调用 jobs.处理一项 item_id={item.id} 出错时 e
  如果 {e} 不为空
    设 f = 调用 jobs.记项失败 item_id={item.id} error={e.error}
  结束
结束
设 d = 调用 jobs.收尾 job_id={job_id}
