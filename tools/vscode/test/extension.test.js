// extension.js 的测试：require("vscode") 换成假的，fetch 换成假的查看服务。
// 看连接、侧边栏分组、状态栏、新停下来的通知、运行页转发请求、在编辑器里打开脚本、标签页标题。
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const Module = require("module");

const TOKEN = "pPIAHbZeIaLzKRUHw5ZMbKmWvjgMhd45";
const LINK = `https://ali-demo.yscinternet.top/trace/${TOKEN}/`;
const ROOT = `https://ali-demo.yscinternet.top/trace/${TOKEN}/`;

// ---------- 假的 vscode ----------
function makeVscode() {
  const S = { config: {}, secrets: {}, commands: {}, info: [], errors: [], panels: [], shown: [], inputs: [], quick: null,
              tree: null, status: null, provider: null, external: [] };
  class EventEmitter { constructor() { this.l = []; this.event = (f) => { this.l.push(f); return { dispose() {} }; }; } fire(x) { this.l.forEach((f) => f(x)); } }
  class TreeItem { constructor(label, state) { this.label = label; this.collapsibleState = state; } }
  class ThemeIcon { constructor(id) { this.id = id; } }
  class ThemeColor { constructor(id) { this.id = id; } }
  class MarkdownString { constructor() { this.value = ""; } appendMarkdown(s) { this.value += s; } appendText(s) { this.value += s; } }
  class Range { constructor(a, b, c, d) { this.start = { line: a, character: b }; this.end = { line: c, character: d }; } }
  const Uri = {
    parse: (s) => ({ toString: () => s }),
    file: (p) => ({ fsPath: p, toString: () => "file://" + p }),
    from: (o) => ({ scheme: o.scheme, path: o.path, toString: () => o.scheme + ":" + o.path }),
  };
  const vscode = {
    EventEmitter, TreeItem, ThemeIcon, ThemeColor, MarkdownString, Range, Uri,
    TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
    StatusBarAlignment: { Left: 1, Right: 2 }, ConfigurationTarget: { Global: 1 }, ViewColumn: { Active: -1, Beside: -2 },
    ColorThemeKind: { Light: 1, Dark: 2, HighContrast: 3, HighContrastLight: 4 },
    ProgressLocation: { Notification: 15 },
    window: {
      showOpenDialog: async (o) => { S.dialogs = (S.dialogs || []).concat([o]); return S.nextFolder ? [{ fsPath: S.nextFolder }] : undefined; },
      showWarningMessage: async (msg, ...items) => { S.warnings = (S.warnings || []).concat([[msg, items]]); return S.nextWarning; },
      withProgress: async (o, f) => { S.progress = (S.progress || []).concat([o.title]); return f(); },
      createOutputChannel: () => (S.output = { lines: [], shown: 0, appendLine(x) { this.lines.push(x); }, show() { this.shown++; } }),
      activeColorTheme: { kind: 1 },
      createStatusBarItem: () => (S.status = { text: "", visible: false, show() { this.visible = true; }, hide() { this.visible = false; }, dispose() {} }),
      registerTreeDataProvider: (id, p) => { S.tree = p; return { dispose() {} }; },
      showInformationMessage: (msg, ...items) => { S.info.push([msg, items]); return Promise.resolve(undefined); },
      showErrorMessage: (msg) => { S.errors.push(msg); return Promise.resolve(); },
      showInputBox: async (o) => { S.inputs.push(o); return Array.isArray(S.nextInput) ? S.nextInput.shift() : S.nextInput; },
      showQuickPick: async (items, o) => {
        S.quick = items;
        if (o && o.canPickMany) return items.filter((x) => x.picked);
        return items[0];
      },
      createWebviewPanel: (type, title, col, opts) => {
        const p = { type, title, opts, sent: [], disposeL: [], msgL: null, revealed: 0,
          webview: { html: "", postMessage(m) { p.sent.push(m); return Promise.resolve(true); }, onDidReceiveMessage(f) { p.msgL = f; } },
          onDidDispose(f) { p.disposeL.push(f); }, reveal() { p.revealed++; } };
        S.panels.push(p);
        return p;
      },
      showTextDocument: async (doc, o) => { S.shown.push([doc, o]); },
      onDidChangeActiveColorTheme: () => ({ dispose() {} }),
    },
    workspace: {
      workspaceFolders: undefined,
      updateWorkspaceFolders: (i, n, f) => { S.added = f; return true; },
      getConfiguration: () => ({
        get: (k, d) => (("agentMcp." + k) in S.config ? S.config["agentMcp." + k] : d),
        update: async (k, v) => { if (v === undefined) delete S.config["agentMcp." + k]; else S.config["agentMcp." + k] = v; },
      }),
      registerTextDocumentContentProvider: (scheme, p) => { S.provider = p; return { dispose() {} }; },
      openTextDocument: async (uri) => {
        const text = S.provider.provideTextDocumentContent(uri);
        const lines = text.split("\n");
        return { uri, text, lineCount: lines.length, lineAt: (i) => ({ text: lines[i] }) };
      },
      onDidChangeConfiguration: () => ({ dispose() {} }),
    },
    commands: {
      registerCommand: (id, f) => { S.commands[id] = f; return { dispose() {} }; },
      executeCommand: async (id, ...a) => (S.commands[id] ? S.commands[id](...a) : undefined),
    },
    env: { openExternal: async (u) => { S.external.push(u.toString()); return true; } },
  };
  return { vscode, S };
}

