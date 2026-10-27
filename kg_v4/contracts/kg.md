模块 kg
依赖 无

## 表
表 kg_point
  code 文本 知识点编号，唯一
  title 文本 中文名
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 kg_edge
  pre_code 文本 前置知识点编号（学后续之前要先会它）
  point_code 文本 后续知识点编号
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 kg_contrast
  a_code 文本 对照一端编号（知识点或表达方式条目，不加外键）；两端按字符串大小规范化，小的放 a_code
  b_code 文本 对照另一端编号
  subject_id 整数 所属科目，默认 1（1 是日语语法）
表 kg_item
  code 文本 条目编号，唯一
  name 文本 条目名称
  point_code 文本 所属知识点（结构点）编号
  after_form 文本 接在哪个形式后，可空
  prev_code 文本 前一个条目编号（只用来排学习顺序），可空
  subject_id 整数 所属科目，默认 1（1 是日语语法）

## 函数
公开 函数 取知识点 code
  返回 {id, code, title}；查不到返回空
  伪代码 按 code 查 kg_point 一行
  伪代码 查不到则返回空
  伪代码 返回 {"id": id, "code": code, "title": title}

公开 函数 列知识点
  返回 {total, points}，points 是 [{code, title}]，按 id 升序
  伪代码 查 kg_point 全部行，按 id 升序
  伪代码 返回 {"total": 行数, "points": 列表}

公开 函数 列前置 code
  返回 {code, total, points}，points 是该节点直接前置 [{code, title}]
  报错 404 没有这个知识点
  伪代码 按 code 查 kg_point，查不到报错 404 没有这个知识点
  伪代码 查 kg_edge 中 point_code=code 的行，取每行 pre_code，连 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列后续 code
  返回 {code, total, points}，points 是该节点直接后续 [{code, title}]
  报错 404 没有这个知识点
  伪代码 按 code 查 kg_point，查不到报错 404 没有这个知识点
  伪代码 查 kg_edge 中 pre_code=code 的行，取每行 point_code，连 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列祖先 code
  返回 {code, total, points}，points 是该节点全部祖先（直接和间接前置，去重，不含自己）[{code, title}]
  报错 404 没有这个知识点
  伪代码 按 code 查 kg_point，查不到报错 404 没有这个知识点
  伪代码 从 code 出发，沿 kg_edge 的 point_code→pre_code 方向逐层向上取前置，已访问过的不再入队，直到没有新节点
  伪代码 把访问到的节点（不含 code 自己）连 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列后代 code
  返回 {code, total, points}，points 是该节点全部后代（直接和间接后续，去重，不含自己）[{code, title}]
  报错 404 没有这个知识点
  伪代码 按 code 查 kg_point，查不到报错 404 没有这个知识点
  伪代码 从 code 出发，沿 kg_edge 的 pre_code→point_code 方向逐层向下取后续，已访问过的不再入队，直到没有新节点
  伪代码 把访问到的节点（不含 code 自己）连 kg_point 取 title，按 id 升序
  伪代码 返回 {"code": code, "total": 个数, "points": 列表}

公开 函数 列根节点
  返回 {total, points}，points 是没有任何前置的知识点 [{code, title}]
  伪代码 取 kg_point 中 code 不出现在 kg_edge.point_code 里的行，按 id 升序
  伪代码 返回 {"total": 个数, "points": 列表}

公开 函数 列分层
  返回 {layer_count, layers}，layers 是 [{depth, points}]，points 是 [{code, title}]；节点的 depth = 0（无前置）或 其所有直接前置 depth 的最大值 + 1（按依赖深度分层）
  伪代码 取全部 kg_point 和 kg_edge
  伪代码 无前置的节点 depth=0；其余节点 depth = 其全部前置 depth 最大值 + 1（图无环，按拓扑顺序算）
  伪代码 按 depth 升序分组，组内按 id 升序
  伪代码 返回 {"layer_count": 层数, "layers": 列表}；没有知识点时 layer_count=0，layers 为空列表

