-- 一个人的做题进度。没做过题就没有这一行（查一行表 得到空对象）。
-- lesson 空就是按等级考点出（mode = review 是复习薄弱点）；seq 是选项打乱的种子的一部分（见「拆选项」）。
SELECT learner, pick_level, pick_kind, COALESCE(current, '') AS current,
       answered, right, total,
       COALESCE(lesson, '') AS lesson,
       COALESCE(round_seen, '') AS round_seen,
       round_n, seq,
       COALESCE(mode, '') AS mode,
       '这一轮 ' || right || '/' || total AS stat
FROM quiz_state
WHERE learner = :learner
