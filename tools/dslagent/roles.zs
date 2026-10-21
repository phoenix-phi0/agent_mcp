# 角色登记表（dslagent 子 agent 管理）。
# 这不是可执行的 DSL 脚本——只是数据，格式仿 DSL 写法（关键字中文、值英文），由 tools/dslagent/roles.py 解析与检查。
# 每个角色一块：「角色 <名>」开头，「结束」收尾。字段：
#   用途          一句话
#   默认模型      模型串（见 tools/dslagent/engines.py parse()：sonnet/opus/haiku、codex:<模型>[:<强度>]、grok[:<强度>]、opencode:<provider/model>、goose[:<模型>[:<强度>]]）
#   回退模型      默认模型调用失败 / 回复不合格时退回的模型串
#   执行方式      可选，模型（缺省：一次模型调用）| v2（起一次完整 v2 运行：python -m tools.dslagent run --pack dslproj …，在项目拷贝里做，
#                 入参要有「模块」，任务文本 = 「模块 <入参.模块>」换行 + 任务；--scope = 可写范围，「本模块路径」展开成该模块的
#                 entities/<m>.entity、services/<m>.zs、routes/<m>*.zs、queries/<m>_*.sql、tests/<m>_*；默认模型设给 v2 的全部步骤，
#                 v2 没跑起来时换回退模型再起一次；验收通过才把范围内的文件拷回项目）
#   工具          无 | 只读 | 读写
#   动词包        工具=只读/读写 时可用的动词包，逗号分隔；没有就留空
#   可读范围      入参里允许出现的材料名，逗号分隔；派代理 的 入参 带了范围外的键就报错（codex 角色尤其要靠这个把关——
#                 codex 的 -s read-only 挡写不挡读，角色只应该看到这里列的材料，不给的东西它读不到）
#   可写范围      允许改动的路径前缀，逗号分隔；没有就「无」
#   单次超时      秒
#   预算          这个角色单次调用的美元上限；「无」= 不限（仍受调度层总预算约束）
#   回复格式      json | zs | text | code
#   提示词文件    tools/dslagent/ 下的相对路径；记文档用的旧步骤（已经有别的调用路径，不经 派代理）可以写说明文字，不是真实文件

角色 plan
  用途: v2 顶层规划 / 规划重写（newproj / modular 的顶层与层次）
  默认模型: sonnet
  回退模型: sonnet
  工具: 只读
  动词包: v3,dslproj
  可读范围: 需求,项目现状
  可写范围: 无
  单次超时: 900
  预算: 无
  回复格式: zs
  提示词文件: agents/plan.md
结束

角色 plan_fix
  用途: 规划检查没过时带问题重写
  默认模型: sonnet
  回退模型: sonnet
  工具: 只读
  动词包: v3,dslproj
  可读范围: 需求,上次规划,问题
  可写范围: 无
  单次超时: 900
  预算: 无
  回复格式: zs
  提示词文件: agents/plan_fix.md
结束

角色 sub
  用途: 普通子任务（问JSON / 派任务 / 并行派任务）
  默认模型: sonnet
  回退模型: sonnet
  工具: 无
  可读范围: 任务,入参
  可写范围: 无
  单次超时: 300
  预算: 无
  回复格式: json
  提示词文件: agents/sub.md
结束

角色 sub_tool
  用途: 带工具的子任务（挂只读 dsl MCP，DSLAGENT_SUBTASK=tool）
  默认模型: sonnet
  回退模型: sonnet
  工具: 只读
  动词包: v3,dslproj
  可读范围: 任务,入参
  可写范围: 无
  单次超时: 300
  预算: 无
  回复格式: json
  提示词文件: agents/sub_tool.md
结束

角色 fix
  用途: 验收补改
  默认模型: sonnet
  回退模型: sonnet
  工具: 无
  可读范围: 原文,失败原因
  可写范围: 无
  单次超时: 600
  预算: 无
  回复格式: code
  提示词文件: verify/code.py: _fix_user
结束

角色 bound
  用途: 边界复核
  默认模型: sonnet
  回退模型: sonnet
  工具: 无
  可读范围: 文件
  可写范围: 无
  单次超时: 600
  预算: 无
  回复格式: code
  提示词文件: agents/bound.md
结束

角色 bfix
  用途: 边界复核的补改
  默认模型: sonnet
  回退模型: sonnet
  工具: 无
  可读范围: 原文,边界问题
  可写范围: 无
  单次超时: 600
  预算: 无
  回复格式: json
  提示词文件: agents/bfix.md