公开 函数 加前置边 pre_code point_code
  返回 {ok, created}，created 为 1 表示新加，0 表示这条边已存在
  报错 400 编号不能为空
  报错 400 不能以自己为前置
  报错 404 没有这个知识点
  报错 400 这条边会形成环
  伪代码 pre_code 或 point_code 为空，报错 400 编号不能为空
  伪代码 pre_code 等于 point_code，报错 400 不能以自己为前置
  伪代码 pre_code 或 point_code 不在 kg_point，报错 404 没有这个知识点
  伪代码 kg_edge 已有 (pre_code, point_code)，返回 {"ok": 1, "created": 0}
  伪代码 环检查：从 point_code 沿 kg_edge 向下取全部后代，若包含 pre_code，报错 400 这条边会形成环
  伪代码 往 kg_edge 插入一行 (pre_code, point_code)
  伪代码 返回 {"ok": 1, "created": 1}

公开 函数 导出图
  返回 {point_count, edge_count, contrast_count, points, edges, contrasts}；points 是 [{code, title}]，edges 是 [{pre_code, point_code}]，contrasts 是 [{a_code, b_code}]
  伪代码 分别查 kg_point、kg_edge、kg_contrast 全部行，按 id 升序
  伪代码 返回三个列表和各自行数

公开 函数 取条目 code
  返回 {id, code, name, point_code, after_form, prev_code}；查不到返回空
  伪代码 按 code 查 kg_item 一行
  伪代码 查不到则返回空
  伪代码 返回该行各字段

公开 函数 列条目
  返回 {total, items}，items 是 [{code, name, point_code, after_form, prev_code}]，按 id 升序
  伪代码 查 kg_item 全部行，按 id 升序
  伪代码 返回 {"total": 行数, "items": 列表}

公开 函数 按知识点列条目 point_code
  返回 {point_code, total, items}，items 同「列条目」
  报错 404 没有这个知识点
  伪代码 按 point_code 查 kg_point，查不到报错 404 没有这个知识点
  伪代码 查 kg_item 中 point_code 相等的行，按 id 升序
  伪代码 返回 {"point_code": point_code, "total": 行数, "items": 列表}

公开 函数 列对照 code?
  返回 {total, contrasts}，contrasts 是 [{a_code, b_code}]
  伪代码 code 为空：查 kg_contrast 全部行，按 id 升序
  伪代码 code 不为空：只取 a_code=code 或 b_code=code 的行（对照无向，任一端匹配都算）
  伪代码 返回 {"total": 行数, "contrasts": 列表}

公开 函数 核对条目存在 codes
  返回 {ok, missing_count, missing}；codes 是用英文逗号隔开的编号，每个编号在 kg_item 或 kg_point 里有就算存在；ok 为 1 表示全部存在；missing 是不存在的编号用英文逗号连起来
  报错 400 codes 不能为空
  伪代码 codes 为空，报错 400 codes 不能为空
  伪代码 按英文逗号拆开，去掉空白项
  伪代码 逐个编号查 kg_item 和 kg_point，两张表都没有的记入 missing
  伪代码 返回 {"ok": missing 为空则 1 否则 0, "missing_count": 个数, "missing": 逗号连接}

公开 函数 导入知识点 file_path
  返回 {ok, total, created, updated}
  报错 400 导入文件有错
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「编号|中文名」，用 | 分隔；编号或中文名为空、或没有 | 就报错 400 导入文件有错（整批不写）
  伪代码 在一个事务里：逐行按 code 查 kg_point，没有则插入 (code, title) 并 created+1，有则更新 title 并 updated+1
  伪代码 同一文件里重复的编号后一行覆盖前一行（按已存在算更新）
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

公开 函数 导入条目 file_path
  返回 {ok, total, created, updated}
  报错 400 导入文件有错
  报错 400 条目对不上知识点
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「编号|名称|知识点编号|接在哪个形式后|前一个条目编号」，用 | 分隔；后三项可以省略或为空（缺的尾部字段当空）；编号、名称、知识点编号任一为空，报错 400 导入文件有错
  伪代码 在一个事务里：逐行按 code 查 kg_item，没有则插入并 created+1，有则更新 name、point_code、after_form、prev_code 并 updated+1
  伪代码 全部行写完后校验：每个条目的 point_code 必须在 kg_point，前一个条目编号不为空时必须在 kg_item，否则报错 400 条目对不上知识点，事务回滚整批不写
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

