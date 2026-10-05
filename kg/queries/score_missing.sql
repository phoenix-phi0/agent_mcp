-- 回填用：有作答、还没有得分的（学习者, 知识点）。/score/rebuild 逐个补算
-- 一次当前分。已经有得分的点不在这里——回填只补缺，不改旧行。
--
-- :learner 给了就只看这个人，空串表示所有人。
SELECT DISTINCT a.learner, a.point
FROM attempt a
WHERE (:learner = '' OR a.learner = :learner)
  AND NOT EXISTS (SELECT 1 FROM score s
                  WHERE s.learner = a.learner AND s.point = a.point)
ORDER BY a.learner, a.point
