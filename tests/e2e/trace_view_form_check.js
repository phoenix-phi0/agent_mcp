// 用 jsdom 把 tools/trace_view.html 当成「本机查看服务开放了写接口」的页面打开（实时模式，fetch 换成假的），
// 载入一份停在某个节点的过程记录，操作「由我来做」那块表单，把看到的东西输出给
// tests/tools/test_trace_view.py 断言。
//   node trace_view_form_check.js <trace_view.html> <trace.json> [readonly]
// readonly：只加实时标记、不加写标记（查看服务没开放写接口时的页面）。
// 假 fetch：api/runs、api/run 回这份记录；POST 记下来，成功一次就把记录的 updated 改一下（像真的往下走了一样）；
// 交的结果里 summary 是「让服务端拒绝」时回 400 和字段错误。
const fs = require("fs");
const { JSDOM } = require("jsdom");

const [html, tracePath, flag] = process.argv.slice(2);
const T = JSON.parse(fs.readFileSync(tracePath, "utf-8"));
const meta = '<head>\n<meta name="trace-live" content="1">' + (flag === "readonly" ? "" : '\n<meta name="trace-write" content="1">');
const page = fs.readFileSync(html, "utf-8").replace("<head>", () => meta);
const errors = [], posts = [];
let rev = 0;

function resp(status, obj) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(obj) });
}
function fakeFetch(url, opts) {
  opts = opts || {};
  if (opts.method === "POST") {
    const body = JSON.parse(opts.body);
    posts.push({ url, type: (opts.headers || {})["Content-Type"], body });
    if (url === "api/submit" && body.result && body.result.summary === "让服务端拒绝") {
      return resp(400, { ok: false, error: "结果不符合格式 review：issues[0].problem: '' should be non-empty",
                         errors: ["issues[0].problem: '' should be non-empty", "(顶层): 'decide' is a required property"] });
    }
    rev++;
    return resp(200, { ok: true, status: {} });
  }
  if (url === "api/runs") {
    return resp(200, { dir: "runs", runs: [{ name: T._name, status: T.status, started: T.started, updated: T.updated, alive: null,
                                              calls: 3, controlled: true, waiting_step: T.pending ? T.pending.step : null }] });
  }
  if (url.indexOf("api/run?") === 0) return resp(200, Object.assign({}, T, { updated: T.updated + (rev ? "#" + rev : "") }));
  return resp(404, { error: "没有这个地址" });
}

