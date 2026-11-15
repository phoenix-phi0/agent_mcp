## 实施检查清单（Go）
- 任务里列出的每个函数、字段、错误、验收条件，在 changes 或 error_handling 里都有对应的落点；漏掉的写进 open_issues 并说明原因。
- 函数签名、导出名（首字母大写）和任务写的一致；任务给了错误名就定义成导出的哨兵错误（`var ErrNotFound = errors.New(...)`），调用方用 errors.Is 能判断。
- 输入校验写在函数入口处：nil、空值、长度、范围，失败时返回任务里规定的错误。
- 测试至少覆盖：每条验收用例、每种错误、一条边界（nil、空切片、零值、上限中的一种）。多组输入用表驱动测试 + t.Run。
- gofmt -l 没有输出，go vet 没有报错，`go test ./...` 全部通过。

## verification 的写法
- 好：method「go test ./...」，result「ok  example.com/algo  0.015s」。
- 好（有失败）：result「--- FAIL: TestMinCoins/unreachable；FAIL example.com/algo 0.010s」，同时 status 写「部分完成」。
- 不行：result「测试通过」——看不出跑了什么。

## 不算「修好」的做法（看到自己想这么做就停下）
- 把期望值改成实际值、只检查 err != nil、缩小数据规模、加 t.Skip、注释掉用例。
这些都要改实现；改不了的写进 open_issues，status 写「部分完成」。

## 人工追加的说明
- 提示词里有「补充说明（人工追加）」或「打回意见」时，那是负责人的裁定，和任务同等效力。
- 实现记录的 summary 开头原样写一句「负责人说明：<要点>」。
