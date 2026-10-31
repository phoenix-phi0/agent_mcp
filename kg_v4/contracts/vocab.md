模块 vocab
依赖 kg subject

## 表
表 vocab_word
  kanji 文本 汉字，可空（假名表条目没有汉字）
  kana 文本 假名，必填
  meaning 文本 中文意思，可空（假名表条目没有意思）
  point_code 文本 所属知识点编号，可空（空表示孤儿词）；不加外键
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 函数
公开 函数 列单词 keyword? point_code? learner? current_role? auth_mode? subject?
  返回 {total, words}，words 是 [{id, kanji, kana, meaning, point_code}]，按 id 升序
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 传参（K170）：keyword 是用户输入的搜索词，先去首尾空白再用（「 猫 」按「猫」搜）；查询参数（keyword、point_code、subject_id）装进对象用 查询表 传，不得按位置 keyword={…} 传（首尾有空白按位置传引擎直接报错）
  伪代码 查 vocab_word 中 subject_id 相等的行
  伪代码 keyword 不为空时，只留下 kanji、kana、meaning 任一字段包含 keyword 的行
  伪代码 point_code 不为空时，只留下 point_code 等于该值的行
  伪代码 按 id 升序，返回 {"total": 行数, "words": 列表}

公开 函数 取单词 word_id? kanji? kana? learner? current_role? auth_mode? subject?
  返回 {id, kanji, kana, meaning, point_code}；查不到返回空
  报错 400 word_id 和 kana 至少要给一个
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 传参（K170）：kanji、kana 先去首尾空白再用（库里存的是去空白后的值）；按 kanji + kana 查的参数装进对象用 查一行表 传，不得按位置 kanji={…} kana={…} 传
  伪代码 word_id 为空且 kana 为空，报错 400 word_id 和 kana 至少要给一个
  伪代码 word_id 不为空：按 id 和 subject_id 查 vocab_word 一行（属于别的科目的词当不存在）
  伪代码 word_id 为空：在本科目内按 kanji + kana 同时相等查一行（kanji 为空串时匹配汉字为空的词）
  伪代码 查不到则返回空
  伪代码 返回该行 {"id": id, "kanji": kanji, "kana": kana, "meaning": meaning, "point_code": point_code}

公开 函数 按知识点列单词 point_code learner? current_role? auth_mode? subject?
  返回 {point_code, total, words}，words 同「列单词」
  报错 404 没有这个知识点
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 调用 kg.取知识点 code=point_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个知识点
  伪代码 查 vocab_word 中 subject_id 相等且 point_code 相等的行，按 id 升序
  伪代码 返回 {"point_code": point_code, "total": 行数, "words": 列表}

公开 函数 列孤儿词 learner? current_role? auth_mode? subject?
  返回 {total, words}，words 同「列单词」；孤儿词指没有挂知识点（point_code 为空）的词
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 查 vocab_word 中 subject_id 相等且 point_code 为空的行，按 id 升序
  伪代码 返回 {"total": 行数, "words": 列表}

