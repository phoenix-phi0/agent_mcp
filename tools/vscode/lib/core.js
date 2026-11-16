// 插件里不依赖 vscode 的部分：解析查看器链接、拼请求地址、限制 Webview 能发的请求、
// 按状态给运行分组、找出新停下来等确认的运行。单元测试在 tools/vscode/test/core.test.js。
"use strict";

// 查看器链接：https://域名/trace/<口令>/ 或本机 http://127.0.0.1:8765/（不带口令）。
// 口令是地址里最后一段、16 位以上的字母数字（trace_server 的 TRACE_TOKEN）。
const TOKEN_RE = /^[A-Za-z0-9_-]{16,}$/;

function parseViewerLink(text) {
  let u;
  try {
    u = new URL(String(text || "").trim());
  } catch (e) {
    throw new Error("不是有效的地址：" + text);
  }
  if (u.protocol !== "https:" && u.protocol !== "http:") throw new Error("地址要以 http:// 或 https:// 开头");
  // 运行页的地址带 #run=…，查询串也用不上：都去掉
  const parts = u.pathname.split("/").filter(Boolean);
  let token = "";
  if (parts.length && TOKEN_RE.test(parts[parts.length - 1])) token = parts.pop();
  const base = u.origin + (parts.length ? "/" + parts.join("/") : "");
  return { base, token };
}

// 查看服务的根（以 / 结尾），页面和 api/… 都相对它
function rootUrl(base, token) {
  return String(base).replace(/\/+$/, "") + "/" + (token ? token + "/" : "");
}

// Webview 里的页面只许请求这几种：读 api/runs、api/run、api/plan，写 _WRITE_OPS 里那些。
// 别的地址（外站、../ 往上走）一律拒绝，免得页面被注入的内容借插件发任意请求。
const READ = new Set(["runs", "run", "plan"]);
// 同 tools/trace_server.py 的 _WRITE_OPS
const WRITE = new Set(["submit", "execute", "resume", "abort", "approve", "reject", "edit_plan", "pause"]);

function checkPageRequest(url, method) {
  const m = String(url || "").match(/^api\/([a-z_]+)(\?[^#]*)?$/);
  method = String(method || "GET").toUpperCase();
  if (!m) return "不允许的地址：" + url;
  if (method === "GET" && READ.has(m[1])) return null;
  if (method === "POST" && WRITE.has(m[1]) && !m[2]) return null;
  return "不允许的请求：" + method + " " + url;
}

// 状态 → [分组, 文字, 图标]。图标是 VS Code 自带的 codicon 名字
function runState(r) {
  if (r.status === "running") return r.alive === false ? ["bad", "已中断", "debug-disconnect"] : ["running", "运行中", "sync~spin"];
  if (r.status === "waiting") return ["waiting", r.waiting_step != null ? "暂停在第 " + r.waiting_step + " 步" : "暂停", "debug-pause"];
  if (r.status === "done") return ["done", "完成", "pass"];
  if (r.status === "error") return ["bad", "出错", "error"];
  if (r.status === "aborted") return ["bad", "已中止", "circle-slash"];
  return ["bad", String(r.status || "?"), "question"];
}

const GROUPS = [
  ["waiting", "等确认"],
  ["running", "运行中"],
  ["bad", "出错、中止、中断"],
  ["done", "完成"],
];

function groupRuns(runs) {
  const out = GROUPS.map(([key, label]) => ({ key, label, runs: [] }));
  for (const r of runs || []) {
    const g = out.find((x) => x.key === runState(r)[0]);
    g.runs.push(r);
  }
  return out;
}

// 一行说明：状态，进行中的再加所在步
function describe(r) {
  const st = runState(r);
  const c = r.current;
  const here = (st[0] === "running" || st[0] === "waiting") && c ? "　" + (c.name || "") + (c.role ? " · " + c.role : "") : "";
  return st[1] + here;
}

// 停下来等确认的那一刻：名字 + 停在第几步。和上一轮比，多出来的就是新停下的
function waitingKeys(runs) {
  const keys = new Map();
  for (const r of runs || []) {
    if (r.status === "waiting") keys.set(r.name + "#" + r.waiting_step, r);
  }
  return keys;
}

function newlyWaiting(prev, runs) {
  const now = waitingKeys(runs);
  if (prev == null) return { keys: now, fresh: [] };     // 第一轮只记下来，不对已经停着的弹通知
  const fresh = [];
  for (const [k, r] of now) if (!prev.has(k)) fresh.push(r);
  return { keys: now, fresh };
}

module.exports = { parseViewerLink, rootUrl, checkPageRequest, runState, groupRuns, describe, newlyWaiting, GROUPS };
