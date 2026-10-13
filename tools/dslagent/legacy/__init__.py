"""旧路径（DSLAGENT_PLANNER 不是 v2 时 runner.run 转到这里）：固定模板 → 模型规划 → 交回兜底。

只有 runner.run（planner≠v2）、legacy 自己的测试用它；v2 不 import 这里。
  run.py          执行器（模板 / 规划 / 任务路径 / 完成核对 / 交接说明）
  template.py     第 1 版固定模板：从任务描述 / 测试摘要里按规则抽关键词和预读段落
  infer.py        推理候选：ast 事实 + 小 Datalog（求值器在 ../datalog.py）+ 打分，并进模板预读
  pool.py         常驻 claude 进程池（stream-json，每次调用后 /clear）+ 对冲
  engine.py       LegacyEngine：定位.zs / 读改测.zs 的调用记录、固定系统提示
  prompts.py      规划提示模板（SYSTEM / first_prompt / replan_prompt / task_*）、LIB_SYSTEM
  reason_rules.py 规则 1 测试变化、规则 2 完成核对的检查、退回规划前回滚
  lib/            定位.zs、读改测.zs
  rules/          测试变化.dl、完成核对.dl
"""
