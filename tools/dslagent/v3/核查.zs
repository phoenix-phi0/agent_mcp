# 核查：新建完成之后（或任何时候）找问题。程序检查是一个个动词，需要判断的地方直接派子任务，结果合并存成问题清单：
#   程序检查  全局检查（重复接口 / 重复表 / 依赖与顶层不一致）、全量回归 方式=核查、接口冒烟 方式=核查（有代码才跑，只报告不重做）
#   规划层    派一个子任务：读需求 / top.zs / 接口目录，找职责重复、模块间缺口、跨模块调用对不上、偏离需求（不读代码）
#   deep=是   再对每个有代码的模块派一个读代码的子任务（核查任务表 + 并行派任务）：约定、代码、需求对一遍
#   logic_check=是  另对全部约定并行跑角色 logic_check，疑点并入清单
# 存问题清单 只信成功的子任务：失败的记进 unchecked（不能当作没问题），回复前后矛盾 / 缺字段的条目丢进 dropped。
# 没有 plan/top.zs 时也能跑：全局检查 0 条，回归 / 冒烟跳过，规划层照派，deep 无效。
# 顶层脚本的入参名用英文（动词的入参名仍是中文；取值 是/否 仍是中文）。model 是引擎关键字别名，不能当变量名，所以叫 llm。
# req 是需求全文，req_file 是需求文件路径（有就读文件，没有用 req）。
# 参数：req req_file? task? llm=sonnet deep=否 logic_check=否
用包 common v3
模型 {llm}
设 a = 全局检查
设 b = 全量回归 方式=核查
设 c = 接口冒烟 方式=核查
设 text = 取文件 {req_file}
如果 {text} 为空
  设 text = {req}
结束
设 topt = 取文件 plan/top.zs
设 cat = 取文件 plan/catalog.md
设 pdesc = 取文件 @audit.md
设 plogic = 取文件 @audit_logic.md
设 inp.需求 = {text}
设 inp.任务 = {task 或 无}
设 inp.顶层规划 = {topt 或 还没有}
设 inp.接口目录 = {cat 或 还没有}
设 inp.程序检查 = {a.summary}
设 inp.全量回归 = {b.summary}
设 inp.接口冒烟 = {c.summary}
设 p = 派任务 {pdesc} {inp} {plogic} found:是否,items:列表
设 m =
设 mods =
如果 {deep} 等于 是
  设 mods = 列出模块 有代码=是
  如果 {mods} 不为空
    设 known.program = {a}
    设 known.regress = {b}
    设 known.smoke = {c}
    设 jobs = 核查任务表 {mods} {task} 已知问题={known}
    设 m = 并行派任务 {jobs}
  结束
结束
设 e =
如果 {logic_check} 等于 是
  设 e = 逻辑核查
结束
设 s = 存问题清单 程序={a} 回归={b} 冒烟={c} 规划={p} 模块={m} 模块名={mods} 疑点={e}
返回 {"count": {s.count}, "path": "{s.path}", "unchecked": {s.unchecked}, "dropped": {s.dropped}}
