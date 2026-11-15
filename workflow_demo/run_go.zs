# Go 版的按成本分配试跑：只放 Go 角色卡。设 x = 值 的值里不能有空格；每次换一个空的 project 目录
# 启动时把验收和返工换成 Go 卡：roles={"QA_ENGINEER": "QA_ENGINEER_GO", "ENGINEER": "ENGINEER_GO"}
用包 workflow
设 content = 用Go实现一个数据分析工具包algo（模块名example.com/algo，只用标准库）：CountPairsWithin(nums[]int,k int)int统计下标i<j且nums[i]+nums[j]<=k的数对个数（nums最多10^5个，可能为nil或空，要求O(nlogn)，不能修改调用方传入的切片）；MinCoins(coins[]int,amount int)(int,error)用给定面值凑出金额的最少硬币数，每种面值可用任意次，凑不出返回-1和nil，amount为负或coins里有非正数时返回导出的哨兵错误ErrInvalidInput；IslandCount(grid[][]int)int统计0/1网格里由1组成的上下左右连通块个数（网格最多1000x1000，可能为nil，不能用递归以免栈过深，不能修改传入的网格）；另外提供Report结构体和NewReport(nums,k,coins,amount,grid)构造函数，Summary()方法返回map[string]any，键为pairs、coins、islands，coins在出错时值为错误信息字符串
设 stack = Go1.26，只用标准库，go.mod模块名example.com/algo，测试用go标准testing
设 project = go_algo1
设 test_content = 验证Go数据分析工具包algo：go.mod模块名为example.com/algo；go build、go vet、gofmt -l、go test -race全部通过；三个函数和Report按需求实现，ErrInvalidInput可用errors.Is判断，大规模输入（10^5个数、1000x1000网格）有测试且不超时，不修改传入的切片和网格
设 budget = 7
设 roles = ENGINEER_GO_LITE,ENGINEER_GO,TEST_ENGINEER_GO
编排执行 cost_workflow.wf
打印 {workflow_trace}
