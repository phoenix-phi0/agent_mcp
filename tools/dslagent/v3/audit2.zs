# 核查2：全量回归 + 每个有代码的模块派一次 派任务（约定 + 代码 + 顶层规划）→ 汇总成一个 result 存 plan/audit2.json 并返回。
# result 按优先级：contract_issue（有约定问题，issues 只放约定问题）> module_issue（模块问题 + 回归不过）> unchecked（有模块没核查成）> ok。
# 参数：req（保留给 CLI，这里用不上）llm=sonnet
用包 common v3 text code
模型 {llm}
设 b = 全量回归
设 lg = 只读不改，读不到的部分不要猜。
设 con = 解析JSON []
设 mod = 解析JSON []
设 un = 解析JSON []
遍历 x 于 {b.code_modules}
  设 desc = 这是用中文DSL写的后端项目的模块「{x.module}」：contracts 下是约定（设计），其余是代码，另附顶层规划。判断它部署运行后能不能按需求工作。约定本身有错 result 填 contract_issue，约定没错但代码有错填 module_issue，都没有填 ok；有问题时 issue 写问题，basis 写哪个文件哪一处。
  设 fl = 列表加项 {x.files} plan/top.zs
  设 r = 派任务 {desc} {fl} {lg} result:ok|module_issue|contract_issue,issue?:文本,basis?:文本
  如果 {r.status} 不等于 成功
    设 u.module = {x.module}
    设 u.reason = {r.reason}
    设 un = 列表加项 {un} {u}
  否则
    设 i.module = {x.module}
    设 i.issue = {r.result.issue 或}
    设 i.basis = {r.result.basis 或}
    如果 {r.result.result} 等于 contract_issue
      设 con = 列表加项 {con} {i}
    否则如果 {r.result.result} 等于 module_issue
      设 mod = 列表加项 {mod} {i}
    结束
  结束
结束
遍历 it 于 {b.items}
  设 g.module = {it.modules}
  设 g.issue = {it.issue}
  设 g.basis = {it.basis}
  设 mod = 列表加项 {mod} {g}
结束
设 w.file = plan/audit2.json
设 w.content.result = ok
设 nu = 列表长度 {un}
如果 {nu} 大于 0
  设 w.content.result = unchecked
  设 w.content.unchecked = {un}
结束
设 nm = 列表长度 {mod}
如果 {nm} 大于 0
  设 w.content.result = module_issue
  设 w.content.issues = {mod}
结束
设 nc = 列表长度 {con}
如果 {nc} 大于 0
  设 w.content.result = contract_issue
  设 w.content.issues = {con}
结束
设 s = 写文件 {w}
返回 {w.content}