公开 函数 挑默写词 direction level? point_code? only_ids? skip_ids? seed learner? current_role? auth_mode? subject?
  返回 {total, word}：total 是满足下面全部条件的词数；word 是其中按排序的第 (seed 对 total 取余) 个（从 0 数）单词对象；排序：only_ids 为空按 id 升序；only_ids 不为空时按单词编号在 only_ids 里出现的先后（错词复习要保持错词本的顺序） {id, kanji, kana, meaning, point_code}，total 为 0 时 word 为空
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 这是给默写选词用的：筛选、数数、挑第几个都在一条 SQL 里做，不把整张表取回来再逐词循环（8105 个词时要在 1 秒内）。direction 为 zh2jp 或 kanji2kana，其他值当 zh2jp
  伪代码 条件（对 vocab_word 每行，全部满足才算）：⓪subject_id 等于本科目；①direction 为 zh2jp 要求 meaning 不为空；direction 为 kanji2kana 要求 kanji 不为空且不等于 kana；②level 不为空时要求 meaning 以「[level]」开头；③point_code 不为空时要求行的 point_code 等于它；④only_ids 不为空（逗号隔开的单词编号）时要求 id 在其中；⑤skip_ids 不为空（逗号隔开）时要求 id 不在其中
  伪代码 再排除不是词义的词条（和默写原来的口径一字不差）：point_code 是 hiragana katakana youon dakuon potential volitional imperative causative causative-passive counters-sound 之一的不要；把 meaning 开头的「[N1]」到「[N5]」去掉再去首尾空白得 bare：bare 为空的不要；bare 里有「一个非空格字符 + 一个半角空格 + 的」的不要（SQL 里 ' ' || bare GLOB '*[^ ] 的*'）；bare 以「的礼貌形」结尾的不要
  伪代码 查两条 SQL：先数满足条件的行数 total（total 为 0 直接返回 {"total": 0, "word": 空}）；再按返回里写的排序取第 (seed 对 total 取余) 行（LIMIT 1 OFFSET）：only_ids 为空按 id 升序；only_ids 不为空按单词编号在 only_ids 里出现的先后（SQL 里 ORDER BY instr(',' || :only_ids || ',', ',' || id || ',')，同 列默写词），再按 id 升序。逗号隔开的编号做集合判断（④ 在其中、⑤ 不在其中）时在 SQL 里用 json_each('[' || :ids || ']') 展开成集合比较（IN / NOT IN），集合判断不要用 instr 在长字符串里找；instr 只用于上面 only_ids 的先后排序
  伪代码 返回 {"total": total, "word": 该行 {"id": id, "kanji": kanji, "kana": kana, "meaning": meaning, "point_code": point_code}}

公开 函数 列默写词 direction level? only_ids skip_ids? learner? current_role? auth_mode? subject?
  返回 {total, words}，words 是只在 only_ids 里、满足「挑默写词」同一套条件的单词对象 [{id, kanji, kana, meaning, point_code}]，按单词编号在 only_ids 里出现的先后排序（SQL 里 ORDER BY instr(',' || only_ids || ',', ',' || id || ',')）；only_ids 为空时返回 {total: 0, words: []}（不允许列全表）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 给错词复习用（错词本很小）：条件与 挑默写词 的⓪①②④⑤（⓪ 是 subject_id 等于本科目）和「排除不是词义的词条」完全相同，没有 point_code 条件；与 挑默写词 共用同一套 WHERE 写法，不另写一套口径
  伪代码 一条 SQL 取出全部行，按上面的排序，返回 {"total": 行数, "words": 列表}

公开 函数 新建单词 kanji? kana meaning? point_code? learner? current_role? auth_mode? subject?
  返回 {ok, id}
  报错 400 假名不能为空
  报错 404 没有这个知识点
  报错 400 单词已存在
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 传参（K170）：kanji、kana、meaning、point_code 是老师在表单里填的原文，先各自去首尾空白（「猫 」存成「猫」），下面的判空、查重、插入都用去空白后的值；查重、插入、取新编号的参数一律装进对象用 查一值表 / 写库表 传，不得按位置 kanji={…} 传（首尾有空白按位置传引擎直接报错）
  伪代码 kana 为空（去空白后），报错 400 假名不能为空
  伪代码 point_code 不为空时，调用 kg.取知识点 code=point_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个知识点
  伪代码 在本科目内按 kanji + kana 查 vocab_word，已有则报错 400 单词已存在（别的科目有同样的词不算重复）
  伪代码 往 vocab_word 插入一行 (kanji, kana, meaning, point_code, subject_id)
  伪代码 返回 {"ok": 1, "id": 新行 id}

