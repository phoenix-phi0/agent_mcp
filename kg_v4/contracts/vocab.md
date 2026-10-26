模块 vocab
依赖 kg

## 表
表 vocab_word
  kanji 文本 汉字，可空（假名表条目没有汉字）
  kana 文本 假名，必填
  meaning 文本 中文意思，可空（假名表条目没有意思）
  point_code 文本 所属知识点编号，可空（空表示孤儿词）；不加外键

## 函数
公开 函数 列单词 keyword? point_code?
  返回 {total, words}，words 是 [{id, kanji, kana, meaning, point_code}]，按 id 升序
  伪代码 查 vocab_word 全部行
  伪代码 keyword 不为空时，只留下 kanji、kana、meaning 任一字段包含 keyword 的行
  伪代码 point_code 不为空时，只留下 point_code 等于该值的行
  伪代码 按 id 升序，返回 {"total": 行数, "words": 列表}

公开 函数 取单词 word_id? kanji? kana?
  返回 {id, kanji, kana, meaning, point_code}；查不到返回空
  报错 400 word_id 和 kana 至少要给一个
  伪代码 word_id 为空且 kana 为空，报错 400 word_id 和 kana 至少要给一个
  伪代码 word_id 不为空：按 id 查 vocab_word 一行
  伪代码 word_id 为空：按 kanji + kana 同时相等查一行（kanji 为空串时匹配汉字为空的词）
  伪代码 查不到则返回空
  伪代码 返回该行 {"id": id, "kanji": kanji, "kana": kana, "meaning": meaning, "point_code": point_code}

公开 函数 按知识点列单词 point_code
  返回 {point_code, total, words}，words 同「列单词」
  报错 404 没有这个知识点
  伪代码 调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
  伪代码 查 vocab_word 中 point_code 相等的行，按 id 升序
  伪代码 返回 {"point_code": point_code, "total": 行数, "words": 列表}

公开 函数 列孤儿词
  返回 {total, words}，words 同「列单词」；孤儿词指没有挂知识点（point_code 为空）的词
  伪代码 查 vocab_word 中 point_code 为空的行，按 id 升序
  伪代码 返回 {"total": 行数, "words": 列表}

公开 函数 挑默写词 direction level? point_code? only_ids? skip_ids? seed
  返回 {total, word}：total 是满足下面全部条件的词数；word 是其中按排序的第 (seed 对 total 取余) 个（从 0 数）单词对象；排序：only_ids 为空按 id 升序；only_ids 不为空时按单词编号在 only_ids 里出现的先后（错词复习要保持错词本的顺序） {id, kanji, kana, meaning, point_code}，total 为 0 时 word 为空
  伪代码 这是给默写选词用的：筛选、数数、挑第几个都在一条 SQL 里做，不把整张表取回来再逐词循环（8105 个词时要在 1 秒内）。direction 为 zh2jp 或 kanji2kana，其他值当 zh2jp
  伪代码 条件（对 vocab_word 每行，全部满足才算）：①direction 为 zh2jp 要求 meaning 不为空；direction 为 kanji2kana 要求 kanji 不为空且不等于 kana；②level 不为空时要求 meaning 以「[level]」开头；③point_code 不为空时要求行的 point_code 等于它；④only_ids 不为空（逗号隔开的单词编号）时要求 id 在其中；⑤skip_ids 不为空（逗号隔开）时要求 id 不在其中
  伪代码 再排除不是词义的词条（和默写原来的口径一字不差）：point_code 是 hiragana katakana youon dakuon potential volitional imperative causative causative-passive counters-sound 之一的不要；把 meaning 开头的「[N1]」到「[N5]」去掉再去首尾空白得 bare：bare 为空的不要；bare 里有「一个非空格字符 + 一个半角空格 + 的」的不要（SQL 里 ' ' || bare GLOB '*[^ ] 的*'）；bare 以「的礼貌形」结尾的不要
  伪代码 查两条 SQL：先数满足条件的行数 total（total 为 0 直接返回 {"total": 0, "word": 空}）；再按 id 升序取第 (seed 对 total 取余) 行（LIMIT 1 OFFSET）。逗号隔开的编号在 SQL 里用 json_each('[' || :ids || ']') 展开成集合比较（IN / NOT IN），不要用 instr 在长字符串里找
  伪代码 返回 {"total": total, "word": 该行 {"id": id, "kanji": kanji, "kana": kana, "meaning": meaning, "point_code": point_code}}

公开 函数 列默写词 direction level? only_ids skip_ids?
  返回 {total, words}，words 是只在 only_ids 里、满足「挑默写词」同一套条件的单词对象 [{id, kanji, kana, meaning, point_code}]，按单词编号在 only_ids 里出现的先后排序（SQL 里 ORDER BY instr(',' || only_ids || ',', ',' || id || ',')）；only_ids 为空时返回 {total: 0, words: []}（不允许列全表）
  伪代码 给错词复习用（错词本很小）：条件与 挑默写词 的①②④⑤和「排除不是词义的词条」完全相同，没有 point_code 条件；与 挑默写词 共用同一套 WHERE 写法，不另写一套口径
  伪代码 一条 SQL 取出全部行，按上面的排序，返回 {"total": 行数, "words": 列表}

