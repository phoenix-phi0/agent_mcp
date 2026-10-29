// 单词默写页的端到端测试：真服务 + kg 项目真实生成的页面。
//
//     cd tests/e2e && node dictation_run.js
//
// 照 kg 项目搭一份到 /tmp/e2e_dictation（实体、查询、接口、界面、内容），导入
// 知识点，单词手工插一批（N5 十四个，好控制），gen run 起真服务。页面在 jsdom
// 里跑，按人的操作点。
//
//   导航里有「默写」，切过去：没有词卡，一句提示；顶栏方向、等级、题源默认值
//   N5 开始 → 卡上是意思（去掉 [N5]）和抬头；写片假名、Enter 交 → 对，同一张卡
//     原地出批改；下一个 → 新卡、输入框是空的
//   答错 → ✗、正确的「汉字【读音】意思」、你写的
//   提示 → 卡上首个假名和字数，「提示」按钮收起；答对 → 对（看了提示），库里 hinted=1
//   做满 10 个：一轮结束卡、本轮成绩、错词表（汉字【读音】意思）、再来一轮、练错词
//   练错词 → 出的是这一轮答错的词，题源下拉变成「错词复习」
//   看汉字写读音：卡上是汉字和意思
//   学习进度页：「单词默写」一块、链接 #默写?source=review；点进去直接开一轮
//     错词复习
//   attempt / mastery / score 一行都没有

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = process.env.M || require("path").resolve(__dirname, "../..");
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_dictation";
const PORT = 8191;
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
const dstate = () => db("SELECT * FROM dictation_state WHERE learner = 'me'")[0] || {};
const curWord = () => db(`SELECT * FROM word WHERE id = ${Number(dstate().current_word) || 0}`)[0] || {};
const bare = m => m.replace(/^\[N\d\]\s*/, "");
const label = w => (w.kanji && w.kanji !== w.kana ? `${w.kanji}【${w.kana}】` : w.kana + " ") + bare(w.meaning);
const kata = s => s.replace(/[ぁ-ゖ]/g, c => String.fromCharCode(c.charCodeAt(0) + 0x60));

// 十四个 N5 词，都有汉字（两个方向都能出）
const WORDS = [
  ["会う", "あう", "见面"], ["山", "やま", "山"], ["川", "かわ", "河"], ["花", "はな", "花"],
  ["水", "みず", "水"], ["火", "ひ", "火"], ["木", "き", "树"], ["空", "そら", "天空"],
  ["雨", "あめ", "雨"], ["雪", "ゆき", "雪"], ["風", "かぜ", "风"], ["海", "うみ", "海"],
  ["車", "くるま", "汽车"], ["本", "ほん", "书"],
];

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
  // jsdom 没有 scrollIntoView：记下谁被滚到了、传的什么参数
  const scrolled = [];
  w.Element.prototype.scrollIntoView = function (o) { scrolled.push({ el: this, opts: o }); };
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + "/app.js", "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const pg = {
    w, $, $$,
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    link: t => $$("a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    selects: () => $$(".bar-top select"),
    pick: (sel, v) => { sel.value = v; sel.dispatchEvent(new w.Event("change")); },
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    enterRepeat: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, repeat: true })),
    // 输入法选字中的 Enter（确定这个词，不是交）
    enterComposing: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, isComposing: true })),
    focused: () => w.document.activeElement,
    scrolled,
    after: (a, b) => !!(a && b && (a.compareDocumentPosition(b) & w.Node.DOCUMENT_POSITION_FOLLOWING)),
    line: f => $$(".card .dyn").find(e => f((e.querySelector(".dyn-v") || {}).textContent || "")),
    stat: () => $$(".bar-top .dyn-v").map(e => e.textContent).find(t => t.startsWith("这一轮")) || "",
    card: () => $(".card"),
    cardText: () => $$(".card").map(e => e.textContent).join("\n"),
    lines: () => $$(".card .dyn-v").map(e => e.textContent),
    verdict: () => $$(".card .dyn-v").map(e => e.textContent).find(t => /^[○✗]/.test(t)) || "",
    box: () => $(".card textarea"),
    rows: () => $$("table tbody tr").map(tr => [...tr.querySelectorAll("td")].map(td => td.textContent.trim())),
    close: () => w.close(),
  };
  // 交一个答案：先等新卡（「下一个」收起、输入框出来），再写、Enter
  pg.answer = async text => {
    await waitFor(() => !pg.btn("下一个") && pg.box());
    pg.type(pg.box(), text);
    pg.enter(pg.box());
    await waitFor(() => pg.verdict());
  };
  return pg;
}

