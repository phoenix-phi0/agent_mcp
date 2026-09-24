-- 更新一条笔记。id 随编辑表单一起提交（列表点编辑时整行拷进去的）。
UPDATE note SET
  title = :title,
  body = :body,
  pinned = CAST(:pinned AS INTEGER)
WHERE id = :id
