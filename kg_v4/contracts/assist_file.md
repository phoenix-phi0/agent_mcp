模块 assist_file
依赖 subject

# 教师助手的附件（M4-P2，design §4，D5–D8）。助手页底栏选文件，经 teacher_assist 的 挂附件页面（接口 /teacher_assist/attach，「上传 assist_file 上限 10MB」，路由存好文件后把路径交过来）调本模块 存附件；挂上的附件「接下来几轮都带上」（attached=1，问答和依据附件出题都用它），直到老师点「移除附件」、挂上别的附件或传了新文件。本模块只管附件的存取，不调模型、不写对话；问答的资料段、依据附件出题都由 teacher_assist 拼（取附件文本 的 text、stats 交给 答一轮 / assist_draft.生成草稿 的 ref_text）。
#
# 类型（D6、D7）：只收 txt、md、csv、pdf、docx。xlsx / xls 报「不支持 Excel 文件，请在 Excel 里另存为 csv（逗号分隔）再上传」；png、jpg、jpeg、gif、webp、bmp 报「本期不支持图片，可以把文字贴进对话里，或者传 PDF」；其它报「只支持 txt、md、csv、pdf、docx 文件」。路由的「上传」不写「类型」（写了的话 xlsx 和图片会被 存文件 用引擎的话拦掉，老师看不到上面两句原文），所以类型由本模块按扩展名判；文件头是否对得上交给 读文档（坏 pdf、坏 docx、二进制冒充 txt 都会读不出来，回 读文档 的 error 原文）。代价：被拒的文件已经由路由存进了 uploads/（按哈希命名，同一个文件不重复存），本模块不记行，清理脚本也不扫这种孤儿文件（uploads/ 与教材导入共用，按「没有行引用」删会误删教材文件）。
#
# 大小：单个文件 10MB（路由「上限 10MB」挡第一道；直接调用时 file_size 大于 10485760 报 400 附件不能超过 10MB）；整个请求另有引擎的 32MB 上限。
#
# 配额（D8）：每位老师在每个科目最多保留 20 个 status=ok 的附件，满了再传新文件报 409（同一个文件重复传不算新附件）；deleted 的不占配额。
#
# 权限：附件是教师自己的。写操作（存附件、挂上附件、移除附件、删除附件）按 need=write 解析科目（只读老师、学生报 403 没有权限修改该科目；D14 只读老师只能提问，不能传文件）；读操作（取当前附件、列附件、取附件文本）按读解析科目，但一律只查 teacher=current_user 的行（别人的附件对本人就是不存在：404 没有这个附件 / 不出现在列表里）。跨科目：所有查询都带 subject_id=本科目。
#
# 清理脚本 setup/cleanup_assist_files.py（Python，手动或 cron 跑，D8；DSL 没有删文件的动词所以写在脚本里；只读这一张表，不碰别的业务表）：
# - 默认 dry-run：只打印要删的行（id、teacher、subject_id、name、last_used_at、path）和要删的文件，不改库、不删文件；加 --apply 才真删。参数 --db（默认 kg_v4/app.db）、--days（默认 30）、--keep（每老师每科目保留的 ok 行数，默认 20）。
# - 一律跳过 attached=1 的行（当前挂着的附件不删，哪怕很旧）。
# - 要删的行：①status=deleted 的全部；②status=ok 且 last_used_at 早于 --days 天前的；③每位老师每个科目 status=ok 的行超过 --keep 个时，按 last_used_at 从旧到新（同时间按 id 小的先）删到只剩 --keep 个（attached=1 的那行计数但不删）。
# - --apply 时先在一个事务里删行，提交后再删磁盘文件：某行的 path 已没有任何 teacher_assist_file 行（含别的老师、别的科目、deleted 以外的）引用，并且 textbook_import 的任务表也没引用同一路径时才删文件（同一个哈希文件可能被别人或教材导入用着）；文件不存在不算错。
# - 结束打印「删了 n 行、m 个文件（跳过当前附件 k 个）」；dry-run 打印「将删 …（dry-run，没有改动；加 --apply 执行）」。不调 DSL、不经 HTTP，正式库上跑之前照例先备份。

