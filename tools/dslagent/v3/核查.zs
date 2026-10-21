# 核查：新建完成之后（或任何时候）只查代码。程序检查用动词（全局检查 / 全量回归 / 接口冒烟，有代码才跑、只报告不重做），
# 再加一段模型核查：对每个有代码的模块 派任务（入参 = contracts/<m>.md + 该模块代码文件，全量回归 返回的 code_modules 里给好的，超 400 行的文件按「文件:起-止」切段），
# 找代码与约定不符、约定写了没实现、实现了约定没写；同时把「看起来是约定本身的问题」（约定前后矛盾、跨模块对不上等）单独列在 contract_items。
# 约定是做模块的依据，约定层的问题必须回规划阶段解决，不交给修改：
#   代码问题（程序 / 回归 / 冒烟 / 模型核查的 items）→ 存问题清单 → plan/issues/<序号>.md，交给 修改.zs；
#   约定层问题（contract_items）→ 写文件 单独存成 plan/contract_issues.md（每次核查整份覆盖），不进问题清单，返回里标明「需回到规划」。
# 规划层核查（需求 / top.zs / 各模块约定）已经挪到规划阶段（规划到通过 规划核查，建模块之前跑），这里不再派规划层任务。
# 存问题清单 只信成功的子任务：某个模块的代码核查失败的记进 unchecked（不能当作没问题）；缺字段的条目丢进 dropped。
# 没有 plan/top.zs / 没有代码时也能跑：全局检查 0 条，回归 / 冒烟跳过，没有模块核查。
# 顶层脚本的入参名用英文；model 是引擎关键字别名，不能当变量名，所以叫 llm。req 保留给 CLI，这里用不上。
# 参数：req task? llm=sonnet
用包 common v3 text code
模型 {llm}
设 a = 全局检查
设 b = 全量回归
设 c = 接口冒烟
设 desc = 代码核查：对照这个模块的约定（contracts/<模块>.md）和它的代码文件（entities / services / routes / queries），找：代码与约定不符、约定写了没实现、实现了约定没写；只读不改。另外，如果你觉得问题出在约定本身（约定前后矛盾、跨模块对不上、引用了不存在的模块或函数等），不要放进 items，单独放进 contract_items。
设 logic = 回复中items和contract_items的每一项必须是对象，字段：issue（问题描述）、modules（涉及模块名，逗号隔开）、basis（依据：文件和位置）；没有就填空列表，found 在 items 非空时填 是、否则填 否。文件很长时按段给你（文件:起-止），读不到的部分不要猜。
设 code_items = 解析JSON []
设 contract_items = 解析JSON []
设 unchecked = 解析JSON []
遍历 x 于 {b.code_modules}
  设 r = 派任务 {desc} {x.files} {logic} found:是否,items:列表,contract_items:列表
  如果 {r.status} 等于 成功
    遍历 it 于 {r.result.items}
      设 code_items = 列表加项 {code_items} {it}
    结束
    遍历 ci 于 {r.result.contract_items}
      设 contract_items = 列表加项 {contract_items} {ci}
    结束
  否则
    设 u.module = {x.module}
    设 u.reason = {r.reason}
    设 unchecked = 列表加项 {unchecked} {u}
  结束
结束
设 n = 列表长度 {code_items}
设 found = 否
如果 {n} 大于 0
  设 found = 是
结束
设 pl.status = 成功
设 pl.result.found = {found}
设 pl.result.items = {code_items}
设 s = 存问题清单 程序={a} 回归={b} 冒烟={c} 规划={pl}
设 cn = 列表长度 {contract_items}
设 cf.file = plan/contract_issues.json
设 cf.content.note = 约定层问题：需回到规划阶段解决，不交给修改（修改.zs 只改代码）
设 cf.content.count = {cn}
设 cf.content.items = {contract_items}
设 w = 写文件 {cf}
如果 {w.ok} 不等于 是
  终止 失败 约定层问题没存下来：{w.msg}
结束
返回 {"count": {s.count}, "path": "{s.path}", "unchecked": {unchecked}, "dropped": {s.dropped}, "contract_count": {cn}, "contract_path": "plan/contract_issues.json", "contract_note": "约定层问题，需回到规划，没有并入问题清单"}
