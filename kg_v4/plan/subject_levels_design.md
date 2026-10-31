# K160 各科目自定义等级：设计（K161 定稿并实施）

> 状态：**已批准，K161 实施**。用户决策（定稿）：
> - **D1** 复用 `subject_info.levels` 逗号串（编码即名称）；空串视为 N5,N4,N3,N2,N1；新建通用科目默认「入门,基础,进阶」，语言科目默认 N5,N4,N3,N2,N1。
> - **D2** 改等级只许新增和调顺序；删除或改名在用（有题目 / 课文 / 教材导入草稿 / 做题进度引用）的等级 → 400 拒绝并提示「等级「X」还有N条记录在用，先改掉题目和课文的等级再删」；不做批量重命名。
> - **D3** 本轮不做教材导入的自定义等级：textbook_import 保持 N5–N1，对非日语科目关闭入口（新建导入加科目门控：subject_id≠1 且 caps.textbook_import≠1 → 403「本科目没开教材导入」）。
> - 不改引擎（tools/、templates/）。
> 契约按第 4 节、D3 口径落地 30 条（S1–S7、Q1–Q8、P1–P4、L1–L4、R1、T1–T3、A1–A2、textbook_import 门控 1 条；X1–X5 不做）。实施中的补充：subject 加私有函数「校验等级」「等级在用数」，quiz 加私有函数「首个有题等级」，按级统计掌握 多返回 level_count（便于用例核对项数）；问老师无学习记录时所有科目统一「先从{first}开始」。
> 依据：kg_v4 源码（与正式服务目录 /workspace/dslagent_exp/kg_v4_data 的 services/contracts 逐文件一致）、正式库只读查询、K157 报告。

## 0. 现状一句话
`subject_info.levels` 这一列**已经存在**（实体注释是「自定义等级列表，英文逗号分隔有序，空表示不分级」）。日语科目 1 的值是 `N5,N4,N3,N2,N1`，Python 科目 2 是空串。但是**没有任何代码读这一列**：建科目时写死空串，`subject_info_full.sql` 不查它，`subject_info_update.sql` 也不写它。所有等级逻辑都写死成 N5–N1。

正式库现状（只读查询）：
- quiz_question：科目 1 有 N5 132 / N4 140 / N3 96 / N2 88 / N1 10；科目 2 是 N5 99。
- lesson_text：只有科目 1 有数据（N5 38 / N4 37 / N3 26 / N2 22 / N1 2）。
- quiz_progress：科目 2 有 1 行，level=N5。

## 1. 盘点：「等级」的所有用处（文件:行号）

图例：**写死** = 写死了 N5–N1，必须改；**透传** = 只读取、展示或传递 level，不用改。

### 1.1 科目（subject）
| 位置 | 作用 | 判定 |
|---|---|---|
| entities/subject.entity:7 | `levels` 文本字段，已存在 | 可直接复用 |
| contracts/subject.md:11 | levels 定义：「空表示不分级」 | 语义要改（见 3.1） |
| contracts/subject.md:167-168 | 建科目时 levels 为空串，caps 模板里 language 带 `levels:1` | 改默认值 |
| contracts/subject.md:44-56、325、334 | 科目管理页面没有 levels 字段，载入和保存都不带 | 新增 |
| services/subject.zs:248-292（290 处写库） | 建科目 | 改 |
| services/subject.zs:300-317 改科目 | 只能改 name 和 intro | 改 |
| services/subject.zs:528/541 载入/保存科目页面 | 不带 levels | 改 |
| queries/subject_info_insert_general.sql:1、subject_info_insert_language.sql:1 | levels 写死 `''` | 改 |
| queries/subject_info_full.sql:1 / subject_info_update.sql:1 | 不读、不写 levels | 改 |
| setup/migrate_subject.py:9、32、116 | 给日语写入 `'N5,N4,N3,N2,N1'` 的种子数据 | 不改 |