## 表
# 约定检查豁免 表名前缀：表名沿用 M4 从 teacher_assist 拆出本模块前的 teacher_assist_ 前缀：库里已有数据，改名要迁移库并改查询；表名不重复由全局检查保证
表 teacher_assist_file 学习记录
  teacher 文本 教师用户名（附件归谁；只有本人能看、挂上、移除、删除）
  subject_id 整数 所属科目，默认 1；别的科目的附件一律当没有（404 没有这个附件）
  name 文本 原文件名（上传信息里的 name；直接调用没给时取 path 的文件名部分）
  ext 文本 类型（小写扩展名，不带点）：txt / md / csv / pdf / docx 之一
  size 整数 文件字节数（上传信息里的 size；直接调用没给时为 0）
  path 文本 存放路径（存文件 返回的 uploads/<sha16>.<ext>，按内容哈希命名，同一个文件只存一份）
  pages 整数 页数（pdf 为 读文档 的 pages，其它为 0）
  chars 整数 全文字数（读文档 的 chars，不是截断后的字数）
  text 长文本 读文档 取出的纯文本，最多存前 50000 字（超出部分不存；chars 仍是全文字数）
  stats 长文本 csv 的基本统计（后端算好的纯文本，见 csv统计），其它类型为空串
  rows 整数 csv 的数据行数（不含表头），其它类型为 0
  status 文本 ok（可用）/ deleted（老师删了，等清理脚本删行和文件；不进列表、不占配额、不能挂上、取不到文本）
  attached 整数 是否为当前附件（1/0）；每位老师在每个科目至多一个 1；清理脚本跳过 1 的
  created_at 文本 上传时间 YYYY-MM-DD HH:MM:SS
  last_used_at 文本 最近一次被用到的时间（存附件、挂上附件、取附件文本 时更新），清理脚本按它排新旧

## 页面字段
页面 assist_file_view 教师助手附件
  assist_file 文件 附件（助手页底栏的选文件；接口 /teacher_assist/attach 的上传字段）
  att_id 整数 附件表「编号」，也是行动作带的参数
  att_name 文本 附件表「文件」列
  att_info 文本 附件表「大小」列（「pdf · 3 页 · 1234 字」「csv · 120 行 · 3456 字」）
  att_at 文本 附件表「上传时间」列
  att_on 整数 是否为当前附件（1/0），行上「挂上」按钮只在 0 时出现

## 函数
函数 本科目 learner current_role auth_mode subject need?
  返回 {subject_id}；本次请求用哪个科目
  伪代码 调用 subject.解析科目 learner=learner current_role=current_role auth_mode=auth_mode subject=subject need=need，原样返回它的 subject_id（四个入参都是空串时得 1；显式 subject 无权时 解析科目 报 403/404、不是数字报 400，need=write 且没有写权限报 403 没有权限修改该科目，原样抛出）。存附件、挂上附件、移除附件、删除附件 传 need=write；取当前附件、列附件、取附件文本 按读处理（只查本人的行）

函数 本人附件 current_user file_id subject_id
  返回 附件行 {id, teacher, subject_id, name, ext, size, path, pages, chars, text, stats, rows, status, attached, created_at, last_used_at}
  报错 400 file_id 不合法
  报错 404 没有这个附件
  伪代码 file_id 不是正整数报错 400 file_id 不合法
  伪代码 查 teacher_assist_file 中 id=file_id、teacher=current_user、subject_id=subject_id、status=ok 的一行；没有（不存在、别人的、别的科目的、已删除的）报错 404 没有这个附件

函数 附件标签 name ext pages chars rows
  返回 {label, info}；info 是「ext · 3 页 · 1234 字」（pdf）/「csv · 120 行 · 3456 字」（csv）/「ext · 1234 字」（其它）；label 是「附件：name（info）」，给附件条和对话里那句「已挂上」用

函数 判类型 file_name file_path file_ext
  返回 {ext, error}；error 为空表示可收
  伪代码 ext 取 file_ext；为空取 file_name 最后一个点之后的部分；还为空取 file_path 的；去掉开头的点、转小写
  伪代码 ext 是 txt、md、csv、pdf、docx 之一：error 为空串
  伪代码 ext 是 xlsx、xls 之一：error「不支持 Excel 文件，请在 Excel 里另存为 csv（逗号分隔）再上传」
  伪代码 ext 是 png、jpg、jpeg、gif、webp、bmp 之一：error「本期不支持图片，可以把文字贴进对话里，或者传 PDF」
  伪代码 其它（含没有扩展名）：error「只支持 txt、md、csv、pdf、docx 文件」

