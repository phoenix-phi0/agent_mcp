// 教材页、学习进度页的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node pages_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_pages（实体、查询、接口、界面、内容），导入
// 知识点、课文、题目（拿掉一课的题，好看「没有题的课」），gen run 起真服务
// （不带 --real：离线的假模型客户端，这两页本来也不调模型）。
//
// 端口 8196：8197 上可能跑着用户自己的 kg 服务，别的 e2e 用 8192–8195、8198。
// 起服务前先看端口空不空，被占了直接报出来，不去连别人的服务。
//
// 按人的操作顺序：
//   导航切到「教材」：课文表、顶栏等级「全部」、课数
//   选 N4 点搜索：只剩 N4；关键字「ようだ」按 Enter：只剩那一课
//   点标题：地址变 #教材?lesson=…，阅读视图（抬头、讲解、例句、条目），课文表收起
//   刷新：还是这一课；后退：回到课文表
//   点「练这一课」：地址变 #做题?lesson=…，出的是这一课的题；后退回到课文
//   地址直达 #教材?lesson=…；没有题的课不显示「练这一课」；没有这一课说清楚
//   学习进度：空库时一句提示和「去做题页」→ 去做题页答两道（一对一错）→
//     回来数字对、在学和最近作答有了；知识图谱浮层里写着这个点答对/答题

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_pages";
const PORT = 8196;
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const LESSON = "hb-n4-118";     // ～ようだ
const NOQ = "hb-n5-007";        // 导入时拿掉这一课的题

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
    calls.push({ path: url.pathname, status: r.status });
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
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    link: t => $$("a").find(a => a.textContent.trim() === t),
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    selects: () => $$(".bar-top select"),
    pick: (sel, v) => { sel.value = v; sel.dispatchEvent(new w.Event("change")); },
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    // 表格：按表头认是哪张（同一页上有好几张）
    table: head => $$(".screen table").find(t =>
      [...t.querySelectorAll("th")].map(th => th.textContent.trim()).join("|") === head),
    rows: head => { const t = pg.table(head); return t ? [...t.querySelectorAll("tbody tr")]
      .map(tr => [...tr.querySelectorAll("td")].map(td => td.textContent.trim())) : null; },
    texts: () => $$(".screen .dyn-v").map(e => e.textContent),
    copies: () => $$(".screen p.copy").map(e => e.textContent),
    // 题卡（做题页）
    card: () => $(".card"),
    choices: () => $$(".card .choice"),
    choice: k => $$(".card .choice").find(b => (b.querySelector(".choice-k") || {}).textContent === k),
    box: () => $(".card textarea"),
    verdict: () => $$(".card .dyn.prose .dyn-v").map(e => e.textContent).find(t => /^[○✗]/.test(t)) || "",
    close: () => w.close(),
  };
  return pg;
}