### 1.2 做题（quiz）
| 位置 | 作用 | 判定 |
|---|---|---|
| services/quiz.zs:1009 开始页面 | 选「全部」时 `遍历 lx 于 N5，N4，N3，N2，N1` 逐级找有题的等级 | **写死** |
| services/quiz.zs:1257 课文页面 | 自由练选「全部」时同样逐级 | **写死** |
| services/quiz.zs:1233 | 复习模式下没有作答记录时，回填 `pick_level: N5` | **写死** |
| services/quiz.zs:951 | 题卡抬头 `{question.level}・{question.category}` | 透传（等级值换掉，这里自然跟着变） |
| services/quiz.zs:157-181、queries/quiz_q_free_all.sql、quiz_q_free_cat.sql | 按 level 相等过滤选题 | 透传 |
| services/quiz.zs:371-508（等级在 482） | /quiz/import 导入：等级列不做任何校验 | 加校验 |
| services/quiz.zs:705-730 开始 | 只判 level 非空 | 加校验 |
| entities/quiz.entity:34 | `pick_level 枚举 全部,N5,N4,N3,N2,N1` | **写死** |
| ui/quiz.ui:68 → web/app.js:1139-1141 | 静态下拉 | **写死**（生成物） |
| contracts/quiz.md:8、35、134、137、163、218、340、400 | 见第 4 节 | 改契约 |

### 1.3 学情 / 进度（progress、report）
| 位置 | 作用 | 判定 |
|---|---|---|
| services/progress.zs:266-311 按级统计掌握（/progress/levels，routes/progress.zs:31） | 5 组计数器、5 段 if，固定返回 N5..N1 五项 | **写死** |
| services/progress.zs:615-652 进度页 levels 段 | 再用 5 段 if 累计答题数 | **写死** |
| services/progress.zs:502-513 取点级映射 | 透传 lesson.取知识点等级 | 透传 |
| contracts/progress.md:151、160、257、278 | 写着「恒为 5 项」「五行」 | 改契约 |
| ui/progress.ui:9、62-64 → web/app.js:1671-1682 | 「各等级」表格，绑定 lists.levels | 透传（只有注释写了 N5..N1） |
| services/report.zs:32-37、192-197、335-339 | 把点等级挂到薄弱点上 | 透传 |
| contracts/report.md:52 | 「返回等级文本（N5 到 N1）」 | 改措辞 |

### 1.4 等级的总来源：lesson.取知识点等级（关键）
| 位置 | 作用 | 判定 |
|---|---|---|
| queries/lesson_level_by_point.sql:1 | `MAX(CAST(SUBSTR(level,2) AS INTEGER))`，假设等级都是「N+数字」 | **写死**，自定义等级在这里会算错 |
| services/lesson.zs:221-252（250：`设 out.level = N{row.lv}`） | 返回知识点最基础的等级 | **写死** |
| 调用方 | progress.zs:287、506；report.zs:36；teacher_assist.zs:250；assist_material.zs:117；assist_draft.zs:144、403；routes/lesson.zs:53 GET /lesson/point-level | 全部依赖它 |
| contracts/lesson.md:148、159 | 「N5 最基础…取数字最大」 | 改契约 |

注意：Python 科目没有课文，所以这个函数对 Python 的每个知识点都返回空串，学情的「各等级」统计在 Python 科目下全是 0。改造时要加一个兜底：没有课文时，从题目的等级里取。

### 1.5 教材 / 课次 / 教材导入（目前只有日语在用，但代码里没有 caps 门控，通用科目也能调到）
| 位置 | 作用 | 判定 |
|---|---|---|
| services/lesson.zs:289-292（导入课文数据）、lesson.zs:574（写入系列课文并重灌，注释在 446） | 课文导入校验 `^N[1-5]$`，共 2 处 | **写死** |
| contracts/lesson.md:15、42、181、208 | 字段说明、筛选枚举、两处导入校验 | 改契约 |
| entities/lesson.entity:46 `lesson_level 枚举 全部,N5..N1`；ui/textbook.ui:45 → web/app.js:1307-1309 | 教材页的等级筛选 | **写死** |
| services/textbook_import.zs:54-56 | 新建导入时的「等级范围」校验 | **写死** |
| services/textbook_import.zs:480、630、1447 | 改草稿、审阅通过、确认前三处校验 N5..N1 | **写死** |
| services/textbook_import.zs:828-839 | 等级范围是 N5..N1 之一时才按等级预筛候选条目 | **写死** |
| services/textbook_import.zs:849 | 模型提示词「level（N5/N4/N3/N2/N1）」 | **写死** |
| queries/textbook_import_draft_approve_mapped.sql:1 | `level IN ('N5','N4','N3','N2','N1')` | **写死** |
| entities/textbook_import.entity:14、34、62（`draft_level 枚举 N5..N1`）；ui/textbook_import.ui:46、107、147 → web/teacher.js:2820-2822、3019-3021 | 等级范围和草稿等级下拉 | **写死** |
| contracts/textbook_import.md:18、34、62、89、207、249、264、539 | 见第 4 节 | 改契约 |

