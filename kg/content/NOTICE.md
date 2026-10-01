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
