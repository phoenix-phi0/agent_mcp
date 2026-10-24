# 接口封装模板（约定「## 接口」行写「模板 页面状态 [取=字段]」；格式见 tools/dslagent/iftpl.py）。
模板 页面状态
用途 整页状态投放：页面聚合函数一次返回整页数据（顶层键=页面 state 根键），整体铺进 state；列表数据键也放返回里（前端 rowsOf 先查 lists 再回退共享状态，同样喂列表）。
参数 取 可选 snake 只铺函数结果里这个字段的值（聚合函数返回 {page:…} 时写 取=page）
例子 POST /page/quiz/state -> 做题页面 动作 quiz_state 模板 页面状态
主体
  响应 state {r}
主体 当 取
  响应 state {r.<<取>>}
