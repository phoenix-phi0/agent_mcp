-- 一课的例句，examples（JSON 文本 [{"jp":…,"zh":…}]）拆成一行一句，按原顺序。
-- 不是合法 JSON 的当成没有例句，不报错——坏了一课的例句不该让整页打不开。
SELECT json_extract(e.value, '$.jp') AS jp,
       coalesce(json_extract(e.value, '$.zh'), '') AS zh
FROM lesson l,
     json_each(CASE WHEN json_valid(l.examples) THEN l.examples ELSE '[]' END) e
WHERE l.code = :lesson
ORDER BY CAST(e.key AS INTEGER)
