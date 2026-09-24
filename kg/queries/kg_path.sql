-- 从 :from 走到 :to 的一条路径，节点用「 → 」连起来。没有路径就没有行。
--
-- 用来解释「会成环」：加 src → dst 被拒，是因为库里已经有 dst → … → src，
-- 把这条路径报出来，人才知道环是从哪儿闭合的。
--
-- path 两头带「|」再用 instr 查重：直接查子串的话，找 noun 会误中 pronoun。
-- 库里本来无环，这个查重只是保险——就算有人手工改出了环，也不会死循环。
WITH RECURSIVE walk(n, path) AS (
  SELECT :from, '|' || :from || '|'
  UNION ALL
  SELECT p.dst, w.path || p.dst || '|'
  FROM prereq p JOIN walk w ON p.src = w.n
  WHERE instr(w.path, '|' || p.dst || '|') = 0
)
SELECT replace(trim(path, '|'), '|', ' → ') AS path
FROM walk WHERE n = :to
LIMIT 1
