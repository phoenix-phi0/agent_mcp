# 修复2：核查 → 改 → 再核查，最多 rounds 轮修改（核查次数 = 修改轮数 + 1，每次改完都核查）。每次核查：执行 audit2.zs（同级目录里的脚本）；ok → 终止 成功；contract_issue / unchecked → 终止 失败并说明；
# module_issue → 还没改满 rounds 轮就执行 change2.zs（只做一轮，按模块分组派 modify_module）→ 再核查；改满 rounds 轮后的最后一次核查仍不是 ok → 终止 失败，带最后一次核查结果。
# 终止信息里带轮数和每轮改了哪些模块。
# 提前停：连续两轮 change2 一个模块都没改成、且没改成的是同一组模块 → 终止 失败。modify_module 失败时改动整个丢弃，
# 下一轮核查看到的还是同样的文件，再改也是同一个结果（K141：同一个「超出预期」拒改重复了 5 轮）。没改成的原因是模型写的文字、每轮措辞不同，所以只比模块。
# 参数：req（保留给 CLI）llm=sonnet rounds=5；scope / modules（可省，模块范围，原样传给 audit2.zs，见那里的说明）；syntax 由 run_entry 注入（prompts/project_syntax.md 全文）
用包 common v3 text
设 hist = 解析JSON []
设 n = 0
设 prev = -
设 total = 计算 {rounds} + 1
重复 {total} 次
  设 n = 计算 {n} + 1
  设 a = 执行 audit2.zs req={req} llm={llm} syntax={syntax} scope={scope} modules={modules}
  如果 {a.result 或} 等于 ok
    终止 成功 第 {n} 轮核查通过；各轮改动：{hist}
  结束
  如果 {a.result 或} 等于 contract_issue
    终止 失败 第 {n} 轮核查：约定有问题，需回到规划：{a.issues}；各轮改动：{hist}
  结束
  如果 {a.result 或} 等于 unchecked
    终止 失败 第 {n} 轮核查：有模块没核查成：{a.unchecked}；各轮改动：{hist}
  结束
  如果 {a.result 或} 不等于 module_issue
    终止 失败 第 {n} 轮核查没有得出结果：{a.reason 或}；各轮改动：{hist}
  结束
  如果 {n} 等于 {total}
    终止 失败 改了 {rounds} 轮后最后一次核查仍有问题；最后一次核查结果：{a}；各轮改动：{hist}
  结束
  设 c = 执行 change2.zs req={req}
  设 line = 第{n}轮：改了 {c.changed 或}，没改成 {c.failed 或}
  设 hist = 列表加项 {hist} {line}
  设 key = -
  如果 {c.cmods 或} 为空
    设 key = 没改成{c.fmods 或}
  结束
  如果 {key} 不等于 - 且 {key} 等于 {prev}
    终止 失败 连续两轮修改都没改成（同样的模块 {c.fmods 或}），改动都被丢弃、再改也是同样结果，提前停止；各轮改动：{hist}
  结束
  设 prev = {key}
结束
终止 失败 核查流程没有走完；最后一次核查结果：{a}；各轮改动：{hist}
