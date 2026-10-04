-- 记一次作答。只进不改。
--
-- at 不填，让列的默认值填：实体里「默认 现在」渲染成
-- datetime('now','localtime')，是本地时间。早先这里自己写了
-- datetime('now')——那是 UTC，跟列默认值差 9 小时，同一个库里两种时间混着。
INSERT INTO attempt(learner, point, item, correct)
VALUES(:learner, :point, :item, CAST(:correct AS INTEGER))
