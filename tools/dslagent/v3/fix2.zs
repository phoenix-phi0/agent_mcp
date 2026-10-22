# 修复2：核查 → 改 → 再核查，最多 rounds 轮。每轮：执行 audit2.zs（同级目录里的脚本）；ok → 终止 成功；contract_issue / unchecked → 终止 失败并说明；
# module_issue → 执行 change2.zs（只做一轮，按模块分组派 modify_module）→ 下一轮。rounds 轮用完仍不是 ok → 终止 失败，带最后一次核查结果。
# 终止信息里带轮数和每轮改了哪些模块。
# 参数：req（保留给 CLI）llm=sonnet rounds=5；syntax 由 run_entry 注入（prompts/project_syntax.md 全文）
用包 common v3 text
设 hist = 解析JSON []
设 n = 0
重复 {rounds} 次
  设 n = 计算 {n} + 1
  设 a = 执行 audit2.zs req={req} llm={llm} syntax={syntax}
  如果 {a.result 或} 等于 ok
    终止 成功 第 {n} 轮核查通过；各轮改动：{hist}
  结束
  如果 {a.result 或} 等于 contract_issue
    终止 失败 第 {n} 轮核查：约定有问题，需回到规划：{a.issues}；各轮改动：{hist}
  结束
  如果 {a.result 或} 等于 unchecked
    终止 失败 第 {n} 轮核查：有模块没核查成：{a.unchecked}；各轮改动：{hist}
  结束
  如果 {a.result 或} 不等于 module_issue
    终止 失败 第 {n} 轮核查没有得出结果：{a.reason 或}；各轮改动：{hist}
  结束
  设 c = 执行 change2.zs req={req}
  设 line = 第{n}轮：改了 {c.changed 或}，没改成 {c.failed 或}
  设 hist = 列表加项 {hist} {line}
结束
终止 失败 {rounds} 轮用完仍有问题（最后一轮改动未再核查）；最后一次核查结果：{a}；各轮改动：{hist}
