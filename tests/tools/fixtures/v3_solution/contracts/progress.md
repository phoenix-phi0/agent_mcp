模块 progress
依赖 graph

## 表
表 progress_answer
  id 整数 主键
  learner 文本 学习者
  point_code 文本 知识点编号
  correct 整数 是否答对（1/0）
  at 文本 作答日期

## 函数
公开 函数 记作答 learner point_code correct
  返回 {ok, total, right, score}，score 是该学习者在该知识点的正确率百分比（四舍五入取整）
  报错 404 没有这个知识点
  报错 400 correct 只能是 0 或 1
  伪代码 调用 graph.取知识点 code=point_code，取不到 报错 404 没有这个知识点
  伪代码 correct 不是 0 也不是 1，报错 400 correct 只能是 0 或 1
  伪代码 往 progress_answer 表插入一行 (learner, point_code, correct, at=当前时间 日期)
  伪代码 统计该 learner 在该 point_code 上的作答总数 total 和答对数 right，score = right * 100 / total 四舍五入
  伪代码 返回 {"ok": 1, "total": total, "right": right, "score": score}

## 接口
POST /progress/answer -> 记作答

## 用例
用例 记作答_答对
  先 数据 graph_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 correct=1
  得 ok=1 total=1 right=1 score=100
  库 progress_answer 共 1 行
  库 progress_answer 含 learner=u1 point_code=P1 correct=1 at=2026-01-01

用例 记作答_累计正确率
  先 数据 graph_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 correct=1
  先 调用 记作答 learner=u1 point_code=P1 correct=1
  调用 记作答 learner=u1 point_code=P1 correct=0
  得 total=3 right=2 score=67

用例 记作答_不同学习者各算各的
  先 数据 graph_point code=P1 title=一次函数
  先 调用 记作答 learner=u1 point_code=P1 correct=0
  调用 记作答 learner=u2 point_code=P1 correct=1
  得 total=1 right=1 score=100

用例 记作答_没有知识点
  调用 记作答 learner=u1 point_code=NOPE correct=1
  报错 404
  库 progress_answer 共 0 行

用例 记作答_correct非法
  先 数据 graph_point code=P1 title=一次函数
  调用 记作答 learner=u1 point_code=P1 correct=2
  报错 400
  库 progress_answer 共 0 行
