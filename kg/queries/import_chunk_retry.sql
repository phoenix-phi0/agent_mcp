-- 重试一块：回到待解析。还在等的（待解析）不动，返回 0，接口据此不再交给后台。
UPDATE import_chunk
SET chunk_status = '待解析', error = NULL, updated = datetime('now', 'localtime')
WHERE id = CAST(:chunk_id AS INTEGER) AND chunk_status <> '待解析'
