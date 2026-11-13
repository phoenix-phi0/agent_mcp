# 用「按设计实现功能」流程做人工确认功能的阶段 2（结束后确认）。改的是副本 work/agent_mcp_confirm，
# 阶段 1 的成果已在副本里本地提交（主仓库已合并），这次在它上面接着做；主仓库不动。
# 启动：workflow.start(workflow_demo, entry=run_confirm_p2.zs, mode=auto,
#        roles={"QA_ENGINEER": "QA_GPT", "ENGINEER": "ENGINEER_GPT"}, confirm_before=["代码修改"])
#   —— 返工前停下给人看 QA 的意见（阶段 1 做出来的功能），范围外的意见由人追加说明或直接交结果
# 注意：「设 x = 值」的值里不能有空格
用包 workflow
读取 design = work/agent_mcp_confirm/DESIGN_confirm.md
设 design_file = DESIGN_confirm.md
设 scope = 设计第9节的阶段2：结束后确认。任务事件新状态review和rejected（2.3），控制器的held/carry和hold/release动作、approve和reject裁决（3.3第2、5步），打回接入重试计数和max_attempts（3.4，默认4，失败和打回合计，到上限只拦打回），打回时提示词带打回意见和上一次的结果（3.2的previous，上限20000字），revisions和result_model（改了再通过时保留模型原结果），_prune扩展到after和revisions（2.1），workflow_ctl新接口approve和reject以及configure/start的confirm_after、max_attempts参数（4.1、4.2、4.3里相关的错误），status里pending.phase=after和pending.result。另加一条：控制文件的读改写加文件锁（fcntl.flock，workflow_ctl所有写控制文件的入口都要拿锁），防止查看器和workflow_ctl同时写互相覆盖。对应测试第8节第8至20条，加到tests/tools/test_wf_confirm.py。阶段3和4（清单修改、逐项设置、遍历item、trace_server和查看器、fs_server_v2工具名）这次都不做
设 goal = 只改副本里的verbs/workflow/、tools/workflow_ctl.py，测试加到tests/tools/test_wf_confirm.py；不改查看器、不改kg_v4/和别的模块、不改requirements.txt、不改已有测试的断言；阶段1已有的行为和测试保持；测试都用离线假模型，不调真模型；不要git提交。设计第11节的问题都按其中的建议执行
设 stack = Python3标准库；测试是各自独立运行的脚本（不是pytest），用dsl.client.ScriptClient做离线假模型，写法照tests/tools/test_wf_confirm.py已有的部分
设 project = agent_mcp_confirm
设 test_content = 人工确认功能阶段2（结束后确认）实现完成，新测试和编排相关的旧测试全部通过
设 test_cmd = /workspace/agent_mcp/data/tmp/confirm_p2_tests.sh
设 budget = 10
设 roles = ENGINEER_GPT_LITE,ENGINEER_GPT,ENGINEER_GPT_SENIOR
编排执行 feature_workflow.wf
打印 {workflow_trace}
