模块 cards
依赖 无

## 表
表 cards_card
  id 整数 主键
  card_no 文本 编号
  front 文本 正面
  back 文本 背面

## 函数
公开 函数 保存卡片 no1 front1 back1 no2 front2 back2
  返回 {saved}
  伪代码 把两张卡片（编号、正面、背面）写成 content/cards/cards.jsonl（文件为准，覆盖旧文件）
  伪代码 调用 按文件重灌，返回 {"saved": 重灌条数}
公开 函数 按文件重灌
  返回 {n}
  伪代码 content/cards/cards.jsonl 不存在则返回 {"n": 0}（库不动）
  伪代码 事务里清空 cards_card，再按文件逐行写库；返回 {"n": 文件条数}
公开 函数 列卡片
  返回 {cards}
  伪代码 从库按 id 升序查出全部卡片
公开 函数 读回卡片
  返回 {exists, n, withdrawn_exists, withdrawn_n}
  伪代码 读 content/cards/cards.jsonl 与 cards.withdrawn.jsonl：是否存在、各有几条
公开 函数 撤下全部
  返回 {withdrawn}
  伪代码 cards.jsonl 存在则读出来写到 cards.withdrawn.jsonl 再删旧文件；清空库；返回撤下的条数

## 接口
POST /cards/save -> 保存卡片
GET /cards/list -> 列卡片
POST /cards/withdraw -> 撤下全部
POST /cards/reload -> 按文件重灌

## 内容文件
content/cards/cards.jsonl 字段 card_no,front,back；写：本模块函数 保存卡片,撤下全部；读：本模块函数 按文件重灌,读回卡片,撤下全部；教师保存的卡片，库按它重灌
content/cards/cards.withdrawn.jsonl 字段 card_no,front,back；写：本模块函数 撤下全部；读：本模块函数 读回卡片；撤下后留着的卡片

## 用例
用例 保存卡片_写文件并重灌库
  调用 保存卡片 no1=C1 front1=猫 back1=cat no2=C2 front2=狗 back2=dog
  得 saved=2
  库 cards_card 共 2 行
  库 cards_card 含 card_no=C2 front=狗 back=dog

用例 保存卡片_覆盖旧文件
  先 调用 保存卡片 no1=C1 front1=猫 back1=cat no2=C2 front2=狗 back2=dog
  调用 保存卡片 no1=C9 front1=鸟 back1=bird no2=C8 front2=鱼 back2=fish
  得 saved=2
  库 cards_card 共 2 行
  库 cards_card 无 card_no=C1

用例 列卡片_从库读
  先 数据 cards_card card_no=C1 front=猫 back=cat
  调用 列卡片
  得 有返回

用例 读回卡片_文件内容
  先 调用 保存卡片 no1=C1 front1=猫 back1=cat no2=C2 front2=狗 back2=dog
  调用 读回卡片
  得 exists=是 n=2 withdrawn_exists=否 withdrawn_n=0

用例 读回卡片_没有文件_上个用例的文件不留
  调用 读回卡片
  得 exists=否 n=0 withdrawn_exists=否

用例 按文件重灌_按先造的文件
  先 文件 content/cards/cards.jsonl 内容={"card_no":"X1","front":"猫","back":"cat"}\n{"card_no":"X2","front":"狗","back":"dog"}\n{"card_no":"X3","front":"鸟","back":"bird"}
  先 数据 cards_card card_no=OLD front=旧 back=old
  调用 按文件重灌
  得 n=3
  库 cards_card 共 3 行
  库 cards_card 无 card_no=OLD

用例 按文件重灌_没有文件库不动
  先 数据 cards_card card_no=KEEP front=留 back=keep
  调用 按文件重灌
  得 n=0
  库 cards_card 含 card_no=KEEP

用例 撤下全部_挪文件并清库
  先 调用 保存卡片 no1=C1 front1=猫 back1=cat no2=C2 front2=狗 back2=dog
  调用 撤下全部
  得 withdrawn=2
  库 cards_card 共 0 行

用例 撤下全部_文件已挪走
  先 调用 保存卡片 no1=C1 front1=猫 back1=cat no2=C2 front2=狗 back2=dog
  先 调用 撤下全部
  调用 读回卡片
  得 exists=否 n=0 withdrawn_exists=是 withdrawn_n=2

用例 撤下后再按文件重灌_回不来
  先 调用 保存卡片 no1=C1 front1=猫 back1=cat no2=C2 front2=狗 back2=dog
  先 调用 撤下全部
  调用 按文件重灌
  得 n=0
  库 cards_card 共 0 行
