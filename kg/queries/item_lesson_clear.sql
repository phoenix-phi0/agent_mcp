-- 一个系列的课↔条目挂接清空，导入这个系列时重灌。要在 lesson_clear 之前
-- 执行（挂接引用课）。别的系列的挂接不动。
DELETE FROM item_lesson
WHERE lesson IN (SELECT code FROM lesson WHERE series = :series)
