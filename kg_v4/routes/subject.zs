接口 GET /subject/mine
  设 r = 调用 subject.列我的科目 learner={learner} current_role={current_role}
  返回 {r}
结束

接口 POST /subject/switch 动作 subject_switch
  设 r = 调用 subject.切换科目 learner={learner} current_role={current_role} subject={subject}
  设 _msg = 已切换科目
  消息 系统 {_msg} ok
结束
