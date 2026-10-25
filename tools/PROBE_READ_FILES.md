# 探针多文件读取（read_files）

`gsb_tools_mcp.py` 支持 `GSB_TOOLS_ONLY=read_files`：stdio MCP 只暴露 `read_files`，schema 很小。

## 后端选择（gsbatch / gsb_tools）

| 开关 | 效果 |
|------|------|
| `probe=True` / `"claude"`（默认） | Claude CLI `claude-haiku-5-5`，`--permission-mode plan` |
| `probe="codex"` | Codex CLI `gpt-6-luna`，`-s read-only` |
| `GSB_PROBE_BACKEND=claude\|codex` | 扩展进程内选后端（未设默认 claude；gsbatch 总是显式带上） |
| `GSB_PROBE_MODEL=…` | 覆盖默认模型 |
| `GSB_PROBE_READ_FILES=0` | 不挂 gsb_read_files MCP |

Review 始终走 Codex（`GSB_REVIEW_MODEL`，默认 `gpt-6-luna`），不受 probe 后端影响。

## Claude CLI 探针（默认）

配置（`tools/` 下）：
- `probe_claude_mcp.json` — 只挂 `gsb_read_files`
- `probe_claude_settings.json` — `disableClaudeAiConnectors: true`
- `probe_claude_run.py` — 启动器：`--strict-mcp-config` + 上述配置 + `ENABLE_CLAUDEAI_MCP_SERVERS=0`，把 JSON `result` 写到 reply 文件

工具名在 Claude 里一般是 `mcp__gsb_read_files__read_files`。内置工具：`Read,Glob,Grep,Bash`。

独立冒烟脚本仍可参考 `data/tmp/haiku_vs_luna_probe/run_one_claude.sh`。

## Codex 探针（`probe="codex"`）

`probe()` / `_codex_start` 默认通过 `-c mcp_servers.gsb_read_files.*` 挂同一脚本（`GSB_TOOLS_ONLY=read_files`）。
开场说明第 5 条提示优先用 `read_files`。

不改全局 `~/.codex/config.toml` / `claude mcp`。
