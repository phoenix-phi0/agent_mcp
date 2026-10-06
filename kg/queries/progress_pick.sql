-- 按进度推荐一课：问老师「进度」「教材」意图用（routes/teacher.zs），给回复
-- 附「读课文」「练这一课」的链接。
--
-- 先挑掌握得分最低的点（当前分低于 :score_line 的，最低的在前）的题所在
-- 的课——得分是按做题情况算的（queries/score_calc.sql），比「最近答错过」
-- 更能看出哪里薄弱；不看 mastered：达标了但最近连错、分掉下去的也该复习。
-- 没有低分点（还没打过分，或者都不低于线）退回原来的顺序：最近答错、还没
-- 掌握的那个点所在的课（错题的 question.lesson，复习）；没有就挑「现在能学」（learn_next 同一套：没掌握、前置都掌握了）的知识点
-- 挂着的课，依赖浅的在前。同一档里有题的课在前，N5 在前。
--
-- 两样都没有（还没答过题、能学的点都没挂课文，或者这一级里对不上）就按
-- 顺序推这一级有题的第一课。
--
-- :level  认出等级（同 progress_brief）就只在这一级里挑，认不出不限（N5 在
--         前）。教材里一课都没有才查不到行，脚本退到按等级做题。
-- :score_line  低分线（整数，调用方给，routes/teacher.zs 里是 80，跟达标的
--         正确率同一个数）。
--
-- read 是教材页读这一课的地址，practice 是做题页按这一课出题的地址（没题
-- 时空串），写法跟 lesson_list / lesson_one 一样（界面名编过码）。
--
-- 只推学习者当前系列（learner_pref，没记过是 hanabira）里的课。知识点、得分
-- 是跨系列共享的，换了系列推的是新系列里讲这些点的课。
--
-- lq 是「课的题」：hanabira 的题库按课文编号打了标（question.lesson），照旧按
-- 标；别的系列的课没有自己的题，按映射取——挂着的条目（item_lesson）的题，
-- 加上直接挂的知识点（lesson_point）下所有条目的题。几个课文查询里是同一段。
WITH RECURSIVE d(code, depth) AS (
  SELECT code, 0 FROM node WHERE code NOT IN (SELECT dst FROM prereq)
  UNION
  SELECT p.dst, d.depth + 1 FROM prereq p JOIN d ON p.src = d.code
),
lq AS (
  SELECT q.lesson AS lesson, q.code, q.item FROM question q WHERE q.lesson IS NOT NULL
  UNION
  SELECT l.code, q.code, q.item FROM lesson l
  JOIN item_lesson il ON il.lesson = l.code JOIN question q ON q.item = il.item
  WHERE l.series <> 'hanabira'
  UNION
  SELECT l.code, q.code, q.item FROM lesson l
  JOIN lesson_point lp ON lp.lesson = l.code JOIN item i ON i.point = lp.point
  JOIN question q ON q.item = i.code
  WHERE l.series <> 'hanabira'
),
qn AS (
  SELECT lesson, count(*) AS n FROM lq GROUP BY lesson
),
cur AS (
  SELECT coalesce((SELECT p.series FROM learner_pref p
                   WHERE p.learner = :learner
                     AND EXISTS (SELECT 1 FROM series s WHERE s.code = p.series)),
                  'hanabira') AS s
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
low AS (
  SELECT s.point, s.value, s.id
  FROM score s
  WHERE s.learner = :learner
    AND s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
    AND s.value < CAST(:score_line AS INTEGER)
),
cand AS (
  -- 低分点的课：同一个点挂着好几课时，先推这个人在里面答错过的那课（最近
  -- 错的在前），没错过的课排后
  SELECT 0 AS pri, w.value AS ord,
         -coalesce((SELECT max(x.id) FROM attempt x
                    JOIN lq q2 ON q2.code = x.item
                    WHERE x.learner = :learner AND x.correct = 0
                      AND x.point = w.point AND q2.lesson = pl.lesson), 0) AS sub,
         pl.lesson,
         '「' || coalesce(n.label, w.point) || '」掌握得分 ' || w.value || '，偏低，先复习' AS reason
  FROM low w
  JOIN (SELECT DISTINCT i.point, q.lesson FROM item i
        JOIN lq q ON q.item = i.code) pl ON pl.point = w.point
  LEFT JOIN node n ON n.code = w.point
  UNION ALL
  SELECT 1 AS pri, -max(x.id) AS ord, 0, q.lesson,
         '最近答错过「' || coalesce(n.label, x.point) || '」，先复习' AS reason
  FROM attempt x
  JOIN lq q ON q.code = x.item
  LEFT JOIN node n ON n.code = x.point
  WHERE x.learner = :learner AND x.correct = 0
    AND x.point NOT IN (SELECT point FROM done)
  GROUP BY q.lesson
  UNION ALL
  SELECT 2, x.depth, 0, il.lesson,
         '「' || x.label || '」的前置都掌握了，现在能学'
  FROM nxt x
  JOIN item i ON i.point = x.code
  JOIN item_lesson il ON il.item = i.code
  UNION ALL
  SELECT 2, x.depth, 0, lp.lesson,
         '「' || x.label || '」的前置都掌握了，现在能学'
  FROM nxt x
  JOIN lesson_point lp ON lp.point = x.code
  UNION ALL
  SELECT 3, 0, 0, code, '按顺序从这一级的课开始' FROM lesson
)
SELECT l.code, l.level, l.title, l.summary, c.reason,
       coalesce((SELECT n FROM qn WHERE qn.lesson = l.code), 0) AS qcount,
       '#%E6%95%99%E6%9D%90?lesson=' || l.code AS read,
       CASE WHEN coalesce((SELECT n FROM qn WHERE qn.lesson = l.code), 0) > 0
            THEN '#%E5%81%9A%E9%A2%98?lesson=' || l.code ELSE '' END AS practice
FROM cand c JOIN lesson l ON l.code = c.lesson, lvl, cur
WHERE l.series = cur.s AND (lvl.v = '' OR l.level = lvl.v)
ORDER BY c.pri, c.ord, c.sub,
         coalesce((SELECT n FROM qn WHERE qn.lesson = l.code), 0) > 0 DESC,
         l.level DESC, coalesce(l.seq, 0), l.code
LIMIT 1
