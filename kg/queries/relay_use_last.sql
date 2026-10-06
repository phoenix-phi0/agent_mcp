-- 刚记的那条 relay_use 的 id（交给后台判定）。没有是空串。
SELECT coalesce(max(id), '') FROM relay_use
WHERE learner = :learner AND relay_id = CAST(:relay_id AS INTEGER)
