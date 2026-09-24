-- 删一条错题本。
DELETE FROM wrong
WHERE learner = :learner
