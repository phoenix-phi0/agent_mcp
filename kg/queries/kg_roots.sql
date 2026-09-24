-- 根：没有任何前置的知识点，学习的起点。
SELECT code, label FROM node
WHERE code NOT IN (SELECT dst FROM prereq)
ORDER BY code
