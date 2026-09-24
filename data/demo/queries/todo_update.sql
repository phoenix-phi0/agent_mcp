-- 更新一条待办。id 随编辑表单一起提交（列表点编辑时整行拷进去的）。
UPDATE todo SET
  task = :task,
  done = CAST(:done AS INTEGER),
  due = :due
WHERE id = :id