函数 csv统计 file_path text
  返回 {rows, stats}；rows 是数据行数（不含表头）；stats 是给模型看的统计文本（数字全由这里算，模型不自己算）
  伪代码 用 data 包 读CSV 读 file_path 得行对象列表（首行是表头，UTF-8，带不带 BOM 都行）；读CSV 出错（如 GBK 编码）时改为把 text（读文档 已按编码规则读好的全文）按行切、第一行当表头、每行按英文逗号切（不处理引号，简单表够用），空行跳过
  伪代码 rows = 数据行数；列名按表头顺序
  伪代码 逐列：去首尾空白后为空串的格记缺失；非缺失的格全都能按数字解析（整数或小数，允许负号）且至少一个时算数值列，否则算文本列
  伪代码 stats 第一行「共 rows 行，n 列：列名1、列名2、…」；数值列每列一行「列名：均值 x，最低 y，最高 z，缺失 k」（均值保留 2 位小数，最低最高按原文去掉多余的 0）；文本列每列一行「列名：文本列，缺失 k」；列超过 30 个时只写前 30 列并加「（另有 m 列未列出）」
  伪代码 rows 等于 0：stats 为「只有表头，没有数据行：列名…」
  伪代码 返回 {"rows": rows, "stats": stats}

公开 函数 存附件 current_user file_path file_name? file_size? file_ext? current_role? auth_mode? subject?
  返回 {ok, file_id, name, ext, pages, chars, rows, label, info, reused}；把一个已存盘的上传文件记成本人在本科目的附件并挂上（attached=1，同时把本人在本科目原来挂着的那个摘下）；reused 为 1 表示本人在本科目已有同一个文件（path 相同、status=ok），没有新建行，只把那一行挂上
  报错 400 current_user 不能为空
  报错 400 文件路径不能为空
  报错 400 不支持 Excel 文件，请在 Excel 里另存为 csv（逗号分隔）再上传
  报错 400 本期不支持图片，可以把文字贴进对话里，或者传 PDF
  报错 400 只支持 txt、md、csv、pdf、docx 文件
  报错 400 附件不能超过 10MB
  报错 400 文件里没有可读的文字
  报错 409 每个科目最多保留 20 个附件，请先删掉不用的附件
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id；四个都不传得 1；teacher_assist 调用时传角色和登录模式（只读老师在这里 403）
  伪代码 current_user 为空报错 400 current_user 不能为空；file_path 去空白后为空报错 400 文件路径不能为空
  伪代码 调用 判类型 file_name=file_name file_path=file_path file_ext=file_ext 得 ext、error；error 不为空报错 400 error 原文（不读文件、不写库）
  伪代码 file_size 不为空且是整数且大于 10485760，报错 400 附件不能超过 10MB
  伪代码 name 取 file_name，为空取 file_path 的文件名部分
  伪代码 同一个文件：查 teacher_assist_file 中 teacher=current_user、subject_id=subject_id、path=file_path、status=ok 的行；有：在一个事务里先把本人在本科目 attached=1 的行置 0，再把这一行置 attached=1、last_used_at=当前时间，返回该行的各项和 reused=1（不重读文件、不查配额）
  伪代码 配额：本人在本科目 status=ok 的行数大于等于 20，报错 409 每个科目最多保留 20 个附件，请先删掉不用的附件（不读文件、不写库）
  伪代码 用 doc 包 读文档 读 file_path 得 kind、text、pages、chars、error；error 不为空报错 400 error 原文（扫描版 PDF 是「需要 OCR，暂不支持」那句，编码认不出来同理）；text 去空白后为空报错 400 文件里没有可读的文字
  伪代码 ext 等于 csv：调用 csv统计 file_path=file_path text=text 得 rows、stats；其它 rows=0、stats 空串
  伪代码 在一个事务里：本人在本科目 attached=1 的行置 0；插入 teacher_assist_file (teacher=current_user, subject_id, name, ext, size=file_size 是整数时取它否则 0, path=file_path, pages, chars, text=text 的前 50000 字, stats, rows, status=ok, attached=1, created_at=当前时间, last_used_at=当前时间)，取新行 id
  伪代码 调用 附件标签 得 label、info
  伪代码 返回 {"ok": 1, "file_id": id, "name": name, "ext": ext, "pages": pages, "chars": chars, "rows": rows, "label": label, "info": info, "reused": 0 或 1}

