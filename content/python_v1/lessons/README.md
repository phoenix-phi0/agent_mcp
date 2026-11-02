# Python 双语教材 · K185

本目录新增 13 课：入门 4 课、基础 4 课、进阶 5 课。覆盖全部 34 个知识点和 110 个条目；52 个示例、26 道带答案练习。中文与日文正文逐项对应；程序代码、标准输入、预期输出保持相同。未连接网络、未启动服务、未访问正式库、未导入任何数据。原有 python_v1 文件未改动。

## 文件与格式

| 文件 | 用途 |
|---|---|
| lessons.zh.json / lessons.ja.json | 结构化教材主文件，UTF-8，顶层含 schema、subject_id、subject_code、language、series_code、series_name、lessons |
| lessons.zh.md / lessons.ja.md | 可直接阅读的全套教材，含全部示例和练习答案 |
| lesson_import.zh.jsonl / lesson_import.ja.jsonl | 符合 lesson 内容文件字段的派生文件；一行一课，换行在 JSON 字符串中转义 |
| lesson_rows.zh.json / lesson_rows.ja.json | 同样的课文对象组成 JSON 数组，可供现有内部 rows_json 参数使用 |
| check_lessons.py | 只读校验与隔离执行；--write-evidence 才写运行证据，不修改预期输出 |
| render_lessons.py | 仅重新生成本目录的 Markdown、JSONL、rows_json，完全不接触库 |
| verification.json | 实际运行记录：代码哈希、输入、预期及实际输出、stderr、返回码与逐项通过状态 |

主文件每课字段：code（稳定业务键 python.lesson01..13）、seq、title、level、level_label、point_codes（课内学习顺序）、point_titles、item_codes、objectives、explanation、examples、common_errors、exercises。示例含 id/title/code/stdin/stdout；练习含 id/prompt/answer，answer 含 code/stdin/stdout/explanation。所有 stdout 均含精确末尾换行；标准输入不算屏幕回显。示例每个单独运行，不能依赖前一个示例的变量或文件。

日文版保留 code、id、point_codes、item_codes 和 level 的业务值。level 仍用合法的“入门/基础/进阶”，可见的 level_label 则是“入門/基礎/応用”。其他叙述文字（目标、解说、标题、错误、练习、答案说明）均翻成日文，知识点标题逐字采用已有 ja/kg_point.tsv。代码内英文字符串、注释、文档字符串属于代码，程序输出也原样保留。

## 已有数据模型与导入调查

只读依据均来自 /workspace/agent_mcp/kg_v4：

- contracts/lesson.md（表、公开函数、路由、内容文件）；entities/lesson.entity（实体字段）；services/lesson.zs（实际校验与写入）。
- setup/init_data.py:74–109：旧 kg/content/lessons.jsonl 及 item_lessons.jsonl 转成 lessons.txt；:312–313 上传 /lesson/import。旧样例 /workspace/agent_mcp/kg/content/lessons.jsonl 使用 explanation、formation 与 JSON 编码的 jp/zh 例句，由此脚本转换，并非当前 lesson JSONL 的同名字段。
- services/textbook_import.zs:5–13：非日语科目检查 caps JSON 的 textbook_import=1，否则报 403 本科目没开教材导入。这里只核实代码，未查正式库 Python 的 caps 值。
- i18n/ja.tsv 文件头、python_v1/ja/kg_point.tsv、ja/kg_item.tsv：采用“知識ポイント、項目、テキスト、練習”等既有术语。
- scripts/migrate_subject_content_translation.py：实际表以 (tbl,row_key,field,lang) 唯一，不能使用设计稿早期 row_id 方案。services/subject.zs 的译文查询使用稳定 row_key。

