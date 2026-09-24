# 知识图谱的接口。导入 + 几个图查询。
#
# 查询都只收一个 code 参数，值里不会有空格，所以直接用「查询」按位置传。
# SQL 在 queries/kg_*.sql。

服务 8190-8199


# 导入在 kg_import.zs 里，用引擎自己写的（读 JSONL、遍历、写库都是 DSL）。


# 导出。file 不给就写到 content/export.jsonl；扩展名是 .json 就导成 JSON 数组。
# 不默认写回 content/kg.jsonl：那是手写的源文件，覆盖它该是人明确要的。
接口 POST /kg/export 动作 kg_export
  用包 kg http
  设 文件 = {file}
  如果 {文件} 为空
    设 文件 = content/export.jsonl
  结束
  设 结果 = 导出图谱JSON app.db {文件}
  返回 {结果}
结束


接口 POST /kg/roots 动作 kg_roots
  用包 db http
  设 行表 = 查询 app.db kg_roots
  设 组.roots = {行表}
  响应 lists {组}
结束


# 按依赖分层，depth 从 0 开始。按 depth 排就是一个合法的学习顺序。
接口 POST /kg/levels 动作 kg_levels
  用包 db http
  设 行表 = 查询 app.db kg_levels
  设 组.levels = {行表}
  响应 lists {组}
结束


# 学 code 之前要先会的全部知识点，dist 是最近的距离
接口 POST /kg/ancestors 动作 kg_ancestors
  用包 db http
  设 行表 = 查询 app.db kg_ancestors code={code}
  设 组.ancestors = {行表}
  响应 lists {组}
结束


# 会了 code 之后往后能学到的全部知识点
接口 POST /kg/descendants 动作 kg_descendants
  用包 db http
  设 行表 = 查询 app.db kg_descendants code={code}
  设 组.descendants = {行表}
  响应 lists {组}
结束


接口 POST /kg/contrasts 动作 kg_contrasts
  用包 db http
  设 行表 = 查询 app.db kg_contrasts code={code}
  设 组.contrasts = {行表}
  响应 lists {组}
结束
