-- 学习进度摘要：一段文字，问老师拼进提示词（routes/teacher.zs）。数字跟
-- 学习进度页同一套算法（progress_overview / progress_doing / progress_recent /
-- progress_levels / learn_next），只是压成几行、截到 800 字。
--
-- :learner    学习者
-- :line       达标线（掌握得分），:keep 回落线——跟进度页一样现算（mastery_one.sql）
-- :level      意图判定给的等级（N4、n4、「N4级」都认），认出来时多一行「这一级
--             还没掌握的知识点」；认不出当没给
--
-- 一道都没答过时写「还没有作答记录」，不列在学、答错（列了也是「无」，
-- 模型反而容易从「无」里编出东西来）。
--
-- 掌握得分：在学的点（有作答的）各取当前分，低的在前，最多 8 个，一行
-- 「在学知识点的掌握得分」——老师给建议时先顾低分点。一个都没打过分就
-- 不写这一行（同上，不给「无」）。
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
a AS (
  SELECT count(*) AS n, coalesce(sum(correct), 0) AS r
  FROM attempt WHERE learner = :learner
),
cur AS (
  SELECT s.point, s.value FROM score s
  WHERE s.learner = :learner
    AND s.id = (SELECT max(x.id) FROM score x
                 WHERE x.learner = s.learner AND x.point = s.point)
),
doing AS (
  SELECT n.label || ' ' || m.right || '/' || m.total || '（' ||
         CASE WHEN c.value IS NULL THEN '还没打分'
              WHEN c.value >= CAST(:line AS INTEGER)
                OR (m.mastered = 1 AND c.value >= CAST(:keep AS INTEGER)) THEN '达标'
              ELSE '得分差 ' || (CAST(:line AS INTEGER) - c.value) || ' 分'
         END || '）' AS s
  FROM mastery m JOIN node n ON n.code = m.point
  LEFT JOIN cur c ON c.point = m.point
  WHERE m.learner = :learner AND m.total > 0
  ORDER BY m.updated DESC, m.id DESC
  LIMIT 8
),
sc AS (
  SELECT n.label || ' ' || s.value AS s
  FROM score s JOIN node n ON n.code = s.point
  WHERE s.learner = :learner
    AND s.id = (SELECT max(m.id) FROM score m
                 WHERE m.learner = s.learner AND m.point = s.point)
    AND s.point IN (SELECT point FROM mastery WHERE learner = :learner AND total > 0)
  ORDER BY s.value, s.id DESC
  LIMIT 8
),
wrong AS (
  SELECT s FROM (
    SELECT coalesce(n.label, x.point)
           || CASE WHEN coalesce(i.label, '') <> '' THEN '·' || i.label ELSE '' END AS s,
           max(x.id) AS last
    FROM attempt x
    LEFT JOIN node n ON n.code = x.point
    LEFT JOIN question q ON q.code = x.item
    LEFT JOIN item i ON i.code = q.item
    WHERE x.learner = :learner AND x.correct = 0
    GROUP BY 1)
  ORDER BY last DESC
  LIMIT 5
),
nxt AS (
  SELECT n.label FROM node n LEFT JOIN d ON d.code = n.code
  WHERE n.code NOT IN (SELECT point FROM done)
    AND NOT EXISTS (SELECT 1 FROM prereq e
                    WHERE e.dst = n.code AND e.src NOT IN (SELECT point FROM done))
  GROUP BY n.code, n.label
  ORDER BY coalesce(max(d.depth), 0), n.code
  LIMIT 6
),
pts AS (
  SELECT DISTINCT q.level, i.point FROM question q JOIN item i ON i.code = q.item
),
lv AS (
  SELECT level, sum(point IN (SELECT point FROM done)) || '/' || count(*) AS t
  FROM pts GROUP BY level
),
gap AS (
  SELECT n.label FROM pts p JOIN node n ON n.code = p.point, lvl
  WHERE p.level = lvl.v AND p.point NOT IN (SELECT point FROM done)
  ORDER BY n.code
),
txt AS (
  SELECT
    '已掌握 ' || (SELECT count(*) FROM done) || ' / 总知识点 ' || (SELECT count(*) FROM node) || char(10)
    || CASE WHEN a.n = 0 THEN '还没有作答记录。' || char(10)
       ELSE '累计答题 ' || a.n || '，答对 ' || a.r || '，正确率 ' || (a.r * 100 / a.n) || '%' || char(10)
         || '在学（答对/答题）：' || coalesce((SELECT group_concat(s, '；') FROM doing), '无') || char(10)
         || coalesce('在学知识点的掌握得分（0–100，按做题情况算，低的在前）：'
                     || (SELECT group_concat(s, '；') FROM sc) || char(10), '')
         || '最近答错（知识点·条目）：' || coalesce((SELECT group_concat(s, '；') FROM wrong), '无') || char(10)
       END
    || '各等级已掌握/涉及知识点：'
    || coalesce((SELECT group_concat(level || ' ' || t, '，')
                 FROM (SELECT * FROM lv ORDER BY level DESC)), '无') || char(10)
    || CASE WHEN lvl.v = '' THEN ''
       ELSE lvl.v || ' 还没掌握的知识点（共 ' || (SELECT count(*) FROM gap) || ' 个）：'
            || coalesce((SELECT group_concat(label, '、') FROM (SELECT label FROM gap LIMIT 15)), '无')
            || CASE WHEN (SELECT count(*) FROM gap) > 15 THEN '……' ELSE '' END || char(10)
       END
    || '现在能学（前置都掌握了）：' || coalesce((SELECT group_concat(label, '、') FROM nxt), '无')
    AS s
  FROM a, lvl
)
SELECT CASE WHEN length(s) > 800 THEN substr(s, 1, 798) || '……' ELSE s END FROM txt
