-- 知识点：有就更新名称，没有就插入。按 code 认。
INSERT INTO node(code, label) VALUES(:code, :label)
ON CONFLICT(code) DO UPDATE SET label = excluded.label
