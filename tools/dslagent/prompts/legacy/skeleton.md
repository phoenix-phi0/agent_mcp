【语法示意（只示意写法，不是答案）】
用包 common text code
设 done = 否
设 t = 跑测试
遍历 k 于 1，2
  如果 {done} 等于 否
    问JSON v = 根据失败 {t.summary} 判断 格式 action:继续|停 reason:文本
    如果 {v.action} 等于 停
      设 done = 是
    结束
    打印 第 {k} 轮：{v.action} {v.reason}
  结束
结束
打印 结论：没修好 示意而已