### 1.6 默写 / 单词（日语专属的数据格式，建议不改）
| 位置 | 作用 | 判定 |
|---|---|---|
| services/dictation.zs:486-491 | 词义开头的 `[N4]` 前缀：识别、截取、去掉 | 日语词库数据格式，不改 |
| queries/vocab_dict_pick/list/count.sql:1 | `GLOB '[[]N[1-5]]*'` 用来去前缀；等级过滤用的是通用的 `'[' || :level || ']'` | 不改 |
| entities/dictation.entity:15、30（`dict_level 枚举`）；ui/quiz_dictation.ui:7-9、37 → web/app.js:1226-1228 | 默写等级下拉 | 不改（只对日语科目有意义） |
| contracts/dictation.md:18、32、330；vocab.md:70 | | 不改 |

### 1.7 教师助手（出题草稿、设置）、问老师
| 位置 | 作用 | 判定 |
|---|---|---|
| services/assist_draft.zs:390-409 | 草稿题的 level 直接用模型输出，不校验；为空时回填知识点等级，再不行就填 `-` | 加校验和兜底 |
| services/assist_draft.zs:603-614 | 出题提示词只写了「level」字段，没列出可选值 | 补上本科目等级 |
| contracts/assist_draft.md:85、116 | | 改契约 |
| services/teacher_assist.zs:92、176、250-251、285；assist_material.zs:117-120、211 | 只用来展示 | 透传 |
| assist_setting（契约和服务） | 没有用到等级 | 不涉及 |
| services/tutor.zs:24 | 判意图提示词写着「level（只能是 N5 N4 N3 N2 N1 或空串）」 | **写死** |
| services/tutor.zs:36 | `匹配 {level} ^(N5|N4|N3|N2|N1)$` | **写死** |
| services/tutor.zs:252-254 | 「先从N5开始」，链接 `level=N5` | **写死** |
| contracts/tutor.md:30、31、33、86 | 33 还规定 subject_id≠1 时 level 一律取空 | 改契约 |

### 1.8 导入导出格式
- 题库导入 /quiz/import：每行「题号|课程|**等级**|考点类别|…」，等级列目前不校验（quiz.md:134、137；quiz.zs:377-482）。
- 题库初始化 setup/init_data.py:149-152：从课程名 `bunpou_n([1-5])` 推出 N 等级。这是日语专用的灌库脚本，不改。
- 教材导入：见 1.5。图谱导入导出（kg.md、kg_manage）**不含等级列**。

### 1.9 测试 / e2e（写死 N5 的地方：tests/kg、tests/kg_v4、tests/e2e 共 20 个文件、113 处，不含 package-lock）
- 和做题直接相关：tests/kg/test_quiz.py（360、365、379、553、577、584-595，共 8 处 N5）、tests/e2e/quiz_run.js:441、567（567 是 `p.pick(p.selects()[0], "N5")`，依赖第一个 select 就是等级下拉）。
- 其余：tests/kg_v4/test_assist_drafts.py:57、58、147、148、196、203、204、354；test_assist_material.py:55-56；test_assist_insight.py:123-125；tests/e2e/series_run.js:186、pages_run.js:275。这些都在日语科目或默认科目下跑，按 3.1 的「空 levels 等于 N5–N1」兼容规则，**不需要改**。
- 契约用例：`先 数据 … level=N5` 这类数据行很多。按兼容规则，在科目 1 或没有 subject_info 行的情况下仍然成立。可能要改的现有用例约 1 条：assist_draft.md 约 375 行的「跨科目_校验草稿本科目条目」，用了 `level=初一`。

