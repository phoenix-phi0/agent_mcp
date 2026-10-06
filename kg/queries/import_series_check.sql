-- 教材导入：新建任务、确认导入前校验系列编号和课号前缀。一行：
--   code_ok        编号格式对：小写字母开头，只有小写字母、数字、下划线、连字符，
--                  不长于 40（会拼进路径 content/series/<code>/；下划线开头的
--                  系列启动时不导，所以不许）
--   prefix_ok      课号前缀格式对：小写字母开头，只有小写字母、数字，不长于 20
--   series_exists  series 表或 lesson 表里已经有这个系列（要覆盖得明确勾选）
--   prefix_taken   别的系列已经有以「前缀-」开头的课号——导入时会撞编号、整批
--                  回滚，先拦下
SELECT
  CASE WHEN :series GLOB '[a-z]*' AND :series NOT GLOB '*[^a-z0-9_-]*'
            AND length(:series) <= 40 THEN 1 ELSE 0 END AS code_ok,
  CASE WHEN :prefix GLOB '[a-z]*' AND :prefix NOT GLOB '*[^a-z0-9]*'
            AND length(:prefix) <= 20 THEN 1 ELSE 0 END AS prefix_ok,
  CASE WHEN EXISTS (SELECT 1 FROM series WHERE code = :series)
         OR EXISTS (SELECT 1 FROM lesson WHERE series = :series) THEN 1 ELSE 0 END AS series_exists,
  (SELECT count(*) FROM lesson
   WHERE substr(code, 1, length(:prefix) + 1) = :prefix || '-'
     AND series <> :series) AS prefix_taken
