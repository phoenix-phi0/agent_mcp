-- 确认导入：一个任务里通过的课，按课序排，编成 content/series/<code>/lessons.jsonl
-- 的行（格式见 content/series/README.md）。课号 = 前缀-三位序号，序号按排好的
-- 顺序从 1 数（课序重复、跳号也不会撞号）；seq 照写审阅后的课序。items / points
-- 是 JSON 数组文本，脚本里解析回数组再写文件。
SELECT printf('%s-%03d', j.prefix, row_number() OVER (ORDER BY d.seq, d.id)) AS code,
       j.series, coalesce(d.draft_level, '') AS level, d.seq, d.title,
       coalesce(d.summary, '') AS summary, coalesce(d.explanation, '') AS explanation,
       coalesce(d.formation, '') AS formation, coalesce(d.examples, '[]') AS examples,
       d.items, d.points
FROM import_lesson d JOIN import_job j ON j.id = d.job
WHERE d.job = CAST(:job AS INTEGER) AND d.review = '通过'
ORDER BY d.seq, d.id