公开 函数 取当前附件 current_user current_role? auth_mode? subject?
  返回 {file_id, name, ext, pages, chars, rows, label}；本人在本科目当前挂着的附件（attached=1 且 status=ok）；没有时各键都是空串（file_id 空串）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id（读权限即可）
  伪代码 查 teacher_assist_file 中 teacher=current_user、subject_id=subject_id、status=ok、attached=1 的行，按 id 降序取一行；没有返回全空串；有则调用 附件标签 补 label

公开 函数 挂上附件 current_user file_id current_role? auth_mode? subject?
  返回 {ok, file_id, label}；把本人在本科目的一个旧附件挂成当前附件（原来挂着的摘下），last_used_at 更新
  报错 400 file_id 不合法
  报错 404 没有这个附件
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id
  伪代码 调用 本人附件 current_user=current_user file_id=file_id subject_id=subject_id（400/404 原样抛）
  伪代码 在一个事务里：本人在本科目 attached=1 的行置 0；该行置 attached=1、last_used_at=当前时间
  伪代码 返回 {"ok": 1, "file_id": file_id, "label": 附件标签 的 label}

公开 函数 移除附件 current_user file_id? current_role? auth_mode? subject?
  返回 {ok, dropped}；「移除附件」：只把附件从当前摘下（attached=0），行和文本都留着（附件表里还在，可以再挂上）；dropped 是这次摘下的行数（0 或 1）
  报错 400 file_id 不合法
  报错 404 没有这个附件
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id
  伪代码 file_id 为空：把本人在本科目 attached=1 的行置 0（附件条上的「移除附件」走这里；没有挂着的不报错，dropped=0）
  伪代码 file_id 不为空：调用 本人附件 current_user=current_user file_id=file_id subject_id=subject_id（400/404 原样抛），把该行置 attached=0；原来就是 0 时 dropped=0
  伪代码 返回 {"ok": 1, "dropped": n}

公开 函数 删除附件 current_user file_id current_role? auth_mode? subject?
  返回 {ok, file_id}；老师删掉一个附件：status=deleted、attached=0、text 和 stats 清成空串（不再进列表、不占配额、取不到文本）；行和磁盘文件留给清理脚本删（DSL 没有删文件的动词）
  报错 400 file_id 不合法
  报错 404 没有这个附件
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 403 没有权限修改该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject need=write 得 subject_id
  伪代码 调用 本人附件 current_user=current_user file_id=file_id subject_id=subject_id（400/404 原样抛；已删除的再删报 404）
  伪代码 UPDATE 该行 SET status=deleted, attached=0, text='', stats=''
  伪代码 返回 {"ok": 1, "file_id": file_id}

公开 函数 列附件 current_user current_role? auth_mode? subject?
  返回 {total, limit, files}；files 是本人在本科目 status=ok 的附件 [{att_id, att_name, att_info, att_at, att_on}]，当前挂着的排第一，其余按 id 降序；att_at 是 created_at 的前 16 个字符；limit 恒为 20（页面提示「已存 total / 20 个」）
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id（读权限即可；只读老师没有附件，得空表）
  伪代码 查 teacher_assist_file 中 teacher=current_user、subject_id=subject_id、status=ok 的行，按 attached 降序、id 降序；att_info 用 附件标签 的 info，att_on=attached
  伪代码 返回 {"total": 条数, "limit": 20, "files": 列表}