公开 函数 新建单词 kanji? kana meaning? point_code?
  返回 {ok, id}
  报错 400 假名不能为空
  报错 404 没有这个知识点
  报错 400 单词已存在
  伪代码 kana 为空，报错 400 假名不能为空
  伪代码 point_code 不为空时，调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
  伪代码 按 kanji + kana 查 vocab_word，已有则报错 400 单词已存在
  伪代码 往 vocab_word 插入一行 (kanji, kana, meaning, point_code)
  伪代码 返回 {"ok": 1, "id": 新行 id}

公开 函数 修改单词 word_id kanji kana meaning point_code
  返回 {ok, id}；四个字段整体覆盖，传空串就是置空（kana 不许空）
  报错 404 没有这个单词
  报错 400 假名不能为空
  报错 404 没有这个知识点
  报错 400 单词已存在
  伪代码 按 id=word_id 查 vocab_word，查不到报错 404 没有这个单词
  伪代码 kana 为空，报错 400 假名不能为空
  伪代码 按 kanji + kana 查 vocab_word，若存在且 id 不等于 word_id，报错 400 单词已存在
  伪代码 point_code 不为空时，调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
  伪代码 更新该行的 kanji、kana、meaning、point_code
  伪代码 返回 {"ok": 1, "id": word_id}

公开 函数 删除单词 word_id
  返回 {ok}
  报错 404 没有这个单词
  伪代码 按 id=word_id 查 vocab_word，查不到报错 404 没有这个单词
  伪代码 删除该行
  伪代码 返回 {"ok": 1}

公开 函数 导入单词 file_path
  返回 {ok, total, created, updated}
  报错 400 导入文件有错
  报错 400 知识点对不上
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「汉字|假名|中文意思|知识点编号」，用 | 分隔；后两项可以省略或为空（缺的尾部字段当空），汉字可以为空；少于 2 项或假名为空，报错 400 导入文件有错（整批不写）
  伪代码 对每个非空的知识点编号，调用 kg.取知识点 code=编号，取不到报错 400 知识点对不上（整批不写）
  伪代码 在一个事务里：逐行按 汉字+假名 查 vocab_word，没有则插入 (kanji, kana, meaning, point_code) 并 created+1，有则更新 meaning、point_code 并 updated+1
  伪代码 同一文件里重复的 汉字+假名，后一行覆盖前一行（按已存在算更新）
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

## 接口
GET /vocab/words -> 列单词
GET /vocab/word -> 取单词
GET /vocab/words/by-point -> 按知识点列单词
GET /vocab/orphans -> 列孤儿词
POST /vocab/word/create -> 新建单词 角色 teacher
POST /vocab/word/update -> 修改单词 角色 teacher
POST /vocab/word/delete -> 删除单词 角色 teacher
POST /vocab/import -> 导入单词 上传 file 类型 md,txt 上限 20MB 角色 teacher

## 用例
用例 列单词_全部
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kana=あ
  调用 列单词
  得 total=2

用例 列单词_关键字和知识点筛选
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kanji=飲む kana=のむ meaning=喝 point_code=P2
  调用 列单词 keyword=喝 point_code=P2
  得 total=1

用例 列单词_无匹配
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  调用 列单词 keyword=不存在的词
  得 total=0

用例 取单词_按编号
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  调用 取单词 word_id=1
  得 kanji=食べる kana=たべる meaning=吃 point_code=P1

用例 取单词_按汉字加假名
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  调用 取单词 kanji=食べる kana=たべる
  得 meaning=吃

用例 取单词_查不到
  调用 取单词 kanji=無 kana=ない
  得 为空

用例 取单词_缺参数
  调用 取单词
  报错 400

用例 按知识点列单词_正常
  先 数据 kg_point code=P1 title=一次函数
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kanji=飲む kana=のむ meaning=喝 point_code=P2
  调用 按知识点列单词 point_code=P1
  得 point_code=P1 total=1

用例 按知识点列单词_没有知识点
  调用 按知识点列单词 point_code=NOPE
  报错 404

用例 列孤儿词_正常
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kana=あ
  调用 列孤儿词
  得 total=1

用例 列孤儿词_没有孤儿
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  调用 列孤儿词
  得 total=0

用例 新建单词_正常
  先 数据 kg_point code=P1 title=一次函数
  调用 新建单词 kanji=食べる kana=たべる meaning=吃 point_code=P1
  得 ok=1
  库 vocab_word 共 1 行
  库 vocab_word 含 kanji=食べる kana=たべる meaning=吃 point_code=P1

用例 新建单词_仅假名
  调用 新建单词 kana=あ
  得 ok=1
  库 vocab_word 含 kana=あ

用例 新建单词_假名为空
  调用 新建单词 kanji=食べる kana=空
  报错 400
  库 vocab_word 共 0 行

