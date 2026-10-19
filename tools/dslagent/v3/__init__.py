"""dslagent v3：一个 .zs 流程脚本（v3.zs）+ v3 动词包（verbs/v3），搭在通用 v2（dslproj 资料包）上，从一份需求做出一个 DSL 项目。

    python -m tools.dslagent v3 --req F --project DIR --out DIR [--stop-after top|contract|build] [--cost-cap USD]

流程（v3.zs）：规划到通过 顶层 → 规划到通过 约定 → 生成骨架 → 生成分配 → 执行 plan/build.zs（做模块组 …）。流程在 .zs 里，
套路封装成带默认值的动词，Python 只做确定性的事和调模型。
  顶层  plan/top.zs               项目 名 / 模块 名 [依赖 …]（top.py：解析、检查、依赖分层）
  约定  contracts/<模块>.md        dslproj 的约定格式；按依赖分层，同层并行写；检查 = dslproj 约定检查 + 与 top 一致 + 表名前缀（contracts.py）
  骨架  entities / services / routes   从冻结的约定生成，已有的不覆盖，生成后加载检查必须过（scaffold.py）
  分配  plan/build.zs             从 top 按依赖分层生成，一层一行 做模块组（scaffold.py）
  做模块组                          组内模块并行；每个模块：已完成跳过 → 最多 N 次（做模块 → 验收），末次换模型；有模块 N 次不过，等组内其他模块结束后 终止 失败

文件职责（tools/dslagent/v3/）：
  core.py       Ctx（运行上下文：项目、记录、Model、花费上限、plan/state.json）、V3Engine、run()（__main__ 的 v3 子命令）
  planning.py   写 / 检查 / 存 规划（提示词 prompts/top.md、contract.md；输入拼装；走 v2 的 Model）
  top.py        顶层规划的解析 / 检查 / 依赖分层
  contracts.py  约定检查（dslproj + v3 另加的）
  scaffold.py   生成骨架 / 生成分配
  modrun.py     做模块：起子进程跑 v2（--pack dslproj），在项目拷贝里做，范围内文件拷回
  v3.zs         流程脚本

续跑规则：断了重跑同一命令。已存在且检查通过的规划（top / 约定）不重写；骨架已有的文件不覆盖；build.zs 每次按 top 重新生成；
模块在 plan/state.json 记了通过且约定 hash 没变才跳过，约定改了就重做；做模块在上一轮留下的文件上接着改。
记录（--out）：result.json（状态、花费、用时、各步记录）、v3_log.jsonl（每次写 / 检查 / 做模块 / 验收一行）、steps/（每次写出的规划原文）、
calls/（v2 Model 逐次调用）、modules/<模块>/r<轮>/（任务、子进程输出、v2 记录目录 v2/、做模块用的项目拷贝 proj/）。
"""
