-- 一个导入任务，加上进度：块总数、做完的（完成 + 出错）、出错的、还在跑的；
-- 草稿课数、通过、驳回、通过且有映射的。running = 还有块在待解析 / 解析中，
-- 页面据此轮询。head / progress 是给人看的两行。
SELECT j.id, j.series, j.label, coalesce(j.source, '') AS source, coalesce(j.license, '') AS license,
       j.prefix, j.level_hint, j.rewrite, j.overwrite, coalesce(j.file_name, '') AS file_name,
       coalesce(j.doc_kind, '') AS doc_kind, j.pages, j.paragraphs, j.chars,
       coalesce(j.imported, '') AS imported, coalesce(j.report, '') AS report, j.created,
       c.total AS chunk_n, c.finished, c.failed, c.total - c.finished AS waiting,
       CASE WHEN c.total - c.finished > 0 THEN 1 ELSE 0 END AS running,
       l.total AS lesson_n, l.passed, l.rejected, l.passed_mapped,
       '系列 ' || j.series || '（' || j.label || '）· 课号前缀 ' || j.prefix || ' · 文件 '
         || coalesce(j.file_name, '') || '（' || upper(coalesce(j.doc_kind, '')) ||
         CASE WHEN j.pages > 0 THEN '，' || j.pages || ' 页' ELSE '' END
         || '，' || j.chars || ' 字）· ' ||
         CASE WHEN j.rewrite = 1 THEN '讲解和例句由模型改写' ELSE '保留原文讲解（没勾改写）' END AS head,
       CASE WHEN c.total - c.finished > 0
            THEN '正在解析：' || c.finished || '/' || c.total || ' 块做完'
                 || CASE WHEN c.failed > 0 THEN '，出错 ' || c.failed || ' 块' ELSE '' END
                 || '。这页会自己刷新，可以先去别的页面。'
            ELSE '解析完了：' || c.total || ' 块，抽出 ' || l.total || ' 课'
                 || CASE WHEN c.failed > 0 THEN '，出错 ' || c.failed || ' 块（在块表里重试）' ELSE '' END
                 || '。通过 ' || l.passed || ' 课、驳回 ' || l.rejected || ' 课。'
                 || CASE WHEN j.imported IS NOT NULL THEN '已于 ' || j.imported || ' 导入。' ELSE '' END
       END AS progress,
       '#%E6%95%99%E6%9D%90%E5%AF%BC%E5%85%A5' AS back
FROM import_job j,
     (SELECT count(*) AS total,
             coalesce(sum(chunk_status IN ('完成', '出错')), 0) AS finished,
             coalesce(sum(chunk_status = '出错'), 0) AS failed
      FROM import_chunk WHERE job = CAST(:job AS INTEGER)) c,
     (SELECT count(*) AS total, coalesce(sum(review = '通过'), 0) AS passed,
             coalesce(sum(review = '驳回'), 0) AS rejected,
             coalesce(sum(review = '通过' AND (json_array_length(items) + json_array_length(points)) > 0), 0)
               AS passed_mapped
      FROM import_lesson WHERE job = CAST(:job AS INTEGER)) l
WHERE j.id = CAST(:job AS INTEGER)
