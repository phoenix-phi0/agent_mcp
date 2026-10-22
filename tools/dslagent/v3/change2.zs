# 修改2：读 plan/audit2.json。module_issue → 对 issues 每条派一次 modify_module（项目拷贝里做，验收通过才拷回），派过才跑全量回归；
# contract_issue → 终止（约定有问题，回规划，不改文件）；ok / unchecked → 直接返回。
# 参数：req（保留给 CLI，这里用不上）
用包 common v3 text
读JSON a = plan/audit2.json
如果 {a.result} 等于 contract_issue
  终止 失败 约定有问题，需回到规划
结束
设 changed = 解析JSON []
设 failed = 解析JSON []
设 out.changed = {changed}
设 out.failed = {failed}
设 out.regression = 没派，没跑
如果 {a.result} 等于 module_issue
  遍历 item 于 {a.issues}
    设 task = 问题：{item.issue}；依据：{item.basis}；只改与这个问题有关的地方，其他函数不动；约定不能改。
    设 inp.模块 = {item.module}
    设 r = 派代理 角色=modify_module 任务={task} 入参={inp}
    如果 {r.status} 等于 ok
      设 changed = 列表加项 {changed} {item.module}：{r.result}
    否则
      设 failed = 列表加项 {failed} {item.module}：{r.reason}
    结束
  结束
  设 g = 全量回归
  设 out.changed = {changed}
  设 out.failed = {failed}
  设 out.regression = {g.summary}
结束
返回 {out}
