-- 一个人在各个知识点上的当前得分：每个点取最新的那一次。
--
-- 「最新」按 id 取，不按 at：同一秒里打两次分，at 一样，按 at 取会随机
-- 挑一行；id 是插入顺序，不会撞。
--
-- :point 给了就只看那一个点，空串表示全部。没打过分的点不出现——没分
-- 就是没分，不填 0（0 分是「打过、完全不会」，跟没打过不是一回事）。
--
-- times 是这个点一共打过几次，看历史之前先知道有没有可看的。
SELECT s.point AS code,
       n.label,
       s.value,
       s.at,
       (SELECT count(*) FROM score c
         WHERE c.learner = s.learner AND c.point = s.point) AS times
FROM score s
JOIN node n ON n.code = s.point
WHERE s.learner = :learner
  AND (:point = '' OR s.point = :point)
  AND s.id = (SELECT max(m.id) FROM score m
               WHERE m.learner = s.learner AND m.point = s.point)
ORDER BY s.point
