-- 按工号查一个作者。查不到返回空结果。
SELECT code, name, level, joined
FROM author
WHERE code = :工号
