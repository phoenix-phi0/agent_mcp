# 和 run.zs 一样的需求，项目目录换成空的 work/users_v2：从零开始实现，用来对比角色卡改动前后的效果
用包 workflow
设 content = 实现用户接口
设 stack = Python3+pytest，第三方包写进requirements.txt
设 project = users_v2
设 test_content = 验证用户接口
编排执行 workflow.wf
