接口 POST /progress/answer
  设 r = 调用 progress.记作答 learner={learner} point_code={point_code} question_no={question_no} correct={correct} answer={answer 或} pass_line={pass_line 或} fall_line={fall_line 或}
  返回 {r}
结束


# 接住业务错误：出错时 后面的变量是 {code, error}，成功时是空串
接口 POST /progress/answer_try
  设 r = 调用 progress.记作答 learner={learner} point_code={point_code} question_no={question_no} correct={correct} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "msg": "{e.error}"}
  结束
  返回 {r}
结束


# 接口在外层事务里调用业务函数：函数里的写库并入这个事务，后面报错整体回滚
接口 POST /progress/recalc_then_fail
  用包 db
  事务 app.db
    设 r = 调用 progress.重算 learner={learner} point_code={point_code}
    报错 409 外层中途失败
  结束
结束


接口 POST /progress/recalc
  设 r = 调用 progress.重算 learner={learner} point_code={point_code}
  返回 {r}
结束


# 调本模块的非公开函数：接口不行，只有业务函数能调私有函数
接口 POST /progress/private
  设 r = 调用 progress.重算得分 learner={learner} point_id=1
  返回 {r}
结束


# 少传必填参数 question_no / correct
接口 POST /progress/missing
  设 r = 调用 progress.记作答 learner={learner} point_code={point_code}
  返回 {r}
结束


# 多传了不认识的参数
接口 POST /progress/extra
  设 r = 调用 progress.记作答 learner={learner} point_code={point_code} question_no=1 correct=1 foo=1
  返回 {r}
结束


# 旧机制照常：执行 scripts 下的脚本
接口 POST /progress/legacy
  设 r = 执行 scripts/hello.zs who={who}
  返回 {r}
结束
