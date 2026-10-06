-- 学情页点进一个学生：抬头。查不到（不是学生、也没有任何学习记录）时 found = 0。
-- 教师账号算查不到。只读。
--
--   label        显示名（没有就是用户名）
--   series_label 当前教材系列（同 series_current：偏好里记的，没有是 hanabira）
--   last_active  最近学习
--   head         抬头那一行
--   back         回全班表
WITH me AS (
  SELECT :student AS learner
),
known AS (
  SELECT CASE WHEN EXISTS (SELECT 1 FROM user t WHERE t.username = me.learner AND t.role = 'teacher') THEN 0
              WHEN EXISTS (SELECT 1 FROM user s WHERE s.username = me.learner AND s.role = 'student')
                OR EXISTS (SELECT 1 FROM attempt WHERE learner = me.learner)
                OR EXISTS (SELECT 1 FROM word_attempt WHERE learner = me.learner)
                OR EXISTS (SELECT 1 FROM chat_message WHERE learner = me.learner) THEN 1
              ELSE 0 END AS found
  FROM me
),
pick AS (
  SELECT coalesce((SELECT p.series FROM learner_pref p, me
                   WHERE p.learner = me.learner
                     AND EXISTS (SELECT 1 FROM series s WHERE s.code = p.series AND s.sort >= 0)),
                  'hanabira') AS code
)
SELECT me.learner AS username,
       known.found,
       coalesce(nullif(u.display_name, ''), me.learner) AS label,
       coalesce(s.label, pick.code) AS series_label,
       coalesce((SELECT max(t) FROM (
           SELECT max(at) AS t FROM attempt WHERE learner = me.learner
           UNION ALL SELECT max(at) FROM word_attempt WHERE learner = me.learner
           UNION ALL SELECT max(created) FROM chat_message WHERE learner = me.learner)), '') AS last_active,
       coalesce(nullif(u.display_name, ''), me.learner) || '（' || me.learner || '）　教材：'
         || coalesce(s.label, pick.code) || '　最近学习：'
         || coalesce((SELECT max(t) FROM (
             SELECT max(at) AS t FROM attempt WHERE learner = me.learner
             UNION ALL SELECT max(at) FROM word_attempt WHERE learner = me.learner
             UNION ALL SELECT max(created) FROM chat_message WHERE learner = me.learner)), '还没有') AS head,
       '#%E5%AD%A6%E6%83%85' AS back
FROM me, known, pick
LEFT JOIN user u ON u.username = me.learner
LEFT JOIN series s ON s.code = pick.code
