# 改代码验收流程（code_accept.wf）：在 agent_mcp 的 git 工作树 workflow_demo/work/<wt> 里改代码，验收过了放进暂存区，停下等人提交。
# 工作树只有提交过的文件（config.json 这类被忽略的配置不在里面）；分支是 wf/<wt>，人提交后再合并回主分支。
# allow 是允许改的文件（JSON 列表，可以写 tools/*.py 这样的通配）；test 是 tests/ 下的一个测试；checklist 是验收清单。
# 启动：workflow.start(workflow_demo, entry=run_code_accept.zs, mode=auto, vars={"task": "...", "allow": "[\"tools/x.py\"]", "test": "tests/tools/test_x.py", "checklist": "...", "wt": "agent_mcp_x"})
# 参数：task? repo? allow? test? checklist? wt? wt_root? engineer? acceptor?
用包 workflow
设 task = {task 或 在tests/tools/test_wf_cost.py末尾补一条检查：tools/wf_plan.py的cost_summary在预算为0时status是超出}
设 repo = {repo 或 /workspace/agent_mcp}
设 allow = {allow 或 ["tests/tools/test_wf_cost.py"]}
设 test = {test 或 tests/tools/test_wf_cost.py}
设 checklist = {checklist 或 1新检查覆盖预算为0；2断言status等于超出；3没有改cost_summary本身；4原有的检查一条没少}
设 wt = {wt 或 agent_mcp_wf}
设 wt_root = {wt_root 或 /workspace/agent_mcp/workflow_demo/work}
设 wt_path = {wt_root}/{wt}
设 project = {wt}
设 engineer = {engineer 或 REPO_ENGINEER}
设 acceptor = {acceptor 或 ACCEPTOR}
编排执行 code_accept.wf
打印 {workflow_trace}
