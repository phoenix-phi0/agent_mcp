-- 重新解析一块之前，删掉这块上次抽出的草稿课（审阅过的也删：内容要换了）。
DELETE FROM import_lesson WHERE chunk = CAST(:chunk AS INTEGER)
