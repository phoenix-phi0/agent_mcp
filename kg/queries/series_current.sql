-- 这个学习者现在用哪个系列：learner_pref 里记的，没记过（或者记的系列已经
-- 不在 series 表里）就是 hanabira。{code, label}，label 取不到就用编号。
WITH pick AS (
  SELECT coalesce((SELECT p.series FROM learner_pref p
                   WHERE p.learner = :learner
                     AND EXISTS (SELECT 1 FROM series s WHERE s.code = p.series)),
                  'hanabira') AS code
)
SELECT pick.code, coalesce(s.label, pick.code) AS label
FROM pick LEFT JOIN series s ON s.code = pick.code
