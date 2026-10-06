-- 一个编号在库里是什么：item（条目）/ node（知识点）/ 空串（都没有）。
-- 两边都有时算条目（条目比知识点具体）。映射只能挑已有的。
SELECT CASE WHEN EXISTS (SELECT 1 FROM item WHERE code = trim(:code)) THEN 'item'
            WHEN EXISTS (SELECT 1 FROM node WHERE code = trim(:code)) THEN 'node'
            ELSE '' END
