# 知识图谱的接口。导入 + 几个图查询。
#
# 查询都只收一个 code 参数，值里不会有空格，所以直接用「查询」按位置传。
# SQL 在 queries/kg_*.sql。

服务 8190-8199

# 已有的库按实体只加不改：后加的表、列、索引补上，学习记录表绝不重建
# （tools/migrate.py）。py -m kg、gen run、双击 app.pyw 都走这一步
迁移 只加


# 导入在 kg_import.zs 里，用引擎自己写的（读 JSONL、遍历、写库都是 DSL）。


# 导出。file 不给就写到 content/export.jsonl；扩展名是 .json 就导成 JSON 数组。
# 不默认写回 content/kg.jsonl：那是手写的源文件，覆盖它该是人明确要的。
接口 POST /kg/export 动作 kg_export
  用包 kg http
  设 file = {file}
  如果 {file} 为空
    设 file = content/export.jsonl
  结束
  设 result = 导出图谱JSON app.db {file}
  返回 {result}
结束


接口 POST /kg/roots 动作 kg_roots
  用包 db http
  设 rows = 查询 app.db kg_roots
  设 group.roots = {rows}
  响应 lists {group}
结束


# 按依赖分层，depth 从 0 开始。按 depth 排就是一个合法的学习顺序。
接口 POST /kg/levels 动作 kg_levels
  用包 db http
  设 rows = 查询 app.db kg_levels
  设 group.levels = {rows}
  响应 lists {group}
结束


# 学 code 之前要先会的全部知识点，dist 是最近的距离
接口 POST /kg/ancestors 动作 kg_ancestors
  用包 db http
  设 rows = 查询 app.db kg_ancestors code={code}
  设 group.ancestors = {rows}
  响应 lists {group}
结束


# 会了 code 之后往后能学到的全部知识点
接口 POST /kg/descendants 动作 kg_descendants
  用包 db http
  设 rows = 查询 app.db kg_descendants code={code}
  设 group.descendants = {rows}
  响应 lists {group}
结束


接口 POST /kg/contrasts 动作 kg_contrasts
  用包 db http
  设 rows = 查询 app.db kg_contrasts code={code}
  设 group.contrasts = {rows}
  响应 lists {group}
结束
