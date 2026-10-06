-- 传达保存（新建、修改）之前查一遍，有问题回一句人话，没问题回空串。
--
-- 要点必填、最多 300 字；必须准确的信息最多 200 字、话题关键词最多 100 字；紧急程度、
-- 口吻只能是那几个（不选由接口补成尽快、以老师名义）；轮数阈值 1 到 20 的整数（0 或空
-- 是默认的 3：「AI老师设定」页上点「新增传达」时表单是空的，数字框是 0）；截止日期空或 YYYY-MM-DD 的真日期。
-- 待传达的条数不设上限：一条回复只带排第一的那条，多了只是排队。
WITH me AS (
  SELECT trim(coalesce(:relay_point, '')) AS point,
         trim(coalesce(:relay_facts, '')) AS facts,
         trim(coalesce(:relay_keywords, '')) AS keywords,
         coalesce(:relay_urgency, '') AS urgency,
         coalesce(:relay_voice, '') AS voice,
         trim(coalesce(:relay_rounds, '')) AS rounds,
         trim(coalesce(:relay_due, '')) AS due
)
SELECT CASE
  WHEN point = '' THEN '要点不能为空：写清楚要让学生明白什么'
  WHEN length(point) > 300 THEN '要点最多 300 字，现在 ' || length(point) || ' 字，删短一点再存'
  WHEN length(facts) > 200 THEN '必须准确的信息最多 200 字，现在 ' || length(facts) || ' 字'
  WHEN length(keywords) > 100 THEN '话题关键词最多 100 字，现在 ' || length(keywords) || ' 字'
  WHEN urgency NOT IN ('顺便', '尽快', '立即') THEN '紧急程度只能是顺便、尽快、立即'
  WHEN voice NOT IN ('以老师名义', 'AI自己的口吻') THEN '口吻只能是以老师名义、AI自己的口吻'
  WHEN rounds <> '' AND (rounds GLOB '*[^0-9]*' OR CAST(rounds AS INTEGER) > 20)
    THEN '轮数阈值要是 1 到 20 的整数（0 或不填是 3）'
  WHEN due <> '' AND (due NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' OR date(due) IS NULL OR date(due) <> due)
    THEN '截止日期要写成 2026-10-20 这样的日期'
  ELSE '' END AS problem
FROM me
