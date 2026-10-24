# 接口封装模板（约定「## 接口」行写「模板 状态 键=数据键 [取=字段]」；格式见 tools/dslagent/iftpl.py）。
模板 状态
用途 进入时取状态：函数结果（或它的某个字段）放进 state.<键>，页面的「共享」字段和「显示」节点读它。
参数 键 必填 snake state 下的数据键，和前端页面读 state.<键> 的键一字不差
参数 取 可选 snake 只把函数结果里这个字段的值放进 state
例子 POST /notes/stats -> 读统计 动作 note_stats 模板 状态 键=stats
主体
  响应 state {"<<键>>":{r}}
主体 当 取
  响应 state {"<<键>>":{r.<<取>>}}
