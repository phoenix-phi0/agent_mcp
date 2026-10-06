-- 这一轮已经总结过的话，老师那条总结的正文；没总结过就没有行。
-- :round_key 是 round_attempts 的 round_key（这一轮的起点 - 最后一道作答的
-- id），/quiz/summary 调模型前查一次（总结过就不再调），写库前在事务里再查
-- 一次（两个请求前后脚都调了模型，只有先写的那个写进去）。
SELECT content FROM chat_message
WHERE learner = :learner AND role = 'teacher' AND intent = '总结'
  AND round_key = :round_key AND :round_key <> ''
ORDER BY id DESC
LIMIT 1
