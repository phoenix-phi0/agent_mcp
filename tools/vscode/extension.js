// agent_mcp 编排查看器的 VS Code 插件：在本机 VS Code 里连流程管理服务（tools/wf_mcp_server.py 的查看器那部分）。
// - 侧边栏「编排运行」：按 等确认 / 运行中 / 出错 / 完成 分组，定时刷新；点一项打开那次运行的页面
// - 运行页：查看服务给的页面放进 Webview，页面的请求经插件转发（只放行 api/runs、api/run、api/plan 和写操作）
// - 有运行新停下来等确认：弹通知；状态栏常驻待确认个数
// - 页面里点「在编辑器里打开」：把流程脚本开成只读文档，跳到那一行
// 访问口令存在 VS Code 的加密存储（SecretStorage），设置里只有地址。
"use strict";

const vscode = require("vscode");
const core = require("./lib/core");
const { buildWebviewHtml } = require("./lib/webview");

const SECRET = "agentMcp.viewerToken";
const SCHEME = "agentmcp-wf";

let ctx, tree, status, timer, waitKeys = null, lastRuns = [], lastError = null;
const panels = new Map();          // 运行名 → WebviewPanel
const scripts = new Map();         // 虚拟文档的 uri → 脚本全文

// ---------- 连接 ----------
async function connection() {
  const base = vscode.workspace.getConfiguration("agentMcp").get("viewerUrl") || "";
  if (!base) return null;
  const token = (await ctx.secrets.get(SECRET)) || "";
  return { base, token, root: core.rootUrl(base, token) };
}

async function request(conn, path, init) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 20000);
  try {
    // 服务端每个回应都带 Cache-Control: no-store；Node 的 fetch 不认 cache 选项，不传
    const r = await fetch(conn.root + path, Object.assign({ signal: ctl.signal }, init || {}));
    return { status: r.status, body: await r.text() };
  } catch (e) {
    throw new Error(e.name === "AbortError" ? "20 秒没有回应" : (e.cause && e.cause.code) || e.message);
  } finally {
    clearTimeout(t);
  }
}

async function cmdConnect() {
  const cur = await connection();
  const link = await vscode.window.showInputBox({
    title: "连接编排查看器",
    prompt: "粘贴查看器链接，如 https://ali-demo.yscinternet.top/trace/<口令>/ ，本机服务可以是 http://127.0.0.1:8765/",
    value: cur ? cur.base + "/" : "",
    ignoreFocusOut: true,
    validateInput: (v) => { try { core.parseViewerLink(v); return null; } catch (e) { return e.message; } },
  });
  if (!link) return;
  const { base, token } = core.parseViewerLink(link);
  await vscode.workspace.getConfiguration("agentMcp").update("viewerUrl", base, vscode.ConfigurationTarget.Global);
  if (token) await ctx.secrets.store(SECRET, token);
  else await ctx.secrets.delete(SECRET);
  waitKeys = null;
  await refresh(true);
  if (!lastError) vscode.window.showInformationMessage(`已连接编排查看器：${base}（${lastRuns.length} 次运行）`);
}

async function cmdDisconnect() {
  await ctx.secrets.delete(SECRET);
  await vscode.workspace.getConfiguration("agentMcp").update("viewerUrl", undefined, vscode.ConfigurationTarget.Global);
  lastRuns = []; lastError = null; waitKeys = null;
  tree.fire(); updateStatus();
}

// ---------- 刷新：列表、状态栏、通知 ----------
async function refresh(manual) {
  const conn = await connection();
  if (!conn) { lastRuns = []; lastError = null; tree.fire(); updateStatus(); return; }
  try {
    const r = await request(conn, "api/runs");
    if (r.status !== 200) throw new Error(r.status === 404 ? "地址或口令不对（404）" : "HTTP " + r.status);
    lastRuns = JSON.parse(r.body).runs || [];
    lastError = null;
  } catch (e) {
    lastError = e.message;
    if (manual) vscode.window.showErrorMessage("连不上编排查看器：" + e.message);
  }
  if (!lastError) notifyWaiting();
  tree.fire();
  updateStatus();
}

function notifyWaiting() {
  const { keys, fresh } = core.newlyWaiting(waitKeys, lastRuns);
  waitKeys = keys;
  if (!vscode.workspace.getConfiguration("agentMcp").get("notify", true)) return;
  for (const r of fresh) {
    const where = r.current && r.current.name ? `第 ${r.waiting_step} 步「${r.current.name}」` : `第 ${r.waiting_step} 步`;
    vscode.window.showInformationMessage(`编排运行 ${r.name.replace(/\.json$/, "")} 停在${where}，等确认`, "打开").then((pick) => {
      if (pick) openRun(r.name);
    });
  }
}

