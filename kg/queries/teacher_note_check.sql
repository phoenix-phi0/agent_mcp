-- 保存（新建、修改、重新启用）之前查一遍，有问题回一句人话，没问题回空串。
--
-- 上限：每条内容 400 字、关键词 100 字；启用的同类设定合计（全班的加上同一个
-- 学生个人的，按最多的那个学生算）记忆 1200 字、作者注 600 字、关键词卡 3000 字。
-- 关键词卡拼进提示词时另有命中的合计 800 字（scripts/teacher_notes.zs）。
--
-- :note_id 新建时空；:student 空 = 全班。存全班的看所有学生里最多的那个，存个人
-- 的只看这个学生。
WITH me AS (
  SELECT CAST(coalesce(nullif(:note_id, ''), '0') AS INTEGER) AS id,
         coalesce(:note_kind, '') AS kind,
         trim(coalesce(:student, '')) AS student,
         trim(coalesce(:note_content, '')) AS content,
         trim(coalesce(:note_keywords, '')) AS keywords,
         CASE WHEN lower(coalesce(:note_enabled, '')) IN ('1', 'true', '是', 'on') THEN 1 ELSE 0 END AS enabled
),
lim AS (
  SELECT CASE kind WHEN '记忆' THEN 1200 WHEN '作者注' THEN 600 ELSE 3000 END AS total FROM me
),
pool AS (
  SELECT coalesce(n.note_student, '') AS student, length(n.note_content) AS size
  FROM teacher_note n, me
  WHERE n.note_kind = me.kind AND n.note_enabled = 1 AND n.id <> me.id
  UNION ALL
  SELECT student, length(content) FROM me WHERE enabled = 1
),
per AS (
  SELECT student, sum(size) AS n FROM pool WHERE student <> '' GROUP BY student
),
worst AS (
  SELECT (SELECT coalesce(sum(size), 0) FROM pool WHERE student = '')
         + coalesce(CASE WHEN me.student = '' THEN (SELECT max(n) FROM per)
                         ELSE (SELECT n FROM per WHERE per.student = me.student) END, 0) AS n
  FROM me
)
SELECT CASE
  WHEN me.kind NOT IN ('记忆', '作者注', '关键词卡') THEN '种类只能是记忆、作者注、关键词卡'
  WHEN me.content = '' THEN '内容不能为空'
  WHEN length(me.content) > 400 THEN '每条内容最多 400 字，现在 ' || length(me.content) || ' 字，删短一点再存'
  WHEN me.kind = '关键词卡' AND replace(replace(replace(me.keywords, ',', ''), '，', ''), '、', '') = ''
    THEN '关键词卡要填关键词（逗号分隔，学生提到任一个才带上）'
  WHEN length(me.keywords) > 100 THEN '关键词最多 100 字，现在 ' || length(me.keywords) || ' 字'
  WHEN me.enabled = 1 AND worst.n > lim.total
    THEN '启用的' || me.kind || '合计最多 ' || lim.total || ' 字（全班的加上同一个学生个人的），这样存会到 '
         || worst.n || ' 字。先停用或删短几条再存'
  ELSE '' END AS problem
FROM me, lim, worst
