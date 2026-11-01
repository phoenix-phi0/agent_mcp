# kg_v4 遗留清单（backlog）

> **维护规则：每个任务的报告里的遗留项要追加到这里，开工前先看一遍。**
> 修好一条就把状态改成「已修（提交 hash，任务号）」，不要删行；决定不修的写清是谁、在哪次任务里决定的。

- 建立：K172（2026-11-01），汇总 data/reports/kg_K155_glm.md、kg_K156.md～kg_K171.md 里「没改 / 不改 / 已知问题 / 待用户决策 / 建议另开任务 / 遗留 / 风险」条目。
- 核对基准：origin/master `5f9c34e`（只读核对代码，未改业务代码）。行号是这个提交上的行号。
- K170（「最近学习」按科目 + 剩余按位置传参）在建清单期间完成（提交 c2d6d06、64adc4d、5f9c34e，已上线、实测 17/17），按最终报告记；K171（dslagent 实现简报 / Haiku 实现）建清单时**仍在进行**，相关条目标「进行中」。
- 状态取值：已修 / 未修 / 部分修 / 决定保留 / 待决策 / 进行中 / 核实不成立（实测证明不是问题，写明证据）。规模：小（半天内、单模块）/ 中（要跑 fix2 或停服窗口）/ 大（跨多模块或需设计）。

## 最该先做的 5 条

1. **O1 部署脚本里看门狗子 shell 挂住**：K159、K162、K163、K164、K166 每次上线都要手动 `kill -TERM` 一个 PID，迟早误杀。→ **已修（K173）**，见 O1。
2. **A1 选项 / 解析拼进 JSON 字面量**：内容侧靠「不用英文双引号」规避，任何老师录一道带 `"` 的题就可能坏题卡；先实测，坏了就改。→ **核实不成立（K173）**，见 A1。
3. **B1 lesson_text.examples_edited 迁移警告**：K119 起每次启动都报，噪声会盖住真警告；停服窗口顺手对齐。→ **已修（K173）**，见 B1。
4. **T1 规则对照组 `no such table: question`**：全量回归每次固定红一组，靠人工判「环境问题」，迟早漏掉真失败。→ **已修（K173）**，见 T1。

（K174 后更新：原第 3 条 G1 已修，见下表 G1；G3 的值域预检也已透进简报，见 G3。）

---

