-- 这个系列里没挂到任何条目、也没挂到知识点上的课有几课（导入后检查用：不是
-- 0 就是映射漏了或拼错了）。
SELECT count(*) FROM lesson
WHERE series = :series
  AND code NOT IN (SELECT lesson FROM item_lesson)
  AND code NOT IN (SELECT lesson FROM lesson_point)
