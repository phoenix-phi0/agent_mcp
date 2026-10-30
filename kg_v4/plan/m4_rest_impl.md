# M4-P3 + P4 实现清单（教师助手：教学材料 / 深度学情）

约定已在 K147 一次写好（只写约定/实体/plan/ui，不写 services/queries/routes），本清单给后续 change2（sonnet v3）用。
用户决定：P3、P4 先都做完，最后再整体验证一次再合并 master（不再每阶段单独验证）。

- 设计依据：data/tmp/k124_design/design.md §5（材料）、§6（深度学情）；决定 decisions_final.md（D9 材料平衡档、长篇强档；D10 教学材料页放右侧「管理」组；
  D11 错题归因放助手侧；D12 字符图；D14 只读老师只能提问；D15 兜底判出的动手类意图只生成草稿/材料，不写教学数据）。
- 落点：data/reports/kg_K133.md「P2–P4 落点」。P3 新模块 **assist_material**（表 teacher_assist_material，界面 ui/teacher_material.ui）；
  P4 新模块 **assist_insight**（不建表）；teacher_assist 依赖它们；方向 teacher_assist → assist_material → assist_draft，不成环。

## 约定改动一览（K147）

| 文件 | 改动 |
|---|---|
| contracts/assist_material.md（新） | 表 teacher_assist_material；生成/保存/改/删/列/取/导出材料、练习转出题草稿、按消息列材料、挂回材料消息；材料页 7 个页面函数；8 个接口 /assist_material/*；24 条用例 |
| contracts/assist_insight.md（新） | 规则常量、字符条、迷你图、空态；学情趋势、错题归因、学生对比、掉队名单、分析上下文；不建表、无接口；11 条用例 |
| contracts/progress.md | 新增公开函数 按天统计作答 days? week? student?（只读；1 个新 SQL）；2 条用例 |
| contracts/teacher_assist.md | 依赖加 assist_material assist_insight；判意图 9 档（make_material、deep_analysis，兜底关键词 ①b ②e）；问助手 两条新路 + 「给掉队学生发传达」③a；答一轮 tail? 与规则⑪；列对话页面 挂材料卡片；3 个新页面函数（材料保存页面、材料导出跳转、材料转草稿页面）与 3 个接口；chitchat 功能说明；8 条用例 |
| entities/assist_material.entity（新） | 表 + 页面实体 assist_material_view（mat_*） |
| ui/teacher_material.ui（新） | 教学材料页（右侧「管理」）：类型筛选、材料表（编辑/导出/保存/做成出题草稿/删除）、编辑浮层、导出浮层 |
| ui/teacher_assist.ui | 消息流「按钮」白名单加 assist_material_save / assist_material_export / assist_material_to_draft；顶栏、提示、等待文案 |
| plan/top.zs | 新增 assist_material、assist_insight 两行；progress 提供加 按天统计作答；teacher_assist 依赖与说明 |
| tests/kg_v4/test_project.py、test_xcall.py | 模块清单 NAMES 加 assist_material assist_insight |

## 约定领先实现时的状态（K147 写完约定时）

- 约定检查 20 个模块 0 问题；top.zs 能解析；全局检查 0 重复；加载检查 0 问题；xcall 2798 处 0 不一致。
- 全量回归 16/20：assist_material 24 条全失败、assist_insight 11 条全失败（没有服务文件）；progress 99 条失败 2 条（新增的两条 按天统计作答）；
  teacher_assist 76 条失败 7 条（全是新增的 8 条里的；「问助手_给掉队学生发传达没有掉队不建草稿」现在碰巧能过——没学生名时 生成草稿 本来就追问，实现后仍应通过）。
  另有「比对约定」报 progress 缺 按天统计作答、assist_material/assist_insight 缺服务文件、teacher_assist 依赖少两个。旧用例 0 失败。
  合计新增用例 45 条，预期失败 44 条。
- gen build 不过，只报缺接口（11 处，无别的编译错误）：teacher_material.ui 的 7 个动作 material_home / open / update / save / export / delete / to_draft
  和 teacher_assist.ui 消息流白名单的 3 个动作 assist_material_save / export / to_draft 在 routes 里还没有（约定「## 接口」已声明，第 3、4 步写路由后恢复）。接口数 101 → 112（assist_material 8 个 + teacher_assist 3 个），
  test_project.py 里的「101 个接口」到时同步改成 112。

## 关键取舍（实现时别改回去）

1. **练习转出题草稿不改 assist_draft**：assist_material 直接调现有 assist_draft.生成草稿 kind=quiz_add，把课堂练习全文作为 ref_text（P2 已有入参，8000 字截断）。
   草稿照常校验、照常要确认；assist_draft 一行不改（「按题目建草稿」不新增）。
2. **材料不走草稿确认**：生成材料不改教学数据，存成 draft（未保存），「保存」直接改 saved；编辑过的一律 saved。删除是硬删。
3. **卡片「导出」用跳转**：E1 消息按钮只能调远程动作、开不了浮层，所以 teacher_assist 的 材料导出跳转 只核对归属（assist_material.取材料），
   接口用模板 提交跳转动态 带 go 到 #教学材料?浮层=导出材料&mat_id={r.mat_id}，导出浮层的「载入」取全文。导出只复制，下载要 E3（未批）。
4. **档位 D9**：默认平衡；教案、讲义且（话里含「详细/完整/长篇/整节课/一整课/一节课」或 ref_text >3000 字）用强。生成材料 返回 tier，用例按它核对。
5. **数字只由后端算**：assist_insight 算好正确率、错误率、名次、掉队名单和字符图；答一轮 规则⑪禁止模型重算、画图；字符图经 tail 原样接在回答后面写进对话。
6. **掉队规则写成约定常量**（assist_insight 的 规则常量）：①全班近 7 天有作答而本人 ≥7 天无作答；②近 14 天正确率比之前 14 天低 ≥15 个百分点（两段各 ≥10 题）。
   design §6.1 的③低分点 ≥3、④过期传达本期不做（任务只要求①②）。
7. **归因直读上游表**（D11）：assist_insight 的 SQL 只读 progress_answer、quiz_question（progress 是直接依赖，quiz 经 report→tutor→quiz 在上游，用例库里有这张表）；
   不调 quiz 的函数所以不声明 quiz 依赖（声明了 xcall 会报「多余依赖」），同 kg 查引用 的直读做法。
8. **给掉队学生发传达**：teacher_assist 先调 assist_insight.掉队名单，名单的 username 用「、」连起来作为 students 交给 assist_draft.生成草稿（≤30 人）；名单为空不调模型、不建草稿。
   assist_draft 不依赖 assist_insight。
9. **深度学情不加「分析」区域**：design §6.2 的列表区可选，本期图在回答正文里；页面字段 ana_* 没加（rows 键已在 assist_insight 返回里，以后要加区域直接用）。
10. **E1 按钮样式**：引擎只认 kind=primary / danger（tools/ui.py:434）。材料按钮按这个写；assist_draft 的 草稿按钮 现在写的是 ""/次要/危险（前端都画成普通按钮），
    不在本期改，记为已知小问题。

## 模块行数估算（每个服务文件 ≤ 约 1800 行）

| 模块 | 现在 | 改动 | 之后 |
|---|---|---|---|
| assist_material（新） | 0 | 本科目 8、类型码/类型名/状态名 15、本人材料 12、材料行 8、材料按钮 20、材料数据段 80、生成材料 90、保存 20、改 35、删 18、列 35、取 18、导出 15、练习转出题草稿 35、按消息列材料 30、挂回材料消息 18、7 个页面函数 75 | 约 530 |
| assist_insight（新） | 0 | 本科目 8、规则常量 10、字符条 10、迷你图 15、空态 25、学情趋势 110、错题归因 100、学生对比 80、掉队名单 100、分析上下文 25 | 约 485 |
| progress | 758 | 按天统计作答 +30 | 约 790 |
| teacher_assist | 968 | 判意图 +30、问助手 make_material +45 / deep_analysis +30 / 掉队传达 +15、答一轮 +6、列对话页面 +12、3 个页面函数 +45 | 约 1150 |
| assist_draft | 1392 | 不改 | 1392 |
| routes/assist_material.zs（新） | 0 | 8 个接口 | 8 个接口 |
| routes/teacher_assist.zs | 11 个接口 | +3 | 14 个接口 |
| setup/cleanup_assist_files.py | 约 140 | 未保存材料 7 天清理 +25 | 约 165 |

均 ≤ 1800；teacher_assist P3+P4 后约 1150（K133 估 P2–P4 后约 1150，一致），离上限还有约 650 行。

## 实现步骤（每步一个 change2，注明输入量）

### 第 1 步：progress 按天统计作答（fix2，小改）
- services/progress.zs 加公开函数，queries/progress_answer_daily.sql（period 按天 substr(at,1,10)，按周 date(at,'-6 days','weekday 1')；since 用当前时间算，
  用例 DSL_NOW=2026-01-01 09:00:00）；角色校验同 统计作答。
- 输入：progress 约定 69KB + 服务 38KB（758 行），改动约 30 行；比 P2 第 3 步（assist_draft 128KB+57KB 改 12 行）输入小，装得下。
- 验收：progress 99 条全过。

### 第 2 步：assist_insight 新模块（fix2 按约定新写；脚手架：新建 services/assist_insight.zs，无路由、无实体、无表）
- 文件头 `模块 assist_insight` / `依赖 assist_common progress report kg subject`；queries/assist_insight_wrong_by_point.sql、assist_insight_wrong_by_item.sql
  （progress_answer LEFT JOIN quiz_question；学生范围用 JSON 参数 + json_each）。数值比较按 skill 的坑一律 CAST。
- 日期窗口（today−6、today−13、today−27）在 SQL 里用 date(当前时间, '-n days') 算，不在 DSL 里做日期运算。
- 输入：约定 27KB + 上游公开函数头（assist_common、progress、report、kg、subject）；新文件约 485 行，与 P2 第 1 步（assist_file 470 行）同量级，装得下。
- 验收：assist_insight 11 条全过；xcall 0 不一致。依赖第 1 步。

### 第 3 步：assist_material 新模块 + 路由（fix2 按约定新写；脚手架：新建 services/assist_material.zs、routes/assist_material.zs，实体已在）
- queries/assist_material_*.sql（建议：get_own、insert、save、update、delete、list、by_msgs、set_msg）。路由 8 个接口按「## 接口」的模板由骨架生成
  （没有上传字段；材料页的 消息={r.note} 用 页面状态消息 模板）。
- 新表靠 ensure_db 补建（只加不改）；正式库只新增一张表，上线前照例备份。
- 输入：约定 44KB + 上游公开函数头（assist_common、assist_draft 的 生成草稿、report、kg、lesson、subject）；新文件约 530 行 + 8 个接口，略大于 assist_file，
  仍远小于 K131b 失败时的规模；若一次 change2 装不下，按「材料 CRUD（本人材料…挂回材料消息）」与「生成材料 + 练习转出题草稿 + 页面函数」拆两批。
- 验收：assist_material 24 条全过；gen build 不再报 material_* 动作缺接口。

### 第 4 步：teacher_assist 接材料与深度学情（fix2）
- 依赖加 assist_material assist_insight（服务文件头要跟上约定和 top.zs）。判意图（9 档、material_kind、analysis_kind、兜底 ①b ②e）、问助手（make_material、deep_analysis、③a 掉队传达）、
  答一轮（tail?、规则⑪）、列对话页面（按消息列材料）、chitchat 说明、新函数 材料保存页面 / 材料导出跳转 / 材料转草稿页面；routes/teacher_assist.zs 加 3 个接口
  （导出那条是 提交跳转动态，跳转目标带 {r.mat_id}）。
- 输入：约定 102KB + 上游公开函数头 + 现有服务 49KB（968 行）；改动约 +185 行，与 P1b（约 +230 行）、P2 第 2 步（+180 行）同量级，装得下。
- 验收：teacher_assist 76 条全过；gen build 112 个接口（test_project.py 的 101 同步改 112）。依赖第 2、3 步。

### 第 5 步：清理脚本加未保存材料（opus 或 sonnet 直接写，不走 change2）
- setup/cleanup_assist_files.py：status=draft 且 created_at 早于 7 天前的 teacher_assist_material 行一并删（只删行；dry-run 照旧只打印；--apply 才删；
  表不存在时跳过）。tests/kg_v4/test_cleanup_assist_files.py 加 2 项（7 天前的 draft 删、saved 不删）。

### 第 6 步：e2e 与整体验证（用户决定：P3、P4 做完后统一验证一次再合并）
- tests/kg_v4/e2e_walk.py 加材料段（DSL_MOCK_SCRIPT：说「写一份点一的教案」→ 对话里出卡片 → 点「保存」→ 教学材料页能看到、状态已保存 →
  编辑保存后再打开内容是新的 → 卡片「导出」跳到导出浮层看到全文 → 课堂练习「做成出题草稿」→ 待确认多一行）与深度学情段（问「有没有掉队的学生」回答末尾有字符图；
  没有学生时回空态原文）；390px 宽度下卡片按钮可点。
- tests/kg_v4/test_project.py 20/20、`bash tests/run_all.sh`、kg_v4 e2e_walk 不退化；真模型冒烟 ≤4 句（教案 1 份看档位与格式、课堂练习转出题草稿、
  趋势回答里的数字与后端一致、掉队名单发传达）。

## 已知限制

- 卡片「导出」点了会离开教师助手页（跳到教学材料页的导出浮层，返回键回来）；E1 按钮开不了本页浮层。
- 材料只能复制导出，下载 .txt 要 E3。
- 深度学情没有单独的「分析」列表区，图在回答正文里（纯文本字符，窄屏会折行）。
- 错题归因里不在题库的题（问老师里出的模板题）条目记成「（题库外的题）」。
- 掉队规则只有①②两条（design 的③④本期不做）；停用学生不判。
- 生成材料不重试（一次模型调用），模型出错整轮不写，老师重发即可。
