-- 一个人的做题进度。没做过题就没有这一行（查一行表 得到空对象）。
SELECT learner, pick_level, pick_kind, COALESCE(current, '') AS current,
       answered, right, total,
       '这一轮 ' || right || '/' || total AS stat
FROM quiz_state
WHERE learner = :learner
