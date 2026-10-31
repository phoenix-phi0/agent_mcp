# dslagent v3 实现简报（--brief）与改代码模型（--impl-model）使用说明

K171 起，v3 的 change2 / fix2 可以给改代码的代理（modify_module）附一份「实现简报」，也可以让它换一个模型（如 Haiku）；
核查员（audit2）不变。两样都是开关，不加时行为与以前一样。代码在 `tools/dslagent/v3/brief.py`。

K174 起：简报的依赖接口附上游函数伪代码节选；新增 `--declare`（设计声明 → 写死旧值盘点 + 用例值域检查）；
audit2 / fix2 开头加约定闸 `--contract-check`（默认拦截，见文末）。

## 怎么开

```bash
# 只看简报（不调模型、不改文件）：不给 --modules 时列契约相对 git HEAD 改了的函数
.venv/bin/python -m tools.dslagent v3 brief --project kg_v4 [--modules subject,teacher_assist] [--out /tmp/brief]
#   给 --out 写 brief.json / brief.md；不给就打印 md，最后一行是摘要 JSON

# 修复时附简报、让 Haiku 改代码（核查仍用 --llm，缺省 sonnet）
.venv/bin/python -m tools.dslagent v3 fix2 --req kg_v4/req.md --project kg_v4 --out /tmp/run \
    --modules subject,teacher_assist --rounds 3 --cost-cap 6 --brief --impl-model haiku

# 设计声明（旧值→新来源函数，K168 domain.tsv 格式也认）：写死旧值盘点 + 用例值域检查
.venv/bin/python -m tools.dslagent v3 brief --project kg_v4 --declare /tmp/domain.tsv --out /tmp/brief
```

- `--impl-model <模型串>`：只顶替 modify_module 的默认模型（`roles.zs` 里是 sonnet），模型串写法同 engines.parse（sonnet / opus / haiku / codex:… 等）；
  v2 子进程里规划、派任务、补改都用它。子进程没跑起来时照旧换回退模型（sonnet），记录里会有一条回退说明。
- `--brief`：只对 change2 / fix2 有效（别的 action 加了直接报错退出）。
- `--declare <文件>`：设计声明，对 brief 单独可用、change2 / fix2 要和 --brief 一起。每行一条（# 开头和空行跳过）：
  `旧值<Tab>新来源函数` 或 `旧值 → 新来源函数`（旧值写标签：`enum:N5..N1`、`persona:老师`、`lit:字面量`、`re:正则`，其它当字面量；
  新来源写 `模块.函数`）；K168 /tmp/k168/domain.tsv 的 5 列格式 `改动<Tab>fn:模块.函数<Tab>旧值<Tab>新值域<Tab>依据` 也认；
  另有 `值域<Tab>字段<Tab>来源`（来源 = `科目等级` 或逗号隔开的合法值）给用例值域检查加字段。声明里看不懂的行打进「设计声明问题」，只提醒。
- 两个参数互不依赖，可以只开一个。

## 简报里有什么

每个「本轮要改的函数」一节（任务 = 核查问题里点名的函数 ∪ 契约相对 git HEAD 改了的函数 ∪ services 里还是「报错 未实现」/ 没有的函数；
三者都没有时，只列出了实现要点的函数，不带骨架）：

| 部分 | 内容 | 来源 |
|---|---|---|
| 骨架 | 函数头、必填 / 可选入参、返回（及返回字段）、报错；挂在哪个接口、公开 / 角色、路由原文 | 契约 + `scaffold.route_text`（和生成骨架、比对约定是同一份渲染） |
| 依赖接口 | 伪代码里 `调用 模块.函数` 点到的别模块函数：函数头、返回；读 / 写的表和列，可空列标「（可空）」；K174 起另附被调函数的伪代码节选（每个最多 1500 字，超长截断并注明全文位置；模块里同一上游函数只附一次） | 契约、entities、现有代码调用的查询 |
| 实现要点 | 只有三条规则（见下） | 契约 + 现有代码 + .ui |

实现要点：
- **R1 读可空列**：现有代码 `查一值` / `查一行` 的 SQL 直接 SELECT 可空列、没写 COALESCE（查一行取到的列函数里没用过的不算）；
  或契约伪代码在「读」的分句里提到可空列 / 写了 NULL。写入的分句、函数入参都不算；伪代码已写 COALESCE/IFNULL 就不出。
  提示：查询里写 `COALESCE(列, '') AS 列`（查一值/查一行取到 NULL 会变成文本 None）。
- **R2 按位置传参**（只看现有代码）：`查一值/查一行/查询/写库 app.db q k={v}`，v 是拼接文本、模型输出、调用方传入的文本或库里自由文本列。
  名字像编号 / 用户名 / 日期的（`_id`、`_no`、`code`、`date`、`_at`…）不算。提示：装进对象用 `查一值表` 等传。
- **R6 编辑浮层字段 ⊆ 表格行**：.ui 列表的行动作「打开 浮层」，返回里提到这个列表键的整页函数，每行要带上浮层的全部字段（前端从行上打开浮层不发载入）。