function updateStatus() {
  if (lastError) {
    status.text = "$(debug-disconnect) 编排：连不上";
    status.tooltip = lastError;
    status.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
    status.command = "agentMcp.refresh";
    status.show();
    return;
  }
  const waiting = lastRuns.filter((r) => r.status === "waiting");
  const running = lastRuns.filter((r) => r.status === "running" && r.alive !== false);
  status.backgroundColor = waiting.length ? new vscode.ThemeColor("statusBarItem.warningBackground") : undefined;
  status.command = "agentMcp.openWaiting";
  if (waiting.length) {
    status.text = `$(debug-pause) ${waiting.length} 个待确认`;
    status.tooltip = waiting.map((r) => r.name.replace(/\.json$/, "") + "：" + core.describe(r)).join("\n");
  } else if (running.length) {
    status.text = `$(sync~spin) ${running.length} 个运行中`;
    status.tooltip = running.map((r) => r.name.replace(/\.json$/, "") + "：" + core.describe(r)).join("\n");
  } else {
    status.hide();
    return;
  }
  status.show();
}

function restartTimer() {
  if (timer) clearInterval(timer);
  const sec = Math.max(2, Number(vscode.workspace.getConfiguration("agentMcp").get("refreshSeconds")) || 5);
  timer = setInterval(() => refresh(false), sec * 1000);
}

// ---------- 侧边栏 ----------
class RunTree {
  constructor() { this.emitter = new vscode.EventEmitter(); this.onDidChangeTreeData = this.emitter.event; }
  fire() { this.emitter.fire(); }
  getTreeItem(el) { return el; }
  async getChildren(el) {
    if (!(await connection())) return [];          // 没连：显示 viewsWelcome 里的「连接」按钮
    if (lastError) {
      const it = new vscode.TreeItem("连不上：" + lastError);
      it.iconPath = new vscode.ThemeIcon("warning");
      it.command = { command: "agentMcp.refresh", title: "重试" };
      return [it];
    }
    if (!el) {
      if (!lastRuns.length) return [new vscode.TreeItem("还没有运行记录")];
      return core.groupRuns(lastRuns).filter((g) => g.runs.length).map((g) => {
        const open = g.key === "waiting" || g.key === "running";
        const it = new vscode.TreeItem(`${g.label}（${g.runs.length}）`,
          open ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.Collapsed);
        it.id = "group:" + g.key;
        it.group = g;
        return it;
      });
    }
    return el.group.runs.map((r) => {
      const st = core.runState(r);
      const it = new vscode.TreeItem(r.name.replace(/\.json$/, ""));
      it.id = "run:" + r.name;
      it.description = (r.workflow ? r.workflow + "　" : "") + core.describe(r);
      it.iconPath = new vscode.ThemeIcon(st[2]);
      const tip = new vscode.MarkdownString();
      tip.appendMarkdown(`**${r.name}**\n\n`);
      tip.appendText(`${r.workflow || ""}　${core.describe(r)}\n`);
      if (r.calls != null) tip.appendText(`${r.calls} 次调用${r.errors ? "，" + r.errors + " 次出错" : ""}\n`);
      if (r.cost_spent != null) tip.appendText(`成本 ${r.cost_spent}${r.usd_spent != null ? "（$" + Number(r.usd_spent).toFixed(2) + "）" : ""}\n`);
      if (r.error) tip.appendText(`出错：${r.error}\n`);
      if (r.goal) tip.appendText(`\n${r.goal}`);
      it.tooltip = tip;
      it.contextValue = st[0] === "waiting" ? "run.waiting" : "run";
      it.command = { command: "agentMcp.openRun", title: "打开", arguments: [r.name] };
      return it;
    });
  }
}

// ---------- 运行页 ----------
function themeKind() {
  const k = vscode.window.activeColorTheme.kind;
  return k === vscode.ColorThemeKind.Light || k === vscode.ColorThemeKind.HighContrastLight ? "light" : "dark";
}

