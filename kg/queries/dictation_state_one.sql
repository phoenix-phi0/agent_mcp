-- 一个人的默写进度。没默写过就没有这一行（查一行表 得到空对象）。
-- direction 是方向的代号（meaning / reading），界面上的下拉是中文。
SELECT learner, dict_direction, dict_level, dict_source,
       coalesce(current_word, '') AS current_word,
       answered, hinted,
       coalesce(round_seen, '') AS round_seen,
       round_n, round_right, round_total, round_from,
       CASE WHEN dict_direction = '看汉字写读音' THEN 'reading' ELSE 'meaning' END AS direction,
       '这一轮 ' || round_right || '/' || round_total AS stat
FROM dictation_state
WHERE learner = :learner
