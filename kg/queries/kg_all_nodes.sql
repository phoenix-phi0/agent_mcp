-- 画图用的节点。图认 id / label 两个键，所以把 code 起别名成 id。
--
-- 不给 x / y：节点图在前端用 dagre 算坐标。后端想按业务含义排布的话，
-- 在这里补上 x、y 两列就行，前端有坐标就不跑 dagre。
SELECT code AS id, label
FROM node
ORDER BY code
