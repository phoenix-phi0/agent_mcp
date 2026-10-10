"""dslagent：用中文 DSL 修「有失败测试的 bug」、做「测试全过、产物明确」的小任务——cbatch 的 engine="dsl" / "auto" 走这里。

把 /tmp/dslagent 的 plan6/plan7 实验（P6 臂）搬成生产路径，只留：
  pool.py      常驻 claude 进程池（stream-json，每次调用后 /clear），单次调用省 ≈3 秒
  template.py  第 1 版固定模板：从任务描述 / 测试摘要里按规则抽关键词和预读段落，不调模型规划
  infer.py     推理候选：ast 事实 + 小 Datalog + 打分，前 8 段并进模板预读（≤675 行；出错/超时回退；DSLAGENT_INFER=0 关）
  prompts.py   规划提示（修 bug 模板没修好时 / 任务路径；不变的大段在系统提示里，跨调用读缓存）
  plan.py      计划检查：去说明文字、白名单、补末尾「结束」、假模型空跑
  engine.py    AgentEngine（DSLEngine 子类）：系统子脚本映射、语句白名单、子脚本调用记录
  runner.py    执行器：开局有失败 → 模板 → 规划（≤2 版）；全过 → 任务路径（模型规划 ≤2 版）；→ 交回（没成时附交接说明，
               cbatch 决定要不要 claude 兜底）；auto 判定
  v2.py        规划路径 v2 的核心（DSLAGENT_PLANNER=v2 时 runner.run 转过去，与任务类型无关）：资料包 → 补查 → 一次规划 .zs
               → 引擎执行（计划内的 跑测试 只在影响走向时真跑）→ 验收 → 补改 1 次 → 边界复核；模型调用 / 保险 / 重试 / 记录 / 预算
  packs/       资料包（DSLAGENT_PACK，缺省 code）：collect / extra / 补查提示 / 规划说明；code = 候选模块、引用行、登记处、测试断言
  verify/      验收（DSLAGENT_VERIFY，缺省跟随 PACK）：check / fix / boundary；code = 全量测试、清单、旧写法残留、边界复核
  snap.py      项目快照（snapshot / changed / diff_text / restore），核心和验收共用
  v2pack.py    旧路径兼容，转发到 packs/code.py
  lib/         定位.zs、读改测.zs 两个系统子脚本
  verbs/       私有动词根：code 包（读、搜、改、写/删文件、改模块名、跑测试、运行看看），common/text 转发到仓库 verbs/，不污染全局动词

命令行（cbatch 起的就是这个，独立进程）：
    python -m tools.dslagent run --project DIR --task-file F --out DIR [--test-cmd CMD] [--max-plan 2]
    python -m tools.dslagent auto --project DIR --task-file F [--test-cmd CMD]

修 bug 路径在 shopkit N1–N10 上验证过；任务路径在 plan8 S1–S8、blind_V V5–V10 上验证过。
能力限于 code 动词包：读/搜文件、精确替换改文件、写/删非测试文件、改模块名、跑测试、跑 ≤30 行只读 Python；
开放式任务、需要动词表外能力（装依赖、跑别的命令、联网）的仍应交 claude。
"""
