# Claude Platform 自托管 worker（角色卡 `platform:` 模型用）

角色卡写 `"model": "platform:claude-sonnet-5-5"` 时，引擎经 `tools/platform_agent.py` → `tools/platform_runner.py`
建托管 agent 会话；模型在 Anthropic 那边推理，bash / 读写文件这些工具由这台机器上的 worker 在沙箱里执行。

## 文件

| 文件 | 装到 | 作用 |
|---|---|---|
| `ali-platform-worker.service` | `/etc/systemd/system/` | `ant beta:worker poll`，systemd 层隔离：看不见 /root、/home、别的进程，全盘只读，只有 `workflow_demo/work` 和 `/var/lib/wfplat` 可写 |
| `on_work.sh` | `/opt/wfplat/on_work.sh`（755） | 每个会话一次：按登记进项目目录，单独挂载命名空间（work/ 只读、只有本项目可写）+ PID 命名空间，丢掉挂载权限后跑 `ant beta:worker run` |

```bash
sudo install -m 755 scripts/wfplat/on_work.sh /opt/wfplat/on_work.sh      # 每个会话启动时才读，不用重启
sudo install -m 644 scripts/wfplat/ali-platform-worker.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ali-platform-worker
```

## 密钥（不进仓库）

- `/root/.config/agent_mcp/platform_env`（600）：`ANTHROPIC_ENVIRONMENT_ID=env_…`、`ANTHROPIC_ENVIRONMENT_KEY=…`，只给 worker 服务读。
- `/root/.config/agent_mcp/platform_api_key`（600）：API 密钥，`platform_runner.py` 读出来显式传给 SDK。
  **不要设 `ANTHROPIC_API_KEY` 环境变量**：本机的 `claude -p`（CBatch、claude 卡）会跟着改成按 API 计费。

## 要知道的

- worker 一次只跑一个会话，流程里同时有几步用 platform 卡会排队。
- 运行记录的 usage：`active_seconds` 只算模型推理；`non_model_seconds` = 总时间 − 推理时间，主要是 worker 上跑测试等工具的时间；
  `reads` 是读代码的次数（卡上 `agentic.min_reads` 用它兜底）；`list_cost` 是平台报的标价。
- 运行器依赖 `/opt/platform_venv`（装了 anthropic SDK），引擎进程不加载 SDK。
