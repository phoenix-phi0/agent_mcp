# K164 教师助手提示词按科目切换：设计与契约改动

> 状态：**K164 实施**（用户已批准「继续」，按任务书默认方案做，没有改引擎、没有加界面字段）。
> 依据：kg_K163.md「已知问题」5；K163 的问老师人设设计见 tutor_persona_design.md。

## 1. 问题
教师助手的提示词写死「日语学习系统」：Python 科目里老师问助手，助手自称日语学习系统的教学助手，判意图时把知识点叫「语法条目」，加知识点草稿里写「非日语科目必须以它开头」，讲义要求【例句】。

## 2. 盘点（改前 HEAD babbcc7，文件:行号）

| 位置 | 用途 | 写死的内容 | 处理 |
|---|---|---|---|
| teacher_assist.zs:528 判意图 | 意图分类（问JSON 快档） | 「你是**日语**学习系统里教师端助手的意图分类器」「问某个知识点或**语法**条目全班的掌握情况」「说这个**语法**、这个点时」 | 按科目取 system / point_desc / this_point |
| teacher_assist.zs:679 答一轮 | 教学助手系统提示 | 「你是**日语**学习系统教师端的教学助手」 | 按科目取 intro（assist_prompt 可覆盖） |
| assist_draft.zs:776 生成草稿 kg_add | 加知识点草稿提示词 | 「编号前缀（非**日语**科目必须以它开头）」 | 按科目取 prefix_note |
| assist_material.zs:272 生成材料 handout | 讲义要求 | 「【要点】【**例句**】【易错点】【小练习】」 | 按科目取 example_tag（语言类【例句】，其它【示例】） |
| assist_draft.zs:604、642 | 草稿系统提示、出题等级 | 通用；等级 K161 已按 科目等级 取 | 不改 |
| assist_material.zs:277 | 材料系统提示 | 通用 | 不改 |
| report.zs:395 写学情总结 | 学情总结提示词 | 通用；数据里的「错词本」是日语默写功能的数据，非日语科目为空 | 不改 |
| report.zs:947/949 | 学生学情页错词本方向 | 「看汉字写读音」「看中文写日语」（日语默写专用） | 不改 |
| teacher_assist.zs:520 | 系统功能说明 | 通用 | 不改 |
| assist_common、assist_setting、assist_kg、assist_file、assist_insight | — | 无 | — |
| textbook_import.zs:856/858 等 | 「你是**日语**教材整理助手」「title只写**语法点**的名称」、N5–N1 校验 | K161 已门控，非日语科目进不来 | 只盘点 |

JLPT：教师侧 services 里没有「JLPT」字样。

## 3. 方案

### 3.1 新函数 `subject.科目助手设定 subject_id`（叶子模块，只读）
返回 `{name, kind, levels, custom, system, intro, point_desc, this_point, prefix_note, example_tag}`。

| 字段 | 日语口径（科目 1，或查不到 subject_info 行） | 其它科目 |
|---|---|---|
| name | 行的 name，没有行取「日语语法」 | 行的 name |
| kind | 行的 kind，没有行取 language | 行的 kind |
| levels | 科目等级 各项用「、」连接（N5、N4、N3、N2、N1） | 同（如 入门、基础、进阶） |
| custom | subject_ai.assist_prompt 去首尾空白 | 同 |
| system | 日语学习系统 | {name}学习系统 |
| intro | custom 不空：custom 去句末标点；否则「你是日语学习系统教师端的教学助手」 | custom 不空同左；否则「你是{system}教师端的教学助手」 |
| point_desc | 知识点或语法条目 | 知识点或条目 |
| this_point | 这个语法、这个点 | 这个知识点、这个点 |
| prefix_note | 编号前缀（非日语科目必须以它开头） | 编号前缀（本科目的编号必须以它开头） |
| example_tag | 【例句】 | kind=language 为【例句】，否则【示例】 |

- 非日语口径生成的文字里除科目名外不出现「日语」「语法」「JLPT」。
- 新查询 `subject_ai_assist_prompt`；levels 调本模块 科目等级。
- 不复用 科目老师设定：那是给学生的「老师」人设（persona、offtopic），教师助手是对老师说话的「同事」，措辞和用途都不同；两个函数各管一侧，日语口径的判定规则相同。

### 3.2 subject_ai.assist_prompt：可选覆盖，界面不暴露
- 去首尾空白后不为空时，替换答一轮开头的自我介绍（intro），后面的回答规则①…⑪照旧拼上（规则管的是数据可信、不改数据，不能被覆盖掉）。为空、NULL、没有行时用默认。
- 本轮不加页面字段、不改 UI；要改只能直接写库。
- **是否复用「AI老师设定」（subject_ai.persona）——判断：不复用，不实施，留给用户决定**。理由：persona 是问老师（学生端）的人设，内容是「你是一位…老师，用中文给学生讲解…」，直接拿来当教师助手的开头会让助手对老师用对学生的口吻说话；而且负责人在科目管理里改 AI 老师设定时，预期只影响学生端。若用户希望老师在界面上能改教师助手的开头，建议以后在科目管理编辑浮层另加「教师助手设定」多行框，写 assist_prompt（≤2000 字，规则同 subj_persona）。

