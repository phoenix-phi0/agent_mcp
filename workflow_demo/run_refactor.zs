# 代码重构：对 work/{project} 里已有的项目做重构（行为不变）。先把要重构的项目复制成新目录再跑，
# 原项目留着做对照。QA 建议启动时换成 QA_GPT：roles={"QA_ENGINEER": "QA_GPT"}
# 参数：goal? project?
# 上面这些参数启动时可以用 vars 传（会议室「交给流程」就是这么传的）；不传就用下面「或」后面的默认值。
用包 workflow
设 goal = {goal 或 降低重复和单个文件的体量，让鉴权、参数校验、写流水这些重复逻辑各自只有一处；不改任何行为}
设 stack = Python3+pytest，存储用sqlite
设 project = {project 或 wallet_refactor1}
设 test_content = 钱包服务重构后行为不变
设 test_cmd = .venv/bin/python -m pytest -p no:cacheprovider -q
设 budget = 12
设 roles = ENGINEER_LITE,ENGINEER_GPT_LITE,ENGINEER_GPT,ENGINEER,ENGINEER_GPT_SENIOR,ENGINEER_SENIOR,TEST_ENGINEER
# 项目已有接口约定（整项目流程、改项目流程写的）就读进来，重构完按新代码更新；没有就是空对象，流程里整理一份
设 contract = 读约定 work/{project}/CONTRACT.json
编排执行 refactor_workflow.wf
# 写回约定：架构师的裁决沿用原约定的（重构不产生新裁决）
存约定 work/{project}/CONTRACT.json arch contract.contract_notes 重构流程
打印 {workflow_trace}
