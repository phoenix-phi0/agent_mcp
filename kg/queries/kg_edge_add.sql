-- 加一条前置边 src → dst（学 dst 之前要先会 src）。**会成环就不加。**
--
-- 加 src → dst 会成环，当且仅当从 dst 出发顺着边能走到 src。reach 就是
-- 从 dst 出发能走到的全部节点。
--
-- 检查和插入写成同一条语句：一条语句是原子的，不存在「先查没环、再插入
-- 之间别人插了一条」的竞态。本想用触发器挡在库这一层，但 SQLite 的触发器
-- 里不能写 WITH。
--
-- UNION 而不是 UNION ALL：去重，就算库里已经有环（比如手工改过库）也不会
-- 死循环。
--
-- 影响 0 行就是被拒了。为什么被拒，查 kg_edge_why。
WITH RECURSIVE reach(n) AS (
  SELECT :dst
  UNION
  SELECT p.dst FROM prereq p JOIN reach r ON p.src = r.n
)
INSERT INTO prereq(src, dst)
SELECT :src, :dst
WHERE :src <> :dst
  AND EXISTS (SELECT 1 FROM node WHERE code = :src)
  AND EXISTS (SELECT 1 FROM node WHERE code = :dst)
  AND NOT EXISTS (SELECT 1 FROM prereq WHERE src = :src AND dst = :dst)
  AND NOT EXISTS (SELECT 1 FROM reach WHERE n = :src)
