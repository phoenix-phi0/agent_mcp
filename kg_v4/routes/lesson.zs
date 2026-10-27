接口 GET /lesson/series
  设 r = 调用 lesson.列系列
  返回 {r}
结束

接口 GET /lesson/series/current
  设 r = 调用 lesson.取当前系列 learner={learner} current_role={current_role 或}
  返回 {r}
结束

接口 POST /lesson/series/select
  设 r = 调用 lesson.选择系列 learner={learner} series_code={series_code} current_role={current_role 或}
  返回 {r}
结束

接口 GET /lesson/list
  设 r = 调用 lesson.列课文 series_code={series_code 或} level={level 或} keyword={keyword 或}
  返回 {r}
结束

接口 POST /lesson/list 动作 lesson_list 角色 student
  设 r = 调用 lesson.教材页面 learner={learner} series={series 或} lesson_level={lesson_level 或} keyword={keyword 或} current_role={current_role 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 GET /lesson/detail
  设 r = 调用 lesson.取课文 code={code}
  返回 {r}
结束

接口 POST /lesson/one 动作 lesson_one 角色 student
  设 r = 调用 lesson.课文页面 learner={learner} lesson={lesson 或} current_role={current_role 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 GET /lesson/by-item
  设 r = 调用 lesson.按条目列课文 item_code={item_code}
  返回 {r}
结束

接口 GET /lesson/by-point
  设 r = 调用 lesson.按知识点列课文 point_code={point_code}
  返回 {r}
结束

接口 GET /lesson/items
  设 r = 调用 lesson.取课文关联条目 lesson_code={lesson_code}
  返回 {r}
结束

接口 GET /lesson/point-level
  设 r = 调用 lesson.取知识点等级 point_code={point_code}
  返回 {r}
结束

接口 POST /lesson/import 角色 teacher
  设 file_path = 存文件 file 类型=md,txt 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 lesson.导入课文 series_code={series_code} file_path={file_path} series_name={series_name 或} intro={intro 或} source={source 或} license={license 或} sort_order={sort_order 或}
  返回 {r}
结束

接口 POST /lesson/series/withdraw 角色 teacher
  设 r = 调用 lesson.撤下系列 series_code={series_code}
  返回 {r}
结束
