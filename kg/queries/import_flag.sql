-- 前端的开关值算不算「开」：true / 1 / 是 / on 是 1，别的（空、false、0）是 0。
-- 勾选框提交上来可能是布尔、数字、字符串，统一在这里认。
SELECT CASE WHEN lower(coalesce(:overwrite, '')) IN ('1', 'true', '是', 'on') THEN 1 ELSE 0 END
