-- 一课草稿，编辑页用：字段原样，加上来自哪块、所属任务的系列和回审阅页的地址。
SELECT d.id AS draft, d.job, d.seq, d.title, d.draft_level, coalesce(d.summary, '') AS summary,
       coalesce(d.explanation, '') AS explanation, coalesce(d.formation, '') AS formation,
       coalesce(d.examples, '[]') AS examples, d.items, d.points, coalesce(d.dropped, '') AS dropped,
       coalesce(d.issues, '') AS issues, coalesce(d.reason, '') AS reason,
       CASE WHEN d.confidence IS NULL THEN '' ELSE d.confidence || '%' END AS confidence,
       d.review, j.series, j.label AS series_label,
       '第 ' || coalesce(c.seq, '?') || ' 块「' || coalesce(c.title, '') || '」' AS from_chunk,
       '系列 ' || j.series || ' · 第 ' || coalesce(d.seq, '?') || ' 课 · ' || d.review AS head,
       '#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?job=' || d.job AS back
FROM import_lesson d JOIN import_job j ON j.id = d.job
LEFT JOIN import_chunk c ON c.id = d.chunk
WHERE d.id = CAST(:draft AS INTEGER)
