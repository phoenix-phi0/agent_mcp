# M4 拆模块实现计划（teacher_assist → teacher_assist + assist_common + assist_draft + assist_setting + assist_kg）

约定已在 K133 改好（contracts/ 五个文件、plan/top.zs、entities/assist_draft.entity），本计划给后面的实现任务用。
起点是 origin/m4-split：services/queries/routes 还是 m4-p1b 的样子（teacher_assist.zs 2124 行，P1 已实现、P1b 未实现）。

## 为什么拆、拆成什么样

K131b/K131c 三次 change2 都改不动 teacher_assist（约定 215KB + 服务 2124 行，P1b 再加约 1200 行）。拆完后：

| 模块 | 约定 | 服务（预计） | 内容 |
|---|---|---|---|
| assist_common | 174 行 / 14KB | 约 310 行 | 本科目、学生范围（改公开，返回 {total, students}）、匹配学生、匹配知识点（原样搬） |
| assist_kg | 136 行 / 17KB | 约 470 行（新写） | 图谱编号前缀（公开，返回 {prefix}）、编号合规、校验/执行/撤销图谱草稿（公开，入参 payload_json / result_json） |
| assist_setting | 117 行 / 18KB | 约 480 行（新写） | 设定候选、校验/执行/撤销设定草稿（公开，入参 payload_json / result_json / snapshot_json） |
| assist_draft | 1330 行 / 127KB | 约 1270 行 | 草稿表、状态机、P1 两种 kind、P1b 分派、按消息列草稿 / 挂回消息（新）、接口 GET /teacher_assist/drafts |
| teacher_assist | 652 行 / 64KB | 约 890 行 | 对话 + 助手页的页面函数 + 记一条 |

依赖：teacher_assist → assist_draft → {assist_setting → assist_common, assist_kg}；teacher_assist → assist_common。无环。
接口路径、动作名全部不变；只有 `GET /teacher_assist/drafts` 的函数改归 assist_draft（路由文件挪到 routes/assist_draft.zs）。

行为上唯一的位置变化：确认草稿 / 撤销草稿（assist_draft）不再写对话，只返回 summary；teacher_assist 的 确认草稿页面 /
撤销草稿页面 拿到 summary 后调 记一条 写进对话（用例里那三行「库 teacher_assist_message 含 …」随之从 确认草稿 / 撤销草稿 的用例
挪到了 确认草稿页面_正常、撤销草稿页面_正常）。

## 现在的回归状态（约定领先实现）

约定检查 17 个模块全过；plan/top.zs 能解析；全局检查 0 重复；加载检查 0 问题；xcall 2585 处 0 不一致、top 0 问题、提供 0 未列；
gen build 97 个接口；初始化脚本照常。全量回归 12/17，预期失败 5 个模块、189 条用例：

| 模块 | 失败 | 原因 |
|---|---|---|
| assist_common | 20/20 | 没有 services/assist_common.zs |
| assist_kg | 9/9 | 没有 services/assist_kg.zs |
| assist_setting | 8/8 | 没有 services/assist_setting.zs |
| assist_draft | 149/149 | 没有 services/assist_draft.zs |
| teacher_assist | 3/57 用例 + 比对约定 | 用例：问助手_兜底判出改设定只生成草稿不写库、问助手_兜底判出加知识点只生成草稿不写库、跨科目_问助手只读老师让助手改设定回模板话（P1b 的判意图兜底，拆分前就不过）；比对约定：业务文件依赖与约定不一致，多出 匹配学生、匹配知识点、7 个草稿公开函数和接口 GET /teacher_assist/drafts |

其余 12 个模块全过。tests/kg_v4/test_assist_drafts.py 现在还按旧代码跑（55/0），第 1 步之后要改调用的模块名（见下）。

## 步骤

每一步结束都跑：`.venv/bin/python tests/kg_v4/test_project.py`（只看本步涉及的模块）、`.venv/bin/python tests/kg_v4/test_xcall.py`。
v3 的用法同 P1：`python -m tools.dslagent v3 fix2 --req kg_v4/req.md --project kg_v4 --out <记录目录> --modules <模块> --rounds 3 --cost-cap 5`
（fix2 = 循环 audit2 → change2；change2 的修改代理只看得到「本模块约定 + 上游公开函数头 + 本模块与上游的 entities + 本模块现有文件」，
看不到别的模块的服务代码，所以**搬家不交给模型**，用第 1 步的脚本做）。

