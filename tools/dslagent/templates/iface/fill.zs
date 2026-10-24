# 接口封装模板（约定「## 接口」行写「模板 回填 [取=字段]」；格式见 tools/dslagent/iftpl.py）。
模板 回填
用途 表单页回填：函数结果（或它的某个字段）放进 form，页面「载入」时取数据回填表单。
参数 取 可选 snake 只把函数结果里这个字段的值放进 form（函数返回 {row:…} 时写 取=row）
例子 POST /notes/one -> 取笔记 动作 note_one 模板 回填
主体
  响应 form {r}
主体 当 取
  响应 form {r.<<取>>}
