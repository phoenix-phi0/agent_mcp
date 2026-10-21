# v3 流程：顶层规划 → 约定 → 同步顶层依赖 → 骨架 → 分配 → 按层做模块。流程在这里，套路封装在 v3 动词包（tools/dslagent/verbs/v3）
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
设 r = 执行 plan/build.zs
终止 {r.status} {r.reason}
