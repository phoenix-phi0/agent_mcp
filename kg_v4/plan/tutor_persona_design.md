# K163 问老师人设按科目切换 + 科目说明不丢：设计与契约改动

> 状态：**K163 实施**（用户已批准「接着修」，按任务书默认方案做，没有改引擎）。
> 依据：kg_K162.md「发现的问题」1、3；kg_K161.md「已知问题」subj_intro。

## 1. 问题
1. 科目管理表格行不带 `subj_intro`。引擎从表格行点「编辑」时直接拿这一行填表单、不发「载入」（templates/frontend/app.js.j2，K161 定位），所以说明框是空的，直接保存会把科目说明清空。
2. Python 科目里问老师，回复讲的是 Python，开头却说「这个问题和日语语法无关」、结尾引导学日语：问老师的系统提示词把老师写死成日语老师。

## 2. 盘点（改前，文件:行号）

### 2.1 tutor（services/tutor.zs，本次改）
| 位置 | 用途 | 写死的内容 | 处理 |
|---|---|---|---|
| tutor.zs:25 判意图（问JSON） | 意图分类、抽关键词 | 「explain 表示问**语法讲解**或其他一切」「学生指名的**语法点**或课文关键词」 | 按科目取 explain_word / point_word；日语逐字不变 |
| tutor.zs:198 答一轮（系统提示） | 进度、教材、讲解三条路共用 | 「你是一位中文老师，教中文学习者**日语语法**，回答简明」；「学生闲聊、与**日语学习**无关时……不要强行讲**语法**」 | 按科目取 persona / offtopic；日语逐字不变 |
| tutor.zs:557 总结本轮 | 一轮做题后的总结 | 「你是一位中文老师，教中文学习者**日语语法**。」 | 按科目取 persona；日语逐字不变 |
| tutor.zs:345 教材目录 | 科目 1 带等级、其他科目不带 | 已按科目分支（K131） | 不改 |
| tutor.zs:241–273 出题模板回复 | 模板文案 | 等级已按 subject.科目等级（K161），「请在做题页自己选等级和考点」通用 | 不改 |
| 问候 / 拒答 / 兜底 | tutor 没有单独的问候、拒答文案；兜底只有「老师暂时无法回答」（通用） | — | 不改 |
| tutor.zs:19、22 注释 | 旧口径注释 | 「level 只会是 N5…」 | 随 fix2 重写，非行为 |

JLPT：kg_v4 的 services 里没有「JLPT」字样。

### 2.2 subject_ai（本次启用 persona 一列）
- 表在 K94 时只建表（entities/subject.entity:38–48、contracts/subject.md:32–41），列：subject_id（唯一）、persona、tutor_prompt、assist_prompt、summary_prompt、import_prompt、kg_gen_prompt、updated_by、updated_at。
- 改前没有任何代码读写它（grep 只有实体、契约、setup/migrate_subject.py 的跳过回填清单）；正式库 0 行。
- **结构合适，直接复用 `persona` 列存「AI 老师设定」**，不加字段、不改表结构；其余 *_prompt 列仍不启用。

### 2.3 教师助手等（只盘点，没改）
| 位置 | 写死的内容 | 是否与问老师共用 |
|---|---|---|
| teacher_assist.zs:528 判意图 | 「你是**日语**学习系统里教师端助手的意图分类器」 | 否（教师端独立提示词） |
| teacher_assist.zs:679 答一轮 | 「你是**日语**学习系统教师端的教学助手」 | 否 |
| textbook_import.zs:856/858 | 「你是**日语**教材整理助手」「title只写**语法点**的名称」，等级 N5–N1 | 否；非日语科目已被 K161 门控挡住 |
| assist_draft.zs:604、assist_material.zs:277、report.zs:395 | 通用措辞（教师助手 / 学情总结） | 否 |
| dictation.zs、vocab | 「看中文写日语」等日语词库专用 | 否，日语专用功能 |

结论：教师端的「日语学习系统」两处与问老师不共用提示词，本任务不改，建议以后按同一个 `科目老师设定` 思路另开任务（可用 subject_ai.assist_prompt）。

## 3. 方案

### 3.1 新函数 `subject.科目老师设定 subject_id`（叶子模块，只读）
返回 `{name, custom, persona, offtopic, point_word, explain_word}`：
- **日语口径**：subject_id = 1，或查不到 subject_info 行（旧库、模块用例库，行为同旧）。
- `custom` = subject_ai.persona 去首尾空白（没有行为空串）。
- `persona`：custom 不空 → custom 去掉末尾句末标点；否则日语口径「你是一位中文老师，教中文学习者日语语法」；否则「你是一位{科目名}老师，用中文给学生讲解{科目名}」。
- `offtopic`：日语口径「学生闲聊、与日语学习无关时，简短自然地回应，不要强行讲语法」；否则「学生闲聊、与{科目名}无关时，简短自然地回应，不要硬拉回{科目名}；学生问的是别的科目的内容时，不要拒答，简短回答要点，并提醒可以在顶栏切换到对应科目再细问」。这就是「跑题按本科目判断、问别的科目不硬拒」。
- `point_word` 语法点 / 知识点；`explain_word` 语法讲解 / 讲解。
- 非日语口径生成的文字里除科目名外不出现「日语」「语法」「JLPT」。

