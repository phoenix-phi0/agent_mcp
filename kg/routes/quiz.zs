# 做题：导入题目、出题、判题、记进学习记录。界面在 ui/quiz.ui。
#
# 题目的源文件在 workspace/japanese/content/bunpou/题库/（沿用旧题库格式，
# quiz 包的「挑题」「判题」也读它）。那个目录在本项目之外，读JSONL 碰不到，
# 所以由 py -m kg 读出来、把整批题放在请求里交给 /quiz/import——怎么进库
# 还是写在这里。
#
# 当前那道题记在 quiz_state 里，不由前端传：判的永远是库里记的那道，
# 同一道交两次只算一次（见 queries/quiz_state_answer.sql）。
#
# 判题用 quiz 包的「判对错」，跟「判题」同一套规则：选择题抓选项字母，
# 接续题整段比对（只认标准答案和「可接受」里列的写法）。
#
# 学习者不传就是 me，跟 learn.zs 同一个默认值。达标线也一样：80%、至少 8 题。


# 整批导入。整表清空重灌，在一个事务里：有坏题（缺题号、缺答案、题号重复）
# 就全部回滚，库里保持原样。条目对不上的题不进库、只计数，报告里说是哪道。
接口 POST /quiz/import
  用包 common db http

  设 题表 = {rows 或}
  如果 {题表} 为空
    返回 {"error":"没有题（rows 是空的）"} 400
  结束

  设 进库 = 0
  设 没进 = 0
  设 说明 = 

  事务 app.db
    设 影响 = 写库 app.db question_clear
    遍历 项 于 {题表} 序号 行
      设 题.code = {项.id 或}
      设 题.course = {项.课程 或}
      设 题.kind = {项.考点 或}
      设 题.difficulty = {项.难度 或}
      设 题.qtype = {项.题型 或}
      设 题.stem = {项.题干 或}
      设 题.answer = {项.答案 或}
      设 题.accept = {项.可接受 或}
      设 题.explain = {项.解析 或}
      设 题.item = {项.条目 或}
      设 题.lesson = {项.课文 或}
      设 影响 = 写库表 app.db question_insert {题}
      如果 {影响} 等于 1
        设 进库 = 相加 {进库} 1
      否则
        设 没进 = 相加 {没进} 1
        设 说明 = {说明}{题.code}的条目「{题.item}」不在库里；
      结束
    结束
  结束

  返回 {"questions":"{进库}","skipped":"{没进}","note":"{说明}"}
结束


# 进页面时：把上次选的等级、考点填回去，显示这一轮的成绩。
#
# 不把上次没答完的那道题重新推出来：进页面这个动作切一次界面就跑一次，
# 推出来的话来回切几次，消息流里就叠几份同一道题。上次那道就放着，
# 点「开始」或「下一题」接着做。
接口 POST /quiz/state 动作 quiz_state
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}

  设 表.pick_level = {进度.pick_level 或 全部}
  设 表.pick_kind = {进度.pick_kind 或 全部}
  响应 form {表}
  设 状态.stat = {进度.stat 或}
  响应 state {状态}
结束


# 开始：按选的等级、考点出第一道，这一轮的计数清零。
接口 POST /quiz/start 动作 quiz_start
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 等级 = {pick_level 或 全部}
  设 考点 = {pick_kind 或 全部}

  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 抽.learner = {学习者}
  设 抽.level = {等级}
  设 抽.kind = {考点}
  设 抽.last = {进度.current 或}
  设 题号 = 查一值表 app.db question_pick {抽}
  如果 {题号} 为空
    返回 {"error":"这个等级和考点下没有题"} 404
  结束

  设 记.learner = {学习者}
  设 记.level = {等级}
  设 记.kind = {考点}
  设 记.code = {题号}
  设 记.reset = 1
  设 影响 = 写库表 app.db quiz_state_pick {记}

  设 取.code = {题号}
  设 题 = 查一行表 app.db question_show {取}
  设 消息.who = 题目
  设 消息.text = {题.text}
  响应 messages {消息}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 状态.qtype = {题.qtype}
  设 状态.phase = ask
  设 状态.stat = {进度.stat}
  响应 state {状态}
结束


