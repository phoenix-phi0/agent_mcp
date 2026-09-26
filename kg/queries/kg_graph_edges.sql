-- 画图用的边：前置边 + 对照边。
--
-- 对照边带 kind='对照'：引擎画成虚线、从侧面连，**不参与布局**——不然
-- 「い形容词 ↔ な形容词」这种同层的一对会被拉成上下两层，图就歪了。
--
-- 对照的两端可能是条目（なければならない ↔ なくてもいい），那些不在图上，
-- 所以要过滤掉：两端都得是节点，否则连出去的边指向不存在的点。
SELECT src AS "from", dst AS "to", '' AS kind FROM prereq
UNION ALL
SELECT c.a, c.b, '对照' FROM contrast c
WHERE c.a IN (SELECT code FROM node) AND c.b IN (SELECT code FROM node)
