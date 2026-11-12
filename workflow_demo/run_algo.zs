# 数据分析工具模块：三个算法函数加一个汇总类，走按成本分配的流程。设 x = 值 的值里不能有空格
# 每次换一个空的 project 目录
用包 workflow
设 content = 实现一个数据分析工具模块：count_pairs_within(nums,k)统计下标i<j且nums[i]+nums[j]<=k的数对个数（nums最多10^5个，可能为空）；min_coins(coins,amount)用给定面值凑出金额的最少硬币数，每种面值可用任意次，凑不出返回-1（amount最多10^4，面值都是正数且互不相同）；island_count(grid)统计0/1网格里由1组成的上下左右连通块个数（网格最多1000x1000，可能为空）；另外提供Report类，构造时传入nums、k、coins、amount、grid，summary()方法返回包含三个函数结果的字典
设 stack = Python3+pytest，第三方包写进requirements.txt
设 project = algo_tools4
设 test_content = 验证数据分析工具模块
设 budget = 7
设 roles = ENGINEER_LITE,ENGINEER,ENGINEER_SENIOR,TEST_ENGINEER
编排执行 cost_workflow.wf
打印 {workflow_trace}