# 下一题：跟「开始」一样出题，只是不清零这一轮的计数。等级、考点用页面上
# 现在选的——中途换了考点，下一道就按新的出。
接口 POST /quiz/next 动作 quiz_next
  用包 db http

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 等级 = {pick_level 或 全部}
  设 考点 = {pick_kind 或 全部}

  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 抽.learner = {学习者}
  设 抽.level = {等级}
  设 抽.kind = {考点}
  设 抽.last = {进度.current 或}
  设 题号 = 查一值表 app.db question_pick {抽}
  如果 {题号} 为空
    返回 {"error":"这个等级和考点下没有题"} 404
  结束

  设 记.learner = {学习者}
  设 记.level = {等级}
  设 记.kind = {考点}
  设 记.code = {题号}
  设 记.reset = 0
  设 影响 = 写库表 app.db quiz_state_pick {记}

  设 取.code = {题号}
  设 题 = 查一行表 app.db question_show {取}
  设 消息.who = 题目
  设 消息.text = {题.text}
  响应 messages {消息}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 状态.qtype = {题.qtype}
  设 状态.phase = ask
  设 状态.stat = {进度.stat}
  响应 state {状态}
结束


# 作答：判当前那道，记进学习记录（跟 /learn/answer 同一套：流水、汇总、
# 掌握标记，一个事务），回对错和解析。
#
# 选择题看 choice（单选），接续题看 given（输入框）。
接口 POST /quiz/answer 动作 quiz_answer
  用包 common db http quiz

  设 学习者 = {learner 或}
  如果 {学习者} 为空
    设 学习者 = me
  结束
  设 正确率 = {rate 或}
  如果 {正确率} 为空
    设 正确率 = 80
  结束
  设 最少题数 = {min_count 或}
  如果 {最少题数} 为空
    设 最少题数 = 8
  结束

  设 查.learner = {学习者}
  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 当前 = {进度.current 或}
  如果 {当前} 为空
    返回 {"error":"还没出题，先点「开始」"} 400
  结束
  如果 {进度.answered} 等于 1
    返回 {"error":"这道已经答过了，点「下一题」"} 400
  结束

  设 键查.code = {当前}
  设 键 = 查一行表 app.db question_key {键查}
  设 作答 = {given 或}
  如果 {键.qtype} 等于 选择
    设 作答 = {choice 或}
  结束
  如果 {作答 或} 为空
    返回 {"error":"还没作答"} 400
  结束

  设 判.题型 = {键.qtype}
  设 判.答案 = {键.answer}
  设 判.可接受 = {键.accept}
  设 判.作答 = {作答}
  设 对错 = 判对错 {判}

  设 刚达标 = 否
  事务 app.db
    设 交.learner = {学习者}
    设 交.code = {当前}
    设 交.choice = {choice 或}
    设 交.given = {given 或}
    设 交.correct = {对错}
    设 影响 = 写库表 app.db quiz_state_answer {交}

    # 影响 0：同一道刚被交过（两个请求挤在一起）。不再记学习记录
    如果 {影响} 等于 1
      设 记.learner = {学习者}
      设 记.point = {键.point}
      设 记.item = {当前}
      设 记.correct = {对错}
      设 影响 = 写库表 app.db attempt_insert {记}
      设 影响 = 写库表 app.db mastery_bump {记}

      设 条件.learner = {学习者}
      设 条件.point = {键.point}
      设 条件.rate = {正确率}
      设 条件.min_count = {最少题数}
      设 现状 = 查一行表 app.db mastery_one {条件}
      如果 {现状.ok} 等于 1
        如果 {现状.mastered} 等于 0
          设 刚达标 = 是
        结束
      结束
      设 标记.learner = {学习者}
      设 标记.point = {键.point}
      设 标记.mastered = {现状.ok}
      设 影响 = 写库表 app.db mastery_set {标记}
    结束
  结束

  设 判后.code = {当前}
  设 判后.correct = {对错}
  设 结果 = 查一行表 app.db question_verdict {判后}
  # 不能写「判题」：那是 quiz 包的动词名，右边整个是它就会被当成调用
  设 消息.who = 批改
  设 消息.text = {结果.text}
  设 消息.kind = no
  如果 {对错} 等于 1
    设 消息.kind = ok
  结束
  响应 messages {消息}
  如果 {刚达标} 等于 是
    设 喜报.who = 进度
    设 喜报.text = 「{键.point_label}」达标了，图上它后面的知识点可能解锁了。
    设 喜报.kind = ok
    响应 messages {喜报}
  结束

  设 进度 = 查一行表 app.db quiz_state_one {查}
  设 状态.phase = done
  设 状态.stat = {进度.stat}
  响应 state {状态}
结束
