接口 GET /vocab/words
  设 r = 调用 vocab.列单词 keyword={keyword 或} point_code={point_code 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /vocab/word
  设 r = 调用 vocab.取单词 word_id={word_id 或} kanji={kanji 或} kana={kana 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /vocab/words/by-point
  设 r = 调用 vocab.按知识点列单词 point_code={point_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /vocab/orphans
  设 r = 调用 vocab.列孤儿词 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /vocab/word/create 角色 teacher
  设 r = 调用 vocab.新建单词 kana={kana} kanji={kanji 或} meaning={meaning 或} point_code={point_code 或} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /vocab/word/update 角色 teacher
  设 r = 调用 vocab.修改单词 word_id={word_id} kanji={kanji} kana={kana} meaning={meaning} point_code={point_code} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /vocab/word/delete 角色 teacher
  设 r = 调用 vocab.删除单词 word_id={word_id} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /vocab/import 角色 teacher
  设 file_path = 存文件 file 类型=md,txt 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 vocab.导入单词 file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束
