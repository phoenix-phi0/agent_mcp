-- 教材页的课文表用哪个系列：这次选的（:series，下拉里有的、没撤下的）优先，
-- 没选或选的不算数就跟 series_current 一样——这个学习者的偏好，没有是 hanabira。
--
-- 学生选了系列时 lesson_list 先把偏好写好了，两条结果一样；教师不记偏好
-- （learner 是空串），靠这里让下拉选的系列照样生效。{code, label}
WITH pick AS (
  SELECT coalesce(
           (SELECT s.code FROM series s WHERE s.code = :series AND s.sort >= 0),
           (SELECT p.series FROM learner_pref p
             WHERE p.learner = :learner
               AND EXISTS (SELECT 1 FROM series s WHERE s.code = p.series AND s.sort >= 0)),
           'hanabira') AS code
)
SELECT pick.code, coalesce(s.label, pick.code) AS label
FROM pick LEFT JOIN series s ON s.code = pick.code
