-- 出了一道新题：记下筛选条件和当前题，清掉上一道的作答。
-- :reset 为 1（点「开始」、按课进来、再来一轮）时这一轮的计数清零；「下一题」接着算。
--
-- 三种模式都把这道题号追加进 round_seen（:seen 是调用方给的这一轮已出过的，
-- 新一轮时是空串），round_n 加一：一轮里每个条目只出一题，抽题要看这一轮
-- 出过哪些题（它们的条目），一轮够数就结束。
-- 按课练（:lesson 不空）：记下在练哪一课；:lesson 空就清掉——点「开始」
-- 就退出按课模式。
-- 复习薄弱点（:mode = review）：lesson 空，mode 记 review。:mode 空就是
-- 清掉——「开始」「按课进来」都退出复习模式。
-- round_from 是这一轮的起点（attempt 当时最大的 id），:reset 为 1 时重记——
-- 这一轮做了哪些题由它划（round_attempts.sql，请老师总结用）。
-- seq 每出一道都加一：选项打乱的种子是「学习者|题号|seq」，同一道题下次
-- 再出顺序就不一样，而这一道出题和判题时 seq 相同、顺序对得上。
INSERT INTO quiz_state(learner, pick_level, pick_kind, current, answered, right, total,
                       lesson, round_seen, round_n, seq, round_from, mode)
VALUES(:learner, :level, :kind, :code, 0, 0, 0,
       NULLIF(:lesson, ''),
       ',' || :code || ',',
       1,
       1,
       (SELECT coalesce(max(id), 0) FROM attempt),
       NULLIF(:mode, ''))
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
  round_seen = (CASE WHEN :seen = '' THEN ',' ELSE :seen END) || :code || ',',
  round_n = CAST(:n AS INTEGER) + 1,
  mode = NULLIF(:mode, ''),
  seq = seq + 1,
  round_from = CASE WHEN CAST(:reset AS INTEGER) = 1
                    THEN (SELECT coalesce(max(id), 0) FROM attempt) ELSE round_from END
