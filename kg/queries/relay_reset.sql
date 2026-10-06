-- 改传达时，要点或必须准确的信息变了：这条的状态全部清掉（每个学生重新传达）。
-- 只改紧急程度、口吻、轮数、截止日这类的不清。先于 relay_update 跑（比的是改之前
-- 库里的）。relay_use 的历史留着。
DELETE FROM relay_state
WHERE relay_id = CAST(:relay_id AS INTEGER)
  AND EXISTS (SELECT 1 FROM teacher_relay r
              WHERE r.id = CAST(:relay_id AS INTEGER)
                AND (r.relay_point <> trim(:relay_point)
                     OR coalesce(r.relay_facts, '') <> trim(coalesce(:relay_facts, ''))))
