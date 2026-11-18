# 整项目流程第四次真跑：模块验收换成 QA_PLATFORM（Claude Platform 托管 agent，工具在阿里云 worker 沙箱里执行），
# 看真实流程里它是否逐条读代码、判得严不严、耗时和费用；集成验收仍用 QA_ENGINEER 做对照。中等规模需求（约 5～6 个模块）。
用包 workflow
设 content = 做一个小团队用的问卷调查网站。（1）账号：注册、登录、登出，密码加盐哈希，会话用cookie。（2）问卷：登录用户创建问卷（标题、说明、截止时间），问卷里有多道题，题型有单选、多选、简答，选择题有选项；问卷在发布前可以增删改题目和调整顺序，发布后不能再改题。（3）作答：发布后生成一个分享链接，任何人不用登录就能打开作答，必答题没答不能提交，截止后不能再答，同一浏览器只能答一次（cookie标记）。（4）结果：创建者看每道选择题各选项的人数和占比、简答题的回答列表，可以导出全部答卷为CSV。（5）网页界面（服务端渲染的HTML表单，不要前端框架）和同样功能的JSON接口
设 stack = Python3+Flask3+SQLite（标准库sqlite3，不用ORM）+pytest，第三方包写进requirements.txt；测试用Flask的test_client，不起真服务；时间相关的逻辑要能在测试里注入当前时间
设 goal = 数据库文件路径和密钥从环境变量读，有默认值；所有表在应用启动时自动建；不要用户管理后台；不要部署脚本
设 project = survey1
设 test_cmd = .venv/bin/python -m pytest -q
设 budget = 9
设 roles = ENGINEER_LITE,ENGINEER_GPT_LITE,ENGINEER,ENGINEER_GPT,ENGINEER_SENIOR,ENGINEER_GPT_SENIOR,TEST_ENGINEER
设 module_qa = QA_PLATFORM
编排执行 project_workflow.wf
打印 {workflow_trace}
