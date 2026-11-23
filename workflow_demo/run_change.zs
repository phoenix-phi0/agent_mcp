# 改项目流程（change_workflow.wf）的示例：给整项目流程做出来的待办网站加截止日期。
# 项目根目录要有接口约定 CONTRACT.json（整项目流程、重构流程、上一次改项目流程跑完都会写；老项目可以从运行记录补）。
# 改之前建议先把项目复制成新目录再跑（原项目留着做对照），复制时 CONTRACT.json 一起带上。
# 想在方案评审会上发言就在 review_attendees 里加 HUMAN；想自己主持就传 moderator=HUMAN。
# 启动：workflow.start(workflow_demo, entry=run_change.zs, mode=auto, vars={"project": "todo_site1_due"})
# 参数：content? project? review_attendees? moderator?
# 上面这些参数启动时可以用 vars 传（会议室「交给流程」就是这么传的）；不传就用下面「或」后面的默认值。
用包 workflow
设 content = {content 或 给待办加截止日期：新建和修改待办时可以填截止日期（可不填）；列表能按截止日期排序（没有截止日期的排在最后）；过期还没完成的待办在网页上标出来；JSON接口同样支持这些}
设 project = {project 或 todo_site1}
设 goal = 只改这次需求涉及的地方，原有功能、页面和接口照常能用；数据库要加列时在应用启动时自动给已有的库补上（不能丢数据）；不要部署脚本
设 test_cmd = .venv/bin/python -m pytest -q
设 budget = 9
设 roles = ENGINEER_LITE,ENGINEER,ENGINEER_SENIOR,TEST_ENGINEER
设 review_attendees = {review_attendees 或 ARCHITECT_GLM,REVIEWER_GPT}
设 contract = 读约定 work/{project}/CONTRACT.json
如果 {contract.architecture 或} 为空
    终止 失败 work/{project}/CONTRACT.json不存在：先用整项目流程或重构流程生成一份接口约定，再改这个项目
结束
设 base = {contract.architecture}
设 contract_notes = {contract.contract_notes}
编排执行 change_workflow.wf
# 跑完把改动方案合并回约定（改动的模块换成新版、新模块加进来），裁决换成这次流程结束时的（原有的 + 这次新加的）
合并约定 work/{project}/CONTRACT.json plan contract_notes 改项目流程
打印 {workflow_trace}