### 3.3 调用方的拼法（日语科目逐字不变）
- teacher_assist.判意图（新增可选入参 subject_id，问助手 传入）：`你是{system}里教师端助手的意图分类器。…point_status（问某个{point_desc}全班的掌握情况）…说{this_point}时，point填上一轮聚焦的知识点标题…`
- teacher_assist.答一轮：`{intro}，像同事一样和老师说话，只读。回答规则：①…`（规则原文不变）
- assist_draft.生成草稿 kg_add：`任务：往图谱里加知识点、条目、前置边。{prefix_note}：{prefix}；编号只能用…`
- assist_material.生成材料 handout：`要求：讲义包含【要点】{example_tag}【易错点】【小练习】。`
- 出题（quiz_add）的等级已按 科目等级（K161），出题提示词本来就没有日语字样，不改。

## 4. 契约改动（共 14 条）
| # | 契约 | 改动 |
|---|---|---|
| S1 | subject.md 表 subject_ai.persona | 「本表其余 *_prompt 列仍未启用」→「除 persona、assist_prompt 外」 |
| S2 | subject.md 表 subject_ai.assist_prompt | 说明改为「教师助手的自我介绍覆盖（可选，界面不暴露）…」 |
| S3 | subject.md 新函数 | 公开 函数 科目助手设定（返回、取数、日语口径、各字段规则、只读） |
| S4 | subject.md 新用例 | 科目助手设定 6 条：日语与旧提示词一致、没有科目行按日语、通用科目按科目名生成、语言类科目讲义仍用例句、自定义开头优先并去句末标点、只有老师人设时教师助手用默认 |
| S5 | subject.md 科目老师设定 取数 | 查询 subject_ai_persona 改为 `COALESCE(persona, '')`（见下「NULL 陷阱」） |
| S6 | subject.md 新用例 | 科目老师设定_只有助手设定时老师人设用默认 |
| T1 | teacher_assist.md 判意图 入参 | 加 subject_id? |
| T2 | teacher_assist.md 判意图 | 新增「措辞按科目取」一条（system / point_desc / this_point，日语逐字一致） |
| T3 | teacher_assist.md 判意图 问JSON | 「这个语法」→「这个知识点（日语科目说这个语法）」 |
| T4 | teacher_assist.md 问助手 | 调用 判意图 带 subject_id |
| T5 | teacher_assist.md 答一轮 | 新增「人设按科目取」一条（intro +「，像同事一样和老师说话，只读。回答规则：」） |
| T6 | teacher_assist.md 答一轮 | 系统提示的助手人设注明取 ap.intro |
| D1 | assist_draft.md 生成草稿 提示词 | kg_add 编号前缀那句按 prefix_note |
| M1 | assist_material.md 生成材料 系统提示 | 讲义的例子小节按 example_tag |

另：plan/top.zs subject 的「提供」加 科目助手设定（说明里加一句）。

**NULL 陷阱（第一次 fix2 失败的原因）**：subject_ai 有这一行但某列为 NULL 时，`查一值` 取到的 NULL 会变成文本 `None`，`{raw 或}` 兜不住。只存过老师人设的行 assist_prompt 是 NULL，教师助手会自称「None」；反过来，只写了 assist_prompt 的行 persona 是 NULL，K163 的 科目老师设定 也会把问老师的人设拼成「None」（K164 新加的用例在改前代码上确实报 custom='None'）。两条查询都在 SQL 里 COALESCE。没有表结构变化（assist_prompt 列 K94 就有），上线不用 ensure_db。

## 5. 测试
- tests/kg_v4/test_assist_persona.py（加进 run_all「教师助手人设」组）：假模型截提示词。GOLDEN（tests/kg_v4/assist_persona_golden.json）是在改前代码上 `--record` 截下的日语科目四处提示词全文；改后日语四处逐字一致；Python 科目四处不含「日语」「语法」「JLPT」，自称「Python 编程学习系统」，加知识点草稿前缀说明不提日语，讲义用【示例】；assist_prompt 覆盖只换开头、不影响日语科目、只有空白时用默认。
- 约定用例：subject 新增 7 条（科目助手设定 6、科目老师设定 NULL 1）。

## 6. 不做 / 以后
- assist_prompt 不在界面暴露（见 3.2，待用户决定）。
- textbook_import 的日语教材整理提示词：K161 已门控，不改。
- report 学生学情页错词本方向文案（看中文写日语）：日语默写专用功能，不改。
- 教师端界面提示里的日语示例（静态文案，不能按科目切换）：ui/teacher_assist.ui:76 输入框提示「按〜たばかり出5道题…写一份〜たばかり的教案」、ui/teacher_material.ui:31 空态「写一份〜たばかり的教案」、ui/teacher_note.ui:29/59/113 与 ui/report.ui:175（AI 老师设定的例子「て形」「ばかり,たばかり」）。本轮不改；若要改，只能换成不分科目的中性例子（会同时改变日语科目的界面），留给用户决定。
- teacher_rules 的 AI 老师设定预览版式「你是一位耐心的日语老师……」（queries/teacher_rules_preview_layout.sql）：学生端设定预览，不在本任务的教师助手范围，建议另开任务。
