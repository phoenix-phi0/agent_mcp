-- 教材目录：一段文字，问老师「教材」意图拼进提示词（routes/teacher.zs）。
-- 按等级分组，只列标题（N5 在前，组内按课文编号），一级一行：
--   N5（38 课）：A。でも、～B。／A は B より～／……
--
-- :level  认出等级（N4、n4、「N4级」）就只列这一级，认不出列全部。
-- :learner  只列他当前系列的课（learner_pref，没记过是 hanabira），第一行写
--           系列名：「教材：hanabira 语法」。组内有课序的按课序排。
-- 全部列出来也就一千字上下；超过 1500 字截断，末尾写「……」。
WITH cur AS (
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
t AS (
  SELECT l.level, l.title FROM lesson l, lvl, cur
  WHERE l.series = cur.s AND (lvl.v = '' OR l.level = lvl.v)
  ORDER BY l.level DESC, coalesce(l.seq, 0), l.code
),
g AS (
  SELECT level, level || '（' || count(*) || ' 课）：' || group_concat(title, '／') AS line
  FROM t GROUP BY level
),
txt AS (
  SELECT '教材：' || coalesce((SELECT label FROM series WHERE code = cur.s), cur.s) || char(10)
         || coalesce((SELECT group_concat(line, char(10)) FROM (SELECT line FROM g ORDER BY level DESC)),
                     '（教材里没有这一级的课文）') AS s
  FROM cur
)
SELECT CASE WHEN length(s) > 1500 THEN substr(s, 1, 1500) || '……' ELSE s END FROM txt
