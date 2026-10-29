// kg 多人模式的端到端测试：真服务（gen run --登录）+ kg 真实生成的页面，在 jsdom 里点。
//
//     cd tests/e2e && node multiuser_run.js
//
// 照 kg 搭一份到 /tmp/e2e_multiuser，导入知识点、课文、题目、单词，命令行建一个教师
// （py -m kg 建教师 --库 --密码环境变量，不碰 kg/app.db），起服务带 --登录。
// 端口 8186（MULTIUSER_E2E_PORT 能改）：8197 上跑着常驻的 kg，别的 e2e 用
// 8187-8199。假模型按规则文件回话（DSL_MOCK_SCRIPT）。
//
// Node 的 fetch 不存 cookie，这里自己当浏览器：收到 Set-Cookie 就记下，之后的
// 请求带上；Max-Age=0 就删掉（跟 auth_run.js 一样）。
//
// 学生端、教师端是两个页面（引擎按界面的「端」拆的，gen/project.py 的 split_pages）：
// 学生端 /（web/index.html + app.js），教师端 /teacher（web/teacher.html + teacher.js）。
//
// 按人的操作顺序：
//   一、打开学生端没登录 → 被弹到登录页；没有注册的入口。打开教师端没登录 → 也是
//       登录页，上面标着「教师端」，标题「…·教师端」
//   二、教师在学生端登录 → 提示去教师端、跳到 /teacher；打开 /teacher 已经登着，落在
//       「学情」；顶栏「教师端」标识、「王老师」「退出」「打开学生端」；导航只有教师页
//   三、学生管理：建 s1、s2，表里出现；退出 → 回登录页、cookie 删了
//   四、s1 在教师端登录：被拒（「这是教师端」），cookie 删了；到学生端登录：落在学生端
//       首页；顶栏「小一」；学习页都在，看不到教师页
//   五、s1 做题一轮、默写一个（写错）：库里记在 s1
//   六、s1 问老师：老师回答出现，库里对话记在 s1
//   七、s1 在学生端直接打 #教材导入、#学情：退回首页并提示在教师端；接口 403「需要教师
//       权限」。登着学生打开 /teacher：回登录页说清楚，不退出、一个 403 都没有
//   八、s1 改密码；退出 → s2 登录：问老师是空的、做题统计是空的；库里 s2 一条都没有
//   九、教师在教师端再登录 → 学情里看到小一的数据（作答、正确率、错词本）→ 点进小一：
//       最近作答、错词本、问老师记录 → 请 AI 写学情总结（假模型）：等待提示、出结果、存库
//   十、教师在教师端直接打 #做题：退回学情并提示在学生端，没去调做题接口；接口 403
//       「教师账号不参与学习」；登着教师打开学生端 #默写：送去 /teacher，一个 403 都没有；
//       库里没有教师的学习记录
//   十一、服务端没有 5xx、没有 Traceback

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM, VirtualConsole } = require("jsdom");

const MCP = process.env.M || require("path").resolve(__dirname, "../..");
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_multiuser";
const PORT = Number(process.env.MULTIUSER_E2E_PORT || 8186);
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const REPLY = "这是老师的回答。";
const SUMMARY = "学情总结：小一刚开始练，做题和默写各一次，数据还少。";
const TEACHER_PW = "teach-e2e-1";

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

// 浏览器的 cookie：一个 jar，所有页面共用（跟真浏览器一样，换页不丢登录）
let jar = "";
const calls = [];
async function browserFetch(u, o = {}) {
  const url = new URL(u, BASE);
  const headers = Object.assign({}, o.headers || {});
  if (jar) headers["Cookie"] = `zs_auth=${jar}`;
  const r = await fetch(url, { ...o, headers, signal: undefined });
  const sets = r.headers.getSetCookie ? r.headers.getSetCookie() : [];
  for (const c of sets) {
    const m = /^zs_auth=([^;]*)/.exec(c);
    if (!m) continue;
    jar = (!m[1] || /Max-Age=0|expires=Thu, 01 Jan 1970/i.test(c)) ? "" : m[1];
  }
  calls.push({ path: url.pathname, status: r.status });
  return r;
}

