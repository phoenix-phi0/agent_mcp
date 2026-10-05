// 复习薄弱点的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node review_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_review，导入知识点、课文、题目，gen run 起真服务
// （不带 --real：离线的假模型，按规则文件回话，见 tools/mock.py）。
//
// 端口 8195：8197 上可能跑着用户自己的 kg 服务，别的 e2e 用 8192–8198 里的
// 其他几个。起服务前先看端口空不空，被占了直接报出来，不去连别人的服务。
//
// 按人的操作顺序：
//   还没答过题就打开 #做题?mode=review：一句「还没有作答记录，先按等级做几道」
//     和「开始」，不报错；点「开始」按 N5 出题，地址回到 #做题
//   造一段作答历史（两个点答错，A 比 B 错得多）
//   问老师「给我出点题」：老师回一句话，列出得分最低的点和分数，链接「复习
//     薄弱点」；点了 → 地址 #做题?mode=review，顶栏「复习薄弱点：A、B」，题来自
//     这两个低分点，第一道是 A
//   做完一轮 10 道（各题的条目都不同）：卡上「请老师总结这一轮」「再来一轮」，
//     顶栏没有「结束并请老师总结」；点总结 → 总结卡片
//   点顶栏「开始」退出复习模式，地址回到 #做题
//   学习进度页的概览里有「复习薄弱点」链接

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_review";
const PORT = 8195;
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const SUMMARY = "E2E复习总结：接续的几道错在同一个地方。";

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
    `r=[dict(x) for x in c.execute(${JSON.stringify(sql)})];c.commit();` +
    "print(json.dumps(r,ensure_ascii=False))";
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
  const pg = {
    w, $, $$,
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    btns: t => $$("button").filter(b => b.textContent.trim() === t),
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    link: t => $$("a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    box: () => $(".screen textarea"),
    cardBox: () => $(".card textarea"),
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    bar: () => $$(".bar-top .dyn-v").map(e => e.textContent),
    card: () => $(".card"),
    choices: () => $$(".card .choice"),
    verdict: () => $$(".card .dyn.prose .dyn-v").map(e => e.textContent).find(t => /^[○✗]/.test(t)) || "",
    teacher: () => $$(".stream .smsg").filter(m => ((m.querySelector(".who") || {}).textContent || "") === "老师"),
    text: () => ($(".screen") || {}).textContent || "",
    close: () => w.close(),
  };
  // 交一个答案（选第一个选项，或者随便写一段），等批改出来
  pg.answerAny = async () => {
    await waitFor(() => !pg.btn("下一题") && (pg.choices().length || pg.cardBox()));
    if (pg.choices().length) pg.choices()[0].click();
    else { pg.type(pg.cardBox(), "x"); pg.btn("作答").click(); }
    await waitFor(() => pg.verdict());
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
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [
      { when: ["意图分类器", "学习者的消息：给我出点题"],
        reply: '{"intent":"出题","keywords":[],"level":"","kind":"","grade":"否"}' },
      { when: ["意图分类器"],
        reply: '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}' },
      { when: ["总结这一轮"], reply: SUMMARY },
    ],
    default: "老师的回答",
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
  const QUIZ = "#" + encodeURIComponent("做题");

  console.log("一、还没答过题就进复习模式");
  let p = openPage(QUIZ + "?mode=review");
  say(await waitFor(() => p.text().includes("还没有作答记录，先按等级做几道")),
      "一句「还没有作答记录，先按等级做几道」");
  say(calls.some(c => c.path === "/quiz/lesson" && c.status === 200), "载入接口 200，不报错");
  say(!p.choices().length && !p.cardBox(), "没有题卡");
  const startInCard = p.btns("开始").find(b => b.closest(".card"));
  say(!!startInCard, "提示卡上有「开始」");
  startInCard.click();
  say(await waitFor(() => p.hash() === "#做题"), `点「开始」：地址回到 ${p.hash()}`);
  say(await waitFor(() => p.choices().length || p.cardBox()), "出了题");
  let st = db("SELECT pick_level, mode FROM quiz_state WHERE learner = 'me'")[0] || {};
  say(st.pick_level === "N5" && st.mode === null, `按 N5 出、不是复习模式：${JSON.stringify(st)}`);
  p.close();

  console.log("二、造作答历史：A 错三道、B 一对一错");
  // 一轮里每个条目只出一题：挑条目多的两个点（各至少 6 个条目），一轮 10 道才凑得够
  const pts = db("SELECT i.point, n.label FROM question q JOIN item i ON i.code = q.item" +
                 " JOIN node n ON n.code = i.point GROUP BY i.point HAVING count(DISTINCT q.item) >= 6 ORDER BY i.point LIMIT 2");
  const [A, B] = pts;
  const qa = db(`SELECT q.code FROM question q JOIN item i ON i.code = q.item WHERE i.point = '${A.point}' ORDER BY q.code LIMIT 3`);
  const qb = db(`SELECT q.code FROM question q JOIN item i ON i.code = q.item WHERE i.point = '${B.point}' ORDER BY q.code LIMIT 2`);
  const learn = async (point, item, correct) => {
    const r = await fetch(BASE + "/learn/answer", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ form: { point, item, correct: String(correct) } }) });
    return r.status;
  };
  const sts = [];
  for (const q of qa) sts.push(await learn(A.point, q.code, 0));
  sts.push(await learn(B.point, qb[0].code, 1));
  sts.push(await learn(B.point, qb[1].code, 0));
  say(sts.every(s => s === 200), `记了 5 条作答：${sts}`);
  const score = pt => db(`SELECT value FROM score WHERE learner = 'me' AND point = '${pt}' ORDER BY id DESC LIMIT 1`)[0].value;
  const sa = score(A.point), sb = score(B.point);
  say(sa < sb && sb < 80, `A「${A.label}」${sa} < B「${B.label}」${sb} < 80`);

  console.log("三、问老师「给我出点题」→ 复习薄弱点");
  p = openPage("#" + encodeURIComponent("问老师"));
  await waitFor(() => p.box());
  p.type(p.box(), "给我出点题");
  p.enter(p.box());
  say(await waitFor(() => p.teacher().length === 1), "老师回了一句");
  const t = p.teacher()[0];
  const tt = t ? t.textContent : "";
  say(tt.includes(`${A.label} ${sa}、${B.label} ${sb}`), `回复里列出得分最低的点和分数：${tt.slice(0, 80)}`);
  const rv = t && [...t.querySelectorAll("a.smsg-link")].find(a => a.textContent.trim() === "复习薄弱点");
  say(rv && decodeURIComponent(rv.getAttribute("href")) === "#做题?mode=review",
      `链接「复习薄弱点」→ #做题?mode=review：${rv && rv.getAttribute("href")}`);
  say(db("SELECT intent FROM chat_message WHERE role = 'teacher' ORDER BY id DESC LIMIT 1")[0].intent === "出题",
      "意图记成出题");
  calls.length = 0;
  rv.click();
  say(await waitFor(() => p.hash() === "#做题?mode=review"), `点了：地址是 ${p.hash()}`);
  say(await waitFor(() => calls.some(c => c.path === "/quiz/lesson" && c.status === 200)), "载入接口带着 mode 调了");
  say(await waitFor(() => p.choices().length || p.cardBox()), "出了题");
  const scope = p.bar().find(x => x.startsWith("复习薄弱点")) || "";
  say(scope === `复习薄弱点：${A.label}、${B.label}`, `顶栏：${scope}`);
  const curPoint = () => (db("SELECT i.point FROM quiz_state s JOIN question q ON q.code = s.current" +
                             " JOIN item i ON i.code = q.item WHERE s.learner = 'me'")[0] || {}).point;
  const seen = [curPoint()];
  say(seen[0] === A.point, `第一道来自得分最低的 A：${seen[0]}`);

  console.log("四、做完一轮 10 道");
  let n = 0;
  while (n < 12 && !p.btn("请老师总结这一轮")) {
    await p.answerAny();
    await waitFor(() => p.btn("下一题"));
    p.btn("下一题").click();
    await waitFor(() => p.btn("请老师总结这一轮") || (p.card() && !p.btn("下一题")));
    n++;
    if (!p.btn("请老师总结这一轮")) seen.push(curPoint());
  }
  say(n === 10, `做了 ${n} 道一轮结束`);
  const its = db("SELECT round_seen FROM quiz_state WHERE learner = 'me'")[0].round_seen.split(",").filter(Boolean)
    .map(c => db(`SELECT item FROM question WHERE code = '${c}'`)[0].item);
  say(its.length === 10 && new Set(its).size === 10, `一轮里各题的条目都不同：${its.join(",")}`);
  say(seen.every(x => x === A.point || x === B.point), `题都来自 A、B 两个低分点：${seen.join(",")}`);
  say(!!p.btn("请老师总结这一轮") && !!p.btn("再来一轮"), "卡上有「请老师总结这一轮」「再来一轮」");
  say(!p.btn("结束并请老师总结"), "顶栏没有「结束并请老师总结」（三种模式都一轮一轮来）");
  say(!p.link("换一课") && !p.link("回教材看这一课"), "没有「换一课」「回教材」");
  say(p.text().includes("这一轮复习做完了"), "卡上一句这一轮复习做完了");
  p.btn("请老师总结这一轮").click();
  say(await waitFor(() => p.$$(".card").some(e => e.textContent.includes(SUMMARY)), 4000), "总结出现在卡片上");
  const ch = db("SELECT content FROM chat_message WHERE intent = '总结' ORDER BY id");
  say(ch.length === 2 && ch[0].content.startsWith("（做完一轮：复习薄弱点，"), `对话记录：${ch.map(x => x.content.slice(0, 20))}`);

  console.log("五、点开始退出复习模式");
  p.btns("开始")[0].click();
  say(await waitFor(() => p.hash() === "#做题"), `地址回到 ${p.hash()}`);
  await waitFor(() => p.choices().length || p.cardBox());
  st = db("SELECT mode FROM quiz_state WHERE learner = 'me'")[0];
  say(st.mode === null, "库里的复习模式清掉了");
  say(!p.bar().some(x => x.startsWith("复习薄弱点")), "顶栏不再是复习薄弱点");

  console.log("六、学习进度页的复习链接");
  p.nav("学习进度").click();
  say(await waitFor(() => p.link("复习薄弱点")), "概览里有「复习薄弱点」");
  say(decodeURIComponent(p.link("复习薄弱点").getAttribute("href")) === "#做题?mode=review", "指向 #做题?mode=review");
  p.close();

  console.log("七、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500), "没有 5xx");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
