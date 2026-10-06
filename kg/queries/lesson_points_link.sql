-- 新教材的一课直接挂到它列出的已有知识点上（lesson_point）。跟
-- lesson_items_link.sql 一样：只挂存在的、没挂过的，重复列的只挂一次。返回挂了几条。
INSERT INTO lesson_point(lesson, point)
SELECT DISTINCT :code, trim(value)
FROM json_each(CASE WHEN json_valid(:points) AND json_type(:points) = 'array' THEN :points
                    WHEN coalesce(:points, '') = '' THEN '[]'
                    ELSE json_array(:points) END)
WHERE trim(value) IN (SELECT code FROM node)
  AND EXISTS (SELECT 1 FROM lesson WHERE code = :code)
  AND NOT EXISTS (SELECT 1 FROM lesson_point WHERE lesson = :code AND point = trim(value))
