// kg 多人模式的端到端测试：真服务（gen run --登录）+ kg 真实生成的页面，在 jsdom 里点。
//
//     cd tests/e2e && node multiuser_run.js
//
// 照 kg 搭一份到 /tmp/e2e_multiuser，导入知识点、课文、题目，命令行建一个教师
// （py -m kg 建教师 --库 --密码环境变量，不碰 kg/app.db），起服务带 --登录。
// 端口 8186（MULTIUSER_E2E_PORT 能改）：8197 上跑着常驻的 kg，别的 e2e 用
// 8187-8199。假模型按规则文件回话（DSL_MOCK_SCRIPT）。
//
// Node 的 fetch 不存 cookie，这里自己当浏览器：收到 Set-Cookie 就记下，之后的
// 请求带上；Max-Age=0 就删掉（跟 auth_run.js 一样）。
//
// 按人的操作顺序：
//   一、打开页面没登录 → 被弹到登录页；没有注册的入口
//   二、教师登录 → 回到原来的页面；顶栏有「王老师」「退出」；导航里有「管理」组
//   三、学生管理：建 s1、s2，表里出现；退出 → 回登录页、cookie 删了
//   四、s1 登录：顶栏「小一」；导航里没有「管理」组
//   五、s1 做题一轮：开始 → 交一个答案 → 出批改，库里作答记在 s1
//   六、s1 问老师：老师回答出现，库里对话记在 s1
//   七、s1 直接打 #教材导入：退回首页并提示没有权限；接口 403「需要教师权限」
//   八、s1 改密码；退出 → s2 登录：问老师是空的、做题统计是空的；库里 s2 一条都没有
//   九、服务端没有 5xx、没有 Traceback

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_multiuser";
const PORT = Number(process.env.MULTIUSER_E2E_PORT || 8186);
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const REPLY = "这是老师的回答。";
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

function openPage(hash) {
  const html = fs.readFileSync(WEB + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/" + (hash || ""), runScripts: "outside-only" });
  const w = dom.window;
  w.fetch = browserFetch;
  w.console.log = () => {};
  w.console.warn = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + "/app.js", "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const pg = {
    w, $, $$,
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

async function login(p, user, pw) {
  await waitFor(() => p.hash() === "#登录" && p.field("用户名"));
  p.type(p.field("用户名"), user);
  p.type(p.$('input[type=password]'), pw);
  p.btn("登录").click();
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
    "r = c.post('/quiz/import', json={'form': {'rows': read_bank(BANK)}})",
    "assert r.status_code == 200, r.get_json()",
  ].join("\n")], { cwd: MCP, encoding: "utf8" });
  // 教师只能命令行建。密码从环境变量读，不进命令行
  execFileSync(PY, ["-m", "kg", "建教师", "t1", "--显示名", "王老师", "--库", PROJ + "/app.db",
                    "--密码环境变量", "E2E_TEACHER_PW"],
               { cwd: MCP, encoding: "utf8", env: Object.assign({}, process.env, { E2E_TEACHER_PW: TEACHER_PW }) });
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [{ when: ["意图分类器"],
              reply: '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}' }],
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

    console.log("二、教师登录");
    say(await login(p, "t1", TEACHER_PW), "教师登录成功");
    say(await waitFor(() => p.hash() === "#做题"), `回到了原来的页面：${p.hash()}`);
    say(await waitFor(() => p.navText().includes("王老师") && p.btn("退出")), "顶栏有「王老师」和「退出」");
    say(await waitFor(() => p.nav("学生管理") && p.nav("教材导入")), "导航里有「管理」组：学生管理、教材导入");
    // 页面链接里没有「登录」「改密码」；改密码只在顶栏右边的账号那一块
    const pageLinks = p.$$("nav > a, nav .nav-side a").map(a => a.textContent.trim());
    say(!pageLinks.includes("登录") && !pageLinks.includes("改密码")
        && p.$$("nav .nav-user a").some(a => a.textContent.trim() === "改密码"),
        `登录、改密码不在页面导航里，改密码在顶栏账号区：${pageLinks.join("|")}`);

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

    console.log("四、学生 s1 登录");
    say(await login(p, "s1", "s1-pass"), "s1 登录成功");
    say(await waitFor(() => p.navText().includes("小一")), "顶栏是「小一」");
    say(await waitFor(() => p.nav("做题") && p.nav("问老师")), "学习的页面都在");
    say(!p.nav("学生管理") && !p.nav("教材导入") && !p.navText().includes("管理"),
        `导航里没有「管理」组：${p.navText().replace(/\s+/g, " ")}`);

    console.log("五、做题一轮");
    p.nav("做题").click();
    say(await waitFor(() => p.hash() === "#做题" && p.btn("开始")), "到了做题页");
    p.btn("开始").click();
    say(await waitFor(() => p.choices().length || p.box()), "出了一张题卡");
    if (p.choices().length) p.choices()[0].click();
    else { p.type(p.box(), "x"); p.btn("作答").click(); }
    say(await waitFor(() => p.verdict()), `出了批改：${p.verdict().slice(0, 20)}`);
    const att = db("SELECT learner, count(*) n FROM attempt GROUP BY learner");
    say(JSON.stringify(att) === '[{"learner":"s1","n":1}]', `作答记在 s1：${JSON.stringify(att)}`);

    console.log("六、问老师");
    p.nav("问老师").click();
    say(await waitFor(() => p.hash() === "#问老师" && p.chatBox()), "到了问老师页");
    p.type(p.chatBox(), "てから怎么用");
    p.enter(p.chatBox());
    say(await waitFor(() => p.msgs().some(m => m.who === "老师" && m.text === REPLY)), "老师的回答出现了");
    const chat = db("SELECT learner, role FROM chat_message ORDER BY id");
    say(chat.length === 2 && chat.every(c => c.learner === "s1"), `对话记在 s1：${JSON.stringify(chat)}`);

    console.log("七、直接打管理页");
    calls.length = 0;
    p.w.location.hash = "#" + encodeURIComponent("教材导入");
    say(await waitFor(() => p.hash() !== "#教材导入" && p.toast().includes("没有权限")),
        `退回了 ${p.hash()}，提示「${p.toast()}」`);
    const r = await browserFetch("/import/home", { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ form: {} }) });
    const body = await r.json();
    say(r.status === 403 && body.error === "需要教师权限", `接口本身也拒：${r.status} ${body.error}`);
    say(!calls.some(c => c.path.startsWith("/import/") && c.status === 200), "没有哪个管理接口回了 200");

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
    say(await waitFor(() => p.hash() === "#问老师" && p.chatBox()), "回到问老师页");
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
    // s1 用新密码能登、旧的不能
    const lg = async (u, pw) => (await fetch(BASE + "/auth/login", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ form: { username: u, password: pw } }) })).status;
    say(await lg("s1", "s1-pass") === 400 && await lg("s1", "s1-new-pass") === 200, "s1 旧密码登不上，新的能登");
    p.close();

    console.log("九、服务端");
    say(!/Traceback/.test(log), "服务日志里没有 Traceback");
    say(!calls.some(c => c.status >= 500), `没有 5xx：${JSON.stringify(calls.filter(c => c.status >= 500))}`);
  } catch (e) {
    say(false, "跑挂了：" + (e && e.stack || e));
  }

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("---- 服务日志（末尾）----\n" + log.slice(-2000));
  stop(fail ? 1 : 0);
})();
