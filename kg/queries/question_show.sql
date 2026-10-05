-- 出题时给题卡用的：抬头和题干原文（选项还在题干里，由「拆选项」拆开）。
-- 不带答案，也不带条目名——挖空题考的就是那个语法，条目名一露出来就等于
-- 给了答案。条目和课文判完再说。
SELECT q.code, q.qtype, q.stem,
       q.level || '・' || q.kind AS head
FROM question q
WHERE q.code = :code
