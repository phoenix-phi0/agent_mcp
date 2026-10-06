// 问老师的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node teacher_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_teacher（实体、查询、接口、界面、内容），导入
// 知识点、课文、题目，gen run 起真服务（不带 --real：离线的假模型客户端）。
// 假模型按规则文件回话（环境变量 DSL_MOCK_SCRIPT，见 tools/mock.py）：
// 意图判定那次按学习者原话回预设的 JSON，老师回答回一句固定的话。
//
// 端口 8194：8197 上可能跑着用户自己的 kg 服务，做题页的测试用 8192。起服务
// 前先看端口空不空，被占了直接报出来，不去连别人的服务。
//
// 按人的操作顺序：
//   导航切到「问老师」：消息流是空的，进来时拉了一次历史
//   输入「てから怎么用」按 Enter：自己的话先出现，然后老师的回答出现在消息流
//   「给我出几道てから的题」：老师回一句话和链接，没有题卡、没有判分；
//     点链接 → 地址变成 #做题?lesson=…，做题页直接出那一课的题
//   切回「问老师」：刚才的对话还在，没有叠两份；刷新：从库里拉回来
//   讲解那条下面有两个链接（读课文、练一练），刷新后也在；点「读课文」→
//     地址变成 #教材?lesson=…，教材页的阅读视图显示的正是那一课
//   教材页点「请老师讲解」→ 到问老师页，地址里的 lesson 随即去掉；历史对话
//     先回来，后面接上「请老师讲解《…》这一课」和老师的讲解，讲解下面是
//     「做这课的题」；之后发的话不带 lesson；刷新不会再讲一遍；点「做这课
//     的题」出那一课的题

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_teacher";
const PORT = 8194;
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const REPLY = "てから表示先做前一件事再做后一件。";
const EXPLAIN = "这一课讲 てから：先做前一件事，再做后一件。";

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
  w.fetch = async (u, o = {}) => {
    const url = new URL(u, BASE);
    // 页面传的 signal 是 jsdom 的 AbortSignal，Node 的 fetch 不认（报不是 AbortSignal 的实例），去掉
    const r = await fetch(url, { ...o, signal: undefined });
    calls.push({ path: url.pathname, status: r.status, body: o.body ? JSON.parse(o.body) : null });
    return r;
  };
  w.console.log = () => {};
  w.console.warn = () => {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + "/app.js", "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const pg = {
    w, $, $$,
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    box: () => $(".screen textarea"),
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    msgs: () => $$(".stream .smsg").map(m => ({
      who: (m.querySelector(".who") || {}).textContent || "",
      text: (m.querySelector(".body") || {}).textContent || "",
      link: m.querySelector("a.smsg-link"),
      links: [...m.querySelectorAll("a.smsg-link")],
      kind: m.className,
    })),
    teacher: () => pg.msgs().filter(m => m.who === "老师"),
    card: () => $(".card"),
    close: () => w.close(),
  };
  return pg;
}

