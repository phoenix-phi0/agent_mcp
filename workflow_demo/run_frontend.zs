# 前端流程（frontend_workflow.wf）的示例：给已经做好的问卷网站 survey1 配一个纯 HTML/JS 的独立前端。
# 全自动跑；想在评审会上发言就在 review_attendees 里加 HUMAN（启动时用 vars 传，或者在会议室「交给流程」里填），评审会在会议页的会议室里开；想看设计再往下走：confirm_after=["界面设计","设计修改"]。
# 设 x = 值 的值里不能有「词+空格」开头（严格模式会把第一个词当动词），所以下面都不带空格。
# 卡里放行的测试命令是 ./web/run_tests.sh：web_dir 换了名字要同时改 FRONTEND_ENGINEER / FRONTEND_QA 的 allowed_tools。
# 参数：content? project? review_attendees? moderator?
# 上面这些参数启动时可以用 vars 传（会议室「交给流程」就是这么传的）；不传就用下面「或」后面的默认值。
用包 workflow
设 content = {content 或 给问卷网站survey1做一个独立的前端，覆盖后端JSON接口的全部功能：注册、登录、登出；我的问卷列表；新建问卷、编辑标题和说明、增删改题目（单选、多选、文本）；发布和关闭；匿名填写已发布的问卷（凭链接，填过不能再填）；看结果统计和导出CSV}
设 backend = Flask3加SQLite；JSON接口都在/api下（survey_app/api.py，蓝图前缀/api），会话用cookie；survey_app.create_app(test_config)可以传DATABASE和SECRET_KEY，测试见tests/conftest.py；survey_app/web.py是旧的服务端渲染页面，新前端不用它们
设 stack = 纯HTML+CSS+原生JavaScript（ES模块，不用框架、不打包、不用TypeScript）；开发服务和测试用Node24，测试依赖只有jsdom
设 goal = 前端代码只放在web目录，不改后端代码和后端测试；页面和接口同源（开发服务把/api转发给后端），照常用cookie会话；不要部署脚本
设 project = {project 或 survey1}
设 web_dir = web
设 test_cmd = ./web/run_tests.sh
设 review_attendees = {review_attendees 或 DESIGNER,ARCHITECT,REVIEWER_GPT}
编排执行 frontend_workflow.wf
打印 {workflow_trace}