async function openRun(name) {
  if (!name) return;
  const conn = await connection();
  if (!conn) return cmdConnect();
  const have = panels.get(name);
  if (have) { have.reveal(); return; }
  const panel = vscode.window.createWebviewPanel("agentMcp.run", "运行 " + name.replace(/\.json$/, ""),
    vscode.ViewColumn.Active, { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
  panel.iconPath = new vscode.ThemeIcon("type-hierarchy");
  let key = name;
  panels.set(key, panel);
  panel.onDidDispose(() => { if (panels.get(key) === panel) panels.delete(key); });
  panel.webview.onDidReceiveMessage(async (m) => {
    if (m.type === "fetch") {
      const bad = core.checkPageRequest(m.url, m.method);
      if (bad) { panel.webview.postMessage({ type: "fetch-result", id: m.id, error: bad }); return; }
      try {
        const c = await connection();
        const init = { method: m.method };
        if (m.method === "POST") { init.headers = { "Content-Type": "application/json" }; init.body = m.body || ""; }
        const r = await request(c, m.url, init);
        panel.webview.postMessage({ type: "fetch-result", id: m.id, status: r.status, body: r.body });
        if (m.method === "POST") setTimeout(() => refresh(false), 500);     // 写完了，侧边栏也跟着变
      } catch (e) {
        panel.webview.postMessage({ type: "fetch-result", id: m.id, error: e.message });
      }
    } else if (m.type === "open-script") {
      openScript(m);
    } else if (m.type === "view") {
      // 页面里换了运行：标签页标题和登记的名字跟着换；回到列表就写「运行列表」
      if (panels.get(key) === panel) panels.delete(key);
      key = m.run || "(列表)";
      if (!panels.has(key)) panels.set(key, panel);
      panel.title = m.run ? "运行 " + m.run.replace(/\.json$/, "") : "编排运行列表";
    }
  });
  try {
    const r = await request(conn, "");
    if (r.status !== 200) throw new Error("HTTP " + r.status);
    panel.webview.html = buildWebviewHtml(r.body, { run: name, theme: themeKind() });
  } catch (e) {
    panel.webview.html = `<!DOCTYPE html><html><body style="font-family:sans-serif;padding:20px">` +
      `<h3>打不开查看器页面</h3><p>${String(e.message).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))}</p></body></html>`;
  }
}

async function cmdOpenWaiting() {
  const waiting = lastRuns.filter((r) => r.status === "waiting");
  if (!waiting.length) return vscode.commands.executeCommand("agentMcpRuns.focus");
  if (waiting.length === 1) return openRun(waiting[0].name);
  const pick = await vscode.window.showQuickPick(waiting.map((r) => ({ label: r.name.replace(/\.json$/, ""), description: core.describe(r), name: r.name })),
    { title: "等确认的运行" });
  if (pick) openRun(pick.name);
}

async function cmdOpenInBrowser(arg) {
  const conn = await connection();
  if (!conn) return cmdConnect();
  const name = typeof arg === "string" ? arg : arg && arg.id && arg.id.startsWith("run:") ? arg.id.slice(4) : null;
  vscode.env.openExternal(vscode.Uri.parse(conn.root + (name ? "#run=" + encodeURIComponent(name) : "")));
}

// ---------- 流程脚本：只读文档，跳到那一行 ----------
async function openScript(m) {
  const run = String(m.run || "运行").replace(/\.json$/, "").replace(/[^\w.-]+/g, "_");
  const wf = String(m.workflow || "workflow").replace(/[^\w.-]+/g, "_");
  const uri = vscode.Uri.from({ scheme: SCHEME, path: `/${run}/${wf}.wf` });
  scripts.set(uri.toString(), String(m.script || ""));
  scriptProvider.emitter.fire(uri);
  const doc = await vscode.workspace.openTextDocument(uri);
  const line = Math.max(0, Math.min(doc.lineCount - 1, (Number(m.line) || 1) - 1));
  const range = new vscode.Range(line, 0, line, doc.lineAt(line).text.length);
  await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside, preserveFocus: false, preview: true, selection: range });
}

const scriptProvider = {
  emitter: new vscode.EventEmitter(),
  get onDidChange() { return this.emitter.event; },
  provideTextDocumentContent(uri) { return scripts.get(uri.toString()) || ""; },
};

// ---------- 入口 ----------
function activate(context) {
  ctx = context;
  tree = new RunTree();
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  context.subscriptions.push(
    status,
    vscode.window.registerTreeDataProvider("agentMcpRuns", tree),
    vscode.workspace.registerTextDocumentContentProvider(SCHEME, scriptProvider),
    vscode.commands.registerCommand("agentMcp.connect", cmdConnect),
    vscode.commands.registerCommand("agentMcp.disconnect", cmdDisconnect),
    vscode.commands.registerCommand("agentMcp.refresh", () => refresh(true)),
    vscode.commands.registerCommand("agentMcp.openRun", openRun),
    vscode.commands.registerCommand("agentMcp.openWaiting", cmdOpenWaiting),
    vscode.commands.registerCommand("agentMcp.openInBrowser", cmdOpenInBrowser),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("agentMcp.refreshSeconds")) restartTimer();
      if (e.affectsConfiguration("agentMcp.viewerUrl")) { waitKeys = null; refresh(false); }
    }),
    vscode.window.onDidChangeActiveColorTheme(() => {
      for (const p of panels.values()) p.webview.postMessage({ type: "theme", kind: themeKind() });
    }),
    { dispose: () => timer && clearInterval(timer) },
  );
  restartTimer();
  refresh(false);
}

function deactivate() {}

module.exports = { activate, deactivate };
