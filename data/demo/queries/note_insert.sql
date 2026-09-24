-- 新建一条笔记。
-- id 是自增主键，不在这里给。
INSERT INTO note(title, body, pinned)
VALUES(:title, :body, CAST(:pinned AS INTEGER))
