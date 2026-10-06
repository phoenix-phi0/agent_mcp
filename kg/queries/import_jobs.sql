-- 教材导入页的任务表：新的在前。job_state 是一句进度：
--   解析中 3/5 块（出错 1）/ 待审 12 课（通过 3、驳回 1）/ 已导入（时间）
-- href 是这个任务的审阅页地址。
SELECT j.id AS job, j.series, j.label, coalesce(j.file_name, '') AS file_name, j.created,
       CASE
         WHEN EXISTS (SELECT 1 FROM import_chunk c WHERE c.job = j.id
                      AND c.chunk_status IN ('待解析', '解析中'))
         THEN '解析中 ' || (SELECT count(*) FROM import_chunk c WHERE c.job = j.id
                            AND c.chunk_status IN ('完成', '出错'))
              || '/' || (SELECT count(*) FROM import_chunk c WHERE c.job = j.id) || ' 块'
         WHEN j.imported IS NOT NULL THEN '已导入（' || j.imported || '）'
         ELSE '待审 ' || (SELECT count(*) FROM import_lesson l WHERE l.job = j.id) || ' 课'
              || '（通过 ' || (SELECT count(*) FROM import_lesson l WHERE l.job = j.id AND l.review = '通过')
              || '、驳回 ' || (SELECT count(*) FROM import_lesson l WHERE l.job = j.id AND l.review = '驳回')
              || '）'
       END
       || CASE WHEN EXISTS (SELECT 1 FROM import_chunk c WHERE c.job = j.id AND c.chunk_status = '出错')
               THEN '，出错 ' || (SELECT count(*) FROM import_chunk c WHERE c.job = j.id
                                 AND c.chunk_status = '出错') || ' 块' ELSE '' END AS job_state,
       '#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5?job=' || j.id AS href
FROM import_job j
ORDER BY j.id DESC