公开 函数 取附件文本 current_user file_id question? max_chars? current_role? auth_mode? subject?
  返回 {file_id, name, ext, chars, pages, rows, text, stats, mode, truncated}；给提示词用的附件文本（D5：最多 6000 字）；mode 为 full（全文）/ keyword（按问题里的关键词摘段）/ headtail（开头加结尾）/ csv（表头加前若干行）；truncated 为 1 表示不是全文；stats 是 csv 的统计文本（其它类型空串，不计入 6000 字）；同时把该行 last_used_at 更新为当前时间
  报错 400 file_id 不合法
  报错 404 没有这个附件
  报错 400 max_chars 不合法
  报错 400 subject 不对
  报错 403 该科目未分配给你
  报错 403 没有权限访问该科目
  报错 404 没有这个科目
  伪代码 科目：调用本模块 本科目 learner=current_user current_role=current_role auth_mode=auth_mode subject=subject 得 subject_id（读权限即可，只取本人的）
  伪代码 调用 本人附件 current_user=current_user file_id=file_id subject_id=subject_id（400/404 原样抛）得行；src = 行的 text（库里最多存了 50000 字），n = 行的 chars（全文字数）
  伪代码 max_chars 为空取 6000；不是 500 到 6000 的整数报错 400 max_chars 不合法（上限就是 D5 的 6000，调用方只能往小里要）；下面的 M 指它
  伪代码 csv：表头一行加数据行，按顺序拼，行数到 200 行或再加一行就超过 M 字时停；没拼完所有行就在末尾加一行「（共 rows 行，只给了前 k 行；统计见上面，是按全部行算的）」，truncated=1，否则 0；mode=csv
  伪代码 其它类型，n 不超过 M 且 src 就是全文：text=src，mode=full，truncated=0
  伪代码 超过 M 且 question 不为空：关键词 = question 按空白和中英文标点（，。、？！；：,.?!;: 引号括号）切开、去空后长度 2 到 20 的片段，去重后最多 8 个；段落 = src 按空行切（没有空行时按换行切），去掉空段；按原顺序取包含任一关键词的段落拼起来（段之间空一行），拼到 M 字为止（最后一段放不下就截到正好 M 字）；至少命中一段时 text=「（按问题里的关键词摘了 k 段，全文 n 字）」+ 换行 + 拼好的段落，mode=keyword，truncated=1
  伪代码 超过 M 且 question 为空，或一段都没命中：text = src 的前 (M − 1500 − 20) 字 + 换行 +「（中间省略，全文 n 字）」+ 换行 + src 的最后 1500 字（M=6000 时就是「开头 4480 字 + 结尾 1500 字」，总长不超过 M），mode=headtail，truncated=1；n 大于 50000（库里只存了前 50000 字，文件真正的结尾没有存）时不取结尾：text = src 的前 (M − 60) 字 + 换行 +「（只给了开头；全文 n 字，系统只保存了前 50000 字，结尾没有保存）」，mode=headtail，truncated=1（不把第 50000 字附近的内容当成文件结尾给模型）；关键词摘段同样只在前 50000 字里找，提示句里写「（按问题里的关键词从前 50000 字里摘了 k 段，全文 n 字）」
  伪代码 UPDATE 该行 SET last_used_at=当前时间
  伪代码 返回 {"file_id": file_id, "name", "ext", "chars": n, "pages", "rows", "text": text, "stats": 行的 stats, "mode": mode, "truncated": 0 或 1}

## 用例
用例 存附件_txt正常挂上
  先 文件 uploads/a.txt 内容=第一段：は和が的区别\n\n第二段：练习
  调用 存附件 current_user=t1 file_path=uploads/a.txt file_name=笔记.txt file_size=40 file_ext=txt
  得 ok=1 ext=txt reused=0 rows=0
  库 teacher_assist_file 共 1 行
  库 teacher_assist_file 含 teacher=t1 subject_id=1 name=笔记.txt ext=txt path=uploads/a.txt status=ok attached=1

用例 存附件_xlsx提示另存csv
  先 文件 uploads/b.xlsx 内容=x
  调用 存附件 current_user=t1 file_path=uploads/b.xlsx file_name=成绩.xlsx file_ext=xlsx
  报错 400
  库 teacher_assist_file 共 0 行

用例 存附件_图片本期不支持
  先 文件 uploads/c.png 内容=x
  调用 存附件 current_user=t1 file_path=uploads/c.png file_name=板书.png file_ext=png
  报错 400
  库 teacher_assist_file 共 0 行

用例 存附件_其它类型不支持
  先 文件 uploads/d.exe 内容=x
  调用 存附件 current_user=t1 file_path=uploads/d.exe file_name=d.exe
  报错 400
  库 teacher_assist_file 共 0 行

用例 存附件_超过10MB
  先 文件 uploads/a.txt 内容=第一段
  调用 存附件 current_user=t1 file_path=uploads/a.txt file_name=a.txt file_size=10485761 file_ext=txt
  报错 400
  库 teacher_assist_file 共 0 行

用例 存附件_没有文字
  先 文件 uploads/e.txt 内容=\n\n
  调用 存附件 current_user=t1 file_path=uploads/e.txt file_name=e.txt file_ext=txt
  报错 400
  库 teacher_assist_file 共 0 行

