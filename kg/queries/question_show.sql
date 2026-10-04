-- 出题时给界面看的那一段：抬头加题干。不带答案，也不带条目名——挖空题
-- 考的就是那个语法，条目名一露出来就等于给了答案。条目和课文判完再说。
SELECT q.code, q.qtype,
       '［' || q.level || '・' || q.kind || '］' || char(10) || q.stem AS text
FROM question q
WHERE q.code = :code
