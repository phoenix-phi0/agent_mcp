-- 这个学习者现在用哪个系列：learner_pref 里记的，没记过（或者记的系列已经
-- 不在 series 表里、已经撤下了——sort < 0）就是 hanabira。{code, label}，label
-- 取不到就用编号。偏好那一行不改：撤下的系列重新上架，学习者回到原来的选择。
WITH pick AS (
  SELECT coalesce((SELECT p.series FROM learner_pref p
                   WHERE p.learner = :learner
                     AND EXISTS (SELECT 1 FROM series s WHERE s.code = p.series AND s.sort >= 0)),
                  'hanabira') AS code
)
SELECT pick.code, coalesce(s.label, pick.code) AS label
FROM pick LEFT JOIN series s ON s.code = pick.code
