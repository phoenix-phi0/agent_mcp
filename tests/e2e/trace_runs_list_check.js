// 用 jsdom 打开实时模式的查看器（fetch 换成假的），看上面的「运行列表」：
// 五次运行各一行、状态和进度对、默认选最新、点一行切过去并取消跟随、按状态和流程筛选、收起展开。
// 输出 JSON 给 tests/tools/test_trace_view.py 断言。
//   node trace_runs_list_check.js <trace_view.html> <trace.json>
// 假的 api/run 不管要哪次运行，都回同一份记录（只把 _name 换成要的名字）。
const fs = require("fs");
const { JSDOM } = require("jsdom");

const [html, tracePath] = process.argv.slice(2);
const T = JSON.parse(fs.readFileSync(tracePath, "utf-8"));
const page = fs.readFileSync(html, "utf-8").replace("<head>", () => '<head>\n<meta name="trace-live" content="1">');
const errors = [], asked = [];

const RUNS = [
  { name: "20261116-151453-cost_workflow.json", workflow: "cost_workflow", status: "running", alive: true, calls: 6, errors: 1,
    controlled: true, waiting_step: null, started: "2026-11-16T15:14:53+0800", updated: "2026-11-16T15:20:00+0800",
    current: { step: 8, name: "任务实现", role: "ENGINEER_DS" }, cost_spent: 12, usd_spent: 0.5, goal: "实现一个数据分析工具模块：count_pairs_within" },
  { name: "20261116-120000-feature_workflow.json", workflow: "feature_workflow", status: "waiting", alive: null, calls: 3,
    controlled: true, waiting_step: 4, started: "2026-11-16T12:00:00+0800", updated: "2026-11-16T12:05:00+0800",
    current: { step: 4, name: "任务研讨", role: "ARCHITECT_GLM" }, goal: "钱包服务" },
  { name: "20261115-100000-cost_workflow.json", workflow: "cost_workflow", status: "done", alive: null, calls: 9,
    started: "2026-11-15T10:00:00+0800", finished: "2026-11-15T10:10:00+0800", seconds: 600, cost_spent: 22, usd_spent: 0.6755,
    current: null, goal: "Go 数据分析工具包" },
  { name: "20261114-100000-refactor_workflow.json", workflow: "refactor_workflow", status: "error", alive: null, calls: 2,
    started: "2026-11-14T10:00:00+0800", seconds: 30, error: "agent「ENGINEER」调用失败：<script>alert(1)</script>", goal: "" },
  { name: "20261113-100000-cost_workflow.json", workflow: "cost_workflow", status: "running", alive: false, calls: 1,
    started: "2026-11-13T10:00:00+0800", updated: "2026-11-13T10:01:30+0800", current: { step: 2, name: "任务研讨" } },
];

function resp(status, obj) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(obj) });
}
function fakeFetch(url) {
  if (url === "api/runs") return resp(200, { dir: "runs", runs: RUNS });
  if (url.indexOf("api/run?") === 0) {
    const name = decodeURIComponent(url.split("name=")[1]);
    asked.push(name);
    return resp(200, Object.assign({}, T, { _name: name }));
  }
  if (url.indexOf("api/plan?") === 0) return resp(400, { error: "没有分配清单" });
  return resp(404, { error: "没有这个地址" });
}

const dom = new JSDOM(page, {
  runScripts: "dangerously", url: "http://127.0.0.1:8765/", pretendToBeVisual: true,
  beforeParse(w) {
    w.fetch = fakeFetch;
    w.addEventListener("error", (e) => errors.push(String(e.message || e.error)));
    w.alert = () => errors.push("页面调了 alert");
  },
});
const w = dom.window, doc = w.document;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rows = () => Array.from(doc.querySelectorAll("#runs-body tr.run-row"));
const names = () => rows().map((tr) => tr.getAttribute("data-run"));
const selRow = () => { const s = doc.querySelector("#runs-body tr.run-row.sel"); return s ? s.getAttribute("data-run") : null; };
function choose(id, value) {
  const el = doc.getElementById(id);
  el.value = value;
  el.dispatchEvent(new w.Event("change", { bubbles: true }));
}

async function main() {
  await sleep(400);
  const out = { errors };
  out.panelHidden = doc.getElementById("runs-panel").hidden;
  out.count = doc.getElementById("runs-count").textContent;
  out.names = names();
  out.sel = selRow();
  out.rowText = rows().map((tr) => tr.textContent);
  out.pills = rows().map((tr) => { const p = tr.querySelector(".pill"); return [p.className, p.textContent]; });
  out.injected = !!doc.querySelector("#runs-body script");
  out.wfOptions = Array.from(doc.getElementById("runs-wf").options).map((o) => o.value);
  out.askedFirst = asked[0] || null;

  // 点第三行（完成的那次）：切过去、取消跟随、请求那份记录
  const before = asked.length;
  rows()[2].dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await sleep(300);
  out.afterClick = { sel: selRow(), follow: doc.getElementById("follow").checked, pick: doc.getElementById("run-pick").value,
                     asked: asked.slice(before) };
  // 再等一轮轮询（1.5 秒）：不跟随了，选择要留在第三行
  await sleep(1700);
  out.afterPoll = { sel: selRow(), lastAsked: asked[asked.length - 1] };

  // 回车也能选
  const r5 = rows()[4];
  r5.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await sleep(300);
  out.afterEnter = selRow();

  // 折叠：输入参数和脚本原文默认收起；点开后换一次运行（整块重画）仍是开的，并记进 localStorage
  const inp = () => doc.querySelector('#summary details.fold[data-fold="inputs"]');
  const scr = () => doc.querySelector('#detail details.fold[data-fold="script"]');
  out.foldDefault = { inputs: inp() ? inp().open : null, script: scr() ? scr().open : null,
                      inputsTitle: inp() ? inp().querySelector("summary").textContent : "" };
  if (inp()) { inp().open = true; inp().dispatchEvent(new w.Event("toggle")); }
  if (scr()) { scr().open = true; scr().dispatchEvent(new w.Event("toggle")); }
  rows()[0].dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await sleep(400);
  out.foldAfter = { inputs: inp() ? inp().open : null, script: scr() ? scr().open : null,
                    stored: [w.localStorage.getItem("trace-fold-inputs"), w.localStorage.getItem("trace-fold-script")] };

  // 筛选
  choose("runs-filter", "bad"); out.filterBad = names(); out.countBad = doc.getElementById("runs-count").textContent;
  choose("runs-filter", "active"); out.filterActive = names();
  choose("runs-filter", ""); choose("runs-wf", "cost_workflow"); out.filterWf = names();
  choose("runs-wf", "");

  // 收起、展开
  const tg = doc.getElementById("runs-toggle");
  tg.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  out.collapsed = { cls: doc.getElementById("runs-panel").classList.contains("collapsed"), text: tg.textContent,
                    aria: tg.getAttribute("aria-expanded") };
  tg.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  out.expanded = { cls: doc.getElementById("runs-panel").classList.contains("collapsed"), text: tg.textContent };
  return out;
}

main().then((out) => { console.log(JSON.stringify(out)); w.close(); process.exit(0); },
            (e) => { console.error(e && e.stack || e); process.exit(1); });