### 1.10 引擎（gen/、tools/、templates/）
- 引擎里没有写死 N5–N1：gen/ 和 templates/ 都没有命中；tools/verbs.py:5、105、111 和 tools/test_ui.py:355、363 是示例或测试夹具。
- ui DSL 已经支持动态下拉：`字段 X 控件 下拉 选项来自 <lists键>`，见 tools/ui.py:384-388、templates/frontend/widgets.j2:66-74，这个分支优先于静态枚举。kg_v4 里已有用例：textbook.ui:44 series_options、kg_manage.ui:93 point_options、subject.ui:103 teacher_options。
- 有一个坑（tools/ui.py:386）：**接口每次都要回这个键，进界面时前端会先清空 lists**。所以做题页每个会刷新页面的接口都要带上 `level_options`。
- DSL 自带逗号字面量遍历（`遍历 lx 于 N5，N4…`）和 text 包的 `按正则切分`，足够把 levels 串拆成列表。

**结论：不需要改引擎。**

## 2. 存储方案

**推荐 A：直接用现有的 `subject_info.levels`**（英文逗号分隔，顺序就是从易到难）。等级的编码同时就是显示名：日语 `N5,N4,N3,N2,N1`，Python `入门,基础,进阶`。
- 好处：列已存在，不用建表、不用迁表结构。现有契约用例里 `levels=空` 的写法不受影响。
- 代价：编码和显示名不能分开（比如改名时，题目里存的值也要跟着改）。

备选 B：新建表 `subject_level(subject_id, code, label, ord)`，code 和 label 分开，改显示名不用动题目。代价是要新建实体、写 CRUD、改科目管理界面加子表编辑，大约多一个模块的工作量（多 $2–4）。现在只有 2 个科目，不值得。

### 2.1 统一取值函数（subject 模块新增）
`公开 函数 科目等级 subject_id` → `{levels: [..有序..], first: 首级, options: [{value:"全部",label:"全部"}, {value:L, label:L}…]}`
- 读 subject_info.levels，按逗号切分，去掉空白和空项。
- **兼容规则**：行不存在或 levels 为空串，当作 `N5,N4,N3,N2,N1`。这样日语科目、现有所有测试库（大多没有 subject_info 行，或者 levels=空）的行为完全不变。Python 科目在迁移前也保持现在的 N5 行为。
- 其他模块一律调它，不再出现 N5–N1 字面量（vocab、dictation 的词义前缀除外）。

### 2.2 默认值
- 日语（kind=language）：新建时默认 `N5,N4,N3,N2,N1`。
- 通用（kind=general）：新建时默认 `入门,基础,进阶`，在科目管理里可以改。
- 校验：1–10 项，每项 1–12 个字，不能有 `,` `|` `^` 和空白，不能重复。

### 2.3 修改规则（改科目 / 保存科目页面）
- 负责教师（或 root）可以改：**新增等级、调整顺序**随时都行。
- **删掉或改名**某个等级时，如果它还被 quiz_question、lesson_text、textbook_import_draft 或本科目的 quiz_progress 引用，报 400「等级 X 还有 N 道题/课在用，先改题目等级再删」。改名可以单独做一个「重命名等级」操作，在一个事务里批量更新题目和课文（见决策点 2）。

## 3. 各功能怎么改

### 3.1 做题页
- 下拉：quiz.entity 的 pick_level 从枚举改成文本；quiz.ui:68 改成 `字段 pick_level 控件 下拉 选项来自 level_options 宽 90px 等级`。开始页面、课文页面、出下一题、提交这些凡是回整页的接口，都在 `lists.level_options` 里回 `科目等级.options`。
- 选「全部」时逐级：quiz.zs:1009 和 1257 改成 `遍历 lx 于 {lv.levels}`，抽成一个共用函数「首个有题等级」。
- 复习模式没有作答记录时（quiz.zs:1233），pick_level 回填 `科目等级.first`。
- 题卡抬头不用改。Python 迁移后会显示「入门・选择」。
- 开始（自由练）：level 不在本科目等级里，报 400「等级不在本科目里」。

