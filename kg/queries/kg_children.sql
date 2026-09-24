-- :code 直接解锁的知识点（直接后续）。
SELECT n.code, n.label
FROM prereq p JOIN node n ON n.code = p.dst
WHERE p.src = :code
ORDER BY n.code
