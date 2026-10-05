-- 按等级、考点抽一道题，只要题号。「全部」或空表示不限。
-- 按课练走 question_pick_lesson.sql（要混对比题、要知道一轮做完没有）。
--
-- 排序三档：刚出过的那道（:last）放最后，免得连着出同一道；然后没做过的
-- 在前（这个人在这道题上还没有作答记录）；同一档里随机。
SELECT q.code
FROM question q
WHERE (:level IN ('', '全部') OR q.level = :level)
  AND (:kind IN ('', '全部') OR q.kind = :kind)
ORDER BY
  q.code = :last,
  EXISTS (SELECT 1 FROM attempt a WHERE a.learner = :learner AND a.item = q.code),
  random()
LIMIT 1
