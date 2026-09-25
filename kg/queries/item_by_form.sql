-- 接在这个形式后面的条目（辞书形后面能接什么、て形后面能接什么）。
--
-- 跟 item_by_point 是两个维度：那个按功能查（表示义务的有哪些），这个按
-- 形式查（て形后面能接哪些）。同一个条目在两边都出现，本来就该如此——
-- 「てもいい」既是「义务许可禁止」里的一条，也是「て形」后面能接的一条。
SELECT i.code, i.label, COALESCE(p.label, '') AS point
FROM item i LEFT JOIN node p ON p.code = i.point
WHERE i.form = :code
ORDER BY i.code