// ---------- 假的查看服务 ----------
const svc = { runs: [], fetched: [], submitReplies: [] };
global.fetch = async (url, init) => {
  init = init || {};
  svc.fetched.push({ url, method: init.method || "GET", headers: init.headers, body: init.body });
  if (!url.startsWith(ROOT)) return { status: 404, text: async () => "{}" };
  const rest = url.slice(ROOT.length);
  if (rest === "") return { status: 200, text: async () => "<!DOCTYPE html><html><head><title>t</title></head><body><script>var LIVE=1</script></body></html>" };
  if (rest === "api/runs") return { status: 200, text: async () => JSON.stringify({ dir: "runs", runs: svc.runs }) };
  if (rest.startsWith("api/run?")) return { status: 200, text: async () => JSON.stringify(svc.run || { _name: "a.json" }) };
  if (rest.startsWith("api/workfiles?")) return { status: svc.workfilesStatus || 200, text: async () => JSON.stringify(svc.workfiles) };
  if (rest === "api/submit_files") {
    const reply = svc.submitReplies.shift();
    return { status: reply[0], text: async () => JSON.stringify(reply[1]) };
  }
  if (init.method === "POST") return { status: 200, text: async () => JSON.stringify({ ok: true }) };
  return { status: 404, text: async () => "{}" };
};

const { vscode, S } = makeVscode();
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (req, ...a) { return req === "vscode" ? "vscode" : origResolve.call(this, req, ...a); };
require.cache.vscode = { id: "vscode", filename: "vscode", loaded: true, exports: vscode };
const ext = require("../extension");

const context = { subscriptions: [], secrets: {
  get: async (k) => S.secrets[k], store: async (k, v) => { S.secrets[k] = v; }, delete: async (k) => { delete S.secrets[k]; } } };
const tick = (ms) => new Promise((r) => setTimeout(r, ms || 20));
const labels = async (el) => (await S.tree.getChildren(el)).map((x) => x.label);

test.after(() => { for (const d of context.subscriptions) if (d && d.dispose) d.dispose(); });

test("没连的时候：侧边栏空着（显示连接按钮），状态栏不出", async () => {
  ext.activate(context);
  await tick();
  assert.deepStrictEqual(await S.tree.getChildren(), []);
  assert.strictEqual(S.status.visible, false);
});

test("连接：粘贴链接，地址进设置，口令进加密存储；第一轮不对已经停着的弹通知", async () => {
  svc.runs = [
    { name: "a.json", workflow: "cost_workflow", status: "waiting", waiting_step: 4, current: { step: 4, name: "任务研讨", role: "ARCHITECT_GLM" }, calls: 3 },
    { name: "b.json", workflow: "cost_workflow", status: "running", alive: true, current: { step: 2, name: "接口约定" } },
    { name: "c.json", workflow: "refactor_workflow", status: "done", calls: 9, cost_spent: 22, usd_spent: 0.68, goal: "重构 kg" },
  ];
  S.nextInput = LINK;
  await S.commands["agentMcp.connect"]();
  assert.strictEqual(S.config["agentMcp.viewerUrl"], "https://ali-demo.yscinternet.top/trace");
  assert.ok(!JSON.stringify(S.config).includes(TOKEN), "设置里没有口令");
  assert.strictEqual(S.secrets["agentMcp.viewerToken"], TOKEN);
  assert.ok(S.inputs[0].validateInput("不是地址"), "链接写错时输入框提示");
  assert.strictEqual(S.inputs[0].validateInput(LINK), null);
  assert.ok(svc.fetched.some((f) => f.url === ROOT + "api/runs"), "按 地址/口令/api/runs 请求");
  assert.deepStrictEqual(S.info.map((x) => x[0]), ["已连接编排查看器：https://ali-demo.yscinternet.top/trace（3 次运行）"]);
});