// path：/ 是学生端，/teacher 是教师端。页面要换到别的地址（location.href = "/teacher"）
// 时 jsdom 不真的跳，只报一条「Not implemented: navigation」：记在 pg.left 里
function openPage(hash, path = "/") {
  const name = path === "/" ? "index" : path.slice(1);
  const html = fs.readFileSync(WEB + `/${name}.html`, "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const left = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => { if (/navigation/i.test(e.message)) left.push(e.message); });
  const dom = new JSDOM(html, { url: BASE + path + (hash || ""), runScripts: "outside-only", virtualConsole: vc });
  const w = dom.window;
  w.fetch = browserFetch;
  w.console.log = () => {};
  w.console.warn = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + (path === "/" ? "/app.js" : `/${name}.js`), "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const pg = {
    w, $, $$, left,
    title: () => w.document.title,
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    navText: () => ($("nav") || {}).textContent || "",
    hash: () => decodeURIComponent(w.location.hash),
    toast: () => ($(".toast") || {}).textContent || "",
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    // 按标签找输入框（标签后面的必填星号不算）
    field: lbl => {
      const l = $$("label.field").find(x => (x.querySelector(".lbl") || {}).textContent.replace("*", "").trim() === lbl);
      return l && l.querySelector("input, textarea, select");
    },
    rows: () => $$("table tbody tr").map(tr => [...tr.querySelectorAll("td")].map(td => td.textContent.trim())),
    msgs: () => $$(".stream .smsg").map(m => ({
      who: (m.querySelector(".who") || {}).textContent || "",
      text: (m.querySelector(".body") || {}).textContent || "",
    })),
    choices: () => $$(".card .choice"),
    box: () => $(".card textarea"),
    verdict: () => $$(".card .dyn.prose .dyn-v").map(e => e.textContent).find(t => /^[○✗]/.test(t)) || "",
    chatBox: () => $(".screen textarea"),
    close: () => w.close(),
  };
  return pg;
}

