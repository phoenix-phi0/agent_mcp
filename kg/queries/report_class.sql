-- 学情页的全班表：每个学生一行。只读。
--
-- 谁算「学生」：user 表里 role = student 的，加上有学习记录（作答、默写、问老师）
-- 的学习者——单人模式没有账号，学习者是 me 这类名字，也要列出来。教师账号一律
-- 不算（多人模式下教师碰不到学习接口，库里早先留下的也不列）。
--
--   label         显示名，没有就是用户名
--   last_active   最近学习：作答、默写、问老师里最晚的一条
--   attempt_n     做题作答数
--   recent_rate   近期正确率：最近 20 道（按 id），没答过是「—」
--   avg_score     平均得分：打过分的知识点各取当前分再平均，没打过是「—」
--   mastered_n    已掌握的知识点数（mastery.mastered）
--   weak_points   薄弱知识点前 3：当前分低于 80（达标线）的，分低的在前
--   book_n        默写错词本几个（两个方向各算，规则同 dictation_stats.sql）
--   href          点名字进这个学生（#学情?student=…）
--
-- :sort  最近学习（默认，最近的在前）/ 平均得分（低的在前，没打过分的排最后）
WITH who AS (
  SELECT username AS learner FROM user WHERE role = 'student'
  UNION SELECT learner FROM attempt
  UNION SELECT learner FROM word_attempt
  UNION SELECT learner FROM chat_message
),
roster AS (
  SELECT w.learner FROM who w
  WHERE coalesce(w.learner, '') <> ''
    AND NOT EXISTS (SELECT 1 FROM user t WHERE t.username = w.learner AND t.role = 'teacher')
),
cur AS (
  SELECT s.learner, s.point, s.value, s.id FROM score s
  WHERE s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
),
sc AS (
  SELECT learner, CAST(round(avg(1.0 * value)) AS INTEGER) AS avg FROM cur GROUP BY learner
),
last_wrong AS (
  SELECT learner, word, direction, max(id) AS wid
  FROM word_attempt WHERE correct = 0
  GROUP BY learner, word, direction
),
book AS (
  SELECT lw.learner, count(*) AS n
  FROM last_wrong lw
  JOIN word w ON w.id = lw.word
  WHERE (SELECT count(*) FROM word_attempt x
          WHERE x.learner = lw.learner AND x.direction = lw.direction
            AND x.word = lw.word AND x.id > lw.wid
            AND x.correct = 1 AND x.hinted = 0) < 2
  GROUP BY lw.learner
),
class_rows AS (
  SELECT r.learner AS username,
         coalesce(nullif(u.display_name, ''), r.learner) AS label,
         coalesce((SELECT max(t) FROM (
             SELECT max(at) AS t FROM attempt WHERE learner = r.learner
             UNION ALL SELECT max(at) FROM word_attempt WHERE learner = r.learner
             UNION ALL SELECT max(created) FROM chat_message WHERE learner = r.learner)), '') AS last_active,
         (SELECT count(*) FROM attempt a WHERE a.learner = r.learner) AS attempt_n,
         (SELECT CASE WHEN count(*) > 0 THEN (sum(correct) * 100 / count(*)) || '%' ELSE '—' END
            FROM (SELECT correct FROM attempt WHERE learner = r.learner ORDER BY id DESC LIMIT 20)) AS recent_rate,
         sc.avg AS avg_num,
         coalesce(CAST(sc.avg AS TEXT), '—') AS avg_score,
         (SELECT count(*) FROM mastery m WHERE m.learner = r.learner AND m.mastered = 1) AS mastered_n,
         coalesce((SELECT group_concat(label, '、') FROM (
             SELECT n.label FROM cur c JOIN node n ON n.code = c.point
             WHERE c.learner = r.learner AND c.value < 80
             ORDER BY c.value, c.id DESC LIMIT 3)), '—') AS weak_points,
         coalesce(book.n, 0) AS book_n,
         '#%E5%AD%A6%E6%83%85?student=' || r.learner AS href
  FROM roster r
  LEFT JOIN user u ON u.username = r.learner
  LEFT JOIN sc ON sc.learner = r.learner
  LEFT JOIN book ON book.learner = r.learner
)
SELECT * FROM class_rows
ORDER BY
  CASE WHEN :sort = '平均得分' THEN (avg_num IS NULL) ELSE 0 END,
  CASE WHEN :sort = '平均得分' THEN avg_num END,
  last_active DESC,
  username
