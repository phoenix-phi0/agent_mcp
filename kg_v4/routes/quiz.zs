接口 GET /quiz/state 角色 student
  设 r = 调用 quiz.取做题状态 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /quiz/state 动作 quiz_state 角色 student
  设 r = 调用 quiz.做题页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /quiz/start 动作 quiz_start 角色 student
  设 r = 调用 quiz.开始页面 learner={learner} pick_level={pick_level 或} pick_kind={pick_kind 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 go 做题
结束

接口 POST /quiz/next 动作 quiz_next 角色 student
  设 r = 调用 quiz.下一题页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /quiz/answer 动作 quiz_answer 角色 student
  设 r = 调用 quiz.判答案页面 learner={learner} choice={choice 或} given={given 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /quiz/again 动作 quiz_again 角色 student
  设 r = 调用 quiz.再来一轮页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /quiz/lesson 动作 quiz_lesson 角色 student
  设 r = 调用 quiz.课文页面 learner={learner} lesson={lesson 或} mode={mode 或} level={level 或} kind={kind 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 GET /quiz/round-answers 角色 student
  设 r = 调用 quiz.取本轮作答 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /quiz/round 角色 student
  设 r = 调用 quiz.取当前轮次信息 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /quiz/import 角色 teacher
  设 file_path = 存文件 file 类型=md,txt 上限=20MB
  如果 {file_path} 开头是 [
    返回 {"error":"{file_path}"} 400
  结束
  设 r = 调用 quiz.导入题库 file_path={file_path} learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束
