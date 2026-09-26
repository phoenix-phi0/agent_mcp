-- 全部前置边。图认 from / to 两个键，所以把 src / dst 起别名。
--
-- 「from」是 SQL 的关键字，必须加引号；不加的话 SQLite 报
-- 「near "from": syntax error」，看着像别处写错了。
SELECT src AS "from", dst AS "to" FROM prereq ORDER BY src, dst
