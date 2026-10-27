业务 vocab
  依赖 kg subject
  用包 common db text doc

  公开 函数 列单词 keyword? point_code? learner? current_role? auth_mode? subject?
    # 返回 {total, words}，words 是 [{id, kanji, kana, meaning, point_code}]，按 id 升序
    # 查 vocab_word 全部行
    # keyword 不为空时，只留下 kanji、kana、meaning 任一字段包含 keyword 的行
    # point_code 不为空时，只留下 point_code 等于该值的行
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 rows = 查询 app.db vocab_list keyword={keyword} point_code={point_code} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    设 out.total = {n}
    设 out.words = {rows}
    返回 {out}
  结束

  公开 函数 取单词 word_id? kanji? kana? learner? current_role? auth_mode? subject?
    # 返回 {id, kanji, kana, meaning, point_code}；查不到返回空
    # 报错 400 word_id 和 kana 至少要给一个
    # word_id 为空且 kana 为空，报错 400 word_id 和 kana 至少要给一个
    # word_id 不为空：按 id 查 vocab_word 一行
    # word_id 为空：按 kanji + kana 同时相等查一行（kanji 为空串时匹配汉字为空的词）
    # 查不到则返回空
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    如果 {word_id} 为空 且 {kana} 为空
      报错 400 word_id 和 kana 至少要给一个
    结束
    如果 {word_id} 不为空
      设 w = 查一行 app.db vocab_by_id word_id={word_id} subject_id={sb.subject_id}
    否则
      设 w = 查一行 app.db vocab_by_key kanji={kanji} kana={kana} subject_id={sb.subject_id}
    结束
    返回 {w}
  结束

  公开 函数 按知识点列单词 point_code learner? current_role? auth_mode? subject?
    # 返回 {point_code, total, words}，words 同「列单词」
    # 报错 404 没有这个知识点
    # 调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
    # 查 vocab_word 中 point_code 相等的行，按 id 升序
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 p = 调用 kg.取知识点 code={point_code} subject={sb.subject_id}
    如果 {p} 为空
      报错 404 没有这个知识点
    结束
    设 rows = 查询 app.db vocab_by_point point_code={point_code} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    设 out.point_code = {point_code}
    设 out.total = {n}
    设 out.words = {rows}
    返回 {out}
  结束

  公开 函数 列孤儿词 learner? current_role? auth_mode? subject?
    # 返回 {total, words}，words 同「列单词」；孤儿词指没有挂知识点（point_code 为空）的词
    # 查 vocab_word 中 point_code 为空的行，按 id 升序
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 rows = 查询 app.db vocab_orphans subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    设 out.total = {n}
    设 out.words = {rows}
    返回 {out}
  结束

  公开 函数 挑默写词 direction level? point_code? only_ids? skip_ids? seed learner? current_role? auth_mode? subject?
    # 筛选、数数、挑第几个都在 SQL 里做，不遍历词表
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 dir = zh2jp
    如果 {direction} 等于 kanji2kana
      设 dir = kanji2kana
    结束
    设 total = 查一值 app.db vocab_dict_count direction={dir} level={level} point_code={point_code} only_ids={only_ids} skip_ids={skip_ids} subject_id={sb.subject_id}
    如果 {total} 等于 0
      返回 {"total": 0, "word": ""}
    结束
    设 off = 计算 {seed 或 0} % {total}
    设 w = 查一行 app.db vocab_dict_pick direction={dir} level={level} point_code={point_code} only_ids={only_ids} skip_ids={skip_ids} offset={off} subject_id={sb.subject_id}
    返回 {"total": {total}, "word": {w}}
  结束

  公开 函数 列默写词 direction level? only_ids skip_ids? learner? current_role? auth_mode? subject?
    # 给错词复习用；only_ids 为空不允许列全表
    设 dir = zh2jp
    如果 {direction} 等于 kanji2kana
      设 dir = kanji2kana
    结束
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 ids = 替换 {only_ids} \s
    如果 {ids} 为空
      返回 {"total": 0, "words": []}
    结束
    设 rows = 查询 app.db vocab_dict_list direction={dir} level={level} only_ids={ids} skip_ids={skip_ids} subject_id={sb.subject_id}
    设 n = 列表长度 {rows}
    设 out.total = {n}
    设 out.words = {rows}
    返回 {out}
  结束

  公开 函数 新建单词 kanji? kana meaning? point_code? learner? current_role? auth_mode? subject?
    # 返回 {ok, id}
    # 报错 400 假名不能为空
    # 报错 404 没有这个知识点
    # 报错 400 单词已存在
    # kana 为空，报错 400 假名不能为空
    # point_code 不为空时，调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
    # 按 kanji + kana 查 vocab_word，已有则报错 400 单词已存在
    # 往 vocab_word 插入一行 (kanji, kana, meaning, point_code)
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    如果 {kana} 为空
      报错 400 假名不能为空
    结束
    如果 {point_code} 不为空
      设 p = 调用 kg.取知识点 code={point_code} subject={sb.subject_id}
      如果 {p} 为空
        报错 404 没有这个知识点
      结束
    结束
    设 ex = 查一值 app.db vocab_id_by_key kanji={kanji} kana={kana} subject_id={sb.subject_id}
    如果 {ex} 不为空
      报错 400 单词已存在
    结束
    事务 app.db
      设 n = 写库 app.db vocab_insert kanji={kanji} kana={kana} meaning={meaning} point_code={point_code} subject_id={sb.subject_id}
    结束
    设 nid = 查一值 app.db vocab_id_by_key kanji={kanji} kana={kana} subject_id={sb.subject_id}
    返回 {"ok": 1, "id": {nid}}
  结束

  公开 函数 修改单词 word_id kanji kana meaning point_code learner? current_role? auth_mode? subject?
    # 返回 {ok, id}；四个字段整体覆盖，传空串就是置空（kana 不许空）
    # 报错 404 没有这个单词
    # 报错 400 假名不能为空
    # 报错 404 没有这个知识点
    # 报错 400 单词已存在
    # 按 id=word_id 查 vocab_word，查不到报错 404 没有这个单词
    # kana 为空，报错 400 假名不能为空
    # point_code 不为空时，调用 kg.取知识点 code=point_code，取不到报错 404 没有这个知识点
    # 按 kanji + kana 查 vocab_word，若存在且 id 不等于 word_id，报错 400 单词已存在
    # 更新该行的 kanji、kana、meaning、point_code
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 w = 查一行 app.db vocab_by_id word_id={word_id} subject_id={sb.subject_id}
    如果 {w} 为空
      报错 404 没有这个单词
    结束
    如果 {kana} 为空
      报错 400 假名不能为空
    结束
    设 dup = 查一值 app.db vocab_dup_other kanji={kanji} kana={kana} word_id={word_id} subject_id={sb.subject_id}
    如果 {dup} 不为空
      报错 400 单词已存在
    结束
    如果 {point_code} 不为空
      设 p = 调用 kg.取知识点 code={point_code} subject={sb.subject_id}
      如果 {p} 为空
        报错 404 没有这个知识点
      结束
    结束
    事务 app.db
      设 n = 写库 app.db vocab_update_full word_id={word_id} kanji={kanji} kana={kana} meaning={meaning} point_code={point_code}
    结束
    返回 {"ok": 1, "id": {word_id}}
  结束

  公开 函数 删除单词 word_id learner? current_role? auth_mode? subject?
    # 返回 {ok}
    # 报错 404 没有这个单词
    # 按 id=word_id 查 vocab_word，查不到报错 404 没有这个单词
    # 删除该行
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 w = 查一行 app.db vocab_by_id word_id={word_id} subject_id={sb.subject_id}
    如果 {w} 为空
      报错 404 没有这个单词
    结束
    事务 app.db
      设 n = 写库 app.db vocab_delete word_id={word_id}
    结束
    返回 {"ok": 1}
  结束

  公开 函数 导入单词 file_path learner? current_role? auth_mode? subject?
    # 返回 {ok, total, created, updated}
    # 报错 400 导入文件有错
    # 报错 400 知识点对不上
    # 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以
    # 每行格式「汉字|假名|中文意思|知识点编号」，用 | 分隔；后两项可以省略或为空（缺的尾部字段当空），汉字可以为空；少于 2 项或假名为空，报错 400 导入文件有错（整批不写）
    # 对每个非空的知识点编号，调用 kg.取知识点 code=编号，取不到报错 400 知识点对不上（整批不写）
    # 在一个事务里：逐行按 汉字+假名 查 vocab_word，没有则插入 (kanji, kana, meaning, point_code) 并 created+1，有则更新 meaning、point_code 并 updated+1
    # 同一文件里重复的 汉字+假名，后一行覆盖前一行（按已存在算更新）
    设 sb = 调用 本科目 learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或} subject={subject 或}
    设 d = 读文档 {file_path}
    如果 {d.error} 不为空
      报错 400 导入文件有错
    结束
    设 raws = 按正则切分 {d.text} \r?\n
    设 pat = ^(?P<kanji>[^|]*)\|(?P<kana>[^|]*)\|(?P<meaning>[^|]*)\|(?P<code>[^|]*)
    设 valid = 解析JSON []
    遍历 raw 于 {raws}
      设 line = 替换 {raw} ^\s+|\s+$
      如果 {line} 为空
        继续
      结束
      设 cm = 匹配 {line} ^#
      如果 {cm.matched} 等于 是
        继续
      结束
      设 full = {line}|||
      设 m = 匹配 {full} {pat}
      如果 {m.matched} 不等于 是
        报错 400 导入文件有错
      结束
      如果 {m.named.kana} 为空
        报错 400 导入文件有错
      结束
      如果 {m.named.code} 不为空
        设 p = 调用 kg.取知识点 code={m.named.code} subject={sb.subject_id}
        如果 {p} 为空
          报错 400 知识点对不上
        结束
      结束
      设 valid = 列表加项 {valid} {full}
    结束
    设 total = 0
    设 created = 0
    设 updated = 0
    事务 app.db
      遍历 full 于 {valid}
        设 m = 匹配 {full} {pat}
        设 ex = 查一值 app.db vocab_id_by_key kanji={m.named.kanji} kana={m.named.kana} subject_id={sb.subject_id}
        如果 {ex} 为空
          设 n = 写库 app.db vocab_insert kanji={m.named.kanji} kana={m.named.kana} meaning={m.named.meaning} point_code={m.named.code} subject_id={sb.subject_id}
          设 created = 计算 {created} + 1
        否则
          设 n = 写库 app.db vocab_update_meaning word_id={ex} meaning={m.named.meaning} point_code={m.named.code}
          设 updated = 计算 {updated} + 1
        结束
        设 total = 计算 {total} + 1
      结束
    结束
    返回 {"ok": 1, "total": {total}, "created": {created}, "updated": {updated}}
  结束

  函数 本科目 learner current_role auth_mode subject
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject}
    返回 {"subject_id": {r.subject_id}}
  结束

结束
