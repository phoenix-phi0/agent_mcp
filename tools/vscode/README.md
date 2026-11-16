# agent_mcp 编排查看器（VS Code 插件）

在本机 VS Code 里看流程管理（`tools/wf_mcp_server.py`）的运行，不用 SSH，也不用开浏览器。

## 安装

1. 拿到 `agent-mcp-trace-0.1.0.vsix`（在本目录运行 `npx @vscode/vsce package` 生成）。
2. VS Code 命令面板：「Extensions: Install from VSIX…」，选这个文件。
3. 左边活动栏出现「编排运行」，点「连接查看器」，粘贴查看器链接，如
   `https://ali-demo.yscinternet.top/trace/<口令>/`。口令存在 VS Code 的加密存储里，设置里只记地址。
   本机起的服务（`python -m tools.trace_server …`）填 `http://127.0.0.1:8765/`。

## 能做什么

- 侧边栏按「等确认 / 运行中 / 出错、中止、中断 / 完成」分组列出运行，默认 5 秒刷新（设置 `agentMcp.refreshSeconds`）。
- 点一项打开运行页：概况、分配清单、耗时、流程图和节点详情，和网页上的一样；批准、驳回、改计划也能在这里做
  （服务端开了写接口时）。深浅色跟着 VS Code。
- 有运行新停下来等确认时弹通知（设置 `agentMcp.notify` 可关），状态栏常驻「⏸ N 个待确认」，点一下直接打开。
- 节点详情底部「脚本原文」旁边有「在编辑器里打开」：把这次运行的流程脚本开成只读文档，跳到这个节点那一行。

## 安全

- 运行页放在 Webview 里，不直接连网；页面的请求交给插件去发，而且只放行
  `api/runs`、`api/run`、`api/plan` 这三个读接口和服务端的几个写接口，别的地址一律拒绝。
- Webview 的内容安全策略不许连任何外部地址。

## 测试

```
cd tools/vscode && node --test test/*.test.js
```

`test/webview.test.js` 要 jsdom（`tests/e2e/node_modules`，设 `NODE_PATH`）。
