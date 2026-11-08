# 放开技术栈后的第一次真跑：新项目、新目录、要用第三方包
用包 workflow
设 content = 实现一个记账工具的核心库：记录收入和支出，按月份和类别汇总，导入导出CSV。金额用Decimal，数据模型用pydantic，不需要命令行界面
设 stack = Python3+pytest+pydantic2，第三方包写进requirements.txt
设 project = ledger
设 test_content = 验证记账工具核心库
编排执行 workflow.wf
打印 {workflow_trace}
