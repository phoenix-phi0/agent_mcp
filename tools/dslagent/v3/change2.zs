# 修改2：最小主干。读问题清单 → 每条问题对每个点名模块派一次 modify_module（v2，项目拷贝里做，验收通过才拷回）→ 最后跑一次全量回归 → 返回汇总。
# 刻意不含（都是以后的扩展）：接口冒烟、全局检查、代码核查、改约定 / 改顶层。
# 参数：req issues=latest（req 保留给 CLI，这里用不上）
用包 common v3 text
设 iss = 读问题清单 {issues}
设 changed = 解析JSON []
设 failed = 解析JSON []
遍历 item 于 {iss.items}
  设 mods = 按正则切分 {item.modules} [,，、\s]+
  遍历 m 于 {mods}
    如果 {m} 不为空
      设 task = 问题：{item.issue}；依据：{item.basis}；只改与这个问题有关的地方，其他函数不动；约定不能改。
      设 inp.模块 = {m}
      设 r = 派代理 角色=modify_module 任务={task} 入参={inp}
      如果 {r.status} 等于 ok
        设 changed = 列表加项 {changed} {m}：{r.result}
      否则
        设 failed = 列表加项 {failed} {m}：{r.reason}
      结束
    结束
  结束
结束
设 g = 全量回归
设 out.changed = {changed}
设 out.failed = {failed}
设 out.regression = {g.summary}
返回 {out}
