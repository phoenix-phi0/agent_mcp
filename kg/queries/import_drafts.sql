-- 一个任务的草稿课表：课序、标题、等级、映射（条目、知识点的名称）、问题、
-- 把握、审阅状态。draft 给行上的「通过」「驳回」带走，href 是编辑这一课的地址。
SELECT d.id AS draft, d.seq, d.title, coalesce(d.draft_level, '?') AS draft_level,
       coalesce(nullif(trim(
         coalesce((SELECT group_concat(i.label, '、') FROM json_each(d.items) je
                   JOIN item i ON i.code = je.value), '')
         || CASE WHEN json_array_length(d.items) > 0 AND json_array_length(d.points) > 0
                 THEN ' / ' ELSE '' END
         || coalesce((SELECT group_concat('〔' || n.label || '〕', '、') FROM json_each(d.points) je
                      JOIN node n ON n.code = je.value), '')), ''), '（没有）') AS mapping,
       coalesce(d.issues, '') AS issues,
       CASE WHEN d.confidence IS NULL THEN '' ELSE d.confidence || '%' END AS confidence,
       d.review,
       '#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?draft=' || d.id AS href
FROM import_lesson d
WHERE d.job = CAST(:job AS INTEGER)
ORDER BY d.seq, d.id
