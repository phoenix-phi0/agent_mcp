# 修改：读问题清单 → 写修改计划（调模型）→ 检查修改计划（程序）→ 不过带问题重写，最多 次 次 → 存修改计划。
# 范围说明（本次预算未实现，留给后续任务）：计划四种动词（改需求 / 新增模块 / 删除模块 / 改约定）的实际执行
# （改 plan/req.md、改 top.zs、带条目重写约定）、之后的 生成骨架 / 生成分配 / 执行 plan/build.zs 都还没做；
# 这个脚本目前只产出并校验一份通过程序检查的修改计划文件，不执行它。
# 顶层脚本参数用英文（同 v3.zs，test_naming 对 verbs/ 以外的 .zs 要求变量名/脚本参数 ASCII）。
# 参数：req issues=latest task? llm=sonnet retries=3
用包 v3
设 iss = 读问题清单 {issues}
设 n = 0
设 passed = 否
设 problems =
设 summary =
当 {passed} 不等于 是 最多 {retries} 次
  设 n = 计算 {n} + 1
  设 plan = 写修改计划 问题={iss.items} 需求={req} 任务={task} 上次问题={problems} 模型={llm}
  设 c = 检查修改计划 {plan} 问题={iss.items} 需求={req}
  如果 {c.ok} 等于 是
    设 w = 存修改计划 {plan}
    设 passed = 是
  否则
    设 problems = {c.problems}
    设 summary = {c.summary}
  结束
结束
如果 {passed} 不等于 是
  终止 失败 修改计划写了 {n} 次都没通过检查：{summary}
结束
返回 {"status":"ok","retries":{n},"path":"{w}"}
