# kg_v4 日语界面（多语言）设计（K179）

状态：设计稿，未实施、未提交。调研基于 origin/master（2026-11-01），正式库为 /workspace/dslagent_exp/kg_v4_data/app.db，只读快照于 2026-11-01 用 sqlite backup API 拷到 /tmp/k179 统计，用完已删（/tmp/k179 现已不存在）。

## 决策点定稿（K180 实施，2026-11-01）

- **D1（定稿，K180 第 1 期已实施）**：项目里有 `i18n/<lang>.tsv` 即启用；中文原文作键，前端对界面文字做 DOM 整串替换（tdom + MutationObserver 兜底）、后端消息整串查表（tmsg），查不到回退中文；语言记在 `account_user.lang`（auth_me 返回，顶栏「中文 / 日本語」切换调 POST /account/lang 后整页刷新），未登录记浏览器 localStorage（键 zs_i18n，默认中文）；状态枚举值、路由键不翻。
- **D2（定稿，第 2 期）**：AI 回答语言跟随界面语言——问老师/教师助手的提示词按 me.lang 注入「用日语回答」，另加假模型固定日语回复的 GOLDEN_JA 回归。
- **D3（定稿，第 3 期）**：科目内容（知识点、条目、题目、讲解、单词释义，共约 16.7 万字）只翻 Python 科目，建 `subject_content_translation` 翻译表（中文原文为键）分批导入，不动现有表和内容行，读取时按 lang 替换。

## 0. 用户决定（范围）

每个用户自己选界面语言，顶栏「中文 / 日本語」切换，记在账号上；默认中文，现有用户行为不变。跟随切换：① 界面文字；② 后端提示和报错；③ AI 老师和教师助手的回答语言；④ 科目内容（知识点、条目、题目、讲解、单词释义等）。

## 1. 待翻译文字盘点

### 1a. 引擎模板写死中文 —— 87 处（独立 66 条，产品侧）

「产品侧」= 会出现在 kg_v4 页面上的；生成器 CLI/编辑器等工具侧约 151 处不计（用户不直接看）。