用例 新建单词_重复
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  调用 新建单词 kanji=食べる kana=たべる
  报错 400
  库 vocab_word 共 1 行

用例 新建单词_知识点不存在
  调用 新建单词 kanji=食べる kana=たべる point_code=NOPE
  报错 404
  库 vocab_word 共 0 行

用例 修改单词_正常
  先 数据 kg_point code=P1 title=一次函数
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  调用 修改单词 word_id=1 kanji=食べる kana=たべる meaning=进食 point_code=空
  得 ok=1 id=1
  库 vocab_word 含 kana=たべる meaning=进食
  库 vocab_word 共 1 行

用例 修改单词_不存在
  调用 修改单词 word_id=99 kanji=空 kana=あ meaning=空 point_code=空
  报错 404

用例 修改单词_与其他词重复
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kanji=飲む kana=のむ meaning=喝 point_code=P1
  调用 修改单词 word_id=2 kanji=食べる kana=たべる meaning=喝 point_code=P1
  报错 400

用例 删除单词_正常
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  调用 删除单词 word_id=1
  得 ok=1
  库 vocab_word 共 0 行

用例 删除单词_不存在
  调用 删除单词 word_id=99
  报错 404

用例 导入单词_新增
  先 数据 kg_point code=P1 title=一次函数
  先 文件 words.md 内容=食べる|たべる|吃|P1
  调用 导入单词 file_path=words.md
  得 ok=1 total=1 created=1 updated=0
  库 vocab_word 共 1 行
  库 vocab_word 含 kanji=食べる kana=たべる meaning=吃 point_code=P1

用例 导入单词_重复是更新
  先 数据 kg_point code=P1 title=一次函数
  先 数据 vocab_word kanji=食べる kana=たべる meaning=旧意思
  先 文件 words.md 内容=食べる|たべる|吃|P1
  调用 导入单词 file_path=words.md
  得 ok=1 total=1 created=0 updated=1
  库 vocab_word 共 1 行
  库 vocab_word 含 kana=たべる meaning=吃 point_code=P1

用例 导入单词_仅假名行
  先 文件 words.md 内容=|あ|
  调用 导入单词 file_path=words.md
  得 ok=1 total=1 created=1 updated=0
  库 vocab_word 含 kana=あ

用例 导入单词_缺假名
  先 文件 words.md 内容=食べる||吃|P1
  调用 导入单词 file_path=words.md
  报错 400
  库 vocab_word 共 0 行

用例 导入单词_知识点对不上
  先 文件 words.md 内容=食べる|たべる|吃|NOPE
  调用 导入单词 file_path=words.md
  报错 400
  库 vocab_word 共 0 行

用例 挑默写词_按序号挑
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=[N5]老师 point_code=P1
  先 数据 vocab_word kanji=食べる kana=たべる meaning=[N4]吃 point_code=P1
  调用 挑默写词 direction=zh2jp seed=4
  得 total=3

用例 挑默写词_等级前缀
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=[N5]老师 point_code=P1
  先 数据 vocab_word kanji=食べる kana=たべる meaning=[N4]吃 point_code=P1
  调用 挑默写词 direction=zh2jp level=N5 seed=3
  得 total=2

用例 挑默写词_跳过编号
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  调用 挑默写词 direction=zh2jp skip_ids=1 seed=0
  得 total=1

用例 挑默写词_全部跳过
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  调用 挑默写词 direction=zh2jp only_ids=1,2 skip_ids=1,2 seed=0
  得 total=0

用例 挑默写词_限定编号
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  调用 挑默写词 direction=zh2jp only_ids=2 seed=7
  得 total=1

用例 挑默写词_按知识点
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P2
  调用 挑默写词 direction=zh2jp point_code=P2 seed=0
  得 total=1

用例 挑默写词_不要五十音和语法说明
  先 数据 vocab_word kana=あ meaning=あ point_code=hiragana
  先 数据 vocab_word kanji=行ける kana=いける meaning=行く的可能形 point_code=potential
  先 数据 vocab_word kanji=です kana=です meaning=です的礼貌形 point_code=P1
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=[N5]学校 point_code=P1
  先 数据 vocab_word kanji=空 kana=から meaning=[N5] point_code=P1
  调用 挑默写词 direction=zh2jp seed=0
  得 total=1

用例 挑默写词_看汉字写读音要有汉字
  先 数据 vocab_word kana=あした meaning=明天 point_code=P1
  先 数据 vocab_word kanji=ほん kana=ほん meaning=书 point_code=P1
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  调用 挑默写词 direction=kanji2kana seed=0
  得 total=1

用例 列默写词_只在给定编号里
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  先 数据 vocab_word kana=あ meaning=あ point_code=hiragana
  调用 列默写词 direction=zh2jp only_ids=2,3
  得 total=1

用例 列默写词_跳过编号
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校 point_code=P1
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 point_code=P1
  调用 列默写词 direction=zh2jp only_ids=1,2 skip_ids=1
  得 total=1
