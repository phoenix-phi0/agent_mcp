# 单词导入，用引擎自己写（原来是 Python：tools/word_import.py）。
#
# 当初写成 Python 的两个理由现在都没了：
#   逐条报错要说第几条 → 遍历有「序号 i」
#   可选字段缺了会留成 {item.kanji} 字面量 → 取值有「{item.kanji 或}」
#
# 按「汉字+假名」认同一个词：光看假名会把同音词当成一个（はし 是桥也是
# 筷子），光看汉字则漏掉没有汉字的词。所以先查再决定插还是改。
#
# 知识点不存在时词照样导，只是不挂——一个拼错的编号不该让整批词都进不去，
# 而挂错知识点比没挂更难发现。

接口 POST /word/import2 动作 word_import2
  用包 common db http

  设 file = {file 或 content/words.jsonl}
  读JSONL words = {file}

  设 added = 0
  设 updated = 0
  设 skipped = 0
  设 no_point = 0
  设 bad_point = 0
  设 note = 

  事务 app.db
    遍历 item 于 {words} 序号 row
      设 kana = {item.kana 或}
      设 meaning = {item.meaning 或}

      如果 {kana} 为空
        设 skipped = 相加 {skipped} 1
        设 note = {note} 第{row}条缺假名；
      否则
        设 word.kanji = {item.kanji 或}
        设 word.kana = {kana}
        设 word.meaning = {meaning}
        设 word.point = {item.point 或}

        # 知识点填了但库里没有：不挂，词照样导
        如果 {word.point} 不为空
          设 exists = 查一值表 app.db node_exists {word}
          如果 {exists} 为空
            设 bad_point = 相加 {bad_point} 1
            设 note = {note} 第{row}条的知识点{word.point}不存在；
            设 word.point = 
          结束
        结束

        # 没挂知识点的计数放在插入/更新之前：放在插入分支里的话，第二遍
        # 导入（走更新）就数不到，报告里那一项凭空消失。
        如果 {word.point} 为空
          设 no_point = 相加 {no_point} 1
        结束

        设 old = 查一值表 app.db word_find {word}
        如果 {old} 为空
          设 affected = 写库表 app.db word_insert {word}
          设 added = 相加 {added} 1
        否则
          设 word.id = {old}
          设 affected = 写库表 app.db word_update {word}
          设 updated = 相加 {updated} 1
        结束
      结束
    结束
  结束

  返回 {"new":"{added}","updated":"{updated}","skipped":"{skipped}","no_point":"{no_point}","bad_point":"{bad_point}","note":"{note}"}
结束