test("侧边栏：按状态分组，等确认和运行中默认展开，每行有状态和所在步", async () => {
  const groups = await S.tree.getChildren();
  assert.deepStrictEqual(groups.map((g) => [g.label, g.collapsibleState]), [["等确认（1）", 2], ["运行中（1）", 2], ["完成（1）", 1]]);
  const waiting = (await S.tree.getChildren(groups[0]))[0];
  assert.strictEqual(waiting.label, "a");
  assert.strictEqual(waiting.description, "cost_workflow　暂停在第 4 步　任务研讨 · ARCHITECT_GLM");
  assert.strictEqual(waiting.iconPath.id, "debug-pause");
  assert.deepStrictEqual(waiting.command, { command: "agentMcp.openRun", title: "打开", arguments: ["a.json"] });
  const done = (await S.tree.getChildren(groups[2]))[0];
  assert.match(done.tooltip.value, /成本 22（\$0\.68）/);
  assert.match(done.tooltip.value, /重构 kg/);
});

test("状态栏：有待确认的就显示个数，点它打开那次运行", async () => {
  assert.strictEqual(S.status.visible, true);
  assert.strictEqual(S.status.text, "$(debug-pause) 1 个待确认");
  assert.strictEqual(S.status.command, "agentMcp.openWaiting");
  await S.commands["agentMcp.openWaiting"]();
  assert.strictEqual(S.panels.length, 1);
  assert.strictEqual(S.panels[0].title, "运行 a");
});

test("又有运行停下来：弹通知；还停在同一步的不再弹", async () => {
  svc.runs[1] = Object.assign({}, svc.runs[1], { status: "waiting", waiting_step: 2 });
  S.info = [];
  await S.commands["agentMcp.refresh"]();
  assert.deepStrictEqual(S.info.map((x) => x[0]), ["编排运行 b 停在第 2 步「接口约定」，等确认"]);
  assert.deepStrictEqual(S.info[0][1], ["打开"]);
  assert.strictEqual(S.status.text, "$(debug-pause) 2 个待确认");
  await S.commands["agentMcp.refresh"]();
  assert.strictEqual(S.info.length, 1);
});

test("运行页：页面从查看服务取，放进 Webview；同一次运行不开第二个", async () => {
  const p = S.panels[0];
  assert.strictEqual(p.opts.enableScripts, true);
  assert.match(p.webview.html, /Content-Security-Policy/);
  assert.match(p.webview.html, /acquireVsCodeApi/);
  assert.match(p.webview.html, /"a\.json"/);
  assert.match(p.webview.html, /"light"/, "VS Code 是浅色主题");
  await S.commands["agentMcp.openRun"]("a.json");
  assert.strictEqual(S.panels.length, 1);
  assert.strictEqual(p.revealed, 1);
});

test("运行页：页面的请求经插件转发；不许的拒绝；写请求带 JSON 头", async () => {
  const p = S.panels[0];
  await p.msgL({ type: "fetch", id: 1, url: "api/runs", method: "GET" });
  let r = p.sent.find((m) => m.id === 1);
  assert.strictEqual(r.status, 200);
  assert.strictEqual(JSON.parse(r.body).runs.length, 3);
  const before = svc.fetched.length;
  await p.msgL({ type: "fetch", id: 2, url: "https://evil.example/x", method: "GET" });
  r = p.sent.find((m) => m.id === 2);
  assert.match(r.error, /不允许的地址/);
  assert.strictEqual(svc.fetched.length, before, "被拒的请求没有发出去");
  await p.msgL({ type: "fetch", id: 3, url: "api/approve", method: "POST", body: '{"name":"a.json","attempt":1}' });
  r = p.sent.find((m) => m.id === 3);
  assert.strictEqual(r.status, 200);
  const sent = svc.fetched[svc.fetched.length - 1];
  assert.deepStrictEqual([sent.url, sent.method, sent.headers["Content-Type"], sent.body],
    [ROOT + "api/approve", "POST", "application/json", '{"name":"a.json","attempt":1}']);
});

