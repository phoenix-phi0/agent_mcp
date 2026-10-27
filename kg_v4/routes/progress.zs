接口 POST /progress/answer 角色 student
  设 r = 调用 progress.记作答 learner={learner} point_code={point_code} question_no={question_no} correct={correct} answer={answer 或} pass_line={pass_line 或} fall_line={fall_line 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /progress/state 角色 student
  设 r = 调用 progress.取状态 learner={learner} point_code={point_code 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /progress/next 角色 student
  设 r = 调用 progress.算下一步 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /progress/overview 角色 student
  设 r = 调用 progress.取概览 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /progress/scores 角色 student
  设 r = 调用 progress.列得分 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /progress/recent 角色 student
  设 r = 调用 progress.列最近作答 learner={learner} limit={limit 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 GET /progress/levels 角色 student
  设 r = 调用 progress.按级统计掌握 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  返回 {r}
结束

接口 POST /progress/scores/rebuild 角色 teacher
  设 r = 调用 progress.重建全部得分 pass_line={pass_line 或} fall_line={fall_line 或}
  返回 {r}
结束

接口 POST /progress/page 动作 progress_page 角色 student
  设 r = 调用 progress.进度页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /progress/graph 动作 node_list 角色 student
  设 r = 调用 progress.图谱页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束

接口 POST /progress/point 动作 node_detail 角色 student
  设 r = 调用 progress.知识点页面 learner={learner} code={code} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
  响应 state {r}
结束