## 一、功能缺陷

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| A1 | 选项、判题回显把文本拼进 JSON 字面量 | 组题面 `{"letter": …, "text": "{tx}"}`，选项 / 解析 / 条目名含英文双引号或反斜杠可能出错；Python 题库靠「统一用单引号」规避 | kg_v4/services/quiz.zs:165、991、1123 | K157 §1 约定确认 | 核实不成立（K173：引擎对 JSON 字符串引号内的 {变量} 按 json.dumps 转义；tests/kg_v4/test_k173_json_literal.py 在改前代码 123e3ca 上用含 `"`、`\`、换行、花括号的选项与解析调 组题面 / 拼题卡 / 判答案页面 / 提交答案，13/13 逐字一致；代码不改，测试留作回归，提交 07b1cd0） | — | — |
| A2 | 科目老师设定 / 科目助手设定 的 custom 原样拼进返回对象 | persona、assist_prompt 含英文双引号时返回对象可能坏 | kg_v4/services/subject.zs:700（科目老师设定），科目助手设定 同写法 | K164 与任务书的差异 3（审查指出） | 核实不成立（K173：同 A1，科目老师设定 / 科目助手设定 的 custom、persona、intro 含 `"`、`\`、换行、花括号时逐字一致，见 test_k173_json_literal.py，提交 07b1cd0） | — | — |
| A3 | 教师端「打开学生端」对已登录教师永远被弹回 | 学生端认出教师身份就 leaveTo('/teacher')；K159 加了「退出」按钮，但这个链接语义没变 | templates/frontend/app.js.j2:551、1400 | K158 §5（可选建议） | 已修（K177：引擎加可选声明「认证 换端 先退出」，kg_v4/routes/account.zs 已启用；教师端顶栏变「退出并打开学生端」，点击先退出、同标签页去 / 登录页；无声明项目生成物逐字节不变，test_ends 第五节、e2e switch_logout_run.js、e2e_walk switch_logout_flow 覆盖） | — | — |
| A4 | 校验草稿 relay_add 的 keywords 为列表时不连接 | 模型把 keywords 给成列表时原样插进字符串，没用逗号连 | kg_v4/services/assist_draft.zs:553-555 | K169 §4 第 4 次核查 | 未修 | 列表时按「，」连接，补一条约定用例 | 小 |
| A5 | 调模型后只校验报错和空、不校验内容 | 推理机 warning「调了模型没处理坏输出」；核对：teacher_assist 答一轮、tutor.总结本轮 已在报错或空回答时报 400，但对乱码 / 格式不对的回答不做检查（tutor.总结页面 本身不调模型） | teacher_assist.zs:706-709；tutor.zs:568-574 | K165 §1 关键事实 | 未修（低优先，可不做） | 有真实坏输出案例再加兜底，不必为 warning 单独改 | 小 |
| A6 | Python 科目教师助手回答不点出科目 | K166 实测回答只讲全班数据，没出现「Python」「编程」，严格检查记 FAIL；离线系统提示开头正确 | teacher_assist 问助手（提示词） | K166 实测 | 待决策（模型行为，不一定是缺陷） | 下次上线实测时复问一次；仍不提再考虑提示词点名科目 | 小 |
| A7 | 前端没有退出入口 / checkEnd 调 auth_logout 失效 | 同一浏览器登过教师号后学生端无法切换账号 | kg_v4/routes/account.zs:15 | K158 §5 | 已修（9a45f19，K159） | — | — |
| A8 | 科目表格行缺 subj_intro，从行点编辑保存会清空说明 | — | queries/subject_page_rows*.sql | K161 已知问题、K162 | 已修（3459c92、64a8a4f，K163） | — | — |
| A9 | 问老师人设不按科目切换（Python 回答「和日语语法无关」） | — | subject.科目老师设定 | K162 发现的问题 | 已修（64a8a4f，K163） | — | — |
| A10 | 教师助手提示词写死「日语学习系统」 | — | teacher_assist、assist_draft、assist_material | K163 盘点 | 已修（22cf64b，K164） | — | — |
| A11 | 班级上下文 第 128 行按位置传参遇首尾空白 500 | Python 科目问教学建议必现 | teacher_assist.班级上下文 | K164 待决策 ① | 已修（41df270，K166；用户在 K166 任务书决定修） | — | — |
| A12 | 查一值 取到 NULL 变文本 'None'（科目助手设定 / 科目老师设定） | — | queries/subject_ai_assist_prompt.sql、subject_ai_persona.sql | K164 差异 2、K165 §3 | 已修（22cf64b，K164，SQL COALESCE） | — | — |
| A13 | teacher_assist.判意图 缺 subject_id? 入参 | — | teacher_assist.zs:543 | K169 §4 chk | 已修（22cf64b，K164） | — | — |
| A14 | assist_draft 确认 / 撤销 kg_add 调 assist_kg 多传 learner= | — | assist_draft.zs:1112、1301 | K169 §4 | 已修（41df270，K166） | — | — |
| A15 | 学情、学生名单「最近学习」只按日语算 | Python 科目下 student 行「最近学习」为空 | account.列学生 / 列学生页面 | K170 一、三 | 已修（64adc4d、5f9c34e，K170，已上线实测） | — | — |

注：K165 推理机另报「teacher_rules.保存传达页面 写两张表没写事务」，K172 核对当前代码不成立——保存传达页面（teacher_rules.zs:751）只调一次 保存传达，后者只写 teacher_rules_relay 一张表、各一条语句，未列入清单。