### 3.2 导入校验
- /quiz/import：第 3 列不在本科目等级里，算坏题，整批 400「题库有坏题：第 N 行等级 X 不在本科目等级（入门/基础/进阶）里」，和现有坏题规则同一个口径。日语题库都是 N5–N1，不受影响。
- 追加题目（quiz.md:163）同样校验。
- 课文导入（lesson.zs:289、574 两处）、教材导入的四处校验、等级范围、approve_mapped.sql：都改成「在本科目等级里」。SQL 改成传入 `:levels` 串，用 `instr(',' || :levels || ',', ',' || level || ',') > 0` 判断。

### 3.3 知识点等级（lesson.取知识点等级）
- lesson_level_by_point.sql 改成返回相关课文的 **DISTINCT level 列表**，不再用 SUBSTR。服务按 `科目等级.levels` 的顺序取**最靠前**的那个，作为「最基础」等级。
- **兜底**：没有相关课文时，查该点下各条目所挂题目的等级（新增 `lesson_level_by_point_quiz.sql`：quiz_question JOIN kg_item ON point_code），同样取最靠前的。Python 科目的学情「各等级」靠这一条才能有数据。日语科目的知识点都有课文，结果不变。
- 返回结构 `{point_code, level, lesson_count}` 不变，所以 6 个调用方都不用改。

### 3.4 学情统计（progress）
- 按级统计掌握：把 5 组计数器换成按 `科目等级.levels` 遍历，每个等级累计 total 和 mastered，返回项数等于等级数，顺序就是科目等级的顺序。
- 进度页 levels 段（615-652）：同样按等级遍历累计答题数，删掉两组 5 段 if。
- 日语科目输出的 5 项、顺序和数值都不变。

### 3.5 教师助手出题（assist_draft）
- 出题提示词（603-614）里加一句「level 只能是：{本科目等级用、连接}」。
- quiz_add 落草稿时（390-409）：level 不在本科目等级里，当作空处理，依次回填知识点等级、`科目等级.first`，不再填 `-`。这样不报错，草稿照样能生成，「跨科目_校验草稿」这条用例的 ok 不受影响，只是落库的 level 值会变（见 1.9）。
- 教师助手的设置（assist_setting）不涉及等级。

### 3.6 问老师（tutor）
- 判意图提示词（tutor.zs:24）：「level（只能是 {本科目等级} 或空串）」。判意图需要多传一个 subject 参数。
- tutor.zs:36：用「在本科目等级里」代替正则。
- 去掉 tutor.md:33 的「subject_id≠1 一律取空」，改成「不在本科目等级里取空」。
- tutor.zs:252-254：「还没有学习记录，先从{first}开始」，链接 `level={first}`（中文等级名要 URL 编码）。

### 3.7 科目管理
- subject_view 页面实体加 `subj_levels 文本`（逗号串）；subject.ui 的编辑浮层加一个输入框，提示「从易到难，英文逗号分隔」。
- 载入科目页面回填它，保存科目页面接收它；新建时传给建科目，编辑时传给改科目。

### 3.8 不改的部分
默写和单词的 `[N4]` 词义前缀、init_data.py 的灌库正则、dictation_level 下拉。这些是日语词库的数据格式，通用科目没有词库。

## 4. 契约改动清单（需要用户批准，共 34 条）

