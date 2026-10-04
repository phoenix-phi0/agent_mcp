-- 一个条目挂着的课文，按 rank 排（同 rank 按等级从易到难：N5 在前）。
SELECT l.code, l.level, l.title, l.summary, l.explanation, l.formation,
       l.examples, l.changed, il.rank
FROM item_lesson il
JOIN lesson l ON l.code = il.lesson
WHERE il.item = :item
ORDER BY il.rank, l.level DESC, l.code
