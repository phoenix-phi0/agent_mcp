用包 common text code dslproj
预算 调用 4 秒 600
# 示例（模块 graph）：#改法 一次写好全部文件 → 套上 → 加载检查 / 比对约定 / 跑用例 → 有问题派任务补改一轮 → 重查 → 终止
设 m = graph
设 res = 改文件 {e1}
如果 {res.ok} 不等于 是
  终止 失败 改法没套上：{res.msg}
结束
设 c = 加载检查 {m}
设 d = 比对约定 {m}
设 t = 跑用例 {m}
如果 {c.ok} 等于 是 且 {d.一致} 等于 是 且 {t.全过} 等于 是
  终止 成功 {m} 的加载检查、比对约定、跑用例都通过
结束
# 有问题：三份报告 + 现有文件交给子任务补改一轮
设 files = 读片段 services/graph.zs,entities/graph.entity
设 inp.files = {files}
设 inp.加载检查 = {c.问题}
设 inp.比对约定 = {d.差异}
设 inp.跑用例 = {t.失败}
设 logic = 要求：只改 services/graph.zs、entities/graph.entity、queries/graph_*.sql、routes/graph*.zs 里有问题的地方，函数头不改；edits 每项字段名固定为 file、old、new，old 从入参原文一字不差抄、不带行号前缀；新文件 old 写空串
设 r = 派任务 补改 {inp} {logic} edits:列表,note:文本
如果 {r.status} 不等于 成功
  终止 失败 补改没成：{r.reason}
结束
设 res2 = 改文件 {r.result}
如果 {res2.ok} 不等于 是
  终止 失败 补改没套上：{res2.msg}
结束
设 c2 = 加载检查 {m}
设 d2 = 比对约定 {m}
设 t2 = 跑用例 {m}
如果 {c2.ok} 等于 是 且 {d2.一致} 等于 是 且 {t2.全过} 等于 是
  终止 成功 补改一轮后通过
结束
终止 失败 补改后仍不过：加载检查 {c2.问题}；比对约定 {d2.差异}；跑用例 {t2.失败}

#改法 e1
@@ 改 services/graph.zs
<<<<<<< 原文
  公开 函数 取知识点 code
    报错 501 未实现
  结束
=======
  公开 函数 取知识点 code
    设 p = 查一行 app.db graph_point_by_code code={code}
    返回 {p}
  结束
>>>>>>> 新文
@@ 新建 queries/graph_point_by_code.sql
<<<<<<< 内容
SELECT id, code, title FROM point WHERE code = :code
>>>>>>> 新文
@@ 新建 entities/graph.entity
<<<<<<< 内容
实体 point 知识点
  字段 code 文本 必填 唯一 编号
  字段 title 文本 必填 名称
结束
>>>>>>> 新文
