# 新建2（最小主干，刻意不含接口冒烟）：顶层 → 约定 → 同步顶层依赖 → 骨架 → 分配 → 按层做模块 → 全量回归 → 结束。
# 和 v3.zs 的区别：不做规划层核查，不跑接口冒烟；全量回归只检查，不过的模块交 plan/redo_failed.zs 按依赖分层重做，最多 2 轮，仍不过 终止 失败。
# 生成分配 照旧写 plan/build.zs（本脚本不执行它）和 plan/redo_failed.zs（本脚本要用）；按层做模块直接写在这里。只用现有动词。
# 参数：req project stop_after?
用包 v3
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
遍历 组 于 {layers}
  做模块组 {组}
结束
设 rs = 全量回归
如果 {rs.count} 大于 0
  设 r = 执行 plan/redo_failed 检查=全量回归 failed={rs.failed} layers={layers}
  如果 {r.status} 不等于 通过
    终止 {r.status} {r.reason}
  结束
  设 rs = 全量回归
  如果 {rs.count} 大于 0
    终止 失败 全量回归两轮仍未通过：{rs.failed_text}
  结束
结束
终止 成功 全部模块完成
