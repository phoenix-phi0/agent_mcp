# 整项目流程（project_workflow.wf）的示例：一个带登录的待办事项网站，从空目录做起。
# 每次换一个空的 project 目录。设 x = 值 的值里不能有空格（严格模式会把第一个词当动词）。
# 预算是每个模块的实施预算；测试命令用项目自己的虚拟环境（工程师卡 venv=true 会在 work/{project}/.venv 建）。
# 启动：workflow.start(workflow_demo, entry=run_project.zs, mode=auto)；想在架构定下来后先看一眼：confirm_after=["架构设计","架构修改"]
# 参数：content? project?
# 上面这些参数启动时可以用 vars 传（会议室「交给流程」就是这么传的）；不传就用下面「或」后面的默认值。
用包 workflow
设 content = {content 或 做一个多人用的待办事项网站：注册、登录、登出（密码加盐哈希，会话用cookie）；登录后只看得到自己的待办；待办可以新增、修改标题、标记完成、删除，按完成状态筛选；有网页界面（服务端渲染的HTML表单即可，不要前端框架）和同样功能的JSON接口}
设 stack = Python3+Flask3+SQLite（标准库sqlite3，不用ORM）+pytest，第三方包写进requirements.txt；测试用Flask的test_client，不起真服务
设 goal = 数据库文件路径和密钥从环境变量读，有默认值；所有表在应用启动时自动建；不要用户管理后台；不要部署脚本
设 project = {project 或 todo_site1}
设 test_cmd = .venv/bin/python -m pytest -q
设 budget = 9
设 roles = ENGINEER_LITE,ENGINEER,ENGINEER_SENIOR,TEST_ENGINEER
编排执行 project_workflow.wf
打印 {workflow_trace}
