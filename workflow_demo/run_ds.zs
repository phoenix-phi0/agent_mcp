# DeepSeek 试跑：需求和 run_algo.zs 一样（好跟 Claude 卡、GPT 卡对比），实施只放 DeepSeek 两张卡。
# 验收照旧用 Claude 的 QA_ENGINEER 当裁判；返工换成 DeepSeek：roles={"ENGINEER": "ENGINEER_DS"}
# 设 x = 值 的值里不能有空格；每次换一个空的 project 目录
用包 workflow
设 content = 实现一个数据分析工具模块：count_pairs_within(nums,k)统计下标i<j且nums[i]+nums[j]<=k的数对个数（nums最多10^5个，可能为空）；min_coins(coins,amount)用给定面值凑出金额的最少硬币数，每种面值可用任意次，凑不出返回-1（amount最多10^4，面值都是正数且互不相同）；island_count(grid)统计0/1网格里由1组成的上下左右连通块个数（网格最多1000x1000，可能为空）；另外提供Report类，构造时传入nums、k、coins、amount、grid，summary()方法返回包含三个函数结果的字典
设 stack = Python3+pytest，第三方包写进requirements.txt
设 project = algo_ds1
设 test_content = 验证数据分析工具模块
设 budget = 7
设 roles = ENGINEER_DS_LITE,ENGINEER_DS
编排执行 cost_workflow.wf
打印 {workflow_trace}
