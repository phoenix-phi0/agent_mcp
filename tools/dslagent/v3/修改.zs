# 修改：读问题清单 → 每条问题对每个点名模块派一次 modify_module（v2 完整运行，在项目拷贝里做，验收通过才拷回）→ 接口冒烟（方式=核查：只报告，不重做别的模块、不改 state）→ 返回汇总。
# 不走计划流程、不动约定与顶层：只改与问题有关的代码，约定不能改。modules 有多个（逗号 / 顿号隔开）就拆开逐个派。
# 参数：req issues=latest（issues 认 latest 也认 最新；req 保留给 CLI，这里用不上）
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
设 s = 接口冒烟 方式=核查
设 out.changed = {changed}
设 out.failed = {failed}
设 out.smoke = {s.summary}
返回 {out}
