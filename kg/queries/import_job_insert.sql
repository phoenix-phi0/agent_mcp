-- 新建一个导入任务。开关从前端来可能是 true / false、1 / 0、"是"，都认。
INSERT INTO import_job(series, label, source, license, prefix, level_hint, rewrite, overwrite,
                       document, file_name, doc_kind, pages, paragraphs, chars)
VALUES(:series, :label, NULLIF(:source, ''), NULLIF(:license, ''), :prefix,
       CASE WHEN :level_hint IN ('N5', 'N4', 'N3', 'N2', 'N1') THEN :level_hint ELSE '全部' END,
       CASE WHEN lower(coalesce(:rewrite, '')) IN ('1', 'true', '是', 'on') THEN 1 ELSE 0 END,
       CASE WHEN lower(coalesce(:overwrite, '')) IN ('1', 'true', '是', 'on') THEN 1 ELSE 0 END,
       :document, :file_name, :doc_kind,
       CAST(coalesce(NULLIF(:pages, ''), '0') AS INTEGER),
       CAST(coalesce(NULLIF(:paragraphs, ''), '0') AS INTEGER),
       CAST(coalesce(NULLIF(:chars, ''), '0') AS INTEGER))
