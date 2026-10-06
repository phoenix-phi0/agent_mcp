# 答完一题后的收尾：重算掌握得分，再按得分改掌握标记。
#
# 调用方：routes/quiz.zs 的 /quiz/answer、routes/learn.zs 的 /learn/answer
# （在它们的事务里、写完流水和汇总之后调），routes/score.zs 的
# /score/rebuild。用「执行 scripts/mastery_update.zs learner=… point=…」调。
# 三处共用这一份：判定规则写在三个接口里，就是改一处漏两处。
#
# 掌握看得分、不看累计正确率，两条线（line 80 / keep 60）的理由见
# queries/mastery_one.sql。**两条线的默认值在这里**，调用时可以按名传进来
# 盖掉（line=90 之类）。
#
# 返回 score_update 的全部字段（changed / before / after / label / text），
# 再加：
#   mastered  1/0  改完之后的标记
#   just      是/否  这次刚从没掌握变成掌握（喜报用）
#   right / total / rate  累计统计，给界面看

用包 db

# 调用方常把自己收到的 line / keep 原样转过来，没收到就是空串——空串和
# 没传一样，补默认值
设 line = {line 或}
如果 {line} 为空
  设 line = 80
结束
设 keep = {keep 或}
如果 {keep} 为空
  设 keep = 60
结束

设 scoring = 执行 scripts/score_update.zs learner={learner} point={point}

设 cond.learner = {learner}
设 cond.point = {point}
设 cond.score = {scoring.after 或}
设 cond.line = {line}
设 cond.keep = {keep}
设 status = 查一行表 app.db mastery_one {cond}

设 just = 否
如果 {status.ok} 等于 1
  如果 {status.mastered} 等于 0
    设 just = 是
  结束
结束

设 mark.learner = {learner}
设 mark.point = {point}
设 mark.mastered = {status.ok 或 0}
设 affected = 写库表 app.db mastery_set {mark}

返回 {"changed":"{scoring.changed}","before":"{scoring.before}","after":"{scoring.after}","label":"{scoring.label}","text":"{scoring.text}","mastered":"{status.ok 或 0}","just":"{just}","right":"{status.right}","total":"{status.total}","rate":"{status.rate}"}
