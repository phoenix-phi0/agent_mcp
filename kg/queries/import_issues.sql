-- 重算一个任务里每课草稿的问题提示（审阅要看的），每次改动之后调：
--   等级没认出 / 没映射到已有条目或知识点（孤课：没题可出，老师不知道讲哪个点）
--   丢掉了库里没有的编号 / 讲解、一句话是空的 / 课序跟别的课重复（驳回的不算）
UPDATE import_lesson SET issues = NULLIF(rtrim(
     CASE WHEN draft_level IS NULL THEN '等级没认出；' ELSE '' END
  || CASE WHEN coalesce(json_array_length(CASE WHEN json_valid(items) THEN items END), 0)
             + coalesce(json_array_length(CASE WHEN json_valid(points) THEN points END), 0) = 0
          THEN '没映射到已有条目或知识点；' ELSE '' END
  || CASE WHEN coalesce(dropped, '') <> '' THEN '丢掉了库里没有的编号；' ELSE '' END
  || CASE WHEN coalesce(trim(explanation), '') = '' THEN '讲解是空的；' ELSE '' END
  || CASE WHEN coalesce(trim(summary), '') = '' THEN '一句话是空的；' ELSE '' END
  || CASE WHEN review <> '驳回' AND EXISTS (
            SELECT 1 FROM import_lesson o
            WHERE o.job = import_lesson.job AND o.id <> import_lesson.id
              AND o.seq = import_lesson.seq AND o.review <> '驳回')
          THEN '课序跟别的课重复；' ELSE '' END, '；'), '')
WHERE job = CAST(:job AS INTEGER)