## 二、数据 / 迁移

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| B1 | lesson_text.examples_edited 迁移警告 | 库里 INTEGER NOT NULL，实体 INTEGER NOT NULL DEFAULT 0，每次启动都打 `[迁移警告]` | kg_v4/entities/lesson.entity:19 | K162、K163、K164、K170 上线（K119 起） | 已修（4d401d8，K173：实体去掉「默认 0」与库一致，库不动；所有写入 lesson_text_insert.sql 都显式传值，默认值从不生效；lesson 契约 9 条用例数据补 examples_edited=0；正式库快照迁移比对 0 警告） | — | — |
| B2 | 正式库验证残留 | subject_pref 多 2 行（K156）；student 在科目 2 的作答 / quiz_progress / tutor_message（K157）；tutor_message 2→4→6（K159、K162）；uploads 多 4 个 csv、1 个 txt（K157） | 正式库 /workspace/dslagent_exp/kg_v4_data | K156 副作用、K157 §5、K159 §4、K162 库对比 | 待决策 | 用户定是否清理；要清就在停服窗口备份后一次清 | 小 |
| B3 | Python 题库源文件不在任何 git 仓库 | content/python_v1/ 只在本机；K162 改 README 时改前无备份 | /workspace/dslagent_exp/content/python_v1/ | K157 §6、K162 第 4 步 | 未修 | 纳入仓库（或单独建仓）并记录当前在用的 quiz_v2.txt | 小 |
| B4 | 科目 2 quiz_progress 残留 level=N5 | — | 正式库 quiz_progress | K160 实施计划 | 已修（K162 停服窗口按手册 SQL 改为「入门」） | — | — |
| B5 | 各科目自定义等级未上线、正式库未迁移 | — | 正式服务 | K161 已知问题 | 已修（K162 上线并迁移） | — | — |

## 三、按位置传参类

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| C1 | 剩余高 / 中风险按位置传参 16 处 | vocab 列单词 / 取单词 / 新建 / 修改 / 导入、progress 作答原文、quiz 题库解析、teacher_rules 科目名与学生 label，首尾空白会让引擎拒绝 | vocab.zs、progress.zs、quiz.zs、teacher_rules.zs（K166 盘点行号） | K166 盘点、K169 §3.3 #120、K170 二 | 已修（64adc4d，K170，已上线） | — | — |
| C2 | textbook_import 编号串按位置传参 | codes 逗号串按位置写库 | kg_v4/services/textbook_import.zs:593、596 | K166 盘点、K170 二 | 决定保留（K170 判定：带空白编号在 kg.取条目 已报错到不了这里，正式库 draft 0 行；用户未单独确认） | 若以后放开非日语教材导入再一起改 | 小 |
| C3 | 低风险按位置传参约 60 处 | 编号、日期、科目号等短值；teacher_rules 其余约 54 处，assist_insight.zs:325/326、account.zs:494、assist_file.zs:239/279、teacher_assist.zs:356、kg.zs kg_str_min/max | 见左 | K166 盘点 | 决定保留（K166 执行者盘点时判低风险不改，用户未单独确认） | 新写代码一律对象传参，旧的不动 | — |
| C4 | vocab 导入循环复用 jq，更新分支的 word_id 会带到下一轮插入 | 对象传参只取 SQL 用到的键，vocab_insert 不用 word_id，目前无害 | kg_v4/services/vocab.zs（导入单词） | K170 六 审查建议 3 | 决定保留（K170：fix2 产物不手改，判无害；用户未单独确认） | 下次改 vocab 时每轮新建 jq | 小 |

