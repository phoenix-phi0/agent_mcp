-- 抽一道题，只要题号。
--
-- 给了 :lesson 就只在这一课的题里抽，等级和考点不管（地址带课文进来时，
-- 页面上的等级下拉可能还停在别的等级，按它筛就一道都没有）。没给课文时
-- 按等级、考点筛，「全部」或空表示不限。
--
-- 排序三档：刚出过的那道（:last）放最后，免得连着出同一道；然后没做过的
-- 在前（这个人在这道题上还没有作答记录）；同一档里随机。
SELECT q.code
FROM question q
WHERE CASE WHEN :lesson <> '' THEN q.lesson = :lesson
           ELSE (:level IN ('', '全部') OR q.level = :level)
            AND (:kind IN ('', '全部') OR q.kind = :kind)
      END
ORDER BY
  q.code = :last,
  EXISTS (SELECT 1 FROM attempt a WHERE a.learner = :learner AND a.item = q.code),
  random()
LIMIT 1
