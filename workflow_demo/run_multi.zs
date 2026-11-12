# 多家模型混用的成本分配：和 run_cost.zs 同样的需求和预算，可用角色里多一个 GPT 工程师（codex）。
# 任务研讨的审查员 ARCHITECT_GLM 是 GLM（goose）；编排进程没有 Z.AI key 时经 batchmgr 调
用包 workflow
设 content = 实现用户接口
设 stack = Python3+pytest，第三方包写进requirements.txt
设 project = users_multi5
设 test_content = 验证用户接口
设 budget = 7
设 roles = ENGINEER_LITE,ENGINEER_GPT_LITE,ENGINEER_GPT,ENGINEER,ENGINEER_GPT_SENIOR,ENGINEER_SENIOR,ENGINEER_FABLE,TEST_ENGINEER
编排执行 cost_workflow.wf
打印 {workflow_trace}
