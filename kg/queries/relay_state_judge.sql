-- 判定的结论写回这个（传达，学生）的状态。:verdict 是 relay_verdict 归出来的：
--   已传达    状态已传达，记那条回复、AI 原话摘录、时间，以后不再带入
--   有误      第一次：传达有误（再带一次，提示词里要求更正）；第二次：有误已停止
--             （不再带，等老师处理）。说错的那句也记下来给老师看
--   未传达 / 判定失败   没传达到的次数加一（到 relay_rounds 升级为立即）
-- 只改还在传达中的（待传达、传达有误）：学生连发两句、两次判定交错时，已经判成
-- 已传达的不会被后一次「未传达」改回去。
UPDATE relay_state
SET status = CASE :verdict
               WHEN '已传达' THEN '已传达'
               WHEN '有误' THEN CASE WHEN wrong_n + 1 >= 2 THEN '有误已停止' ELSE '传达有误' END
               ELSE status END,
    miss_n = miss_n + CASE WHEN :verdict IN ('未传达', '判定失败') THEN 1 ELSE 0 END,
    wrong_n = wrong_n + CASE WHEN :verdict = '有误' THEN 1 ELSE 0 END,
    message_id = CASE WHEN :verdict IN ('已传达', '有误')
                      THEN (SELECT message_id FROM relay_use WHERE id = CAST(:use_id AS INTEGER))
                      ELSE message_id END,
    excerpt = CASE WHEN :verdict IN ('已传达', '有误') THEN :quote ELSE excerpt END,
    delivered_at = CASE WHEN :verdict = '已传达' THEN datetime('now', 'localtime') ELSE delivered_at END,
    state_updated = datetime('now', 'localtime')
WHERE relay_id = (SELECT relay_id FROM relay_use WHERE id = CAST(:use_id AS INTEGER))
  AND learner = (SELECT learner FROM relay_use WHERE id = CAST(:use_id AS INTEGER))
  AND status IN ('待传达', '传达有误')
