# 用「按设计实现功能」流程做人工确认功能的阶段 1。改的是副本 work/agent_mcp_confirm
# （git clone 自仓库已提交的内容，.venv 链到主仓库的，config.json 里的密钥已清空），主仓库不动。
# 设计：副本根目录 DESIGN_confirm.md（= data/tmp/confirm_design.md，第 11 节的问题都按建议执行）。
# 启动：workflow.start(workflow_demo, entry=run_confirm_p1.zs, mode=auto,
#        roles={"QA_ENGINEER": "QA_GPT", "ENGINEER": "ENGINEER_GPT"})
# 注意：「设 x = 值」的值里不能有空格（strict 模式会把「标识符 空格」当动词调用）
用包 workflow
读取 design = work/agent_mcp_confirm/DESIGN_confirm.md
设 design_file = DESIGN_confirm.md
设 scope = 设计第9节的阶段1：确认规则匹配（卡名、前缀通配、节点名；原卡和换后的卡都算）＋confirm_before（旧名stop_roles照常可用，旧控制文件不用迁移）＋execute的note追加说明（进提示词和记录，不改任务原文）＋所有写接口的actor来源（写进事件和history）＋任务事件里的attempt、notes、confirm字段。对应设计2.1（confirm_before、notes、go的新字段）、2.2、2.3里开始前用到的字段、2.4、3.1(e)(f)的开始前部分、3.2、3.3、4.1，测试第8节第1至7条和第21条，新测试文件tests/tools/test_wf_confirm.py。阶段2至4（结束后确认、approve/reject、清单修改、trace_server和查看器）这次都不做
设 goal = 只改副本里的verbs/workflow/、tools/workflow_ctl.py，新增tests/tools/test_wf_confirm.py；不改查看器、不改kg_v4/和别的模块、不改已有测试的断言；测试都用离线假模型，不调真模型；不要git提交
设 stack = Python3标准库；测试是各自独立运行的脚本（不是pytest），用dsl.client.ScriptClient做离线假模型，写法照tests/tools/test_workflow_ctl.py
设 project = agent_mcp_confirm
设 test_content = 人工确认功能阶段1实现完成，新测试和编排相关的旧测试全部通过
设 test_cmd = /workspace/agent_mcp/data/tmp/confirm_p1_tests.sh
设 budget = 8
设 roles = ENGINEER_GPT_LITE,ENGINEER_GPT,ENGINEER_GPT_SENIOR
编排执行 feature_workflow.wf
打印 {workflow_trace}
