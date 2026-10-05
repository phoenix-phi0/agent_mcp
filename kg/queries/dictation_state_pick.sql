-- 出了一个新词：记下方向、等级、题源和当前词，清掉上一个的作答和提示。
-- :reset 为 1（开始、再来一轮、练错词）时这一轮清零、重记起点（word_attempt
-- 当时最大的 id，一轮结束列错词用）；0（下一个）接着算。
-- :seen 是这一轮已出过的词（新一轮是空串），这个词追加进去，round_n 加一。
INSERT INTO dictation_state(learner, dict_direction, dict_level, dict_source,
                            current_word, answered, hinted, round_seen, round_n,
                            round_right, round_total, round_from)
VALUES(:learner, :direction_label, :level, :source_label,
       CAST(:word AS INTEGER), 0, 0, ',' || :word || ',', 1, 0, 0,
       (SELECT coalesce(max(id), 0) FROM word_attempt))
ON CONFLICT(learner) DO UPDATE SET
  dict_direction = :direction_label,
  dict_level = :level,
  dict_source = :source_label,
  current_word = CAST(:word AS INTEGER),
  answered = 0,
  hinted = 0,
  dict_answer = NULL,
  round_seen = (CASE WHEN :seen = '' THEN ',' ELSE :seen END) || :word || ',',
  round_n = CAST(:n AS INTEGER) + 1,
  round_right = CASE WHEN CAST(:reset AS INTEGER) = 1 THEN 0 ELSE round_right END,
  round_total = CASE WHEN CAST(:reset AS INTEGER) = 1 THEN 0 ELSE round_total END,
  round_from = CASE WHEN CAST(:reset AS INTEGER) = 1
                    THEN (SELECT coalesce(max(id), 0) FROM word_attempt) ELSE round_from END
