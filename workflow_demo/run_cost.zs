# 按成本分配的流程：和 run_fresh.zs 同样的需求，项目目录换成空的 work/users_cost。
# 实施预算 7：三项全给中档 ENGINEER（cost 3）要 9，会超；架构师得按难度混着挑
用包 workflow
设 content = 实现用户接口
设 stack = Python3+pytest，第三方包写进requirements.txt
设 project = users_cost2
设 test_content = 验证用户接口
设 budget = 7
设 roles = ENGINEER_LITE,ENGINEER,ENGINEER_SENIOR,TEST_ENGINEER
编排执行 cost_workflow.wf
打印 {workflow_trace}
