# AI 会议示例：给 survey1（问卷网站）配一个独立前端，用什么技术、怎么验收。人参会（HUMAN），轮到人时在查看器上发言。
用包 workflow
设 topic = 给已经做好的问卷网站survey1配一个独立前端：用纯HTML/JS还是React加Vite，页面怎么验收（浏览器测试、截图、看图检查各管什么）
设 background = 后端是Flask加SQLite，已经有完整的JSON接口（注册登录、问卷和题目增删改、发布、匿名作答、结果统计和CSV导出），会话用cookie。前端要放在单独目录里，调这些接口。机器上可以装Playwright和Chromium做截图
设 attendees = ARCHITECT,REVIEWER_GPT,ARCHITECT_GLM,HUMAN
编排执行 meeting_workflow.wf
打印 {decision}
