"""dslagent v3：一个 .zs 流程脚本（v3.zs）+ v3 动词包（verbs/v3），搭在通用 v2（dslproj 资料包）上，从一份需求做出一个 DSL 项目。

    python -m tools.dslagent v3 --req F --project DIR --out DIR [--stop-after top|contract|build] [--cost-cap USD]

流程（v3.zs）：规划到通过 顶层 → 规划到通过 约定 → 生成骨架 → 生成分配 → 执行 plan/build.zs（做模块组 … → 全量回归 → 接口冒烟）。
流程在 .zs 里，套路封装成带默认值的动词，Python 只做确定性的事和调模型。
  顶层  plan/top.zs               项目 名 / 模块 名 [依赖 …]（top.py：解析、检查、依赖分层）
  约定  contracts/<模块>.md        dslproj 的约定格式；按依赖分层，同层并行写；检查 = dslproj 约定检查 + 与 top 一致 + 表名前缀（contracts.py）；
                                  全部约定过后 全局检查：同一「方法+路径」或同一张表在两个模块都定义，带问题逼相关模块重写，最多 2 轮（globalcheck.py）
  目录  plan/catalog.md           程序生成的接口目录：每个已有约定的模块一节（说明 / 依赖 / 表 / 公开函数 / 接口）；约定通过 / 重写 /
                                  删除模块 / 同步顶层依赖时自动刷新，内容没变不重写（catalog.py）；写约定时非直接依赖的模块只给目录里的一行概要，
                                  复核约定、写顶层 / 做模块 / 补改把它当只读参考带上
  骨架  entities / services / routes   从冻结的约定生成，已有的不覆盖，生成后加载检查必须过（scaffold.py）
  分配  plan/build.zs             从 top 按依赖分层生成，一层一行 做模块组，末尾加 全量回归 + 接口冒烟（scaffold.py）
  做模块组                          组内模块并行；每个模块：已完成跳过 → 最多 N 次（做模块 → 验收），末次换模型；有模块 N 次不过，等组内其他模块结束后 终止 失败
  全量回归                          所有模块（含已完成的）重新跑一次验收；不过的标未完成、按依赖分层交 做一个模块 重做（带上回归原因），最多 2 轮，仍不过 终止 失败
  接口冒烟                          真起 tools.dsl_http 的 Router（Flask 测试客户端），每个接口取第一条正常用例，同一份数据上核对「直接调用」和「走 HTTP」是否一致；不过的模块同回归规则重做

  修改  修改.zs                   落实修改 只对「约定文本真的变了」的模块刷新骨架并按依赖分层 改模块（修改式重做，不走 build.zs、不整模块新建）；约定没变的上下游不重做

文件职责（tools/dslagent/v3/）：
  core.py       Ctx（运行上下文：项目、记录、Model、花费上限、plan/state.json）、V3Engine、run()（__main__ 的 v3 子命令）
  planning.py   写 / 检查 / 存 规划（提示词 prompts/top.md、contract.md；输入拼装；走 v2 的 Model）
  top.py        顶层规划的解析 / 检查 / 依赖分层
  contracts.py  约定检查（dslproj + v3 另加的）
  catalog.py    plan/catalog.md 的生成 / 刷新（程序生成，不调模型）
  globalcheck.py 全局程序检查：跨模块的「方法+路径」/ 表名重复
  scaffold.py   生成骨架 / 生成分配
  modrun.py     做模块：起子进程跑 v2（--pack dslproj），在项目拷贝里做，范围内文件拷回
  regress.py    全量回归 / 接口冒烟 的实现（两步共用按依赖分层重做的循环）
  modify.py     修改式重做（M2）：plan/changes/<序号>.json 旧约定与用例基线、新旧约定差异、改模块 的任务文本、未受影响用例检查
  v3.zs         流程脚本

续跑规则：断了重跑同一命令。已存在且检查通过的规划（top / 约定）不重写；骨架已有的文件不覆盖；build.zs 每次按 top 重新生成；
模块在 plan/state.json 记了通过且约定 hash 没变才跳过，约定改了就重做；做模块在上一轮留下的文件上接着改。
记录（--out）：result.json（状态、花费、用时、各步记录）、v3_log.jsonl（每次写 / 检查 / 做模块 / 验收一行）、steps/（每次写出的规划原文）、
calls/（v2 Model 逐次调用）、modules/<模块>/r<轮>/（任务、子进程输出、v2 记录目录 v2/、做模块用的项目拷贝 proj/）。
"""
