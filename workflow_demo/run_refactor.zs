# 代码重构：对 work/{project} 里已有的项目做重构（行为不变）。先把要重构的项目复制成新目录再跑，
# 原项目留着做对照。QA 建议启动时换成 QA_GPT：roles={"QA_ENGINEER": "QA_GPT"}
用包 workflow
设 goal = 降低重复和单个文件的体量，让鉴权、参数校验、写流水这些重复逻辑各自只有一处；不改任何行为
设 stack = Python3+pytest，存储用sqlite
设 project = wallet_refactor1
设 test_content = 钱包服务重构后行为不变
设 test_cmd = .venv/bin/python -m pytest -p no:cacheprovider -q
设 budget = 12
设 roles = ENGINEER_LITE,ENGINEER_GPT_LITE,ENGINEER_GPT,ENGINEER,ENGINEER_GPT_SENIOR,ENGINEER_SENIOR,TEST_ENGINEER
编排执行 refactor_workflow.wf
打印 {workflow_trace}
