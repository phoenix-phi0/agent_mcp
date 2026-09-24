-- 更新一条学习者。code 是表单字段。
UPDATE learner SET
  name = :name,
  level = :level,
  note = :note
WHERE code = :code