## 四、日语写死 / 多科目化

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| D1 | 教材导入只支持日语、N5–N1 写死 | 「你是日语教材整理助手」、N5–N1 校验多处；非日语科目已关入口 | textbook_import.zs:8、48（门控），856、858 等 | K160 决策 3、K161 已知问题、K164 盘点 | 决定保留（用户在 K160 决策 3 选「本轮不含教材导入、非日语关入口」，K161 按 D3 实施） | 有非日语教材需求时另开任务 | 大 |
| D2 | 默写 / 单词 `[N4]` 前缀与灌库正则 | 日语词库数据格式 | dictation.zs:486-491、queries/vocab_dict_*.sql、setup/init_data.py | K160 不改的部分、K161 | 决定保留（K160 设计定稿、K161 按批准方案实施） | — | — |
| D3 | 错词本方向「看汉字写读音」「看中文写日语」 | 日语默写专用，非日语科目为空 | kg_v4/services/report.zs:947、949 | K164 盘点 | 决定保留（K164） | — | — |
| D4 | 测试里写死 N5 共 113 处 | 日语 / 默认科目下仍成立 | tests/kg、tests/kg_v4、tests/e2e 20 个文件 | K160 方法与核实 | 决定保留（K160 设计盘点定为不改，用户在 K161 批准该方案；Python 科目用例由 K161 补） | — | — |
| D5 | 设定预览与学生端真实提示词不一致 | 无自定义设定时预览开头是「你是一位耐心的日语老师」，问老师真实人设是「你是一位中文老师，教中文学习者日语语法」 | kg_v4/services/teacher_rules.zs:697-698（拼进 queries/teacher_rules_preview_layout.sql 的 :opener）；subject.zs:687 | K164 盘点、K166 已知问题 2 | 部分修（41df270，K166：预览按科目取，有自定义时显示自定义；日语默认措辞为保持改前一致有意不动） | 待用户决定是否让预览直接取 科目老师设定.persona | 小 |
| D6 | 做题页等级只有 N5–N1、题卡显示「N5・选择」 | — | quiz.zs、quiz.entity | K157 §2、K160 | 已修（f6ede27、7e06dad，K161） | — | — |
| D7 | 学情 5 个桶、知识点等级取数、课文导入、问老师写死 N5–N1 | — | progress.zs、lesson.zs、tutor.zs | K160 涉及文件 | 已修（7e06dad，K161；代码里已无 N5 字面量，注释残留见 W1） | — | — |
| I1 | AI 回答语言跟随界面语言（日语版第 2 期） | 界面切到日本語后，问老师 / 教师助手的回答仍是中文（提示词不按 me.lang 注入） | kg_v4/services/tutor.zs、teacher_assist.zs 的提示词拼装 | K180 第 1 期上线后遗留（设计 kg_v4/plan/i18n_ja_design.md D2 定稿） | 已修（044248e，K181，已上线；四个注入点：tutor.答一轮/总结本轮跟学习者、teacher_assist.答一轮、report.写学情总结跟教师，lang=ja 时追加同一句日语指示；教师设定写明确回答语言指示时不追加、身份描述不算；GOLDEN_JA tests/kg_v4/test_i18n_ai_lang.py 23 检查点；草稿/材料按任务书决定保持中文） | — | — |
| I2 | 科目内容日语翻译（日语版第 3 期） | 知识点、条目、题目、讲解、单词释义（约 16.7 万字）仍是中文，切日本語后内容不翻 | content 各表；kg/content | K180 第 1 期上线后遗留（设计 D3 定稿） | 已实现（K182：仅 Python 内容 442 条译文；专项回归 24/24，待完成全量验证与上线） | subject_content_translation 按稳定业务键取译文，ja 替换展示、缺译文回退中文；日语科目保持中文 | 大 |

## 五、界面文案

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| U1 | 教师端提示里的日语示例（〜たばかり、て形） | 静态文案不能按科目切 | ui/teacher_assist.ui、teacher_material.ui、teacher_note.ui、report.ui | K164 待决策 ③ | 已修（7869f95，K166；用户在 K166 任务书决定换中性例子） | — | — |
| U2 | assist_prompt 不在科目管理暴露为「教师助手设定」 | 只能直接写库 | kg_v4/contracts/subject.md:36 | K164 待决策 ② | 决定保留（用户在 K166 任务书决定「不加教师助手设定输入框」） | — | — |