const LIST_HEAD = "等级|标题|一句话|题数";
const EX_HEAD = "日语|中文";
const ITEM_HEAD = "条目|所属知识点";

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
    `rows = [q for q in read_bank(BANK) if q.get('课文') != '${NOQ}']`,
    "r = c.post('/quiz/import', json={'form': {'rows': rows}})",
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

  const total = db("SELECT count(*) n FROM lesson")[0].n;
  const n4 = db("SELECT count(*) n FROM lesson WHERE level = 'N4'")[0].n;
  const L = db(`SELECT * FROM lesson WHERE code = '${LESSON}'`)[0];
  const exs = JSON.parse(L.examples);

  console.log("一、切到教材");
  let p = openPage("");
  say(await waitFor(() => p.nav("教材") && p.nav("学习进度") && p.nav("知识图谱") && p.nav("做题")),
      "导航里有「教材」「学习进度」，原来的几项还在");
  calls.length = 0;
  p.nav("教材").click();
  say(await waitFor(() => p.hash() === "#教材"), `到了 ${p.hash()}`);
  say(await waitFor(() => (p.rows(LIST_HEAD) || []).length === total), `课文表 ${(p.rows(LIST_HEAD) || []).length} 行（库里 ${total}）`);
  // 顶栏两个下拉：系列（选项是接口给的，只有 hanabira 一项也显示）、等级
  say(await waitFor(() => p.selects().length === 2 && p.selects()[0].value === "hanabira"
                       && [...p.selects()[0].options].filter(o => o.value).length === 1),
      "顶栏最前面是系列下拉，只有一个系列也显示，选着 hanabira");
  say(p.selects()[1].value === "全部", "顶栏等级默认「全部」");
  say(p.texts().includes(`共${total}课`), "顶栏写着共几课");
  say(!p.table(EX_HEAD), "还没读课：没有例句表");
  say(!(p.$$(".stream .smsg").length), "没有往哪条消息流里推东西");

  console.log("二、按等级、关键字筛");
  p.pick(p.selects()[1], "N4");
  p.btn("搜索").click();
  say(await waitFor(() => (p.rows(LIST_HEAD) || []).length === n4), `选 N4 点搜索：${(p.rows(LIST_HEAD) || []).length} 行（库里 ${n4}）`);
  say(p.rows(LIST_HEAD).every(r => r[0] === "N4"), "每行都是 N4");
  const kw = p.$(".bar-top textarea");
  p.type(kw, "ようだ");
  p.enter(kw);
  say(await waitFor(() => (p.rows(LIST_HEAD) || []).length === 1), `关键字「ようだ」按 Enter：剩 ${(p.rows(LIST_HEAD) || []).length} 行`);
  say((p.rows(LIST_HEAD) || [[]])[0][1] === L.title, `是《${L.title}》`);
  p.type(kw, "没有这种课zzz");
  p.btn("搜索").click();
  say(await waitFor(() => !p.table(LIST_HEAD) && p.copies().some(t => t.includes("没有符合的课文"))),
      "搜不到：表收起，说一句没有符合的");
  p.type(kw, "ようだ");
  p.btn("搜索").click();
  await waitFor(() => (p.rows(LIST_HEAD) || []).length === 1);

  console.log("三、点标题读这一课");
  const a = p.$$(".screen a.cell-link").find(x => x.textContent.trim() === L.title);
  say(!!a, "标题是个链接");
  calls.length = 0;
  a.click();
  say(await waitFor(() => p.hash() === `#教材?lesson=${LESSON}`), `地址变成 ${p.hash()}`);
  say(await waitFor(() => p.texts().includes(`《${L.title}》　N4　第${Number(L.code.slice(-3))}课（${L.code}）`)), "顶栏是这一课的抬头（带课号）");
  say(calls.some(c => c.path === "/lesson/one" && c.status === 200), "调了「载入」拉这一课");
  say(p.texts().includes(L.summary) && p.texts().includes(L.explanation), "一句话、讲解都在");
  say(p.$$(".screen .dyn.prose .dyn-v").some(e => e.textContent === L.explanation), "讲解按正文排");
  say(p.texts().includes(L.formation), "接续在");
  const ex = p.rows(EX_HEAD) || [];
  say(ex.length === exs.length && ex[0][0] === exs[0].jp && ex[0][1] === exs[0].zh,
      `例句拆成 ${ex.length} 行（JSON 里 ${exs.length} 句）：${ex[0] && ex[0][0]}`);
  const items = p.rows(ITEM_HEAD) || [];
  say(items.some(r => r[0] === "ようだ"), `挂着的条目：${items.map(r => r.join("/"))}`);
  say(!p.table(LIST_HEAD) && !p.selects().length, "课文表和筛选收起来了");
  say(!!p.link("练这一课") && !!p.link("问老师") && !!p.link("← 回课文表"), "有「练这一课」「问老师」「回课文表」");
  say(!!p.link("请老师讲解这一课") && !!p.link("请老师讲解"), "有「请老师讲解这一课」（底下）和「请老师讲解」（顶上）");
  say(p.texts().some(t => t.startsWith("这一课有 ")), "写着这一课有几道题");
  p.close();

  console.log("四、刷新、后退");
  p = openPage("#" + encodeURIComponent("教材") + "?lesson=" + LESSON);
  say(await waitFor(() => p.texts().some(t => t.startsWith(`《${L.title}》　N4　`)) && (p.rows(EX_HEAD) || []).length === exs.length),
      "地址直达 #教材?lesson=…（也就是刷新）：直接是这一课");
  say(!p.table(LIST_HEAD), "直达时课文表不出来");
  // 先从课文表点进来，后退应该回到课文表
  p.close();
  p = openPage("#" + encodeURIComponent("教材"));
  await waitFor(() => (p.rows(LIST_HEAD) || []).length === total);
  p.$$(".screen a.cell-link").find(x => x.textContent.trim() === L.title).click();
  await waitFor(() => p.texts().some(t => t.startsWith(`《${L.title}》　N4　`)));
  p.w.history.back();
  say(await waitFor(() => p.hash() === "#教材" && (p.rows(LIST_HEAD) || []).length === total),
      `后退：回到课文表（${p.hash()}，${(p.rows(LIST_HEAD) || []).length} 行）`);
  say(p.selects().length === 2 && p.selects()[1].value === "全部", "回来时顶栏等级跟表一致（全部）");
  say(!p.table(EX_HEAD), "阅读视图收起来了");
  p.$$(".screen a.cell-link").find(x => x.textContent.trim() === L.title).click();
  await waitFor(() => p.texts().some(t => t.startsWith(`《${L.title}》　N4　`)));
  p.link("← 回课文表").click();
  say(await waitFor(() => p.hash() === "#教材" && p.table(LIST_HEAD)), "点「回课文表」也回去");

  console.log("五、练这一课、问老师");
  p.$$(".screen a.cell-link").find(x => x.textContent.trim() === L.title).click();
  await waitFor(() => p.link("练这一课"));
  p.link("练这一课").click();
  say(await waitFor(() => p.hash() === `#做题?lesson=${LESSON}`), `地址变成 ${p.hash()}`);
  say(await waitFor(() => p.card()), "做题页一打开就出了题");
  const cur = () => (db("SELECT current FROM quiz_state WHERE learner = 'me'")[0] || {}).current;
  say(await waitFor(() => (db(`SELECT lesson FROM question WHERE code = '${cur()}'`)[0] || {}).lesson === LESSON),
      `是这一课的题：${cur()}`);
  p.w.history.back();
  say(await waitFor(() => p.hash() === `#教材?lesson=${LESSON}` && p.texts().some(t => t.startsWith(`《${L.title}》　N4　`))
                       && (p.rows(EX_HEAD) || []).length === exs.length),
      "后退：回到这一课，例句还在");
  p.link("问老师").click();
  say(await waitFor(() => p.hash() === "#问老师" && p.$(".stream")), "点「问老师」：到了问老师页");
  p.close();

  console.log("六、没有题的课、没有这一课");
  const NQ = db(`SELECT * FROM lesson WHERE code = '${NOQ}'`)[0];
  p = openPage("#" + encodeURIComponent("教材") + "?lesson=" + NOQ);
  say(await waitFor(() => p.texts().some(t => t.startsWith(`《${NQ.title}》　${NQ.level}　`)) && p.rows(EX_HEAD)),
      `没有题的课照样能读：《${NQ.title}》`);
  say(!p.link("练这一课") && !!p.link("问老师"), "没有题：不显示「练这一课」，「问老师」还在");
  say(p.texts().some(t => t.includes("还没有题")), "说了这一课还没有题");
  p.close();
  p = openPage("#" + encodeURIComponent("教材") + "?lesson=hb-no-such");
  say(await waitFor(() => p.texts().some(t => t.includes("没有这一课") && t.includes("hb-no-such"))),
      "没有这一课：页面上说清楚");
  say(!p.table(EX_HEAD) && !p.link("练这一课"), "没有这一课：不出例句、不出「练这一课」");
  say(!!p.link("← 回课文表"), "能回课文表");
  p.close();

  console.log("七、学习进度：还没答过");
  const nodes = db("SELECT count(*) n FROM node")[0].n;
  p = openPage("");
  await waitFor(() => p.nav("学习进度"));
  calls.length = 0;
  p.nav("学习进度").click();
  say(await waitFor(() => p.texts().includes(`已掌握 0 / 总知识点 ${nodes}`)), `概览：已掌握 0 / 总知识点 ${nodes}`);
  say(p.copies().some(t => t.includes("还没有作答记录")), "说还没有作答记录");
  say(!!p.link("去做题页"), "有「去做题页」");
  say(!p.texts().some(t => t.startsWith("累计答题")), "没答过不摆答题数、正确率");
  say(!p.table("知识点|答对/答题|是否达标") && !p.table("时间|知识点|条目|对错"), "在学、最近作答不出来");
  say(!!p.table("知识点|第几步"), "对照：现在能学那张表在");
  say((p.rows("等级|已掌握/总数|答过的题") || []).map(r => r[0]).join() === "N5,N4,N3,N2,N1", "按等级五行");
  say(!p.table("知识点|得分|变化|打分时间"), "没打过分：得分整块不显示");
  say(!p.texts().some(t => t.startsWith("平均得分")), "没答过不摆平均得分");

  console.log("八、去做题页答两道（一对一错），回来看");
  p.link("去做题页").click();
  say(await waitFor(() => p.hash() === "#做题"), `到了 ${p.hash()}`);
  await waitFor(() => p.btn("开始"));
  p.btn("开始").click();
  async function answer(right) {
    await waitFor(() => p.choices().length || p.box());
    const q = db(`SELECT * FROM question WHERE code = '${cur()}'`)[0];
    // 库里的 current 先变，页面晚一拍才换题：等题卡上是这道题、上一道的结论没了再答，
    // 不然点到的是上一道已经答完（按钮禁用）的题卡，这一道根本没交
    const body = q.stem.split("\n").filter(l => !/^\s*[A-D]\s*[.．、:：]/.test(l)).join("\n").trim();
    const shown = await waitFor(() => !p.verdict() && (p.choices().length || p.box()) &&
      p.$$(".card .dyn-v").some(e => e.textContent.trim() === body));
    if (!shown) say(false, `题卡没换成 ${q.code}：${p.$$(".card .dyn-v").map(e => e.textContent).join(" / ")}`);
    if (p.choices().length) {
      // 选项打乱过：按内容找正确答案在界面上的那个按钮
      const line = q.stem.split("\n").find(l => new RegExp("^\\s*" + q.answer + "\\s*[.．、:：]").test(l)) || "";
      const want = line.replace(/^\s*[A-D]\s*[.．、:：]\s*/, "").trim();
      const btn = p.choices().find(b => (b.querySelector(".choice-t") || {}).textContent === want);
      if (!btn) say(false, `界面上找不到正确答案「${want}」：${p.choices().map(b => b.textContent)}`);
      (right ? btn : p.choices().find(b => b !== btn)).click();
    }
    else { p.type(p.box(), right ? q.answer : "ぜんぜんちがう"); p.btn("作答").click(); }
    await waitFor(() => p.verdict());
    return q;
  }
  const q1 = await answer(true);
  say(p.verdict().startsWith("○"), "第一道答对");
  p.btn("下一题").click();
  await waitFor(() => cur() !== q1.code);
  const q2 = await answer(false);
  say(p.verdict().startsWith("✗"), "第二道答错");
  p.nav("学习进度").click();
  say(await waitFor(() => p.texts().includes("累计答题 2") && p.texts().includes("正确率 50%")),
      `回来：${p.texts().filter(t => /累计|正确率/.test(t)).join("，")}`);
  say(p.texts().includes(`已掌握 0 / 总知识点 ${nodes}`), "还没达标：已掌握 0");
  say(!p.copies().some(t => t.includes("还没有作答记录")) && !p.link("去做题页"), "提示和「去做题页」收起来了");
  const pts = db("SELECT a.point, n.label, sum(a.correct) r, count(*) t FROM attempt a" +
                 " JOIN node n ON n.code = a.point GROUP BY a.point");
  const doing = p.rows("知识点|答对/答题|是否达标") || [];
  say(doing.length === pts.length && pts.every(x => doing.some(r => r[0] === x.label && r[1] === `${x.r}/${x.t}`)),
      `在学：${doing.map(r => r.join(" "))}`);
  const rec = p.rows("时间|知识点|条目|对错") || [];
  say(rec.length === 2 && rec[0][3] === "错" && rec[1][3] === "对", `最近作答新的在前：${rec.map(r => r[3])}`);
  const lbl = code => db(`SELECT n.label FROM question q JOIN item i ON i.code = q.item` +
                         ` JOIN node n ON n.code = i.point WHERE q.code = '${code}'`)[0].label;
  say(rec.length === 2 && rec[0][1] === lbl(q2.code) && rec[1][1] === lbl(q1.code), "最近作答关联到知识点名");
  const lv = p.rows("等级|已掌握/总数|答过的题") || [];
  const want = {};
  [q1, q2].forEach(q => { want[q.level] = (want[q.level] || 0) + 1; });
  say(lv.every(r => Number(r[2]) === (want[r[0]] || 0)), `按等级答过的题：${lv.map(r => r[0] + "=" + r[2])}`);
  // 答题时自动打的分：掌握得分区出现答过的点，分低的在前，概览有平均得分
  const curScores = db("SELECT n.label, s.value FROM score s JOIN node n ON n.code = s.point" +
                 " WHERE s.learner = 'me' AND s.id = (SELECT max(id) FROM score m" +
                 " WHERE m.learner = s.learner AND m.point = s.point) ORDER BY s.value, s.id DESC");
  const sc = p.rows("知识点|得分|变化|打分时间") || [];
  say(sc.length === pts.length && sc.length > 0 && sc.every((r, i) => r[0] === curScores[i].label && Number(r[1]) === curScores[i].value),
      `掌握得分区出现答过的点，分低的在前：${sc.map(r => r.join(" "))}`);
  say(sc.every(r => /^(首次|[+−]\d+|±0)$/.test(r[2]) && r[3]), `变化和打分时间：${sc.map(r => r[2] + " " + r[3])}`);
  const avg = Math.round(curScores.reduce((a, x) => a + x.value, 0) / curScores.length);
  say(p.texts().includes(`平均得分 ${avg}`), `概览有平均得分：${p.texts().filter(t => t.startsWith("平均得分"))}`);

  console.log("九、知识图谱浮层：答对/答题");
  const pt = pts[0];
  p.close();
  p = openPage("#" + encodeURIComponent("知识图谱") + "?" +
               new URLSearchParams({ "浮层": "节点详情", code: pt.point }));
  say(await waitFor(() => p.$$(".overlay .dyn").some(e => e.textContent.includes(`答对 ${pt.r} / 答题 ${pt.t}`))),
      `浮层里写着「答对 ${pt.r} / 答题 ${pt.t}」`);
  const ptScore = db(`SELECT value FROM score WHERE learner = 'me' AND point = '${pt.point}' ORDER BY id DESC LIMIT 1`)[0].value;
  const scoreCell = () => p.$$(".overlay .dyn").find(e => e.textContent.includes("得分") && !e.textContent.includes("答对"));
  say(await waitFor(() => scoreCell() && scoreCell().textContent.includes(String(ptScore))),
      `答对/答题后面有「得分 ${ptScore}」：${scoreCell() && scoreCell().textContent.trim()}`);
  const fresh = db("SELECT code FROM node WHERE code NOT IN (SELECT point FROM attempt) LIMIT 1")[0].code;
  p.close();
  p = openPage("#" + encodeURIComponent("知识图谱") + "?" +
               new URLSearchParams({ "浮层": "节点详情", code: fresh }));
  say(await waitFor(() => p.$$(".overlay .dyn").some(e => e.textContent.includes("还没做过"))),
      "没做过的点写「还没做过」");
  say(!scoreCell(), "没打过分的点不显示得分");
  p.close();

  console.log("十、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500), "没有 5xx");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
