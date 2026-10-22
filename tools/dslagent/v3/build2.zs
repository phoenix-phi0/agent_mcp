# 新建2（最小主干，刻意不含接口冒烟）：顶层 → 约定 → 同步顶层依赖 → 骨架 → 分配 → 按层做模块 → 全量回归 → 结束。
# 和 v3.zs 的区别：不做规划层核查，不跑接口冒烟；全量回归只检查，不过的模块交 plan/redo_failed.zs 按依赖分层重做，最多 2 轮，仍不过 终止 失败。
# 生成分配 照旧写 plan/build.zs（本脚本不执行它）和 plan/redo_failed.zs（本脚本要用）；按层做模块直接写在这里。只用现有动词。
# 参数：req project stop_after? skip?（skip：逗号隔开的模块名，直接当作跳过，依赖它们的模块也跳过）
用包 common v3 text
预算 调用 120 秒 36000
规划到通过 顶层 需求={req} 停在={stop_after}
规划到通过 约定 需求={req} 停在={stop_after}
同步顶层依赖
生成骨架
生成分配
如果 {stop_after 或} 等于 build
  终止 成功 停在分配脚本
结束
设 layers = 依赖分层
设 top_text = 已有规划 顶层
设 bad = |
设 skip_text = {skip 或}
设 skipped_list = 按正则切分 {skip_text} [,，、\s]+
设 done_text = 
设 failed_text = 
设 skipped_text = 
设 n_bad = 0
# 按层做模块：一个模块失败 / 被跳过，只拦住直接或间接依赖它的模块（bad 里记着失败 / 跳过的模块名），其余照常做；同层可做的模块并行（做模块任务表 + 并行执行，和 做模块组 一致）
遍历 group 于 {layers}
  设 mods = 按正则切分 {group} [,，、\s]+
  设 ready = 
  遍历 m 于 {mods}
    设 why = 
    遍历 sk 于 {skipped_list}
      如果 {sk} 等于 {m}
        设 why = 按skip参数跳过
      结束
    结束
    设 dm = 匹配 {top_text} (?m)^模块\s+{m}(?![A-Za-z0-9_])(?:\s+依赖\s+([^#]*?))?(?:\s+提供\s+[^#]*?)?\s*(?:#.*)?$
    设 deps = 按正则切分 {dm.groups.0} [,，、\s]+
    遍历 d 于 {deps}
      如果 {why} 为空 且 {d} 不为空 且 {bad} 包含 |{d}|
        设 why = 因依赖{d}失败或被跳过而跳过
      结束
    结束
    如果 {why} 不为空
      设 bad = {bad}{m}|
      设 n_bad = 计算 {n_bad} + 1
      设 skipped_text = {skipped_text}{m}：{why}；
    否则
      设 isdone = 已完成 {m}
      如果 {isdone} 等于 是
        设 done_text = {done_text}{m}（已完成）、
      否则
        设 ready = {ready},{m}
      结束
    结束
  结束
  设 jobs = 做模块任务表 {ready} 3 opus
  设 rs = 并行执行 {jobs} 并发=3
  遍历 r 于 {rs}
    如果 {r.status} 等于 成功
      设 done_text = {done_text}{r.params.模块}、
    结束
    如果 {r.status} 等于 超出预期
      终止 超出预期 {r.params.模块}：{r.reason}；已完成：{done_text}
    结束
    如果 {r.status} 不等于 成功 且 {r.status} 不等于 超出预期
      设 short = 截取 {r.reason} 1 400
      设 bad = {bad}{r.params.模块}|
      设 n_bad = 计算 {n_bad} + 1
      设 failed_text = {failed_text}{r.params.模块}：{short}；
    结束
  结束
结束
如果 {n_bad} 大于 0
  终止 失败 有模块没做成，不跑全量回归。失败的模块：{failed_text}被跳过的模块：{skipped_text}已完成的模块：{done_text}
结束
设 rs = 全量回归
如果 {rs.count} 大于 0
  设 r = 执行 plan/redo_failed check=全量回归 failed={rs.failed} layers={layers}
  如果 {r.status} 不等于 通过
    终止 {r.status} {r.reason}
  结束
  设 rs = 全量回归
  如果 {rs.count} 大于 0
    终止 失败 全量回归两轮仍未通过：{rs.failed_text}
  结束
结束
终止 成功 全部模块完成
