# 开一场会：议题、背景、参会名单和主持人都在启动时传（查看器的会议页、流程 MCP 的 start 用 vars 传）。
# 参数：topic attendees background=无 moderator=MODERATOR
# attendees 是逗号分隔的卡名，按发言顺序；人参会写 HUMAN。moderator 写 HUMAN 就是人来判断和拍板。
用包 workflow
编排执行 meeting_workflow.wf
打印 {decision}
