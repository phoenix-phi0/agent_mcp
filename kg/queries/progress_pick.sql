-- 按进度推荐一课：问老师「进度」「教材」意图用（routes/teacher.zs），给回复
-- 附「读课文」「练这一课」的链接。
--
-- 先挑最近答错、还没掌握的那个点所在的课（错题的 question.lesson，复习）；
-- 没有就挑「现在能学」（learn_next 同一套：没掌握、前置都掌握了）的知识点
-- 挂着的课，依赖浅的在前。同一档里有题的课在前，N5 在前。
--
-- 两样都没有（还没答过题、能学的点都没挂课文，或者这一级里对不上）就按
-- 顺序推这一级有题的第一课。
--
-- :level  认出等级（同 progress_brief）就只在这一级里挑，认不出不限（N5 在
--         前）。教材里一课都没有才查不到行，脚本退到按等级做题。
--
-- read 是教材页读这一课的地址，practice 是做题页按这一课出题的地址（没题
-- 时空串），写法跟 lesson_list / lesson_one 一样（界面名编过码）。
WITH RECURSIVE d(code, depth) AS (
  SELECT code, 0 FROM node WHERE code NOT IN (SELECT dst FROM prereq)
  UNION
  SELECT p.dst, d.depth + 1 FROM prereq p JOIN d ON p.src = d.code
),
lvl AS (
  SELECT CASE WHEN instr(upper(coalesce(:level, '')), 'N5') > 0 THEN 'N5'
              WHEN instr(upper(coalesce(:level, '')), 'N4') > 0 THEN 'N4'
              WHEN instr(upper(coalesce(:level, '')), 'N3') > 0 THEN 'N3'
              WHEN instr(upper(coalesce(:level, '')), 'N2') > 0 THEN 'N2'
              WHEN instr(upper(coalesce(:level, '')), 'N1') > 0 THEN 'N1'
              ELSE '' END AS v
),
done AS (
  SELECT point FROM mastery WHERE learner = :learner AND mastered = 1
),
nxt AS (
  SELECT n.code, n.label, coalesce(max(d.depth), 0) AS depth
  FROM node n LEFT JOIN d ON d.code = n.code
  WHERE n.code NOT IN (SELECT point FROM done)
    AND NOT EXISTS (SELECT 1 FROM prereq e
                    WHERE e.dst = n.code AND e.src NOT IN (SELECT point FROM done))
  GROUP BY n.code, n.label
),
cand AS (
  SELECT 1 AS pri, -max(x.id) AS ord, q.lesson,
         '最近答错过「' || coalesce(n.label, x.point) || '」，先复习' AS reason
  FROM attempt x
  JOIN question q ON q.code = x.item
  LEFT JOIN node n ON n.code = x.point
  WHERE x.learner = :learner AND x.correct = 0 AND q.lesson IS NOT NULL
    AND x.point NOT IN (SELECT point FROM done)
  GROUP BY q.lesson
  UNION ALL
  SELECT 2, x.depth, il.lesson,
         '「' || x.label || '」的前置都掌握了，现在能学'
  FROM nxt x
  JOIN item i ON i.point = x.code
  JOIN item_lesson il ON il.item = i.code
  UNION ALL
  SELECT 3, 0, code, '按顺序从这一级的课开始' FROM lesson
)
SELECT l.code, l.level, l.title, l.summary, c.reason,
       (SELECT count(*) FROM question q WHERE q.lesson = l.code) AS qcount,
       '#%E6%95%99%E6%9D%90?lesson=' || l.code AS read,
       CASE WHEN (SELECT count(*) FROM question q WHERE q.lesson = l.code) > 0
            THEN '#%E5%81%9A%E9%A2%98?lesson=' || l.code ELSE '' END AS practice
FROM cand c JOIN lesson l ON l.code = c.lesson, lvl
WHERE lvl.v = '' OR l.level = lvl.v
ORDER BY c.pri, c.ord,
         (SELECT count(*) FROM question q WHERE q.lesson = l.code) > 0 DESC,
         l.level DESC, l.code
LIMIT 1