## 六、测试 / 环境

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| T1 | 规则对照组固定失败 | 工作区报 `no such table: question`（本机 kg/app.db 缺表），干净 worktree 报 `unable to open database file` | tests/run_all.sh「规则对照」组，kg/app.db | K159、K161、K163、K164、K166、K170 | 已修（07b1cd0，K173：本机 kg/app.db 是 0 字节空文件；测试改为照 kg 搭临时库、经导入接口导题和词（tests/kg/helpers），不再读 kg/app.db，run_all 去掉写进 kg/ 的 `kg setup`；4/4 通过） | — | — |
| T2 | 命名约定组 62 处失败 | 全在他人未跟踪的 dsl/sandbox/，kg_v4 下 0 处 | test_naming.py --全部 | K159、K161、K163、K164、K166、K170 | 未修 | 找 dsl/sandbox/ 的主人处理，或让测试只扫已跟踪文件 | 小 |
| T3 | 教材导入E2E「确认后撤下了」已知失败 | 旧 kg 项目撤下后重新载入盖掉提示 | tests/run_all.sh:24-29 KNOWN | K159、K161、K163、K164、K166、K170 | 决定保留（用户决定旧 kg 不修，kg_v4 已修于 6863960；见 kg_K116、kg_K117） | — | — |
| T4 | gsb verify 跑不了本仓库全量回归 | 沙箱 /tmp 与仓库只读，115 组全报 `No usable temporary directory` | gsb_tools verify | K161、K163 | 未修 | 回归仍自己跑；或给 verify 沙箱可写临时目录 | 小 |
| T5 | 约定用例只比顶层键 | 嵌套键（设定预览版式）、按科目的 last_at 值、带空白传参都比不到 | 约定用例比对器 | K166 测试、K170 三 | 未修（靠专项测试 test_k166_*、test_k170_* 补） | 约定用例支持比嵌套键 / 值 | 中 |
| T6 | 偶发失败未查明 | DSLv3流程 461/1（疑并发干扰）；kg_v4走查教师助手草稿一步 `Locator.fill: Timeout 30000ms` | tests/kg_v4/e2e_walk.py | K166 测试 | 未修 | 再出现时保留完整日志定位 | 小 |
| T7 | quiz_run.js 依赖 select 顺序 | `p.selects()[0]` 当作等级下拉 | tests/e2e/quiz_run.js:130、567 | K160 涉及文件 | 未修（当前能过） | 改按 name / 标签选下拉 | 小 |
| T8 | 测试环境依赖未就绪 | tests/e2e/node_modules 需 `npm ci --prefix tests/e2e`；Playwright 虚拟环境没装 chromium（K158 改用系统 google-chrome） | tests/e2e、PW venv | K158、K159 | 未修 | 写进 tests/README 的准备步骤 | 小 |
| T9 | 主工作区长期残留未提交内容 | data/tmp、data/reports、kg_v4/plan/audit2.json、他人的 gen/out 删除与 dsl/sandbox/ | /workspace/agent_mcp 工作区 | K159、K161、K164、K166 | 待决策 | 找主人确认 gen/out 删除与 dsl/sandbox/ 去留；audit2.json 加 .gitignore | 小 |