| 来源 | 处数 | 例子（文件:行） |
|---|---|---|
| templates/frontend/app.js.j2 | 29 | :1379「退出登录」、:1413「改密码」、:1415「退出」、:345 请求超时提示、:549/562/565 端跳转提示、:616–618 无权限提示、:1276–1282 节点图「学习中 N%/已掌握/可学」 |
| templates/frontend/widgets.j2 | 3 | :72,:77「请选择」、:192「次工具调用」 |
| gen/templates/_base/screens.ui.j2 | 10 | :35「刷新」、:54「保存」、:56「删除」 |
| gen/templates/default/screens.ui.j2 | 11 | 「编辑」「返回」等 |
| gen/templates/*/routes.zs.j2 | 13 | 「没有这条记录」「已保存」「已删除」等回包文字 |
| gen/templates/private/project/auth.ui.j2 + auth.zs.j2 | 16 | 「登录」「注册」「用户名或密码不对」「不开放自助注册」 |
| gen/project.py | 5 | :521「{end}端」徽标、:524「退出并打开{main_end}端」（K177 声明分支）、:526「打开{main_end}端」 |

关键核实：任务书点名的顶栏「退出」「改密码」在 app.js.j2:1413/1415（另有 nav 分支「退出登录」:1379）；「退出并打开学生端」不在模板里，由 gen/project.py:524 按 K177 的 switch_logout 声明生成。登录页文字在 gen/templates/private/project/auth.ui.j2（kg_v4 用自己的 ui/auth.ui，见 1b）。引擎里没有通用「确定要删除吗」确认框（删除按钮无确认），也没有「加载中/暂无数据」类空态文字。

### 1b. kg_v4 .ui 界面文字 —— 逐元素盘点 607 处（独立约 450 条）

口径：探针逐元素手工盘点，一个按钮/标签/列头/文案=一处，共 607 处；机械可复核口径（rg 统计）：带中文的行 1,467 行（一行可含多处文字），「文案|按钮|列|链接|标签|提示|显示|界面|动作」文字载体行 390 行，量级一致。

15 个 .ui 全部有中文。大项：report.ui 106、teacher_note.ui 83、textbook_import.ui 87、kg_manage.ui 80、subject.ui 62、teacher_assist.ui 34、teacher_material.ui 24、quiz.ui 22、progress.ui 22、node.ui 18、textbook.ui 20、student.ui 17、quiz_dictation.ui 16、auth.ui 10、teacher.ui 6。例子：auth.ui:14「请用老师给你的账号登录。」、progress.ui:33「还没有作答记录，去做题页做几道，这里就有进度了。」、textbook.ui:54「没有符合的课文，换个等级或关键字试试。」

编译链（中文在编译时写进生成物）：gen/project.py build → tools/ui.py compile_ui(:1585) → render_vue(:1305) → tools/render.py frontend_renderer(:301，模板目录 templates/frontend/) → widgets.j2 里 `<%= f.label %>`、`<%= a.label or a.name %>` 直接输出。引擎目前没有任何 i18n 机制（tools/ui.py:50–52 注释说明 DSL 关键字与节点类型值保留中文、不额外做翻译查表）。

风险点（已核实 8 处）：「当」条件直接比较后端返回的中文状态值，如 subject.ui:67 `row.subj_status!=='启用'`、student.ui:34 `==='正常'`、quiz.ui:88 `shared.qtype==='选择'` 等。界面翻译不能动这些数据值。

### 1c. 后端消息 —— 584 处

services 里非注释 `报错 <码> <中文>` 539 处（复核口径 `报错 \d+ .*[一-龥]`，TOTAL 539；若放宽为所有非注释 `报错` 开头行则 549，其中 10 行不带状态码或非中文消息，不按可翻文案计）+ routes 成功提示（`消息 系统`）45 处。大项：kg.zs 107、subject.zs 62、textbook_import.zs 58、quiz.zs 45、teacher_rules.zs 45、lesson.zs 41、account.zs 28、assist_draft.zs 27。例子：services/account.zs:105「用户名或密码错误」、routes/account.zs:30「密码改好了，下次用新密码登录」、routes/kg.zs:188「知识点已保存」、progress.zs:219「还没有作答，先去做题吧」。

引擎层（tools/db_errors.py:87–103）约束翻译 6 条：「{字段}已经存在，换一个」「{字段}不能为空」「关联的记录不存在…」「数据不符合要求」「数据冲突：{msg}」；字段中文名取自实体标签，日语化需补字段名来源。另：services/account.zs:191–196 role_label 硬编码「教师」「学生」（auth_me 返回的界面文字，归入消息类一并处理）。

### 1d. 提示词里决定回答语言的部分 —— 显式 2 处，相关提示词段 25–35 处

- services/subject.zs:689（非日语科目默认人设）「你是一位{nm}老师，**用中文**给学生讲解{nm}」——唯一的显式讲解语言指示。
- services/subject.zs:687（日语科目默认人设）「你是一位**中文**老师，教中文学习者日语语法」——隐含中文讲解。
- services/report.zs:395「写一段简明的学情总结（**中文**，不超过300字）」。
- tutor.zs:208 的系统提示词无显式语言指示，语言完全继承 persona；教师助手各脚本（teacher_assist/assist_draft/assist_material/assist_insight）也无语言指示，默认随输入中文。
- subject_ai 表当前 0 行：人设 = 代码默认（subject.zs:687/689）+ 教师存库覆盖（persona 列），init_data.py 不初始化。

### 1e. 科目内容 —— 需翻译 9,203 行 / 约 16.7 万字

正式库快照统计（/workspace/dslagent_exp/kg_v4_data/app.db）：

| 表 | 行数 | 需翻译列与字数 |
|---|---|---|
| vocab_word | 8,105 | meaning 72,870 字 |
| quiz_question | 565 | stem 25,404 + options 13,069 + explain 31,901 + category 1,152（约 7.1 万字；answer 是选项字母/日语答案、course 是课号代码，不算） |
| lesson_text | 125 | title+summary+explain+connection 20,471 字（examples/orig_title 是日语原文，不算） |
| kg_item | 302 | name 1,566 字（after_form 是日语词形，不算） |
| kg_point | 103 | title 449 字 |
| subject_info | 2 | name 13 字 |
| lesson_series | 1 | 59 字 |
| 合计 | 9,203 | 166,954 ≈ 16.7 万字 |

不翻译的日语原文：lesson_text.examples 16,304 + orig_title 2,462 字、vocab_word.kanji/kana（约 4.5 万字）、kg_item.after_form。quiz_question.options 里挖空/接续题选项本身常是日语词，实际翻译量略小于上表。另有教师自建内容（teacher_rules_setting/relay、assist 材料）当前 0 行，暂不计。

## 2. 方案设计

总原则（参照 K177）：中文原文作键；日语缺失一律回退中文；引擎改动全部做成「可选声明/可选文件」，无声明的项目生成物逐字节不变；默认语言 zh 的运行行为与现在完全一致。

### 2.1 引擎层 i18n 机制（需用户批准）——推荐：编译期可选启用 + 前端 DOM 词典替换

启用条件：项目 `ui/` 同级存在 `i18n/ja.tsv`（tab 分两列：中文原文 → 日语）。存在即启用，不新增 DSL 语法。

引擎改动面（diff 草案级别）：
1. gen/project.py page_options 增加 i18n 探测：读 i18n/*.tsv 得 `langs`、把词条 JSON 传进模板上下文；默认（无目录）False。
2. 编译时新增产物 `web/i18n.<lang>.js`：`window.I18N={"中文原文":"日语…",…}`（按语言一份，有声明才生成）。
3. templates/frontend/index.html.j2：`{% if page.i18n_langs %}` 追加一行 `<script src="i18n.ja.js"></script>`，`<html lang>` 随语言（无声明不加，保证逐字节不变）。
4. templates/frontend/app.js.j2：`{% if page.i18n_langs %}` 内加约 60–80 行：`tdom()` 遍历文本节点与 placeholder/title/value 属性做整串查表替换；路由切换后与 MutationObserver 兜底重跑；顶栏渲染「中文 / 日本語」切换按钮（调 2.2 的接口，成功后 reload）。中文原文作键只替换显示文本，不碰 `s.name`/`go('学情')` 等路由键与 JS 逻辑字符串——顶栏导航、401 跳转、「登录/改密码」界面名这些耦合点天然不受影响。
5. style.css.j2 字体栈补日文字体（有声明时）。

无声明保证：全部包在 Jinja 分支里，page_options 默认 False；验收 = 对 kg/、app2/ 等无 i18n/ 项目 build 前后产物 sha256 逐一相同 + tests/gen 钉行（照 K177 test_ends.py 的手法）。

为什么不在编译期把 .ui 文字抽成键或直接输出日语：450+66 条文字散在 15 个 .ui 与 6 个模板里，键化要动 DSL 与全部模板（改动大、易错），且界面名同时是路由键（tools/ui.py:50–52、app.js.j2:155/157），键化必须把「路由名/显示名」拆两套，风险高。DOM 替换把翻译完全放在词典文件里，DSL、.ui、生成物（中文版）都不变。

备选 B：完整键化 i18n（.ui 加 `文案 键=…` 可选语法、模板抽键、编译期按语言出全套产物）。彻底、无替换闪烁，但引擎改动大、周期长，建议作为后续演进，不作为第一期。

已知代价与风险：切到日语的瞬间先渲染中文再替换（一次性闪烁，可在 app 启动前先替换首屏缓解）；替换的是 Vue 管理的文本节点，组件重渲染（vdom patch）可能覆盖替换结果——靠 MutationObserver 兜底重跑缓解，需限定触发频率防抖；词典整串匹配，.ui 改文案后日语缺失自动回退中文（无害）。第 1 期实现后用 e2e 实测确认无闪烁循环。

### 2.2 用户语言

- account_user 加列：`ALTER TABLE account_user ADD COLUMN lang TEXT NOT NULL DEFAULT 'zh'`（无迁移机制，kg_v4/scripts 手写迁移脚本，照 migrate_subject.py 模式；不重建表，学习记录不受影响）。
- auth_me（services/account.zs:164–198）返回键加 `lang`（读库 COALESCE(lang,'zh')；未登录返回 'zh'，前端可另用 localStorage 记住未登录时的选择）。
- 新接口 `POST /account/lang`（routes/account.zs + services/account.zs 各加一函数）：写当前用户 lang，仅允许 zh/ja。
- 顶栏切换按钮（引擎模板 2.1-4）：点「日本語」→ 调接口 → reload；zh 路径完全不变。

### 2.3 后端消息按语言输出——推荐：前端词典替换（后端零改动）

后端 584 处消息不改一个字。前端 applyResponse 在显示 error/messages 前，对整串文本查同一份词典（词典分 ui 段与 msg 段；db_errors.py 的 6 条约束消息和高频消息手工收录）。第 1 期 msg 段只收录高频 30–50 条（登录/保存/删除/权限/约束冲突类），其余消息按原文中文显示，后续按使用反馈补录——即「机制一次到位、覆盖逐步补全」，不是 584 处一次全翻。带插值的拼接消息（如「知识点或条目已被引用，不能撤销（{reasons}）」）整串匹配不到时回退中文显示——约定：新增消息尽量整句、少插值。

风险与约束：词典只翻「提示性文本」，**不翻状态枚举值**（「启用/停用/正常/通过/待确认」等出现在行数据里、被「当」条件比较的值）；这类值的日语显示由 DOM 替换层处理，数据层始终中文，8 处已核实的比较不受影响。

备选：消息代码化（`报错 409 @dup_title` + 前端按码翻）——最干净但要改 584 处 .zs 和用例断言，工作量数倍，不推荐第一期。

对用例的影响：接口层用例断言的中文消息不变（后端没改，照旧通过）；e2e 若断言日语界面上的消息文字，用日语词条。

### 2.4 AI 回答语言（第 2 期）

按 auth_me 的 lang 在提示词里指定回答语言；**zh 路径一个字都不改**（现有 GOLDEN 逐字不变），ja 才加指示：
- subject.zs:687/689 默认人设：lang=ja 时改用日语版默认人设（等价句），或统一在 persona 末尾拼「必ず日本語で回答してください」。
- tutor.zs:208 sysp、report.zs:395（「中文，不超过300字」→「日本語で、300字以内」）、teacher_assist/assist_material 的学生或教师可见输出处同样按 lang 追加指示；新增 GOLDEN_JA_* 钉住日语版提示词。
- 教师端助手默认仍中文（教师自选语言后再翻），提示词段 25–35 处中第 2 期只需动学生可见的 4–6 处。

日语科目 + 日语界面是否「用日语讲日语语法」：**建议跟随界面语言，但保留中文术语辅助**——即 lang=ja 时用日语讲解、例句继续给假名注音、关键语法术语首次出现可括注中文（写进 ja 版默认人设）；教师可在科目设定里自定义人设覆盖。理由：会把界面切到日语的用户，默认已具备日语阅读能力；内容库的中文讲解（lesson_text.explain）在 ja 界面下 AI 不直接照念，允许其用日语重组。备选：锁死中文讲解（把「面向中文学习者的日语课」视为产品定位，与界面语言解耦），实现更简单，等用户拍板。

### 2.5 科目内容多语言（第 3 期）——推荐：通用翻译表

三选一：
- **a. 通用翻译表（推荐）**：新表 `subject_content_translation(id, subject_id, tbl, row_id, field, lang, text, updated_at)`，唯一索引 (tbl,row_id,field,lang)。不动现有内容表、无需逐表 ALTER；查询不到回退原文=天然满足「缺日语回退中文」；读路径在 services 出口加一个统一函数（按 lang 查翻译表替换对应字段），或按需给热点查询加 LEFT JOIN 版查询。导入导出：导出加 `--lang ja`（tsv：tbl,row_id,field,text），导入走同表 upsert；textbook_import 产出的新内容暂不自动翻译，走人工/批量流程补。
- b. 各表加 _ja 列：查询最简单（COALESCE(stem_ja, stem)），但要 ALTER 7 张表、改导入导出与 40+ 个查询，列膨胀。
- c. 按语言分科目（jp_grammar_ja）：数据翻倍、学习记录不共享，不推荐。

翻译产出流程与费用估算（只估算，不实际调模型）：16.7 万字分 4 批——界面词表（约 500 条）与知识点/条目（约 2 千字）先行 → 题目+解析（7.2 万字）→ 课文讲解（2 万字）→ 单词释义（7.3 万字）；每批「导出 tsv → 模型批量翻 → 回导 → 教师抽样校对」，预计 3 遍迭代，模型量约 50–70 万 token 级，按 GLM 价位约 ¥100–300（$15–45），人工校对另计（工时费用参考任务书给的 K161 $18、K163 $10、K177 GLM 2.5h 量级；单词释义可抽样 10% 校对）。界面/知识点批次的模型费用忽略不计（<¥5）。

### 2.6 测试策略

- 无声明不变：tests/gen 新增生成物 sha256 快照（kg_v4 无 i18n/ 时全部产物哈希钉住）+ 对 app2/ 同验，照 test_ends.py 手法。
- GOLDEN：zh 路径逐字不变 → 现有 GOLDEN（test_tutor_persona.py 内嵌原文、assist_persona_golden.json、k166_preview_golden.json）不动；第 2 期新增 GOLDEN_JA_*。
- e2e：新增 tests/e2e/i18n_run.js——临时工作区写 ja.tsv、gen build 起服务：断言日语顶栏（ログアウト等）、登录页、做题页按钮，切回中文断言复原；现有 17 个 e2e 照旧跑（默认 zh，行为不变）。
- 回归：tests/run_all.sh 全量（130 组）每期必跑；第 1、2 期加组。

## 3. 分期实施计划

| 期 | 范围 | 改动模块 | 预估 | 需用户批准 |
|---|---|---|---|---|
| 第 1 期（最小可用） | 引擎可选 i18n 机制 + account_user.lang + auth_me.lang + 切换接口/按钮 + 界面词表 ja.tsv（.ui 450 条 + 引擎 66 条 + gen 模板 + 顶部高频消息 30–50 条）+ 前端消息替换 | gen/project.py、tools/render.py、templates/frontend/*.j2（引擎，单独 diff 评审）；kg_v4 routes/services/account.zs、scripts 迁移、i18n/ja.tsv | GLM 约 4–6 小时（参考 K177 引擎小改 2.5h；词典制作另需 1–2h），约 $10–20；界面词表翻译 <¥5 | **是**：引擎模板与 ui.py 注入点、account_user 加列 |
| 第 2 期 | AI 回答语言跟随界面（tutor/report/subject 人设 4–6 处按 lang 指示）+ GOLDEN_JA + 日语人设措辞 | kg_v4 services/{subject,tutor,report,teacher_assist}.zs、tests/kg_v4 | GLM 约 2–3 小时，约 $5–10 | 是：提示词改动（GOLDEN 更新） |
| 第 3 期 | 内容翻译：subject_content_translation 表 + 读路径替换 + 导入导出扩展 + 16.7 万字批量翻译与校对（4 批） | kg_v4 entities/queries/services、scripts、i18n 内容 tsv | 模型 GLM 约 3–4 小时 + 翻译费 ¥100–300（$15–45），人工校对另计 | 是：新表与导入导出格式、翻译花费 |
| （可选第 4 期） | 全量后端消息代码化、键化 i18n 演进、教师端助手日语化 | 引擎 + services 全量 | 另估 | 是 |

## 4. 需要用户拍板的决策点

1. **界面机制（批准引擎改动）**：推荐「i18n/ 目录存在即启用 + 前端 DOM 词典替换、中文原文作键」；备选「全键化 i18n」（彻底但引擎改动数倍）。→ 推荐前者。
2. **后端消息**：推荐前端词典替换（后端 584 处零改动，插值消息回退中文）；备选消息代码化（干净但要改全部 .zs 与用例）。→ 推荐前者。
3. **AI 回答语言**：跟随界面语言（ja 界面用日语讲日语语法，术语括注中文，教师人设可覆盖）还是锁中文？→ 推荐跟随界面语言。
4. **内容多语言模型（涉表结构）**：推荐通用翻译表 subject_content_translation（原表不动、缺省回退）；备选 _ja 列 / 按语言分科目。→ 推荐翻译表。
5. **翻译范围与预算**：16.7 万字全翻（约 ¥100–300 模型费 + 人工校对）还是先翻界面+知识点+题目（约 9.5 万字）、单词释义 7.3 万字暂缓？→ 推荐分批，单词释义最后。
