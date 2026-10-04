// 做题页的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node quiz_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_quiz（实体、查询、接口、界面、内容），导入
// 知识点、课文、题目，gen run 起真服务。页面在 jsdom 里跑，按人的操作点：
//   导航切到「做题」；进来时作答区不出现
//   选 N4・接续 → 开始 → 出题、只有输入框；答错（Enter 交）→ 回显、批改、
//     作答区收起、成绩 0/1；库里多一条流水，记在条目所属的结构点上
//   下一题 → 点「作答」答对 → 成绩 1/2
//   换成挖空 → 开始 → 只有 A–D 单选；点选项交 → 判对、成绩清零后 1/1
//   切到图谱再切回来：消息流不重复、选择还在
//   刷新：消息流是空的、作答区不出现（看不见的题不能交），等级考点填回上次的

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_quiz";
const PORT = 8192;
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";

let pass = 0, fail = 0;
const say = (ok, msg) => { ok ? pass++ : fail++; console.log((ok ? "  ✓ " : "  ✗ ") + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 4000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    try { if (fn()) return true; } catch (e) { /* 还没渲染 */ }
    await sleep(30);
  }
  return false;
}
function db(sql) {
  const code = "import sqlite3,json;" +
    `c=sqlite3.connect('${PROJ}/app.db');c.row_factory=sqlite3.Row;` +
    `print(json.dumps([dict(r) for r in c.execute(${JSON.stringify(sql)})],ensure_ascii=False))`;
  return JSON.parse(execFileSync(PY, ["-c", code], { encoding: "utf8" }));
}
const state = () => db("SELECT * FROM quiz_state WHERE learner = 'me'")[0] || {};
const question = code => db(`SELECT * FROM question WHERE code = '${code}'`)[0] || {};

