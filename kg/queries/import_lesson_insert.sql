-- 模型抽出的一课写成草稿。items / points 原样进来（JSON 数组文本），紧接着
-- import_lesson_check 过存在性。等级不是 N5–N1 的存 NULL（审阅时补）。
-- 课序不是数字的用块序。把握：0–1 的小数换成百分数，0–100 的照存。
INSERT INTO import_lesson(job, chunk, seq, title, draft_level, summary, explanation, formation,
                          examples, items, points, confidence, reason)
VALUES(CAST(:job AS INTEGER), CAST(:chunk AS INTEGER),
       CASE WHEN trim(coalesce(:seq, '')) GLOB '[0-9]*' AND trim(:seq) NOT GLOB '*[^0-9]*'
            THEN CAST(trim(:seq) AS INTEGER) ELSE CAST(:chunk_seq AS INTEGER) END,
       coalesce(NULLIF(trim(coalesce(:title, '')), ''), '（没有标题）'),
       CASE WHEN upper(trim(coalesce(:level, ''))) IN ('N5', 'N4', 'N3', 'N2', 'N1')
            THEN upper(trim(:level)) END,
       NULLIF(trim(coalesce(:summary, '')), ''), NULLIF(trim(coalesce(:explanation, '')), ''),
       NULLIF(trim(coalesce(:formation, '')), ''),
       CASE WHEN json_valid(:examples) AND json_type(:examples) = 'array' THEN :examples ELSE '[]' END,
       CASE WHEN json_valid(:items) AND json_type(:items) = 'array' THEN :items
            WHEN coalesce(:items, '') = '' THEN '[]' ELSE json_array(:items) END,
       CASE WHEN json_valid(:points) AND json_type(:points) = 'array' THEN :points
            WHEN coalesce(:points, '') = '' THEN '[]' ELSE json_array(:points) END,
       CASE WHEN CAST(:confidence AS REAL) > 0 AND CAST(:confidence AS REAL) <= 1
            THEN CAST(round(CAST(:confidence AS REAL) * 100) AS INTEGER)
            WHEN CAST(:confidence AS REAL) > 1
            THEN min(CAST(round(CAST(:confidence AS REAL)) AS INTEGER), 100) END,
       NULLIF(trim(coalesce(:reason, '')), ''))
