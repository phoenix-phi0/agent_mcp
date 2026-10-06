-- 刚插入的那一行的 id。要在同一个事务里调（同一个连接），事务外拿到的是 0。
SELECT last_insert_rowid()
