-- 一个系列的管理信息：名称、来源、课数、映射数、状态。can_withdraw：不是
-- hanabira、还没撤下（sort ≥ 0）或者库里还有课。
SELECT s.code, s.label, coalesce(s.source, '') AS source, coalesce(s.license, '') AS license, s.sort,
       (SELECT count(*) FROM lesson l WHERE l.series = s.code) AS lesson_n,
       '系列 ' || s.code || '（' || s.label || '）：'
         || (SELECT count(*) FROM lesson l WHERE l.series = s.code) || ' 课，映射到条目 '
         || (SELECT count(*) FROM item_lesson il JOIN lesson l ON l.code = il.lesson WHERE l.series = s.code)
         || ' 条、知识点 '
         || (SELECT count(*) FROM lesson_point lp JOIN lesson l ON l.code = lp.lesson WHERE l.series = s.code)
         || ' 条。' || CASE WHEN s.sort < 0 THEN '已撤下，教材页的下拉里没有它。'
                           ELSE '在用，教材页的下拉里能选到。' END AS head,
       CASE WHEN s.code <> 'hanabira'
                 AND (s.sort >= 0 OR EXISTS (SELECT 1 FROM lesson l WHERE l.series = s.code))
            THEN 1 ELSE 0 END AS can_withdraw,
       '#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5' AS back
FROM series s WHERE s.code = :series