| # | 契约:行 | 改前 | 改后 |
|---|---|---|---|
| S1 | subject.md:11 | levels…「空表示不分级」 | 「英文逗号分隔有序（从易到难）；空串视为 N5,N4,N3,N2,N1（兼容旧数据）；1–10 项，每项 1–12 字，不含 , \| ^ 和空白，不重复」 |
| S2 | subject.md:44-56 | subject_view 没有等级字段 | 新增 `subj_levels 文本 本科目等级，逗号分隔从易到难` |
| S3 | subject.md:167 | 建科目「levels 为空串」 | language 默认 `N5,N4,N3,N2,N1`，general 默认 `入门,基础,进阶`；传了 levels 就按 S1 校验，不过报 400「等级格式不对」 |
| S4 | subject.md:168 | insert subject_info … levels 写空串 | levels 写入 S3 的值（两条 insert sql 都改成 `:levels`） |
| S5 | subject.md（新增函数） | 无 | `公开 函数 科目等级 subject_id` → `{levels, first, options}`，按 2.1 的规则，含兼容规则 |
| S6 | subject.md:172-173 改科目 | 只能改 name、intro | 增加可选的 levels：校验同 S1；被删掉的等级如果还被题目、课文、草稿、做题进度引用，报 400「等级 X 还有 N 条在用」 |
| S7 | subject.md:325、334 载入/保存科目页面 | 不带 levels | 载入时回填 subj_levels；保存时接收 subj_levels，新建时传给建科目，编辑时传给改科目 |
| Q1 | quiz.md:8 | quiz_question.level「N5/N4/N3/N2/N1」 | 「本科目等级之一」 |
| Q2 | quiz.md:35 | `pick_level 枚举 全部,N5,N4,N3,N2,N1` | `pick_level 文本`，下拉选项来自 lists.level_options（「全部」加上本科目等级） |
| Q3 | quiz.md:134、137 导入题库 | 等级列不校验 | 等级为空或不在本科目等级里，算坏题，报 400「题库有坏题」，报错里带上行号和等级 |
| Q4 | quiz.md:163 追加题目 | 只判 level 非空 | 再加一条：不在本科目等级里报 400 |
| Q5 | quiz.md:218 开始（自由练） | level 为空报 400 | 再加一条：level 不在本科目等级里，报 400「等级不在本科目里」 |
| Q6 | quiz.md:340 开始页面/课文页面 | 「全部」按 N5,N4,N3,N2,N1 逐级找 | 「全部」按 `subject.科目等级.levels` 的顺序逐级找 |
| Q7 | quiz.md:400 复习、没有作答记录 | form.pick_level = N5 | form.pick_level = 科目等级.first |
| Q8 | quiz.md 开始页面、课文页面、出题、提交这些回整页的接口 | 不回等级选项 | 每次都在 lists 里回 level_options（引擎约定：进界面前端会先清空 lists） |
| P1 | progress.md:151 按级统计掌握 | levels 恒为 5 项，顺序 N5..N1 | levels 的项数等于本科目等级数，顺序就是科目等级的顺序 |
| P2 | progress.md:160 | 返回 5 项列表 | 返回按科目等级逐项的列表 |
| P3 | progress.md:257 取点级映射 | N5–N1 等级的映射 | 本科目等级的映射 |
| P4 | progress.md:278 进度页 | levels 五行 | 每个本科目等级一行 |
| L1 | lesson.md:15 | lesson_text.level「N5/N4/N3/N2/N1」 | 「本科目等级之一」 |
| L2 | lesson.md:148、159 取知识点等级 | 「N5 最基础…取等级数字最大的」 | 「在相关课文的等级里，取本科目等级顺序最靠前的；没有课文时，从该点条目所挂题目的等级里取最靠前的；都没有返回空串」。lesson_count 的口径不变 |
| L3 | lesson.md:181、208 课文导入校验 | level 必须是 N5..N1 之一 | level 必须在本科目等级里 |
| L4 | lesson.md:42 | `lesson_level 枚举 全部,N5..N1` | 文本，下拉选项来自 level_options（教材页的接口也回这个键） |
| R1 | report.md:52 取点等级 | 返回等级文本（N5 到 N1） | 返回本科目等级之一，取不到返回空串 |
| T1 | tutor.md:30-31 判意图 | level 只会是 N5..N1 或空；提示词不带等级清单 | 提示词里列出本科目等级；判意图多一个 subject 参数 |
| T2 | tutor.md:33 | level 不是 N5..N1 取空；subject_id≠1 一律取空 | level 不在本科目等级里取空（删掉科目 1 的特判） |
| T3 | tutor.md:86 | 「先从N5开始」，link level=N5 | 「先从{first}开始」，link level={first}（URL 编码） |
| A1 | assist_draft.md:85 quiz_add | level 为空取知识点等级，不校验 | level 不在本科目等级里当空；依次回填知识点等级、科目等级.first（不再填 `-`） |
| A2 | assist_draft.md:116 出题提示词 | 没写可选的等级值 | 写明「level 只能是：本科目等级」 |
| X1 | textbook_import.md:18、89 等级范围 | 「全部或 N5 到 N1」；报 400「等级范围只能是全部或 N5 到 N1」 | 「全部或本科目等级之一」；报 400「等级范围只能是全部或本科目等级」 |
| X2 | textbook_import.md:34、62 | 草稿 level「N5/N4..」；`draft_level 枚举 N5..N1` | 「本科目等级之一」；draft_level 改成文本，下拉选项来自 level_options |
| X3 | textbook_import.md:207、249 改草稿/审阅 | level 不是 N5..N1 报 400 | level 不在本科目等级里报 400 |
| X4 | textbook_import.md:264、539 批量通过/确认前检查 | level 是 N5..N1 之一 | level 在本科目等级里（approve_mapped.sql 传 :levels） |
| X5 | textbook_import.md:340 附近（实现在 textbook_import.zs:849、828-839） | 提示词「level（N5/N4/N3/N2/N1）」；N5..N1 才预筛 | 提示词列出本科目等级；等级范围在本科目等级里就预筛 |

