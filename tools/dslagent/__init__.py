"""dslagent：用中文 DSL 修「有失败测试的 bug」——cbatch 的 engine="dsl" / "auto" 走这里。

把 /tmp/dslagent 的 plan6/plan7 实验（P6 臂）搬成生产路径，只留：
  pool.py      常驻 claude 进程池（stream-json，每次调用后 /clear），单次调用省 ≈3 秒
  template.py  第 1 版固定模板：从任务描述 / 测试摘要里按规则抽关键词和预读段落，不调模型规划
  prompts.py   模板没修好时的规划提示（不变的大段在系统提示里，跨调用读缓存）
  plan.py      计划检查：去说明文字、白名单、补末尾「结束」、假模型空跑
  engine.py    AgentEngine（DSLEngine 子类）：系统子脚本映射、语句白名单、子脚本调用记录
  runner.py    执行器：模板 → 规划（≤2 版）→ 交回（没修好时附交接说明，cbatch 决定要不要 claude 兜底）；auto 判定
  lib/         定位.zs、读改测.zs 两个系统子脚本
  verbs/       私有动词根：code 包（读、搜、改、跑测试、运行看看），common/text 转发到仓库 verbs/，不污染全局动词

命令行（cbatch 起的就是这个，独立进程）：
    python -m tools.dslagent run --project DIR --task-file F --out DIR [--test-cmd CMD] [--max-plan 2]
    python -m tools.dslagent auto --project DIR --task-file F [--test-cmd CMD]

只在「项目有测试、任务是让失败的测试通过」的修 bug 任务上验证过（shopkit N1–N10）；
能力限于 code 动词包：读/搜 .py、精确替换改文件、跑测试、跑 ≤30 行只读 Python。
"""
