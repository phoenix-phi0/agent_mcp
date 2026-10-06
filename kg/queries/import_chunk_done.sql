-- 一块解析完了。:note 是给人看的一句（「这块没认出课」），没有就空。
UPDATE import_chunk
SET chunk_status = '完成', error = NULLIF(:note, ''), updated = datetime('now', 'localtime')
WHERE id = CAST(:chunk AS INTEGER)
