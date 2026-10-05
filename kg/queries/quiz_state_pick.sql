-- 出了一道新题：记下筛选条件和当前题，清掉上一道的作答。
-- :reset 为 1（点「开始」、按课进来、再来一轮）时这一轮的计数清零；「下一题」接着算。
--
-- 按课练（:lesson 不空）：记下在练哪一课，这道题号追加进 round_seen
-- （:seen 是调用方给的这一轮已出过的，新一轮时是空串），round_n 加一。
-- 按等级考点（:lesson 空）：这三样都清掉——点「开始」就退出按课模式。
-- round_from 是这一轮的起点（attempt 当时最大的 id），:reset 为 1 时重记——
-- 这一轮做了哪些题由它划（round_attempts.sql，请老师总结用）。
-- seq 每出一道都加一：选项打乱的种子是「学习者|题号|seq」，同一道题下次
-- 再出顺序就不一样，而这一道出题和判题时 seq 相同、顺序对得上。
INSERT INTO quiz_state(learner, pick_level, pick_kind, current, answered, right, total,
                       lesson, round_seen, round_n, seq, round_from)
VALUES(:learner, :level, :kind, :code, 0, 0, 0,
       NULLIF(:lesson, ''),
       CASE WHEN :lesson <> '' THEN ',' || :code || ',' ELSE '' END,
       CASE WHEN :lesson <> '' THEN 1 ELSE 0 END,
       1,
       (SELECT coalesce(max(id), 0) FROM attempt))
ON CONFLICT(learner) DO UPDATE SET
  pick_level = :level,
  pick_kind = :kind,
  current = :code,
  answered = 0,
  choice = NULL,
  given = NULL,
  right = CASE WHEN CAST(:reset AS INTEGER) = 1 THEN 0 ELSE right END,
  total = CASE WHEN CAST(:reset AS INTEGER) = 1 THEN 0 ELSE total END,
  lesson = NULLIF(:lesson, ''),
  round_seen = CASE WHEN :lesson <> ''
                    THEN (CASE WHEN :seen = '' THEN ',' ELSE :seen END) || :code || ','
                    ELSE '' END,
  round_n = CASE WHEN :lesson <> '' THEN CAST(:n AS INTEGER) + 1 ELSE 0 END,
  seq = seq + 1,
  round_from = CASE WHEN CAST(:reset AS INTEGER) = 1
                    THEN (SELECT coalesce(max(id), 0) FROM attempt) ELSE round_from END
