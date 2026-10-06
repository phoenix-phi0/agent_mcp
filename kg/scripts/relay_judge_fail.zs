# 传达判定出错了（scripts/relay_judge.zs 抛了错：模型超时、额度、回的不是 JSON……，
# 引擎带着 error 跑这个，见「后台执行 … on_error=…」）。当「没传达到」算：这一次记
# 成「判定失败」、原因记在 relay_use.judge_note（引擎也往 stderr 打了一行），没传达到
# 的次数加一，下一条回复照常再带。学生早就拿到回复了，不受影响。
#
# 参数 use_id：relay_use 的 id；error：出错原因（引擎给的一句人话）。

用包 db

设 judge.use_id = {use_id}
设 judge.verdict = 判定失败
设 judge.quote =
设 judge.reason = 判定出错，当没传达到算：{error 或}
事务 app.db
  设 affected = 写库表 app.db relay_use_judge {judge}
  设 affected = 写库表 app.db relay_state_judge {judge}
结束