公开 函数 修改单词 word_id kanji kana meaning point_code learner? current_role? auth_mode? subject?
  返回 {ok, id}；四个字段整体覆盖，传空串就是置空（kana 不许空）
  报错 404 没有这个单词
  报错 400 假名不能为空
  报错 404 没有这个知识点
  报错 400 单词已存在
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 传参（K170）：kanji、kana、meaning、point_code 先各自去首尾空白，下面的判空、查重、更新都用去空白后的值；查重、更新的参数一律装进对象用 查一值表 / 写库表 传，不得按位置 kanji={…} 传
  伪代码 按 id=word_id 和 subject_id 查 vocab_word，查不到（包括属于别的科目）报错 404 没有这个单词
  伪代码 kana 为空（去空白后），报错 400 假名不能为空
  伪代码 在本科目内按 kanji + kana 查 vocab_word，若存在且 id 不等于 word_id，报错 400 单词已存在
  伪代码 point_code 不为空时，调用 kg.取知识点 code=point_code subject=subject_id，取不到（包括属于别的科目）报错 404 没有这个知识点
  伪代码 更新该行的 kanji、kana、meaning、point_code；更新语句的 SQL 条件同时写 id=word_id 和 subject_id=本科目（属于当前科目才改，纵深防御，不只靠上面的查询）
  伪代码 返回 {"ok": 1, "id": word_id}

公开 函数 删除单词 word_id learner? current_role? auth_mode? subject?
  返回 {ok}
  报错 404 没有这个单词
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 按 id=word_id 和 subject_id 查 vocab_word，查不到（包括属于别的科目）报错 404 没有这个单词
  伪代码 删除该行；删除语句的 SQL 条件同时写 id=word_id 和 subject_id=本科目（属于当前科目才删，纵深防御，不只靠上面的查询）
  伪代码 返回 {"ok": 1}

公开 函数 导入单词 file_path learner? current_role? auth_mode? subject?
  返回 {ok, total, created, updated}
  报错 400 导入文件有错
  报错 400 知识点对不上
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  报错 403 没有权限修改该科目
  伪代码 科目：调用本模块 本科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；learner、current_role、auth_mode、subject 都可选（路由层注入登录用户、角色、登录模式和地址参数 subject；别的模块调用时传 subject=已解析的科目编号），四个都不传得 1，行为同旧；下面所有查询和写入都只限这个 subject_id
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「汉字|假名|中文意思|知识点编号」，用 | 分隔；后两项可以省略或为空（缺的尾部字段当空），汉字可以为空；少于 2 项或假名为空，报错 400 导入文件有错（整批不写）
  伪代码 传参（K170）：按 | 拆开后各项（汉字、假名、中文意思、知识点编号）先各自去首尾空白再用（「猫 | ねこ | 小猫 | P1」等同「猫|ねこ|小猫|P1」；假名去空白后为空也算假名为空），核对知识点、查重、插入、更新都用去空白后的值；查重、插入、更新的参数一律装进对象用 查一值表 / 写库表 传，不得按位置 kanji={…} 传（正则切出来的组会带着 | 两边的空格，按位置传引擎直接报错，整批导入 500）
  伪代码 对每个非空的知识点编号，调用 kg.取知识点 code=编号 subject=subject_id，取不到（包括属于别的科目）报错 400 知识点对不上（整批不写）
  伪代码 在一个事务里：逐行在本科目内按 汉字+假名 查 vocab_word，没有则插入 (kanji, kana, meaning, point_code, subject_id) 并 created+1，有则更新 meaning、point_code 并 updated+1（更新语句的 SQL 条件同时写 id=该行 id 和 subject_id=本科目，纵深防御，同 修改单词/删除单词）
  伪代码 同一文件里重复的 汉字+假名，后一行覆盖前一行（按已存在算更新）
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（need 不传按 read；need=write 时登录模式下只有负责/协作教师通过，否则 解析科目 报 403 没有权限修改该科目、原样抛出；四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，原样抛出）

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

用例 导入单词_各项首尾有空格
  先 数据 kg_point code=P1 title=一次函数
  先 文件 words.md 内容=食べる | たべる | 吃 | P1
  调用 导入单词 file_path=words.md
  得 ok=1 total=1 created=1 updated=0
  库 vocab_word 共 1 行
  库 vocab_word 含 kanji=食べる kana=たべる meaning=吃 point_code=P1

用例 导入单词_带空格的行更新已有词
  先 数据 vocab_word kanji=猫 kana=ねこ meaning=旧意思
  先 文件 words.md 内容=猫 | ねこ | 小猫
  调用 导入单词 file_path=words.md
  得 ok=1 total=1 created=0 updated=1
  库 vocab_word 共 1 行
  库 vocab_word 含 kanji=猫 kana=ねこ meaning=小猫

