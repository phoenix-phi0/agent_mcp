-- 一块开始解析：解析中，次数加一，清掉上次的出错原因。
UPDATE import_chunk
SET chunk_status = '解析中', tries = tries + 1, error = NULL,
    updated = datetime('now', 'localtime')
WHERE id = CAST(:chunk AS INTEGER)
