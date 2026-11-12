# 看顶档 ENGINEER_FABLE（Fable 5.2，cost 15）的效果：换一个更难的需求，预算放到 22，
# 够放一张 fable 加几张便宜的；挑不挑、给哪一项由架构师按难度决定。QA 在启动时换成 QA_GPT
用包 workflow
设 content = 实现多用户钱包服务：注册登录（令牌）、两种角色（普通用户/管理员）、充值、用户之间转账（并发下余额不能为负、不能多扣少扣；带幂等键，同一个键重复提交只生效一次）、本人流水查询（分页）、管理员冻结和解冻账户（冻结后不能转出也不能收款）
设 stack = Python3+pytest，第三方包写进requirements.txt，存储用sqlite
设 project = wallet_fable1
设 test_content = 验证钱包服务
设 budget = 22
设 roles = ENGINEER_LITE,ENGINEER_GPT_LITE,ENGINEER_GPT,ENGINEER,ENGINEER_GPT_SENIOR,ENGINEER_SENIOR,ENGINEER_FABLE,TEST_ENGINEER
编排执行 cost_workflow.wf
打印 {workflow_trace}
