接口 GET /subject/mine
  设 r = 调用 subject.列我的科目 learner={learner} current_role={current_role}
  返回 {r}
结束

接口 POST /subject/switch 动作 subject_switch
  设 r = 调用 subject.切换科目 learner={learner} current_role={current_role} subject={subject}
  设 _msg = 已切换科目
  消息 系统 {_msg} ok
结束

接口 GET /subject/manageable 角色 teacher
  设 r = 调用 subject.列可管理科目 learner={learner} current_role={current_role} auth_mode={auth_mode 或}
  返回 {r}
结束

接口 GET /subject/detail 角色 teacher
  设 r = 调用 subject.科目详情 learner={learner} subject_id={subject_id} current_role={current_role} auth_mode={auth_mode 或}
  返回 {r}
结束

接口 POST /subject/manage/home 动作 subject_manage_home 角色 teacher
  设 r = 调用 subject.科目管理页面 learner={learner} current_role={current_role 或} auth_mode={auth_mode 或}
  响应 state {r}
结束

接口 POST /subject/manage/open 动作 subject_open 角色 teacher
  设 r = 调用 subject.载入科目页面 learner={learner} subj_id={subj_id 或} current_role={current_role 或} auth_mode={auth_mode 或}
  响应 form {r}
结束

接口 POST /subject/manage/save 动作 subject_save 角色 teacher
  设 r = 调用 subject.保存科目页面 learner={learner} subj_name={subj_name} subj_id={subj_id 或} subj_code={subj_code 或} subj_intro={subj_intro 或} subj_kind={subj_kind 或} subj_levels={subj_levels 或} subj_persona={subj_persona 或} current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 科目已保存
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /subject/manage/publish 动作 subject_publish 角色 teacher
  设 r = 调用 subject.设科目可见性页面 learner={learner} subj_id={subj_id} visibility=public current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已设为公共科目
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /subject/manage/private 动作 subject_private 角色 teacher
  设 r = 调用 subject.设科目可见性页面 learner={learner} subj_id={subj_id} visibility=private current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 已设为私有科目
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /subject/manage/enable 动作 subject_enable 角色 teacher
  设 r = 调用 subject.设科目状态页面 learner={learner} subj_id={subj_id} status=active current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 科目已启用
  消息 系统 {_msg} ok
  响应 state {r}
结束

接口 POST /subject/manage/disable 动作 subject_disable 角色 teacher
  设 r = 调用 subject.设科目状态页面 learner={learner} subj_id={subj_id} status=disabled current_role={current_role 或} auth_mode={auth_mode 或}
  设 _msg = 科目已停用
  消息 系统 {_msg} ok
  响应 state {r}
结束
