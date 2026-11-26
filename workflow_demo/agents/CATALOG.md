# 角色卡目录

卡都平放在 `agents/<名字>/`（加载按名字找，不分子目录）；分类写在 `agent.json` 的 `category` 里，
只用来分组显示（`agents` 工具、查看器的换卡下拉）。新加卡时 `category` 从下面几类里选：
架构、分析、会议、实现、测试、验收、记录、人。

验收员、失败分析员、记录员（ACCEPTOR / ACCEPTOR_SENIOR、TRIAGE、SCRIBE）的格式都带「依据」和「把握」：
依据是「出处 + 原文」（代码写 `文件:行`，命令输出写命令名），流程用指令 `check_evidence` 按出处抽查原文；
把握是 高 / 中 / 低，ACCEPTOR 把握低或依据对不上，流程换 ACCEPTOR_SENIOR 重判（见 code_accept.wf）。

## 架构
| 卡 | 模型 | 用在 |
|---|---|---|
| ARCHITECT | sonnet@high | 架构设计、改动方案、重构方案、约定整理（各流程默认） |
| ARCHITECT_GPT | Codex gpt-6.2-astra@medium | 同 ARCHITECT（技能照它复制，改 ARCHITECT 要同步） |
| ARCHITECT_FABLE | Fable@medium | 同 ARCHITECT，顶档 |
| ARCHITECT_GLM | GLM（goose） | 审查、评审会发言（交格式不稳） |
| DESIGNER | sonnet | 前端界面设计 |

## 分析（只读）
| 卡 | 模型 | 用在 |
|---|---|---|
| REFACTOR_ANALYST | Codex gpt-6.2-sol | 重构前的现状分析 |
| SITE_SURVEYOR | sonnet | 老站现状摸底（测试流程） |
| TRIAGE | sonnet@medium | 失败分析：拿对照失败和诊断（test_report）的结果，判断新挂的原因和出处：这次的改动、别人的改动、环境、原来就有、测试本身（格式 failure_analysis） |

## 会议
| 卡 | 模型 | 用在 |
|---|---|---|
| MODERATOR | sonnet | 主持会议：每轮判断、写结论 |

## 实现
| 档 | 卡 |
|---|---|
| 便宜 | ENGINEER_LITE（haiku）、ENGINEER_GPT_LITE（Codex）、ENGINEER_DS_LITE（DeepSeek）、ENGINEER_GO_LITE（Go 项目） |
| 中档 | ENGINEER（sonnet）、ENGINEER_MUSE（Muse，流程里的中档默认用它）、ENGINEER_GPT（Codex）、ENGINEER_DS（DeepSeek）、ENGINEER_GO（Go 项目） |
| 高档 | ENGINEER_SENIOR（opus）、ENGINEER_GPT_SENIOR（Codex astra）、ENGINEER_FABLE（Fable） |
| 前端 | FRONTEND_ENGINEER |
| 仓库 | REPO_ENGINEER（Muse）：在 agent_mcp 的 git 工作树里改代码，改代码验收流程的默认工程师 |

`MUSE` 也是 Muse 工程师，是早先另一种接法的卡，和 ENGINEER_MUSE 重复，留待决定。

## 测试
| 卡 | 用在 |
|---|---|
| TEST_ENGINEER | 给已实现的功能补测试（不改实现） |
| TEST_ENGINEER_GO | 同上，Go 项目 |
| SITE_TESTER | 老站补特征测试、搭测试环境（只写 tests_char/） |

## 验收和审查
| 卡 | 用在 |
|---|---|
| QA_ENGINEER | 模块验收、集成验收、基线核对（各流程默认） |
| QA_GPT | 同上，Codex |
| QA_ENGINEER_GO | 同上，Go 项目 |
| QA_PLATFORM | 同上，走 Claude Platform |
| FRONTEND_QA | 前端页面验收、整体验收 |
| SITE_QA | 老站测试环境核对、特征测试验收、稳定性检查 |
| REVIEWER_GPT | 方案审查、评审会发言 |
| ACCEPTOR | 验收员（中档，Codex sol，只读）：按清单读代码和命令输出逐条验收（格式 accept_check）；和工程师 Muse 不是同一个模型 |
| ACCEPTOR_SENIOR | 高档验收员（Codex astra，只读）：ACCEPTOR 把握低或依据对不上时重判 |

## 记录
| 卡 | 用在 |
|---|---|
| SCRIBE | 记录员（haiku）：写提交说明、汇总报告（格式 record_note）；写出来的先过查密钥再用 |

## 人
| 卡 | 用在 |
|---|---|
| HUMAN | 人：流程停下等人交结果、会议里人发言 |

## 机械步骤（不调模型，没有卡）
- 节点里写 `指令 命令名 键=值 …`，由内置的 ROBOT 执行；卡上不能写 `model: "cmd"`。
- 能用的命令是命令表（`tools/cmd_table.json`）里调用方 `workflow` 放行的：只读命令和几条跑测试的命令；提交、推送、重启服务不在里面。
