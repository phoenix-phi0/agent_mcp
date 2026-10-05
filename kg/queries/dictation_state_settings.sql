-- 只记下方向、等级、题源（挑不出词、一轮结束时用：不出题，但下次进页面
-- 顶栏还是这次选的）。没有这一行就建一行，计数都是 0。
INSERT INTO dictation_state(learner, dict_direction, dict_level, dict_source)
VALUES(:learner, :direction_label, :level, :source_label)
ON CONFLICT(learner) DO UPDATE SET
  dict_direction = :direction_label,
  dict_level = :level,
  dict_source = :source_label
