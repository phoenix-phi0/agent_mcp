# 整项目流程第二次真跑：同一个待办网站，可用清单里同时放 Claude 和 Codex 的工程师卡，让架构师按成本自己挑。
# 和 run_project.zs 只差 project 目录和 roles。
用包 workflow
设 content = 做一个多人用的待办事项网站：注册、登录、登出（密码加盐哈希，会话用cookie）；登录后只看得到自己的待办；待办可以新增、修改标题、标记完成、删除，按完成状态筛选；有网页界面（服务端渲染的HTML表单即可，不要前端框架）和同样功能的JSON接口
设 stack = Python3+Flask3+SQLite（标准库sqlite3，不用ORM）+pytest，第三方包写进requirements.txt；测试用Flask的test_client，不起真服务
设 goal = 数据库文件路径和密钥从环境变量读，有默认值；所有表在应用启动时自动建；不要用户管理后台；不要部署脚本
设 project = todo_site2
设 test_cmd = .venv/bin/python -m pytest -q
设 budget = 9
设 roles = ENGINEER_LITE,ENGINEER_GPT_LITE,ENGINEER,ENGINEER_GPT,ENGINEER_SENIOR,ENGINEER_GPT_SENIOR,TEST_ENGINEER
编排执行 project_workflow.wf
打印 {workflow_trace}
