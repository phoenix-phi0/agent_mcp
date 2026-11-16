// 用 jsdom 打开实时模式的查看器（fetch 换成假的），看两层页面：
// 列表页（地址不带 #run=）：五次运行各一行、状态和进度对、只刷列表不拉单次记录、按状态和流程筛选；
// 点一行或回车进运行页（#run=名字）：列表藏起来、概况和流程图出来、载入那份记录；「← 运行列表」回来；
// 运行页里的折叠块默认收起、点开后换一次运行仍是开的。输出 JSON 给 tests/tools/test_trace_view.py 断言。
//   node trace_runs_list_check.js <trace_view.html> <trace.json> [直接打开的运行名]
// 第三个参数：直接用 #run=名字 打开（分享出去的链接），看是不是直接进运行页；名字不在列表里时要说没找到。
// 假的 api/run 不管要哪次运行，都回同一份记录（只把 _name 换成要的名字）。
const fs = require("fs");
const { JSDOM } = require("jsdom");

const [html, tracePath, direct] = process.argv.slice(2);
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
  { name: "20261110-100000-cost_workflow.json", workflow: "cost_workflow", status: "done", alive: null, calls: 15,
    started: "2026-11-10T09:00:00+0800", finished: "2026-11-10T18:32:30+0800", cost_spent: 60 },
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
  runScripts: "dangerously", pretendToBeVisual: true,
  url: "http://127.0.0.1:8765/" + (direct ? "#run=" + encodeURIComponent(direct) : ""),
  beforeParse(w) {
    w.fetch = fakeFetch;
    w.addEventListener("error", (e) => errors.push(String(e.message || e.error)));
    w.alert = () => errors.push("页面调了 alert");
    w.scrollTo = () => {};
  },
});
const w = dom.window, doc = w.document;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rows = () => Array.from(doc.querySelectorAll("#runs-body tr.run-row"));
const names = () => rows().map((tr) => tr.getAttribute("data-run"));
const selRow = () => { const s = doc.querySelector("#runs-body tr.run-row.sel"); return s ? s.getAttribute("data-run") : null; };
// 「看得见」：没有被 view-list / view-run 的样式藏起来
// 往上逐层看：自己或哪一层祖先被藏了都算看不见（勾选框藏在 label 里，藏的是 label）
const shown = (sel) => {
  for (let e = doc.querySelector(sel); e && e !== doc.body; e = e.parentElement)
    if (e.hidden || w.getComputedStyle(e).display === "none") return false;
  return !!doc.querySelector(sel);
};
function view() {
  return { body: doc.body.className, hash: w.location.hash, title: doc.title,
           list: shown("#runs-panel"), summary: shown('section[aria-label="概况"]'), main: shown(".main"),
           back: shown("#back-list"), pick: shown("#run-pick"), follow: shown("#follow") };
}
function choose(id, value) {
  const el = doc.getElementById(id);
  el.value = value;
  el.dispatchEvent(new w.Event("change", { bubbles: true }));
}

async function directMain() {
  await sleep(500);
  return { errors, view: view(), asked: asked.slice(), summary: doc.getElementById("summary").textContent,
           pick: doc.getElementById("run-pick").value };
}

async function main() {
  await sleep(400);
  const out = { errors };
  out.start = view();
  out.count = doc.getElementById("runs-count").textContent;
  out.names = names();
  out.sel = selRow();
  out.rowText = rows().map((tr) => tr.textContent);
  out.pills = rows().map((tr) => { const p = tr.querySelector(".pill"); return [p.className, p.textContent]; });
  out.injected = !!doc.querySelector("#runs-body script");
  out.wfOptions = Array.from(doc.getElementById("runs-wf").options).map((o) => o.value);
  out.askedOnList = asked.length;

  // 点第三行：进运行页
  rows()[2].dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await sleep(300);
  out.afterClick = { view: view(), asked: asked.slice(), pick: doc.getElementById("run-pick").value,
                     summary: doc.getElementById("summary").textContent };
  // 再等一轮轮询：还在这次运行
  await sleep(1700);
  out.afterPoll = { hash: w.location.hash, lastAsked: asked[asked.length - 1] };

  // 运行页的折叠块：默认收起；点开后换一次运行（用下拉框换，整块重画）仍是开的
  const inp = () => doc.querySelector('#summary details.fold[data-fold="inputs"]');
  const scr = () => doc.querySelector('#detail details.fold[data-fold="script"]');
  out.foldDefault = { inputs: inp() ? inp().open : null, script: scr() ? scr().open : null,
                      inputsTitle: inp() ? inp().querySelector("summary").textContent : "" };
  if (inp()) { inp().open = true; inp().dispatchEvent(new w.Event("toggle")); }
  if (scr()) { scr().open = true; scr().dispatchEvent(new w.Event("toggle")); }
  choose("run-pick", RUNS[0].name);
  await sleep(400);
  out.afterPick = { hash: w.location.hash, lastAsked: asked[asked.length - 1] };
  out.foldAfter = { inputs: inp() ? inp().open : null, script: scr() ? scr().open : null,
                    stored: [w.localStorage.getItem("trace-fold-inputs"), w.localStorage.getItem("trace-fold-script")] };

  // 「← 运行列表」回来：只看列表，地址不留 #，标出刚看的那次
  const before = asked.length;
  doc.getElementById("back-list").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await sleep(1700);
  out.back = { view: view(), url: w.location.href, sel: selRow(), askedAfter: asked.length - before };

  // 回车也能进
  rows()[4].dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await sleep(300);
  out.afterEnter = { hash: w.location.hash, lastAsked: asked[asked.length - 1], list: shown("#runs-panel") };
  doc.getElementById("back-list").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await sleep(300);

  // 列表页筛选
  choose("runs-filter", "bad"); out.filterBad = names(); out.countBad = doc.getElementById("runs-count").textContent;
  choose("runs-filter", "active"); out.filterActive = names();
  choose("runs-filter", ""); choose("runs-wf", "cost_workflow"); out.filterWf = names();
  choose("runs-wf", "");
  return out;
}

(direct ? directMain() : main()).then((out) => { console.log(JSON.stringify(out)); w.close(); process.exit(0); },
            (e) => { console.error(e && e.stack || e); process.exit(1); });
