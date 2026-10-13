"""dslagent：用中文 DSL 修「有失败测试的 bug」、做「测试全过、产物明确」的小任务——cbatch 的 engine="dsl" / "auto" 走这里。

两条路径，runner.run 按 DSLAGENT_PLANNER 选：
  v2（cbatch 现在的用法）：文件大纲 → 模型读代码规划 .zs → 引擎执行 → 验收 → 补改 → 边界复核。
  旧路径（planner≠v2，保留、隔离在 legacy/）：固定模板 → 模型规划 → 交回兜底。v2 不 import legacy/。

文件职责（tools/dslagent/）：
  __main__.py   命令行入口：run → runner.run；auto → auto.decide_auto
  runner.py     入口 run()：planner=v2 → v2.run，否则 legacy/run.py；并把 common / auto 的公共名字 import 进来（旧写法 runner.xxx 仍可用）
  common.py     公共：目录（tmp_dir）、测试命令探测（detect_test_cmd）、动词模块加载（_verb_module）、claude 子进程环境（child_env）
  auto.py       engine=auto 的判定：decide_auto、capability_gaps、test_state（cbatch 用）
  agents.py     各 agent（plan / plan_fix / sub / sub_tool / fix / bound / bfix）的定义：从 agents/*.md 读步骤、工具、轮数、回复格式、system；user 拼装、解析、重试在代码里
  guard.py      模型调用保险的常量和原因（超时 / 空闲 / 超长 / invoke 拦截 / 禁工具…），四个引擎和 Model 共用
  engines.py    按步骤选模型（parse / validate / step_of）、_Proc 进程保险、call_claude / call_codex / call_grok / call_opencode
  v2.py         v2 核心：Model（唯一模型入口：计数 / 墙钟 / 记账 / 重试）、Client、规划（plan_read_call）、V2Engine、计划检查、run、记录
  verify/       验收（DSLAGENT_VERIFY，缺省跟随 PACK）：check / fix / boundary；code = 全量测试、清单、旧写法残留、边界复核
  packs/        资料包（DSLAGENT_PACK，缺省 code）：plan_outline（文件大纲）、规划说明、计划专属检查
  v2pack.py     旧名兼容，转发到 packs/code.py
  engine.py     AgentEngine（DSLEngine 子类）：子脚本映射、语句白名单、子任务 tool 模式入口、写类动词前的开局快照
  toolsub.py    子任务 tool 模式（dsl_options.subtask=tool）：2 次尝试、快照恢复、退回 json
  dslmcp.py     stdio MCP：单个 dsl 工具（可写 / --readonly），日志落 toollogs/
  dslcheck.py   tool / 只读工具的白名单检查、空跑、edit_problems、子任务方式（env_mode / check_mode）
  plan.py       计划检查：strip_prose / autoclose / split_subs / whitelist_check、假模型 dry_run、write_subs
  prompts.py    共用的提示：CHEAT / VERBS / TIPS / SEE / fix_prompt（文本在 agents/shared/ 和 agents/plan_fix.md，见 agents/README.md）
  promptfile.py 提示词文件加载器（agents/*.md：frontmatter、插入、变体；旧路径 prompts/legacy/）
  agents/       一个 agent 一个 Markdown（system 提示词 + 说明），见 agents/README.md
  snap.py       项目快照（snapshot / changed / diff_text / restore），核心和验收共用
  reason.py     逻辑规则：规则求值 infer、规则 3 安全约束 check（写 / 删文件前）、开局快照 setup、done_items
  datalog.py    小 Datalog 求值器（reason 和 legacy/infer 共用）
  rules/        安全.dl
  lib/          示例_分支规划.zs（规划 system 的末尾示例）
  verbs/        私有动词根：code 包（读、搜、改、写 / 删文件、改模块名、跑测试、运行看看），common / text 转发仓库 verbs/
  legacy/       旧路径：run.py（执行器）、template.py、infer.py、pool.py、engine.py（LegacyEngine）、prompts.py、
                reason_rules.py（测试变化 / 完成核对检查 / 退回规划前回滚）、lib/（定位.zs、读改测.zs）、rules/（测试变化.dl、完成核对.dl）

命令行（cbatch 起的就是这个，独立进程）：
    python -m tools.dslagent run --project DIR --task-file F --out DIR [--test-cmd CMD] [--max-plan 2]
    python -m tools.dslagent auto --project DIR --task-file F [--test-cmd CMD]

修 bug 路径在 shopkit N1–N10 上验证过；任务路径在 plan8 S1–S8、blind_V V5–V10 上验证过。
能力限于 code 动词包：读/搜文件、精确替换改文件、写/删非测试文件、改模块名、跑测试、跑 ≤30 行只读 Python；
开放式任务、需要动词表外能力（装依赖、跑别的命令、联网）的仍应交 claude。
"""
