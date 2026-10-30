# 修改2（只做一轮）：读 plan/audit2.json。module_issue → 把 issues 按 module 分组，每个模块派一次 modify_module（任务文本列出该模块全部问题）；
# contract_issue / unchecked → 终止（约定有问题回规划 / 有模块没核查成）；ok → 直接返回。不跑回归、不核查，循环交给 fix2.zs。
# 参数：req（保留给 CLI，这里用不上）
# 返回 {changed, failed, cmods, fmods}：cmods / fmods 是改成 / 没改成的模块名（形如 |graph|vocab|，没有就是空串），给 fix2.zs 判断「连续两轮同样没改成」。
用包 common v3 text
读JSON a = plan/audit2.json
如果 {a.result} 等于 contract_issue
  终止 失败 约定有问题，需回到规划
结束
如果 {a.result} 等于 unchecked
  终止 失败 有模块没核查成，先重新核查
结束
设 changed = 解析JSON []
设 failed = 解析JSON []
设 out.changed = {changed}
设 out.failed = {failed}
设 cmods = {cmods 或}
设 fmods = {fmods 或}
如果 {a.result} 等于 module_issue
  设 seen = |
  遍历 item 于 {a.issues}
    如果 {seen} 不包含 |{item.module}|
      设 seen = {seen}{item.module}|
      设 task = 该模块的问题：
      遍历 it 于 {a.issues}
        如果 {it.module} 等于 {item.module}
          设 task = {task} 问题：{it.issue}；依据：{it.basis}。
        结束
      结束
      设 task = {task} 只改与这些问题有关的地方，其他函数不动；约定不能改。
      设 inp.模块 = {item.module}
      设 r = 派代理 角色=modify_module 任务={task} 入参={inp}
      如果 {r.status} 等于 ok
        设 changed = 列表加项 {changed} {item.module}：{r.result}
        设 cmods = {cmods}|{item.module}|
      否则
        设 failed = 列表加项 {failed} {item.module}：{r.reason}
        设 fmods = {fmods}|{item.module}|
      结束
    结束
  结束
  设 out.changed = {changed}
  设 out.failed = {failed}
结束
设 out.cmods = {cmods}
设 out.fmods = {fmods}
返回 {out}
