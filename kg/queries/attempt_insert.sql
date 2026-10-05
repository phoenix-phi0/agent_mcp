-- 记一次作答。只进不改。
--
-- at 不填，让列的默认值填：实体里「默认 现在」渲染成
-- datetime('now','localtime')，是本地时间。早先这里自己写了
-- datetime('now')——那是 UTC，跟列默认值差 9 小时，同一个库里两种时间混着。
--
-- answer 是交上来的作答（做题页：选择题的原字母、接续题写的那段；
-- /learn/answer 不给，记 NULL）。
INSERT INTO attempt(learner, point, item, correct, answer)
VALUES(:learner, :point, :item, CAST(:correct AS INTEGER), NULLIF(:answer, ''))
