业务 progress
  依赖 graph                 # 可调用 graph 里的公开函数
  用包 db                    # 本文件里函数共用的包

  公开 函数 记作答 learner point_code question_no correct answer? pass_line? fall_line?
    设 p = 调用 graph.取知识点 code={point_code}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    事务 app.db
      设 n = 写库 app.db answer_insert learner={learner} point_id={p.id} question_no={question_no} correct={correct}
      设 r = 调用 重算得分 learner={learner} point_id={p.id} pass_line={pass_line} fall_line={fall_line}
      如果 {question_no} 等于 boom
        报错 409 中途失败
      结束
    结束
    返回 {"score": {r.score}, "mastered": {r.mastered}, "weak": {r.weak}}
  结束

  # 不写「公开」= 只给本模块用。在外层事务里被调用时，写库并入外层事务
  函数 重算得分 learner point_id pass_line? fall_line?
    设 pl = {pass_line 或 80}
    设 fl = {fall_line 或 40}
    设 total = 查一值 app.db answer_count learner={learner} point_id={point_id}
    设 right = 查一值 app.db answer_right learner={learner} point_id={point_id}
    设 score = 计算 {right} * 100 / {total}
    设 mastered = 0
    设 weak = 0
    如果 {score} 不小于 {pl}
      设 mastered = 1
    否则如果 {score} 小于 {fl}
      设 weak = 1
    结束
    设 n = 写库 app.db mastery_upsert learner={learner} point_id={point_id} score={score} mastered={mastered}
    返回 {"score": {score}, "mastered": {mastered}, "weak": {weak}}
  结束

  # 自己开事务的公开函数：单独调用时自己提交；在外层事务里被调用时并入外层
  公开 函数 重算 learner point_code
    设 p = 调用 graph.取知识点 code={point_code}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    事务 app.db
      设 r = 调用 重算得分 learner={learner} point_id={p.id}
    结束
    返回 {r}
  结束
结束
