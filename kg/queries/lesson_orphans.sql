-- 没挂到任何条目上的课文有几课（导入后检查用：不是 0 就是映射文件漏了或拼错了）。
SELECT count(*) FROM lesson
WHERE code NOT IN (SELECT lesson FROM item_lesson)
