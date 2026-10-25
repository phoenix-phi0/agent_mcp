用包 common text code dslproj
预算 调用 8 秒 900
# 示例（模块 graph）：改动拆成小段（e1 实体+查询、e2 业务函数），每套一段就查一轮 → 没过进补改循环 →
# 直到三项检查全过（终止 成功）/ 预算用完（引擎自动按 超出预期 收场，不用你管）/ 连续两轮检查输出完全相同（终止 失败 防空转）/ 轮数用完（终止 失败）
设 m = graph
设 res = 改文件 {e1}
如果 {res.ok} 不等于 是
  终止 失败 改法 e1 没套上：{res.msg}
结束
设 c = 加载检查 {m}
设 d = 比对约定 {m}
设 t = 跑用例 {m}
如果 {c.ok} 等于 是 且 {d.consistent} 等于 是 且 {t.all_passed} 等于 是
  终止 成功 e1 套上后三项检查就全过
结束
设 res = 改文件 {e2}
如果 {res.ok} 不等于 是
  终止 失败 改法 e2 没套上：{res.msg}
结束
设 c = 加载检查 {m}
设 d = 比对约定 {m}
设 t = 跑用例 {m}
如果 {c.ok} 等于 是 且 {d.consistent} 等于 是 且 {t.all_passed} 等于 是
  终止 成功 各段套上后三项检查就全过
结束
# 补改循环：每轮只修当轮检查报出的问题，把三份报告的当轮原文 + 本模块文件交给 派任务；轮数 K ≤ 预算 N − 1
设 prev.c = 未跑
设 prev.d = 未跑
设 prev.t = 未跑
重复 6 次 计数 k
  如果 {c.problems} 等于 {prev.c} 且 {d.diffs} 等于 {prev.d} 且 {t.failures} 等于 {prev.t}
    终止 失败 连续两轮三项检查输出完全相同（补改没有进展），第 {k} 轮停：加载检查 {c.problems}；比对约定 {d.diffs}；跑用例 {t.failures}
  结束
  设 prev.c = {c.problems}
  设 prev.d = {d.diffs}
  设 prev.t = {t.failures}
  设 files = 读片段 entities/graph.entity:全文,services/graph.zs:全文,routes/graph*.zs:全文,queries/graph_*.sql:全文
  设 inp.files = {files}
  设 inp.加载检查 = {c.problems}
  设 inp.比对约定 = {d.diffs}
  设 inp.跑用例 = {t.failures}
  设 logic = 要求：只修入参三份报告里报出的问题，报告没点名的不要动；只改 services/graph.zs、entities/graph.entity、queries/graph_*.sql、routes/graph*.zs，函数头不改；edits 每项是 {file, old, new, line?}，old 从入参原文一字不差抄、不带行号前缀，可能出现多次的写 line；新文件 old 写空串
  设 r = 派任务 第{k}轮补改 {inp} {logic} edits:列表,note:文本
  如果 {r.status} 不等于 成功
    终止 失败 补改没成：{r.reason}
  结束
  设 res = 改文件 {r.result}
  如果 {res.ok} 不等于 是
    终止 失败 补改没套上或没改任何文件：{res.msg}
  结束
  设 c = 加载检查 {m}
  设 d = 比对约定 {m}
  设 t = 跑用例 {m}
  如果 {c.ok} 等于 是 且 {d.consistent} 等于 是 且 {t.all_passed} 等于 是
    终止 成功 第 {k} 轮补改后三项检查全过
  结束
结束
终止 失败 补改 6 轮仍不过：加载检查 {c.problems}；比对约定 {d.diffs}；跑用例 {t.failures}

#改法 e1
[
  {"file": "queries/graph_point_by_code.sql", "old": "", "new": "SELECT id, code, title FROM point WHERE code = :code\n"},
  {"file": "entities/graph.entity", "old": "", "new": "实体 point 知识点\n  字段 code 文本 必填 唯一 编号\n  字段 title 文本 必填 名称\n结束\n"}
]
#改法 e2
[
  {"file": "services/graph.zs", "old": "  公开 函数 取知识点 code\n    报错 501 未实现\n  结束", "new": "  公开 函数 取知识点 code\n    设 p = 查一行 app.db graph_point_by_code code={code}\n    返回 {p}\n  结束", "line": 12}
]
