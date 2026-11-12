# 用重构流程重构 kg_v4 的一个模块。改的是副本 work/kg_v4_refactor（rsync 自 kg_v4，不带 app.db/web/uploads，
# 副本里 git 提交了重构前基线），原项目和真学习记录不动。
# 测试用 data/tmp/kg_copy_test.py 包一层 tests/kg_v4/test_project.py（约定检查 + 17 模块回归 + 编译 117 接口 + 初始化）。
# Claude 工程师卡只允许跑 pytest，跑不了这个测试，所以实施只用 codex 档；启动时
#   roles={"QA_ENGINEER": "QA_GPT", "ENGINEER": "ENGINEER_GPT"}（返工的「代码修改」也走 codex）
用包 workflow
设 goal = 这个项目是kg_v4，中文DSL项目（.zs接口脚本、contracts/约定、plan/top.zs模块清单，写法见README.md）。这次只重构kg模块（上一次分析已按重复行数从20个服务里选定它：services/kg.zs共2121行，重复集中在校验、导入处理、页面组装），只改services/kg.zs，必要时改routes/kg.zs；分析只需细读这两个文件和contracts/kg.md，别的模块不用逐个读；contracts/、plan/、entities/、queries/、ui/、setup/和别的模块一律不改。已知要保留的差异：旧导入入口与「预检→确认」入口的校验规则不完全相同，不能合并成一套。公开函数（contracts/kg.md里列的）的名字、入参、返回和报错原样保留；目标是减少重复、拆过长的函数，不改任何行为
设 stack = 中文DSL（.zs），引擎在仓库根目录/workspace/agent_mcp，测试离线不调模型
设 project = kg_v4_refactor
设 test_content = 这个项目是kg_v4，一个模块重构后行为不变：约定检查、17/17模块回归、117个接口编译、初始化脚本全过，测试汇总「通过12，失败0」
设 test_cmd = /workspace/agent_mcp/.venv/bin/python /workspace/agent_mcp/data/tmp/kg_copy_test.py /workspace/agent_mcp/workflow_demo/work/kg_v4_refactor
设 budget = 10
设 roles = ENGINEER_GPT_LITE,ENGINEER_GPT,ENGINEER_GPT_SENIOR
编排执行 refactor_workflow.wf
打印 {workflow_trace}