test("在编辑器里打开：脚本开成只读文档，选中那一行，放在旁边", async () => {
  const p = S.panels[0];
  await p.msgL({ type: "open-script", line: 3, workflow: "cost_workflow", script: "角色清单 roster {roles}\n接口约定\n    任务 {content}\n", run: "a.json" });
  const [doc, o] = S.shown[0];
  assert.strictEqual(doc.uri.toString(), "agentmcp-wf:/a/cost_workflow.wf");
  assert.match(doc.text, /接口约定/);
  assert.deepStrictEqual([o.selection.start.line, o.selection.end.character, o.viewColumn], [2, "    任务 {content}".length, -2]);
});

test("页面里换运行、回列表：标签页标题跟着改", async () => {
  const p = S.panels[0];
  await p.msgL({ type: "view", run: "c.json" });
  assert.strictEqual(p.title, "运行 c");
  await p.msgL({ type: "view", run: null });
  assert.strictEqual(p.title, "编排运行列表");
});

test("在浏览器里打开：用带口令的地址，运行项带 #run=", async () => {
  await S.commands["agentMcp.openInBrowser"]({ id: "run:c.json" });
  assert.deepStrictEqual(S.external, [ROOT + "#run=c.json"]);
});

// ---------- 实现步骤：拉到本地、交代码 ----------
const fs = require("fs");
const os = require("os");
const path = require("path");
const W = require("../lib/workdir");
const wtmp = fs.mkdtempSync(path.join(os.tmpdir(), "amext-"));
test.after(() => fs.rmSync(wtmp, { recursive: true, force: true }));
const PEND = { step: 6, attempt: 1, phase: "before", name: "任务实现", cwd: "work/demo", test_cmd: "pytest -q" };

test("拉到本地：请求 api/workfiles，选空文件夹写进去，问要不要加到工作区", async () => {
  svc.workfiles = { step: 6, attempt: 1, phase: "before", cwd: "work/demo", files: [{ path: "user.py", content: "x = 1\n" }],
                    skipped: [{ path: "b.bin", reason: "二进制" }] };
  S.nextFolder = path.join(wtmp, "w");
  fs.mkdirSync(S.nextFolder);
  S.info = [];
  await S.commands["agentMcp.pullWorkdir"]({ id: "run:a.json" });
  assert.ok(svc.fetched.some((f) => f.url === ROOT + "api/workfiles?name=a.json"));
  assert.strictEqual(fs.readFileSync(path.join(S.nextFolder, "user.py"), "utf8"), "x = 1\n");
  assert.strictEqual(W.readMarker(S.nextFolder).run, "a.json");
  assert.match(S.info[0][0], /已拉到 .*：1 个文件，跳过 1 个（b\.bin：二进制）/);
  assert.deepStrictEqual(S.info[0][1], ["加到工作区", "在新窗口打开"]);
});

test("拉不了：服务器的报错原样告诉人", async () => {
  svc.workfilesStatus = 400;
  svc.workfiles = { error: "这一步的角色没有工作目录" };
  S.errors = [];
  await S.commands["agentMcp.pullWorkdir"]("a.json");
  assert.deepStrictEqual(S.errors, ["拉不了工作目录：这一步的角色没有工作目录"]);
  svc.workfilesStatus = 200;
});

test("交代码：找到拉过的文件夹，交改动的文件，带步号、尝试次数、摘要；交完本地基线前移", async () => {
  const dir = path.join(wtmp, "w");
  vscode.workspace.workspaceFolders = [{ uri: { fsPath: dir } }];
  fs.writeFileSync(path.join(dir, "user.py"), "x = 2\n");
  fs.writeFileSync(path.join(dir, "test_user.py"), "def test(): pass\n");
  svc.run = { _name: "a.json", status: "waiting", pending: PEND };
  svc.submitReplies = [[200, { ok: true, status: { submitted_files: {
    changes: [{ target: "test_user.py" }, { target: "user.py" }], record: { verification: { result: "通过（退出码 0）：2 passed" } },
    test: { tail: "2 passed" } } } }]];
  S.nextInput = ["实现了 create_user", "没做校验；没做分页"];
  S.info = [];
  await S.commands["agentMcp.submitChanges"]("a.json");
  const post = svc.fetched.filter((f) => f.url === ROOT + "api/submit_files").pop();
  const body = JSON.parse(post.body);
  assert.deepStrictEqual([body.name, body.step, body.attempt, body.summary, body.status, body.open_issues],
    ["a.json", 6, 1, "实现了 create_user", "完成", ["没做校验", "没做分页"]]);
  assert.deepStrictEqual(body.files, [{ path: "test_user.py", content: "def test(): pass\n" }, { path: "user.py", content: "x = 2\n" }]);
  assert.strictEqual(post.headers["Content-Type"], "application/json");
  assert.ok(!("allow_fail" in body));
  assert.match(S.progress.pop(), /跑测试/);
  assert.deepStrictEqual(S.info.map((x) => x[0]), ["已交第 6 步：2 个文件改动；验证：通过（退出码 0）：2 passed"]);
  assert.deepStrictEqual(await W.collectChanges(dir), [], "交完本地没有改动了");
});

