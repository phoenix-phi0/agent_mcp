-- 切出来的一块，待解析。
INSERT INTO import_chunk(job, seq, title, body)
VALUES(CAST(:job AS INTEGER), CAST(:seq AS INTEGER), :title, :body)
