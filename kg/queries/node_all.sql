-- 全部知识点，按编号排。列表页和远程下拉共用。
--
-- 不给 code 起 value 的别名：列名要能在字段表里找到（.ui 的列会按字段表
-- 查类型），而前端取下拉的值时本来就会在没有 value 列时退回用头两列。
SELECT code, label
FROM node
ORDER BY code
LIMIT CAST(:limit AS INTEGER)
