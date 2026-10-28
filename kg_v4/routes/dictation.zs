接口 GET /dictation/state 角色 student
  设 r = 调用 dictation.取状态 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /dictation/state 动作 dictation_state 角色 student
  设 r = 调用 dictation.默写页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /dictation/start 动作 dictation_start 角色 student
  设 r = 调用 dictation.开始页面 learner={learner} dict_direction={dict_direction 或} dict_level={dict_level 或} dict_source={dict_source 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /dictation/random 动作 dictation_random 角色 student
  设 r = 调用 dictation.随机页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /dictation/wrong 动作 dictation_wrong 角色 student
  设 r = 调用 dictation.练错词页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /dictation/load 动作 dictation_load 角色 student
  设 r = 调用 dictation.载入页面 learner={learner} source={source 或} direction={direction 或} level={level 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
  响应 form {r.form}
结束

接口 POST /dictation/again 动作 dictation_again 角色 student
  设 r = 调用 dictation.再来一轮页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /dictation/next 动作 dictation_next 角色 student
  设 r = 调用 dictation.下一个页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /dictation/hint 动作 dictation_hint 角色 student
  设 r = 调用 dictation.提示页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /dictation/answer 动作 dictation_answer 角色 student
  设 r = 调用 dictation.判答案页面 learner={learner} dict_answer={dict_answer 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 GET /dictation/round-wrong 角色 student
  设 r = 调用 dictation.列本轮错词 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /dictation/wrong-book 角色 student
  设 r = 调用 dictation.取错词本 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /dictation/wrong-book/count 角色 student
  设 r = 调用 dictation.统计错词本数 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /dictation/overview 角色 student
  设 r = 调用 dictation.取默写概况 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束
