// lib/webview.js + 真的查看器页面（tools/trace_view.html）放进 jsdom，模拟 VS Code Webview：
// acquireVsCodeApi 换成假的，插件这一侧按 lib/core.js 的规则转发请求、回假数据。
// 要 jsdom：NODE_PATH 指到 tests/e2e/node_modules。node --test test/*.test.js
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const core = require("../lib/core");
const { buildWebviewHtml } = require("../lib/webview");

let JSDOM;
try { ({ JSDOM } = require("jsdom")); } catch (e) { JSDOM = null; }

const ROOT = path.resolve(__dirname, "../../..");
const VIEW = fs.readFileSync(path.join(ROOT, "tools/trace_view.html"), "utf-8");
// 查看服务给的页面：带实时和写标记（同 trace_server.view_html(write=True)）
const SERVED = VIEW.replace("<head>", '<head>\n<meta name="trace-live" content="1">\n<meta name="trace-write" content="1">');

const schema = { type: "object", required: ["summary"], properties: { summary: { type: "string", minLength: 1 } } };
const TRACE = {
  _name: "confirm.json", workflow: "test", status: "waiting", updated: "1",
  script: "实现\n  角色 ENGINEER\n  任务 写代码\n  格式 implementation\n  记录 result",
  _control: { mode: "auto", stop_roles: [], confirm_before: [], confirm_after: ["实现"], max_attempts: 4, models: {}, roles: {} },
  _agents: [{ name: "ENGINEER" }],
  pending: { phase: "after", line: 1, step: 1, name: "实现", role: "ENGINEER", attempt: 1, max_attempts: 4, schema,
             result: { summary: "模型结果" } },
  events: [{ type: "task", line: 1, seq: 1, step: 1, name: "实现", task: "写代码", role: "ENGINEER", status: "review",
             attempt: 1, result: { summary: "模型结果" } }],
};
const RUNS = [{ name: "confirm.json", workflow: "test", status: "waiting", waiting_step: 1, controlled: true, calls: 1 },
              { name: "other.json", workflow: "test", status: "done", calls: 3 }];

const wait = (ms) => new Promise((r) => setTimeout(r, ms || 60));

function open(opts) {
  const sent = [], asked = [], posts = [], errors = [];
  const html = buildWebviewHtml(SERVED, opts);
  const dom = new JSDOM(html, {
    url: "vscode-webview://test-panel/index.html", runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse(w) {
      w.addEventListener("error", (e) => errors.push(String(e.message || e.error)));
      w.scrollTo = () => {};
      w.acquireVsCodeApi = () => ({
        postMessage(m) {
          sent.push(m);
          if (m.type !== "fetch") return;
          // 插件这一侧：同 extension.js，先过 checkPageRequest
          const bad = core.checkPageRequest(m.url, m.method);
          let reply;
          if (bad) reply = { type: "fetch-result", id: m.id, error: bad };
          else if (m.method === "POST") {
            posts.push({ url: m.url, headers: m.headers, body: JSON.parse(m.body) });
            reply = { type: "fetch-result", id: m.id, status: 200, body: JSON.stringify({ ok: true }) };
          } else {
            asked.push(m.url);
            const data = m.url === "api/runs" ? { dir: "runs", runs: RUNS }
              : m.url.startsWith("api/run?") ? Object.assign({}, TRACE, { _name: decodeURIComponent(m.url.split("name=")[1]) })
              : null;
            reply = data ? { type: "fetch-result", id: m.id, status: 200, body: JSON.stringify(data) }
              : { type: "fetch-result", id: m.id, status: 400, body: JSON.stringify({ error: "没有清单" }) };
          }
          setTimeout(() => w.dispatchEvent(new w.MessageEvent("message", { data: reply })), 5);
        },
      });
    },
  });
  return { dom, w: dom.window, d: dom.window.document, sent, asked, posts, errors };
}

test("生成的 Webview 页面：内容安全策略和桥接在页面脚本之前，外部字体去掉", () => {
  const html = buildWebviewHtml(SERVED, { run: "a.json", theme: "dark" });
  const head = html.slice(0, html.indexOf("<style>"));
  assert.match(head, /Content-Security-Policy[^>]*default-src 'none'/);
  assert.ok(head.indexOf("acquireVsCodeApi") > head.indexOf("Content-Security-Policy"));
  assert.ok(html.indexOf("acquireVsCodeApi") < html.indexOf("var LIVE"));
  assert.doesNotMatch(html, /fonts\.googleapis\.com/);
  assert.throws(() => buildWebviewHtml("没有 head 的东西", {}), /不像查看器页面/);
});

