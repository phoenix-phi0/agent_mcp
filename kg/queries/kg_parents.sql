-- :code 的直接前置。
SELECT n.code, n.label
FROM prereq p JOIN node n ON n.code = p.src
WHERE p.dst = :code
ORDER BY n.code
