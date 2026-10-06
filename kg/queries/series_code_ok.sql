-- 导入的系列编号能不能用：非空，只有小写字母、数字、下划线、连字符。它会
-- 拼进文件路径（content/series/<code>/lessons.jsonl），挡掉 ../ 这类东西。
-- 1 = 能用，0 = 不能。
SELECT CASE WHEN coalesce(:series, '') <> '' AND :series NOT GLOB '*[^a-z0-9_-]*'
            THEN 1 ELSE 0 END
