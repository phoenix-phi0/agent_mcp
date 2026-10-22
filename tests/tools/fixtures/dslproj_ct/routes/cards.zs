接口 POST /cards/save
  设 r = 调用 cards.保存卡片 no1={no1} front1={front1} back1={back1} no2={no2} front2={front2} back2={back2}
  返回 {r}
结束

接口 GET /cards/list
  设 r = 调用 cards.列卡片
  返回 {r}
结束

接口 POST /cards/withdraw
  设 r = 调用 cards.撤下全部
  返回 {r}
结束

接口 POST /cards/reload
  设 r = 调用 cards.按文件重灌
  返回 {r}
结束