test("交代码：没有改动就不交；工作目录对不上就不交", async () => {
  S.info = []; S.errors = [];
  const n = svc.fetched.length;
  await S.commands["agentMcp.submitChanges"]("a.json");
  assert.deepStrictEqual(S.info.map((x) => x[0]), ["和拉下来时比没有改动，没什么可交的"]);
  fs.writeFileSync(path.join(wtmp, "w", "user.py"), "x = 3\n");
  svc.run = { _name: "a.json", status: "waiting", pending: Object.assign({}, PEND, { cwd: "work/other" }) };
  await S.commands["agentMcp.submitChanges"]("a.json");
  assert.match(S.errors[0], /工作目录是 work\/other，本地拉的是 work\/demo/);
  assert.ok(!svc.fetched.slice(n).some((f) => f.url.endsWith("api/submit_files")), "都没往服务器交");
  S.errors = [];
});

test("交代码：测试没过，输出放进输出面板；人选「仍然交」就带 allow_fail 再交一次", async () => {
  svc.run = { _name: "a.json", status: "waiting", pending: Object.assign({}, PEND, { step: 7 }) };
  svc.submitReplies = [
    [400, { ok: false, error: "测试没过（退出码 1），文件已撤回，没有提交。输出最后：\n1 failed" }],
    [200, { ok: true, status: { submitted_files: { changes: [{ target: "user.py" }], record: { verification: { result: "失败（退出码 1）" } } } } }],
  ];
  S.nextInput = ["先交一半", ""];
  S.nextWarning = "仍然交（状态记为部分完成）";
  S.info = [];
  await S.commands["agentMcp.submitChanges"]("a.json");
  const posts = svc.fetched.filter((f) => f.url === ROOT + "api/submit_files").slice(-2).map((f) => JSON.parse(f.body));
  assert.deepStrictEqual(posts.map((b) => [b.step, b.allow_fail]), [[7, undefined], [7, true]]);
  assert.ok(S.output.lines.some((l) => /1 failed/.test(l)) && S.output.shown >= 1, "测试输出进了输出面板");
  assert.deepStrictEqual(S.info.map((x) => x[0]), ["已交第 7 步：1 个文件改动；验证：失败（退出码 1）"]);
  vscode.workspace.workspaceFolders = undefined;
});

test("运行页里的按钮：拉到本地、交代码走同一套命令", async () => {
  const p = S.panels[0];
  svc.workfiles = { step: 9, attempt: 1, phase: "after", cwd: "work/demo", files: [], skipped: [] };
  S.nextFolder = path.join(wtmp, "w2");
  S.info = [];
  await p.msgL({ type: "pull-workdir", run: "c.json" });
  await tick(50);
  assert.ok(svc.fetched.some((f) => f.url === ROOT + "api/workfiles?name=c.json"));
  assert.strictEqual(W.readMarker(S.nextFolder).run, "c.json");
});

test("连不上：侧边栏和状态栏说清楚，手动刷新时弹错误", async () => {
  const real = global.fetch;
  global.fetch = async () => { const e = new Error("fetch failed"); e.cause = { code: "ECONNREFUSED" }; throw e; };
  try {
    await S.commands["agentMcp.refresh"]();
    assert.deepStrictEqual(await labels(), ["连不上：ECONNREFUSED"]);
    assert.strictEqual(S.status.text, "$(debug-disconnect) 编排：连不上");
    assert.deepStrictEqual(S.errors, ["连不上编排查看器：ECONNREFUSED"]);
  } finally {
    global.fetch = real;
  }
});

test("断开：口令从加密存储删掉，侧边栏回到连接按钮", async () => {
  await S.commands["agentMcp.disconnect"]();
  assert.strictEqual(S.secrets["agentMcp.viewerToken"], undefined);
  assert.strictEqual(S.config["agentMcp.viewerUrl"], undefined);
  assert.deepStrictEqual(await S.tree.getChildren(), []);
});
