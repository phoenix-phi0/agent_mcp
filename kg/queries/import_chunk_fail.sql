-- 一块解析失败：出错，记一句人话（模型超时、回复不是 JSON……），页面上能重试。
UPDATE import_chunk
SET chunk_status = '出错', error = coalesce(NULLIF(:error, ''), '没有说明的错误'),
    updated = datetime('now', 'localtime')
WHERE id = CAST(:chunk AS INTEGER)