const calls = [];
function openPage(hash) {
  const html = fs.readFileSync(WEB + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/" + (hash || ""), runScripts: "outside-only" });
  const w = dom.window;
  w.fetch = async (u, o = {}) => {
    const url = new URL(u, BASE);
    const r = await fetch(url, o);
    calls.push({ path: url.pathname, status: r.status });
    return r;
  };
  w.console.log = () => {};
  w.console.warn = () => {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + "/app.js", "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  return {
    w, $, $$,
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    msgs: () => $$(".stream .smsg").map(m => ({
      who: (m.querySelector(".who") || {}).textContent || "",
      text: (m.querySelector(".body") || {}).textContent || "",
      cls: m.className })),
    selects: () => $$(".bar-top select"),
    pick: (sel, v) => { sel.value = v; sel.dispatchEvent(new w.Event("change")); },
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    stat: () => ($(".bar-top .dyn-v") || {}).textContent || "",
    radios: () => $$(".bar-bottom input[type=radio]"),
    box: () => $(".bar-bottom textarea"),
    close: () => w.close(),
  };
}

(async () => {
  // 照 kg 搭一份，导入知识点、课文、题目。走的是跟 py -m kg 同一组接口
  fs.rmSync(PROJ, { recursive: true, force: true });
  execFileSync(PY, ["-c", [
    "import sys, shutil, pathlib",
    "sys.path.insert(0, '.')",
    "from tests.kg.helpers import make_ws, client",
    "from kg.__main__ import BANK, read_bank",
    `ws = pathlib.Path('${PROJ}'); ws.mkdir()`,
    "make_ws(ws)",
    "shutil.copytree('kg/ui', ws / 'ui')",
    "c = client(ws)",
    "assert c.post('/kg/import2', json={'form': {}}).status_code == 200",
    "assert c.post('/lesson/import', json={'form': {}}).status_code == 200",
    "r = c.post('/quiz/import', json={'form': {'rows': read_bank(BANK)}})",
    "assert r.status_code == 200, r.get_json()",
  ].join("\n")], { cwd: MCP, encoding: "utf8" });

  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器"],
                       { cwd: MCP, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  server.stdout.on("data", d => { log += d; });
  server.stderr.on("data", d => { log += d; });
  const stop = code => { server.kill(); process.exit(code); };
  let up = false;
  for (let i = 0; i < 150 && !up; i++) {
    try { up = (await fetch(BASE + "/")).ok; } catch (e) { /* 还没起来 */ }
    if (!up) await sleep(100);
  }
  if (!up) { console.log("服务没起来：\n" + log); stop(1); }

  console.log("一、切到做题");
  let p = openPage("");
  say(await waitFor(() => p.nav("做题") && p.nav("知识图谱")), "导航里有「知识图谱」「做题」");
  calls.length = 0;
  p.nav("做题").click();
  say(await waitFor(() => p.hash() === "#做题"), `到了 ${p.hash()}`);
  say(await waitFor(() => calls.some(c => c.path === "/quiz/state" && c.status === 200)),
      "进来时拉了一次进度");
  say(await waitFor(() => p.selects().length === 2 && p.selects().every(s => s.value === "全部")),
      "等级、考点默认「全部」");
  say(!p.box() && !p.radios().length && !p.btn("作答") && !p.btn("下一题"),
      "还没出题：作答区、作答、下一题都不出现");

  console.log("二、接续题：答错");
  p.pick(p.selects()[0], "N4");
  p.pick(p.selects()[1], "接续");
  p.btn("开始").click();
  say(await waitFor(() => p.msgs().some(m => m.who === "题目")), "出了一道题");
  let q = question(state().current);
  say(q.level === "N4" && q.kind === "接续", `按选的出：${q.code}`);
  const shown = p.msgs()[0].text, line = q.stem.split("\n")[1] || q.stem;
  say(shown.includes(line), "消息里是这道题的题干" +
      (shown.includes(line) ? "" : `\n      显示：${JSON.stringify(shown)}\n      题干：${JSON.stringify(q.stem)}`));
  say(await waitFor(() => p.box() && !p.radios().length), "接续题：只有输入框，没有单选");
  p.type(p.box(), "わかりません");
  p.enter(p.box());
  say(await waitFor(() => p.msgs().some(m => m.who === "批改")), "Enter 交了，回来批改");
  let ms = p.msgs();
  say(ms.some(m => m.who === "你" && m.text === "わかりません"), "自己写的先回显在消息流里");
  let v = ms.find(m => m.who === "批改");
  say(v.cls.includes("smsg-no") && v.text.includes(q.answer), `判错，给了正确答案「${q.answer}」`);
  say(v.text.includes("考的是："), "批改里说了考的是哪个条目");
  say(await waitFor(() => !p.box() && !p.btn("作答") && p.btn("下一题")), "判完：作答区收起，出现「下一题」");
  say(await waitFor(() => p.stat() === "这一轮 0/1"), `顶栏成绩：${p.stat()}`);
  const a = db("SELECT a.*, i.point AS want FROM attempt a JOIN question q ON q.code = a.item" +
               " JOIN item i ON i.code = q.item");
  say(a.length === 1 && a[0].correct === 0 && a[0].point === a[0].want && a[0].item === q.code,
      `库里一条流水，记在结构点 ${a[0] && a[0].point} 上`);

  console.log("三、下一题：答对");
  const first = q.code;
  p.btn("下一题").click();
  say(await waitFor(() => state().current !== first && p.box()), "出了下一道，输入框回来了");
  say(p.box().value === "", "输入框是空的（上一道写的清掉了）");
  q = question(state().current);
  p.type(p.box(), q.answer);
  p.btn("作答").click();
  say(await waitFor(() => p.msgs().filter(m => m.who === "批改").length === 2), "又批改了一次");
  v = p.msgs().filter(m => m.who === "批改")[1];
  say(v.cls.includes("smsg-ok") && v.text.startsWith("○"), "判对");
  say(await waitFor(() => p.stat() === "这一轮 1/2"), `成绩接着算：${p.stat()}`);

  console.log("四、选择题");
  p.pick(p.selects()[1], "挖空");
  p.btn("开始").click();
  say(await waitFor(() => p.radios().length === 4 && !p.box()), "挖空：A–D 四个单选，没有输入框");
  say(await waitFor(() => p.stat() === "这一轮 0/0"), `开始：这一轮清零 ${p.stat()}`);
  q = question(state().current);
  say(q.kind === "挖空" && q.level === "N4", `按新的考点出：${q.code}`);
  p.radios().find(r => r.value === q.answer).click();
  p.btn("作答").click();
  say(await waitFor(() => p.msgs().filter(m => m.who === "批改").length === 3), "交了");
  ms = p.msgs();
  say(ms.some(m => m.who === "你" && m.text === q.answer), `回显选的「${q.answer}」`);
  say(ms[ms.length - 1].cls.includes("smsg-ok"), "判对");
  say(await waitFor(() => p.stat() === "这一轮 1/1"), `成绩：${p.stat()}`);
  say(state().choice === q.answer, "库里记着选的是哪个");
  say(!p.radios().some(r => r.checked) || !p.radios().length, "单选清掉了");

  console.log("五、切走再切回来");
  const count = p.msgs().length;
  p.nav("知识图谱").click();
  await waitFor(() => p.hash() === "#知识图谱");
  calls.length = 0;
  p.nav("做题").click();
  await waitFor(() => calls.some(c => c.path === "/quiz/state"));
  await sleep(200);
  say(p.msgs().length === count, `消息流没有重复（${p.msgs().length} 条）`);
  say(p.selects()[0].value === "N4" && p.selects()[1].value === "挖空", "等级、考点还是刚才选的");
  say(!!p.btn("下一题"), "「下一题」还在");
  p.close();

  console.log("六、刷新");
  p = openPage("#" + encodeURIComponent("做题"));
  say(await waitFor(() => p.selects().length === 2 && p.selects()[0].value === "N4"
                       && p.selects()[1].value === "挖空"), "等级、考点填回上次的");
  say(await waitFor(() => p.stat() === "这一轮 1/1"), `成绩还在：${p.stat()}`);
  say(p.msgs().length === 0, "消息流是空的");
  say(!p.box() && !p.radios().length && !p.btn("作答"), "作答区不出现——看不见的题不能交");
  p.btn("开始").click();
  say(await waitFor(() => p.radios().length === 4), "点开始接着做");
  p.close();

  console.log("七、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500), "没有 5xx");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
