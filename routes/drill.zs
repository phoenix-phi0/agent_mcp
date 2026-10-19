# 练习模式的四个接口。
#
# 这是 app2/serve.py 里那套状态机搬进 .zs 的样子。
#
# 「动作 submit」声明这个接口服务于界面上哪个动作。app2/build.py 扫
# routes/ 时把这些导出成端点表，所以加个接口前端自动知道地址——先前
# 那个表是手写的，改一边另一边不知道。
#
# 为什么不靠约定自动推：动作名和路径没有可靠对应，send 对的是 /chat。
# 靠「动作名等于路径最后一段」的话现有路由全要改名，而路径是给人看的
# URL，不该迁就界面里的变量名。
#
# 请求字段直接当变量：{learner}、{answer}、{course} 就是 POST body 里
# 的同名字段。跨请求的状态在 {session.xxx}，脚本改完自动存回
# sessions/<learner>.json。
#
# 注意：动词参数里不能有空格，**全角空格也不行**——normalize 会把它转成
# 半角，于是多切出一个参数。要拼带空格的文本，先用「设」存进变量。

服务 8090


# 没有「动作」：这个接口由界面切到练习模式时触发，不是某个按钮
接口 POST /drill/start
  用包 common quiz http

  设 session.课程 = {course}
  设 session.考点 = {kind}
  设 session.对 = 0
  设 session.总 = 0
  设 session.错题 =

  # 「全部考点」是下拉里的占位项，对动词来说等于不筛选
  如果 {session.考点} 等于 全部考点
    设 session.考点 =
  结束

  设 code = 挑题号 content/n2n3/题库 1 {session.课程} {session.考点}
  如果 {code} 为空
    消息 系统 没有匹配的题目：{session.课程} no
  否则
    设 session.题号 = {code}
    设 question = 取题 content/n2n3/题库 {code}
    消息 题目 {question}
    设 progress_text = {session.课程}　尚未作答
    状态 stat {progress_text}
  结束
结束


接口 POST /drill/answer 动作 submit
  用包 common quiz http

  如果 {session.题号} 为空
    消息 系统 当前没有待答的题 no
  否则
    设 result = 判题 content/n2n3/题库 {session.题号} {answer}
    设 session.总 = 计算 {session.总} + 1

    # 判题结果以 ○ 开头表示答对。这个约定散在好几处，
    # 等输出结构化之后应该换成显式字段。
    如果 {result} 开头是 ○
      设 session.对 = 计算 {session.对} + 1
      消息 批改 {result} ok
    否则
      设 session.错题 = {session.错题},{session.题号}
      消息 批改 {result} no
    结束

    设 session.题号 =
    设 ratio = 计算 四舍五入({session.对} * 100 / {session.总})
    设 progress_text = {session.课程}　{session.对}/{session.总}（{ratio}%）
    状态 stat {progress_text}
  结束
结束


接口 POST /drill/next 动作 next
  用包 common quiz http

  设 code = 挑题号 content/n2n3/题库 1 {session.课程} {session.考点}
  如果 {code} 为空
    消息 系统 这一课的题出完了 no
  否则
    设 session.题号 = {code}
    设 question = 取题 content/n2n3/题库 {code}
    消息 题目 {question}
  结束
结束


接口 POST /drill/stop 动作 stop
  用包 common quiz http

  如果 {session.总} 为空
    消息 系统 本来就没在练习
  否则
    # 一道没答时总数是 0，除不了，正确率按 0 算
    设 ratio = 0
    如果 {session.总} 大于 0
      设 ratio = 计算 四舍五入({session.对} * 100 / {session.总})
    结束
    设 recap = 练习结束：{session.对}/{session.总}（{ratio}%）\n错题：{session.错题}
    消息 系统 {recap} ok
  结束

  设 session.题号 =
  设 session.总 =
  设 session.对 =
  状态 stat
结束
