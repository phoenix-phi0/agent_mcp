-- 教材导入页「系列」表：除 hanabira 外的系列（hanabira 是主教材，不在这里管），
-- 课数、状态（在用 / 已撤下 = sort < 0）。href 是这个系列的管理地址（撤下）。
SELECT s.code, s.label,
       (SELECT count(*) FROM lesson l WHERE l.series = s.code) AS lesson_n,
       CASE WHEN s.sort < 0 THEN '已撤下（教材页不显示）' ELSE '在用' END AS series_state,
       '#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?manage=' || s.code AS href
FROM series s
WHERE s.code <> 'hanabira'
ORDER BY s.sort < 0, s.sort, s.code
