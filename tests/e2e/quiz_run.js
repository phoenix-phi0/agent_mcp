// 做题页的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node quiz_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_quiz（实体、查询、接口、界面、内容），导入
// 知识点、课文、题目，gen run 起真服务。页面在 jsdom 里跑，按人的操作点。
//
// 做题页是题卡式：一张卡上是抬头、题干、选项按钮（或输入框）、批改、
// 「下一题」。早先是三段式（题在中间消息流、A–D 单选在最底下的底栏），
// 用的人说选项放得太低——所以这里专门查：选项、输入框、下一题都在卡里；
// 换题是换一张新卡（翻页），判完是同一张卡原地更新。
//
//   导航切到「做题」：没有题卡，有一句提示
//   N4・接续 → 开始 → 卡里只有输入框；答错（Enter 交）→ 卡上出批改、
//     写着你交的；同一张卡；库里一条流水记在结构点上
//   下一题 → 新的一张卡、干净的；答对
//   挖空 → 卡里四个带内容的选项按钮，没有「作答」；点错的 → 选的红、答案绿、
//     全部锁住；下一题 → 选项干净；点对的
//   切走再切回来：还是那张卡；刷新：没有卡（看不见的题不能交）
//   老师给的链接：一打开就出那一课的题，答完下一题一直在这一课（每第三道
//     是易混对比题）；点「开始」退出按课练，地址回到 #做题
//   选项打乱：按钮上的字母跟题库里的不一样，判题、标红绿按界面上的位置
//   达标喜报：在做题页的题卡上看得见；问老师的消息流里没有它
//   请老师总结：按课做完一轮 → 「请老师总结这一轮」→ 等待的那句话 → 总结卡片
//     出现在做题页 → 「去问老师接着聊」到问老师页，历史里有这条总结；自由练
//     答满 5 道顶栏才出「结束并请老师总结」，点了题卡收起、计数清零。
//     假模型按规则文件回话（DSL_MOCK_SCRIPT）；总结请求在测试这边压 600 毫秒，
//     模拟模型慢，好看见等待的那句话

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_quiz";
const PORT = 8192;
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const SUMMARY = "E2E老师总结：本轮有两道错在易混的说法上，先回去读课文再练。";

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
// 题库里的原选项 {原字母: 内容}。界面上的选项打乱过，按内容对
function origOptions(q) {
  const out = {};
  for (const l of q.stem.split("\n")) {
    const m = l.match(/^\s*([A-D])\s*[.．、:：]\s*(.*)$/);
    if (m) out[m[1]] = m[2].trim();
  }
  return out;
}