## 七、运维（反代、口令、看门狗）

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| O1 | 部署脚本起看门狗的子 shell 握着 tee 管道挂住 | 每次上线都要按 PID `kill -TERM`（771842、940475、1031072、1159911、1252006、1342315） | /tmp/k1xx_tools/deploy.sh（不在仓库） | K159、K162、K163、K164、K166、K170 | 已修（K173：标准脚本 /workspace/dslagent_exp/kg_v4_run/deploy.sh，带 --dry-run，README「上线」一节；看门狗 setsid -f + 全部重定向 + 关 3–255 号描述符；全文见 data/reports/kg_K173.md；dslagent_exp 不是 git 仓库，脚本不进 agent_mcp） | — | — |
| O2 | 实测账号口令不在环境里 | s1、t1、root、student 口令都没有；root 不是日语科目负责人，实测只能建临时账号再删 | 正式库账号 | K158 §2、K163 已知问题 | 未修 | 用户决定是否给专用实测账号（口令放环境变量，不进仓库） | 小 |
| O3 | /tmp 下历任务临时物与旧 worktree 堆积 | /tmp/k157～k169、k1xx_src / _tools、/tmp/k138_wt、/tmp/k147_wt 等 | /tmp | K159、K165 等 | 未修 | 确认无用后统一清理，旧 worktree 用 `git worktree remove` | 小 |
| O4 | 推理机依赖本机手搭 | JDK / Maven 在 ~/opt，clingo 在 ~/opt/logic-venv，不在仓库、不在 CI | /workspace/drools-engine | K165 §1 | 未修 | 若要接入流程，先写安装脚本 | 中 |

## 八、dslagent / 工具

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| G1 | v3/contracts.check 只在写规划时调用 | K174 起已修：audit2 / fix2 开头约定闸（逐模块 contracts.check，不调模型），`--contract-check 拦截/提醒/关`，默认拦截（违约项目可用 提醒/关 过渡）；豁免写法见 v3/contracts.py（被报行正上方 `# 约定检查豁免 表名前缀/可选传空 <入参>：理由`）；kg_v4 现存 12 条违约已逐条判定并全部豁免，m4-rest 快照（K148 时期）11 条会被拦下 | tools/dslagent/v3/contracts.py、v3/audit2.zs | K165 §2、§4.1、§6；kg_K174.md | 已修（K174） | — | 小 |
| G2 | 调用图漏边：reaches 召回 17/24 | 契约写「"level_options": 科目等级 options」而不是「调用 x.y」，QCALL_RE 只认 `调用 模块.函数` | tools/dslagent/packs/dslproj/contract.py:72 | K165 §4.2、K167 §3 | 未修 | 「提到公开函数却没写调用」出 warning；影响面只当提示不当闸 | 小 |
| G3 | 用例数据与跨模块规则冲突的预检 | K174 起已修：brief.py 值域检查（用例数据行 / 调用参数含 rows_json，内置 level=该用例科目 levels，空按 N5..N1；设计声明 `--declare` 的 值域 行可加字段），进 brief CLI / fix2 --brief 影响面和本模块简报，只是提醒不拦截；K161 回放夹具 quiz 7/7、assist_draft 6/6 全报出，HEAD 误报 2 条 | tools/dslagent/v3/brief.py | K165 §4.3、§6；kg_K174.md | 已修（K174，$0：纯规则不调模型） | — | 小 |
| G4 | 推理机影响面接入方案 | B 侧 --modules = F 所在模块 ∪ 签名变直接调用方；A 侧「旧值→新来源函数」写死提示；不做自动闸 | /workspace/drools-engine/dslagent/impact/ | K167 §6、K168 §6 | 未修（只有实验结论） | 用户决定是否接入；接入用 Python 在 B 侧实现 | 中 |
| G5 | 人设正则误命中问句 | 「你是想让我出题…」被当成人设 | 推理机值域规则 | K168 §5.2、§6 ② | 已修（K174，简报写死盘点的 persona: 正则已排除问句） | — | 小 |
| G6 | 实现要点规则误报多、未接入 | 抽样 20 条 9 有用；契约层 R2 0/5；R1 把写入算读；R3 不处理否定；fix2 只跑一次证据不足 | /tmp/k169/hints.py（432 行，K169 临时文件，未入任何仓库；清 /tmp 前先归档） | K169 §3.3、§5 | 未修 | 去掉契约层 R2、修 R1/R3；接入只给 modify_module；要证明省钱需同起点各跑 2–3 次 | 中 |
| G7 | 大模块 change2 空闲超时 | teacher_assist 约 3500 行，change2 两次 rc=-9（$4.15 + $3.23） | dslagent change2 | K165 §3（K131b、K131c） | 未修 | 先按函数切片定位再改；K171 的实现简报可能相关 | 大 |
| G8 | K171 实现简报（--brief）+ Haiku 实现（--impl-model） | 单测、全量、两项实验都未完成 | /tmp/k171_wt（分支 dslagent-brief） | K171 | 进行中 | 等 K171 报告 | 中 |
| G9 | 核查员把实现要点当契约要求 / 误判等价写法 | K169 要点被 audit2 当要求多改一轮；K170 fix2_b 把 progress.取概览 hint 改成等价写法 | dslagent audit2 | K169 §4、K170 四 | 未修 | 要点不交给核查员；核查员给「等价改写」时要求举反例 | 小 |
| G10 | drools-engine 目录有并发写入、归属未确认 | K167 时 dslagent/impact/ 有非本任务文件；K169 时 README.md、dslagent/codecheck/ 被改 | /workspace/drools-engine（非 git） | K167 §7、K169 §7 | 待决策 | 把 drools-engine 纳入 git 或约定谁能写 | 小 |
| G11 | 未验证的推理机结论 | clarify nullable 规则能否提前提示 NULL→'None'；mvn 测试未重跑；Haiku 拆任务数据只在 /tmp/hx、/tmp/hx2 | /workspace/drools-engine | K165 §4.7、§4.8、§7 | 未修 | 需要时再验，数据先归档进仓库 | 小 |

