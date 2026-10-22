接口 POST /jobs/submit
  设 r = 调用 jobs.提交任务 title={title} t1={t1} t2={t2} t3={t3}
  返回 {r}
结束

接口 GET /jobs/progress
  设 r = 调用 jobs.任务进度 job_id={job_id}
  返回 {r}
结束

接口 GET /jobs/items
  设 r = 调用 jobs.各项状态 job_id={job_id}
  返回 {r}
结束

接口 POST /jobs/retry
  设 r = 调用 jobs.重试失败项 job_id={job_id}
  返回 {r}
结束
