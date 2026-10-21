# 修改：读问题清单 → 写修改计划（调模型，自己存 plan/changes/<序号>.zs）→ 检查修改计划（程序，问题清单/需求从
# ctx 取，跟这里读的是同一份）→ 不过带问题重写，最多 次数 次 → 执行 这份计划（真的用 执行 把它当 DSL 脚本跑：
# 改需求/新增模块/删除模块/改约定 四个动词边跑边改，固定末行 落实修改 按依赖分层写/重写约定并同步顶层依赖）→
# 生成骨架 → 生成分配 → 执行 plan/build.zs，返回 build 的状态/原因。
# 顶层脚本参数用中文（语法层，跟动词参数名一样，tests/dsl/test_naming.py 对声明过的顶层参数名放行）。
# 参数：需求 问题=最新 任务? 模型=sonnet 次数=3
用包 v3
设 iss = 读问题清单 {问题}
设 n = 0
设 passed = 否
设 problems =
设 summary =
当 {passed} 不等于 是 最多 {次数} 次
  设 n = 计算 {n} + 1
  设 plan = 写修改计划 问题={iss.items} 需求={需求} 任务={任务} 上次问题={problems} 模型={模型}
  设 c = 检查修改计划 {plan}
  如果 {c.ok} 等于 是
    设 passed = 是
  否则
    设 problems = {c.problems}
    设 summary = {c.summary}
  结束
结束
如果 {passed} 不等于 是
  终止 失败 修改计划写了 {n} 次都没通过检查：{summary}
结束
设 r = 执行 {plan} 需求={需求}
如果 {r.status 或 成功} 不等于 成功
  终止 {r.status} 执行修改计划失败（{r.at}）：{r.reason}
结束
生成骨架
生成分配
设 b = 执行 plan/build.zs
终止 {b.status} {b.reason}
