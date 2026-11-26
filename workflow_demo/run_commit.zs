# 提交流程（commit.wf）：代码已经改好、只差提交。查范围、查密钥、暂存、暂存版跑测试、对照失败，写好提交说明后停下等人提交。
# mark 是开工时 git_mark 给的起点编号；allow 是允许提交的文件（JSON 列表，可写通配）；test 是 tests/ 下的一个测试。
# repo 默认是 workflow_demo/work/<wt>（改代码验收流程开的工作树）；失败分析员的 cwd 是 work/<wt>。
# 参数：repo? mark? allow? test? wt? wt_root? triage? scribe?
用包 workflow
设 wt = {wt 或 agent_mcp_wf}
设 wt_root = {wt_root 或 /workspace/agent_mcp/workflow_demo/work}
设 repo = {repo 或}
如果 {repo 或} 为空
    设 repo = {wt_root}/{wt}
结束
设 mark = {mark 或 未给起点}
设 allow = {allow 或 ["tests/tools/test_wf_cost.py"]}
设 test = {test 或 tests/tools/test_wf_cost.py}
设 project = {wt}
设 triage = {triage 或 TRIAGE}
设 scribe = {scribe 或 SCRIBE}
编排执行 commit.wf
打印 {workflow_trace}