### 第 1 步：程序搬家（脚本，不调模型，约 0 元）

一个 Python 脚本（放 data/tmp/，按字节读写、保留 LF、每个锚点 assert 只出现一次），一次做完：

1. 新建 services/assist_common.zs：头部 `业务 assist_common / 依赖 account subject kg / 用包 db common text`；从 teacher_assist.zs
   原样复制 本科目（5 行）、学生范围（24）、匹配学生（122）、匹配知识点（153）；学生范围 改成 `公开 函数 学生范围 learner? current_role? auth_mode? subject?`
   并在开头加 本科目 解析、结尾改返回 {total, students}（约 +6 行；匹配学生 里 `调用 学生范围 subject_id=…` 改成取 `.students`）。
   查询：复制 teacher_assist_len.sql、teacher_assist_lower.sql 为 assist_common_len.sql、assist_common_lower.sql，服务里引用改名。
2. 新建 services/assist_draft.zs：头部依赖照约定；复制 本科目、状态名 … 草稿按钮（1094–1194）、出题候选条目 … 撤销草稿（1203–2090），
   **不带** 记一条 和 4 个页面函数；删掉 确认草稿 / 撤销草稿 里两行 `设 mid = 调用 记一条 …`（mid 没被用）；
   `调用 匹配学生` / `调用 匹配知识点` 改成 `调用 assist_common.匹配学生` / `assist_common.匹配知识点`（6 处）。
   查询：`git mv` teacher_assist_draft_*.sql（11 个）→ assist_draft_*.sql（去掉中间的 draft_，如 assist_draft_get.sql），
   teacher_assist_can_undo.sql、teacher_assist_token.sql → assist_draft_can_undo.sql、assist_draft_token.sql；
   复制 teacher_assist_nl / substr / len.sql 为 assist_draft_nl / substr / len.sql；服务里引用全部改名。
3. teacher_assist.zs：删掉上面搬走的函数（学生范围、匹配学生、匹配知识点、状态名 … 草稿按钮、出题候选条目 … 撤销草稿，约 1300 行），
   保留 记一条 和 4 个页面函数；`调用 匹配学生/匹配知识点` → assist_common（3 处），`调用 列草稿/生成草稿/取草稿/确认草稿/放弃草稿/撤销草稿`
   → `调用 assist_draft.…`（页面函数和 问助手、列对话页面 里共约 9 处）；依赖行改成约定的依赖。
4. routes：teacher_assist.zs 删掉 `GET /teacher_assist/drafts` 那段，新建 routes/assist_draft.zs 放这一段（调用改成 assist_draft.列草稿）。
5. tests/kg_v4/test_assist_drafts.py：`P.closure(ws, "teacher_assist")` 不变（闭包已含 assist_draft）；`run()` 里
   `K.call(eng, "teacher_assist", …)` 改成 `"assist_draft"`（它只调 生成/确认/放弃/撤销草稿，不查对话表），一处。

预计改动：新增约 1350 行（搬过去的）、删除约 1300 行，手写的改动约 30 行。预计结果：assist_common 除 学生范围 两条外全过；assist_draft 的 P1
用例（约 90 条）全过，P1b 的（约 55 条，setting_save / kg_add 相关）和 按消息列草稿 / 挂回消息 4 条不过；teacher_assist 剩 学生范围 取值、
挂回消息、按消息列草稿、页面函数写 记一条 几处不过。这一步没有模型参与，不存在「装不下」。

### 第 2 步：fix2 assist_common（约 20–40 行改动）

问题只剩 学生范围 的返回形状和 2 条新用例。约定 14KB + 服务约 310 行，远低于 change2 的预算（本模块文件 150KB）。预计 1 轮、$0.5–1。

### 第 3 步：fix2 assist_kg（新写约 470 行）

模块是空的，change2 照约定全文写一个新文件；输入只有约定 17KB + kg / subject 的公开函数头 + entities，比 P1 批 2 的单次改动（约 1000 行）小一半。
`--max-turns 30`，预计 1–2 轮、$1.5–3。

### 第 4 步：fix2 assist_setting（新写约 480 行）

同第 3 步；上游多 assist_common（第 2 步已过）、teacher_rules。预计 1–2 轮、$1.5–3。第 3、4 步互不依赖，可以并行。

### 第 5 步：fix2 assist_draft（改约 280 行，文件约 1000 → 1270 行）

