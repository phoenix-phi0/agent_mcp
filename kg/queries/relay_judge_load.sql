-- 后台判定（scripts/relay_judge.zs）要的材料：这次带的是哪条传达、老师那条回复的原文。
-- 传达后来删了的、回复找不到的没有行。
SELECT u.id AS use_id, u.relay_id, u.learner, u.message_id,
       r.relay_point, coalesce(r.relay_facts, '') AS relay_facts,
       m.content AS reply
FROM relay_use u
JOIN teacher_relay r ON r.id = u.relay_id
JOIN chat_message m ON m.id = u.message_id
WHERE u.id = CAST(:use_id AS INTEGER)
