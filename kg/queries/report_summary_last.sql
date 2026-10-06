-- 学情页：这个学生最近一份 AI 学情总结（learner_report），没有就是空行。
SELECT summary_text AS text, written_at AS at, coalesce(written_by, '') AS by_who,
       'AI 学情总结（' || written_at || CASE WHEN coalesce(written_by, '') <> ''
                                             THEN '，' || written_by || ' 请的' ELSE '' END || '）' AS head
FROM learner_report
WHERE learner = :student
ORDER BY id DESC
LIMIT 1
