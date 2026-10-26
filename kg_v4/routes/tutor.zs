接口 POST /tutor/ask 动作 teacher_send 角色 student
  设 r = 调用 tutor.问老师页面 learner={learner} message={content 或} lesson={lesson 或}
  消息 老师 {r.reply} ok
结束

接口 POST /tutor/history 动作 teacher_state 角色 student
  设 r = 调用 tutor.列对话页面 learner={learner}
  响应 state {"talk":{r.talk}}
结束

接口 POST /quiz/summary 动作 quiz_summary 角色 student
  设 r = 调用 tutor.总结页面 learner={learner}
  响应 state {r}
结束

接口 POST /tutor/explain 角色 student
  设 r = 调用 tutor.讲解一课 learner={learner} lesson_code={lesson_code}
  返回 {r}
结束

接口 GET /tutor/messages 角色 student
  设 r = 调用 tutor.列对话 learner={learner} limit={limit 或}
  返回 {r}
结束

接口 POST /tutor/summarize-round 角色 student
  设 r = 调用 tutor.总结本轮 learner={learner}
  返回 {r}
结束
