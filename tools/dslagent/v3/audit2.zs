# 核查2：全量回归 + 每个有代码的模块派一次 派任务（约定 + 代码 + 顶层规划）→ 汇总成一个 result 存 plan/audit2.json 并返回。
# result 按优先级：contract_issue（有约定问题，issues 只放约定问题）> module_issue（模块问题 + 回归不过）> unchecked（有模块没核查成）> ok。
# 参数：req（保留给 CLI，这里用不上）llm=sonnet；syntax 由 run_entry 注入（prompts/project_syntax.md 全文）；
#   scope / modules（可省，缺省空 = 审全部模块，行为同旧）：CLI --modules a,b 注入，scope 是 |a|b| 形式，modules 是原文。
# 给了范围：只对点名模块派任务，result / issues / unchecked 只含范围内模块的问题；范围外模块（没审）的全量回归不过、
#   以及范围内模块的核查员指出「问题出在范围外的模块」（owner）的 contract_issue / module_issue，都不算数、不终止：
#   记进 skipped_issues（module, owner, kind[contract_issue|module_issue|regression], issue, basis, reason），继续审后面的模块。范围内模块自己的 contract_issue 仍照旧（result=contract_issue）。
#   audit2.json 另带 scope（点名的模块原文）；没有被跳过的问题时不写 skipped_issues，不给范围时两个字段都不写。
# 约定闸（K174）：最开头先跑 全局检查 约定=是（逐模块 v3/contracts.check，不调模型）。contract_check（CLI --contract-check）：
#   空 / 拦截（缺省）= 范围内有违约就立刻写 audit2.json：result=contract_issue、issues=违约、contract_check=拦截，不跑回归、不派核查员；
#   提醒 = 不拦，照常审完，违约放进 audit2.json 的 contract_warnings（不影响 result）；关 = 不跑（同旧）。
#   给了范围时范围外模块的违约不拦，记进 skipped_issues（kind=contract_check）。
用包 common v3 text code
模型 {llm}
设 sc = {scope 或}
设 cm = {contract_check 或}
设 sk = 解析JSON []
设 cw = 解析JSON []
如果 {cm} 不等于 关
  设 g0 = 全局检查 约定=是
  遍历 ci 于 {g0.items}
    设 cin = 是
    如果 {sc} 不为空
      如果 {sc} 不包含 |{ci.modules}|
        设 cin = 否
      结束
    结束
    如果 {cin} 等于 是
      设 e.module = {ci.modules}
      设 e.issue = {ci.issue}
      设 e.basis = {ci.basis}
      设 cw = 列表加项 {cw} {e}
    否则
      设 k0.module = {ci.modules}
      设 k0.owner = {ci.modules}
      设 k0.kind = contract_check
      设 k0.issue = {ci.issue}
      设 k0.basis = {ci.basis}
      设 k0.reason = 模块在范围外，约定闸不拦
      设 sk = 列表加项 {sk} {k0}
    结束
  结束
  设 ncw = 列表长度 {cw}
  如果 {ncw} 大于 0 且 {cm} 不等于 提醒
    设 w0.file = plan/audit2.json
    设 w0.content.result = contract_issue
    设 w0.content.contract_check = 拦截
    设 w0.content.issues = {cw}
    如果 {sc} 不为空
      设 w0.content.scope = {modules}
    结束
    设 nsk0 = 列表长度 {sk}
    如果 {nsk0} 大于 0
      设 w0.content.skipped_issues = {sk}
    结束
    设 s0 = 写文件 {w0}
    返回 {w0.content}
  结束
结束
设 b = 全量回归
设 lg = 只读不改，读不到的部分不要猜。
设 con = 解析JSON []
设 mod = 解析JSON []
设 un = 解析JSON []
遍历 x 于 {b.code_modules}
  设 ins = 是
  如果 {sc} 不为空
    如果 {sc} 不包含 |{x.module}|
      设 ins = 否
    结束
  结束
  如果 {ins} 等于 是
    设 desc = 这是用中文DSL写的后端项目的模块「{x.module}」：contracts 下是约定（设计），其余是代码，另附顶层规划。判断它部署运行后能不能按需求工作。判断依据以附上的项目写法说明为准，说明里写了的规则（参数含义、支持与不支持的写法）都要核对。约定本身有错 result 填 contract_issue，约定没错但代码有错填 module_issue，都没有填 ok；有问题时 issue 写问题，basis 写哪个文件哪一处。
    设 fl = 列表加项 {x.files} plan/top.zs
    设 fl = 列表加项 {fl} {syntax}
    如果 {sc} 为空
      设 r = 派任务 {desc} {fl} {lg} result:ok|module_issue|contract_issue,issue?:文本,basis?:文本
    否则
      设 desc = {desc} 有问题时 owner 写问题出在哪个模块（只写模块名，如 lesson；问题就在「{x.module}」本身时不写）。
      设 r = 派任务 {desc} {fl} {lg} result:ok|module_issue|contract_issue,issue?:文本,basis?:文本,owner?:文本
    结束
    如果 {r.status} 不等于 成功
      设 u.module = {x.module}
      设 u.reason = {r.reason}
      设 un = 列表加项 {un} {u}
    否则
      设 i.module = {x.module}
      设 i.issue = {r.result.issue 或}
      设 i.basis = {r.result.basis 或}
      设 own = {r.result.owner 或}
      设 foreign = 否
      如果 {sc} 不为空
        如果 {own} 不为空
          如果 {own} 不包含 {x.module}
            如果 {sc} 不包含 |{own}|
              设 foreign = 是
            结束
          结束
        结束
      结束
      如果 {foreign} 等于 是
        设 k.module = {x.module}
        设 k.owner = {own}
        设 k.kind = {r.result.result}
        设 k.issue = {i.issue}
        设 k.basis = {i.basis}
        设 k.reason = 问题出在范围外的模块，本次不处理
        设 sk = 列表加项 {sk} {k}
      否则如果 {r.result.result} 等于 contract_issue
        设 con = 列表加项 {con} {i}
      否则如果 {r.result.result} 等于 module_issue
        设 mod = 列表加项 {mod} {i}
      结束
    结束
  结束
结束
遍历 it 于 {b.items}
  设 inscope = 是
  如果 {sc} 不为空
    如果 {sc} 不包含 |{it.modules}|
      设 inscope = 否
    结束
  结束
  如果 {inscope} 等于 是
    设 g.module = {it.modules}
    设 g.issue = {it.issue}
    设 g.basis = {it.basis}
    设 mod = 列表加项 {mod} {g}
  否则
    设 k2.module = {it.modules}
    设 k2.owner = {it.modules}
    设 k2.kind = regression
    设 k2.issue = {it.issue}
    设 k2.basis = {it.basis}
    设 k2.reason = 模块在范围外，没有审，本次不处理
    设 sk = 列表加项 {sk} {k2}
  结束
结束
设 w.file = plan/audit2.json
设 w.content.result = ok
如果 {sc} 不为空
  设 w.content.scope = {modules}
结束
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
设 ncw = 列表长度 {cw}
如果 {ncw} 大于 0
  设 w.content.contract_warnings = {cw}
结束
设 ns = 列表长度 {sk}
如果 {ns} 大于 0
  设 w.content.skipped_issues = {sk}
结束
设 s = 写文件 {w}
返回 {w.content}