const calls = [];
// 路径 → 压多少毫秒再发（模拟慢的接口）
const slow = {};
// 路径 → 不发请求，直接回这个（状态码, body）——模拟模型出错时路由器回的 502
const fake = {};
function openPage(hash) {
  const html = fs.readFileSync(WEB + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/" + (hash || ""), runScripts: "outside-only" });
  const w = dom.window;
  w.fetch = async (u, o = {}) => {
    const url = new URL(u, BASE);
    if (slow[url.pathname]) await sleep(slow[url.pathname]);
    if (fake[url.pathname]) {
      const [st, body] = fake[url.pathname];
      calls.push({ path: url.pathname, status: st, fake: true });
      return new Response(JSON.stringify(body), { status: st, headers: { "Content-Type": "application/json" } });
    }
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
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    selects: () => $$(".bar-top select"),
    pick: (sel, v) => { sel.value = v; sel.dispatchEvent(new w.Event("change")); },
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    // 顶栏有两个「显示」：scope（只练哪一课）和 stat（这一轮成绩），按内容认
    stat: () => $$(".bar-top .dyn-v").map(e => e.textContent).find(t => t.startsWith("这一轮")) || "",
    card: () => $(".card"),
    cardText: () => ($(".card") || {}).textContent || "",
    choices: () => $$(".card .choice"),
    choice: k => $$(".card .choice").find(b => (b.querySelector(".choice-k") || {}).textContent === k),
    // 内容是这一段的那个选项按钮（选项打乱过，不能按题库里的字母找）
    choiceText: s => $$(".card .choice").find(b => (b.querySelector(".choice-t") || {}).textContent === s),
    keyOf: b => (b.querySelector(".choice-k") || {}).textContent,
    // 跨界面状态（Vue 实例上的 shared），查别的界面的消息流里有什么
    shared: () => $("#app")._vnode.component.setupState.shared,
    // 批改：卡上以 ○ / ✗ 开头的那段正文
    verdict: () => $$(".card .dyn.prose .dyn-v").map(e => e.textContent).find(t => /^[○✗]/.test(t)) || "",
    box: () => $(".card textarea"),
    close: () => w.close(),
  };
  // 不管是哪种题，先交一个答案（按课文练时题型不固定）
  // 先等新题卡出来（「下一题」收起 = phase 回到 ask）：库里的当前题先变、
  // 题卡后画，只看库就去点的话点的是上一张判完的卡，「下一题」请求还在
  // 路上，再点一下被 busy 吞掉——跑全量时撞上过
  pg.answerAny = async () => {
    await waitFor(() => !pg.btn("下一题") && (pg.choices().length || pg.box()));
    if (pg.choices().length) pg.choices()[0].click();
    else { pg.type(pg.box(), "x"); pg.btn("作答").click(); }
    await waitFor(() => pg.verdict());
  };
  return pg;
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
  // 总结的系统提示词里有「总结这一轮」；别的（问老师）回一句默认的
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [{ when: ["总结这一轮"], reply: SUMMARY }], default: "老师的回答" }));

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
  say(!p.card() && !p.btn("作答") && !p.btn("下一题"), "还没出题：没有题卡");
  say(p.$$("p.copy").some(e => e.textContent.includes("点上面的「开始」")), "有一句提示告诉人点「开始」");

  console.log("二、接续题：答错");
  p.pick(p.selects()[0], "N4");
  p.pick(p.selects()[1], "接续");
  p.btn("开始").click();
  say(await waitFor(() => p.card()), "出了一张题卡");
  say(!p.$$("p.copy").some(e => e.textContent.includes("点上面的「开始」")), "出了题，提示收起来了");
  let q = question(state().current);
  say(q.level === "N4" && q.kind === "接续", `按选的出：${q.code}`);
  const line = q.stem.split("\n")[1] || q.stem;
  say(p.cardText().includes(line) && p.cardText().includes("N4・接续"), "卡上是这道题的抬头和题干");
  say(await waitFor(() => p.box() && !p.choices().length), "接续题：卡里只有输入框，没有选项按钮");
  say(p.card().contains(p.box()), "输入框就在题卡里（不在屏幕最底下）");
  const card1 = p.card();
  p.type(p.box(), "わかりません");
  p.enter(p.box());
  say(await waitFor(() => p.verdict()), "Enter 交了，卡上出了批改");
  say(p.verdict().startsWith("✗") && p.verdict().includes(q.answer), `判错，给了正确答案「${q.answer}」`);
  say(p.verdict().includes("考的是："), "批改里说了考的是哪个条目");
  say(p.cardText().includes("わかりません"), "卡上写着你交的是什么");
  say(p.card() === card1, "判完是同一张卡原地更新，没有翻页");
  say(await waitFor(() => !p.box() && !p.btn("作答") && p.btn("下一题")), "判完：输入框收起，出现「下一题」");
  say(p.card().contains(p.btn("下一题")), "「下一题」也在卡里");
  say(await waitFor(() => p.stat() === "这一轮 0/1"), `顶栏成绩：${p.stat()}`);
  const a = db("SELECT a.*, i.point AS want FROM attempt a JOIN question q ON q.code = a.item" +
               " JOIN item i ON i.code = q.item");
  say(a.length === 1 && a[0].correct === 0 && a[0].point === a[0].want && a[0].item === q.code,
      `库里一条流水，记在结构点 ${a[0] && a[0].point} 上`);
  // 批改下面一行得分变化：「知识点 得分 a → b」，第一次打分写「（第一次打分）」
  const scoreLine = qq => {
    const r = db(`SELECT s.value, n.label FROM score s JOIN item i ON i.point = s.point JOIN node n ON n.code = s.point` +
                 ` JOIN question q ON q.item = i.code WHERE q.code = '${qq.code}' AND s.learner = 'me' ORDER BY s.id DESC LIMIT 2`);
    if (!r.length) return "（没有得分）";
    return r.length === 1 ? `${r[0].label} 得分 ${r[0].value}（第一次打分）` : `${r[0].label} 得分 ${r[1].value} → ${r[0].value}`;
  };
  const want1 = scoreLine(q);
  say(await waitFor(() => p.$$(".card .dyn-v").some(e => e.textContent === want1)), `批改卡上有「${want1}」`);

  console.log("三、下一题：翻页、答对");
  const first = q.code;
  p.btn("下一题").click();
  say(await waitFor(() => state().current !== first && p.box()), "出了下一道，输入框回来了");
  say(p.card() !== card1, "换了一张新卡（翻页）");
  say(!p.verdict(), "新卡上没有上一道的批改");
  say(p.box().value === "", "输入框是空的（上一道写的清掉了）");
  q = question(state().current);
  // 这道的点上先记一个分（/score/add 手工记），答完就是「旧分 → 新分」
  const pt3 = db(`SELECT i.point FROM question q JOIN item i ON i.code = q.item WHERE q.code = '${q.code}'`)[0].point;
  const added = await (await fetch(BASE + "/score/add", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ form: { point: pt3, value: "1" } }) })).json();
  say(added.lists && added.lists.scores && added.lists.scores[0].value === 1, "这个点先手工记了 1 分");
  p.type(p.box(), q.answer);
  p.btn("作答").click();
  say(await waitFor(() => p.verdict().startsWith("○")), "判对");
  say(await waitFor(() => p.stat() === "这一轮 1/2"), `成绩接着算：${p.stat()}`);
  const want2 = scoreLine(q);
  say(/ 得分 1 → \d+$/.test(want2) &&
      await waitFor(() => p.$$(".card .dyn-v").some(e => e.textContent === want2)), `答对后卡上的得分：「${want2}」`);
  say(p.$$(".card .dyn-v").filter(e => e.textContent.includes(" 得分 ")).length === 1, "只有这一道的一行得分（上一道的没留着）");

  console.log("四、选择题：选项是卡里的大按钮，点了就交");
  p.pick(p.selects()[1], "挖空");
  p.btn("开始").click();
  say(await waitFor(() => p.choices().length === 4 && !p.box()), "挖空：卡里四个选项按钮，没有输入框");
  say(p.choices().every(b => p.card().contains(b)), "选项都在题卡里，就在题干下面");
  say(await waitFor(() => p.stat() === "这一轮 0/0"), `开始：这一轮清零 ${p.stat()}`);
  q = question(state().current);
  say(q.kind === "挖空" && q.level === "N4", `按新的考点出：${q.code}`);
  const optLine = q.stem.split("\n").find(l => /^A[.．]/.test(l)) || "";
  say(optLine && p.choices().some(b => b.textContent.includes(optLine.replace(/^A[.．]\s*/, "")))
      && p.choices().map(b => b.querySelector(".choice-t").textContent).sort().join("|")
         === Object.values(origOptions(q)).sort().join("|"),
      "按钮上写着选项内容，不只是字母（四个选项的内容都在，顺序打乱过）");
  say(!p.cardText().split("\n").some(l => /^A[.．]/.test(l.trim())), "题面里不再重复列一遍选项");
  say(!p.btn("作答") && !p.btn("下一题"), "选择题没有「作答」按钮——点选项就是交");
  let opts = origOptions(q);
  let rightBtn = p.choiceText(opts[q.answer]);
  const rightKey = p.keyOf(rightBtn);
  const wrong = ["A", "B", "C", "D"].find(k => k !== rightKey);
  const wrongText = p.choice(wrong).querySelector(".choice-t").textContent;
  p.choice(wrong).click();
  say(await waitFor(() => p.verdict()), "点了选项就交了");
  say(p.choice(wrong).className.includes("choice-wrong") && p.choice(rightKey).className.includes("choice-right"),
      `选的 ${wrong} 标红、答案（界面上的 ${rightKey}，题库里的 ${q.answer}）标绿`);
  say(p.verdict().includes("正确答案是 " + rightKey), `批改说正确答案是界面上的 ${rightKey}`);
  say(p.choices().every(b => b.disabled), "判完选项都锁住，不能再点");
  say(await waitFor(() => p.stat() === "这一轮 0/1"), `成绩：${p.stat()}`);
  say(opts[state().choice] === wrongText, "库里记着选的是哪个（题库里的原字母）");
  p.btn("下一题").click();
  say(await waitFor(() => p.choices().length === 4
                       && p.choices().every(b => !b.disabled && !/choice-(right|wrong|dim)/.test(b.className))),
      "下一题：新卡上的选项都是干净的、能点");
  q = question(state().current);
  p.choiceText(origOptions(q)[q.answer]).click();
  say(await waitFor(() => p.verdict().startsWith("○")), "选对（按内容找到的那个按钮）");
  say(await waitFor(() => p.stat() === "这一轮 1/2"), `成绩：${p.stat()}`);

  console.log("五、切走再切回来");
  const cardBefore = p.cardText();
  p.nav("知识图谱").click();
  await waitFor(() => p.hash() === "#知识图谱");
  calls.length = 0;
  p.nav("做题").click();
  await waitFor(() => calls.some(c => c.path === "/quiz/state"));
  await sleep(200);
  say(p.cardText() === cardBefore, "题卡还是刚才那张");
  say(p.selects()[0].value === "N4" && p.selects()[1].value === "挖空", "等级、考点还是刚才选的");
  say(!!p.btn("下一题"), "「下一题」还在");
  p.close();

  console.log("六、刷新");
  p = openPage("#" + encodeURIComponent("做题"));
  say(await waitFor(() => p.selects().length === 2 && p.selects()[0].value === "N4"
                       && p.selects()[1].value === "挖空"), "等级、考点填回上次的");
  say(await waitFor(() => p.stat() === "这一轮 1/2"), `成绩还在：${p.stat()}`);
  say(!p.card(), "没有题卡——看不见的题不能交");
  p.btn("开始").click();
  say(await waitFor(() => p.choices().length === 4), "点开始接着做");
  p.close();

  console.log("七、老师给的链接：按课文练");
  // 挑有易混对比、题最多的一课；链接的写法跟 kg/__main__.py 的 quiz_link 一样（界面名编码）
  const L = db("SELECT q.lesson, count(*) n FROM question q WHERE q.item IN " +
               "(SELECT a FROM contrast UNION SELECT b FROM contrast) GROUP BY q.lesson ORDER BY n DESC, q.lesson LIMIT 1")[0];
  const title = db(`SELECT title FROM lesson WHERE code = '${L.lesson}'`)[0].title;
  const lv = db(`SELECT level FROM lesson WHERE code = '${L.lesson}'`)[0].level;
  calls.length = 0;
  p = openPage("#" + encodeURIComponent("做题") + "?lesson=" + encodeURIComponent(L.lesson));
  say(await waitFor(() => calls.some(c => c.path === "/quiz/lesson" && c.status === 200)),
      "带 lesson 打开：调了载入接口");
  say(await waitFor(() => p.card()), "一打开就出了题，不用点开始");
  say(question(state().current).lesson === L.lesson, `是那一课的题：${state().current}`);
  say(await waitFor(() => p.$$(".bar-top .dyn-v").some(e => e.textContent.includes(title)
                                                        && e.textContent.includes("易混对比"))),
      `顶栏写着练这一课《${title}》（本课 + 易混对比）`);
  // 连做：本课的、或者是对比题（别的课、同等级或易混对比），不会跑到不相干的课
  const seq = [question(state().current)];
  const rightPos = [];
  const stuck = [];
  for (let i = 0; i < L.n + 1; i++) {
    const before = state().current;
    const cq = question(before);
    if (cq.qtype === "选择") {
      await waitFor(() => !p.btn("下一题") && p.choiceText(origOptions(cq)[cq.answer]));
      const rb = p.choiceText(origOptions(cq)[cq.answer]);
      rightPos.push(rb ? p.keyOf(rb) : "?");
    }
    await p.answerAny();
    await waitFor(() => p.btn("下一题"));
    p.btn("下一题").click();
    // 没换题（点击被吞了之类）要单独报出来，别混成「顺序不对」
    if (!await waitFor(() => state().current !== before)) stuck.push(i);
    seq.push(question(state().current));
  }
  say(!stuck.length, `每次点下一题都换了题${stuck.length ? "：第 " + stuck.join("、") + " 次没换" : ""}`);
  const pairItems = new Set(db("SELECT b x FROM contrast WHERE a IN (SELECT item FROM question WHERE lesson = '" + L.lesson +
                               "') UNION SELECT a FROM contrast WHERE b IN (SELECT item FROM question WHERE lesson = '" +
                               L.lesson + "')").map(r => r.x));
  const shape = seq.map(x => x.lesson === L.lesson ? "L" : "O").join("");
  say(seq.every((x, i) => (x.lesson === L.lesson) === (i % 3 !== 2)),
      `答完点下一题：本课两道、对比一道（${shape}）` +
      (seq.every((x, i) => (x.lesson === L.lesson) === (i % 3 !== 2)) ? "" :
       " " + seq.map(x => x.code).join(",") + " 调用：" + calls.map(c => c.path).join(",")));
  say(seq.filter(x => x.lesson !== L.lesson).every(x => pairItems.has(x.item) || x.level === lv),
      "混进来的都是易混对比或同等级的题");
  say(new Set(rightPos).size >= 2, `正确答案在界面上的位置随题变化：${rightPos.join(" ")}`);
  // 点开始：退出按课练，地址回到 #做题
  const other = lv === "N5" ? "N4" : "N5";
  p.pick(p.selects()[0], other);
  p.pick(p.selects()[1], "全部");
  p.btn("开始").click();
  say(await waitFor(() => question(state().current).level === other),
      `点开始：按等级出（${state().current}）`);
  say(await waitFor(() => p.hash() === "#做题"), `地址回到不带 lesson 的 #做题：${p.hash()}`);
  say(await waitFor(() => !p.$$(".bar-top .dyn-v").some(e => e.textContent.includes("练这一课"))),
      "「练这一课」的说明没了");
  const before7 = state().current;
  await p.answerAny();
  p.btn("下一题").click();
  await waitFor(() => state().current !== before7);
  say(question(state().current).level === other && !state().lesson, "之后的下一题也按等级出");
  p.close();

  console.log("七之二、达标喜报");
  p = openPage("#" + encodeURIComponent("做题"));
  await waitFor(() => p.selects().length === 2);
  p.pick(p.selects()[1], "挖空");
  p.btn("开始").click();
  await waitFor(() => p.choices().length === 4);
  q = question(state().current);
  const pt = db(`SELECT i.point, n.label FROM item i JOIN node n ON n.code = i.point WHERE i.code = '${q.item}'`)[0];
  execFileSync(PY, ["-c", "import sqlite3;c=sqlite3.connect('" + PROJ + "/app.db');" +
    "c.execute(\"DELETE FROM mastery WHERE learner='me' AND point=?\", ('" + pt.point + "',));" +
    "c.execute(\"INSERT INTO mastery(learner, point, right, total, mastered) VALUES ('me', ?, 7, 7, 0)\", ('" + pt.point + "',));" +
    "c.commit()"]);
  say(Array.isArray(p.shared().talk), "对照：读得到问老师的消息流（talk）");
  const talkBefore = p.shared().talk.length;
  p.choiceText(origOptions(q)[q.answer]).click();
  say(await waitFor(() => p.verdict().startsWith("○")), "答对，凑满 8/8");
  say(await waitFor(() => p.cardText().includes(`「${pt.label}」达标了`)), `题卡上看得见喜报：「${pt.label}」达标了`);
  say(p.shared().talk.length === talkBefore && !p.shared().talk.some(m => (m.text || "").includes("达标")),
      "问老师的消息流里没有多出喜报");
  p.nav("问老师").click();
  await waitFor(() => p.hash() === "#问老师");
  await sleep(300);
  say(!p.$$(".stream .smsg").some(e => e.textContent.includes("达标了")), "切到问老师页：消息流里没有喜报");
  p.close();

  console.log("七之三、请老师总结：按课练一轮");
  // 题少的一课，好做完一轮
  const S = db("SELECT lesson, count(*) n FROM question WHERE lesson IS NOT NULL GROUP BY lesson" +
               " HAVING count(*) BETWEEN 3 AND 5 ORDER BY lesson LIMIT 1")[0];
  const sTitle = db(`SELECT title FROM lesson WHERE code = '${S.lesson}'`)[0].title;
  db("DELETE FROM chat_message");
  p = openPage("#" + encodeURIComponent("做题") + "?lesson=" + encodeURIComponent(S.lesson));
  await waitFor(() => p.card());
  say(!p.btn("请老师总结这一轮") && !p.btn("结束并请老师总结"), "一轮没做完：没有总结按钮");
  let rounds = 0;
  while (rounds < 20 && !p.btn("请老师总结这一轮")) {
    await p.answerAny();
    await waitFor(() => p.btn("下一题"));
    p.btn("下一题").click();
    await waitFor(() => p.btn("请老师总结这一轮") || (p.card() && !p.btn("下一题")));
    rounds++;
  }
  const ended = state();
  say(!!p.btn("请老师总结这一轮") && p.btn("再来一轮"),
      `做了 ${rounds} 道，一轮做完：卡上有「再来一轮」和「请老师总结这一轮」（${ended.right}/${ended.total}）`);
  say(!p.btn("结束并请老师总结"), "按课练时顶栏没有「结束并请老师总结」");
  slow["/quiz/summary"] = 600;
  calls.length = 0;
  p.btn("请老师总结这一轮").click();
  say(await waitFor(() => p.$$("p.copy").some(e => e.textContent.includes("老师正在看你的作答")), 500),
      "点了：出现「老师正在看你的作答…」");
  say(p.btn("请老师总结这一轮").disabled && p.btn("再来一轮").disabled, "等的时候按钮锁着");
  const sumCard = () => p.$$(".card").find(e => e.textContent.includes(SUMMARY));
  say(await waitFor(() => sumCard(), 4000), "总结出现在做题页的一张卡片上");
  delete slow["/quiz/summary"];
  say(await waitFor(() => !p.$$("p.copy").some(e => e.textContent.includes("老师正在看你的作答"))),
      "等待的那句话收起来了");
  say(calls.some(c => c.path === "/quiz/summary" && c.status === 200), "调了 /quiz/summary");
  const sumLinks = () => p.$$("a").filter(a => ["去问老师接着聊", "读课文", "再练这一课"].includes(a.textContent.trim()));
  const sl = sumLinks().map(a => [a.textContent.trim(), decodeURIComponent(a.getAttribute("href"))]);
  say(sl.some(([t, h]) => t === "去问老师接着聊" && h === "#问老师")
      && sl.some(([t, h]) => t === "读课文" && h === `#教材?lesson=${S.lesson}`),
      `链接：${JSON.stringify(sl)}`);
  say(!!p.btn("再来一轮"), "那张一轮做完的卡还在（再来一轮）");
  const chatRows = db("SELECT role, intent, content FROM chat_message ORDER BY id");
  say(chatRows.length === 2 && chatRows[1].content === SUMMARY && chatRows.every(r => r.intent === "总结")
      && chatRows[0].content.includes(`《${sTitle}》`),
      `对话记录两条：${chatRows.map(r => r.role + "：" + r.content.slice(0, 30)).join(" / ")}`);
  sumLinks().find(a => a.textContent.trim() === "去问老师接着聊").click();
  say(await waitFor(() => p.hash() === "#问老师"), `点「去问老师接着聊」到了 ${p.hash()}`);
  say(await waitFor(() => p.$$(".stream .smsg").some(e => e.textContent.includes(SUMMARY))),
      "问老师页的历史里有这条总结");
  say(p.$$(".stream .smsg").some(e => e.textContent.includes("请老师总结")), "学习者那条（请老师总结）也在");
  p.close();

  console.log("七之四、自由练：答满 5 道才出「结束并请老师总结」");
  p = openPage("#" + encodeURIComponent("做题"));
  await waitFor(() => p.selects().length === 2);
  p.pick(p.selects()[0], "N5");
  p.pick(p.selects()[1], "全部");
  p.btn("开始").click();
  await waitFor(() => p.card());
  const seen = [];
  for (let i = 0; i < 5; i++) {
    await p.answerAny();
    await waitFor(() => p.stat() === `这一轮 ${state().right}/${i + 1}`);
    seen.push(!!p.btn("结束并请老师总结"));
    if (i < 4) {
      const b4 = state().current;
      p.btn("下一题").click();
      await waitFor(() => state().current !== b4);
    }
  }
  say(seen.slice(0, 4).every(x => !x) && seen[4], `第 5 道答完才出按钮：${seen.join(",")}`);
  p.btn("结束并请老师总结").click();
  say(await waitFor(() => p.$$(".card").some(e => e.textContent.includes(SUMMARY))), "总结卡片出来了");
  say(await waitFor(() => !p.btn("下一题") && p.stat() === "这一轮 0/0" && !p.btn("结束并请老师总结")),
      `这一轮结束：题卡收起、计数清零（${p.stat()}）、按钮收起`);
  // 出错时：做题页没有消息流，error 弹成底部的提示条
  const toast = () => (p.$(".toast-no") || {}).textContent || "";
  const vm = p.$("#app")._vnode.component.setupState;
  vm.submitTo("quiz_summary");
  say(await waitFor(() => toast().includes("这一轮还没有做题")), `这一轮 0 道再请总结：提示条「${toast()}」`);
  fake["/quiz/summary"] = [502, { error: "模型这次没有回应（claude 超过 180 秒没有返回），过一会儿再试。" }];
  await waitFor(() => !vm.busy);
  vm.submitTo("quiz_summary");
  say(await waitFor(() => toast().includes("模型这次没有回应")), `模型出错（502）：提示条「${toast()}」`);
  delete fake["/quiz/summary"];
  p.btn("开始").click();
  say(await waitFor(() => p.card() && !p.$$(".card").some(e => e.textContent.includes(SUMMARY))),
      "点开始出新题：总结卡片收起");
  p.close();

  console.log("八、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500 && !c.fake), "没有 5xx（测试自己造的 502 不算）");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
