// 教材导入（管理侧）的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node textbook_import_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_textbook_import，导入知识点、hanabira 课文、题目。
// gen run 起真服务（不带 --real：离线的假模型，按规则文件回话；解析一块的回复
// 慢 1 秒，看得到「正在解析」和轮询）。上传的是测试里现造的几行 md，不是真教材。
//
// 端口 8188：8197 上可能跑着用户自己的 kg 服务，别的 e2e 用 8191–8196、8198、8199。
// 起服务前先看端口空不空，被占了直接报出来，不去连别人的服务。
//
// 按人的操作顺序：
//   导航：「教材导入」在右边「管理」那组，不跟学习者的页面混排
//   进去：新建表单，改写默认勾着；填系列代号、显示名，选 md 文件，「开始解析」
//   跳到审阅页：看到「正在解析」，页面自己轮询，跑完变「解析完了」，草稿课表 3 课
//   点一课的标题进编辑页：改标题、保存；回审阅页
//   「全部通过有映射的课」：两课通过、孤课留着待审
//   「确认导入」：导入报告；点「去教材页看看」
//   教材页的系列下拉里有新系列；选它，课文表是它的 2 课；读一课；「请老师讲解」
//   回教材导入页：系列表里有它；进系列页「撤下这个系列」，浮层里确认；下拉里没了

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_textbook_import";
const PORT = 8188;
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const EXPLAIN = "老师讲：这一课说先做完一件事再做下一件。";
const BOOK = [
  "# 测试小教材（测试里现造的）",
  "",
  "## 第1课 てから",
  "做完一件事再做另一件。",
  "",
  "## 第2课 たい",
  "想做什么。",
  "",
  "## 第3课 ながら",
  "一边一边。",
  "",
].join("\n");
const lesson = (seq, title, items, points) => ({
  seq, title, level: "N5", summary: `${title}的一句话`, explanation: `${title}的讲解（模型改写）。`,
  formation: "", examples: [{ jp: "食べてから行きます。", zh: "吃完再去。" }],
  items, points, confidence: 0.8, reason: "测试",
});