新增用例（估计约 25 条）：subject 约 8 条（默认值、格式校验、删除在用等级、兼容空串）；quiz 约 7 条（Python 科目「全部」逐级、导入坏等级、开始时等级不在科目里、level_options 返回）；progress 3 条（3 级科目的统计）；lesson 3 条（题目兜底、自定义顺序取最靠前）；tutor 2 条；assist_draft 2 条。另外有 1 条现有用例的落库 level 需要复核（assist_draft.md 约 375 行）。

## 5. 已有数据迁移（Python 科目 2）
日语科目 1 不动（levels 已经是 N5,N4,N3,N2,N1）。

Python：先 `UPDATE subject_info SET levels='入门,基础,进阶' WHERE id=2`，再按下表改 99 道题的 level。改法有两种：
1. 改 /workspace/dslagent_exp/content/python_v1/quiz.txt 第 3 列，然后通过接口用 root 在科目 2 下 `/quiz/import` 重灌（推荐，和 K157 同一条路，导入时也会顺带验证新校验）；
2. 或者在备份后，用一条 UPDATE 按 item_code→point_code 映射直接改库。

科目 2 的 quiz_progress 那 1 行 level=N5，改成「入门」，或者直接删掉，让学生重新开一轮。

| 段 | 知识点（按 K157 的顺序） | 题数 |
|---|---|---|
| 入门（1–13） | env 环境与第一个程序、var 变量与赋值、num 数字类型、op 算术运算、str 字符串基础、strm 字符串方法、fstr f-string、io 输入输出、bool 布尔与比较、logic 逻辑运算、if 条件语句、while 循环、for 循环与 range | 38 |
| 基础（14–25） | list 列表、listop 列表常用操作、slice 切片、tuple 元组、dict 字典、set 集合、nest 嵌套数据、func 函数定义、param 函数参数、ret 返回值、scope 作用域、lambda 匿名函数 | 34 |
| 进阶（26–34） | module 模块与 import、exc 异常处理、file 文件读写、comp 列表推导式、builtin 常用内置函数、type 类型判断与 None、class 类与对象、method 方法与属性、inherit 继承 | 27 |

合计 99 题（逐点题数来自正式库只读查询）。可以讨论的点：`type 类型判断与 None` 也可以放进「基础」；`builtin 常用内置函数` 也可以提前到「基础」。现在按图谱学习顺序直接切段，好处是「全部」逐级出题的顺序和前置边的方向一致。

## 6. 引擎
**不需要改。** 动态下拉（选项来自）、列表遍历、字符串切分都是现成的能力。生成的 web/app.js 和 teacher.js 用 gen 重新生成就行，不用手改。唯一的约束是 tools/ui.py:386 的「每个接口都要回 lists 键」，这条在应用层（Q8）满足。

## 7. 实施计划

