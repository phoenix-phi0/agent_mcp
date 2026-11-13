## 实施检查清单
- 任务里列出的每个字段、错误码、验收条件，在 changes 或 error_handling 里都有对应的落点；漏掉的写进 open_issues 并说明原因。
- 输入校验写在入口处：类型、必填、长度、格式，失败时返回任务里规定的错误码。
- 测试至少覆盖：每条验收用例、每个错误码、一条边界（空值、超长、不存在中的一种）。
- 跑的是全部测试；verification.method 写实际命令，result 贴汇总行原文。

## verification 的写法
- 好：method「python -m pytest -q」，result「41 passed in 0.52s」。
- 好（有失败）：result「39 passed, 2 failed：test_login_expired、test_logout_twice」，同时 status 写「部分完成」。
- 不行：result「测试通过」「全部 OK」——看不出跑了什么、跑了多少。

## 不算「修好」的做法（看到自己想这么做就停下）
- 断言失败 → 把期望值改成实际值，或把 assertEqual 改成 assertIn。
- 用例跑不过 → 加 @pytest.mark.skip，或把它注释掉。
这些都要改实现；改不了的写进 open_issues，status 写「部分完成」。

## 人工追加的说明
- 提示词里有「补充说明（人工追加）」或「打回意见」时，那是负责人的裁定，和任务同等效力。
- 实现记录的 summary 开头原样写一句「负责人说明：<要点>」，验收的人看不到你的提示词，要靠这句知道哪些是负责人认可过的做法。
