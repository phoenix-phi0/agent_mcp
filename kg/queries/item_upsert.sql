-- 条目：有就更新，没有就插入。按 code 认。
--
-- point 指向的结构点必须存在（外键拦着）。after 指向另一个条目，可以为空，
-- 也可能指向还没插入的条目——所以导入器先插全部条目、再回填 after。
INSERT INTO item(code, label, point, after)
VALUES(:code, :label, :point, NULLIF(:after, ''))
ON CONFLICT(code) DO UPDATE SET
  label = excluded.label,
  point = excluded.point,
  after = excluded.after
