# 教材导入：后台解析一块出错了（scripts/import_chunk.zs 抛了错，引擎带着 error
# 跑这个，见「后台执行 … on_error=…」）。把块标成出错、记下那句人话，页面上
# 能看到原因、能重试这一块。
#
# 参数 chunk：import_chunk 的 id；error：出错原因（引擎给的，模型的错是
# 「模型没有回应：…」）。

用包 db

设 fail.chunk = {chunk}
设 fail.error = {error 或}
设 affected = 写库表 app.db import_chunk_fail {fail}
