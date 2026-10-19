## DSL 项目写法速查（实体、查询、业务层、接口）
- 实体 entities/<模块>.entity（建表）：
```
实体 answer 作答
  字段 learner 文本 必填 索引 学习者
  字段 correct 布尔 必填 默认 否 对错
  字段 at 文本 必填 默认 now 时间
结束
```
  类型：文本 长文本 整数 小数 日期 布尔 枚举（枚举写 枚举 a,b,c）；旗标：必填 唯一 索引；`关联 <实体>`、`默认 <值>`、`主键 a b`、`唯一 a b`。一个实体 = 一张表，隐含自增 id（有 主键 就不加）；每个实体以「结束」收尾；约定「## 表」里每个表名都要有同名实体；只写本模块拥有的表。
- SQL queries/<名>.sql：一个文件一条语句，参数 `:名`；参数传进来都是字符串，数值比较 / LIMIT 要 CAST，如 `CAST(:n AS INTEGER)`。文件名以模块名开头（queries/progress_answer_insert.sql）。
- 业务 services/<模块>.zs（所有逻辑写在这里）：
```
业务 progress
  依赖 graph                 # 要调用哪些别的模块的公开函数；不写就不能调（和约定的「依赖」一致）
  用包 db                    # 本文件函数共用的包

  公开 函数 记作答 learner point_code correct answer?
    设 p = 调用 graph.取知识点 code={point_code}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    事务 app.db
      设 n = 写库 app.db progress_answer_insert learner={learner} point_id={p.id} correct={correct}
    结束
    返回 {"ok": 1}
  结束

  函数 内部帮手 learner         # 不写「公开」= 只给本模块用
    设 total = 查一值 app.db progress_answer_count learner={learner}
    返回 {"total": {total}}
  结束
结束
```
  函数是独立作用域：里面只有入参，要什么当入参传（可选入参 `名?` 不传是空串）。`返回 值`（对象写 JSON，值里可嵌 {变量}）交出结果；`报错 4xx 文字` 是业务错误（沿调用链到接口变成 HTTP 码 + {"error": 文字}）。
  调用：`设 r = 调用 模块.函数 键=值 …`（同模块可只写函数名）；接住业务错误加 `出错时 e`（`{e.code}` `{e.error}`，没出错 `{e}` 是空串）。几个写操作要一起成功或一起失败，包在 `事务 app.db … 结束` 里。
  条件：等于 不等于 为空 不为空 包含 大于 小于 不小于 不大于 开头是（也可 > < >= <= == !=）；组合用 且 或 非。算数：`设 n = 计算 {a} * 100 / {b}`。取时间：`设 now = 当前时间`。`{x 或 默认}` 取变量，空时用默认。
  db 包动词：`查一行 app.db 查询名 键=值`（没有则空）、`查一值 …`（单列）、`查询 app.db 查询名 键=值`（多行列表，可 遍历）、`写库 app.db 查询名 键=值`。查询名 = queries/ 下的文件名（不含 .sql）。
- 接口 routes/<模块>*.zs（文件名以模块名开头）：只收请求、调一个函数、返回，一个接口只调约定里写的那个函数：
```
接口 POST /progress/answer
  设 r = 调用 progress.记作答 learner={learner} point_code={point_code} correct={correct}
  返回 {r}
结束
```
  请求字段直接是变量（如 `{learner}`），可选入参没传时就是空串。
- 函数头（名字、入参、公开与否、依赖）必须和约定一字不差，程序会比对；约定文件 contracts/ 不能改，验收用例由程序按约定里的「## 用例」跑，不要自己写别的测试。
