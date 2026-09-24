-- 按学习者查最近的错题，用于复习
SELECT 题号, 课程, 考点, 错次, 最后错于
FROM 错题
WHERE 学习者 = :学习者
ORDER BY 最后错于 DESC
LIMIT :条数
