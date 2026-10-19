模块 graph
依赖 无

## 表
表 point
  id 整数 主键
  code 文本 唯一 知识点编号
  title 文本 名称
表 edge
  id 整数 主键
  src 文本 前置知识点编号
  dst 文本 后继知识点编号

## 函数
公开 函数 取知识点 code
  返回 {id, code, title}，没有这个知识点返回空
  伪代码 按 code 查 point 表的一行，原样返回（查不到就返回空）
公开 函数 加边 src dst
  返回 {ok}
  报错 404 没有这个知识点
  报错 409 会形成环
  伪代码 src、dst 都要在 point 表里，否则 报错 404 没有这个知识点
  伪代码 src 等于 dst，或者沿 edge 表（src → dst 方向）从 dst 出发能走到 src，则 报错 409 会形成环
  伪代码 否则往 edge 表插入一行 (src, dst)，返回 {"ok": 1}

## 接口
GET /graph/point -> 取知识点
POST /graph/edge -> 加边

## 用例
用例 取知识点_取到
  先 数据 point code=P1 title=一次函数
  调用 取知识点 code=P1
  得 code=P1 title=一次函数

用例 取知识点_没有
  调用 取知识点 code=NOPE
  得 为空

用例 加边_成功
  先 数据 point code=P1 title=甲
  先 数据 point code=P2 title=乙
  调用 加边 src=P1 dst=P2
  得 ok=1
  库 edge 共 1 行
  库 edge 含 src=P1 dst=P2

用例 加边_没有知识点
  先 数据 point code=P1 title=甲
  调用 加边 src=P1 dst=P9
  报错 404
  库 edge 共 0 行

用例 加边_自环
  先 数据 point code=P1 title=甲
  调用 加边 src=P1 dst=P1
  报错 409
  库 edge 共 0 行

用例 加边_成环
  先 数据 point code=P1 title=甲
  先 数据 point code=P2 title=乙
  先 数据 point code=P3 title=丙
  先 数据 edge src=P1 dst=P2
  先 数据 edge src=P2 dst=P3
  调用 加边 src=P3 dst=P1
  报错 409
  库 edge 共 2 行

用例 加边_菱形不成环
  先 数据 point code=P1 title=甲
  先 数据 point code=P2 title=乙
  先 数据 point code=P3 title=丙
  先 数据 point code=P4 title=丁
  先 数据 edge src=P1 dst=P2
  先 数据 edge src=P1 dst=P3
  先 数据 edge src=P2 dst=P4
  调用 加边 src=P3 dst=P4
  得 ok=1
  库 edge 共 4 行
