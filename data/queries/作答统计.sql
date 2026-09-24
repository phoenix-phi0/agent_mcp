-- 统计某个学习者一共答过多少题、对了多少
SELECT
  count(*)                              AS 总数,
  sum(CASE WHEN 对错 = 1 THEN 1 ELSE 0 END) AS 对数
FROM 作答
WHERE 学习者 = :学习者