结束

角色 write_top
  用途: v3 写顶层规划
  默认模型: sonnet
  回退模型: sonnet
  工具: 只读
  动词包: v3
  可读范围: 需求,上次顶层
  可写范围: 无
  单次超时: 900
  预算: 无
  回复格式: zs
  提示词文件: v3/prompts/top.md
结束

角色 write_contract
  用途: v3 写约定 / 重写约定
  默认模型: sonnet
  回退模型: sonnet
  工具: 只读
  动词包: v3
  可读范围: 需求,顶层,目录,直接依赖约定,上一版
  可写范围: 无
  单次超时: 900
  预算: 无
  回复格式: text
  提示词文件: v3/prompts/contract.md
结束

角色 review
  用途: v3 约定复核（对照需求再读一次）
  默认模型: sonnet
  回退模型: sonnet
  工具: 无
  可读范围: 需求,顶层,目录,约定
  可写范围: 无
  单次超时: 600
  预算: 无
  回复格式: json
  提示词文件: v3/prompts/review.md
结束

角色 audit
  用途: v3 核查（全局性问题）
  默认模型: sonnet
  回退模型: sonnet
  工具: 无
  可读范围: 需求,任务,顶层,目录,程序检查,上次修改计划
  可写范围: 无
  单次超时: 600
  预算: 无
  回复格式: json
  提示词文件: v3/prompts/audit.md
结束

角色 write_change_plan
  用途: v3 写修改计划
  默认模型: sonnet
  回退模型: sonnet
  工具: 无
  可读范围: 问题清单,需求节选,任务,顶层,目录,涉及模块约定
  可写范围: 无
  单次超时: 900
  预算: 无
  回复格式: zs
  提示词文件: v3/prompts/change_plan.md
结束

角色 build_module
  用途: 做模块（起 v2 子进程跑完整规划/生成/验收）
  默认模型: sonnet
  回退模型: sonnet
  工具: 读写
  动词包: v3,dslproj
  可读范围: 约定,目录,需求
  可写范围: 本模块路径
  单次超时: 1800
  预算: 无
  回复格式: text
  提示词文件: （v2 子进程，另见 agents/ 下各步骤）
结束

角色 modify_module
  用途: 按问题修改一个已有模块（v2）
  执行方式: v2
  默认模型: sonnet
  回退模型: sonnet
  工具: 读写
  动词包: v3,dslproj
  可读范围: 模块
  可写范围: 本模块路径
  单次超时: 1800
  预算: 无
  回复格式: text
  提示词文件: （v2 子进程，另见 agents/ 下各步骤）
结束

角色 logic_check
  用途: 对新写 / 重写的约定找伪代码逻辑漏洞（疑点并入核查问题清单，由修改规划决定采不采纳）
  默认模型: codex:gpt-6-luna:medium
  回退模型: sonnet
  工具: 无
  可读范围: 约定
  可写范围: 无
  单次超时: 300
  预算: 0.5
  回复格式: json
  提示词文件: v3/prompts/logic_check.md
结束

角色 summarize
  用途: 通用助手：把过长原文压缩成要点
  默认模型: codex:gpt-6-luna:low
  回退模型: sonnet
  工具: 无
  可读范围: 原文
  可写范围: 无
  单次超时: 120
  预算: 0.2
  回复格式: text
  提示词文件: v3/prompts/summarize.md
结束

角色 classify
  用途: 通用助手：给原文分类（返回一个标签）
  默认模型: codex:gpt-6-luna:low
  回退模型: sonnet
  工具: 无
  可读范围: 原文,候选标签
  可写范围: 无
  单次超时: 120
  预算: 0.2
  回复格式: json
  提示词文件: v3/prompts/classify.md
结束

角色 extract
  用途: 通用助手：从原文抽取结构化字段
  默认模型: codex:gpt-6-luna:medium
  回退模型: sonnet
  工具: 无
  可读范围: 原文,要抽取的字段
  可写范围: 无
  单次超时: 180
  预算: 0.3
  回复格式: json
  提示词文件: v3/prompts/extract.md
结束

角色 prescreen
  用途: 通用助手：初筛（这份材料值不值得交给主模型细看）
  默认模型: codex:gpt-6-luna:medium
  回退模型: sonnet
  工具: 无
  可读范围: 原文,筛选标准
  可写范围: 无
  单次超时: 180
  预算: 0.3
  回复格式: json
  提示词文件: v3/prompts/prescreen.md
结束
