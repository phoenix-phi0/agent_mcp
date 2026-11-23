# 给 Muse：怎么接 agent_mcp 的活

阿里云上的 agent_mcp（仓库根 `/workspace/agent_mcp`）有两个只存不跑的队列，都等你认领：

| 队列 | 任务目录 | 是什么活 | 怎么交 |
|---|---|---|---|
| **mbatch** | `~/.mbatch/jobs` | 普通批量任务：一条提示词，做完把最后的回复写回 | `set_task` 写回文字，最后 `finish` |
| **musebatch** | `~/.musebatch/jobs` | 编排流程里交给你的一步（角色卡 `model=muse`，如 ENGINEER_MUSE）：流程停在这一步等你 | `set_task` 写回**一个 JSON 对象**，当场校验，合格就交进流程，**不用 finish** |

两个队列的认领、写回用法一样，下面只讲 musebatch 不同的地方。

---

## 一、怎么调

三种写法都行，挑你手边方便的：

- **MCP**（agent_mcp_aliyun 的 `tool_call`，和 `mbatch.*` 并排）：
  `tool_call(name="musebatch.claim", args={"job_id": "…"})`
  可用的名字：`musebatch.describe` `queued` `jobs` `status` `claim` `set_task` `finish` `cancel` `reclaim` `reclaim_stuck`
- **Python**（在仓库根）：`from tools import musebatch as mb; mb.claim("…")`
- **命令行**（在仓库根）：`.venv/bin/python -m tools.musebatch claim <job_id>`

> 白名单刚加了 musebatch，agent_mcp_aliyun 服务重启后 MCP 写法才能用；之前用命令行。

---

## 二、一个流程步骤从头到尾

### 1. 看有没有活

```
musebatch.queued()
```

每项有 `job_id`、`name`（如「流程 20261122-… 第4步 实现」）、`flow`（`run` 运行记录、`step` 第几步、`attempt` 第几次、`card` 角色卡、`format` 交结果的格式），`prompts` 只有前 300 字。

### 2. 认领

```
musebatch.claim(job_id)
```

- 成功：任务变成 `running`，返回整条记录。**完整提示词在 `tasks[0].prompt`**，工作目录在 `cwd`。
- 报「不用做了」：流程已经不等这一步了（别人先交了、退回了、中止了），任务已经被取消。**换下一条，不用做。**
- 报「不是 queued」：已经有人认领过了，别重复做。

### 3. 照提示词做

提示词按顺序是：

1. **角色说明和技能**：你在这一步是谁（比如工程师），按什么顺序做，有哪些禁止事项。
2. **【工作环境】**：项目目录、项目虚拟环境的 python、这次流程的测试命令。
3. **任务和参考文本**：要做什么、接口签名、验收条件。
4. **JSON Schema**：交结果的格式。
5. **【怎么交】**：这条任务的 job_id 和交的写法。

要点：

- 只在 `cwd`（项目目录，`/workspace/agent_mcp/workflow_demo/work/<项目>`）里读写，**不要改目录以外的任何东西**，不要读、不要输出密钥。
- 命令一律用给你的项目 python（`<cwd>/.venv/bin/python -m pytest`）；要装包先写进 `requirements.txt`。
- 每次都是全新的任务：看不到之前的对话和接口约定原文，只能依据这次的任务和参考文本。任务说不清楚就不要硬猜，在结果里写 `status: 部分完成`，并在 `need_architect` 里写清卡在哪里（实现记录格式里有这个字段）。
- 实现记录里的 `verification` 写**你真跑过的**测试结果；没跑就写 `executed: false`。

### 4. 写回结果

```
musebatch.set_task(job_id, 0, output=<结果>)
```

- `output` 是按提示词里 JSON Schema 的**一个 JSON 对象**：MCP 里直接传对象，或者传它的 JSON 文本；不要套代码围栏，不要在前后加说明文字。
- 命令行写法：先把结果写进一个文件，再
  `.venv/bin/python -m tools.musebatch set_task <job_id> 0 --file <文件>`（不给 `--file` 就从标准输入读）。

结果有三种：

| 返回 | 意思 | 你接着做什么 |
|---|---|---|
| `{"ok": true, "status": "done", "next": …}` | 交进流程了，整批已经结束，流程在后台接着往下走 | 完事。**不用 finish**，交完不要再改项目里的文件 |
| 报错「没交上，什么都没写，改了再 set_task：…共 N 条问题」 | 格式不合格，逐条列出了问题。什么都没写，任务还是 running | 照着问题改结果，再调一次 `set_task`，直到合格 |
| 报错「不用交了」 | 你做的时候流程已经不等这一步了，任务已经取消 | 停手，不用再交 |

### 5. 做不了

```
musebatch.set_task(job_id, 0, error="卡在哪里、为什么", status="failed")
```

命令行写法：`set_task <job_id> 0 --failed --error "原因"`。整批会变成 `failed`，流程还停在这一步，等人换卡或换模型处理。同一步同一次不会再给你派新任务。

---

## 三、和 mbatch 不一样的地方（容易做错）

- **一条任务就是一步，只有一条 task**，`index` 永远是 0。
- **output 是结果 JSON，不是聊天回复**。mbatch 写回的是最后的回复原文，musebatch 写回的是按 Schema 的 JSON 对象。
- **合格就结束，不用 finish**。真去调 `finish` 只会回「已经结束了」。如果认领后放弃不做，用 `set_task(..., status="failed")` 写原因，不要用 finish。
- **不合格什么都没写**：可以放心反复改、反复交，不用重新认领。
- **认领后 30 分钟没写回**，`reclaim_stuck` 会把任务退回 queued，下一轮再派。如果流程已经不等了，就直接取消。做大活超过 30 分钟时要知道这一点：被退回以后，你手上那份写回时会报「要先 claim」或「不用交了」。

---

## 四、报错对照

| 报错里有 | 原因 | 怎么办 |
|---|---|---|
| 认领不了：…不是 queued | 已经被认领过或已结束 | 换下一条 |
| 不用做了 | claim 时流程已经不等这一步，任务已取消 | 换下一条 |
| 写不了：…要先 claim | 没认领就写，或者任务被 reclaim_stuck 退回了 | 先 claim（退回的重新认领后再写） |
| 没交上…结果不是 JSON | output 不是合法 JSON | 只写一个 JSON 对象 |
| 没交上…共 N 条问题 | 缺字段、类型不对、取值不在范围内 | 照着逐条改，再 set_task |
| 不用交了 | 写回时流程已经不等这一步 | 停手 |
| 没有这个任务 | job_id 写错 | 用 queued() 给的 job_id |

---

## 五、不经队列的直接写法（备用）

队列不方便的时候，可以直接对运行记录操作，底层是同一套：

```
.venv/bin/python -m tools.muse_flow queue                     # 哪些运行停在等 Muse
.venv/bin/python -m tools.muse_flow show <run>                # 这一步的完整请求（JSON）
.venv/bin/python -m tools.muse_flow submit <run> --step N --attempt A --file <结果文件>
```

退出码：0 已交；1 不合格（打印问题，改了再交）；2 这一步已经不等你了。

用这种写法交了以后，队列里对应的那条任务下次会被自动取消，不用管它。
