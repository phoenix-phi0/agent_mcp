# 词表来源

## words.jsonl

从本项目自己的题库（workspace/japanese/content/n2n3/题库）抽取：
词和中文释义来自题库的题干与解析，读音用模型补齐后机器校验
（必须是平假名，且送假名要跟词尾对得上）。

另含手工整理的几类固定表：五十音、日期时刻、数量词、敬语动词、
自他动词对、动词变形例子。资料查多份日语教学材料交叉核对。

## words_jlpt.jsonl

来自 **OpenJLPT**（https://github.com/evanclan/OpenJLPT），
许可 **CC BY-SA 4.0**。

OpenJLPT 本身的上游：

- **JMdict / EDICT**，© Electronic Dictionary Research and
  Development Group，CC BY-SA 4.0 —— 词条、读音、释义、词性
- **Jonathan Waller 的 JLPT 词表**，CC BY —— N5–N1 等级划分
- **Tatoeba**，CC BY —— 例句（本项目未导入）

本项目的改动：按 JMdict 的词性码（v5\*、v1、adj-i、adj-na、n、adv）
把词挂到知识图谱的对应节点上；释义取前三条，前面加等级标记；
例句和罗马音没有导入。

释义是英文——JMdict 的日英词典，没有中文层。

# 课文来源

## lessons.jsonl、item_lessons.jsonl

语法点取自 **hanabira.org** 的日语语法库
（https://hanabira.org ，内容仓库 https://github.com/tristcoil/hanabira.org-japanese-content ），
许可 **CC BY 4.0**。

本项目的改动（CC BY 要求注明）：

- 只取了跟本项目条目对得上的 125 个语法点（N5 38、N4 37、N3 26、N2 22、N1 2），
  对应关系在 item_lessons.jsonl。
- 讲解不是逐句翻译：按中国学习者重写成中文，英文原文里的接续错误、
  意思偏差一并改正（如五段动词被动形、ところが 的用法、以上 的意思）。
- 逐句核对了例句。不自然、用错语法点、违反常识的改写了（lessons.jsonl 里
  changed=1 的课）；原句、新句和理由记在 lesson_review.jsonl。
- 原标题保留在 source_title 字段。

hanabira 自己说明内容是自建的、可能有错；核对时确实发现约四成的课有例句
问题，所以不要直接拿原始数据替换这里的文件。
