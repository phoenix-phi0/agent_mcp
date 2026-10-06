-- 审阅时改一课草稿的字段。例句要是 JSON 数组文本（[{"jp":…,"zh":…}]），不是
-- 的话接口先拦下（import_examples_ok），这里不再判。等级不在 N5–N1 的存 NULL。
UPDATE import_lesson SET
  title = coalesce(NULLIF(trim(coalesce(:title, '')), ''), title),
  draft_level = CASE WHEN :draft_level IN ('N5', 'N4', 'N3', 'N2', 'N1') THEN :draft_level END,
  seq = CASE WHEN trim(coalesce(:seq, '')) GLOB '[0-9]*' AND trim(:seq) NOT GLOB '*[^0-9]*'
             THEN CAST(trim(:seq) AS INTEGER) ELSE seq END,
  summary = NULLIF(trim(coalesce(:summary, '')), ''),
  explanation = NULLIF(trim(coalesce(:explanation, '')), ''),
  formation = NULLIF(trim(coalesce(:formation, '')), ''),
  examples = CASE WHEN coalesce(trim(:examples), '') = '' THEN '[]' ELSE :examples END
WHERE id = CAST(:draft AS INTEGER)