放在 subject 而不是 tutor：subject 是叶子模块、本来就管 subject_ai；以后教师助手要按科目换人设也调它。函数是纯计算，人设文本在 subject 模块用例里能逐字断言（tutor 的模块用例用假模型，断言不了提示词）。

### 3.2 tutor 的拼法
- 答一轮：`{persona}，回答简明。回答格式与口吻要求：……；{offtopic}；不要说……`
- 总结本轮：`{persona}。请为学生写一段……`
- 判意图：`explain 表示问{explain_word}或其他一切 … 学生指名的{point_word}或课文关键词`
- 日语科目三处拼出来与改前**逐字一致**（tests/kg_v4/test_tutor_persona.py 用假模型截下提示词，和改前原文逐字比对）。唯一例外是判意图的等级清单：改前代码写「只能是 N5,N4,N3,N2,N1 其中之一，逗号分隔，或空串」，K161 契约本来就要求「本科目等级用空格连接」，这次 fix2 照契约写成「只能是 N5 N4 N3 N2 N1 或空串」，意思相同（语义等价），测试里单独核对这半句。

### 3.3 科目管理
- 页面字段 `subj_persona`（长文本），编辑浮层加多行框「AI老师设定」，提示留空按科目名自动生成。
- 表格行补 `subj_intro`、`subj_persona`（两条行查询 LEFT JOIN subject_ai），载入科目页面 也回填 `subj_persona`。
- 保存科目页面 收 `subj_persona`：先校验 ≤2000 字（超了什么都不写）；新建在 建科目 之后、编辑在 改科目 之后调私有函数 `存科目人设`：与库里现值相同不写（不改设定不会多出 subject_ai 行），否则 upsert（只动 persona、updated_by、updated_at）。留空 = 清掉自定义、回到默认。
- 权限：沿用 改科目 / 编辑按钮的规则——只有负责人（单人模式不校验）能改；协作、公共只读教师 403。
- 说明框标签原来写「会进AI老师的人设」，实际从来没有进；改成「说明（可空）」，人设单独在「AI老师设定」里写。

## 4. 契约改动（共 18 条）
| # | 契约 | 改动 |
|---|---|---|
| S1 | subject.md 表 subject_ai.persona | 说明改为「AI 老师设定……空时按科目名生成默认」 |
| S2 | subject.md 页面字段 | 新增 subj_persona |
| S3 | subject.md 新函数 | 公开 函数 科目老师设定 |
| S4 | subject.md 新函数 | 私有 函数 存科目人设 |
| S5 | subject.md 科目管理页面 返回 | 行字段补 subj_intro、subj_persona（说明为什么要在行里） |
| S6 | subject.md 科目管理页面 伪代码 | subj_intro、subj_persona 的取法，两条行查询 LEFT JOIN subject_ai |
| S7 | subject.md 载入科目页面 返回 | 加 subj_persona |
| S8 | subject.md 载入科目页面 新建空表单 | 加 subj_persona 空串 |
| S9 | subject.md 载入科目页面 编辑 | 回填 subj_persona |
| S10 | subject.md 保存科目页面 入参 | 加 subj_persona? |
| S11 | subject.md 保存科目页面 报错 | 加 400 AI老师设定最长2000字，先于写库检查 |
| S12 | subject.md 保存科目页面 新建 | 建科目 后 存科目人设 |
| S13 | subject.md 保存科目页面 编辑 | 改科目 后 存科目人设（负责人才能改） |
| T1 | tutor.md 判意图 | 称呼按科目取 point_word / explain_word |
| T2 | tutor.md 答一轮 | 新增「人设按科目取」一条 |
| T3 | tutor.md 答一轮 系统提示 | persona +「，回答简明。」；③ 换成 offtopic |
| T4 | tutor.md 总结本轮 | 提示词以 persona +「。」开头 |
| T5 | tutor.md 8 个公开函数的「科目」伪代码 | 「提示词不按科目换」→「老师人设和措辞按科目取（日语科目与旧提示词逐字一致）」 |

另：plan/top.zs subject 提供 加 科目老师设定；entities/subject.entity、ui/subject.ui 手改（惯例）。

新增用例：subject 15 条（科目老师设定 5、行字段 1、从行原样保存说明不丢 1、载入回填 2、保存设定 6）；tutor 3 条（通用科目问老师、自定义设定问老师、通用科目总结本轮）。

## 5. 不做 / 以后
- 教师助手（teacher_assist）的「日语学习系统」提示词：不共用，另开任务。
- subject_ai 其余 *_prompt 列不启用。
- 科目说明（intro）不自动拼进人设：要进人设就写在「AI老师设定」里。
- 没有表结构变化，上线不用 ensure_db。