要做：按消息列草稿、挂回消息两个新公开函数（约 40 行，查询用第 1 步搬来的 assist_draft_by_source / assist_draft_source）；P1b 分派——
校验草稿 的 setting_save / kg_add 分支（调 assist_setting / assist_kg 的校验，约 20 行）、生成草稿 的两种备料与提示词（约 100 行）、
取草稿 的两种 result_text 和 compare_text（约 80 行）、确认草稿 / 撤销草稿 的分派、snapshot 落库（新查询 assist_draft_finish_snap.sql）
与 summary（约 50 行）。输入：约定 127KB + 服务约 45KB + 上游函数头，约为 K131b 失败时（约定 215KB + 服务 88KB）的一半多一点，
改动量约为它的四分之一。预计 1–2 轮、$2–4。
依赖第 2–4 步（上游函数要先存在，否则 P1b 用例跑不过）。
如果单轮还是轮数用尽：再跑一轮 fix2（changed 不为空就会有进展），不要改约定拆批（K127：同模块暂存约定会自相矛盾）。

### 第 6 步：fix2 teacher_assist（改约 60–80 行，文件约 830 → 890 行）

要做：学生范围 调用改取 `.students`（3 处）；问助手 写完一轮后 `调用 assist_draft.挂回消息`（替换 teacher_assist_draft_source 那行）；
列对话页面 改用 `assist_draft.按消息列草稿` 一次取回按钮（替换逐条查 teacher_assist_draft_by_source）；确认草稿页面 / 撤销草稿页面 加
`调用 记一条 content=r.summary`；P1b 的判意图兜底 ②b ②c、问助手 文案、chitchat 功能说明与 答一轮 规则⑤（这 3 条用例拆分前就不过）。
约定 64KB + 服务约 35KB。预计 1 轮、$1–2。依赖第 5 步。

### 第 7 步：整体验证

- `tests/kg_v4/test_project.py` 全绿（回归 17/17）；`tests/kg_v4/test_xcall.py` 0 不一致；`tests/kg_v4/test_assist_drafts.py` 全过。
- 教师助手的 e2e 在 `tests/kg_v4/e2e_walk.py` 的教师助手段（6aa3dba 加的；动作名、接口路径没变，应当不用改）。P1b 计划「批后验证」里写的
  `tests/e2e/teacher_assist_run.js` 并不存在，那两段（设定草稿、知识点草稿）要追加到 e2e_walk.py 的教师助手段。
- `bash tests/run_all.sh` 不退化；真模型冒烟同 P1b 计划。
- 正式库：teacher_assist_draft 表名、列都没变，不需要迁移；只是建表语句从 entities/assist_draft.entity 来。

## 费用与行数汇总

| 步 | 方式 | 改动行数（预计） | 单次输入量 | 预计费用 |
|---|---|---|---|---|
| 1 | 脚本搬家 | 搬约 1300 行 + 手改约 30 行 | — | 0 |
| 2 | fix2 assist_common | 20–40 | 约 30KB | $0.5–1 |
| 3 | fix2 assist_kg | 新写约 470 | 约 40KB | $1.5–3 |
| 4 | fix2 assist_setting | 新写约 480 | 约 45KB | $1.5–3 |
| 5 | fix2 assist_draft | 约 280 | 约 180KB | $2–4 |
| 6 | fix2 teacher_assist | 60–80 | 约 105KB | $1–2 |

合计约 $6.5–13，6 步（1 步脚本 + 5 步 fix2）。每步单个 change2 的改动量都不超过约 500 行，最大的输入（第 5 步）也比 K131b 失败时小约四成。

## P2–P4 落点（规划，不写约定）

- P2 上传文件 → 新模块 assist_file（表 teacher_assist_file）；teacher_assist 依赖它（`/teacher_assist/ask` 的上传字段仍在 问助手页面）；
  「依据文件出题」由 teacher_assist 把附件文本作为新入参交给 assist_draft.生成草稿，assist_draft 不依赖 assist_file。
- P3 教学材料 → 新模块 assist_material（表 teacher_assist_material、ui/teacher_material.ui）；「练习转出题草稿」依赖 assist_draft；
  teacher_assist 依赖它。
- P4 深度学情 → 新模块 assist_insight（不建表；依赖 progress report quiz assist_common subject）；「给掉队学生发传达」由 teacher_assist
  先取名单再交给 生成草稿。
- 新的草稿类型一律各自成模块（同 assist_setting / assist_kg 的形状：校验 / 执行 / 撤销，入参 JSON，不碰草稿表），assist_draft 只加分派。