用例 存附件_csv算统计
  先 文件 uploads/s.csv 内容=姓名,分数\n小明,80\n小红,\n小刚,60
  调用 存附件 current_user=t1 file_path=uploads/s.csv file_name=成绩.csv file_ext=csv
  得 ok=1 ext=csv rows=3
  库 teacher_assist_file 含 ext=csv rows=3 attached=1

用例 存附件_新附件挂上旧的摘下
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=旧.txt ext=txt size=3 path=uploads/old.txt pages=0 chars=3 text=旧内容 stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  先 文件 uploads/a.txt 内容=新内容
  调用 存附件 current_user=t1 file_path=uploads/a.txt file_name=新.txt file_ext=txt
  得 ok=1
  库 teacher_assist_file 共 2 行
  库 teacher_assist_file 含 id=1 attached=0 status=ok
  库 teacher_assist_file 含 id=2 attached=1

用例 存附件_同一文件不重复记
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=a.txt ext=txt size=9 path=uploads/a.txt pages=0 chars=3 text=新内容 stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 文件 uploads/a.txt 内容=新内容
  调用 存附件 current_user=t1 file_path=uploads/a.txt file_name=a.txt file_ext=txt
  得 ok=1 file_id=1 reused=1
  库 teacher_assist_file 共 1 行
  库 teacher_assist_file 含 id=1 attached=1

用例 存附件_满20个409
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f1.txt ext=txt size=1 path=uploads/f1.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f2.txt ext=txt size=1 path=uploads/f2.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f3.txt ext=txt size=1 path=uploads/f3.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f4.txt ext=txt size=1 path=uploads/f4.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f5.txt ext=txt size=1 path=uploads/f5.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f6.txt ext=txt size=1 path=uploads/f6.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f7.txt ext=txt size=1 path=uploads/f7.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f8.txt ext=txt size=1 path=uploads/f8.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f9.txt ext=txt size=1 path=uploads/f9.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f10.txt ext=txt size=1 path=uploads/f10.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f11.txt ext=txt size=1 path=uploads/f11.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f12.txt ext=txt size=1 path=uploads/f12.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f13.txt ext=txt size=1 path=uploads/f13.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f14.txt ext=txt size=1 path=uploads/f14.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f15.txt ext=txt size=1 path=uploads/f15.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f16.txt ext=txt size=1 path=uploads/f16.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f17.txt ext=txt size=1 path=uploads/f17.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f18.txt ext=txt size=1 path=uploads/f18.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f19.txt ext=txt size=1 path=uploads/f19.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f20.txt ext=txt size=1 path=uploads/f20.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 文件 uploads/a.txt 内容=第二十一个
  调用 存附件 current_user=t1 file_path=uploads/a.txt file_name=a.txt file_ext=txt
  报错 409
  库 teacher_assist_file 共 20 行

用例 存附件_已删除的不占配额
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f1.txt ext=txt size=1 path=uploads/f1.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f2.txt ext=txt size=1 path=uploads/f2.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f3.txt ext=txt size=1 path=uploads/f3.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f4.txt ext=txt size=1 path=uploads/f4.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f5.txt ext=txt size=1 path=uploads/f5.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f6.txt ext=txt size=1 path=uploads/f6.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f7.txt ext=txt size=1 path=uploads/f7.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f8.txt ext=txt size=1 path=uploads/f8.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f9.txt ext=txt size=1 path=uploads/f9.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f10.txt ext=txt size=1 path=uploads/f10.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f11.txt ext=txt size=1 path=uploads/f11.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f12.txt ext=txt size=1 path=uploads/f12.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f13.txt ext=txt size=1 path=uploads/f13.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f14.txt ext=txt size=1 path=uploads/f14.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f15.txt ext=txt size=1 path=uploads/f15.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f16.txt ext=txt size=1 path=uploads/f16.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f17.txt ext=txt size=1 path=uploads/f17.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f18.txt ext=txt size=1 path=uploads/f18.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f19.txt ext=txt size=1 path=uploads/f19.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=f20.txt ext=txt size=1 path=uploads/f20.txt pages=0 chars=1 text=x stats=空 rows=0 status=deleted attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  先 文件 uploads/a.txt 内容=第二十个
  调用 存附件 current_user=t1 file_path=uploads/a.txt file_name=a.txt file_ext=txt
  得 ok=1 reused=0
  库 teacher_assist_file 共 21 行