lesson_series 存 code/name/intro/source/license/sort_order/subject_id；series code 全局唯一，sort_order<0 代表撤下。
lesson_text 存 code/level/title/summary/explain/connection/examples/examples_edited/orig_title/series_code/seq/subject_id；code 全局唯一。
lesson_item_link 存 lesson_code/item_code/subject_id，lesson_point_link 存 lesson_code/point_code/subject_id。
lesson_pref 存 learner/series_code/subject_id，唯一 learner+subject_id，系列重灌不应清空偏好。

旧 HTTP 入口是教师角色 POST /lesson/import，上传 md/txt（20MB），显式传 subject=2、series_code=python.core_v1、series_name。有效行格式为：

```text
课号|等级|标题|一句话|讲解|接续|例句|是否改过例句|原标题|课序|条目编号列表|知识点编号列表
```

空行及 # 注释忽略，编号列表用英文逗号。现有例句正文用 @@ 分例、^^ 分左右列；页面列名是日语/中文。逐行竖线解析没有适合多行 Python 代码的可靠通用转义协议。源代码中的 |（集合并集）、缩进、换行也会与此路径冲突，所以本次不制造有损的竖线文件。

现有内部函数“写入系列课文并重灌”接收 series_code、rows_json、series_name 等和 subject；rows_json 为数组，一课的字段恰为本目录 lesson_rows.*.json 中的字段：code/level/title/summary/explain/connection/examples/examples_edited/orig_title/seq/item_codes/point_codes。函数写 content/lesson/series/{series_code}.jsonl，再事务重灌，映射不存在的课会被单独拒收；这不是已暴露的 JSONL HTTP 上传接口。

lesson 自身导入无 textbook_import 的非日语 caps 门控，但依然要求该科目写权限、编号前缀、映射归属和等级合法。非日语课号必须以 python. 开头；等级必须属于 subject.科目等级 返回的本科目 levels。本教材依据当前源 quiz_v2.txt 使用入门/基础/进阶，未采用 README 遗留段落中的旧 N5 规则。服务里的旧注释仍可能写 N5..N1，实际执行代码已调用本科目等级。

## 内容到旧模型的映射

- 系列：python.core_v1 / Python 从零入门；subject_id 应由 subject=2 的上下文注入，不能依赖默认 1。
- 课号、标题、等级、课序、知识点、条目：直接映射相应字段与 link 表。
- objectives[0] → summary；完整学习目标、讲解、52 个代码示例、常见错误和练习答案 → explain（Markdown）。
- connection 留空（K188）：这一栏是日语语法的「接续」，Python 没有对应内容，留空时课文页整栏隐藏；知识点关联看 point_codes。orig_title 用该语言的本课标题；examples_edited=0。
- 例句概念应映射为代码/标准输入/预期输出。当前派生导入文件将 examples 留空，完整代码放在 explain，避开 jp^^zh 文本解析。若后续增加结构化示例 UI，可直接从主文件 examples 提取，原内容不丢失。
- 原模型没有独立学习目标、常见错误、练习答案表，本次全部完整保存到 explain；若以后需要交互答题，再由单独任务建模，不把教材练习混入现有正式题库。

## 建议的后续导入步骤（本任务未执行）

1. 在可写测试环境中核验科目 id=2、code=python、等级和全部 34/110 关联编码。检查 python.core_v1 与课号是否碰撞，备份已有同系列内容；重灌会替换整系列。
2. 先运行下面的只读校验。优先写一次性 JSON 适配脚本或正式受控入口，读取 lesson_rows.zh.json，显式传 subject=2 和 series_code=python.core_v1，调用 lesson 内部“写入系列课文并重灌”。不要把 JSONL 直接传给 /lesson/import。
3. 核对 total/imported/file_rows=13、rejected=[]、point_links=34、item_links=110，确认其它系列/科目及 lesson_pref 未受影响。实际服务效果需后续任务实测，本任务不声称已导入成功。
4. 中文作为主内容。日文 JSONL/数组是同键的另一语言视图，不要再向同一系列导入日文导致中文被替换。后续转换成译文 TSV 时采用 tbl=lesson_text、row_key=python.lessonNN、field=title/summary/explain/orig_title，以及 lesson_series/python.core_v1/name；language 由导入器设为 ja。对于含换行文本，必须由支持 CSV 引号的 TSV 写入/读取器配套处理，或直接用结构化参数导入。
5. 读取时按账号语言替换受支持字段，缺失回退中文；同时核验多行代码安全显示。先测试回滚，再经另一个已授权任务导入正式库。