另外，简报 CLI 还给：
- **影响面**：契约 git HEAD vs 工作区，按函数比签名（入参、返回字段）和伪代码。建议 `--modules` = 改动函数所在模块 ∪ 签名变（新增 / 入参或返回字段变 / 取不出字段 / 删除）函数的直接调用方；
  只改伪代码的函数的调用方列为「参考」；直接调用方里自己契约没改的模块提示「可能漏改契约」。
- **只读检查**：`v3/contracts.check` 的结果；「伪代码提到别模块公开函数名却没写 `调用 模块.函数`」。
- **写死盘点**（给了 `--declare` 才做）：按设计声明在约定（函数的返回 + 伪代码）、services/*.zs、ui/*.ui 三处找还写死旧值的行，
  输出「这些位置还写死旧值：文件:行」；新来源函数自己的块、提到新来源函数名的行不算；人设类正则排除「你是想…」这类问句。只是提示。
- **用例数据值域检查**（总是做）：抽用例「先 数据」行的字段值和调用参数（含 rows_json 这类 JSON 参数里的对象），
  能确定值域的字段（内置 level：必须在该用例造的 subject_info.levels 里，没有这行或 levels 为空按 N5..N1；
  设计声明的 值域 行可加字段）和值对不上 → 提醒（可能是约定漏改）。值为空、「全部」这类哨兵值不查；
  用例名里点到这个概念（level →「等级」）的是故意测非法值，不查。只是提醒，不拦截。

## fix2 / change2 里怎么用

- 加 `--brief` 后，开始前先算影响面，写到记录目录 `brief_impact.json / brief_impact.md`、`v3_log.jsonl`（类「简报影响面」），并打印到 stderr。
  K174 起影响面里还带用例值域提醒（总是算）、写死盘点（给了 `--declare` 才算），同样只是提醒。
  **不会自动改 --modules**：看一眼建议，有漏的模块自己加上再跑。
- 每次派 modify_module 前，生成本模块那一节写到 `<out>/brief/<模块>_<n>.json / .md`，经环境变量 `DSLAGENT_BRIEF_FILE` 交给 v2 子进程；
  packs/dslproj 的 materials()（首次改）和 fix_input()（补改）在「本模块约定」之后加一节「本模块实现简报（自动推出，只是提醒）」。
- 核查员（audit2）**拿不到**简报：K169 把要点交给核查员后，核查员把它当契约要求、多改了一轮。
- `v3_log.jsonl` 里「实现简报」一行记每次附没附、写在哪；`agents.jsonl` 记 modify_module 实际用的模型。

## 已知局限

- 规则是正则 + 一跳来源追踪：R2 追不到 `解析JSON` 之后再取字段、跨函数传进来的值；R1 判断「读 / 写」靠分句里的动词，契约措辞不规整时会漏或误报。
  K169 抽样里列出的误报这次都去掉了，但没有重新抽样算准确率。HEAD（f4d417c）上全项目 80 条（R1 40、R2 24、R6 16），K169 版是 137 条。
- R6 只比对契约「返回」文字里的字段名，不看现有查询真的有没有返回这些列。
- 影响面只认 `调用 模块.函数`（和约定检查同一口径），伪代码里只写了函数名的调用看不到（只读检查里的 lint 会提示）。
- 项目不在 git 仓库里时没有影响面，简报也不会因为「契约改了」列函数（只按任务点名和未实现）。
- Haiku 改代码的效果只各跑了一次实验（见 data/reports/kg_K171.md），结论不稳；花费上限 `--cost-cap` 是调用前检查，最后一次调用可能略超。
- 值域检查的科目编号推断靠「先 数据 subject_info 按出现顺序即科目 1、2…（写了 id= 按 id）」和调用参数 subject / subject_id / subj_id，
  用例里「先 调用 建科目 / 保存科目页面」时算不准就只查已知科目；HEAD 上误报 2 条（跨科目造数 payload 里 level=初一）。

## 约定闸（audit2 / fix2 开头，K174）

audit2 / fix2 最开头先跑逐模块 `v3/contracts.check`（不调模型，费用 0）。`--contract-check`：
- **拦截（缺省）**：范围内有违约就立刻写 `plan/audit2.json`：result=contract_issue、issues=违约、contract_check=拦截，
  不跑全量回归、不派核查员。选默认拦截的理由：约定自相矛盾（如 K148 assist_material 改材料_标题为空）时回归和核查都是白花钱，
  而且现在 kg_v4 全项目 0 条违约，干净的流程不会被拖慢。
- **提醒**：照常审完，违约放进 audit2.json 的 contract_warnings（不影响 result）。项目临时不干净、又想先跑完看别的结果时用。
- **关**：不查（同 K174 之前）。
- 给了 `--modules` 时范围外模块的违约不拦，记进 skipped_issues（kind=contract_check）。
- 豁免：在被报的那一行（「表 …」行 / 用例的「调用 …」行）正上方写注释
  `# 约定检查豁免 表名前缀：<理由>` 或 `# 约定检查豁免 可选传空 <入参>：理由`。理由必填；可选传空必须点名入参，
  且只该在「传空和不传本来就是同一件事、用例期望与不传时一致」时用；豁免没对上下一行的违约也报成问题（免得过期）。
  问题文字里故意不提示豁免写法，免得规划模型为了过检查自己加。详法见 `tools/dslagent/v3/contracts.py` 文档。