(async () => {
  if (!(await portFree(PORT))) {
    console.log(`端口 ${PORT} 已经被占用，不去连别人的服务。先停掉它再跑`);
    process.exit(1);
  }

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

  // 假模型的规则：按顺序找第一条命中的（几个词都出现才算），都不中回 default。
  // 意图判定的系统提示词里有「意图分类器」，学习者原话跟在「学习者的消息：」后面
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [
      // 讲一课那一路的提示词（routes/teacher.zs）
      { when: ["学生请你讲解教材里的这一课"], reply: EXPLAIN },
      { when: ["意图分类器", "学习者的消息：给我出几道てから的题"],
        reply: '{"intent":"出题","keywords":["てから"],"level":"","kind":"","grade":"否"}' },
      { when: ["意图分类器"],
        reply: '{"intent":"讲解","keywords":["てから"],"level":"","kind":"","grade":"否"}' },
    ],
    default: REPLY,
  }));
  const lesson = db("SELECT code, title, summary FROM lesson WHERE title LIKE '%てから%'")[0];

  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器"],
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

  console.log("一、切到问老师");
  let p = openPage("");
  say(await waitFor(() => p.nav("问老师") && p.nav("做题") && p.nav("知识图谱")),
      "导航里有「知识图谱」「做题」「问老师」");
  calls.length = 0;
  p.nav("问老师").click();
  say(await waitFor(() => p.hash() === "#问老师"), `到了 ${p.hash()}`);
  say(await waitFor(() => calls.some(c => c.path === "/teacher/state" && c.status === 200)),
      "进来时拉了一次对话历史");
  say(await waitFor(() => p.box()) && p.msgs().length === 0, "有输入框，消息流是空的");

  console.log("二、问一句：Enter 发送，老师回答出现在消息流");
  p.type(p.box(), "てから怎么用");
  p.enter(p.box());
  say(await waitFor(() => p.msgs().some(m => m.who === "你" && m.text === "てから怎么用")),
      "自己的话先出现在消息流");
  say(await waitFor(() => p.teacher().length === 1), "老师的回答出现了");
  let t = p.teacher()[0] || {};
  // 回的是规则文件里那句：「用 快」「用 平衡」都由离线假模型接住，没去起 claude
  say(t.text === REPLY, `回答的内容：${t.text}`);
  say(t.link && t.link.textContent.includes(lesson.title),
      `回答下面附了这一课的做题链接：${t.link && t.link.textContent}`);
  say(p.box().value === "", "输入框清空了");
  say(!p.msgs().some(m => m.kind.includes("pending")), "「…」占位收掉了");
  let rows = db("SELECT role, content, intent FROM chat_message WHERE learner = 'me' ORDER BY id");
  say(rows.length === 2 && rows[0].role === "learner" && rows[1].content === REPLY && rows[1].intent === "讲解",
      `库里两条对话记录：${JSON.stringify(rows.map(r => r.role + ":" + r.intent))}`);

  console.log("三、想做题：老师给链接，点了到做题页");
  p.type(p.box(), "给我出几道てから的题");
  p.enter(p.box());
  say(await waitFor(() => p.teacher().length === 2), "老师回了第二句");
  t = p.teacher()[1] || {};
  say(t.text.includes("做题页") && t.text.includes(lesson.title), `说了去做题页做哪一课：${t.text}`);
  say(!p.card() && !p.$$(".choice").length, "对话页上没有题卡、没有选项——老师不在对话里出题");
  say(db("SELECT count(*) n FROM attempt")[0].n === 0, "没有判分（学习记录是空的）");
  const a = t.link;
  say(a && decodeURIComponent(a.getAttribute("href")) === `#做题?lesson=${lesson.code}`,
      `链接是 #做题?lesson=${lesson.code}：${a && a.getAttribute("href")}`);
  calls.length = 0;
  a.click();
  say(await waitFor(() => p.hash() === `#做题?lesson=${lesson.code}`), `点链接，地址变成 ${p.hash()}`);
  say(await waitFor(() => calls.some(c => c.path === "/quiz/lesson" && c.status === 200)),
      "做题页按地址里的课文调了载入接口");
  say(await waitFor(() => p.card()), "一到做题页就出了题卡");
  const cur = db("SELECT q.lesson FROM quiz_state s JOIN question q ON q.code = s.current WHERE s.learner = 'me'")[0] || {};
  say(cur.lesson === lesson.code, `出的是那一课的题：${cur.lesson}`);

  console.log("四、切回问老师、刷新");
  calls.length = 0;
  p.nav("问老师").click();
  say(await waitFor(() => calls.some(c => c.path === "/teacher/state")), "切回来又拉了一次历史");
  await sleep(200);
  say(p.msgs().length === 4 && p.teacher().length === 2, `对话还在、没有叠两份：${p.msgs().length} 条`);
  p.close();
  p = openPage("#" + encodeURIComponent("问老师"));
  say(await waitFor(() => p.msgs().length === 4), `刷新后从库里拉回 ${p.msgs().length} 条`);
  const m = p.msgs();
  say(m[0].who === "你" && m[0].text === "てから怎么用" && m[1].who === "老师" && m[1].text === REPLY,
      "顺序和说话人都对");
  say(m[3].link && decodeURIComponent(m[3].link.getAttribute("href")) === `#做题?lesson=${lesson.code}`,
      "刷新后老师那条的链接还在");

  console.log("五、一条消息多个链接，点「读课文」到教材页读那一课");
  const ls = (m[1].links || []).map(a => ({ text: a.textContent, href: decodeURIComponent(a.getAttribute("href")) }));
  say(ls.length === 2, `讲解那条下面有两个链接（刷新后从库里拉回来的）：${JSON.stringify(ls)}`);
  say(ls[0] && ls[0].text === `读课文：《${lesson.title}》` && ls[0].href === `#教材?lesson=${lesson.code}`,
      `第一个是读课文：${JSON.stringify(ls[0])}`);
  say(ls[1] && ls[1].text.startsWith("练一练") && ls[1].href === `#做题?lesson=${lesson.code}`,
      `第二个是练一练：${JSON.stringify(ls[1])}`);
  say(p.$$(".smsg-links").length >= 1 && m[1].links.every(a => a.parentElement.classList.contains("smsg-links")),
      "两个链接排在一行（.smsg-links），旧的单个链接没有重复画");
  calls.length = 0;
  m[1].links[0].click();
  say(await waitFor(() => p.hash() === `#教材?lesson=${lesson.code}`), `点「读课文」，地址变成 ${p.hash()}`);
  say(await waitFor(() => calls.some(c => c.path === "/lesson/one" && c.status === 200)),
      `教材页按地址里的课调了载入接口：${JSON.stringify(calls.map(c => c.path))}`);
  say(await waitFor(() => p.$(".screen") && p.$(".screen").textContent.includes(`《${lesson.title}》`)
                          && p.$(".screen").textContent.includes(lesson.summary)),
      `阅读视图显示的是《${lesson.title}》：抬头和一句话都在`);
  say(!p.$$(".screen table").some(t => t.textContent.includes("一句话") && t.textContent.includes("题数")),
      "没有显示课文表（是阅读视图，不是列表）");
  p.close();

  console.log("七、教材页「请老师讲解」→ 问老师页讲这一课");
  const before = db("SELECT count(*) n FROM chat_message")[0].n;
  p = openPage("#" + encodeURIComponent("教材") + "?lesson=" + lesson.code);
  say(await waitFor(() => p.$(".screen") && p.$(".screen").textContent.includes(lesson.summary)),
      "教材页读这一课");
  const ex = () => p.$$(".screen a").filter(a => a.textContent.trim().startsWith("请老师讲解"));
  say(await waitFor(() => ex().length === 2), `顶上和底下各有一个「请老师讲解」：${ex().map(a => a.textContent.trim())}`);
  say(ex().every(a => decodeURIComponent(a.getAttribute("href")) === `#问老师?lesson=${lesson.code}`),
      `地址是 #问老师?lesson=${lesson.code}：${ex()[0] && ex()[0].getAttribute("href")}`);
  calls.length = 0;
  ex()[0].click();
  say(await waitFor(() => calls.some(c => c.path === "/teacher/send")), "到问老师页就发出了讲解请求");
  const sent = calls.find(c => c.path === "/teacher/send") || {};
  say(sent.body && sent.body.form && sent.body.form.lesson === lesson.code && !sent.body.form.content,
      `请求带着 lesson、没有 content：${JSON.stringify(sent.body && sent.body.form)}`);
  say(calls.findIndex(c => c.path === "/teacher/state") >= 0
      && calls.findIndex(c => c.path === "/teacher/state") < calls.findIndex(c => c.path === "/teacher/send"),
      `先拉历史再发请求：${calls.map(c => c.path)}`);
  say(await waitFor(() => p.hash() === "#问老师"), `地址里的 lesson 去掉了：${p.hash()}`);
  say(await waitFor(() => p.teacher().some(m => m.text === EXPLAIN), 8000), "老师的讲解出现在消息流");
  let ms = p.msgs();
  const k = ms.findIndex(m => m.text === EXPLAIN);
  say(k > 0 && ms[k - 1].who === "你" && ms[k - 1].text.includes(`《${lesson.title}》`),
      `讲解前面是「你：请老师讲解《${lesson.title}》…」：${k > 0 && ms[k - 1].text}`);
  say(ms.length - 2 === before, `历史对话还在、没有叠：${ms.length} 条（之前 ${before} 条）`);
  say(!ms.some(m => m.kind.includes("pending")), "「…」占位收掉了");
  const el = (ms[k] && ms[k].links || []).map(a => ({ text: a.textContent, href: decodeURIComponent(a.getAttribute("href")) }));
  say(el[0] && el[0].text.startsWith("做这课的题") && el[0].href === `#做题?lesson=${lesson.code}`,
      `讲解下面第一个链接是做这课的题：${JSON.stringify(el)}`);
  rows = db(`SELECT role, intent, lesson FROM chat_message ORDER BY id DESC LIMIT 2`);
  say(rows.every(r => r.intent === "讲解" && r.lesson === lesson.code), `库里两条记着这一课：${JSON.stringify(rows)}`);

  calls.length = 0;
  p.type(p.box(), "这一课的接续再说一遍");
  p.enter(p.box());
  say(await waitFor(() => p.teacher().filter(m => m.text === EXPLAIN).length === 2), "接着问「这一课」，还是讲这一课");
  const next = calls.find(c => c.path === "/teacher/send") || {};
  say(next.body && !("lesson" in next.body.form), `之后发的话不带 lesson：${JSON.stringify(next.body && next.body.form)}`);
  const n0 = db("SELECT count(*) n FROM chat_message")[0].n;
  p.close();
  calls.length = 0;
  p = openPage("#" + encodeURIComponent("问老师"));
  say(await waitFor(() => p.teacher().filter(m => m.text === EXPLAIN).length === 2), "刷新后讲解从库里拉回来");
  await sleep(300);
  say(!calls.some(c => c.path === "/teacher/send") && db("SELECT count(*) n FROM chat_message")[0].n === n0,
      "刷新没有再讲一遍");
  ms = p.msgs();
  const go = (ms.find(m => m.text === EXPLAIN) || {}).links || [];
  calls.length = 0;
  go[0] && go[0].click();
  say(await waitFor(() => p.hash() === `#做题?lesson=${lesson.code}`), `点「做这课的题」：${p.hash()}`);
  say(await waitFor(() => p.card()), "出了题卡");
  const cur2 = db("SELECT q.lesson FROM quiz_state s JOIN question q ON q.code = s.current WHERE s.learner = 'me'")[0] || {};
  say(cur2.lesson === lesson.code, `出的是那一课的题：${cur2.lesson}`);
  p.close();

  console.log("六、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500), "没有 5xx");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
