-- 总体进度：一共多少个知识点、掌握了多少。
SELECT
  (SELECT count(*) FROM node) AS total,
  (SELECT count(*) FROM mastery
   WHERE learner = :learner AND mastered = 1) AS done
