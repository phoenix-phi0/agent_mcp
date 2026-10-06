-- 记一条老师回复用了哪些教师设定：这个学习者刚写进去的老师那条（最大的 id）。
-- 跟 chat_add 在同一个事务里，模型出错时整轮不记，「只用于下一条」不被消耗。
-- note_ids 空的不记（HAVING 挡住，聚合在没有行时也会出一行 NULL）。
INSERT INTO chat_note_use(message_id, learner, note_ids)
SELECT max(id), :learner, :note_ids FROM chat_message
WHERE learner = :learner AND role = 'teacher'
HAVING :note_ids <> '' AND max(id) IS NOT NULL
