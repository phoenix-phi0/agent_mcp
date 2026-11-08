# 从 workflow_demo 目录运行；只验证编排流程。真实模型调用需正确配置客户端。
用包 workflow
设 content = 实现用户接口
设 stack = Python3+pytest，第三方包写进requirements.txt
设 project = demo
设 test_content = 验证用户接口
编排执行 workflow.wf
打印 {contract}
