# 前端流程（frontend_workflow.wf）的第二个例子：做「人参加 AI 会议」的网页，作为查看器里的一页（<前缀>/meeting/）。
# 后端是查看器服务，已经做好（启动可传会议参数、静态页挂载）；接口说明在 work/meeting_room/backend/BACKEND.md。
# 设 x = 值 的值里不能有「词+空格」开头，所以下面都不带空格。
用包 workflow
设 content = 做一个让人参加AI会议的网页（查看器里的会议页）：1开会：填议题和背景，从角色卡里按发言顺序选参会者（可以把人自己HUMAN排进去），选主持人（AI主持人或人自己），启动；2会议列表：只列会议类运行，显示议题、状态、现在轮到谁，点进会议室；3会议室：按轮次显示每个人的发言（谁、说了什么、是否认可、点名问了谁什么、追问的回答紧跟在后面）、主持人每轮的判断（还有哪些分歧）和最后的结论（决定、理由、保留意见、待办）；会议进行中显示现在轮到谁、AI在发言时显示正在发言；轮到我发言或回答追问时出发言表单（发言、是否认可、点名问谁从参会名单里选、问题），我当主持人时出判断表单和结论表单，交上去会议接着走；页面自动刷新跟上进度；4只读的服务上不出现任何表单，只能看
设 backend = 查看器服务（agent_mcp的tools/trace_server.py），接口和数据格式全部写在backend/BACKEND.md，相关代码的只读副本在backend/ref/；会议页的静态文件放web/public，服务把它挂在<前缀>/meeting/下，接口一律用相对地址../api/；测试用的真后端用backend/start_test_server.py起（全离线：卡全是人，轮到AI替身时测试脚本自己调api/submit替它交）
设 stack = 纯HTML+CSS+原生JavaScript（ES模块，不用框架、不打包、不用TypeScript）；测试用Node24，测试依赖只有jsdom
设 goal = 前端代码只放在web目录，不改backend目录和别的文件；页面静态文件全在web/public，入口web/public/index.html，单页（用地址的#区分列表、开会、会议室），不要前端路由库；不要开发服务和构建步骤，页面由查看器服务提供；serve写成怎么用start_test_server.py把页面起起来看
设 project = meeting_room
设 web_dir = web
设 test_cmd = ./web/run_tests.sh
设 review_attendees = DESIGNER,ARCHITECT,REVIEWER_GPT
编排执行 frontend_workflow.wf
打印 {workflow_trace}
