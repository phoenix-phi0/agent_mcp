// 教材系列的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node series_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_series，导入知识点、hanabira 课文、题目，再把
// content/series/_example（格式示例，2 课，映射到已有的条目 / 知识点）当第二套
// 教材导进来——测试库里给它在 series.jsonl 里加一行（sort 1，进下拉），正式的
// 种子里没有它。gen run 起真服务（不带 --real：离线的假模型，按规则文件回话）。
//
// 端口 8199：8197 上可能跑着用户自己的 kg 服务，别的 e2e 用 8191–8196、8198。
// 起服务前先看端口空不空，被占了直接报出来，不去连别人的服务。
//
// 按人的操作顺序：
//   导航切到「教材」：顶栏最前面是「系列」下拉，两项；课文表是 hanabira 的
//   下拉切到「示例教材」：不用点搜索，课文表就只剩这个系列的 2 课，顶栏写着
//     系列名、共2课；库里记下偏好；刷新还是这个系列
//   点标题读一课：抬头「第2课」（按课序），写着系列名，有「练这一课」
//   点「请老师讲解」：到问老师页，老师讲的是这一课，下面的链接带这一课的课号
//   点「做这课的题」：做题页出的是这一课映射的知识点下的题
//   切回 hanabira：课文表回到 125 课

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = process.env.M || require("path").resolve(__dirname, "../..");
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_series";
const PORT = 8199;
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const EXPLAIN = "这一课讲怎么说「想做某事」。";
const LESSON = "_example-002";
const TITLE = "示例：想做某事";

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
    // 页面传的 signal 是 jsdom 的 AbortSignal，Node 的 fetch 不认，去掉
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
    link: t => $$("a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    selects: () => $$(".bar-top select"),
    pick: (sel, v) => { sel.value = v; sel.dispatchEvent(new w.Event("change")); },
    rows: () => { const t = $$(".screen table").find(t =>
      [...t.querySelectorAll("th")].map(th => th.textContent.trim()).join("|") === "等级|标题|一句话|题数");
      return t ? [...t.querySelectorAll("tbody tr")].map(tr => [...tr.querySelectorAll("td")].map(td => td.textContent.trim())) : null; },
    texts: () => $$(".screen .dyn-v").map(e => e.textContent),
    msgs: () => $$(".stream .smsg").map(m => ({
      who: (m.querySelector(".who") || {}).textContent || "",
      text: (m.querySelector(".body") || {}).textContent || "",
      links: [...m.querySelectorAll("a.smsg-link")],
    })),
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

  fs.rmSync(PROJ, { recursive: true, force: true });
  execFileSync(PY, ["-c", [
    "import sys, shutil, pathlib, json",
    "sys.path.insert(0, '.')",
    "from tests.kg.helpers import make_ws, client",
    "from kg.__main__ import BANK, read_bank",
    `ws = pathlib.Path('${PROJ}'); ws.mkdir()`,
    "make_ws(ws)",
    "shutil.copytree('kg/ui', ws / 'ui')",
    "shutil.copytree('kg/content/series/_example', ws / 'content/series/_example', dirs_exist_ok=True)",
    "p = ws / 'content/series.jsonl'",
    "p.write_text(p.read_text(encoding='utf-8') + json.dumps({'code': '_example', 'label': '示例教材', 'sort': 1}, ensure_ascii=False) + '\\n', encoding='utf-8')",
    "c = client(ws)",
    "assert c.post('/kg/import2', json={'form': {}}).status_code == 200",
    "assert c.post('/lesson/import', json={'form': {}}).status_code == 200",
    "r = c.post('/lesson/import', json={'form': {'series': '_example'}})",
    "assert r.status_code == 200 and r.get_json()['lessons'] == '2', r.get_json()",
    "r = c.post('/quiz/import', json={'form': {'rows': read_bank(BANK)}})",
    "assert r.status_code == 200, r.get_json()",
  ].join("\n")], { cwd: MCP, encoding: "utf8" });

  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [{ when: ["学生请你讲解教材里的这一课"], reply: EXPLAIN }],
    default: '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}',
  }));

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

  const total = db("SELECT count(*) n FROM lesson WHERE series = 'hanabira'")[0].n;
  const mapped = db(`SELECT q.code FROM question q JOIN item i ON i.code = q.item
                     JOIN lesson_point lp ON lp.point = i.point WHERE lp.lesson = '${LESSON}'`).map(r => r.code);

  console.log("一、教材页的系列下拉");
  let p = openPage("");
  await waitFor(() => p.nav("教材"));
  p.nav("教材").click();
  say(await waitFor(() => (p.rows() || []).length === total), `课文表是 hanabira 的 ${total} 课`);
  const sel = () => p.selects()[0];
  say(p.selects().length === 2 && sel().value === "hanabira", "顶栏最前面是系列下拉（等级前），选着 hanabira");
  const opts = [...sel().options].filter(o => o.value).map(o => `${o.value}=${o.textContent}`);
  say(JSON.stringify(opts) === JSON.stringify(["hanabira=hanabira 语法", "_example=示例教材"]),
      `下拉两项（名称从 series 表来）：${opts}`);
  say(p.texts().includes("hanabira 语法"), "顶栏写着系列名");

  console.log("二、切到示例教材");
  calls.length = 0;
  p.pick(sel(), "_example");
  say(await waitFor(() => (p.rows() || []).length === 2), `不用点搜索，课文表换成 ${(p.rows() || []).length} 课`);
  say(calls.some(c => c.path === "/lesson/list" && c.body && c.body.form.series === "_example"),
      "切换就提交了 lesson_list，带着 series");
  say((p.rows() || []).map(r => r[1]).join("|") === "示例：做完再做（てから）|" + TITLE, `是 _example 的两课：${(p.rows() || []).map(r => r[1])}`);
  say(p.texts().includes("示例教材") && p.texts().includes("共2课"), "顶栏：系列名、共2课");
  say(JSON.stringify(db("SELECT learner, series FROM learner_pref")) === '[{"learner":"me","series":"_example"}]',
      "库里记下了偏好");
  p.close();
  p = openPage("#" + encodeURIComponent("教材"));
  say(await waitFor(() => (p.rows() || []).length === 2 && sel() && sel().value === "_example"),
      "刷新：还是示例教材（按偏好）");

  console.log("三、读一课");
  const a = p.$$(".screen a.cell-link").find(x => x.textContent.trim() === TITLE);
  say(!!a, "标题是链接");
  a.click();
  say(await waitFor(() => p.hash() === `#教材?lesson=${LESSON}`), `地址 ${p.hash()}`);
  say(await waitFor(() => p.texts().includes(`《${TITLE}》　N5　第2课（${LESSON}）`)), "抬头按课序写「第2课」、带课号");
  say(p.texts().includes("示例教材"), "阅读顶栏写着系列名");
  say(await waitFor(() => !!p.link("练这一课")) && p.texts().includes(`这一课有 ${mapped.length} 道题`),
      `「练这一课」在，题数按映射算（${mapped.length}）`);

  console.log("四、请老师讲解");
  const ex = p.$$(".screen a").find(x => x.textContent.trim() === "请老师讲解");
  say(!!ex && decodeURIComponent(ex.getAttribute("href")) === `#问老师?lesson=${LESSON}`,
      `「请老师讲解」的地址带课号：${ex && decodeURIComponent(ex.getAttribute("href"))}`);
  calls.length = 0;
  ex.click();
  say(await waitFor(() => p.msgs().some(m => m.who === "老师" && m.text === EXPLAIN), 8000), "老师讲的是这一课");
  const sent = calls.find(c => c.path === "/teacher/send") || {};
  say(sent.body && sent.body.form.lesson === LESSON, `请求带着这一课：${JSON.stringify(sent.body && sent.body.form)}`);
  const ms = p.msgs();
  const t = ms.find(m => m.text === EXPLAIN) || { links: [] };
  const el = t.links.map(x => ({ text: x.textContent, href: decodeURIComponent(x.getAttribute("href")) }));
  say(el.length === 2 && el[0].href === `#做题?lesson=${LESSON}` && el[0].text === `做这课的题：《${TITLE}》（${mapped.length} 道）`
      && el[1].href === `#教材?lesson=${LESSON}` && el[1].text === `读课文：《${TITLE}》`,
      `讲解下面的链接带正确课号，当前系列的课不标系列名：${JSON.stringify(el)}`);
  say(ms.some(m => m.who === "你" && m.text.includes(`《${TITLE}》`)), "问话是「请老师讲解《示例：想做某事》…」");

  console.log("五、做这课的题");
  t.links[0].click();
  say(await waitFor(() => p.hash() === `#做题?lesson=${LESSON}`), `地址 ${p.hash()}`);
  const cur = () => (db("SELECT current FROM quiz_state WHERE learner = 'me'")[0] || {}).current;
  say(await waitFor(() => p.card() && mapped.includes(cur())), `出的是映射的知识点下的题：${cur()}`);
  p.close();

  console.log("六、切回 hanabira");
  p = openPage("#" + encodeURIComponent("教材"));
  await waitFor(() => (p.rows() || []).length === 2);
  p.pick(sel(), "hanabira");
  say(await waitFor(() => (p.rows() || []).length === total), `课文表回到 ${total} 课`);
  say(db("SELECT series FROM learner_pref WHERE learner = 'me'")[0].series === "hanabira", "偏好改回 hanabira");
  p.close();

  console.log(`\n通过 ${pass}，失败 ${fail}`);
  stop(fail ? 1 : 0);
})().catch(e => { console.log("崩了：", e); process.exit(1); });
