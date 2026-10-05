# 按做题情况给一个知识点重算一次掌握得分，跟当前分不同才记一行。
#
# 调用方：routes/quiz.zs 的 /quiz/answer、routes/learn.zs 的 /learn/answer
# （答完一题，在它们的事务里调——作答和得分一起成、一起败），以及
# routes/score.zs 的 /score/rebuild（回填有作答、没得分的点）。用
# 「执行 scripts/score_update.zs 学习者=… 知识点=…」调。
#
# 算法在 queries/score_calc.sql。**打分参数的默认值都在这里**：三个接口
# 共用一套，写在各自的接口里就是三份，改一处漏两处。调用时也可以按名
# 传进来盖掉默认值（窗口=10 之类）。
#
#   窗口     20    只看最近几次作答
#   衰减     0.85  越近权重越大，第 k 次（0 是最近）权重 衰减^k
#   先验对   0.25  先验：相当于预先记了 1.5 道虚拟题、其中 0.25 道对
#   先验错   1.25  （答得少时分数往 1/6 拉；8 道全对正好到 80）
#   难题对   1.3   进阶题答对的权重
#   易题错   1.3   基础题答错的权重
#
# 返回 {"changed":"1/0","before":"旧分或空","after":"新分","label":…,"text":…}；
# text 是「推量判断 得分 42 → 51」这样一句，做题页批改下面显示。这个点
# 没有作答（n=0）时不打分，changed=0、after 空。

用包 db

设 参.learner = {学习者}
设 参.point = {知识点}
设 参.window = {窗口 或 20}
设 参.decay = {衰减 或 0.85}
设 参.prior_right = {先验对 或 0.25}
设 参.prior_wrong = {先验错 或 1.25}
设 参.hard_right = {难题对 或 1.3}
设 参.easy_wrong = {易题错 或 1.3}
设 算 = 查一行表 app.db score_calc {参}

如果 {算.n 或 0} 等于 0
  返回 {"changed":"0","before":"","after":"","label":"","text":""}
结束

设 旧 = {算.prev 或}
设 说法 = {算.label} 得分 {旧} → {算.value}
如果 {旧} 为空
  设 说法 = {算.label} 得分 {算.value}（第一次打分）
结束

如果 {算.changed} 等于 0
  设 说法 = {算.label} 得分 {算.value}（没变）
  返回 {"changed":"0","before":"{旧}","after":"{算.value}","label":"{算.label}","text":"{说法}"}
结束

设 记.learner = {学习者}
设 记.point = {知识点}
设 记.value = {算.value}
设 影响 = 写库表 app.db score_add {记}
返回 {"changed":"1","before":"{旧}","after":"{算.value}","label":"{算.label}","text":"{说法}"}