async function typeLogin(p, user, pw) {
  await waitFor(() => p.hash() === "#登录" && p.field("用户名"));
  p.type(p.field("用户名"), user);
  p.type(p.$('input[type=password]'), pw);
  p.btn("登录").click();
}
async function login(p, user, pw) {
  await typeLogin(p, user, pw);
  return waitFor(() => p.hash() !== "#登录" && jar);
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
    "assert c.post('/word/import2', json={'form': {'file': 'content/words.jsonl'}}).status_code == 200",
    "r = c.post('/quiz/import', json={'form': {'rows': read_bank(BANK)}})",
    "assert r.status_code == 200, r.get_json()",
  ].join("\n")], { cwd: MCP, encoding: "utf8" });
  // 教师只能命令行建。密码从环境变量读，不进命令行
  execFileSync(PY, ["-m", "kg", "建教师", "t1", "--显示名", "王老师", "--库", PROJ + "/app.db",
                    "--密码环境变量", "E2E_TEACHER_PW"],
               { cwd: MCP, encoding: "utf8", env: Object.assign({}, process.env, { E2E_TEACHER_PW: TEACHER_PW }) });
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [{ when: ["意图分类器"],
              reply: '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}' },
            { when: ["教研"], reply: SUMMARY, delay: 1 }],
    default: REPLY,
  }));

  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器", "--登录"],
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
  say(log.includes("要求登录（多人模式）"), "启动日志说了是多人模式");

  try {
    console.log("一、没登录");
    let p = openPage("#做题");
    say(await waitFor(() => p.hash() === "#登录"), `被弹到登录页：${p.hash()}`);
    say(!p.btn("没有账号？注册") && !p.$$("button, a").some(e => e.textContent.includes("注册")),
        "登录页上没有注册的入口");
    say(!p.$("nav"), "登录页上不显示导航");
    say(p.title() === "e2e_multiuser" && !p.$(".page-end"), `学生端：标题 ${p.title()}，登录框上没有端的标识`);
    let t = openPage("", "/teacher");
    say(await waitFor(() => t.hash() === "#登录"), `教师端没登录：也到登录页：${t.hash()}`);
    say(await waitFor(() => t.$(".page-end") && t.$(".page-end").textContent.trim() === "教师端")
        && t.title() === "e2e_multiuser·教师端", `登录框上标着「教师端」，标题 ${t.title()}`);
    t.close();

    console.log("二、教师在学生端登录：送去教师端");
    await typeLogin(p, "t1", TEACHER_PW);
    say(await waitFor(() => p.left.length && p.toast().includes("正在打开 /teacher")),
        `提示去教师端、跳了一次：「${p.toast()}」 ${p.left.length}`);
    say(!!jar, "登录本身成功了（cookie 在，到教师端不用再登）");
    say(!calls.some(c => c.status === 403), `没有 403：${JSON.stringify(calls.filter(c => c.status === 403))}`);
    p.close();
    p = openPage("", "/teacher");
    // 空地址落在第一个界面（学情）上，地址栏不改；看导航里亮的是哪一个
    const active = () => (p.$("nav a.active") || {}).textContent || "";
    say(await waitFor(() => active().trim() === "学情" && p.hash() === ""),
        `打开 /teacher：已经登着，落地「学情」：${active()} ${p.hash()}`);
    say(await waitFor(() => p.navText().includes("王老师") && p.btn("退出")), "顶栏有「王老师」和「退出」");
    say(await waitFor(() => p.$("nav .nav-badge") && p.$("nav .nav-badge").textContent.trim() === "教师端"
                          && p.$("nav").classList.contains("nav-role-teacher")),
        "顶栏最前面是「教师端」标识，整条换了颜色（nav-role-teacher）");
    const teacherPages = () => p.$$("nav > a, nav .nav-side a").map(a => a.textContent.trim());
    say(await waitFor(() => teacherPages().join("|") === "学情|学生管理|AI老师设定|教材导入"),
        `导航只有教师页：${teacherPages().join("|")}`);
    say(!["知识图谱", "做题", "默写", "问老师", "教材", "学习进度"].some(t => p.nav(t)) && !p.$("nav .nav-side"),
        "没有学生的学习页、没有「管理」那组");
    const home = p.$("nav .nav-home a");
    say(home && home.textContent.trim() === "打开学生端" && home.getAttribute("href") === "/"
        && home.getAttribute("target") === "_blank", "顶栏有「打开学生端」（新标签页开 /）");
    say(p.$$("nav .nav-user a").some(a => a.textContent.trim() === "改密码"), "改密码在顶栏账号区");
    say(await waitFor(() => p.$$(".screen").some(e => e.textContent.includes("还没有学生"))),
        "学情页：还没有学生");
    say(!calls.some(c => c.status === 403), `落地过程中没有 403：${JSON.stringify(calls.filter(c => c.status === 403))}`);

    console.log("三、学生管理：建两个学生");
    p.nav("学生管理").click();
    say(await waitFor(() => p.hash() === "#学生管理" && p.field("初始密码（至少6位）")), "到了学生管理页");
    for (const [u, label, pw] of [["s1", "小一", "s1-pass"], ["s2", "小二", "s2-pass"]]) {
      p.type(p.field("用户名"), u);
      p.type(p.field("显示名"), label);
      p.type(p.field("初始密码（至少6位）"), pw);
      p.btn("建账号").click();
      say(await waitFor(() => p.rows().some(r => r[0] === u)), `建了 ${u}，学生表里有它`);
      say(await waitFor(() => p.field("用户名").value === ""), "建完输入框清空了");
    }
    const users = db("SELECT username, role, display_name FROM user ORDER BY username");
    say(JSON.stringify(users.map(u => [u.username, u.role])) === '[["s1","student"],["s2","student"],["t1","teacher"]]',
        `库里：${JSON.stringify(users)}`);
    p.btn("退出").click();
    say(await waitFor(() => p.hash() === "#登录" && jar === ""), "退出：回到登录页，cookie 删了");

    console.log("四、学生 s1：教师端登录被拒，学生端登录");
    calls.length = 0;
    await typeLogin(p, "s1", "s1-pass");
    say(await waitFor(() => p.toast().includes("这是教师端") && jar === "" && p.hash() === "#登录" && !p.$("nav")),
        `在教师端登录被拒：「${p.toast()}」，cookie 删了，还在登录页`);
    say(!calls.some(c => c.status === 403 || c.path.startsWith("/report/")), "没进学情、没有 403");
    p.close();
    p = openPage("");
    calls.length = 0;
    say(await login(p, "s1", "s1-pass"), "s1 在学生端登录成功");
    say(await waitFor(() => p.navText().includes("小一")), "顶栏是「小一」");
    say(await waitFor(() => p.hash() === "#知识图谱"), `落在学生端首页：${p.hash()}`);
    say(await waitFor(() => ["知识图谱", "做题", "默写", "问老师", "教材", "学习进度"].every(t => p.nav(t))),
        "学习的页面都在");
    say(!p.nav("学情") && !p.nav("学生管理") && !p.nav("教材导入") && !p.navText().includes("管理"),
        `看不到教师页：${p.navText().replace(/\s+/g, " ")}`);
    say(!p.$("nav .nav-badge") && !p.$("nav").classList.contains("nav-role-teacher"), "没有「教师端」标识");

    console.log("五、做题一轮、默写一个");
    p.nav("做题").click();
    say(await waitFor(() => p.hash() === "#做题" && p.btn("开始")), "到了做题页");
    p.btn("开始").click();
    say(await waitFor(() => p.choices().length || p.box()), "出了一张题卡");
    if (p.choices().length) p.choices()[0].click();
    else { p.type(p.box(), "x"); p.btn("作答").click(); }
    say(await waitFor(() => p.verdict()), `出了批改：${p.verdict().slice(0, 20)}`);
    const att = db("SELECT learner, count(*) n FROM attempt GROUP BY learner");
    say(JSON.stringify(att) === '[{"learner":"s1","n":1}]', `作答记在 s1：${JSON.stringify(att)}`);
    p.nav("默写").click();
    say(await waitFor(() => p.hash() === "#默写" && p.btn("开始")), "到了默写页");
    p.btn("开始").click();
    say(await waitFor(() => p.box() && p.btn("交")), "出了一个词");
    p.type(p.box(), "ちがう");
    p.btn("交").click();
    say(await waitFor(() => p.btn("下一个")), "判完了");
    const wa = db("SELECT learner, correct FROM word_attempt");
    say(JSON.stringify(wa) === '[{"learner":"s1","correct":0}]', `默写记在 s1、错了：${JSON.stringify(wa)}`);

    console.log("六、问老师");
    p.nav("问老师").click();
    say(await waitFor(() => p.hash() === "#问老师" && p.chatBox()), "到了问老师页");
    p.type(p.chatBox(), "てから怎么用");
    p.enter(p.chatBox());
    say(await waitFor(() => p.msgs().some(m => m.who === "老师" && m.text === REPLY)), "老师的回答出现了");
    const chat = db("SELECT learner, role FROM chat_message ORDER BY id");
    say(chat.length === 2 && chat.every(c => c.learner === "s1"), `对话记在 s1：${JSON.stringify(chat)}`);

    console.log("七、学生直接打教师页");
    for (const page of ["教材导入", "学情"]) {
      calls.length = 0;
      p.w.location.hash = "#" + encodeURIComponent(page);
      say(await waitFor(() => p.hash() === "#知识图谱" && p.toast().includes(`「${page}」在教师端（/teacher）`)),
          `#${page}：退回了 ${p.hash()}，提示「${p.toast()}」`);
      say(!calls.some(c => c.path.startsWith("/import/") || c.path.startsWith("/report/")),
          "没去调教师端的接口");
    }
    for (const path of ["/import/home", "/report/home"]) {
      const r = await browserFetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify({ form: {} }) });
      const body = await r.json();
      say(r.status === 403 && body.error === "需要教师权限", `接口本身也拒 ${path}：${r.status} ${body.error}`);
    }
    calls.length = 0;
    t = openPage("", "/teacher");
    say(await waitFor(() => t.hash() === "#登录" && t.toast().includes("现在登录的是学生账号（小一）")),
        `登着学生打开 /teacher：回登录页「${t.toast()}」`);
    await sleep(200);
    say(!!jar && !calls.some(c => c.status === 403 || c.path.startsWith("/report/")),
        `没把学生退出（别的标签页还在用），没调学情、没有 403：${JSON.stringify(calls)}`);
    t.close();

    console.log("八、改密码、换 s2");
    p.$$("nav a").find(a => a.textContent.trim() === "改密码").click();
    say(await waitFor(() => p.hash() === "#改密码" && p.field("旧密码")), "到了改密码页");
    p.type(p.field("旧密码"), "s1-pass");
    p.type(p.field("新密码（至少6位）"), "s1-new-pass");
    p.type(p.field("再输一次新密码"), "s1-new-pass");
    p.btn("改密码").click();
    say(await waitFor(() => p.toast().includes("密码改好了")), `提示：${p.toast()}`);
    p.btn("退出").click();
    say(await waitFor(() => p.hash() === "#登录" && jar === ""), "s1 退出");
    p.close();

    p = openPage("#问老师");
    say(await login(p, "s2", "s2-pass"), "s2 登录成功");
    say(await waitFor(() => p.hash() === "#问老师" && p.chatBox()), "回到问老师页（学生端的页面，照常回来处）");
    await waitFor(() => calls.some(c => c.path === "/teacher/state" && c.status === 200));
    await sleep(200);
    say(p.msgs().length === 0, `s2 的问老师是空的（看不到 s1 的对话）：${p.msgs().length} 条`);
    p.nav("做题").click();
    say(await waitFor(() => p.hash() === "#做题" && p.btn("开始")), "s2 的做题页：还没开始");
    say(!p.$(".card"), "没有 s1 那张题卡");
    const s2rows = db("SELECT (SELECT count(*) FROM attempt WHERE learner='s2') a," +
                      " (SELECT count(*) FROM chat_message WHERE learner='s2') c," +
                      " (SELECT count(*) FROM quiz_state WHERE learner='s2' AND current IS NOT NULL AND current != '') q")[0];
    say(s2rows.a === 0 && s2rows.c === 0 && s2rows.q === 0, `库里 s2 一条记录都没有：${JSON.stringify(s2rows)}`);
    const lg = async (u, pw) => (await fetch(BASE + "/auth/login", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ form: { username: u, password: pw } }) })).status;
    say(await lg("s1", "s1-pass") === 400 && await lg("s1", "s1-new-pass") === 200, "s1 旧密码登不上，新的能登");
    p.btn("退出").click();
    say(await waitFor(() => p.hash() === "#登录" && jar === ""), "s2 退出");
    p.close();

    console.log("九、教师看学情");
    calls.length = 0;
    p = openPage("", "/teacher");
    say(await login(p, "t1", TEACHER_PW), "教师在教师端再登录");
    say(await waitFor(() => p.hash() === "#学情"), `落地学情：${p.hash()}`);
    const rowOf = name => p.rows().find(r => r[0] === name);
    say(await waitFor(() => rowOf("小一") && rowOf("小二")), `全班表有小一、小二：${JSON.stringify(p.rows().slice(0, 3))}`);
    // 列：学生 最近学习 作答数 近期正确率 平均得分 已掌握 薄弱知识点 错词本
    const r1 = rowOf("小一") || [];
    const s1att = db("SELECT correct FROM attempt WHERE learner='s1'");
    say(r1[1] && r1[2] === "1" && r1[3] === (s1att[0].correct ? "100%" : "0%") && r1[7] === "1",
        `小一：最近学习 ${r1[1]}、作答 1、近期正确率 ${r1[3]}、错词本 1：${JSON.stringify(r1)}`);
    say(JSON.stringify((rowOf("小二") || []).slice(2)) === '["0","—","—","0","—","0"]',
        `小二：什么都没做：${JSON.stringify(rowOf("小二"))}`);
    say(p.$$("table").length >= 2 || p.$$(".screen").some(e => e.textContent.includes("全班薄弱点")),
        "下面有全班薄弱点");
    const link = p.$$("table tbody a").find(a => a.textContent.trim() === "小一");
    say(!!link, "小一是个链接");
    p.w.location.hash = link.getAttribute("href");
    say(await waitFor(() => p.hash() === "#学情?student=s1"
                            && p.$$(".screen").some(e => e.textContent.includes("小一（s1）"))),
        `进了小一：${p.hash()}`);
    const page = () => (p.$(".screen") || {}).textContent || "";
    say(await waitFor(() => page().includes("最近作答") && page().includes("默写错词本") && page().includes("问老师记录")),
        "有最近作答、默写错词本、问老师记录");
    say(page().includes("てから怎么用") && page().includes(REPLY.slice(0, 6)), "问老师记录里有 s1 问的和老师答的");
    say(p.rows().some(r => r.includes(s1att[0].correct ? "对" : "错")), "最近作答表有那一道");
    p.btn("请 AI 写学情总结").click();
    say(await waitFor(() => page().includes("AI 正在看这个学生的数据")), "等的时候有提示");
    say(await waitFor(() => page().includes(SUMMARY), 10000), "AI 学情总结出来了");
    say(await waitFor(() => !page().includes("AI 正在看这个学生的数据")), "提示收起");
    const rep = db("SELECT learner, written_by FROM learner_report");
    say(JSON.stringify(rep) === '[{"learner":"s1","written_by":"t1"}]', `存进了 learner_report：${JSON.stringify(rep)}`);
    say(db("SELECT count(*) n FROM chat_message")[0].n === 2, "学生的问老师记录没多（总结不进 chat_message）");

    console.log("十、教师直接打学生页");
    calls.length = 0;
    p.w.location.hash = "#" + encodeURIComponent("做题");
    say(await waitFor(() => p.hash() === "#学情" && p.toast().includes("「做题」在学生端（/）")),
        `退回了 ${p.hash()}，提示「${p.toast()}」`);
    await sleep(200);
    say(!calls.some(c => c.path.startsWith("/quiz/")), `没去调做题的接口：${JSON.stringify(calls)}`);
    const rq = await browserFetch("/quiz/state", { method: "POST", headers: { "Content-Type": "application/json" },
                                                   body: JSON.stringify({ form: {} }) });
    const bq = await rq.json();
    say(rq.status === 403 && bq.error === "教师账号不参与学习，请用学生账号", `接口本身也拒：${rq.status} ${bq.error}`);
    p.close();
    // 登着教师打开学生端 #默写：先认出是教师，送去 /teacher——不会先进默写页收 403
    calls.length = 0;
    p = openPage("#" + encodeURIComponent("默写"));
    say(await waitFor(() => p.left.length && p.toast().includes("正在打开 /teacher")),
        `学生端 #默写：送去教师端「${p.toast()}」`);
    await sleep(300);
    say(!calls.some(c => c.status === 403), `没有一个 403：${JSON.stringify(calls.filter(c => c.status === 403))}`);
    const tdata = db("SELECT (SELECT count(*) FROM attempt WHERE learner='t1') + (SELECT count(*) FROM word_attempt WHERE learner='t1')" +
                     " + (SELECT count(*) FROM chat_message WHERE learner='t1') + (SELECT count(*) FROM quiz_state WHERE learner='t1')" +
                     " + (SELECT count(*) FROM learner_pref WHERE learner='t1') n")[0].n;
    say(tdata === 0, `库里没有教师的学习记录：${tdata}`);
    p.close();
    console.log("十一、服务端");
    say(!/Traceback/.test(log), "服务日志里没有 Traceback");
    say(!calls.some(c => c.status >= 500), `没有 5xx：${JSON.stringify(calls.filter(c => c.status >= 500))}`);
  } catch (e) {
    say(false, "跑挂了：" + (e && e.stack || e));
  }

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("---- 服务日志（末尾）----\n" + log.slice(-2000));
  stop(fail ? 1 : 0);
})();
