# 按做题情况给一个知识点重算一次掌握得分，跟当前分不同才记一行。
#
# 调用方：routes/quiz.zs 的 /quiz/answer、routes/learn.zs 的 /learn/answer
# （答完一题，在它们的事务里调——作答和得分一起成、一起败），以及
# routes/score.zs 的 /score/rebuild（回填有作答、没得分的点）。用
# 「执行 scripts/score_update.zs learner=… point=…」调。
#
# 算法在 queries/score_calc.sql。**打分参数的默认值都在这里**：三个接口
# 共用一套，写在各自的接口里就是三份，改一处漏两处。调用时也可以按名
# 传进来盖掉默认值（window=10 之类）。
#
#   window       20    只看最近几次作答
#   decay        0.85  越近权重越大，第 k 次（0 是最近）权重 decay^k
#   prior_right  0.25  先验：相当于预先记了 1.5 道虚拟题、其中 0.25 道对
#   prior_wrong  1.25  （答得少时分数往 1/6 拉；8 道全对正好到 80）
#   hard_right   1.3   进阶题答对的权重
#   easy_wrong   1.3   基础题答错的权重
#
# 返回 {"changed":"1/0","before":"旧分或空","after":"新分","label":…,"text":…}；
# text 是「推量判断 得分 42 → 51」这样一句，做题页批改下面显示。这个点
# 没有作答（n=0）时不打分，changed=0、after 空。

用包 db

设 calc_args.learner = {learner}
设 calc_args.point = {point}
设 calc_args.window = {window 或 20}
设 calc_args.decay = {decay 或 0.85}
设 calc_args.prior_right = {prior_right 或 0.25}
设 calc_args.prior_wrong = {prior_wrong 或 1.25}
设 calc_args.hard_right = {hard_right 或 1.3}
设 calc_args.easy_wrong = {easy_wrong 或 1.3}
设 calc = 查一行表 app.db score_calc {calc_args}

如果 {calc.n 或 0} 等于 0
  返回 {"changed":"0","before":"","after":"","label":"","text":""}
结束

设 old = {calc.prev 或}
设 phrase = {calc.label} 得分 {old} → {calc.value}
如果 {old} 为空
  设 phrase = {calc.label} 得分 {calc.value}（第一次打分）
结束

如果 {calc.changed} 等于 0
  设 phrase = {calc.label} 得分 {calc.value}（没变）
  返回 {"changed":"0","before":"{old}","after":"{calc.value}","label":"{calc.label}","text":"{phrase}"}
结束

设 rec.learner = {learner}
设 rec.point = {point}
设 rec.value = {calc.value}
设 affected = 写库表 app.db score_add {rec}
返回 {"changed":"1","before":"{old}","after":"{calc.value}","label":"{calc.label}","text":"{phrase}"}
