-- 记一条老师回复带了哪条传达（scripts/teacher_notes.zs 挑的那一条）：这个学习者刚
-- 写进去的老师那条（最大的 id）。跟 chat_add 在同一个事务里，模型出错时整轮不记。
-- urgency 是这次实际用的紧急程度（升级过的是「立即」）。判定在后台跑完再改 verdict。
INSERT INTO relay_use(message_id, relay_id, learner, urgency, verdict)
SELECT max(id), CAST(:relay_id AS INTEGER), :learner, :urgency, '待判定' FROM chat_message
WHERE learner = :learner AND role = 'teacher'
HAVING :relay_id <> '' AND max(id) IS NOT NULL
