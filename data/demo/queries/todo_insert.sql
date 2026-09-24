-- 新建一条待办。
-- id 是自增主键，不在这里给。
INSERT INTO todo(task, done, due)
VALUES(:task, CAST(:done AS INTEGER), :due)