## 九、文档旧口径

| 编号 | 标题 | 现象 | 位置 | 出处 | 状态 | 建议处理 | 规模 |
|---|---|---|---|---|---|---|---|
| W1 | 服务注释仍是 N5–N1 / 日语口径 | 「level 只会是 N5 N4 N3 N2 N1」「levels 恒为 5 项」「等级文本（N5 到 N1）」「老师人设（中文老师，教中文学习者日语语法…）」等；代码已按科目 | tutor.zs:19、22、194、232；progress.zs:269；report.zs:33；lesson.zs:224、475 | K161 已知问题、K163、K164 差异 1 | 未修 | 下次这些模块跑 fix2 时顺带改注释（services 只经 dslagent 改） | 小 |
| W2 | Python 题库 README 第 20 行旧口径 | 仍写「等级一律填 N5…」，与 K161 后的自定义等级矛盾 | /workspace/dslagent_exp/content/python_v1/README.md:20 | K162 发现的问题 | 未修 | 改成按科目等级填写；与 B3 一起入库 | 小 |
| W3 | assist_draft 契约里 level=初一 未复核 | 数学科目用例的等级取值 | kg_v4/contracts/assist_draft.md（17 处「初一」） | K160 方法与核实 | 部分修（K161 改了 6 条冲突用例；其余未逐条复核） | 下次动 assist_draft 契约时复核 | 小 |
| W4 | tutor 判意图等级清单与契约不逐字一致 | 契约是空格连接，K161 代码当时用逗号；K163 改后意思相同、措辞不逐字 | tutor.zs:19-22 | K163 已知问题 | 决定保留（K163 执行者判定意思相同、不为半句话跑 fix2，用户未单独确认） | — | — |

---

## 状态统计（K172 建立时）

| 状态 | 条数 |
|---|---|
| 未修 | 28 |
| 已修 | 15 |
| 部分修 | 2 |
| 决定保留 | 10 |
| 待决策 | 5 |
| 进行中 | 1 |
| 合计 | 61 |

K173 后：未修 23、已修 18（+O1、B1、T1）、核实不成立 2（A1、A2），其余不变，合计 61。

K181 后：未修 22、已修 19（+I1），其余不变，合计 61。

按类别：功能缺陷 15、数据/迁移 5、按位置传参 4、日语写死/多科目化 7、界面文案 2、测试/环境 9、运维 4、dslagent/工具 11、文档旧口径 4。
