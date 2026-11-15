## 补测试检查清单（Go）
- 每种错误至少一个触发它的测试，用 errors.Is / errors.As 断言是哪种错误，不要只断言 err != nil；多个错误同时成立时，测先报的那个。
- 边界：nil、空切片或空 map、零值、恰好在上下限、超出上下限一格、超长、重复调用、记录不存在。
- 组合：前一步的副作用影响后一步（关闭后再用、删除后再查、过期边界前后）。
- 多组输入写成表驱动测试，每行用 t.Run(name, ...) 跑子测试，失败时能直接看出是哪一行。
- 断言要具体：返回值用相等比较（结构体可用 reflect.DeepEqual），失败信息里写出期望值和实际值（t.Errorf("got %v, want %v", got, want)）。
- 有并发的代码写一个多 goroutine 同时调用的测试，并用 -race 跑。
- 不用真实时钟和网络：时间靠参数或注入，文件用 t.TempDir()。

## 缺陷的写法（open_issues）
- 好：「TestLogout_Twice：第二次 Logout 期望返回 ErrUnauthenticated，实际返回 nil；疑在 auth.go:Service.Logout 没检查令牌是否已撤销」。
- 不行：「登出有问题」——看不出是哪个测试、期望什么。
