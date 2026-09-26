-- 画图用的节点，带状态和角标。
--
-- state：前置全掌握=open（可学），自己掌握了=done，否则 locked。
--        引擎按它上色：实心 / 粗描边 / 淡出。
-- badge：下游节点数（递归数后代），标出瓶颈——角标大的先学，解锁得多。
-- desc ：点开浮层时显示，这里放「学它之前要先会什么」。
--
-- :learner 不给（空串）时一个都没掌握，整张图是「只有根可学」的初始样子。
WITH RECURSIVE
down(src, dst) AS (          -- 后代：传递闭包
  SELECT src, dst FROM prereq
  UNION
  SELECT d.src, p.dst FROM down d JOIN prereq p ON p.src = d.dst
),
done(code) AS (
  SELECT point FROM mastery WHERE learner = :learner AND mastered = 1
)
SELECT
  n.code AS id,
  n.label,
  CASE
    WHEN n.code IN (SELECT code FROM done) THEN 'done'
    WHEN NOT EXISTS (SELECT 1 FROM prereq e
                     WHERE e.dst = n.code
                       AND e.src NOT IN (SELECT code FROM done)) THEN 'open'
    ELSE 'locked'
  END AS state,
  (SELECT count(*) FROM down WHERE src = n.code) AS badge,
  COALESCE((SELECT group_concat(p.label, '、')
            FROM prereq e JOIN node p ON p.code = e.src
            WHERE e.dst = n.code), '（起点）') AS desc
FROM node n
ORDER BY n.code
