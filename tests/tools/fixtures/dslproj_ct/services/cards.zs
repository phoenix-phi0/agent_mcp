业务 cards
  用包 db data text

  公开 函数 保存卡片 no1 front1 back1 no2 front2 back2
    设 rows = 解析JSON []
    设 c1.card_no = {no1}
    设 c1.front = {front1}
    设 c1.back = {back1}
    设 rows = 列表加项 {rows} {c1}
    设 c2.card_no = {no2}
    设 c2.front = {front2}
    设 c2.back = {back2}
    设 rows = 列表加项 {rows} {c2}
    设 w = 写JSONL content/cards/cards.jsonl {rows}
    设 r = 调用 按文件重灌
    返回 {"saved": {r.n}}
  结束

  公开 函数 按文件重灌
    设 has = 存在 content/cards/cards.jsonl
    如果 {has} 不等于 是
      返回 {"n": 0}
    结束
    读JSONL rows = content/cards/cards.jsonl
    设 n = 条数 {rows}
    事务 app.db
      设 x = 写库 app.db cards_card_clear
      遍历 row 于 {rows}
        设 x = 写库表 app.db cards_card_insert {row}
      结束
    结束
    返回 {"n": {n}}
  结束

  公开 函数 列卡片
    设 rows = 查询 app.db cards_card_list
    返回 {"cards": {rows}}
  结束

  公开 函数 读回卡片
    设 has = 存在 content/cards/cards.jsonl
    设 had = 存在 content/cards/cards.withdrawn.jsonl
    设 n = 0
    设 wn = 0
    如果 {has} 等于 是
      读JSONL rows = content/cards/cards.jsonl
      设 n = 条数 {rows}
    结束
    如果 {had} 等于 是
      读JSONL old = content/cards/cards.withdrawn.jsonl
      设 wn = 条数 {old}
    结束
    返回 {"exists": "{has}", "n": {n}, "withdrawn_exists": "{had}", "withdrawn_n": {wn}}
  结束

  公开 函数 撤下全部
    设 has = 存在 content/cards/cards.jsonl
    设 n = 0
    如果 {has} 等于 是
      读JSONL rows = content/cards/cards.jsonl
      设 n = 条数 {rows}
      设 w = 写JSONL content/cards/cards.withdrawn.jsonl {rows}
      设 d = 删文件 content/cards/cards.jsonl
    结束
    设 x = 写库 app.db cards_card_clear
    返回 {"withdrawn": {n}}
  结束
结束
