-- 学情页「全班薄弱点」的知识点表：全班（只算学生，教师的不算，同 report_class）
-- 答错最多的知识点前 10。wrong_n 答错几次、answer_n 一共答了几次、learner_n 有
-- 几个人答错过。只读。
SELECT n.code, n.label,
       sum(CASE WHEN a.correct = 0 THEN 1 ELSE 0 END) AS wrong_n,
       count(*) AS answer_n,
       count(DISTINCT CASE WHEN a.correct = 0 THEN a.learner END) AS learner_n
FROM attempt a
JOIN node n ON n.code = a.point
WHERE NOT EXISTS (SELECT 1 FROM user t WHERE t.username = a.learner AND t.role = 'teacher')
GROUP BY n.code
HAVING wrong_n > 0
ORDER BY wrong_n DESC, answer_n DESC, n.code
LIMIT 10
