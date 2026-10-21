# 修改：读问题清单 → 写修改计划（调模型，自己存 plan/changes/<序号>.zs）→ 检查修改计划（程序，问题清单/需求从
# ctx 取，跟这里读的是同一份）→ 不过带问题重写，最多 次数 次 → 执行 这份计划（真的用 执行 把它当 DSL 脚本跑：
# 改需求/新增模块/删除模块/改约定/改文件 边跑边改，固定末行 落实修改：改过文件的模块先验收；再按依赖分层写/重写约定、同步顶层依赖，
# 然后只对「约定内容真的变了」的模块刷新骨架并按依赖分层 改模块（修改式重做：带修改说明 + 新旧约定差异，验收含查未受影响用例），
# 约定没变的模块一律不重做）。然后收尾：全量回归 + 接口冒烟（方式=修改：失败项只对所属模块调 改模块，带失败原文，最多 2 轮，仍不过 终止 失败；
# 冒烟完整结果存 out/smoke_<轮>.json 与 .txt 摘要，返回带路径）。不再生成分配、不跑 plan/build.zs。
# 计划里只有 改文件（和验收）时（检查修改计划 的 only_files）：落实修改 已对改过文件的模块验收（不过就恢复文件并失败），
# 返回改了哪些文件。执行失败时先 恢复改动 再终止。
# 顶层脚本的入参名用英文（动词的入参名仍是中文；取值 最新/成功 等仍是中文）。model 是引擎关键字别名，不能当变量名，所以叫 llm。
# 参数：req issues=latest task? llm=sonnet retries=3（issues 认 latest 也认 最新）
用包 dslproj v3
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
  设 back = 恢复改动
  终止 {r.status} 执行修改计划失败（{r.at}）：{r.reason}
结束
设 g = 全量回归 方式=修改
设 sm = 接口冒烟 方式=修改
如果 {c.only_files} 等于 是
  终止 成功 只改了文件：{c.files}；全量回归 {g.status}，接口冒烟 {sm.status}，结果 {sm.files}
结束
终止 成功 修改完成（约定没变的模块没有重做）；全量回归 {g.status}，接口冒烟 {sm.status}，结果 {sm.files}