let pass = 0, fail = 0;
const say = (ok, msg) => { ok ? pass++ : fail++; console.log((ok ? "  ✓ " : "  ✗ ") + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 5000) {
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
function portFree(port) {
  return new Promise(res => {
    const s = net.connect(port, "127.0.0.1");
    s.on("connect", () => { s.destroy(); res(false); });
    s.on("error", () => res(true));
  });
}

const calls = [];
function openPage(hash) {
  const html = fs.readFileSync(WEB + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/" + (hash || ""), runScripts: "outside-only" });
  const w = dom.window;
  // 上传走 FormData：用 Node 自己的 FormData / File，Node 的 fetch 才会把它
  // 编成 multipart（jsdom 的 FormData Node 不认）
  w.FormData = FormData;
  w.fetch = async (u, o = {}) => {
    const url = new URL(u, BASE);
    const r = await fetch(url, { ...o, signal: undefined });
    let body = null;
    if (o.body instanceof FormData) body = { multipart: true, payload: JSON.parse(o.body.get("payload")) };
    else if (o.body) body = JSON.parse(o.body);
    calls.push({ path: url.pathname, status: r.status, body });
    return r;
  };
  w.alert = m => { calls.push({ alert: m }); };
  w.console.log = () => {};
  w.console.warn = () => {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + "/app.js", "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const field = lbl => $$(".screen label.field").find(l => (l.querySelector(".lbl") || {}).textContent
    && l.querySelector(".lbl").textContent.replace("*", "").trim() === lbl);
  const pg = {
    w, $, $$,
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    link: t => $$("a").find(a => a.textContent.trim() === t),
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    field,
    type: (lbl, v) => {
      const el = field(lbl).querySelector("input,textarea");
      el.value = v;
      el.dispatchEvent(new w.Event("input"));
    },
    table: head => {
      const t = $$(".screen table").find(t =>
        [...t.querySelectorAll("th")].map(th => th.textContent.trim()).filter(Boolean).join("|") === head);
      return t ? [...t.querySelectorAll("tbody tr")].map(tr => [...tr.querySelectorAll("td")]) : null;
    },
    texts: () => $$(".screen .dyn-v").map(e => e.textContent),
    msgs: () => $$(".stream .smsg").map(m => ({
      who: (m.querySelector(".who") || {}).textContent || "",
      text: (m.querySelector(".body") || {}).textContent || "",
    })),
    close: () => w.close(),
  };
  return pg;
}

let server = null;
(async () => {
  if (!(await portFree(PORT))) {
    console.log(`端口 ${PORT} 已经被占用，不去连别人的服务。先停掉它再跑`);
    process.exit(1);
  }

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

  const reply = ls => JSON.stringify({ lessons: ls });
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [
      { when: ["块标题「第1课 てから」"], delay: 1,
        reply: reply([lesson(1, "〜てから", ["te-kara", "no-such-item"], ["f-time"])]) },
      { when: ["块标题「第2课 たい」"], delay: 1,
        reply: reply([lesson(2, "〜たい", [], ["f-desire"])]) },
      { when: ["块标题「第3课 ながら」"], delay: 1,
        reply: reply([lesson(3, "〜ながら", ["nagara-fake"], [])]) },
      { when: ["学生请你讲解教材里的这一课"], reply: EXPLAIN },
    ],
    default: '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}',
  }));

  server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器"],
                       { cwd: MCP, stdio: ["ignore", "pipe", "pipe"],
                         env: Object.assign({}, process.env, { DSL_MOCK_SCRIPT: MOCK }) });
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
  const hbLessons = db("SELECT count(*) n FROM lesson WHERE series = 'hanabira'")[0].n;

  console.log("一、导航：管理侧");
  let p = openPage("");
  await waitFor(() => p.nav("教材导入"));
  const side = p.$("nav .nav-side");
  say(!!side && side.querySelector(".nav-side-h").textContent.trim() === "管理"
      // 管理组里还有「学生管理」（多人模式的账号页，ui/student.ui），按 .ui 文件名排在前面
      && [...side.querySelectorAll("a")].map(a => a.textContent.trim()).join("|") === "学生管理|教材导入",
      "「教材导入」在右边「管理」那一组（同组还有「学生管理」）");
  const left = p.$$("nav > a").map(a => a.textContent.trim());
  say(left.includes("教材") && left.includes("问老师") && !left.includes("教材导入"),
      `学习者的页面在左边，不含教材导入：${left.join("、")}`);

  console.log("二、新建导入");
  p.nav("教材导入").click();
  say(await waitFor(() => p.btn("开始解析")), "进到教材导入页，有「开始解析」");
  const rewrite = () => p.field("改写讲解和例句（商业教材原文不能直接入库，模型用自己的话重写）").querySelector("input");
  say(await waitFor(() => rewrite().checked === true), "「改写讲解和例句」默认勾着");
  say(!p.field("覆盖已有系列").querySelector("input").checked, "「覆盖已有系列」默认不勾");
  say(await waitFor(() => p.$$(".screen p.copy").some(e => e.textContent.includes("还没有导入任务"))), "还没有导入任务");
  calls.length = 0;
  p.btn("开始解析").click();
  say(await waitFor(() => p.$(".toast") && p.$(".toast").textContent.includes("系列代号")),
      `什么都没填就点：提示条说要填系列代号：${p.$(".toast") && p.$(".toast").textContent}`);
  p.type("系列代号", "minna");
  p.type("显示名", "小测试教材");
  p.type("来源", "测试里现造");
  p.type("授权", "自用");
  const fileInput = p.field("教材文件").querySelector("input[type=file]");
  say(fileInput.getAttribute("accept") === ".pdf,.docx,.md,.txt", `文件框只列 pdf/docx/md/txt：${fileInput.getAttribute("accept")}`);
  const file = new File([BOOK], "small_book.md", { type: "text/markdown" });
  Object.defineProperty(fileInput, "files", { value: [file], configurable: true });
  fileInput.dispatchEvent(new p.w.Event("change"));
  calls.length = 0;
  p.btn("开始解析").click();
  say(await waitFor(() => p.hash().startsWith("#教材导入?job=")), `跳到审阅页：${p.hash()}`);
  const create = calls.find(c => c.path === "/import/create") || {};
  say(create.body && create.body.multipart && create.body.payload.form.series === "minna"
      && create.body.payload.form.rewrite === true,
      "提交走 multipart：表单字段（系列代号、改写）和文件一起到后端");
  const job = p.hash().split("job=")[1];
  say(await waitFor(() => p.texts().some(t => t.startsWith("正在解析：")), 3000),
      `看到进度：${p.texts().find(t => t.includes("解析")) || ""}`);
  say(await waitFor(() => p.texts().some(t => t.startsWith("解析完了：3 块，抽出 3 课")), 15000),
      `页面自己轮询，跑完：${p.texts().find(t => t.includes("解析")) || ""}`);
  const polls = calls.filter(c => c.path === "/import/poll").length;
  say(polls >= 1, `解析中时轮询了 /import/poll（${polls} 次）`);
  await sleep(2500);
  say(calls.filter(c => c.path === "/import/poll").length === polls, "跑完就不再轮询");
  const drafts = () => (p.table("课序|标题|等级|映射|问题|把握|审阅") || []);
  say(await waitFor(() => drafts().length === 3), `草稿课表 3 课：${drafts().map(r => r[1].textContent).join("、")}`);
  const r0 = drafts()[0].map(td => td.textContent.trim());
  say(r0[3].includes("てから") && r0[4].includes("丢掉了库里没有的编号"),
      `第一课映射到てから，问题里说丢掉了库里没有的编号：${r0[3]} / ${r0[4]}`);
  const r2 = drafts()[2].map(td => td.textContent.trim());
  say(r2[3] === "（没有）" && r2[4].includes("没映射到"), `第三课是孤课：${r2[4]}`);

  console.log("三、编辑一课");
  drafts()[1][1].querySelector("a").click();
  say(await waitFor(() => p.hash().startsWith("#教材导入?draft=")), `进编辑页：${p.hash()}`);
  say(await waitFor(() => p.field("标题") && p.field("标题").querySelector("input").value === "〜たい"),
      "标题填回来了");
  const maps = () => p.table("种类|编号|名称") || [];
  say(await waitFor(() => maps().length === 1 && maps()[0][1].textContent.trim() === "f-desire"),
      "映射表：知识点 f-desire");
  p.type("标题", "〜たい（想做）");
  p.btn("保存").click();
  say(await waitFor(() => p.texts().includes("保存了。")), "保存了");
  say(db(`SELECT title FROM import_lesson WHERE job = ${job} AND seq = 2`)[0].title === "〜たい（想做）",
      "库里的草稿标题改了");
  p.link("← 回审阅页").click();
  say(await waitFor(() => drafts().length === 3 && drafts()[1][1].textContent.trim() === "〜たい（想做）"),
      "回审阅页，表里是新标题");

  console.log("四、通过、确认导入");
  p.btn("全部通过有映射的课").click();
  say(await waitFor(() => drafts().map(r => r[6].textContent.trim()).join("|") === "通过|通过|待审"),
      `有映射的两课通过，孤课待审：${drafts().map(r => r[6].textContent.trim())}`);
  p.btn("确认导入").click();
  say(await waitFor(() => p.texts().some(t => t.startsWith("导入报告：导入 2 课"))),
      `导入报告：${p.texts().find(t => t.startsWith("导入报告")) || ""}`);
  say(db("SELECT count(*) n FROM lesson WHERE series = 'minna'")[0].n === 2, "库里有这个系列的 2 课");
  say(fs.existsSync(PROJ + "/content/series/minna/lessons.jsonl"), "写了 content/series/minna/lessons.jsonl");

  console.log("五、教材页");
  p.link("去教材页看看").click();
  say(await waitFor(() => p.hash() === "#教材"), "到了教材页");
  const sel = () => p.$$(".bar-top select")[0];
  say(await waitFor(() => sel() && [...sel().options].some(o => o.value === "minna" && o.textContent === "小测试教材")),
      "系列下拉里有新系列「小测试教材」");
  sel().value = "minna";
  sel().dispatchEvent(new p.w.Event("change"));
  const rows = () => { const t = p.$$(".screen table").find(t =>
    [...t.querySelectorAll("th")].map(th => th.textContent.trim()).join("|") === "等级|标题|一句话|题数");
    return t ? [...t.querySelectorAll("tbody tr")].map(tr => [...tr.querySelectorAll("td")]) : []; };
  say(await waitFor(() => rows().length === 2), `选了它课文表是它的 2 课：${rows().map(r => r[1].textContent.trim())}`);
  rows()[0][1].querySelector("a").click();
  say(await waitFor(() => p.hash() === "#教材?lesson=minna-001"), `读一课：${p.hash()}`);
  say(await waitFor(() => p.texts().some(t => t.includes("〜てから的讲解（模型改写）。"))), "讲解是草稿里的内容");
  const ex = p.$$(".screen a").find(x => x.textContent.trim() === "请老师讲解");
  say(!!ex, "有「请老师讲解」");
  ex.click();
  say(await waitFor(() => p.msgs().some(m => m.who === "老师" && m.text === EXPLAIN), 8000), "老师讲了这一课");
  const sent = calls.find(c => c.path === "/teacher/send") || {};
  say(sent.body && sent.body.form.lesson === "minna-001", "请求带着这一课的课号");

  console.log("六、撤下系列");
  p.nav("教材导入").click();
  const seriesRows = () => p.table("代号|名称|课数|状态") || [];
  say(await waitFor(() => seriesRows().length === 1 && seriesRows()[0][3].textContent.trim() === "在用"),
      "首页的系列表里有它，在用");
  seriesRows()[0][1].querySelector("a").click();
  say(await waitFor(() => p.btn("撤下这个系列")), `系列页：${p.texts().find(t => t.startsWith("系列 minna")) || ""}`);
  p.btn("撤下这个系列").click();
  say(await waitFor(() => p.$(".overlay") && p.hash().includes("manage=minna") && p.hash().includes("浮层=")),
      `确认浮层，地址里还带着 manage：${p.hash()}`);
  p.$$(".overlay button").find(b => b.textContent.trim() === "算了").click();
  say(await waitFor(() => !p.$(".overlay") && p.hash() === "#教材导入?manage=minna"), "点「算了」：浮层关掉，回到系列页");
  say(db("SELECT count(*) n FROM lesson WHERE series = 'minna'")[0].n === 2, "没撤");
  p.btn("撤下这个系列").click();
  await waitFor(() => p.$(".overlay"));
  p.$$(".overlay button").find(b => b.textContent.trim() === "确认撤下").click();
  say(await waitFor(() => p.texts().some(t => t.startsWith("撤下了："))), "确认后撤下了");
  say(db("SELECT count(*) n FROM lesson WHERE series = 'minna'")[0].n === 0
      && db("SELECT sort FROM series WHERE code = 'minna'")[0].sort === -1, "库里课清空，sort = -1");
  say(db("SELECT count(*) n FROM lesson WHERE series = 'hanabira'")[0].n === hbLessons, "hanabira 一课不少");
  p.close();
  p = openPage("#" + encodeURIComponent("教材"));
  const sel2 = () => p.$$(".bar-top select")[0];
  say(await waitFor(() => sel2() && sel2().options.length > 1 && ![...sel2().options].some(o => o.value === "minna")),
      "教材页的下拉里没有它了");
  p.close();

  console.log(`\n通过 ${pass}，失败 ${fail}`);
  stop(fail ? 1 : 0);
})().catch(e => {
  // 崩了也要把服务停掉，不然端口一直占着，下次跑直接报「被占用」
  console.log("崩了：", e);
  if (server) server.kill();
  process.exit(1);
});
