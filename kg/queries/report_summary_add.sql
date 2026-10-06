-- 存一份 AI 学情总结。不进 chat_message（那是学生自己的问老师记录）。
INSERT INTO learner_report(learner, summary_text, written_by, written_at)
VALUES (:student, :summary_text, :written_by, datetime('now', 'localtime'))
