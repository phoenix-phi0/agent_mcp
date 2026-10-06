-- 写一个教材系列（content/series.jsonl 一行）。按编号 upsert：文件就是来源，
-- 改了名称、简介、排序，重导一次就跟上。不删文件里没有的系列——那些系列的
-- 课可能还在库里，删了系列只会让下拉、抬头少一个名字。
INSERT INTO series(code, label, description, source, license, sort)
VALUES(NULLIF(:code, ''), :label, NULLIF(:description, ''), NULLIF(:source, ''),
       NULLIF(:license, ''), CAST(coalesce(NULLIF(:sort, ''), '0') AS INTEGER))
ON CONFLICT(code) DO UPDATE SET
  label = excluded.label, description = excluded.description, source = excluded.source,
  license = excluded.license, sort = excluded.sort
