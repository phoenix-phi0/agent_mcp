-- 「全部通过有映射的课」：这个任务里还待审、映射到了至少一个条目或知识点的课
-- 一律通过。驳回过的、孤课不动。返回通过了几课。
UPDATE import_lesson SET review = '通过'
WHERE job = CAST(:job AS INTEGER) AND review = '待审'
  AND json_array_length(items) + json_array_length(points) > 0