公开 函数 导入对照 file_path
  返回 {ok, total, created, updated}，重复的对照（不分顺序）算 updated，不新增行
  报错 400 导入文件有错
  伪代码 用 doc 包「读文档」读 file_path 取文本，按行拆开；空行和以 # 开头的行忽略
  伪代码 每行格式「编号A|编号B」，用 | 分隔；任一为空、或两端相同，报错 400 导入文件有错（整批不写）；对照两端可以是知识点也可以是条目，不核对是否存在，不加外键，不做环检查
  伪代码 在一个事务里：每行把两端按字符串大小规范化（小的为 a_code），按 (a_code, b_code) 查 kg_contrast，没有则插入并 created+1，有则 updated+1
  伪代码 返回 {"ok": 1, "total": 有效行数, "created": created, "updated": updated}

## 接口
GET /kg/point -> 取知识点
GET /kg/points -> 列知识点
GET /kg/prerequisites -> 列前置
GET /kg/successors -> 列后续
GET /kg/ancestors -> 列祖先
GET /kg/descendants -> 列后代
GET /kg/roots -> 列根节点
GET /kg/layers -> 列分层
POST /kg/edge/add -> 加前置边 角色 teacher
GET /kg/export -> 导出图
GET /kg/item -> 取条目
GET /kg/items -> 列条目
GET /kg/items/by-point -> 按知识点列条目
GET /kg/contrasts -> 列对照
POST /kg/import/points -> 导入知识点 上传 file 类型 md,txt 上限 20MB 角色 teacher
POST /kg/import/items -> 导入条目 上传 file 类型 md,txt 上限 20MB 角色 teacher
POST /kg/import/contrasts -> 导入对照 上传 file 类型 md,txt 上限 20MB 角色 teacher

## 用例
用例 取知识点_存在
  先 数据 kg_point code=P1 title=一次函数
  调用 取知识点 code=P1
  得 code=P1 title=一次函数

用例 取知识点_不存在
  调用 取知识点 code=NOPE
  得 为空

用例 列知识点_两个
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=P2 title=乙
  调用 列知识点
  得 total=2

用例 列知识点_空库
  调用 列知识点
  得 total=0

用例 列前置_直接前置
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 列前置 code=C
  得 code=C total=1

用例 列前置_没有这个点
  调用 列前置 code=NOPE
  报错 404

用例 列后续_直接后续
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=A point_code=C
  调用 列后续 code=A
  得 code=A total=2

用例 列后续_没有这个点
  调用 列后续 code=NOPE
  报错 404

用例 列祖先_间接也算
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 列祖先 code=C
  得 code=C total=2

用例 列祖先_根节点没有祖先
  先 数据 kg_point code=A title=甲
  调用 列祖先 code=A
  得 total=0

用例 列祖先_没有这个点
  调用 列祖先 code=NOPE
  报错 404

用例 列后代_间接也算
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 列后代 code=A
  得 code=A total=2

用例 列后代_没有这个点
  调用 列后代 code=NOPE
  报错 404

用例 列根节点_只有无前置的
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=D title=丁
  先 数据 kg_edge pre_code=A point_code=B
  调用 列根节点
  得 total=2

用例 列根节点_空库
  调用 列根节点
  得 total=0

用例 列分层_最长路径定深度
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  先 数据 kg_edge pre_code=A point_code=C
  调用 列分层
  得 layer_count=3

用例 列分层_空库
  调用 列分层
  得 layer_count=0

用例 加前置边_正常
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  调用 加前置边 pre_code=A point_code=B
  得 ok=1 created=1
  库 kg_edge 共 1 行
  库 kg_edge 含 pre_code=A point_code=B

用例 加前置边_重复不新增
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  调用 加前置边 pre_code=A point_code=B
  得 ok=1 created=0
  库 kg_edge 共 1 行

用例 加前置边_成环被拒
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_point code=C title=丙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_edge pre_code=B point_code=C
  调用 加前置边 pre_code=C point_code=A
  报错 400
  库 kg_edge 共 2 行

用例 加前置边_自环被拒
  先 数据 kg_point code=A title=甲
  调用 加前置边 pre_code=A point_code=A
  报错 400
  库 kg_edge 共 0 行

用例 加前置边_没有这个点
  先 数据 kg_point code=A title=甲
  调用 加前置边 pre_code=A point_code=NOPE
  报错 404
  库 kg_edge 共 0 行

用例 导出图_全部
  先 数据 kg_point code=A title=甲
  先 数据 kg_point code=B title=乙
  先 数据 kg_edge pre_code=A point_code=B
  先 数据 kg_contrast a_code=A b_code=B
  调用 导出图
  得 point_count=2 edge_count=1 contrast_count=1