用例 导入单词_假名只有空格算缺假名
  先 文件 words.md 内容=猫 |   | 小猫
  调用 导入单词 file_path=words.md
  报错 400
  库 vocab_word 共 0 行

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

用例 跨科目_列单词只看本科目
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kana=ゼロ meaning=零 subject_id=2
  调用 列单词 subject=2
  得 total=1

用例 跨科目_不传科目是日语
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kana=ゼロ meaning=零 subject_id=2
  调用 列单词
  得 total=1

用例 跨科目_取单词别的科目当不存在
  先 数据 vocab_word kana=ゼロ meaning=零 subject_id=2
  调用 取单词 word_id=1
  得 为空

用例 跨科目_取单词按汉字假名只看本科目
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃 point_code=P1
  先 数据 vocab_word kanji=食べる kana=たべる meaning=进食 subject_id=2
  调用 取单词 kanji=食べる kana=たべる subject=2
  得 meaning=进食

用例 跨科目_按知识点列单词别的科目的点404
  先 数据 kg_point code=P1 title=甲
  调用 按知识点列单词 point_code=P1 subject=2
  报错 404

用例 跨科目_列孤儿词只看本科目
  先 数据 vocab_word kana=あ
  先 数据 vocab_word kana=ゼロ subject_id=2
  调用 列孤儿词 subject=2
  得 total=1

用例 跨科目_新建单词落当前科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  调用 新建单词 kana=ゼロ meaning=零 point_code=math.a subject=2
  得 ok=1
  库 vocab_word 含 kana=ゼロ meaning=零 point_code=math.a subject_id=2

用例 跨科目_新建单词挂别的科目的点被拒
  先 数据 kg_point code=P1 title=甲
  调用 新建单词 kana=ゼロ point_code=P1 subject=2
  报错 404
  库 vocab_word 共 0 行

用例 跨科目_新建单词别的科目有同样的词不算重复
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃
  调用 新建单词 kanji=食べる kana=たべる meaning=进食 subject=2
  得 ok=1
  库 vocab_word 共 2 行

用例 跨科目_修改单词别的科目404
  先 数据 vocab_word kana=ゼロ meaning=零 subject_id=2
  调用 修改单词 word_id=1 kanji=空 kana=ゼロ meaning=空 point_code=空
  报错 404

用例 跨科目_删除单词别的科目404
  先 数据 vocab_word kana=ゼロ meaning=零 subject_id=2
  调用 删除单词 word_id=1
  报错 404
  库 vocab_word 共 1 行

用例 跨科目_导入单词落当前科目
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 文件 words.md 内容=空|ゼロ|零|math.a
  调用 导入单词 file_path=words.md subject=2
  得 ok=1 total=1 created=1 updated=0
  库 vocab_word 含 kana=ゼロ meaning=零 point_code=math.a subject_id=2

用例 跨科目_导入单词知识点在别的科目对不上
  先 数据 kg_point code=P1 title=甲
  先 文件 words.md 内容=食べる|たべる|吃|P1
  调用 导入单词 file_path=words.md subject=2
  报错 400
  库 vocab_word 共 0 行

用例 跨科目_导入单词只更新本科目的同词
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃
  先 文件 words.md 内容=食べる|たべる|进食
  调用 导入单词 file_path=words.md subject=2
  得 ok=1 total=1 created=1 updated=0
  库 vocab_word 共 2 行

用例 跨科目_挑默写词只数本科目
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 subject_id=2
  先 数据 vocab_word kanji=医者 kana=いしゃ meaning=医生 subject_id=2
  调用 挑默写词 direction=zh2jp seed=0 subject=2
  得 total=2

用例 跨科目_列默写词只在本科目里
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 subject_id=2
  调用 列默写词 direction=zh2jp only_ids=1,2 subject=2
  得 total=1

用例 跨科目_need_新建单词公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  调用 新建单词 kana=ゼロ meaning=零 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 vocab_word 共 0 行

