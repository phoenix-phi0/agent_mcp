-- 一个系列的课↔知识点挂接清空，导入这个系列时重灌。要在 lesson_clear 之前执行。
DELETE FROM lesson_point
WHERE lesson IN (SELECT code FROM lesson WHERE series = :series)