test("运行名里有 </script> 也关不掉桥接脚本", () => {
  const html = buildWebviewHtml(SERVED, { run: "x</script><script>alert(1)</script>.json" });
  const bridge = html.slice(html.indexOf("acquireVsCodeApi"), html.indexOf("</script>", html.indexOf("acquireVsCodeApi")));
  assert.match(bridge, /\\u003c\/script>/);
});

test("在 Webview 里：直接进那次运行的页面，请求经插件转发，深浅色跟 VS Code", { skip: !JSDOM && "没有 jsdom" }, async () => {
  const p = open({ run: "confirm.json", theme: "light" });
  await wait(300);
  assert.deepStrictEqual(p.errors, []);
  assert.strictEqual(p.w.location.hash, "#run=confirm.json");
  assert.ok(p.d.body.classList.contains("view-run"), "运行页");
  assert.strictEqual(p.d.documentElement.getAttribute("data-theme"), "light");
  assert.ok(p.asked.includes("api/runs") && p.asked.includes("api/run?name=confirm.json"), JSON.stringify(p.asked));
  assert.match(p.d.getElementById("summary").textContent, /test\.wf/);
  // VS Code 换了主题
  p.w.dispatchEvent(new p.w.MessageEvent("message", { data: { type: "theme", kind: "dark" } }));
  assert.strictEqual(p.d.documentElement.getAttribute("data-theme"), "dark");
  await wait(100);       // 页面换主题后会重画流程图，等它画完再关窗口
  p.w.close();
});

test("在 Webview 里：批准走插件转发的 POST，带 JSON 头", { skip: !JSDOM && "没有 jsdom" }, async () => {
  const p = open({ run: "confirm.json", theme: "dark" });
  await wait(300);
  const btn = p.d.querySelector('[data-act="approve"]');
  assert.ok(btn, "有批准按钮（服务端开了写接口）");
  btn.click();
  await wait(200);
  assert.deepStrictEqual(p.posts.map((x) => [x.url, x.headers["Content-Type"], x.body]),
    [["api/approve", "application/json", { name: "confirm.json", attempt: 1 }]]);
  assert.deepStrictEqual(p.errors, []);
  p.w.close();
});

test("在 Webview 里：不许的地址被插件拒绝，页面拿到网络错误", { skip: !JSDOM && "没有 jsdom" }, async () => {
  const p = open({ run: "confirm.json" });
  await wait(200);
  await assert.rejects(p.w.fetch("https://evil.example/steal"), /不允许的地址/);
  await assert.rejects(p.w.fetch("api/runs", { method: "POST", body: "{}" }), /不允许的请求/);
  p.w.close();
});

test("在 Webview 里：「在编辑器里打开」把脚本和行号交给插件", { skip: !JSDOM && "没有 jsdom" }, async () => {
  const p = open({ run: "confirm.json" });
  await wait(300);
  const b = p.d.querySelector("[data-open-script]");
  assert.ok(b, "脚本原文那一栏有「在编辑器里打开」");
  const fold = b.closest("details");
  const wasOpen = fold.open;
  b.click();
  const m = p.sent.filter((x) => x.type === "open-script");
  assert.strictEqual(m.length, 1);
  assert.deepStrictEqual([m[0].line, m[0].workflow, m[0].run], [1, "test", "confirm.json"]);
  assert.match(m[0].script, /角色 ENGINEER/);
  assert.strictEqual(fold.open, wasOpen, "点按钮不让折叠块跟着开合");
  p.w.close();
});

test("在 Webview 里：换运行、回列表都告诉插件（好改标签页标题）", { skip: !JSDOM && "没有 jsdom" }, async () => {
  const p = open({ run: "confirm.json" });
  await wait(300);
  const pick = p.d.getElementById("run-pick");
  pick.value = "other.json";
  pick.dispatchEvent(new p.w.Event("change", { bubbles: true }));
  await wait(100);
  p.d.getElementById("back-list").click();
  await wait(100);
  const views = p.sent.filter((x) => x.type === "view").map((x) => x.run);
  assert.deepStrictEqual(views, ["other.json", null]);
  assert.ok(p.d.body.classList.contains("view-list"));
  p.w.close();
});

test("不在插件里（普通浏览器）：页面没有「在编辑器里打开」", { skip: !JSDOM && "没有 jsdom" }, async () => {
  const runs = { dir: "runs", runs: RUNS };
  const dom = new JSDOM(SERVED, {
    url: "http://127.0.0.1:8765/#run=confirm.json", runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse(w) {
      w.scrollTo = () => {};
      w.fetch = async (u) => ({ ok: true, status: 200,
        json: async () => (u === "api/runs" ? runs : u.startsWith("api/run?") ? TRACE : {}) });
    },
  });
  await wait(300);
  assert.ok(dom.window.document.getElementById("summary").textContent.includes("test.wf"));
  assert.strictEqual(dom.window.document.querySelector("[data-open-script]"), null);
  dom.window.close();
});
