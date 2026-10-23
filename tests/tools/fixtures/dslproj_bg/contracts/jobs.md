模块 jobs
依赖 无

## 表
表 jobs_task
  id 整数 主键
  title 文本 任务标题
  status 文本 状态：待处理 / 处理中 / 完成 / 部分失败 / 失败
  error 文本 任务级失败原因
表 jobs_item
  id 整数 主键
  task_id 整数 所属任务
  body 文本 原文
  result 文本 处理结果（大写）
  status 文本 状态：待处理 / 完成 / 失败
  error 文本 失败原因

## 函数
公开 函数 提交任务 title t1 t2 t3
  返回 {job_id}
  伪代码 往 jobs_task 插一行 (title, status=待处理)，取到 job_id
  伪代码 往 jobs_item 插三行 (task_id=job_id, body=t1/t2/t3, status=待处理)，写库在一个事务里
  伪代码 事务结束之后 后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/jobs_run_fail.zs
  伪代码 返回 {"job_id": job_id}
公开 函数 任务进度 job_id
  返回 {status, total, done, failed}
  报错 404 没有这个任务
  伪代码 查任务，没有则报错 404；统计各项完成数 done、失败数 failed、总数 total
  伪代码 返回 {"status": 任务状态, "total": total, "done": done, "failed": failed}
公开 函数 各项状态 job_id
  返回 {items}，每项 {id, body, result, status, error}
  伪代码 查该任务的全部项，按 id 排序，返回 {"items": 列表}
公开 函数 重试失败项 job_id
  返回 {retried}
  报错 404 没有这个任务
  伪代码 查任务，没有则报错 404；把失败项改回待处理，任务状态改回待处理；事务结束之后 后台执行 scripts/jobs_run.zs job_id={job_id} on_error=scripts/jobs_run_fail.zs
  伪代码 返回 {"retried": 失败项个数}
公开 函数 开始 job_id
  返回 {ok}
  报错 400 标题不能是explode
  伪代码 查任务；标题是 explode 则报错 400 标题不能是explode（模拟任务级出错）；任务状态=处理中
公开 函数 待处理项 job_id
  返回 {items}
  伪代码 查该任务状态=待处理的项（id 升序）
公开 函数 处理一项 item_id
  返回 {ok}
  报错 400 内容为空
  伪代码 查该项；原文为空则报错 400 内容为空；否则 result=转大写(原文)，状态=完成
公开 函数 记项失败 item_id error
  返回 {ok}
  伪代码 该项状态=失败，error=error
公开 函数 收尾 job_id
  返回 {status}
  伪代码 有失败项则任务状态=部分失败，否则=完成
公开 函数 标任务失败 job_id error
  返回 {ok}
  伪代码 任务状态=失败，error=error

## 接口
POST /jobs/submit -> 提交任务
GET /jobs/progress -> 任务进度
GET /jobs/items -> 各项状态
POST /jobs/retry -> 重试失败项

## 脚本
scripts/jobs_run.zs 入参 job_id；出错 scripts/jobs_run_fail.zs；逐项处理任务里待处理的项，失败项记原因，最后收尾

## 用例
用例 提交任务_全成功
  调用 提交任务 title=第1课\n讲解 t1=a t2=b t3=c
  得 job_id=1
  库 jobs_item 共 3 行
  库 jobs_item 含 body=b result=B status=完成
  库 jobs_task 含 id=1 status=完成

用例 提交任务_某项为空记失败原因
  调用 提交任务 title=T t1=a t2=空 t3=c
  得 job_id=1
  库 jobs_item 含 body=a result=A status=完成
  库 jobs_item 含 id=2 status=失败 error=内容为空
  库 jobs_item 含 body=c result=C status=完成
  库 jobs_task 含 id=1 status=部分失败

用例 提交任务_任务级出错走on_error
  调用 提交任务 title=explode t1=a t2=b t3=c
  得 job_id=1
  库 jobs_task 含 id=1 status=失败
  库 jobs_item 无 status=完成

用例 任务进度_完成
  先 调用 提交任务 title=T t1=a t2=空 t3=c
  调用 任务进度 job_id=1
  得 status=部分失败 total=3 done=2 failed=1

用例 任务进度_没有任务
  调用 任务进度 job_id=99
  报错 404

用例 各项状态_列出各项
  先 调用 提交任务 title=T t1=a t2=b t3=c
  调用 各项状态 job_id=1
  得 有返回

用例 重试失败项_失败项重新处理
  先 数据 jobs_task title=T status=部分失败
  先 数据 jobs_item task_id=1 body=x status=失败 error=boom
  调用 重试失败项 job_id=1
  得 retried=1
  库 jobs_item 含 body=x result=X status=完成
  库 jobs_task 含 id=1 status=完成

用例 重试失败项_没有任务
  调用 重试失败项 job_id=99
  报错 404

用例 开始_标处理中
  先 数据 jobs_task title=T status=待处理
  调用 开始 job_id=1
  得 ok=1
  库 jobs_task 含 id=1 status=处理中

用例 开始_explode报错
  先 数据 jobs_task title=explode status=待处理
  调用 开始 job_id=1
  报错 400

用例 待处理项_只列待处理
  先 数据 jobs_task title=T status=待处理
  先 数据 jobs_item task_id=1 body=a status=待处理
  先 数据 jobs_item task_id=1 body=b status=完成
  调用 待处理项 job_id=1
  得 有返回

用例 处理一项_转大写
  先 数据 jobs_item task_id=1 body=ab status=待处理
  调用 处理一项 item_id=1
  得 ok=1
  库 jobs_item 含 id=1 result=AB status=完成

用例 处理一项_内容为空
  先 数据 jobs_item task_id=1 body= status=待处理
  调用 处理一项 item_id=1
  报错 400

用例 记项失败_写原因
  先 数据 jobs_item task_id=1 body=a status=待处理
  调用 记项失败 item_id=1 error=坏了
  得 ok=1
  库 jobs_item 含 id=1 status=失败 error=坏了

用例 收尾_有失败项
  先 数据 jobs_task title=T status=处理中
  先 数据 jobs_item task_id=1 body=a status=失败
  调用 收尾 job_id=1
  得 status=部分失败

用例 收尾_全完成
  先 数据 jobs_task title=T status=处理中
  先 数据 jobs_item task_id=1 body=a status=完成
  调用 收尾 job_id=1
  得 status=完成

用例 标任务失败_记原因
  先 数据 jobs_task title=T status=处理中
  调用 标任务失败 job_id=1 error=模型没回应
  得 ok=1
  库 jobs_task 含 id=1 status=失败 error=模型没回应
