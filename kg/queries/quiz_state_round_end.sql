-- 自由练「结束并请老师总结」：老师总结完，这一轮就此结束——起点挪到现在
-- （attempt 当时最大的 id），计数清零。接着做就是新的一轮，再请总结不会
-- 把总结过的题再算一遍。按课练不走这里（「再来一轮」才开新一轮）。
UPDATE quiz_state
SET round_from = (SELECT coalesce(max(id), 0) FROM attempt),
    right = 0,
    total = 0
WHERE learner = :learner