| 步 | 内容 | 模块 / 工具 | 风险 | 预估 |
|---|---|---|---|---|
| 0 | 用户批准第 4 节和第 8 节的决策；备份正式库 | — | — | $0 |
| 1 | 改契约：subject、quiz、progress、lesson、report、tutor、assist_draft（textbook_import 视决策 3）。补用例 | 手改 contracts/*.md | 新契约和现有用例冲突；先跑一遍 audit2 只读核对 | $0 |
| 2 | audit2 分模块核对契约和代码差距：subject、lesson、quiz、progress、tutor、assist_draft（可并行） | dslagent v3 audit2 | 低 | $3–5（K13 一次 $1.8；小模块约 $0.6） |
| 3a | subject：levels 读写、科目等级函数、默认值、改等级的校验；subject.ui 加输入框；4 条 sql | fix2 --modules subject | 「删除在用等级」的跨表计数 | $1–2 |
| 3b | lesson：取知识点等级加题目兜底、去掉 SUBSTR、导入校验（依赖 3a） | fix2 --modules lesson | 被 6 个模块共用，返回结构必须不变 | $1–2 |
| 3c | quiz：逐级、level_options、导入和开始的校验、pick_level 改动态（依赖 3a） | fix2 --modules quiz | 每个回整页的接口都要带 level_options，漏一个下拉就空了；quiz_run.js 依赖 select 的顺序 | $1.5–3 |
| 3d | progress：动态等级统计（依赖 3a、3b） | fix2 --modules progress | 日语 5 项的输出要逐字不变 | $1–2 |
| 3e | tutor + assist_draft：提示词、校验、兜底（依赖 3a、3b，两者可并行） | fix2 ×2 | assist_draft 输入大（约 180KB），参考 K134/K139 有空闲超时、要重跑的风险 | $2.5–5 |
| 3f | （可选）textbook_import：5 处校验、提示词、approve_mapped.sql | fix2 --modules textbook_import | 文件大、用例多 | $1.5–3 |
| 4 | gen 重新生成前端；全量回归（17–18 套）+ drafts/files/e2e；新加 Python 科目的 e2e：选「全部」先出入门题，题卡显示「入门・选择」 | verify | e2e 选择器依赖下拉位置 | $0（模型）|
| 5 | 迁移：备份 → subject_info.levels=入门,基础,进阶 → 重导 Python 题库（按第 5 节的映射）→ quiz_progress 处理 → 只读核对日语 5 张表计数不变 | 接口 + 只读校验 | 迁移之前、新代码上线之后，Python 科目 levels 还是空（按兼容规则当 N5–N1），旧题照样能出，不存在中间态断档 | $0 |
| 6 | 上线：合并分支、重启 8119（需要停服窗口）、学生实测日语和 Python 两个科目的做题、学情、问老师 | — | 重启要用户批准 | $0–0.1（1 次真模型实测）|

**合计：核心（不含 3f）$10–19，含 textbook_import $12–22。** 参考：M4-split 计划合计 $6.5–13（实际 $7.57）；K139 $8.71；K148 $3.67。fix2 的 cost-cap 会小幅超出，留 20% 余量。

## 8. 决策点（给用户；K161 已定：1 选 A，2 选「只许新增和调顺序」，3 选「不含教材导入 + 门控」）
1. **存在哪**：A 复用 subject_info.levels 逗号串，编码即名称（**推荐**）；B 新表 subject_level，code 和 label 分开（多 $2–4，好处是改显示名不用动题目）。
2. **改等级的规则**：只允许新增和调顺序，删除或改名在用的等级直接拒绝（**推荐**，简单安全）；或者提供「重命名等级」操作，在事务里批量更新题目、课文和进度（多约 $1–2）。
3. **范围**：这一轮只做做题、学情、问老师、教师助手、科目管理，加上 lesson 的取等级和导入校验（**推荐**）。教材导入（textbook_import）留在 N5–N1 不动，以后用到再做（省 $1.5–3）。默写和单词无论哪种方案都不动。
   **注意**：现在 textbook_import 没有按科目门控（textbook_import.zs:41 只对 subject_id=1 做前缀检查），所以选「不做教材导入」时要**补一道门**：创建导入任务时，本科目 caps.textbook_import 不为 1 就报 403「本科目没开教材导入」（textbook_import.md 加 1 条契约，服务加几行）。否则 Python 科目还能通过教材导入写进 N5–N1 的课文，取知识点等级时这些课会被漏掉。这样契约是 29+1=30 条，涉及文件约 31 个。

（Python 题的分段不单列为决策点，按第 5 节的推荐，即按学习顺序 13/12/9 切。用户有意见再调。）