用例 存附件_只读老师403
  先 数据 subject_info code=jp_grammar name=日语语法 kind=language caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 数据 subject_info code=math name=数学 kind=general caps=x levels=空 qtypes=choice visibility=public owner=t1 status=active created_at=2026-01-01 updated_at=2026-01-01
  先 文件 uploads/a.txt 内容=内容
  调用 存附件 current_user=t2 file_path=uploads/a.txt file_name=a.txt file_ext=txt current_role=teacher auth_mode=on subject=2
  报错 403
  库 teacher_assist_file 共 0 行

用例 跨科目_存附件落当前科目只摘本科目的
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=日语.txt ext=txt size=3 path=uploads/jp.txt pages=0 chars=3 text=日语 stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  先 文件 uploads/a.txt 内容=数学讲义
  调用 存附件 current_user=t1 file_path=uploads/a.txt file_name=a.txt file_ext=txt subject=2
  得 ok=1
  库 teacher_assist_file 含 id=1 subject_id=1 attached=1
  库 teacher_assist_file 含 id=2 subject_id=2 attached=1

用例 取当前附件_没有为空
  调用 取当前附件 current_user=t1
  得 file_id=空

用例 取附件文本_短文全文
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=a.txt ext=txt size=9 path=uploads/a.txt pages=0 chars=3 text=短内容 stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  调用 取附件文本 current_user=t1 file_id=1
  得 file_id=1 text=短内容 mode=full truncated=0 chars=3

用例 取附件文本_别人的404
  先 数据 teacher_assist_file teacher=t2 subject_id=1 name=a.txt ext=txt size=9 path=uploads/a.txt pages=0 chars=3 text=短内容 stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  调用 取附件文本 current_user=t1 file_id=1
  报错 404

用例 跨科目_取附件文本别的科目404
  先 数据 teacher_assist_file teacher=t1 subject_id=2 name=a.txt ext=txt size=9 path=uploads/a.txt pages=0 chars=3 text=短内容 stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  调用 取附件文本 current_user=t1 file_id=1
  报错 404

用例 取附件文本_上限不合法
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=a.txt ext=txt size=9 path=uploads/a.txt pages=0 chars=3 text=短内容 stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  调用 取附件文本 current_user=t1 file_id=1 max_chars=9000
  报错 400

用例 挂上附件_换当前附件
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=a.txt ext=txt size=1 path=uploads/a.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=b.txt ext=txt size=1 path=uploads/b.txt pages=0 chars=1 text=y stats=空 rows=0 status=ok attached=0 created_at=2026-01-01 last_used_at=2026-01-01
  调用 挂上附件 current_user=t1 file_id=2
  得 ok=1 file_id=2
  库 teacher_assist_file 含 id=1 attached=0
  库 teacher_assist_file 含 id=2 attached=1

用例 移除附件_只摘下不删
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=a.txt ext=txt size=1 path=uploads/a.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  调用 移除附件 current_user=t1
  得 ok=1 dropped=1
  库 teacher_assist_file 共 1 行
  库 teacher_assist_file 含 id=1 attached=0 status=ok

用例 删除附件_标记删除不再列出
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=a.txt ext=txt size=1 path=uploads/a.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  先 调用 删除附件 current_user=t1 file_id=1
  调用 列附件 current_user=t1
  得 total=0 limit=20
  库 teacher_assist_file 含 id=1 status=deleted attached=0

用例 删除附件_别人的404
  先 数据 teacher_assist_file teacher=t2 subject_id=1 name=a.txt ext=txt size=1 path=uploads/a.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  调用 删除附件 current_user=t1 file_id=1
  报错 404
  库 teacher_assist_file 含 id=1 status=ok attached=1

用例 跨科目_列附件只列本人本科目
  先 数据 teacher_assist_file teacher=t1 subject_id=1 name=a.txt ext=txt size=1 path=uploads/a.txt pages=0 chars=1 text=x stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t2 subject_id=1 name=b.txt ext=txt size=1 path=uploads/b.txt pages=0 chars=1 text=y stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  先 数据 teacher_assist_file teacher=t1 subject_id=2 name=c.txt ext=txt size=1 path=uploads/c.txt pages=0 chars=1 text=z stats=空 rows=0 status=ok attached=1 created_at=2026-01-01 last_used_at=2026-01-01
  调用 列附件 current_user=t1
  得 total=1 limit=20