用例 导出图_空库
  调用 导出图
  得 point_count=0 edge_count=0 contrast_count=0

用例 取条目_存在
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 取条目 code=I1
  得 code=I1 name=条目一 point_code=P1

用例 取条目_不存在
  调用 取条目 code=NOPE
  得 为空

用例 列条目_两个
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P1 prev_code=I1
  调用 列条目
  得 total=2

用例 列条目_空库
  调用 列条目
  得 total=0

用例 按知识点列条目_正常
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_point code=P2 title=乙
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  先 数据 kg_item code=I2 name=条目二 point_code=P2
  调用 按知识点列条目 point_code=P1
  得 point_code=P1 total=1

用例 按知识点列条目_没有这个点
  调用 按知识点列条目 point_code=NOPE
  报错 404

用例 列对照_全部
  先 数据 kg_contrast a_code=A b_code=B
  先 数据 kg_contrast a_code=C b_code=D
  调用 列对照
  得 total=2

用例 列对照_按一端筛选
  先 数据 kg_contrast a_code=A b_code=B
  先 数据 kg_contrast a_code=C b_code=D
  调用 列对照 code=B
  得 total=1

用例 核对条目存在_都在
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 核对条目存在 codes=I1,P1
  得 ok=1 missing_count=0

用例 核对条目存在_有缺
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=条目一 point_code=P1
  调用 核对条目存在 codes=I1,ZZ
  得 ok=0 missing_count=1 missing=ZZ

用例 核对条目存在_空
  调用 核对条目存在 codes=空
  报错 400

用例 导入知识点_新建
  先 文件 kg_in/p.txt 内容=P1|一次函数
  调用 导入知识点 file_path=kg_in/p.txt
  得 ok=1 total=1 created=1 updated=0
  库 kg_point 含 code=P1 title=一次函数

用例 导入知识点_重复是更新
  先 数据 kg_point code=P1 title=旧名
  先 文件 kg_in/p.txt 内容=P1|新名
  调用 导入知识点 file_path=kg_in/p.txt
  得 ok=1 total=1 created=0 updated=1
  库 kg_point 共 1 行
  库 kg_point 含 code=P1 title=新名

用例 导入知识点_坏行回滚
  先 文件 kg_in/p.txt 内容=只有一项没有分隔符
  调用 导入知识点 file_path=kg_in/p.txt
  报错 400
  库 kg_point 共 0 行

用例 导入条目_新建
  先 数据 kg_point code=P1 title=甲
  先 文件 kg_in/i.txt 内容=I1|条目一|P1
  调用 导入条目 file_path=kg_in/i.txt
  得 ok=1 total=1 created=1 updated=0
  库 kg_item 含 code=I1 name=条目一 point_code=P1

用例 导入条目_重复是更新
  先 数据 kg_point code=P1 title=甲
  先 数据 kg_item code=I1 name=旧名 point_code=P1
  先 文件 kg_in/i.txt 内容=I1|新名|P1
  调用 导入条目 file_path=kg_in/i.txt
  得 ok=1 created=0 updated=1
  库 kg_item 共 1 行
  库 kg_item 含 code=I1 name=新名

用例 导入条目_知识点对不上
  先 文件 kg_in/i.txt 内容=I1|条目一|NOPE
  调用 导入条目 file_path=kg_in/i.txt
  报错 400
  库 kg_item 共 0 行

用例 导入条目_缺字段
  先 文件 kg_in/i.txt 内容=I1
  调用 导入条目 file_path=kg_in/i.txt
  报错 400
  库 kg_item 共 0 行

用例 导入对照_新建
  先 文件 kg_in/c.txt 内容=B|A
  调用 导入对照 file_path=kg_in/c.txt
  得 ok=1 total=1 created=1 updated=0
  库 kg_contrast 共 1 行
  库 kg_contrast 含 a_code=A b_code=B

用例 导入对照_反向重复不新增
  先 数据 kg_contrast a_code=A b_code=B
  先 文件 kg_in/c.txt 内容=B|A
  调用 导入对照 file_path=kg_in/c.txt
  得 ok=1 created=0 updated=1
  库 kg_contrast 共 1 行

用例 导入对照_两端相同
  先 文件 kg_in/c.txt 内容=A|A
  调用 导入对照 file_path=kg_in/c.txt
  报错 400
  库 kg_contrast 共 0 行