用例 跨科目_need_新建单词协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  调用 新建单词 kana=ゼロ meaning=零 learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1
  库 vocab_word 含 kana=ゼロ meaning=零 subject_id=2

用例 跨科目_need_修改单词公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 subject_id=2
  调用 修改单词 word_id=1 kanji=先生 kana=せんせい meaning=教师 point_code=空 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 vocab_word 含 kana=せんせい meaning=老师 subject_id=2

用例 跨科目_need_删除单词公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 subject_id=2
  调用 删除单词 word_id=1 learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 vocab_word 共 1 行

用例 跨科目_need_删除单词协作教师可写
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_teacher subject_id=2 teacher=t2 role=editor created_at=2026-01-01
  先 数据 vocab_word kanji=先生 kana=せんせい meaning=老师 subject_id=2
  调用 删除单词 word_id=1 learner=t2 current_role=teacher auth_mode=on subject=2
  得 ok=1
  库 vocab_word 共 0 行

用例 跨科目_need_导入单词公共科目非负责教师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 words.md 内容=空|ゼロ|零
  调用 导入单词 file_path=words.md learner=t2 current_role=teacher auth_mode=on subject=2
  报错 403
  库 vocab_word 共 0 行

用例 跨科目_修改单词别的科目的词404且不改
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校
  调用 修改单词 word_id=1 kanji=学校 kana=がっこう meaning=改了 point_code=空 subject=2
  报错 404
  库 vocab_word 含 kana=がっこう meaning=学校 subject_id=1

用例 跨科目_删除单词别的科目的词404且不删
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 vocab_word kanji=学校 kana=がっこう meaning=学校
  调用 删除单词 word_id=1 subject=2
  报错 404
  库 vocab_word 共 1 行

用例 跨科目_修改单词不影响别的科目的同词
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃
  先 数据 vocab_word kanji=食べる kana=たべる meaning=进食 subject_id=2
  调用 修改单词 word_id=1 kanji=食べる kana=たべる meaning=改了 point_code=空
  得 ok=1 id=1
  库 vocab_word 含 kana=たべる meaning=改了 subject_id=1
  库 vocab_word 含 kana=たべる meaning=进食 subject_id=2
  库 vocab_word 共 2 行

用例 跨科目_修改2号科目的词不撞1号的同词
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃
  先 数据 vocab_word kanji=飲む kana=のむ meaning=喝 subject_id=2
  调用 修改单词 word_id=2 kanji=食べる kana=たべる meaning=喝 point_code=空 subject=2
  得 ok=1 id=2
  库 vocab_word 含 kanji=食べる meaning=吃 subject_id=1
  库 vocab_word 含 kanji=食べる meaning=喝 subject_id=2

用例 跨科目_修改单词挂别的科目的点被拒且不改
  先 数据 kg_point code=P1 title=甲
  先 数据 vocab_word kanji=飲む kana=のむ meaning=喝 subject_id=2
  调用 修改单词 word_id=1 kanji=飲む kana=のむ meaning=改了 point_code=P1 subject=2
  报错 404
  库 vocab_word 含 kana=のむ meaning=喝 subject_id=2

用例 跨科目_修改单词挂本科目的点
  先 数据 kg_point code=math.a title=代数 subject_id=2
  先 数据 vocab_word kanji=飲む kana=のむ meaning=喝 subject_id=2
  调用 修改单词 word_id=1 kanji=飲む kana=のむ meaning=喝 point_code=math.a subject=2
  得 ok=1 id=1
  库 vocab_word 含 kana=のむ point_code=math.a subject_id=2

用例 跨科目_导入单词更新不碰别的科目的同词
  先 数据 vocab_word kanji=食べる kana=たべる meaning=吃
  先 数据 vocab_word kanji=食べる kana=たべる meaning=进食 subject_id=2
  先 文件 words.md 内容=食べる|たべる|新义
  调用 导入单词 file_path=words.md subject=2
  得 ok=1 total=1 created=0 updated=1
  库 vocab_word 共 2 行
  库 vocab_word 含 kana=たべる meaning=吃 subject_id=1
  库 vocab_word 含 kana=たべる meaning=新义 subject_id=2
