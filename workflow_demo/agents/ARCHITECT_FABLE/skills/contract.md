## 接口约定自查清单（提交前逐项过一遍）
- 每个输入字段都写了类型、必填还是可选、取值范围或格式（如「3–32 位，字母数字下划线」）。
- 每个接口至少列出一个错误码，并写明触发条件；调用方拿到错误码能知道是改输入、重新登录还是放弃。
- 多个错误同时成立时的先后顺序写进了 constraints。
- 权限写清楚：谁能调用，越权时返回哪个错误码；涉及他人数据的接口单独说明。
- 边界情况有明确行为：空值、超长、重复提交、并发修改、记录不存在、删除最后一个管理员这类「不能为零」的情况。
- 要哈希、写库的字符串字段，写了含不可编码字符（孤立代理字符）时的错误码。
- 「读 → 判断 → 写」的操作写了必须在同一锁 / 同一事务里，并有一条并发交错的验收用例。
- 不变量写成能判断真假的句子。
- 验收条件能直接改写成测试用例：给定什么输入，期望什么输出或错误码。
- 没有加需求里没提的功能；拿不准的写进 open_questions。

## 任务分配的 content 样例（照这个结构写，内容按约定填）
```
【第2项：登录与登出】依赖第1项（沿用 user_service.py 的 UserService、UserError、tokens 表）。
目标：实现 login、logout，令牌只存摘要。
文件和函数：user_service.py 里新增 UserService.login(username, password)、UserService.logout(token)；测试写进 tests/test_user_service.py。
接口要点（约定原文）：
- login 输入 username（str，必填）、password（str，必填）；输出 {"token": str, "expires_at": int}；
  错误：INVALID_CREDENTIALS（用户名不存在或密码错，两种情况返回同一个错误码）。
- logout 输入 token；错误：UNAUTHENTICATED（令牌不存在、已登出或已过期）。
验收用例：
1. 正确的用户名密码 → 返回 token；
2. 错误密码、不存在的用户 → 都是 INVALID_CREDENTIALS；
3. logout 之后再用这个 token → UNAUTHENTICATED。
不做什么：不改第1项已有接口的行为；不实现修改密码（第3项做）。
```

## 拆分粒度
- 一项里接口超过 3 个，或 content 超过 1500 字，就拆。
- 拆的时候按依赖拆：先存储和校验，再鉴权，再增删改查，最后是依赖前面全部的接口。