## 可能需要的代码改动（这里只列出）

1. 为 lesson 增加受控的 JSON/JSONL 文件导入入口或一次性适配脚本，将 lesson_rows.zh.json 数组传给现有“写入系列课文并重灌”；当前 /lesson/import 仅接收竖线分隔的 md/txt，不能直接上传本 JSONL。
2. 教材详情按科目显示代码内容：安全渲染 explain 的 Markdown 与代码块，保留缩进、行尾空格和换行；若需要专门示例栏，把日语/中文列改成代码/预期输出并采用结构化字段，避免 @@、^^ 分隔符。
3. 将 Python lesson_text（title/summary/explain/orig_title）及 lesson_series（name）纳入 subject_content_translation 的导入校验与读取替换；按稳定课号/系列号定位，缺译文回退中文。先核查现有实现是否已支持这些字段，再补缺口。

lesson 的科目门控、等级模型本身不需要为本教材改成日语规则，也不需要为走 lesson 内部导入而开启 textbook_import。若坚持使用 textbook_import AI 流水线，则还需由后续任务评估 Python 的能力配置、提示词与代码保真，不能据本任务直接打开。

## 自查

```bash
python3 -I /workspace/dslagent_exp/content/python_v1/lessons/check_lessons.py
```

如需重建证据，添加 --write-evidence。更改主文件内容后，先执行 render_lessons.py 再校验；渲染器不会根据实际执行结果修改任何预期输出。

本次本机 Python 3.13.5：13 课、34/34 知识点、110/110 条目、49/49 前置边；52 示例+26 答案=78 个独立程序。中日分别运行，共 156/156 次通过。每次在新临时目录以 python3 -I 执行，stdin 按 UTF-8 传入，stdout 按字节比对，要求 stderr 为空、返回码 0，单次限时 5 秒。代码不会读写教材目录，文件读写示例仅操作临时目录。预期输出由作者先写好，实际运行只验证，不反填。

| 课号 | 标题 | 等级 | 知识点（课内顺序） |
|---|---|---|---|
| python.lesson01 | 从第一个程序到算术运算 | 入门 | python.env, python.var, python.num, python.op |
| python.lesson02 | 字符串、方法与格式化输出 | 入门 | python.str, python.strm, python.fstr |
| python.lesson03 | 输入、比较与条件分支 | 入门 | python.io, python.bool, python.logic, python.if |
| python.lesson04 | 重复执行：while 与 for | 入门 | python.while, python.for |
| python.lesson05 | 列表、常用操作与切片 | 基础 | python.list, python.listop, python.slice |
| python.lesson06 | 元组、字典、集合与嵌套数据 | 基础 | python.tuple, python.dict, python.set, python.nest |
| python.lesson07 | 定义函数、参数与返回值 | 基础 | python.func, python.param, python.ret |
| python.lesson08 | 作用域与 lambda 排序 | 基础 | python.scope, python.lambda |
| python.lesson09 | 模块与标准库 | 进阶 | python.module |
| python.lesson10 | 异常处理与文件读写 | 进阶 | python.exc, python.file |
| python.lesson11 | 推导式、内置函数与类型判断 | 进阶 | python.comp, python.builtin, python.type |
| python.lesson12 | 类、对象、方法与属性 | 进阶 | python.class, python.method |
| python.lesson13 | 继承、重写与 super | 进阶 | python.inherit |
