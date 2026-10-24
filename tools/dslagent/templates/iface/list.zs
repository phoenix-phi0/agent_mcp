# 接口封装模板（约定「## 接口」行写「模板 列表 键=值 …」；格式见 tools/dslagent/iftpl.py）。
模板 列表
用途 列表页取数据：函数结果（或它的某个字段）放进 lists.<键>，页面「进入时」的远程动作调它。
参数 键 必填 snake lists 下的数据键，和前端页面列表「绑」的键一字不差
参数 取 可选 snake 只把函数结果里这个字段的值放进 lists（函数返回 {rows:…} 时写 取=rows）
参数 行 可选 snake_list 逗号隔开的行字段名，都要在实体字段表里（比对约定会查），和前端列表的列对得上
例子 POST /notes/list -> 列笔记 动作 note_list 模板 列表 键=notes 行=title,content,created_at
主体
  表格 <<键>> {r}
主体 当 取
  表格 <<键>> {r.<<取>>}