const dom = new JSDOM(page, {
  runScripts: "dangerously", url: "http://127.0.0.1:8765/", pretendToBeVisual: true,
  beforeParse(w) {
    w.fetch = fakeFetch;
    w.addEventListener("error", (e) => errors.push(String(e.message || e.error)));
    // 页面不该用浏览器弹窗：用了就记下来
    w.alert = () => errors.push("页面调了 alert");
    w.confirm = () => { errors.push("页面调了 confirm"); return true; };
  },
});
const w = dom.window, doc = w.document;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const at = (ps) => Array.from(doc.querySelectorAll("#act [data-p]")).find((x) => x.getAttribute("data-ps") === ps);
const act = (name) => doc.querySelector('#act [data-act="' + name + '"]');
const click = (el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
function type(el, value) {
  el.value = value;
  el.dispatchEvent(new w.Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
}
function pick(el, text) {
  const o = Array.from(el.options).find((x) => x.textContent === text);
  type(el, o.value);
}
const msg = () => (doc.getElementById("act-msg") ? doc.getElementById("act-msg").textContent : "");
const items = () => doc.querySelectorAll("#act-form .f-arr[data-ps='issues'] > .f-item").length;

async function main() {
  await sleep(300);
  const out = { errors, posts };
  const box = doc.getElementById("act");
  out.hasAct = !!box;
  out.writeButtons = doc.querySelectorAll("[data-act], [data-add], [data-mode]").length;
  out.note = doc.getElementById("note").textContent;
  if (!box) return out;

  // 1. 表单长什么样
  const detail = doc.getElementById("detail").textContent;
  out.title = box.querySelector(".act-head h3").textContent;
  out.below = detail.indexOf("由我来做") > detail.indexOf("系统提示（角色卡）") && detail.indexOf("由我来做") > detail.indexOf("提示词（外部自己执行时照这个发）") &&
    detail.indexOf("由我来做") > detail.indexOf("参考文本");
  out.order = Array.from(doc.querySelectorAll("#act-form > *")).map((x) => (x.querySelector(".f-lab b") || {}).textContent);
  out.decideTag = at("decide").tagName;
  out.decideOptions = Array.from(at("decide").options).map((o) => o.textContent);
  out.summaryTag = at("summary").tagName;
  out.stars = Array.from(doc.querySelectorAll("#act-form > * > .f-lab")).filter((x) => x.querySelector(".req")).map((x) => x.querySelector("b").textContent);
  out.actions = Array.from(doc.querySelectorAll("#act [data-act]")).map((x) => x.textContent);
  out.cards = Array.from(doc.getElementById("act-card").options).map((o) => o.value);
  out.modes = Array.from(doc.querySelectorAll("#act [data-mode]")).map((x) => x.textContent);

  // 2. 从上次这个节点的结果复制，再清空
  out.hasCopy = !!act("copy-last");
  if (out.hasCopy) {
    click(act("copy-last"));
    out.copied = { decide: at("decide").options[at("decide").selectedIndex].textContent, summary: at("summary").value, items: items(),
                   severity: at("issues[0].severity") ? at("issues[0].severity").options[at("issues[0].severity").selectedIndex].textContent : null };
    click(act("clear"));
  }
  out.cleared = { decide: at("decide").value, summary: at("summary").value, items: items() };

  // 3. 数组加条目、删条目；数组里是对象就是一组子字段，其中的 enum 也是下拉
  click(doc.querySelector('#act [data-add="[\\"issues\\"]"]'));
  out.items1 = items();
  out.itemFields = Array.from(doc.querySelectorAll("#act-form .f-item [data-p]")).map((x) => x.getAttribute("data-ps") + ":" + x.tagName);
  click(doc.querySelector('#act [data-add="[\\"issues\\"]"]'));
  out.items2 = items();
  click(doc.querySelector('#act [data-del="[\\"issues\\",1]"]'));
  out.items3 = items();

  // 4. 填一部分就提交：页面先拦下，不发请求，缺的字段标红
  pick(at("decide"), "需修改");
  type(at("summary"), "人工审查：缺错误码");
  type(at("issues[0].location"), "create_user.errors");
  type(at("issues[0].problem"), "缺错误码");
  type(at("issues[0].suggestion"), "补上");
  click(act("submit"));
  out.clientMsg = msg();
  out.clientBad = Array.from(doc.querySelectorAll("#act .bad[data-p]")).map((x) => x.getAttribute("data-ps"));
  out.postsAfterInvalid = posts.length;
  pick(at("issues[0].severity"), "一般");

  // 5. 切到 JSON：内容就是表单里填的；改 JSON 再切回表单：表单跟着变；JSON 写坏了切不回去
  click(doc.querySelector('#act [data-mode="json"]'));
  const ta = () => doc.getElementById("act-json");
  out.jsonFromForm = JSON.parse(ta().value);
  const edited = JSON.parse(ta().value);
  edited.summary = "从 JSON 改的";
  edited.issues.push({ location: "b", problem: "p2", suggestion: "s2", severity: "轻微" });
  type(ta(), "{ 写坏了");
  click(doc.querySelector('#act [data-mode="form"]'));
  out.badJsonStays = !!ta() && !doc.getElementById("act-form");
  out.badJsonMsg = msg();
  type(ta(), JSON.stringify(edited));
  click(doc.querySelector('#act [data-mode="form"]'));
  out.formFromJson = { summary: at("summary").value, items: items(),
                       severity1: at("issues[1].severity").options[at("issues[1].severity").selectedIndex].textContent };

  // 6. 服务端拒绝：原样显示它回的字段错误，对应字段标红，可以接着改
  type(at("summary"), "让服务端拒绝");
  click(act("submit"));
  await sleep(50);
  out.serverMsg = msg();
  out.serverBad = Array.from(doc.querySelectorAll("#act .bad[data-p]")).map((x) => x.getAttribute("data-ps"));
  out.canRetry = !act("submit").disabled;

  // 7. 改好再交：发 POST，成功后有提示并重拉运行状态
  type(at("summary"), "人工审查：缺错误码");
  click(act("submit"));
  out.busyWhileSending = act("submit").disabled;
  await sleep(100);
  out.noteAfterSubmit = doc.getElementById("note").textContent;
  out.formResetAfterSubmit = !!at("summary") && at("summary").value === "";

  // 8. 换卡执行
  click(act("exec-as"));
  out.execNeedsChoice = msg();
  type(doc.getElementById("act-card"), "ARCHITECT_GLM");
  type(doc.getElementById("act-model"), "cli:goose/glm-5.3");
  click(act("exec-as"));
  await sleep(100);

  // 9. 中止要在页面里二次确认
  click(act("abort"));
  out.abortConfirm = doc.getElementById("act-abort").textContent;
  out.postsBeforeAbortYes = posts.length;
  click(act("abort-no"));
  out.abortBack = !!act("abort") && !act("abort-yes");
  click(act("abort"));
  click(act("abort-yes"));
  await sleep(100);
  out.noteAfterAbort = doc.getElementById("note").textContent;
  return out;
}

main().then((out) => {
  process.stdout.write(JSON.stringify(out));
  w.close();
  process.exit(0);
}, (err) => {
  process.stderr.write(String(err && err.stack || err) + "\n页面脚本报错：" + JSON.stringify(errors) + "\n");
  process.exit(1);
});
