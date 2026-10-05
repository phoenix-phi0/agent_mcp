# 按知识点查词。挂接本身不用单独的接口了——一个词属于一个知识点，就是
# word 表上的一列，改它用生成的那套增删改查（编辑浮层里选知识点）。
#
# 这个项目没有开认证（没跑过 gen auth），所以接口上不写「公开」——那个
# 标记只在开了认证的项目里有意义。


# 批量导入单词。file 不给就导 content/words.jsonl。
接口 POST /word/import 动作 word_import
  用包 kg http
  设 file = {file}
  如果 {file} 为空
    设 file = content/words.jsonl
  结束
  设 report = 导入单词JSON app.db {file}
  返回 {report}
结束


# 一个知识点下面有哪些词。出题时用这个取。
接口 POST /point/words 动作 point_words
  用包 db http
  设 rows = 查询 app.db word_by_point point={point} limit=200
  设 group.words = {rows}
  响应 lists {group}
结束


# 还没挂到知识点上的词。批量导入之后先看这个。
接口 POST /word/orphans 动作 word_orphans
  用包 db http
  设 rows = 查询 app.db word_orphans limit=200
  设 group.words = {rows}
  响应 lists {group}
结束
