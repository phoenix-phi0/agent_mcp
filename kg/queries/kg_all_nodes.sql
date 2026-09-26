-- 画图用的节点。图认 id / label 两个键，所以把 code 起别名成 id。
--
-- 不给 x / y：布局是「节点图」控件的事（前端 dagre 算）。早先在 Python 里
-- 算好坐标塞进来，那是把引擎该做的事挪到了应用里——布局不好该改控件
-- （templates/frontend/graph.j2），所有项目都受益。
SELECT code AS id, label
FROM node
ORDER BY code
