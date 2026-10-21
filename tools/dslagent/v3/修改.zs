# 修改：读问题清单 → 写修改计划（调模型，自己存 plan/changes/<序号>.zs）→ 检查修改计划（程序，问题清单用这里读到的 items、需求从
# ctx 取）→ 不过带问题重写，最多 次数 次 → 执行 这份计划（真的用 执行 把它当 DSL 脚本跑：
# 改需求/新增模块/删除模块/改约定 四个动词边跑边改，固定末行 落实修改 按依赖分层写/重写约定并同步顶层依赖）→
# 生成骨架 → 生成分配 → 执行 plan/build.zs，返回 build 的状态/原因。
# 顶层脚本的入参名用英文（动词的入参名仍是中文；取值 最新/成功 等仍是中文）。model 是引擎关键字别名，不能当变量名，所以叫 llm。
# 参数：req issues=latest task? llm=sonnet retries=3（issues 认 latest 也认 最新）
用包 v3
设 iss = 读问题清单 {issues}
设 n = 0
设 passed = 否
设 problems =
设 summary =
当 {passed} 不等于 是 最多 {retries} 次
  设 n = 计算 {n} + 1
  设 plan = 写修改计划 问题={iss.items} 需求={req} 任务={task} 上次问题={problems} 模型={llm}
  设 c = 检查修改计划 {plan} 问题={iss.items}
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
设 r = 执行 {plan} req={req}
如果 {r.status 或 成功} 不等于 成功
  终止 {r.status} 执行修改计划失败（{r.at}）：{r.reason}
结束
生成骨架
生成分配
设 b = 执行 plan/build.zs
终止 {b.status} {b.reason}
