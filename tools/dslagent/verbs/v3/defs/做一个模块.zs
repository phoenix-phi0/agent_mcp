# 做一个模块：已完成就跳过；当未完成最多 N 次：做模块（末次换模型）→ 验收（加载检查 + 比对约定 + 跑用例）→ 过了标记完成，没过带失败原因进下一次；N 次都没过 终止 失败
# 起始原因：全量回归 / 接口冒烟 发现问题后逼它重做时，第一轮就带上查出的原因（当普通的「做一个模块」调用不给，就是空串）
# 参数：模块 最多=3 末次模型=opus 起始原因?
用包 dslproj v3
设 done = 已完成 {模块}
如果 {done} 等于 是
  返回 {"status":"跳过","rounds":0}
结束
设 n = 0
设 fail_text = {起始原因}
当 {done} 不等于 是 最多 {最多} 次
  设 n = 计算 {n} + 1
  设 use_model = sonnet
  如果 {n} 等于 {最多}
    设 use_model = {末次模型}
  结束
  设 r = 做模块 {模块} {fail_text} 模型={use_model}
  设 a = 加载检查 {模块}
  设 b = 比对约定 {模块}
  设 t = 跑用例 {模块}
  如果 {a.ok} 等于 是 且 {b.consistent} 等于 是 且 {t.all_passed} 等于 是
    设 m = 标记完成 {模块}
    设 done = 是
  否则
    设 fail_text = 做模块的结果：{r.status} {r.reason} ／ 验收：加载检查：{a.problems} ／ 比对约定：{b.diffs} ／ 跑用例：{t.failures}
    设 m = 记验收 {模块} 否 {fail_text}
  结束
结束
如果 {done} 不等于 是
  终止 失败 模块 {模块} 做了 {最多} 次仍未通过：{fail_text}
结束
返回 {"status":"通过","rounds":{n}}