(async () => {
  fs.rmSync(PROJ, { recursive: true, force: true });
  execFileSync(PY, ["-c", [
    "import sys, shutil, pathlib, sqlite3",
    "sys.path.insert(0, '.')",
    "from tests.kg.helpers import make_ws, client",
    `ws = pathlib.Path('${PROJ}'); ws.mkdir()`,
    "make_ws(ws)",
    "shutil.copytree('kg/ui', ws / 'ui')",
    "c = client(ws)",
    "assert c.post('/kg/import2', json={'form': {}}).status_code == 200",
    "con = sqlite3.connect(ws / 'app.db')",
    `con.executemany("INSERT INTO word(kanji, kana, meaning, point) VALUES(?, ?, '[N5] ' || ?, 'noun')", ${JSON.stringify(WORDS)})`,
    "con.commit()",
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

  try {
    console.log("一、切到默写");
    let p = openPage("");
    say(await waitFor(() => p.nav("默写") && p.nav("做题")), "导航里有「默写」");
    const navs = p.$$("nav a").map(a => a.textContent.trim());
    say(navs[0] === "知识图谱" && navs.indexOf("默写") === navs.indexOf("做题") + 1,
        `首页还是知识图谱，「默写」紧跟「做题」：${navs.join(" ")}`);
    calls.length = 0;
    p.nav("默写").click();
    say(await waitFor(() => p.hash() === "#默写"), `到了 ${p.hash()}`);
    say(await waitFor(() => calls.some(c => c.path === "/dictation/state" && c.status === 200)), "进来时拉了一次进度");
    say(await waitFor(() => p.selects().length === 3 && p.selects()[0].value === "看中文写日语"
                         && p.selects()[1].value === "全部" && p.selects()[2].value === "随机"),
        "顶栏：方向、等级、题源，默认 看中文写日语 / 全部 / 随机");
    say(!p.card() && p.$$("p.copy").some(e => e.textContent.includes("点上面的「开始」")), "还没开始：没有词卡，有一句提示");

    console.log("二、看中文写日语：答对（片假名、Enter 交）");
    p.pick(p.selects()[1], "N5");
    p.btn("开始").click();
    say(await waitFor(() => p.card() && p.box()), "出了一张词卡，卡里有输入框");
    let w = curWord();
    say(p.lines().includes("N5・看中文写日语") && p.lines().includes(bare(w.meaning)),
        `卡上是抬头和去掉等级的意思「${bare(w.meaning)}」`);
    say(!p.cardText().includes(w.kana) && !p.cardText().includes("[N5]"), "卡上没露出答案，也没有 [N5]");
    say(p.card().contains(p.btn("交")) && p.card().contains(p.btn("提示")), "「交」「提示」在卡里");
    const card1 = p.card();
    await p.answer(kata(w.kana));
    say(p.verdict().startsWith("○"), `写片假名「${kata(w.kana)}」判对：${p.verdict()}`);
    say(p.lines().includes("正确：" + label(w)) && p.lines().includes("你写的：" + kata(w.kana)),
        `批改：正确的写法和你写的（${label(w)}）`);
    say(p.card() === card1, "判完是同一张卡原地更新");
    say(await waitFor(() => !p.box() && p.btn("下一个")), "判完：输入框收起，出现「下一个」");
    {
      const nb = p.btn("下一个");
      const v = p.line(t => /^[○✗]/.test(t));
      const right = p.line(t => t.startsWith("正确："));
      const mine = p.line(t => t.startsWith("你写的："));
      say(p.after(v, nb) && p.after(nb, right) && p.after(nb, mine)
          && !p.$$(".card .dyn").some(e => p.after(v, e) && p.after(e, nb))
          && p.$$(".card .dyn").filter(e => p.after(v, e)).every(e => p.after(nb, e)),
          "「下一个」紧跟对错，正确写法、你写的、补充都排在它后面");
    }
    say(await waitFor(() => p.focused() === p.btn("下一个")), "判完焦点落在「下一个」上");
    say(p.scrolled.some(x => x.el === p.btn("下一个") && x.opts && x.opts.block === "nearest"),
        "「下一个」滚进了看得见的地方（scrollIntoView block:nearest）");
    // 交的那次 Enter 不连带翻页；按住 Enter 的连发也不算
    await sleep(300);
    say(curWord().id === w.id && !calls.some(c => c.path === "/dictation/next") && p.verdict(),
        "交答案的那次 Enter 没有连带翻到下一个");
    p.enterRepeat(p.btn("下一个"));
    await sleep(300);
    say(curWord().id === w.id && !calls.some(c => c.path === "/dictation/next"), "按住 Enter 的连发不会翻页");
    say(await waitFor(() => p.stat() === "这一轮 1/1"), `顶栏成绩：${p.stat()}`);

    console.log("三、答错");
    const seen = [w.id];
    // 焦点在「下一个」上，Enter 就是下一个
    p.enter(p.focused());
    say(await waitFor(() => p.box() && p.box().value === "" && !p.verdict()), "Enter：新卡，输入框是空的，没有上一张的批改");
    say(calls.filter(c => c.path === "/dictation/next").length === 1, "一次 Enter 只发了一次「下一个」");
    say(await waitFor(() => p.focused() === p.box()), "新卡：焦点回到输入框，接着写");
    say(p.card() !== card1, "换了一张新卡（翻页）");
    w = curWord();
    seen.push(w.id);
    const wrongs = [w];
    // 输入法选字时的 Enter 不交
    const answers0 = calls.filter(c => c.path === "/dictation/answer").length;
    p.type(p.box(), "ちがう");
    p.enterComposing(p.box());
    await sleep(300);
    say(!p.verdict() && calls.filter(c => c.path === "/dictation/answer").length === answers0 && p.box(),
        "输入法选字时按 Enter 不交");
    await p.answer("ちがう");
    say(p.verdict().startsWith("✗"), `判错：${p.verdict()}`);
    say(p.lines().includes("正确：" + label(w)) && p.lines().includes("你写的：ちがう"), `给了正确的「${label(w)}」和你写的`);

    console.log("四、提示");
    p.btn("下一个").click();
    await waitFor(() => p.box() && !p.verdict());
    w = curWord();
    seen.push(w.id);
    p.btn("提示").click();
    say(await waitFor(() => p.lines().some(t => t.includes(`「${w.kana[0]}」`) && t.includes(`一共 ${w.kana.length} 个字`))),
        `卡上出了提示：首个假名「${w.kana[0]}」、${w.kana.length} 个字`);
    say(!p.btn("提示") && p.box(), "看过提示：「提示」收起，还能写");
    await p.answer(w.kanji);
    say(p.verdict().startsWith("○") && p.verdict().includes("提示"), `写汉字判对，注明看了提示：${p.verdict()}`);
    say(!p.lines().some(t => t.includes(`一共 ${w.kana.length} 个字`)), "判完提示那一行收起（正确写法里都有了）");
    const last = db("SELECT correct, hinted, direction FROM word_attempt ORDER BY id DESC LIMIT 1")[0];
    say(last.correct === 1 && last.hinted === 1 && last.direction === "meaning", "库里记 correct=1、hinted=1");

    console.log("五、做满一轮");
    for (let i = 3; i < 10; i++) {
      p.btn("下一个").click();
      await waitFor(() => p.box() && !p.verdict());
      w = curWord();
      seen.push(w.id);
      if (i % 2) { wrongs.push(w); await p.answer("x"); } else await p.answer(w.kana);
    }
    say(new Set(seen).size === 10, `一轮 10 个词不重复：${new Set(seen).size}`);
    p.btn("下一个").click();
    say(await waitFor(() => p.btn("再来一轮") && p.btn("练错词")), "一轮结束：「再来一轮」「练错词」");
    const right = 10 - wrongs.length;
    say(p.cardText().includes(`答对 ${right} 个，共 10 个`), `本轮成绩：答对 ${right} 个`);
    const rows = p.rows();
    say(rows.length === wrongs.length && wrongs.every((x, i) => rows[i][0] === label(x)),
        `错词表 ${rows.length} 行：${rows.map(r => r[0]).join("、")}`);
    say(!p.box(), "一轮结束：没有输入框");

    console.log("六、练错词");
    p.btn("练错词").click();
    say(await waitFor(() => p.box() && p.card()), "出了词卡");
    const wrongIds = new Set(wrongs.map(x => x.id));
    say(wrongIds.has(curWord().id), `出的是这一轮答错的：${label(curWord())}`);
    say(await waitFor(() => p.selects()[2].value === "错词复习"), "题源下拉变成「错词复习」");
    const reviewSeen = [];
    for (let i = 0; i < 10 && !p.btn("再来一轮"); i++) {
      await waitFor(() => (p.box() && !p.verdict()) || p.btn("再来一轮"));
      if (p.btn("再来一轮")) break;
      reviewSeen.push(curWord().id);
      await p.answer(curWord().kana);
      p.btn("下一个").click();
      await waitFor(() => (p.box() && !p.verdict()) || p.btn("再来一轮"));
    }
    say(reviewSeen.length === wrongIds.size && reviewSeen.every(x => wrongIds.has(x)),
        `错词复习一轮就是错词本里的 ${reviewSeen.length} 个`);

    console.log("七、看汉字写读音");
    p.pick(p.selects()[0], "看汉字写读音");
    p.pick(p.selects()[2], "随机");
    p.btn("开始").click();
    say(await waitFor(() => p.lines().some(t => t.startsWith("N5・看汉字写读音"))), "抬头是「N5・看汉字写读音」");
    w = curWord();
    say(p.lines().includes(w.kanji) && p.lines().includes("意思：" + bare(w.meaning)), `卡上是汉字「${w.kanji}」和意思`);
    await p.answer(w.kanji);
    say(p.verdict().startsWith("✗"), "看汉字写读音写汉字：判错");
    p.btn("下一个").click();
    await waitFor(() => p.box() && !p.verdict());
    w = curWord();
    await p.answer(w.kana);
    say(p.verdict().startsWith("○"), `写读音「${w.kana}」判对`);
    p.close();

    console.log("八、学习进度页");
    p = openPage("");
    await waitFor(() => p.nav("学习进度"));
    p.nav("学习进度").click();
    say(await waitFor(() => p.$$(".dyn-v").some(e => e.textContent.startsWith("练过 "))), "有「单词默写」一块");
    const text = p.$$(".dyn-v").map(e => e.textContent).find(t => t.startsWith("练过 "));
    say(/练过 \d+ 个词，默写 \d+ 次，正确率 \d+%，错词本 \d+ 个/.test(text), `统计：${text}`);
    const book = db("SELECT count(*) n FROM word_attempt")[0].n;
    say(book > 0, `word_attempt 有 ${book} 行`);
    const a = p.link("去默写");
    say(a && decodeURIComponent(a.getAttribute("href")) === "#默写?source=review", `链接：${a && decodeURIComponent(a.getAttribute("href"))}`);
    p.close();
    calls.length = 0;
    p = openPage("#" + encodeURIComponent("默写") + "?source=review");
    say(await waitFor(() => calls.some(c => c.path === "/dictation/load" && c.status === 200)), "带 source=review 打开：调了载入");
    say(await waitFor(() => p.box() && p.selects().length === 3 && p.selects()[2].value === "错词复习"),
        "一打开就是一轮错词复习，题源是「错词复习」");
    const inBook = db("SELECT DISTINCT word FROM word_attempt WHERE direction = 'reading' AND correct = 0").map(r => r.word);
    say(inBook.includes(curWord().id), `出的是读音方向错词本里的：${label(curWord())}`);
    p.close();

    console.log("九、不碰学习记录");
    for (const t of ["attempt", "mastery", "score"]) {
      const n = db(`SELECT count(*) n FROM ${t}`)[0].n;
      say(n === 0, `${t} 没有行：${n}`);
    }
  } catch (e) {
    say(false, "出错：" + (e.stack || e));
  }

  console.log(`\n通过 ${pass}，失败 ${fail}`);
  stop(fail ? 1 : 0);
})();
